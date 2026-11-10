"""Vendetta, card by card (BACKLOG.md section D): the sentences the corpus pass
found wrong or missing, each played through the engine."""

from __future__ import annotations

from riftbound.core.battlefield import FacedownCard
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext
from riftbound.core.player import Rune, RuneDeck
from riftbound.core.state import ChainItem
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import (_always, _cast_now, _deck, _fight, _pick, _setup, _unit)


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


# -- Part 2 (BACKLOG.md D, Vendetta VEN-002..077) ---------------------------------

def _start_turn(loop, side="A"):
    """The Beginning Phase, then its start-of-turn triggers (as _begin_turn)."""
    loop._phase_beginning(side)
    loop._fire_turn_trigger("on_start_of_turn", side)
    loop._recompute_passives()


def _usable(loop, side, effect):
    """The index of `side`'s usable activated ability doing `effect`."""
    p = loop.gs.get_player(side)
    return next(i for i, e in enumerate(loop.activatable_abilities(side))
                if e.get("eff") is not None and e["eff"].effect == effect
                and loop._ability_usable(p, e))


def _equip(unit, name):
    gear = CARD_REGISTRY[name].instantiate()
    unit.gear.append(gear)
    return gear


def test_blade_twirler_burns_a_player_only_the_first_move_each_turn():
    """'The first time I move each turn, choose a player. They BURN 1.'"""
    loop, a, b = _setup()
    twirler = _unit("Blade Twirler")
    a.base_units.append(twirler)
    _deck(b, *[SpellCard(name=f"S{i}") for i in range(3)])
    loop._move_unit_by_effect(twirler, loop.gs.battlefields[0])
    burned = len(a.trash) + len(b.trash)
    loop._move_unit_by_effect(twirler, loop.gs.battlefields[1])
    assert burned == 1 and len(a.trash) + len(b.trash) == 1


def test_forsaken_baccai_counts_runes_before_the_channel():
    """'If you control fewer runes than an opponent at the start of your
    Beginning Phase, give me +1 [might] this turn.' 4 against 5, then channel 2."""
    loop, a, b = _setup()
    loop.gs.turn = 3
    baccai = _unit("Forsaken Baccai")
    a.base_units.append(baccai)
    _runes(a, 4)
    _runes(b, 5)
    a.rune_deck = RuneDeck([Rune(Domain.FURY) for _ in range(4)])
    _start_turn(loop)
    assert a.total_runes_in_play() == 6 and baccai.might == 3
    loop, a, b = _setup()
    loop.gs.turn = 3
    baccai = _unit("Forsaken Baccai")
    a.base_units.append(baccai)
    _runes(a, 5)
    _runes(b, 5)
    a.rune_deck = RuneDeck([Rune(Domain.FURY) for _ in range(4)])
    _start_turn(loop)
    assert baccai.might == 2


def test_oasis_raider_gets_two_and_ganking_with_fewer_runes():
    """'... give me +2 [might] and GANKING this turn.'"""
    loop, a, b = _setup()
    loop.gs.turn = 3
    raider = _unit("Oasis Raider")
    a.base_units.append(raider)
    _runes(a, 4)
    _runes(b, 5)
    a.rune_deck = RuneDeck([Rune(Domain.FURY) for _ in range(4)])
    _start_turn(loop)
    assert raider.might == 6 and raider.has_keyword("GANKING")


def test_baccai_reaper_may_pay_fury_for_assault_two():
    """'When I attack, you may pay [fury] to give me ASSAULT 2 this turn.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    reaper = _unit("Baccai Reaper")
    loop.gs.battlefields[0].add_unit("A", reaper)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 1))
    _attack_at(loop)
    assert reaper.keyword_value("ASSAULT") == 2 and a.power_pool[Domain.FURY] == 4


def test_pendulum_blade_gives_its_unit_two_when_it_moves_to_a_battlefield():
    """Equipment: 'When I move to a battlefield, give me +2 [might] this turn.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    _equip(unit, "Pendulum Blade")
    a.base_units.append(unit)
    loop._recompute_passives()
    base = unit.might
    loop._move_unit_by_effect(unit, loop.gs.battlefields[0])
    assert unit.might == base + 2


def test_hand_hammer_needs_exactly_one_other_friendly_unit_there():
    """Equipment: 'I have +2 [might] while I'm at a battlefield with exactly one
    other unit you control.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    _equip(unit, "Hand Hammer")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit)
    bf.add_unit("B", _unit("Enemy", 1))
    loop._recompute_passives()
    alone = unit.might
    bf.add_unit("A", _unit("Friend", 1))
    loop._recompute_passives()
    assert unit.might == alone + 2
    bf.add_unit("A", _unit("Friend 2", 1))
    loop._recompute_passives()
    assert unit.might == alone


def test_renekton_rage_fueled_hits_all_enemies_here_with_four_runes():
    """'When I attack, if you control 4 or fewer runes, deal 2 to all enemy units here.'"""
    loop, a, b = _setup()
    _runes(a, 4)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Renekton Rage Fueled"))
    e1, e2, far = _unit("E1", 9), _unit("E2", 9), _unit("Far", 9)
    bf.add_unit("B", e1)
    bf.add_unit("B", e2)
    loop.gs.battlefields[1].add_unit("B", far)
    _attack_at(loop)
    assert (e1.damage, e2.damage, far.damage) == (2, 2, 0)


def test_twilight_reveler_readies_another_friendly_unit():
    """'When I attack, ready another friendly unit.'"""
    loop, a, b = _setup()
    reveler = _unit("Twilight Reveler")
    tired = _unit("Tired", 1)
    tired.ready = False
    a.base_units.append(tired)
    loop.gs.battlefields[0].add_unit("A", reveler)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 1))
    reveler.ready = False
    _attack_at(loop)
    assert tired.ready and not reveler.ready


def test_zed_from_the_shadows_makes_a_shadow_clone_when_you_discard():
    """'You may discard 1 as an additional cost to play me. When you play me, if
    you paid the additional cost, play a 0 [might] Shadow Clone unit token.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    a.hand.extend([CARD_REGISTRY["Zed From the Shadows"].instantiate(), SpellCard(name="Junk")])
    loop._apply_action(a, ("UNIT", 0, None))
    names = sorted(u.card.name for u in a.base_units)
    assert names == ["Shadow Clone", "Zed From the Shadows"] and [c.name for c in a.trash] == ["Junk"]


def test_pakaa_protector_draws_a_unit_or_trashes_and_grows():
    """'When I move, reveal the top card of your Main Deck. If it's a unit, draw
    it. Otherwise, put it in your trash and give me +2 [might] this turn.'"""
    loop, a, b = _setup()
    pakaa = _unit("Pakaa Protector")
    a.base_units.append(pakaa)
    top_unit = UnitCard(name="Top", might=1)
    _deck(a, top_unit, SpellCard(name="Spell"))
    loop._move_unit_by_effect(pakaa, loop.gs.battlefields[0])
    assert top_unit in a.hand and pakaa.might == 4
    loop._move_unit_by_effect(pakaa, None)
    assert [c.name for c in a.trash] == ["Spell"] and pakaa.might == 6


