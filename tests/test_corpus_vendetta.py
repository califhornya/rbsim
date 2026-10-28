"""Vendetta, card by card (BACKLOG.md section D): the sentences the corpus pass
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

from test_corpus_cards import (_always, _cast_now, _deck, _pick, _setup, _unit)


def _ctx(loop, p, card=None):
    o = loop.gs.get_player(loop.gs.other(p.name))
    return EffectContext(loop, card or SpellCard(name="Effect"), p, o, loop.gs.battlefields[0], {})


def _ability(loop, side, effect):
    return next(i for i, e in enumerate(loop.activatable_abilities(side))
                if e.get("eff") is not None and e["eff"].effect == effect)


def _runes(p, n, domain=Domain.FURY):
    p.rune_pool = {domain: [Rune(domain) for _ in range(n)]}


def _attack_at(loop, bf_idx=0):
    bf = loop.gs.battlefields[bf_idx]
    loop.gs.showdown_active, loop.gs.showdown_bf_idx, loop.gs.showdown_attacker = True, bf_idx, "A"
    loop._open_combat(bf, "A")
    return bf


def test_deadly_flourish_plays_a_gold_when_it_dies():
    """'Deal 3 to an enemy unit. When it dies this turn, play a Gold gear token
    exhausted.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    _cast_now(loop, a, "Deadly Flourish")
    assert [g.name for g in a.base_gear] == ["Gold"]


def test_siphoning_strike_deals_seven_with_seven_runes_and_channels_on_death():
    """'Deal 4 to a unit at a battlefield. If you control 7 or more runes, deal 7
    to it instead. When it dies this turn, channel 1 rune exhausted.'"""
    loop, a, b = _setup()
    big = _unit("Big", 9)
    loop.gs.battlefields[0].add_unit("B", big)
    _runes(a, 6)
    a.rune_deck = RuneDeck([Rune(Domain.FURY) for _ in range(3)])
    _cast_now(loop, a, "Siphoning Strike")
    assert big.damage == 4 and a.total_runes_in_play() == 6
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Seven", 7))
    _runes(a, 7)
    a.rune_deck = RuneDeck([Rune(Domain.FURY) for _ in range(3)])
    _cast_now(loop, a, "Siphoning Strike")
    assert not loop.gs.battlefields[0].units_B and a.total_runes_in_play() == 8


def test_baccai_sandspinner_empowers_for_two_with_four_runes():
    """'EMPOWER [5]. This ability costs [3] less if you control 4 or fewer runes.
    EMPOWERED: I have DEFLECT and ASSAULT 2.'"""
    loop, a, b = _setup()
    unit = _unit("Baccai Sandspinner")
    a.base_units.append(unit)
    _runes(a, 4)
    assert not unit.has_keyword("DEFLECT")
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert a.energy == 18 and unit.has_keyword("DEFLECT") and unit.has_keyword("ASSAULT")
    loop, a, b = _setup()
    a.base_units.append(_unit("Baccai Sandspinner"))
    _runes(a, 5)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert a.energy == 15


def test_consuming_curse_adds_one_per_copy_in_your_trash():
    """'Deal 2 to a unit at a battlefield. This deals 1 Bonus Damage for each card
    with this name in your trash.'"""
    loop, a, b = _setup()
    big = _unit("Big", 9)
    loop.gs.battlefields[0].add_unit("B", big)
    a.trash.extend(CARD_REGISTRY["Consuming Curse"].instantiate() for _ in range(2))
    _cast_now(loop, a, "Consuming Curse")
    assert big.damage == 4


def test_decree_of_rage_hits_only_calm_and_cant_be_countered():
    """'This can't be countered. Deal 4 to an enemy Calm unit.'"""
    loop, a, b = _setup()
    fury = _unit("Fury", 9)
    fury.card.domain = Domain.FURY
    calm = _unit("Calm", 9)
    calm.card.domain = Domain.CALM
    loop.gs.battlefields[0].add_unit("B", fury)
    loop.gs.battlefields[0].add_unit("B", calm)
    _cast_now(loop, a, "Decree of Rage")
    assert calm.damage == 4 and fury.damage == 0
    loop.gs.chain.append(ChainItem(player="B", card=CARD_REGISTRY["Decree of Rage"].instantiate(), bf_idx=0))
    REGISTRY["counter_spell"](_ctx(loop, a), {})
    assert loop.gs.chain


