"""Unleashed, card by card (BACKLOG.md section D): the sentences the corpus pass
found wrong or missing, each played through the engine."""

from __future__ import annotations

from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext
from riftbound.core.player import Rune, RuneDeck
from riftbound.core.state import ChainItem
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import (_always, _cast_now, _deck, _fight, _pick, _play_spell, _setup, _unit)


def _ctx(loop, p, card=None):
    o = loop.gs.get_player(loop.gs.other(p.name))
    return EffectContext(loop, card or SpellCard(name="Effect"), p, o, loop.gs.battlefields[0], {})


def _ability(loop, side, effect):
    return next(i for i, e in enumerate(loop.activatable_abilities(side))
                if e.get("eff") is not None and e["eff"].effect == effect)


def _attack_at(loop, bf_idx=0):
    bf = loop.gs.battlefields[bf_idx]
    loop.gs.showdown_active, loop.gs.showdown_bf_idx, loop.gs.showdown_attacker = True, bf_idx, "A"
    loop._open_combat(bf, "A")
    return bf


def test_mischievous_marai_hits_only_when_played_to_a_battlefield():
    """'When you play me at a battlefield, deal 2 to an enemy unit here.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    enemy = _unit("Enemy", 5)
    bf.add_unit("B", enemy)
    loop._play_unit(CARD_REGISTRY["Mischievous Marai"].instantiate(), "A")
    assert enemy.damage == 0
    loop._play_unit(CARD_REGISTRY["Mischievous Marai"].instantiate(), "A", bf=bf)
    assert enemy.damage == 2


def test_smite_banishes_what_would_die_this_turn():
    """'Deal 3 to a unit at a battlefield. If it would die this turn, banish it
    instead.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Smite")
    assert enemy.card in b.banished and enemy.card not in b.trash


def test_towering_pairofant_counts_any_units_death():
    """'If a unit died this turn, I enter ready.'"""
    loop, a, b = _setup()
    loop.gs.friendly_unit_died_this_turn["B"] = True
    assert loop._play_unit(CARD_REGISTRY["Towering Pairofant"].instantiate(), "A").ready


def test_monster_harpoon_deals_four_with_a_facedown_card():
    """'Deal 2 to a unit at a battlefield. If you control a facedown card, deal 4
    to it instead.'"""
    from riftbound.core.battlefield import FacedownCard
    loop, a, b = _setup()
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Monster Harpoon")
    assert enemy.damage == 2
    loop.gs.battlefields[1].add_unit("A", _unit("Holder", 1))
    loop.gs.battlefields[1].facedown = FacedownCard(card=SpellCard(name="Hidden"), owner="A", turn_hidden=0)
    _cast_now(loop, a, "Monster Harpoon")
    assert enemy.damage == 6


def test_right_of_conquest_draws_one_plus_one_per_battlefield():
    """'Draw 1, then draw 1 for each battlefield you or your allies control.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    loop.gs.battlefields[0].add_unit("A", _unit("H1", 1))
    loop.gs.battlefields[1].add_unit("A", _unit("H2", 1))
    _cast_now(loop, a, "Right of Conquest")
    assert len(a.hand) == 3


def test_red_brambleback_doubles_conquer_effects_here():
    """'Your conquer effects for conquering here trigger an additional time.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.card = CARD_REGISTRY["Seat of Power"].instantiate()
    bf.add_unit("A", _unit("Red Brambleback"))
    loop.gs.battlefields[1].add_unit("A", _unit("Holder", 1))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert len(a.hand) == 2                               # Seat of Power twice


def test_vi_hotheaded_costs_fury_too():
    """'[2] [fury]: Double my Might this turn.'"""
    loop, a, b = _setup()
    vi = _unit("Vi Hotheaded")
    a.base_units.append(vi)
    fury = a.power_pool[Domain.FURY]
    loop._apply_activated_ability(a, b, _ability(loop, "A", "double_might"))
    assert a.power_pool.get(Domain.FURY, 0) == fury - 1 and vi.might == 2 * vi.card.might