def test_resonating_strike_moves_a_unit_to_a_battlefield_you_control():
    """'Choose a battlefield you control and a unit you control at a different
    location. Move that unit to that battlefield and give it +2 [might] this turn.'"""
    loop, a, b = _setup()
    held = loop.gs.battlefields[1]
    held.add_unit("A", _unit("Holder", 1))
    runner = _unit("Runner", 2)
    a.base_units.append(runner)
    _pick(loop, "Runner")
    _cast_now(loop, a, "Resonating Strike")
    assert runner in held.units_A and runner.might == 4


def test_riven_shattered_deals_two_per_attached_equipment():
    """'When I attack, choose an enemy unit here. Deal 2 to it for each Equipment
    attached to me.'"""
    loop, a, b = _setup()
    riven = _unit("Riven Shattered")
    _equip(riven, "Pendulum Blade")
    _equip(riven, "Hand Hammer")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", riven)
    enemy, far = _unit("Enemy", 9), _unit("Far", 9)
    bf.add_unit("B", enemy)
    loop.gs.battlefields[1].add_unit("B", far)
    _attack_at(loop)
    assert enemy.damage == 4 and far.damage == 0


def test_shen_scourge_draws_when_holding_with_exactly_one_other_friend():
    """'When I hold, if there is exactly one other unit you control here, draw 1.'"""
    for friends, drawn in ((0, 0), (1, 1), (2, 0)):
        loop, a, b = _setup()
        _deck(a, *[SpellCard(name=f"S{i}") for i in range(3)])
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Shen Scourge of Shadows"))
        for i in range(friends):
            bf.add_unit("A", _unit(f"F{i}", 1))
        loop._fire_scoring_trigger("on_hold", bf, "A")
        assert len(a.hand) == drawn, friends


def test_astral_heron_discounts_the_second_card_when_at_a_battlefield():
    """'When you play your first card each turn, if I'm at a battlefield, the next
    card you play this turn costs [2] [rune] [rune] less.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Astral Heron"))
    a.hand.append(UnitCard(name="First", might=1, cost_energy=1))
    loop._apply_action(a, ("UNIT", 0, None))
    second = UnitCard(name="Second", might=1, cost_energy=4, cost_power=2)
    assert loop._effective_cost(second, a)[:2] == (2, 0)


def test_nasus_ascended_scores_when_conquering_only_empowered():
    """'EMPOWERED: When I conquer, you score 1 point.'"""
    loop, a, b = _setup()
    nasus = _unit("Nasus Ascended")
    loop.gs.battlefields[0].add_unit("A", nasus)
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert loop.gs.points_A == 0
    nasus.empowered = True
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert loop.gs.points_A == 1


def test_apprentice_mage_predicts_when_empowered_not_when_played(monkeypatch):
    """'When I become EMPOWERED, PREDICT 2.' Played: nothing."""
    loop, a, b = _setup()
    seen = []
    monkeypatch.setitem(REGISTRY, "predict",
                        lambda ctx, spec: ctx.loop is loop and seen.append(spec.get("amount")))
    a.hand.append(CARD_REGISTRY["Apprentice Mage"].instantiate())
    loop._apply_action(a, ("UNIT", 0, None))
    assert seen == []
    loop._empower(a.base_units[0].card, "A")
    assert seen == [2]


def test_clairvoyance_predicts_five_then_draws_two(monkeypatch):
    """'PREDICT 5. Draw 2.'"""
    loop, a, b = _setup()
    seen = []
    monkeypatch.setitem(REGISTRY, "predict", lambda ctx, spec: seen.append(spec.get("amount")))
    _deck(a, *[SpellCard(name=f"S{i}") for i in range(6)])
    _cast_now(loop, a, "Clairvoyance")
    assert seen == [5] and len(a.hand) == 2


def test_iterative_design_has_its_flow_cost():
    """'Play a 3 [might] Mech unit token. [Flow] [2] [Mind]'"""
    card = CARD_REGISTRY["Iterative Design"].instantiate()
    assert card.flow_cost == {"energy": 2, "power": 1, "domain": "MIND"}
    loop, a, b = _setup()
    _cast_now(loop, a, "Iterative Design")
    assert [(u.card.name, u.might) for u in a.base_units + loop.gs.battlefields[0].units_A] == [("Mech", 3)]


def test_mesmerize_returns_a_friend_to_hand_or_shrinks_an_enemy():
    """'Choose one - Return a friendly unit to its owner's hand. / Give an enemy
    unit -2 [might] this turn.'"""
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    a.base_units.append(mine)
    loop.chooser = lambda _l, kind, side, options, default, source: 0 if kind.startswith("mode") else None
    _cast_now(loop, a, "Mesmerize")
    assert mine.card in a.hand and not a.base_units
    loop, a, b = _setup()
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.chooser = lambda _l, kind, side, options, default, source: 1 if kind.startswith("mode") else None
    _cast_now(loop, a, "Mesmerize")
    assert enemy.might == 3


def test_patched_porobot_draws_with_three_other_gear():
    """'When you play me, if you control 3 or more other gear, draw 1.'"""
    for gear, drawn in ((2, 0), (3, 1)):
        loop, a, b = _setup()
        _deck(a, SpellCard(name="S"))
        a.base_gear.extend(GearCard(name=f"G{i}") for i in range(gear))
        loop._play_unit(CARD_REGISTRY["Patched Porobot"].instantiate(), "A")
        assert len(a.hand) == drawn


def test_hextech_formula_and_platewyrm_egg_enter_exhausted():
    """'This enters exhausted.'"""
    for name in ("Hextech Formula", "Platewyrm Egg"):
        loop, a, b = _setup()
        gear = CARD_REGISTRY[name].instantiate()
        loop._play_gear(gear, "A")
        assert gear in a.base_gear and gear.tapped, name


def test_platewyrm_egg_adds_one_or_two_when_empowered():
    """'EMPOWER - [1], [tap]. REACTION [tap]: ADD [1]. If this is EMPOWERED, ADD [2]
    instead.'"""
    loop, a, b = _setup()
    egg = CARD_REGISTRY["Platewyrm Egg"].instantiate()
    a.base_gear.append(egg)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "gain_energy"))
    assert a.energy == 21
    egg.tapped, egg.empowered = False, True
    loop._apply_activated_ability(a, b, _usable(loop, "A", "gain_energy"))
    assert a.energy == 23


def test_nasus_guardian_channels_once_per_turn_when_an_enemy_dies_here():
    """'Once each turn, when an enemy unit here dies, channel 1 rune exhausted.'"""
    loop, a, b = _setup()
    a.rune_deck = RuneDeck([Rune(Domain.MIND) for _ in range(3)])
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Nasus Guardian of Knowledge"))
    e1, e2, far = _unit("E1", 1), _unit("E2", 1), _unit("Far", 1)
    bf.add_unit("B", e1)
    bf.add_unit("B", e2)
    loop._route_deaths([(far, "B")], loop.gs.battlefields[1])
    assert a.total_runes_in_play() == 0
    for e in (e1, e2):
        bf.units_B.remove(e)
        loop._route_deaths([(e, "B")], bf)
    assert a.total_runes_in_play() == 1