def test_rage_amplifier_gives_one_and_two_when_empowered():
    """'Your units have +1 [might]. If I'm EMPOWERED, they have +2 [might] instead.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    amp = CARD_REGISTRY["Rage Amplifier"].instantiate()
    a.base_gear.append(amp)
    loop._recompute_passives()
    assert unit.might == 3
    fury = a.power_pool[Domain.FURY]
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert unit.might == 4 and a.energy == 14 and a.power_pool.get(Domain.FURY, 0) == fury - 1


def test_affectionate_poro_draws_only_if_undamaged():
    """'When a combat that I was in ends, if I haven't been dealt damage this
    turn, draw 1.'"""
    for enemy_might, drawn in ((0, 1), (1, 0)):
        loop, a, b = _setup()
        a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
        loop.gs.battlefields[0].add_unit("A", _unit("Affectionate Poro"))
        loop.gs.battlefields[0].add_unit("B", _unit("Enemy", enemy_might))
        loop._phase_combat_and_conquer_single(0, "A")
        assert len(a.hand) == drawn


def test_frostcoat_mother_empower_costs_one_less_per_rune():
    """'EMPOWER [12]. This ability costs [1] less for each rune you control.
    EMPOWERED: I have +3 [might].'"""
    loop, a, b = _setup()
    unit = _unit("Frostcoat Mother")
    a.base_units.append(unit)
    _runes(a, 9)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert a.energy == 17 and unit.might == 6


def test_grumpy_rockbear_has_deflect_and_shield_only_when_empowered():
    """'EMPOWER [12], [1] less for each rune you control. EMPOWERED: I have
    DEFLECT and SHIELD 3.'"""
    loop, a, b = _setup()
    unit = _unit("Grumpy Rockbear")
    a.base_units.append(unit)
    loop._recompute_passives()
    assert not unit.has_keyword("DEFLECT") and not unit.has_keyword("SHIELD")
    _runes(a, 10)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert a.energy == 18 and unit.has_keyword("DEFLECT") and unit.has_keyword("SHIELD")


def test_tomb_raider_barbara_kills_or_disempowers_with_seven_runes():
    """'When you play me, if you control 7 or more runes, choose an enemy gear. If
    it's EMPOWERED, disempower it. Otherwise, kill it.'"""
    loop, a, b = _setup()
    gear = GearCard(name="Gear", cost_energy=2)
    b.base_gear.append(gear)
    _runes(a, 6)
    loop._play_unit(CARD_REGISTRY["Tomb-Raider Barbara"].instantiate(), "A")
    assert gear in b.base_gear
    _runes(a, 7)
    gear.empowered = True
    loop._play_unit(CARD_REGISTRY["Tomb-Raider Barbara"].instantiate(), "A")
    assert gear in b.base_gear and not gear.empowered
    loop._play_unit(CARD_REGISTRY["Tomb-Raider Barbara"].instantiate(), "A")
    assert gear not in b.base_gear and gear in b.trash


def test_akali_silent_can_be_chosen_only_in_combat():
    """'I can't be chosen by enemy spells and abilities unless I'm in combat.'"""
    loop, a, b = _setup()
    akali = _unit("Akali Silent")
    loop.gs.battlefields[0].add_unit("A", akali)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 1))
    loop._recompute_passives()
    assert not loop._can_choose(akali, "B", SpellCard(name="S"))
    assert loop._can_choose(akali, "A", SpellCard(name="S"))
    _attack_at(loop)
    loop._recompute_passives()
    assert loop._can_choose(akali, "B", SpellCard(name="S"))