def test_shadow_watcher_needs_a_death_during_your_beginning_phase():
    """'If a friendly unit died during your Beginning Phase this turn, I enter
    ready.'"""
    loop, a, b = _setup()
    loop.gs.friendly_unit_died_this_turn["A"] = True
    assert not loop._play_unit(CARD_REGISTRY["Shadow Watcher"].instantiate(), "A").ready
    loop.gs.died_in_beginning["A"] = loop.gs.turn
    assert loop._play_unit(CARD_REGISTRY["Shadow Watcher"].instantiate(), "A").ready


def test_soul_sword_gives_one_only_at_level_three():
    """'LEVEL 3[>] I have an additional +1 [might].'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    unit.gear.append(CARD_REGISTRY["Soul Sword"].instantiate())
    a.base_units.append(unit)
    loop._recompute_passives()
    low = unit.might
    loop.gs.add_xp("A", 3)
    loop._recompute_passives()
    assert unit.might == low + 1


def test_back_off_draws_only_from_hand():
    """'STUN a unit. If you played this from your hand, draw 1.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    _play_spell(loop, a, "Back Off")
    assert len(a.hand) == 1
    card = CARD_REGISTRY["Back Off"].instantiate()
    loop._spell_played(card, a, from_zone="facedown")
    loop._resolve_card_effects(card, loop.gs.battlefields[0], a, b)
    assert len(a.hand) == 1


def test_nami_headstrong_readies_and_buffs_the_next_unit_after_holding():
    """'When I hold, the next time you play a unit this turn, ready it and BUFF it.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Nami Headstrong"))
    loop._fire_scoring_trigger("on_hold", bf, "A")
    first = loop._play_unit(UnitCard(name="First", might=1), "A")
    second = loop._play_unit(UnitCard(name="Second", might=1), "A")
    assert first.ready and first.might_counters == 1 and not second.ready


def test_yuumi_gives_might_and_tank_to_the_same_unit():
    """'When I attack or defend, give one of your other units here +3 power and
    TANK this turn.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    yuumi, x, y = _unit("Yuumi Magical Cat"), _unit("X", 1), _unit("Y", 5)
    for u in (yuumi, x, y):
        bf.add_unit("A", u)
    bf.add_unit("B", _unit("Def", 9))
    loop._open_combat(bf, "A")
    pumped = [u for u in (x, y) if u.temporary_might == 3]
    assert len(pumped) == 1 and pumped[0].has_keyword("TANK")


def test_master_yi_unstoppable_costs_less_by_level_and_hides_at_sixteen():
    """'LEVEL 3[>] I cost [2] [calm] less. LEVEL 6[>] [4] [calm] [calm] less
    instead. LEVEL 11[>] [6] [calm] [calm] [calm] less instead. LEVEL 16[>] I
    can't be chosen by enemy spells and abilities.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Master Yi Unstoppable"].instantiate()
    base = loop._effective_cost(card, a)[0]
    reductions = []
    for xp in (3, 3, 5, 5):
        loop.gs.add_xp("A", xp)
        reductions.append(base - loop._effective_cost(card, a)[0])
    assert reductions == [2, 4, 6, 6]
    yi = _unit("Master Yi Unstoppable")
    a.base_units.append(yi)
    loop._recompute_passives()
    assert not loop._can_choose(yi, "B", SpellCard(name="Aim"))


def test_vilemaw_silences_weaker_enemies_here():
    """'Enemy units here with less Might than me don't deal combat damage.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    vile = _unit("Vilemaw")
    weak, strong = _unit("Weak", 1), _unit("Strong", 99)
    bf.add_unit("A", vile)
    bf.add_unit("B", weak)
    bf.add_unit("B", strong)
    loop._recompute_passives()
    assert weak.no_combat_damage and not strong.no_combat_damage


def test_spectral_centaur_grows_two_per_friendly_death():
    """'When another friendly unit dies, give me +2 [might] this turn.'"""
    loop, a, b = _setup()
    centaur = _unit("Spectral Centaur")
    a.base_units.append(centaur)
    for i in range(2):
        f = _unit(f"F{i}", 1)
        loop._route_deaths([(f, "A")], loop.gs.battlefields[0], in_base=True)
    assert centaur.might == centaur.card.might + 4


def test_sprite_burst_sprites_are_ready():
    """'Play two ready 3 [might] Sprite unit tokens with TEMPORARY.'"""
    loop, a, b = _setup()
    _cast_now(loop, a, "Sprite Burst")
    sprites = [u for u in a.base_units if u.card.name == "Sprite"]
    assert len(sprites) == 2 and all(u.ready and u.might == 3 for u in sprites)