def test_swain_visionary_scores_after_unit_gear_and_spell():
    """'When I conquer, if you've played a non-token unit, a non-token gear, and a
    spell this turn, you score 1 point.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Swain Visionary"))
    for card in (UnitCard(name="U", might=1), GearCard(name="G")):
        loop.gs.played_cards_this_turn["A"].append(card)
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert loop.gs.points_A == 0
    loop.gs.played_cards_this_turn["A"].append(SpellCard(name="S"))
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert loop.gs.points_A == 1


def test_bottled_constellation_kills_three_others_for_a_point():
    """'At the start of your Main Phase, you may kill 3 other friendly units
    and/or gear to score 1 point.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    bottle = CARD_REGISTRY["Bottled Constellation"].instantiate()
    a.base_gear.append(bottle)
    a.base_units.extend([_unit("U1", 1), _unit("U2", 1)])
    a.base_gear.append(GearCard(name="G1"))
    loop._fire_turn_trigger("on_start_of_main", "A")
    assert loop.gs.points_A == 1 and a.base_gear == [bottle] and not a.base_units


def test_fretful_feline_grows_when_readied():
    """'When I become ready, give me +2 [might] this turn.'"""
    loop, a, b = _setup()
    feline = _unit("Fretful Feline")
    feline.ready = False
    loop.gs.battlefields[0].add_unit("A", feline)
    REGISTRY["ready_unit"](_ctx(loop, a), {"target": "friendly_unit", "where": "anywhere"})
    assert feline.ready and feline.might == 7


def test_repair_specialist_has_assault_per_gear():
    """'I have ASSAULT equal to the number of gear you control.'"""
    loop, a, b = _setup()
    rs = _unit("Repair Specialist")
    a.base_units.append(rs)
    a.base_gear.extend([GearCard(name="G1"), GearCard(name="G2")])
    loop._recompute_passives()
    assert rs.keyword_value("ASSAULT") == 2


def test_tools_of_empire_gives_two_or_four_when_empowered():
    """'[tap]: Give a unit +2 [might] this turn. If this is EMPOWERED, +4 instead.'"""
    loop, a, b = _setup()
    tools = CARD_REGISTRY["Tools of Empire"].instantiate()
    a.base_gear.append(tools)
    unit = _unit("Unit", 1)
    a.base_units.append(unit)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "grant_temporary_might"))
    assert unit.might == 3
    tools.tapped, tools.empowered = False, True
    loop._apply_activated_ability(a, b, _usable(loop, "A", "grant_temporary_might"))
    assert unit.might == 7


def test_covert_informant_draws_on_move_only_empowered():
    """'EMPOWERED: When I move, draw 1.'"""
    loop, a, b = _setup()
    _deck(a, *[SpellCard(name=f"S{i}") for i in range(3)])
    spy = _unit("Covert Informant")
    a.base_units.append(spy)
    loop._move_unit_by_effect(spy, loop.gs.battlefields[0])
    assert not a.hand
    spy.empowered = True
    loop._move_unit_by_effect(spy, None)
    assert len(a.hand) == 1


def test_applied_researchers_discount_spells_to_a_minimum_of_one():
    """'EMPOWERED: Your spells cost [1] [rune] less, to a minimum of [1].'"""
    loop, a, b = _setup()
    res = _unit("Applied Researchers")
    a.base_units.append(res)
    spell = SpellCard(name="S", cost_energy=3, cost_power=1)
    cheap = SpellCard(name="C", cost_energy=1)
    assert loop._effective_cost(spell, a)[:2] == (3, 1)
    res.empowered = True
    assert loop._effective_cost(spell, a)[:2] == (2, 0) and loop._effective_cost(cheap, a)[0] == 1


def test_steel_paws_has_seven_more_when_empowered():
    """'DEFLECT. EMPOWER [7]. EMPOWERED: I have +7 [might].'"""
    loop, a, b = _setup()
    paws = _unit("Steel Paws")
    a.base_units.append(paws)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert a.energy == 13 and paws.might == 7 and paws.has_keyword("DEFLECT")


def test_twilight_shroud_pumps_and_hides_from_enemies():
    """'Give a friendly unit +1 [might] this turn. It can't be chosen by enemy
    spells and abilities this turn.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    _cast_now(loop, a, "Twilight Shroud")
    assert unit.might == 3
    assert not loop._can_choose(unit, "B", SpellCard(name="S"))
    assert loop._can_choose(unit, "A", SpellCard(name="S"))


def test_esteemed_hierophant_ignores_enemy_ability_damage_at_seven_runes():
    """'While you control 7 or more runes, prevent all damage that enemy spells
    and abilities would deal to me.'"""
    loop, a, b = _setup()
    _runes(a, 7)
    hiero = _unit("Esteemed Hierophant")
    loop.gs.battlefields[0].add_unit("A", hiero)
    sky = _unit("Sky Cruiser")
    b.base_units.append(sky)
    loop._recompute_passives()
    REGISTRY["deal_damage"](_ctx(loop, b, sky.card), {"target": "enemy_unit", "amount": 4})
    assert hiero.damage == 0
    REGISTRY["deal_damage"](_ctx(loop, a), {"target": "friendly_unit", "amount": 4})
    assert hiero.damage == 4


def test_brittle_steel_kills_any_gear():
    """'Kill a gear.'"""
    loop, a, b = _setup()
    theirs = GearCard(name="Theirs", cost_energy=3)
    b.base_gear.append(theirs)
    _cast_now(loop, a, "Brittle Steel")
    assert theirs not in b.base_gear and theirs in b.trash


def test_shadow_assassin_enters_ready_with_a_copy_in_trash():
    """'I enter ready if you have a card with my name in your trash.'"""
    loop, a, b = _setup()
    assert not loop._play_unit(CARD_REGISTRY["Shadow Assassin"].instantiate(), "A").ready
    a.trash.append(CARD_REGISTRY["Shadow Assassin"].instantiate())
    assert loop._play_unit(CARD_REGISTRY["Shadow Assassin"].instantiate(), "A").ready


def test_eclipse_dragon_draws_on_move_with_four_runes():
    """'When I move, if you control 4 or fewer runes, draw 1.'"""
    for runes, drawn in ((4, 1), (5, 0)):
        loop, a, b = _setup()
        _runes(a, runes)
        _deck(a, SpellCard(name="S"))
        dragon = _unit("Eclipse Dragon")
        a.base_units.append(dragon)
        loop._move_unit_by_effect(dragon, loop.gs.battlefields[0])
        assert len(a.hand) == drawn


# -- Part 3 (BACKLOG.md D, Vendetta VEN-078..156) --------------------------------

def test_baccai_witherclaw_grows_and_channels_two_on_death_when_empowered():
    """'EMPOWER [1] [rune] [rune]. EMPOWERED: +2 [might]. EMPOWERED DEATHKNELL:
    Channel 2 runes exhausted.'"""
    loop, a, b = _setup()
    a.rune_deck = RuneDeck([Rune(Domain.BODY) for _ in range(3)])
    claw = _unit("Baccai Witherclaw")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", claw)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert claw.empowered and claw.might == 6 and a.energy == 19
    bf.remove_unit("A", claw)
    loop._route_deaths([(claw, "A")], bf)
    runes = [r for rs in a.rune_pool.values() for r in rs]
    assert len(runes) == 2 and not any(r.ready for r in runes)