def test_decree_of_focus_pumps_a_unit_fighting_a_fury_unit():
    """'Choose a friendly unit that's in combat with an enemy Fury unit or that's
    being chosen by an enemy Fury spell. Give it +4 [might] this turn.'"""
    loop, a, b = _setup()
    home = _unit("Home", 2)
    a.base_units.append(home)
    fighter = _unit("Fighter", 2)
    loop.gs.battlefields[0].add_unit("A", fighter)
    enemy = _unit("Enemy", 3)
    enemy.card.domain = Domain.FURY
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Decree of Focus")
    assert fighter.might == 2 and home.might == 2
    _attack_at(loop)
    _cast_now(loop, a, "Decree of Focus")
    assert fighter.might == 6 and home.might == 2


def test_shock_blast_costs_two_less_with_something_empowered():
    """'This costs [2] less if you control something that's EMPOWERED.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Shock Blast"].instantiate()
    unit = _unit("Unit", 1)
    a.base_units.append(unit)
    assert loop._effective_cost(card, a)[0] == 3
    unit.empowered = True
    assert loop._effective_cost(card, a)[0] == 1


def test_sky_cruiser_discards_a_gear_to_deal_four():
    """'Discard a gear, [1], [tap]: Deal 4 to a unit at a battlefield.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Sky Cruiser"))
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.hand.append(SpellCard(name="Not a gear"))
    entry = loop.activatable_abilities("A")[_ability(loop, "A", "deal_damage")]
    assert not loop._ability_usable(a, entry)
    gear = GearCard(name="Gear", cost_energy=1)
    a.hand.append(gear)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "deal_damage"))
    assert enemy.damage == 4 and gear in a.trash and a.energy == 19


def test_decree_of_insight_hits_only_body():
    """'Give an enemy Body unit -5 [might] this turn.'"""
    loop, a, b = _setup()
    mind = _unit("Mind", 9)
    mind.card.domain = Domain.MIND
    body = _unit("Body", 9)
    body.card.domain = Domain.BODY
    loop.gs.battlefields[0].add_unit("B", mind)
    loop.gs.battlefields[0].add_unit("B", body)
    _cast_now(loop, a, "Decree of Insight")
    assert body.might == 4 and mind.might == 9


def test_plaza_guardian_costs_one_less_per_gear():
    """'I cost [1] less for each gear you control.'"""
    loop, a, b = _setup()
    a.base_gear.extend([GearCard(name="G1"), GearCard(name="G2")])
    assert loop._effective_cost(CARD_REGISTRY["Plaza Guardian"].instantiate(), a)[0] == 8


def test_jayce_brilliant_inventor_readies_on_play_and_first_gear_each_turn():
    """'When you play me or the first time you play a non-token gear each turn,
    you may ready something besides me that's exhausted.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    tired = _unit("Tired", 2)
    tired.ready = False
    a.base_units.append(tired)
    jayce = loop._play_unit(CARD_REGISTRY["Jayce Brilliant Inventor"].instantiate(), "A")
    assert tired.ready
    tired.ready = False
    for name in ("G1", "G2"):
        gear = GearCard(name=name, cost_energy=1)
        loop._play_gear(gear, "A")
        loop._note_card_played(gear, "A")
        if name == "G1":
            assert tired.ready
            tired.ready = False
    assert not tired.ready and jayce is not None


def test_guttural_roar_gives_four_to_an_empowered_unit():
    """'Give a unit +2 [might] this turn. If it's EMPOWERED, give it +4 instead.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 1)
    a.base_units.append(unit)
    _cast_now(loop, a, "Guttural Roar")
    assert unit.might == 3
    unit.empowered = True
    _cast_now(loop, a, "Guttural Roar")
    assert unit.might == 7


def test_jagged_cutlass_unit_cant_be_moved_by_enemies():
    """'I can't be moved by enemy spells and abilities' (the attached unit)."""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    unit.gear.append(CARD_REGISTRY["Jagged Cutlass"].instantiate())
    loop.gs.battlefields[0].add_unit("B", unit)
    loop._recompute_passives()
    REGISTRY["move_unit"](_ctx(loop, a), {"target": "enemy_unit", "destination": "base"})
    assert unit in loop.gs.battlefields[0].units_B
    REGISTRY["move_unit"](_ctx(loop, b), {"target": "friendly_unit", "destination": "base"})
    assert unit in b.base_units