def test_crescent_strike_hits_the_others_for_one():
    """'Deal 4 to that unit and 1 to each other enemy unit there.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    big, small = _unit("Big", 9), _unit("Small", 9)
    bf.add_unit("B", big)
    bf.add_unit("B", small)
    _pick(loop, "Big")
    _cast_now(loop, a, "Crescent Strike")
    assert big.damage == 4 and small.damage == 1


def test_deadly_flourish_gold_when_it_dies():
    """'Deal 3 to an enemy unit. When it dies this turn, play a Gold gear token
    exhausted.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Deadly Flourish")
    assert not a.base_gear
    _ctx(loop, a).damage_units([enemy], 5)
    assert [g.name for g in a.base_gear] == ["Gold"]


def test_petal_pixie_counts_temporary_units_there():
    """'I have +1 [might] for each of your units with TEMPORARY at my battlefield.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    pixie = _unit("Petal Pixie")
    bf.add_unit("A", pixie)
    bf.add_unit("A", UnitInPlay(card=UnitCard(name="T", might=1, keywords=["TEMPORARY"])))
    loop._recompute_passives()
    assert pixie.might == pixie.card.might + 1


def test_soul_shepherd_pumps_every_token():
    """'Your token units have +1 [might].'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Soul Shepherd"))
    token = loop._play_token("Recruit", "A")
    loop._recompute_passives()
    assert token.might == 2


def test_hwei_does_something_by_the_discarded_type():
    """'Unit - Give me +3 [might] this turn.'"""
    loop, a, b = _setup()
    hwei = _unit("Hwei Brooding Painter")
    a.base_units.append(hwei)
    a.hand = []
    a.deck.cards = [UnitCard(name="Drawn", might=1)]
    loop._move_unit_by_effect(hwei, loop.gs.battlefields[0])
    assert hwei.might == hwei.card.might + 3


def test_keeper_of_masks_reflections_become_copies():
    """'Play two Reflection unit tokens here. They become copies of me.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    loop._play_unit(CARD_REGISTRY["Keeper of Masks"].instantiate(), "A", bf=bf)
    copies = [u for u in bf.units_A if u.card.name == "Keeper of Masks"]
    assert len(copies) == 3 and sum(u.is_token or getattr(u.card, "is_token", False) for u in copies) == 2


def test_smoke_and_mirrors_swaps_when_one_has_temporary():
    """'Choose a unit you control and another unit you control at a different
    location. If at least one of them has TEMPORARY, move each to the other's
    location. Draw 1.'"""
    loop, a, b = _setup()
    temp = UnitInPlay(card=UnitCard(name="Temp", might=1, keywords=["TEMPORARY"]))
    other = _unit("Other", 2)
    a.base_units.append(temp)
    loop.gs.battlefields[0].add_unit("A", other)
    _cast_now(loop, a, "Smoke and Mirrors")
    assert temp in loop.gs.battlefields[0].units_A and other in a.base_units


def test_blue_sentinel_doubles_hold_effects_here():
    """'Your hold effects for holding here trigger an additional time.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.card = CARD_REGISTRY["Grove of the God-Willow"].instantiate()
    bf.add_unit("A", _unit("Blue Sentinel"))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert len(a.hand) == 2


def test_concentrate_costs_four_less_at_level_eleven():
    """'LEVEL 6[>] This costs 2 less. LEVEL 11[>] This costs 4 less instead.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Concentrate"].instantiate()
    base = loop._effective_cost(card, a)[0]
    loop.gs.add_xp("A", 6)
    six = base - loop._effective_cost(card, a)[0]
    loop.gs.add_xp("A", 5)
    eleven = base - loop._effective_cost(card, a)[0]
    assert (six, eleven) == (min(2, base), min(4, base))