def test_onslaught_gives_six_and_has_flow_four():
    """'Give a unit +6 [might] this turn. FLOW [4]'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    _cast_now(loop, a, "Onslaught")
    assert unit.might == 8
    assert CARD_REGISTRY["Onslaught"].instantiate().flow_cost["energy"] == 4


def test_profiteer_moves_empowerment_to_a_card_that_uses_it():
    """'When you play me, you may disempower something you control to empower a
    legend, unit, or gear.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    idle, user = _unit("Idle", 2), _unit("Kinkou Lifeblade")
    idle.empowered = True
    a.base_units.extend([idle, user])
    loop._play_unit(CARD_REGISTRY["Profiteer"].instantiate(), "A")
    assert not idle.empowered and user.empowered


def test_hextech_disc_spends_its_empowerment_on_a_mech():
    """'EMPOWER - [tap]. Disempower this, [1], [tap]: Play a 3 [might] Mech unit
    token to your base.'"""
    loop, a, b = _setup()
    disc = CARD_REGISTRY["Hextech Disc"].instantiate()
    a.base_gear.append(disc)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert disc.empowered and disc.tapped
    disc.tapped = False
    loop._apply_activated_ability(a, b, _usable(loop, "A", "play_token"))
    assert [(u.card.name, u.might) for u in a.base_units] == [("Mech", 3)]
    assert not disc.empowered and disc.tapped and a.energy == 19


def test_jayce_hammer_in_hand_picks_a_keyword_when_readied():
    """'When I become ready, choose one to give me this turn - ASSAULT 2 /
    DEFLECT 2 / GANKING.'"""
    loop, a, b = _setup()
    jayce = _unit("Jayce Hammer in Hand")
    jayce.ready = False
    a.base_units.append(jayce)
    loop.chooser = lambda _l, kind, side, options, default, source: 2 if kind.startswith("mode") else None
    _start_turn(loop)
    assert jayce.ready and jayce.has_keyword("GANKING")


def test_cataclysmic_duel_leaves_each_player_one_unit():
    """'Each player chooses a unit they control. Kill the rest.'"""
    loop, a, b = _setup()
    a.base_units.extend([_unit("A1", 1), _unit("A2", 5)])
    loop.gs.battlefields[0].add_unit("B", _unit("B1", 3))
    loop.gs.battlefields[1].add_unit("B", _unit("B2", 4))
    _cast_now(loop, a, "Cataclysmic Duel")
    left = a.base_units + b.base_units + [u for bf in loop.gs.battlefields for u in bf.units_A + bf.units_B]
    assert sorted(u.card.name for u in left) == ["A2", "B2"]


def test_renekton_brute_pumps_and_empowers_at_ten():
    """'[1]: Give me +1 [might] this turn. When my Might becomes 10 or more,
    empower me. EMPOWERED: DEFLECT and GANKING.'"""
    loop, a, b = _setup()
    brute = _unit("Renekton Brute")
    loop.gs.battlefields[0].add_unit("A", brute)
    for _ in range(5):
        loop._apply_activated_ability(a, b, _ability(loop, "A", "grant_temporary_might"))
        loop._recompute_passives()
    assert brute.might == 9 and not brute.empowered
    loop._apply_activated_ability(a, b, _ability(loop, "A", "grant_temporary_might"))
    loop._recompute_passives()
    assert brute.empowered and brute.has_keyword("GANKING") and brute.has_keyword("DEFLECT")


def test_kinkou_lifeblade_and_solari_sunhawk_when_empowered():
    """'EMPOWERED: +1 [might] and GANKING' / '+1 [might] and DEFLECT 2'."""
    for name, kw in (("Kinkou Lifeblade", "GANKING"), ("Solari Sunhawk", "DEFLECT")):
        loop, a, b = _setup()
        unit = _unit(name)
        a.base_units.append(unit)
        printed = unit.might
        loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
        loop._recompute_passives()
        assert unit.might == printed + 1 and unit.has_keyword(kw) and a.energy == 18, name


def test_mask_mother_pumps_a_friend_when_discarded():
    """'When you discard me, you may pay [1] to give a friendly unit +2 [might]
    this turn.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    friend = _unit("Friend", 2)
    a.base_units.append(friend)
    mother = CARD_REGISTRY["Mask Mother"].instantiate()
    a.hand.append(mother)
    loop._discard(a, mother)
    assert friend.might == 4 and a.energy == 19


def test_shadow_order_disciple_may_burn_one_to_grow_when_it_moves():
    """'When I move, you may BURN 1 to give me +1 [might] this turn.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    disciple = _unit("Shadow Order Disciple")
    a.base_units.append(disciple)
    _deck(a, SpellCard(name="S1"), SpellCard(name="S2"))
    loop._move_unit_by_effect(disciple, loop.gs.battlefields[0])
    assert disciple.might == 3 and [c.name for c in a.trash] == ["S1"]


def test_shadowblade_lurker_costs_two_less_per_copy_in_trash():
    """'I cost [2] less for each card with my name in your trash.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Shadowblade Lurker"].instantiate()
    full = loop._effective_cost(card, a)[0]
    a.trash.extend(CARD_REGISTRY["Shadowblade Lurker"].instantiate() for _ in range(2))
    assert loop._effective_cost(card, a)[0] == full - 4


def test_stargazer_discounts_flow_from_the_trash_to_one():
    """'Spells with FLOW you play from your trash cost [2] less, to a minimum of [1].'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Stargazer"))
    onslaught, step = (CARD_REGISTRY[n].instantiate() for n in ("Onslaught", "Up from the Deep"))
    assert loop._flow_cost(onslaught, "A")[0] == 2 and loop._flow_cost(step, "A")[0] == 1
    assert loop._effective_cost(onslaught, a)[0] == onslaught.cost_energy


def test_up_from_the_deep_plays_two_tentacles():
    """'Play two 1 [might] Tentacle unit tokens. FLOW [3]'"""
    loop, a, b = _setup()
    _cast_now(loop, a, "Up from the Deep")
    units = a.base_units + [u for bf in loop.gs.battlefields for u in bf.units_A]
    assert [(u.card.name, u.might) for u in units] == [("Tentacle", 1)] * 2


def test_gust_monk_banishes_from_a_trash_for_assault_two():
    """'You may pay [1] as an additional cost to play me. When you play me, if you
    paid the additional cost, banish a card from any trash to give a unit
    ASSAULT 2 this turn.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    b.trash.append(SpellCard(name="Theirs"))
    friend = _unit("Friend", 2)
    a.base_units.append(friend)
    a.hand.append(CARD_REGISTRY["Gust Monk"].instantiate())
    loop._apply_action(a, ("UNIT", 0, None))
    assert not b.trash and [c.name for c in b.banished] == ["Theirs"]
    assert any(u.keyword_value("ASSAULT") == 2 for u in a.base_units)


def test_ravenbloom_prefect_banishes_itself_and_an_enemy_gear():
    """'When an opponent plays a gear, you may banish me to banish it.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    prefect = _unit("Ravenbloom Prefect")
    b.base_units.append(prefect)
    gear = GearCard(name="Gear", cost_energy=2)
    loop._play_gear(gear, "A")
    assert gear not in a.base_gear and gear in a.banished
    assert prefect not in b.base_units and prefect.card in b.banished