def test_dame_the_despoiler_matches_a_unit_here_plus_one_when_empowered():
    """'EMPOWERED: When I attack or defend, choose a unit here. Increase my Might
    to its Might this turn, then give me +1 [might] this turn.'"""
    loop, a, b = _setup()
    dame = _unit("Dame the Despoiler")
    loop.gs.battlefields[0].add_unit("A", dame)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 8))
    _attack_at(loop)
    assert dame.might == 5
    loop, a, b = _setup()
    dame = _unit("Dame the Despoiler", empowered=True)
    loop.gs.battlefields[0].add_unit("A", dame)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 8))
    _attack_at(loop)
    assert dame.might == 9


def test_noxian_demolitionist_kills_a_gear_up_to_its_might():
    """'When I conquer, you may kill a gear with Energy cost no more than my Might.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    loop.gs.battlefields[0].add_unit("A", _unit("Noxian Demolitionist"))
    dear, cheap = GearCard(name="Dear", cost_energy=2), GearCard(name="Cheap", cost_energy=1)
    b.base_gear.extend([dear, cheap])
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert dear in b.base_gear and cheap not in b.base_gear


def test_rampage_fights_and_adds_two_with_the_additional_cost():
    """'Choose a friendly unit and an enemy unit. If you paid the additional cost,
    give the friendly unit +2 [might] this turn. They deal damage equal to their
    Mights to each other.'"""
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 3), _unit("Theirs", 9)
    a.base_units.append(mine)
    loop.gs.battlefields[0].add_unit("B", theirs)
    _cast_now(loop, a, "Rampage")
    assert theirs.damage == 3
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 3), _unit("Theirs", 9)
    a.base_units.append(mine)
    loop.gs.battlefields[0].add_unit("B", theirs)
    card = CARD_REGISTRY["Rampage"].instantiate()
    card._kicker_paid = True
    loop._resolve_card_effects(card, loop.gs.battlefields[0], a, b)
    assert theirs.damage == 5


def test_ambessa_the_wolf_takes_no_damage_outside_combat_when_empowered():
    """'EMPOWERED: I have +3 [might] and can't be dealt damage unless I'm in combat.'"""
    loop, a, b = _setup()
    ambessa = _unit("Ambessa The Wolf", empowered=True)
    loop.gs.battlefields[0].add_unit("B", ambessa)
    loop._recompute_passives()
    assert ambessa.might == 7
    REGISTRY["deal_damage"](_ctx(loop, a), {"amount": 3, "target": "enemy_unit", "where": "anywhere"})
    assert ambessa.damage == 0
    ambessa.empowered = False
    REGISTRY["deal_damage"](_ctx(loop, a), {"amount": 3, "target": "enemy_unit", "where": "anywhere"})
    assert ambessa.damage == 3


def test_gangplank_naval_turns_a_stun_into_three_when_empowered():
    """'EMPOWERED: If a spell or ability that chooses me would stun me, give me
    -[might], or return me to hand, give me +3 [might] this turn instead.'"""
    loop, a, b = _setup()
    gp = _unit("Gangplank Naval", empowered=True)
    loop.gs.battlefields[0].add_unit("B", gp)
    REGISTRY["stun_unit"](_ctx(loop, a), {"target": "enemy_unit"})
    REGISTRY["grant_temporary_might"](_ctx(loop, a), {"target": "enemy_unit", "amount": -2})
    assert not gp.stunned and gp.might == 12
    gp.empowered = False
    REGISTRY["stun_unit"](_ctx(loop, a), {"target": "enemy_unit"})
    assert gp.stunned