def test_grim_resolve_gives_xp_when_the_unit_wins():
    """'Give a friendly unit +3 [might] this turn. When it wins a combat this turn,
    gain 2 XP.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    hero = _unit("Hero", 2)
    bf.add_unit("A", hero)
    bf.add_unit("B", _unit("Def", 4))
    _cast_now(loop, a, "Grim Resolve")
    _fight(loop)
    assert loop.gs.get_xp("A") == 2


def test_disposal_order_recycles_from_the_opponents_trash():
    """'Choose up to 3 cards from opponents' trashes. Their owners recycle them.'"""
    loop, a, b = _setup()
    b.trash = [UnitCard(name=f"T{i}", might=1) for i in range(4)]
    a.hand = [UnitCard(name="Keep", might=1)]
    loop.chooser = lambda _l, kind, side, options, default, source: 0 if kind == "mode" else None
    _cast_now(loop, a, "Disposal Order")
    assert len(b.trash) == 1 and len(b.deck.cards) == 3 and [c.name for c in a.hand] == ["Keep"]


def test_repulse_counters_a_spell_aimed_only_at_one_friendly_unit():
    """'Counter an enemy spell or ability that chooses it and no other friendly unit.'"""
    loop, a, b = _setup()
    x, y = _unit("X", 2), _unit("Y", 2)
    loop.gs.battlefields[0].add_unit("A", x)
    loop.gs.battlefields[0].add_unit("A", y)
    both = ChainItem(player="B", card=SpellCard(name="Both"), bf_idx=0)
    both.declared = {(0, 0, 0): ("target:deal_damage", 0, [x, y])}
    loop.gs.chain.append(both)
    assert not loop._spell_has_targets(CARD_REGISTRY["Repulse"].instantiate(), "A", 0)
    loop.gs.chain[-1].declared = {(0, 0, 0): ("target:deal_damage", 0, [x])}
    _cast_now(loop, a, "Repulse")
    assert not loop.gs.chain


def test_elder_dragon_makes_any_damage_lethal_and_pings_each_location():
    """'Any amount of your damage is enough to kill enemy units. When you play me,
    choose up to one enemy unit at each location. Deal 1 to them.'"""
    loop, a, b = _setup()
    e0, e1, home = _unit("E0", 9), _unit("E1", 9), _unit("Home", 9)
    loop.gs.battlefields[0].add_unit("B", e0)
    loop.gs.battlefields[1].add_unit("B", e1)
    b.base_units.append(home)
    loop._play_unit(CARD_REGISTRY["Elder Dragon"].instantiate(), "A")
    assert all(u.card in b.trash for u in (e0, e1, home))