def test_shadows_of_the_past_returns_two_units_from_trashes():
    """'Return up to 2 units from trashes to their owners' hands.'"""
    loop, a, b = _setup()
    mine, theirs, spell = UnitCard(name="Mine", might=1), UnitCard(name="Theirs", might=1), SpellCard(name="S")
    a.trash.extend([mine, spell])
    b.trash.append(theirs)
    loop.chooser = lambda _l, kind, side, options, default, source: (
        next(i for i, o in enumerate(options) if o in (mine, theirs)) if kind.startswith("card") else None)
    _cast_now(loop, a, "Shadows of the Past")
    assert mine in a.hand and theirs in b.hand and spell in a.trash


def test_twilight_step_moves_a_small_unit():
    """'Move a unit with 3 [might] or less.'"""
    loop, a, b = _setup()
    small, big = _unit("Small", 3), _unit("Big", 4)
    a.base_units.extend([big, small])
    _cast_now(loop, a, "Twilight Step")
    assert big in a.base_units and small not in a.base_units


def test_wind_and_ghosts_banishes_small_returns_big():
    """'Choose a unit at a battlefield. If it has 3 [might] or less, banish it.
    Otherwise, return it to its owner's hand.'"""
    for might, zone in ((3, "banished"), (4, "hand")):
        loop, a, b = _setup()
        enemy = _unit("Enemy", might)
        loop.gs.battlefields[0].add_unit("B", enemy)
        _cast_now(loop, a, "Wind and Ghosts")
        assert enemy.card in getattr(b, zone), might


def test_forgotten_relic_buffs_by_a_burned_units_might():
    """'When you play this or at the start of your Beginning Phase, BURN 1. When
    you burn a unit this way, give a friendly unit +[might] equal to the burned
    card's Might this turn.'"""
    loop, a, b = _setup()
    friend = _unit("Friend", 1)
    a.base_units.append(friend)
    _deck(a, UnitCard(name="Burned", might=4), SpellCard(name="Spell"))
    loop._play_gear(CARD_REGISTRY["Forgotten Relic"].instantiate(), "A")
    assert friend.might == 5
    loop.gs.turn = 3
    _start_turn(loop)
    assert [c.name for c in a.trash] == ["Burned", "Spell"] and friend.might == 5


def test_mel_defiant_soul_discards_a_spell_and_banishes_a_small_enemy():
    """'EMPOWER - Discard a spell. When I become EMPOWERED, banish an enemy unit
    at a battlefield with 3 [might] or less.'"""
    loop, a, b = _setup()
    mel = _unit("Mel Defiant Soul")
    a.base_units.append(mel)
    a.hand.extend([UnitCard(name="Unit", might=1), SpellCard(name="Spell")])
    small, big = _unit("Small", 3), _unit("Big", 4)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.gs.battlefields[0].add_unit("B", big)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert mel.empowered and [c.name for c in a.trash] == ["Spell"]
    assert small.card in b.banished and big in loop.gs.battlefields[0].units_B


def test_minah_swiftfoot_draws_or_discards_for_each_player_at_a_battlefield():
    """'When I move to a battlefield, choose one - Each player discards 1. / Each
    player draws 1.'"""
    loop, a, b = _setup()
    minah = _unit("Minah Swiftfoot")
    a.base_units.append(minah)
    _deck(a, SpellCard(name="A1"))
    _deck(b, SpellCard(name="B1"))
    loop.chooser = lambda _l, kind, side, options, default, source: 1 if kind.startswith("mode") else None
    loop._move_unit_by_effect(minah, loop.gs.battlefields[0])
    assert len(a.hand) == 1 and len(b.hand) == 1
    loop.chooser = lambda _l, kind, side, options, default, source: 0 if kind.startswith("mode") else None
    loop._move_unit_by_effect(minah, None)
    assert len(a.hand) == 1                       # to base: nothing
    loop._move_unit_by_effect(minah, loop.gs.battlefields[1])
    assert not a.hand and not b.hand


def test_zed_without_a_sound_makes_a_clone_and_swaps_with_it():
    """'When I conquer, play a 0 [might] Shadow Clone unit token to your base.
    ACTION [1] [Chaos]: Move me and a Shadow Clone you control to each other's
    locations.'"""
    loop, a, b = _setup()
    zed = _unit("Zed Without a Sound")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", zed)
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    clone = next(u for u in a.base_units if u.card.name == "Shadow Clone")
    loop._apply_activated_ability(a, b, _ability(loop, "A", "swap_position"))
    assert zed in a.base_units and clone in bf.units_A and a.energy == 19


def test_kennen_storm_of_shuriken_burns_two_and_gives_flow_on_conquer():
    """'When you play me, BURN 2. When I conquer, give a spell in your trash FLOW
    equal to its cost this turn.'"""
    loop, a, b = _setup()
    spell = CARD_REGISTRY["Wind and Ghosts"].instantiate()
    _deck(a, spell, SpellCard(name="S2"), SpellCard(name="S3"))
    kennen = loop._play_unit(CARD_REGISTRY["Kennen Storm of Shuriken"].instantiate(), "A")
    assert len(a.trash) == 2 and loop._flow_cost(spell, "A") is None
    a.base_units.remove(kennen)
    loop.gs.battlefields[0].add_unit("A", kennen)
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert loop._flow_cost(spell, "A")[:2] == (3, 1)


def test_kharox_burns_three_and_plays_a_unit_from_their_trash():
    """'When I become EMPOWERED, choose an opponent. They BURN 3. Then you may
    choose a unit in their trash and play it, ignoring its cost.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    kharox = _unit("Kharox")
    a.base_units.append(kharox)
    _deck(b, SpellCard(name="S1"), UnitCard(name="Theirs", might=3), SpellCard(name="S3"))
    loop._empower(kharox.card, "A")
    assert len(b.trash) == 2 and any(u.card.name == "Theirs" for u in a.base_units)


def test_tornado_warrior_empowers_something_here_until_end_of_turn():
    """'HIDDEN. When you play me from face down, you may empower something here.
    Disempower it at end of turn.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    loop.gs.turn = 3
    bf = loop.gs.battlefields[0]
    friend = _unit("Kinkou Lifeblade")
    bf.add_unit("A", friend)
    bf.facedown = FacedownCard(card=CARD_REGISTRY["Tornado Warrior"].instantiate(), owner="A", turn_hidden=1)
    assert loop._play_from_hidden("A", 0)
    assert friend.empowered
    loop._end_turn()
    assert not friend.empowered


def test_dragon_form_sets_base_might_to_five():
    """'Choose a unit. Its base Might becomes 5 this turn. FLOW [3]'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    _cast_now(loop, a, "Dragon Form")
    loop._recompute_passives()
    assert unit.might == 5


def test_disciple_of_shen_has_shield_three_with_exactly_one_friend():
    """'I have SHIELD 3 while I'm at a battlefield with exactly one other unit you
    control.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    disciple = _unit("Disciple of Shen")
    bf.add_unit("A", disciple)
    loop._recompute_passives()
    assert disciple.keyword_value("SHIELD") == 0
    bf.add_unit("A", _unit("F1", 1))
    loop._recompute_passives()
    assert disciple.keyword_value("SHIELD") == 3
    bf.add_unit("A", _unit("F2", 1))
    loop._recompute_passives()
    assert disciple.keyword_value("SHIELD") == 0