def test_wild_claw_plays_a_unit_five_cheaper_and_empowers_it():
    """'Look at the top 5 cards. You may banish a unit or gear from among them and
    play it, reducing its Energy cost by [5]. Recycle the rest. Then you may
    empower it.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    big = UnitCard(name="Big", might=6, cost_energy=7)
    _deck(a, SpellCard(name="S1"), big, SpellCard(name="S2"))
    _cast_now(loop, a, "Wild Claw")
    unit = next(u for u in a.base_units if u.card is big)
    assert a.energy == 18 and unit.empowered


def test_corrupted_dragon_enters_ready_far_from_victory_and_sends_small_ones_home():
    """'If your score is not within 3 points of the Victory Score, I enter ready.
    When I attack, you may move any number of enemy units here each with 5
    [might] or less to their base.'"""
    loop, a, b = _setup()
    assert loop._play_unit(CARD_REGISTRY["Corrupted Dragon"].instantiate(), "A").ready
    loop.gs.points_A = 5
    assert not loop._play_unit(CARD_REGISTRY["Corrupted Dragon"].instantiate(), "A").ready
    loop, a, b = _setup()
    loop.chooser = _always(True)
    loop.gs.battlefields[0].add_unit("A", _unit("Corrupted Dragon"))
    small, large = _unit("Small", 5), _unit("Large", 6)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.gs.battlefields[0].add_unit("B", large)
    _attack_at(loop)
    assert small in b.base_units and large in loop.gs.battlefields[0].units_B


def test_spiderling_counts_other_spiderlings_here():
    """'I have +1 [might] for each other unit you control here with my name.'"""
    loop, a, b = _setup()
    spiders = [_unit("Spiderling") for _ in range(3)]
    for s in spiders[:2]:
        loop.gs.battlefields[0].add_unit("A", s)
    a.base_units.append(spiders[2])
    loop._recompute_passives()
    assert [s.might for s in spiders] == [2, 2, 1]


def test_tail_cloaked_matriarch_plays_a_small_unit_from_the_trash_when_empowered():
    """'When I become EMPOWERED, you may choose a unit with Energy cost no more
    than [3] and Power cost no more than [rune]. Play it to your base, ignoring
    its cost.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    a.base_units.append(_unit("Tail-Cloaked Matriarch"))
    small = UnitCard(name="Small", might=2, cost_energy=3)
    big = UnitCard(name="Big", might=5, cost_energy=4)
    a.trash.extend([big, small])
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert any(u.card is small for u in a.base_units) and big in a.trash
    assert a.energy == 18


def test_decree_of_discord_returns_order_units_up_to_five_might():
    """'Return any number of enemy Order units with total Might 5 or less to their
    owners' hands.'"""
    loop, a, b = _setup()
    units = [_unit(f"O{m}", m) for m in (3, 2)] + [_unit("Other", 1)]
    for u in units[:2]:
        u.card.domain = Domain.ORDER
    units[2].card.domain = Domain.FURY
    for u in units:
        loop.gs.battlefields[0].add_unit("B", u)
    _cast_now(loop, a, "Decree of Discord")
    assert loop.gs.battlefields[0].units_B == [units[2]]
    assert {c.name for c in b.hand} == {"O3", "O2"}


def test_illaoi_makes_tentacles_and_grows_with_tokens():
    """'When you play me or when I score, play a 1 [might] Tentacle unit token. I
    have +1 [might] for each token unit you control.'"""
    loop, a, b = _setup()
    illaoi = loop._play_unit(CARD_REGISTRY["Illaoi Prophet of the Great Kraken"].instantiate(), "A")
    loop._recompute_passives()
    tentacles = [u for u in loop._friendly_units_of("A") if u.card.name == "Tentacle"]
    assert len(tentacles) == 1 and illaoi.might == 5