def test_crescent_guardian_needs_a_spell_played_this_turn():
    """'If you've played a spell this turn, you may pay [chaos] ... If you do, I
    enter ready.'"""
    loop, a, b = _setup()
    a.hand = [CARD_REGISTRY["Crescent Guardian"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert not a.base_units[-1].ready
    loop.gs.spells_played_this_turn["A"] = 1
    a.hand = [CARD_REGISTRY["Crescent Guardian"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert a.base_units[-1].ready


def test_isolate_draws_when_an_enemy_is_left_alone():
    """'Move an enemy unit from a battlefield to its base. Then, if there's an enemy
    unit alone at that battlefield, draw 1.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    big, small = _unit("Big", 5), _unit("Small", 1)
    bf.add_unit("B", big)
    bf.add_unit("B", small)
    a.deck.cards = [UnitCard(name="D", might=1)]
    _cast_now(loop, a, "Isolate")
    assert len(bf.units_B) == 1 and len(a.hand) == 1


def test_blast_cone_stuns_an_enemy_you_move():
    """'When you play this, you may move an enemy unit. When you move an enemy
    unit, you may exhaust this to STUN it.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    cone = CARD_REGISTRY["Blast Cone"].instantiate()
    a.base_gear.append(cone)
    REGISTRY["move_unit"](_ctx(loop, a), {"target": "enemy_unit", "destination": "any"})
    assert enemy.stunned and cone.tapped


def test_existential_dread_stuns_an_attacker_or_returns_a_stunned_one():
    """'STUN an attacking unit. If it's already stunned, return it to its owner's
    hand instead.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    atk = _unit("Atk", 3)
    bf.add_unit("B", _unit("Def", 3))
    bf.add_unit("A", atk)
    _attack_at(loop, 0)
    _cast_now(loop, b, "Existential Dread")
    assert atk.stunned
    _cast_now(loop, b, "Existential Dread")
    assert atk.card in a.hand


def test_the_list_hits_only_the_named_tag():
    """'As you play this, name a tag. [tap]: Give a unit with the named tag -2
    [might] this turn.'"""
    loop, a, b = _setup()
    dragon = UnitInPlay(card=UnitCard(name="Drake", might=5, tags=["Dragon"]))
    plain = _unit("Plain", 5)
    loop.gs.battlefields[0].add_unit("B", dragon)
    loop.gs.battlefields[0].add_unit("B", plain)
    a.hand = [CARD_REGISTRY["The List"].instantiate()]
    loop._apply_action(a, ("GEAR", 0, 0))
    loop._apply_activated_ability(a, b, _ability(loop, "A", "grant_temporary_might"))
    assert dragon.might == 3 and plain.might == 5


def test_safety_inspector_each_player_kills_one_unless_you_paid():
    """'You may spend 3 XP as an additional cost to play me. When you play me, each
    player must kill one of their units. If you paid my additional cost, you don't
    kill a unit this way.'"""
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 1), _unit("Theirs", 1)
    a.base_units.append(mine)
    b.base_units.append(theirs)
    loop.gs.add_xp("A", 3)
    a.hand = [CARD_REGISTRY["Safety Inspector"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert theirs.card in b.trash and mine in a.base_units and loop.gs.get_xp("A") == 0


def test_starhound_returns_any_pet():
    """'Return a Bird, Cat, Dog, or Poro from your trash to your hand.'"""
    loop, a, b = _setup()
    cat = UnitCard(name="Cat Unit", might=1, tags=["Cat"])
    a.trash.append(cat)
    loop._play_unit(CARD_REGISTRY["Starhound"].instantiate(), "A")
    assert cat in a.hand


def test_leblanc_fragmented_draws_two_in_your_beginning_phase():
    """'DEATHKNELL[>] Draw 1. If it's your Beginning Phase, draw 2 instead.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(4)]
    lb = _unit("Leblanc Fragmented")
    loop.gs.in_beginning_phase = True
    loop._route_deaths([(lb, "A")], loop.gs.battlefields[0], in_base=True)
    assert len(a.hand) == 2


def test_tactical_retreat_saves_a_unit_for_free():
    """'Choose a friendly unit. The next time it would die this turn, heal it,
    exhaust it, and recall it instead.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    _cast_now(loop, a, "Tactical Retreat")
    power = sum(a.power_pool.values())
    _ctx(loop, b).damage_units([unit], 5)
    assert unit in a.base_units and sum(a.power_pool.values()) == power


def test_rift_herald_plays_a_unit_from_hand_when_it_dies():
    """'DEATHKNELL[>] Play a unit from your hand to your base, ignoring its Energy
    cost.'"""
    loop, a, b = _setup()
    big = UnitCard(name="Big", might=8, cost_energy=9)
    a.hand = [big]
    herald = _unit("Rift Herald")
    loop._route_deaths([(herald, "A")], loop.gs.battlefields[0], in_base=True)
    assert any(u.card is big for u in a.base_units) and a.energy == 20


def test_undying_legion_plays_from_the_trash_with_legion():
    """'LEGION[>] You may play me from your trash for [3] [fury].'"""
    loop, a, b = _setup()
    legion = CARD_REGISTRY["Undying Legion"].instantiate()
    a.trash.append(legion)
    entries = [e for e in loop.activatable_abilities("A") if e["type"] == "trash_play"]
    assert entries and not loop._ability_usable(a, entries[0])
    loop.gs.played_cards_this_turn["A"].append(UnitCard(name="First", might=1))
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "trash_play")
    loop._apply_activated_ability(a, b, idx)
    assert any(u.card is legion for u in a.base_units) and a.energy == 17


def test_lillia_bashful_bloom_costs_one_less_per_temporary_unit():
    """'[4], [tap]: Play a ready 3 [might] Sprite unit token with TEMPORARY. This
    ability costs [1] less for each friendly unit with TEMPORARY.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Lillia Bashful Bloom")
    for i in range(2):
        a.base_units.append(UnitInPlay(card=UnitCard(name=f"T{i}", might=1, keywords=["TEMPORARY"])))
    loop._apply_activated_ability(a, b, _ability(loop, "A", "play_token"))
    assert a.energy == 18


def test_lilting_lullaby_stops_their_spells_this_turn():
    """'Counter a spell. Its controller can't play spells this turn.'"""
    loop, a, b = _setup()
    loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="S", cost_energy=1), bf_idx=0))
    _cast_now(loop, a, "Lilting Lullaby")
    assert not loop.gs.chain and loop._play_forbidden(b, SpellCard(name="Next"))


def test_master_yi_wuju_master_pumps_every_unit_and_readies_them_at_eleven():
    """'LEVEL 6[>] Your units have +1 [might]. LEVEL 11[>] Your units enter ready.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Master Yi Wuju Master")
    far = _unit("Far", 2)
    loop.gs.battlefields[1].add_unit("A", far)
    loop.gs.add_xp("A", 6)
    loop._recompute_passives()
    assert far.might == 3
    assert not loop._play_unit(UnitCard(name="New", might=1), "A").ready
    loop.gs.add_xp("A", 5)
    assert loop._play_unit(UnitCard(name="New2", might=1), "A").ready


def test_shadow_enters_ready_at_a_battlefield_and_stuns_an_attacker():
    """'If you play me to a battlefield, I enter ready. [1] [rune], [tap]: STUN an
    enemy unit attacking here.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    shadow = loop._play_unit(CARD_REGISTRY["Shadow"].instantiate(), "B", bf=bf)
    assert shadow.ready
    assert not loop._play_unit(CARD_REGISTRY["Shadow"].instantiate(), "B").ready


def test_daisy_enters_ready_and_costs_less_per_pet_tag():
    """'I enter ready. Reduce my cost by [1] for each of the following tags among
    your units - Bird, Cat, Dog, and Poro.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Daisy!"].instantiate()
    base = loop._effective_cost(card, a)[0]
    a.base_units.append(UnitInPlay(card=UnitCard(name="C", might=1, tags=["Cat"])))
    a.base_units.append(UnitInPlay(card=UnitCard(name="D", might=1, tags=["Dog"])))
    assert loop._effective_cost(card, a)[0] == max(0, base - 2)
    assert loop._play_unit(CARD_REGISTRY["Daisy!"].instantiate(), "A").ready


def test_mirror_image_makes_a_temporary_copy():
    """'Choose a unit. Play a ready Reflection unit token to your base. It becomes
    a copy of that unit. Give it TEMPORARY.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Vilemaw"))
    _cast_now(loop, a, "Mirror Image")
    copy = next(u for u in a.base_units)
    assert copy.card.name == "Vilemaw" and copy.ready and copy.has_keyword("TEMPORARY")


def test_cursed_sarcophagus_banishes_trash_units_then_plays_one():
    """'When you play this, banish all units from your trash. [tap]: Play a unit
    banished with this.'"""
    loop, a, b = _setup()
    unit = UnitCard(name="Dead", might=2, cost_energy=2)
    a.trash = [unit, SpellCard(name="S")]
    a.hand = [CARD_REGISTRY["Cursed Sarcophagus"].instantiate()]
    loop._apply_action(a, ("GEAR", 0, 0))
    assert unit in a.banished and [c.name for c in a.trash] == ["S"]
    energy = a.energy
    loop._apply_activated_ability(a, b, _ability(loop, "A", "play_one_banished_with_this"))
    assert any(u.card is unit for u in a.base_units) and a.energy == energy - 2


def test_heroic_charge_stuns_an_enemy_where_the_friend_is():
    """'Give a friendly unit +1 [might] this turn and STUN an enemy unit at its
    location.'"""
    loop, a, b = _setup()
    friend = _unit("Friend", 2)
    loop.gs.battlefields[1].add_unit("A", friend)
    there, elsewhere = _unit("There", 3), _unit("Elsewhere", 3)
    loop.gs.battlefields[1].add_unit("B", there)
    loop.gs.battlefields[0].add_unit("B", elsewhere)
    _cast_now(loop, a, "Heroic Charge")
    assert there.stunned and not elsewhere.stunned


def test_scrutinizing_sergeant_counts_all_friendly_units():
    """'When you play me, gain 1 XP for each friendly unit.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("A1", 1))
    loop.gs.battlefields[1].add_unit("A", _unit("A2", 1))
    loop._play_unit(CARD_REGISTRY["Scrutinizing Sergeant"].instantiate(), "A")
    assert loop.gs.get_xp("A") == 3