def test_horns_of_the_dragon_tank_and_soulspinner_ambush():
    assert _unit("Horns of the Dragon").has_keyword("TANK")
    assert _unit("Soulspinner").has_keyword("AMBUSH")


def test_keeper_of_law_discounted_with_a_two_unit_battlefield():
    """'I cost [2] [order] less if you control a battlefield with exactly two
    units there.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Keeper of Law"].instantiate()
    assert loop._effective_cost(card, a)[:2] == (5, 1)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("F1", 1))
    bf.add_unit("A", _unit("F2", 1))
    assert loop._effective_cost(card, a)[:2] == (3, 0)


def test_masa_crashing_thunder_stuns_with_the_additional_cost():
    """'You may pay [order] as an additional cost to play me. When you play me, if
    you paid the additional cost, STUN an enemy unit at a battlefield.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.hand.append(CARD_REGISTRY["Masa Crashing Thunder"].instantiate())
    loop._apply_action(a, ("UNIT", 0, None))
    assert enemy.stunned and a.power_pool[Domain.ORDER] == 4


def test_reluctant_leader_grows_when_you_play_another_unit():
    """'When you play another unit, give me +2 [might] this turn.'"""
    loop, a, b = _setup()
    leader = loop._play_unit(CARD_REGISTRY["Reluctant Leader"].instantiate(), "A")
    assert leader.might == 3
    loop._play_unit(UnitCard(name="Other", might=1), "A")
    assert leader.might == 5


def test_escaped_grayback_kills_a_friend_to_empower():
    """'EMPOWER - Kill a friendly unit. EMPOWERED: +2 [might].'"""
    loop, a, b = _setup()
    grayback, friend = _unit("Escaped Grayback"), _unit("Friend", 1)
    a.base_units.extend([grayback, friend])
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    loop._recompute_passives()
    assert grayback.empowered and grayback.might == 5 and friend not in a.base_units


def test_hungry_wolf_readies_once_after_choosing_an_enemy():
    """'[order]: Ready me and give me +1 [might] this turn. Use only if you've
    chosen an enemy unit this turn and only once each turn.'"""
    loop, a, b = _setup()
    wolf = _unit("Hungry Wolf")
    wolf.ready = False
    a.base_units.append(wolf)
    enemy = _unit("Enemy", 1)
    loop.gs.battlefields[0].add_unit("B", enemy)
    assert not any(loop._ability_usable(a, e) for e in loop.activatable_abilities("A")
                   if e.get("eff") is not None and e["eff"].effect == "sequence")
    loop._note_chosen(SpellCard(name="Spell"), "A", [enemy])
    loop._apply_activated_ability(a, b, _usable(loop, "A", "sequence"))
    assert wolf.ready and wolf.might == 5
    wolf.ready = False
    assert not any(loop._ability_usable(a, e) for e in loop.activatable_abilities("A")
                   if e.get("eff") is not None and e["eff"].effect == "sequence")


def test_ki_barrier_prevents_the_next_seven():
    """'Choose a unit. Prevent the next 7 damage that would be dealt to it this turn.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 9)
    loop.gs.battlefields[0].add_unit("A", unit)
    _cast_now(loop, a, "Ki Barrier")
    REGISTRY["deal_damage"](_ctx(loop, b), {"target": "enemy_unit", "amount": 8, "where": "anywhere"})
    assert unit.damage == 1


def test_lacerate_disempowers_then_kills_a_small_unit():
    """'Choose a unit. If it's EMPOWERED, disempower it. Then kill it if it has 3
    [might] or less.' Sunhawk is 4 empowered, 3 without."""
    loop, a, b = _setup()
    hawk = _unit("Solari Sunhawk")
    hawk.empowered = True
    loop.gs.battlefields[0].add_unit("B", hawk)
    loop._recompute_passives()
    assert hawk.might == 4
    _cast_now(loop, a, "Lacerate")
    assert hawk.card in b.trash
    assert CARD_REGISTRY["Lacerate"].instantiate().flow_cost == {"energy": 4, "power": 2, "domain": "ORDER"}


def test_noxian_emissary_leaves_two_recruits_when_it_dies_empowered():
    """'EMPOWERED DEATHKNELL: Play two 1 [might] Recruit unit tokens to your base.'"""
    for empowered, recruits in ((False, 0), (True, 2)):
        loop, a, b = _setup()
        bf = loop.gs.battlefields[0]
        emissary = _unit("Noxian Emissary")
        emissary.empowered = empowered
        bf.add_unit("A", emissary)
        bf.remove_unit("A", emissary)
        loop._route_deaths([(emissary, "A")], bf)
        assert [u.card.name for u in a.base_units] == ["Recruit"] * recruits


def test_sacred_protector_deals_combat_damage_only_with_exactly_one_friend():
    """'I don't deal combat damage unless I'm at a battlefield with exactly one
    other unit you control.'"""
    for friends, killed in ((0, False), (1, True)):
        loop, a, b = _setup()
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Sacred Protector"))
        for i in range(friends):
            bf.add_unit("A", _unit(f"F{i}", 0))
        enemy = _unit("Enemy", 5)
        bf.add_unit("B", enemy)
        _fight(loop)
        assert (enemy not in bf.units_B) == killed, friends


def test_fallen_feline_forbids_the_named_spell_while_at_a_battlefield():
    """'When you play me, name a spell. While I'm at a battlefield, opponents
    can't play spells with that name.'"""
    loop, a, b = _setup()
    b.trash.append(CARD_REGISTRY["Onslaught"].instantiate())
    feline = loop._play_unit(CARD_REGISTRY["Fallen Feline"].instantiate(), "A")
    onslaught = CARD_REGISTRY["Onslaught"].instantiate()
    assert not loop._play_forbidden(b, onslaught)
    a.base_units.remove(feline)
    loop.gs.battlefields[0].add_unit("A", feline)
    assert loop._play_forbidden(b, onslaught)
    assert not loop._play_forbidden(a, onslaught)


def test_glowstone_burns_its_controllers_units_at_the_end_of_their_turn():
    """'EMPOWER [rune] [rune]. Disempower this, [tap]: Choose a player. They gain
    control of this and recall it. At the end of your turn, kill this and deal 5
    to all units you control.'"""
    loop, a, b = _setup()
    stone = CARD_REGISTRY["Glowstone"].instantiate()
    a.base_gear.append(stone)
    mine, theirs = _unit("Mine", 9), _unit("Theirs", 9)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.gs.battlefields[1].add_unit("B", theirs)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert stone.empowered
    stone.tapped = False
    loop._apply_activated_ability(a, b, _usable(loop, "A", "give_this_to_opponent"))
    assert stone in b.base_gear and not stone.empowered
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert mine.damage == 0 and stone in b.base_gear
    loop._fire_turn_trigger("on_end_of_turn", "B")
    assert theirs.damage == 5 and stone in b.trash