def test_ocean_drake_may_return_a_non_dragon_unit():
    """'When you play me, you may return a non-Dragon unit to its owner's hand.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    dragon = UnitInPlay(card=UnitCard(name="Dragon", might=9, tags=["Dragon"]))
    loop.gs.battlefields[0].add_unit("B", dragon)
    loop._play_unit(CARD_REGISTRY["Ocean Drake"].instantiate(), "A")
    assert dragon in loop.gs.battlefields[0].units_B
    other = _unit("Other", 2)
    loop.gs.battlefields[0].add_unit("B", other)
    loop._play_unit(CARD_REGISTRY["Ocean Drake"].instantiate(), "A")
    assert other.card in b.hand and dragon in loop.gs.battlefields[0].units_B


def test_aurok_general_pumps_empowered_units_when_empowered():
    """'EMPOWERED: Your units that are EMPOWERED have +2 [might].'"""
    loop, a, b = _setup()
    general = _unit("Aurok General", empowered=True)
    hot, cold = _unit("Hot", 1, empowered=True), _unit("Cold", 1)
    a.base_units.extend([general, hot, cold])
    loop._recompute_passives()
    assert (general.might, hot.might, cold.might) == (7, 3, 1)


def test_decree_of_unity_kills_a_chaos_unit():
    """'Kill an enemy Chaos unit or gear.'"""
    loop, a, b = _setup()
    chaos, calm = _unit("Chaos", 9), _unit("Calm", 1)
    chaos.card.domain, calm.card.domain = Domain.CHAOS, Domain.CALM
    loop.gs.battlefields[0].add_unit("B", calm)
    loop.gs.battlefields[0].add_unit("B", chaos)
    _cast_now(loop, a, "Decree of Unity")
    assert loop.gs.battlefields[0].units_B == [calm]
    gear = GearCard(name="Chaos Gear", cost_energy=2)
    gear.domain = Domain.CHAOS
    b.base_gear.extend([GearCard(name="Plain", cost_energy=3), gear])
    _cast_now(loop, a, "Decree of Unity")
    assert [g.name for g in b.base_gear] == ["Plain"] and gear in b.trash


def test_akali_rogue_assassin_pulls_a_unit_out_of_a_showdown():
    """'[tap]: If it's your turn, move a friendly unit in a showdown to base and if
    I'm EMPOWERED ready it.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Akali Rogue Assassin", empowered=True)
    unit = _unit("Unit", 2)
    unit.ready = False
    loop.gs.battlefields[0].add_unit("A", unit)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    loop.gs.showdown_active, loop.gs.showdown_bf_idx = True, 0
    loop._apply_activated_ability(a, b, _ability(loop, "A", "akali_retreat"))
    assert unit in a.base_units and unit.ready


def test_dominus_doubles_might_and_grants_a_ready_ability():
    """'This turn, double a unit's Might and give it "[rune] [rune]: Ready me."'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 3)
    unit.ready = False
    a.base_units.append(unit)
    _cast_now(loop, a, "Dominus")
    assert unit.might == 6
    loop._apply_activated_ability(a, b, _ability(loop, "A", "ready_unit"))
    assert unit.ready
    loop.gs.turn += 1
    assert not any(e.get("unit") is unit for e in loop.activatable_abilities("A"))


def test_nasus_curator_readies_two_runes_on_a_seven_cost_unit():
    """'When you play a unit, gear or activated ability with Energy cost [7] or
    more, you may exhaust me to ready up to 2 runes.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    loop.gs.legend_unit_A = _unit("Nasus Curator of the Sands")
    _runes(a, 3)
    for r in a.rune_pool[Domain.FURY]:
        r.ready = False
    loop._play_unit(UnitCard(name="Six", might=1, cost_energy=6), "A")
    loop._note_card_played(UnitCard(name="Six", might=1, cost_energy=6), "A")
    assert a.energy == 20
    seven = UnitCard(name="Seven", might=1, cost_energy=7)
    loop._play_unit(seven, "A")
    loop._note_card_played(seven, "A")
    assert a.energy == 22 and not loop.gs.legend_unit_A.ready      # a readied rune = its Energy back


def test_mel_souls_reflection_empowers_when_you_empower_something_else():
    """'When you empower something else, empower me. Disempower me, [tap]: Give a
    unit at a battlefield -2 [might] this turn.'"""
    loop, a, b = _setup()
    mel = _unit("Mel Soul's Reflection")
    loop.gs.legend_unit_A = mel
    other = _unit("Other", 1)
    a.base_units.append(other)
    loop._empower(other.card, "A")
    assert mel.empowered
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "grant_temporary_might"))
    assert enemy.might == 3 and not mel.empowered


def test_public_execution_kills_an_enemy_weaker_than_your_unit():
    """'Choose a friendly unit. Kill an enemy unit with less Might than it.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Mine", 4))
    weak, strong = _unit("Weak", 3), _unit("Strong", 4)
    loop.gs.battlefields[0].add_unit("B", weak)
    loop.gs.battlefields[0].add_unit("B", strong)
    _cast_now(loop, a, "Public Execution")
    assert loop.gs.battlefields[0].units_B == [strong] and weak.card in b.trash