def test_kayle_justified_empowers_three_times():
    """'EMPOWER [3]. I can be EMPOWERED up to three times. +2 [might] for each
    time. While EMPOWERED three times, DEFLECT 3 and GANKING.'"""
    loop, a, b = _setup()
    kayle = _unit("Kayle Justified")
    a.base_units.append(kayle)
    for times in (1, 2, 3):
        loop._apply_activated_ability(a, b, _usable(loop, "A", "empower_self"))
        loop._recompute_passives()
        assert kayle.might == 3 + 2 * times, times
    assert kayle.keyword_value("DEFLECT") == 3 and kayle.has_keyword("GANKING")
    assert not any(loop._ability_usable(a, e) for e in loop.activatable_abilities("A")
                   if e.get("eff") is not None and e["eff"].effect == "empower_self")


def test_kennen_keeper_of_balance_stuns_and_grows_next_to_a_stunned_enemy():
    """'When you play me or I attack, you may pay [2] to STUN a unit. While
    there's a stunned enemy unit here, I have +2 [might].'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    bf = loop.gs.battlefields[0]
    enemy = _unit("Enemy", 3)
    bf.add_unit("B", enemy)
    kennen = loop._play_unit(CARD_REGISTRY["Kennen Keeper of Balance"].instantiate(), "A")
    assert enemy.stunned and a.energy == 18 and kennen.might == 2
    a.base_units.remove(kennen)
    bf.add_unit("A", kennen)
    loop._recompute_passives()
    assert kennen.might == 4


def test_ambessa_respected_kills_a_weaker_enemy_when_attacking_empowered():
    """'EMPOWERED: [Assault 2]. EMPOWERED: When I attack, kill an enemy unit here
    with less Might than me.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    ambessa = _unit("Ambessa Respected and Feared")
    ambessa.empowered = True
    bf.add_unit("A", ambessa)
    weak, strong = _unit("Weak", 6), _unit("Strong", 8)
    bf.add_unit("B", weak)
    bf.add_unit("B", strong)
    loop._recompute_passives()
    _attack_at(loop)
    assert ambessa.keyword_value("ASSAULT") == 2
    assert weak not in bf.units_B and strong in bf.units_B


def test_shen_leader_scores_holding_with_exactly_one_friend():
    """'When I hold, if there is exactly one other unit you control here, you
    score 1 point.'"""
    for friends, points in ((0, 0), (1, 1), (2, 0)):
        loop, a, b = _setup()
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Shen Leader of the Kinkou Order"))
        for i in range(friends):
            bf.add_unit("A", _unit(f"F{i}", 1))
        before = loop.gs.points_A
        loop._fire_scoring_trigger("on_hold", bf, "A")
        assert loop.gs.points_A - before == points, friends


def test_assault_and_shield_hold_for_the_whole_combat_only():
    """ASSAULT: 'While I'm an attacker, I have +X [might]' (§807.1.c-d), from the
    designation until the combat ends; SHIELD the same for a defender."""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    atk, dfn = _unit("Atk", 5, turn_keywords=["ASSAULT 2"]), _unit("Def", 1, turn_keywords=["SHIELD 3"])
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    loop._recompute_passives()
    assert (atk.might, dfn.might) == (5, 1)
    _attack_at(loop)
    assert (atk.might, dfn.might) == (7, 4)
    _fight(loop)
    loop._recompute_passives()
    assert atk.might == 5


def test_shuriken_flip_deals_two_then_moves_a_friend():
    """'Deal 2 to up to one enemy unit at a battlefield, then move a friendly
    unit. FLOW [3] [rune]'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    friend = _unit("Friend", 2)
    a.base_units.append(friend)
    _cast_now(loop, a, "Shuriken Flip")
    assert enemy.damage == 2 and friend not in a.base_units
    assert CARD_REGISTRY["Shuriken Flip"].instantiate().flow_cost == {"energy": 3, "power": 1, "domain": None}


def test_renekton_butcher_energy_only_for_units_and_their_abilities():
    """'REACTION [rune] [rune], [tap]: ADD [2]. Spend this Energy only to play units
    or activated abilities of units.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Renekton Butcher of the Sands")
    a.energy = 0
    loop._apply_activated_ability(a, b, _ability(loop, "A", "gain_energy"))
    assert a.energy == 0 and a.earmarked_energy_unit == 2
    spell = SpellCard(name="Spell", cost_energy=2)
    assert not loop._can_pay_card(a, spell, 2, 0)
    brute = _unit("Renekton Brute")
    a.base_units.append(brute)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "grant_temporary_might"))
    assert a.earmarked_energy_unit == 1 and brute.might == 5
    unit = UnitCard(name="Unit", might=1, cost_energy=1)
    assert loop._pay_card(a, unit, 1, 0) and a.earmarked_energy_unit == 0


def test_death_mark_clone_banishes_for_assault_four_and_empowers_zed():
    """Death Mark: 'BURN 3. Play a 0 [might] Shadow Clone unit token.' The clone:
    'When I attack, you may banish a unit from your trash. If you do, give me
    ASSAULT 4 this turn.' Zed Master of Shadows: 'When you banish a card you
    own, empower me. ACTION Disempower me, [tap]: Discard 1, then draw 1.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    zed = _unit("Zed Master of Shadows")
    loop.gs.legend_unit_A = zed
    _deck(a, UnitCard(name="U1", might=1), SpellCard(name="S2"), SpellCard(name="S3"), SpellCard(name="Draw"))
    _cast_now(loop, a, "Death Mark")
    assert len(a.trash) == 3
    clone = next(u for u in a.base_units + loop.gs.battlefields[0].units_A if u.card.name == "Shadow Clone")
    assert clone.might == 0
    if clone in a.base_units:
        a.base_units.remove(clone)
        loop.gs.battlefields[0].add_unit("A", clone)
    clone.ready = True
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 1))
    _attack_at(loop)
    assert clone.keyword_value("ASSAULT") == 4 and [c.name for c in a.banished] == ["U1"]
    assert zed.empowered
    a.hand.append(SpellCard(name="Junk"))
    loop._apply_activated_ability(a, b, _usable(loop, "A", "sequence"))
    assert [c.name for c in a.hand] == ["Draw"] and not zed.empowered


def test_shen_eye_of_twilight_gives_a_friend_tank():
    """'ACTION [tap]: Give a friendly unit TANK this turn.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Shen Eye of Twilight")
    friend = _unit("Friend", 2)
    a.base_units.append(friend)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "give_keyword"))
    assert friend.has_keyword("TANK") and not loop.gs.legend_unit_A.ready


def test_shadow_dash_pulls_an_enemy_and_pumps_a_pair():
    """'Move an enemy unit to a battlefield where you have units. If you have
    exactly two units there, they each get +1 [might] this turn.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[1]
    f1, f2 = _unit("F1", 1), _unit("F2", 1)
    bf.add_unit("A", f1)
    bf.add_unit("A", f2)
    enemy = _unit("Enemy", 3)
    b.base_units.append(enemy)
    _cast_now(loop, a, "Shadow Dash")
    assert enemy in bf.units_B and (f1.might, f2.might, enemy.might) == (2, 2, 3)


def test_jayce_defender_readies_one_gear_or_two_empowered():
    """'[1], [tap]: Ready a gear. EMPOWERED: [1], [tap]: Ready 2 gear.'"""
    for empowered, readied in ((False, 1), (True, 2)):
        loop, a, b = _setup()
        jayce = _unit("Jayce Defender of Tomorrow", empowered=empowered)
        loop.gs.legend_unit_A = jayce
        gear = [GearCard(name=f"G{i}", cost_energy=2) for i in range(3)]
        for g in gear:
            g.tapped = True
        a.base_gear.extend(gear)
        loop._apply_activated_ability(a, b, _usable(loop, "A", "ready_gear"))
        assert sum(not g.tapped for g in gear) == readied and a.energy == 19, empowered


def test_acceleration_gate_readies_units_gear_and_runes():
    """'Ready up to 4 units, gear, and/or runes.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    unit.ready = False
    a.base_units.append(unit)
    gear = GearCard(name="Gear", cost_energy=2)
    gear.tapped = True
    a.base_gear.append(gear)
    _runes(a, 4)
    for r in a.rune_pool[Domain.FURY]:
        r.ready = False
    a.energy = 0
    loop.chooser = lambda _l, kind, side, options, default, source: (
        next(i for o in (gear, unit, None) for i, x in enumerate(options) if x is o or (o is None and isinstance(x, Rune)))
        if kind.startswith("target") else None)
    _cast_now(loop, a, "Acceleration Gate")
    assert unit.ready and not gear.tapped and a.energy == 2


def test_ambessa_matriarch_empowers_with_you_and_readies_a_unit():
    """'When you empower something else, empower me. Disempower me, [rune], [tap]:
    Ready a unit.'"""
    loop, a, b = _setup()
    ambessa = _unit("Ambessa Matriarch of War")
    loop.gs.legend_unit_A = ambessa
    hawk = _unit("Solari Sunhawk")
    hawk.ready = False
    a.base_units.append(hawk)
    loop._empower(hawk.card, "A")
    assert ambessa.empowered
    loop._apply_activated_ability(a, b, _usable(loop, "A", "ready_unit"))
    assert hawk.ready and not ambessa.empowered and not ambessa.ready


def test_kennen_heart_empowers_on_a_card_played_from_elsewhere():
    """'When you play a card from anywhere other than your hand, empower me.
    ACTION Disempower me, [tap]: Give a unit ASSAULT 2 this turn.'"""
    loop, a, b = _setup()
    kennen = _unit("Kennen Heart of the Tempest")
    loop.gs.legend_unit_A = kennen
    a.hand.append(UnitCard(name="From Hand", might=1, cost_energy=1))
    loop._apply_action(a, ("UNIT", 0, None))
    assert not kennen.empowered
    loop.gs.turn = 3
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Holder", 1))
    bf.facedown = FacedownCard(card=CARD_REGISTRY["Tornado Warrior"].instantiate(), owner="A", turn_hidden=1)
    loop._play_from_hidden("A", 0)
    assert kennen.empowered
    loop._apply_activated_ability(a, b, _usable(loop, "A", "give_temporary_assault"))
    assert not kennen.empowered
    assert any(u.keyword_value("ASSAULT") == 2 for u in a.base_units + bf.units_A)


def test_lightning_rush_draws_one_of_three_and_trashes_the_rest():
    """'Look at the top 3 cards of your Main Deck. You may choose a card from among
    them and draw it. Put the rest into your trash. FLOW [2] [rune]'"""
    loop, a, b = _setup()
    _deck(a, SpellCard(name="S1"), SpellCard(name="S2"), SpellCard(name="S3"), SpellCard(name="S4"))
    _cast_now(loop, a, "Lightning Rush")
    assert len(a.hand) == 1 and len(a.trash) == 2 and [c.name for c in a.deck.cards] == ["S4"]
    assert CARD_REGISTRY["Lightning Rush"].instantiate().flow_cost["energy"] == 2


def _rebuttal_over(loop, *items):
    """`items` (side, card name) on the chain, oldest first, then A's Rebuttal;
    the chain resolves."""
    cards = []
    for side, name in items:
        cards.append(CARD_REGISTRY[name].instantiate())
        loop._put_on_chain(ChainItem(player=side, card=cards[-1], bf_idx=0))
    loop._put_on_chain(ChainItem(player="A", card=CARD_REGISTRY["Rebuttal"].instantiate(), bf_idx=0))
    loop._resolve_chain()
    return cards


def test_rebuttal_pays_a_rune_to_take_over_a_spell_with_new_choices():
    """'Choose a spell with Energy cost no more than [4]. You may pay [rune]. If
    you do, gain control of it and you may make new choices for it.'"""
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 4), _unit("Theirs", 4)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.gs.battlefields[0].add_unit("B", theirs)
    _pick(loop, "Mine")                                # B aims Hextech Ray at our unit
    loop.gs.chain.clear()
    ray = CARD_REGISTRY["Hextech Ray"].instantiate()
    loop._put_on_chain(ChainItem(player="B", card=ray, bf_idx=0))
    loop.chooser = None
    power = sum(a.power_pool.values())
    loop._put_on_chain(ChainItem(player="A", card=CARD_REGISTRY["Rebuttal"].instantiate(), bf_idx=0))
    loop._resolve_chain()
    assert sum(a.power_pool.values()) == power - 1
    assert mine.damage == 0 and theirs.damage == 3     # ours now, aimed anew
    assert ray in b.trash and ray not in a.trash       # still B's card


def test_rebuttal_draws_for_us_and_trashes_to_the_owner():
    loop, a, b = _setup()
    _deck(a, SpellCard(name="S1"), SpellCard(name="S2"))
    (consult,) = _rebuttal_over(loop, ("B", "Consult the Past"))
    assert [c.name for c in a.hand] == ["S1", "S2"] and not b.hand
    assert consult in b.trash


def test_rebuttal_counters_it_without_a_rune():
    """'Otherwise, counter it.'"""
    loop, a, b = _setup()
    a.power_pool = {}
    _deck(b, SpellCard(name="S1"), SpellCard(name="S2"))
    (consult,) = _rebuttal_over(loop, ("B", "Consult the Past"))
    assert not b.hand and consult in b.trash


def test_rebuttal_ignores_spells_costing_over_four():
    loop, a, b = _setup()
    a.power_pool = {}
    big = SpellCard(name="Big", cost_energy=5)
    loop.gs.chain.append(ChainItem(player="B", card=big, bf_idx=0))
    REGISTRY["steal_or_counter_spell"](_ctx(loop, a, CARD_REGISTRY["Rebuttal"].instantiate()),
                                       {"max_energy": 4, "pay_power": 1})
    assert [it.card for it in loop.gs.chain] == [big] and loop.gs.chain[0].player == "B"


def test_rebuttal_counters_an_enemy_counter_rather_than_taking_it():
    """Baseline: taking over Defy would counter our own spell."""
    loop, a, b = _setup()
    _deck(a, SpellCard(name="S1"), SpellCard(name="S2"))
    consult, defy = _rebuttal_over(loop, ("A", "Consult the Past"), ("B", "Defy"))
    assert [c.name for c in a.hand] == ["S1", "S2"]    # our spell resolved
    assert defy in b.trash and consult in a.trash
