"""Corpus cards, sentence by sentence (BACKLOG.md section D): each fix is
played through the engine and checked against the printed text."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, DeployedGear
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _setup():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    for p in (a, b):
        p.energy = 20
        for d in Domain:
            p.add_power(d, 5)
    return GameLoop(gs), a, b


def _unit(name, might=None, **kw):
    card = CARD_REGISTRY[name].instantiate() if name in CARD_REGISTRY else UnitCard(name=name, might=might)
    return UnitInPlay(card=card, ready=True, **kw)


def _battlefield(loop, i, name):
    loop.gs.battlefields[i].card = CARD_REGISTRY[name].instantiate()


def _fight(loop, attacker="A", bf=0):
    loop._phase_combat_and_conquer_single(bf, attacker)


def _pick(loop, name):
    """Every target choice picks the unit called `name`."""
    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target"):
            return next((i for i, o in enumerate(options)
                         if getattr(getattr(o, "card", None), "name", None) == name), None)
        return None
    loop.chooser = chooser


# -- "When you defend here" / "attack here": battlefields and deployed gear ------

def test_fortified_position_gives_a_chosen_unit_shield_two_this_combat():
    """'When you defend here, choose a unit. It gains SHIELD 2 this combat.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Fortified Position")
    bf = loop.gs.battlefields[0]
    atk, dfn = _unit("Atk", 4), _unit("Def", 3)
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    _pick(loop, "Def")
    _fight(loop)
    assert dfn in bf.units_B and atk not in bf.units_A      # 3 + 2 holds off 4
    assert dfn.keyword_value("SHIELD") == 0                 # only this combat


def test_durand_memorial_gives_a_unit_here_tank_this_combat():
    """'When you defend here, choose a unit you control here. Give it TANK this
    combat.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Durand Memorial")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 3))
    big, small = _unit("Big", 5), _unit("Small", 1)
    bf.add_unit("B", big)
    bf.add_unit("B", small)
    _pick(loop, "Big")
    _fight(loop)
    assert small in bf.units_B                              # Big soaked the damage first
    assert not big.has_keyword("TANK")


def test_ravenbloom_conservatory_puts_a_revealed_spell_in_hand():
    """'When you defend here, reveal the top card of your Main Deck. If it's a
    spell, put it in your hand. Otherwise, recycle it.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Ravenbloom Conservatory")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 1))
    bf.add_unit("B", _unit("Def", 5))
    b.deck.cards = [UnitCard(name="Bottom", might=1), SpellCard(name="Top Spell")]
    _fight(loop)
    assert [c.name for c in b.hand] == ["Top Spell"] and b.draws_this_turn == 0


def test_ravenbloom_conservatory_recycles_anything_else():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Ravenbloom Conservatory")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 1))
    bf.add_unit("B", _unit("Def", 5))
    b.deck.cards = [UnitCard(name="Bottom", might=1), UnitCard(name="Top", might=1)]
    _fight(loop)
    assert not b.hand and [c.name for c in b.deck.cards] == ["Top", "Bottom"]


def test_battlefield_defend_trigger_is_the_defenders_only():
    """The attacker doesn't 'defend here'."""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Ravenbloom Conservatory")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 1))
    bf.add_unit("B", _unit("Def", 5))
    a.deck.cards = [SpellCard(name="A Spell")]
    b.deck.cards = []
    _fight(loop)
    assert not a.hand


def test_demacian_standard_gives_an_attacker_here_two():
    """'When one or more friendly units attack here, give one of them +2 [might]
    this turn.' (a DEPLOY gear here)"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.gear_for("A").append(DeployedGear(card=CARD_REGISTRY["Demacian Standard"].instantiate()))
    atk, dfn = _unit("Atk", 2), _unit("Def", 4)
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    _fight(loop)
    assert dfn not in bf.units_B                           # 2 + 2 kills 4
    assert atk.might == 4                                  # this turn


def test_demacian_standard_doesnt_help_a_defender():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.gear_for("B").append(DeployedGear(card=CARD_REGISTRY["Demacian Standard"].instantiate()))
    atk, dfn = _unit("Atk", 4), _unit("Def", 2)
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    _fight(loop)
    assert dfn not in bf.units_B and dfn.might == 2


def test_demacian_standard_may_return_to_hand_when_you_hold():
    """'When you hold here, you may return this to its owner's hand.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    card = CARD_REGISTRY["Demacian Standard"].instantiate()
    bf.gear_for("A").append(DeployedGear(card=card))
    bf.add_unit("A", _unit("Holder", 2))
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert card in a.hand and not bf.gear_for("A")


def test_the_good_stuff_returns_to_hand_when_you_hold():
    """'When you hold here, return this to its owner's hand.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    card = CARD_REGISTRY["The Good Stuff"].instantiate()
    bf.gear_for("A").append(DeployedGear(card=card))
    bf.add_unit("A", _unit("Holder", 2))
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert card in a.hand and not bf.gear_for("A")


# -- Control during a contest (§190.4.b) ----------------------------------------

def test_a_contested_battlefield_stays_controlled_by_who_held_it():
    """While both sides have units (a showdown or combat), control doesn't
    change: the holder still controls it; it changes when the combat ends."""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("B", _unit("Holder", 1))
    assert bf.control() == "B"
    bf.add_unit("A", _unit("Attacker", 5))
    assert bf.control() == "B" and bf.controller() is None    # contest machinery unchanged
    assert loop._check_condition({"type": "you_control_this_battlefield"}, UnitCard(name="X"),
                                 b, a, {"battlefield": bf})
    _fight(loop)
    assert bf.control() == "A"
    bf.remove_unit("A", bf.units_A[0])
    assert bf.control() is None


# -- Legends that watch combats ---------------------------------------------------

def test_ahri_nine_tailed_fox_weakens_each_attacker_of_your_battlefield():
    """'When an enemy unit attacks a battlefield you control, give it -1 [might]
    this turn, to a minimum of 1 [might].'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_B = _unit("Ahri Nine-Tailed Fox")
    bf = loop.gs.battlefields[0]
    bf.add_unit("B", _unit("Def", 2))                      # B controls it
    big, tiny = _unit("Big", 3), _unit("Tiny", 1)
    bf.add_unit("A", big)
    bf.add_unit("A", tiny)
    loop._open_combat(bf, "A")
    assert big.might == 2 and tiny.might == 1


def test_ahri_nine_tailed_fox_ignores_an_uncontrolled_battlefield():
    loop, a, b = _setup()
    loop.gs.legend_unit_B = _unit("Ahri Nine-Tailed Fox")
    bf = loop.gs.battlefields[0]
    big = _unit("Big", 3)
    bf.add_unit("A", big)
    bf.add_unit("B", _unit("Def", 2))                      # both arrived: no controller
    loop._open_combat(bf, "A")
    assert big.might == 3


def test_master_yi_wuju_bladesman_gives_a_lone_defender_two():
    """'While a friendly unit defends alone, it gets +2 [might].'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_B = _unit("Master Yi Wuju Bladesman")
    bf = loop.gs.battlefields[0]
    atk, dfn = _unit("Atk", 4), _unit("Def", 3)
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    _fight(loop)
    assert dfn in bf.units_B and atk not in bf.units_A      # 3 + 2 = 5 against 4


def test_master_yi_wuju_bladesman_needs_the_defender_alone():
    loop, a, b = _setup()
    loop.gs.legend_unit_B = _unit("Master Yi Wuju Bladesman")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 9))
    d1, d2 = _unit("D1", 3), _unit("D2", 3)
    bf.add_unit("B", d1)
    bf.add_unit("B", d2)
    _fight(loop)
    assert d1 not in bf.units_B and d2 not in bf.units_B    # 9 damage, no bonus


# -- Units ----------------------------------------------------------------------

def test_loyal_pup_may_move_to_where_you_defend():
    """'When you defend at a battlefield, you may move me there.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    pup = _unit("Loyal Pup")
    b.base_units.append(pup)
    bf.add_unit("B", _unit("Def", 1))
    bf.add_unit("A", _unit("Atk", 3))
    loop._open_combat(bf, "A")
    assert pup in bf.units_B and pup not in b.base_units


def test_fiora_peerless_doubles_her_might_one_on_one_this_combat_only():
    """'When I attack or defend one on one, double my Might this combat.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    fiora = _unit("Fiora Peerless")                        # 3 Might
    dfn = _unit("Def", 5)
    bf.add_unit("A", fiora)
    bf.add_unit("B", dfn)
    _fight(loop)
    assert dfn not in bf.units_B and fiora in loop.gs.A.base_units + bf.units_A
    assert fiora.might == 3                                 # the combat is over


def test_fiora_victorious_is_mighty_with_her_current_might():
    """'While I'm MIGHTY, I have DEFLECT, GANKING and SHIELD.' (5+ Might now, a
    buff counts)"""
    loop, a, b = _setup()
    fiora = _unit("Fiora Victorious")                      # 4 printed
    a.base_units.append(fiora)
    loop._recompute_passives()
    assert not fiora.has_keyword("GANKING")
    fiora.might_counters = 1
    loop._recompute_passives()
    assert fiora.has_keyword("GANKING") and fiora.has_keyword("DEFLECT")


def test_volibear_relentless_storm_sees_a_unit_mighty_as_it_is_played():
    """'When you play a MIGHTY unit, you may exhaust me to channel 1 rune
    exhausted.' A 4 printed unit with +1 from an aura is Mighty."""
    spec = CardSpec.from_dict({
        "name": "Test Anthem", "category": "Gear",
        "effects": [{"effect": "grant_might", "trigger": "passive", "target": "friendly_unit",
                     "scope": "board", "amount": 1}],
    })
    CARD_REGISTRY[spec.name] = spec
    loop, a, b = _setup()
    legend = _unit("Volibear Relentless Storm")
    loop.gs.legend_unit_A = legend
    a.base_gear.append(spec.instantiate())
    unit = _unit("Four", 4)
    a.base_units.append(unit)
    loop._recompute_passives()
    assert unit.might == 5
    mighty = {"type": "triggering_unit_is_mighty"}
    assert loop._check_condition(mighty, legend.card, a, b, {"triggering_card": unit.card})
    a.base_gear.clear()
    loop._recompute_passives()
    assert not loop._check_condition(mighty, legend.card, a, b, {"triggering_card": unit.card})


# -- Battlefields that score ---------------------------------------------------

def test_seat_of_power_draws_one_per_other_battlefield_you_control():
    """'When you conquer here, draw 1 for each other battlefield you or allies
    control.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Seat of Power")
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    loop.gs.battlefields[0].add_unit("A", _unit("Conqueror", 2))
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert len(a.hand) == 0                                  # no other battlefield
    loop.gs.battlefields[1].add_unit("A", _unit("Holder", 2))
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert len(a.hand) == 1


def test_sunken_temple_pays_one_to_draw_with_a_mighty_unit_here():
    """'When you conquer here with one or more MIGHTY units, you may pay [1] to
    draw 1.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Sunken Temple")
    bf = loop.gs.battlefields[0]
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    unit = _unit("Four", 4)
    bf.add_unit("A", unit)
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert not a.hand and a.energy == 20
    unit.might_counters = 1                                  # buffed to 5: Mighty
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert len(a.hand) == 1 and a.energy == 19


# -- Battlefields, batch 2, and "when you play a spell" ------------------------------

def _spec(name, **raw):
    spec = CardSpec.from_dict({"name": name, **raw})
    CARD_REGISTRY[name] = spec
    return spec


def _spell(cost, name=None):
    name = name or f"Test Spell {cost}"
    _spec(name, category="Spell", cost_energy=cost,
          effects=[{"effect": "draw_cards", "trigger": "on_cast", "count": 0}])
    return name


def _play_spell(loop, p, name, lane=0):
    p.hand.append(CARD_REGISTRY[name].instantiate())
    loop._apply_action(p, ("SPELL", len(p.hand) - 1, lane))
    loop._recompute_passives()


def _always(answer):
    """A chooser answering every "you may" with `answer`."""
    return lambda _l, kind, side, options, default, source: (
        options.index(answer) if kind.startswith("optional:") else None)


class _Predictor:
    def __init__(self):
        self.seen = []

    def decide_predict_recycle(self, card):
        self.seen.append(card.name)
        return False


def test_rakelstake_predicts_on_the_first_unit_or_gear_played_here():
    """'For each player, the first time they play a unit or a gear here each turn,
    they PREDICT.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Rakelstake")
    bf = loop.gs.battlefields[0]
    a.agent = _Predictor()
    a.deck.cards = [UnitCard(name="Top", might=1)]
    loop._play_unit(UnitCard(name="First", might=1), "A", bf=bf)
    loop._play_unit(UnitCard(name="Second", might=1), "A", bf=bf)
    assert a.agent.seen == ["Top"]                        # once this turn


def test_hunters_circle_takes_one_off_the_first_unit_played_here_on_your_turn():
    """'For each player, the first unit or gear they play here on their turn costs
    [1] less.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hunters' Circle")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))   # A may play units here
    for i in range(2):
        a.hand.append(UnitCard(name=f"U{i}", might=1, cost_energy=3))
    loop._apply_action(a, ("UNIT", 0, 0, 0))
    assert a.energy == 18
    loop._apply_action(a, ("UNIT", 0, 0, 0))
    assert a.energy == 15                                 # the second pays in full


def test_ornns_forge_discounts_your_first_gear_each_turn_while_you_control_it():
    """'When you control this battlefield, the first friendly non-token gear
    played each turn costs [1] less.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Ornn's Forge")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    for i in range(2):
        a.hand.append(GearCard(name=f"G{i}", cost_energy=2))
    loop._apply_action(a, ("GEAR", 0, 0))
    assert a.energy == 19
    loop._apply_action(a, ("GEAR", 0, 0))
    assert a.energy == 17


def test_ornns_forge_needs_control():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Ornn's Forge")
    a.hand.append(GearCard(name="G", cost_energy=2))
    loop._apply_action(a, ("GEAR", 0, 0))
    assert a.energy == 18


def test_piltovan_forge_discounts_the_first_gear_ability_each_turn():
    """'While you control this battlefield, the first friendly gear activated
    ability played each turn costs [1] less.'"""
    loop, a, b = _setup()
    _spec("Test Gadget", category="Gear",
          effects=[{"effect": "draw_cards", "trigger": "activated", "count": 0, "cost": {"energy": 2}}])
    _battlefield(loop, 0, "Piltovan Forge")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    a.base_gear.append(CARD_REGISTRY["Test Gadget"].instantiate())
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "gear_ability")
    loop._apply_activated_ability(a, b, idx)
    assert a.energy == 19
    loop._apply_activated_ability(a, b, idx)
    assert a.energy == 17


def test_marai_spire_takes_one_off_repeat_costs():
    """'While you control this battlefield, friendly REPEAT costs cost [1] less.'"""
    loop, a, b = _setup()
    _spec("Test Repeater", category="Spell", cost_energy=2, keywords=["REPEAT"],
          effect="REPEAT (You may pay the additional cost to repeat this spell's effect.) Draw 1.",
          effects=[{"effect": "draw_cards", "trigger": "on_cast", "count": 1}])
    _battlefield(loop, 0, "Marai Spire")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    _play_spell(loop, a, "Test Repeater")
    assert a.energy == 17 and len(a.hand) == 2            # [2] + REPEAT [2] - [1]


def test_abandoned_hall_lets_a_spell_player_pump_a_unit_there():
    """'When a player plays a spell, they may give a unit they control here +1
    [might] this turn.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Abandoned Hall")
    mine, theirs = _unit("Mine", 2), _unit("Theirs", 2)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.gs.battlefields[1].add_unit("B", theirs)
    _play_spell(loop, a, _spell(1))
    assert mine.might == 3 and theirs.might == 2


def test_forgotten_library_predicts_on_a_spell_you_spent_four_on(monkeypatch):
    """'While you control this battlefield, when you play a spell, if you spent
    [4] or more, PREDICT.'"""
    from riftbound.core.effects import REGISTRY
    loop, a, b = _setup()
    _battlefield(loop, 0, "Forgotten Library")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    predicted = []
    monkeypatch.setitem(REGISTRY, "predict", lambda ctx, spec: predicted.append(ctx.actor.name))
    _play_spell(loop, a, _spell(3))
    assert predicted == []
    _play_spell(loop, a, _spell(4))
    assert predicted == ["A"]


def test_revna_readies_when_you_spend_four_on_a_spell():
    """'When you play a spell, if you spent [4] or more, ready me.'"""
    loop, a, b = _setup()
    revna = _unit("Revna the Lorekeeper")
    revna.ready = False
    a.base_units.append(revna)
    _play_spell(loop, a, _spell(3))
    assert not revna.ready
    _play_spell(loop, a, _spell(4))
    assert revna.ready


def test_ravenbloom_student_grows_as_the_spell_is_played():
    """'When you play a spell, give me +1 [might] this turn.' On the play, before
    the spell resolves."""
    loop, a, b = _setup()
    student = _unit("Ravenbloom Student")
    a.base_units.append(student)
    base = student.might
    card = CARD_REGISTRY[_spell(1)].instantiate()
    from riftbound.core.state import ChainItem
    loop._spell_played(card, a)
    assert student.might == base                           # its choices aren't made yet
    loop._put_on_chain(ChainItem(player="A", card=card, bf_idx=0))   # played, not resolved yet
    assert student.might == base + 1


def test_prepared_neophyte_has_four_more_after_a_four_spell_this_turn():
    """'If you've spent [4] or more to play a spell this turn, I have +4 [might].'"""
    loop, a, b = _setup()
    neo = _unit("Prepared Neophyte")
    a.base_units.append(neo)
    loop._recompute_passives()
    base = neo.might
    _play_spell(loop, a, _spell(4))
    assert neo.might == base + 4


def test_altar_of_blood_saves_a_unit_dying_in_combat_for_three_power():
    """'If a unit here would die during combat, its controller may pay
    [rune][rune][rune] to heal it, exhaust it, and recall it instead.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Altar of Blood")
    bf = loop.gs.battlefields[0]
    atk, dfn = _unit("Atk", 5), _unit("Def", 2)
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    power = sum(b.power_pool.values())
    _fight(loop)
    assert dfn in b.base_units and dfn.damage == 0 and not dfn.ready
    assert sum(b.power_pool.values()) == power - 3


def test_gardens_of_becoming_units_there_tap_for_xp():
    """'Units here have "[tap]: Gain 1 XP."'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Gardens of Becoming")
    unit = _unit("Student", 1)
    loop.gs.battlefields[0].add_unit("A", unit)
    a.base_units.append(_unit("Elsewhere", 1))
    entries = [i for i, e in enumerate(loop.activatable_abilities("A"))
               if e["type"] == "ability" and e["eff"].effect == "gain_xp"]
    assert len(entries) == 1                              # only the unit there
    loop._apply_activated_ability(a, b, entries[0])
    assert loop.gs.get_xp("A") == 1 and not unit.ready


def test_black_market_draws_for_two_power_once_per_turn_for_anyone():
    """'[rune] [rune]: Draw 1. Each player may use this ability once on their turn
    (even if they don't control this battlefield.)'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Black Market")
    loop.gs.battlefields[0].add_unit("B", _unit("Owner", 1))   # B controls it
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "bf_ability")
    assert loop._ability_usable(a, loop.activatable_abilities("A")[idx])
    loop._apply_activated_ability(a, b, idx)
    assert len(a.hand) == 1
    assert not loop._ability_usable(a, loop.activatable_abilities("A")[idx])


def test_black_rose_sanctum_makes_a_recruit_on_the_first_death_each_turn():
    """'For each player, the first time each turn a non-token unit they control
    dies here, they play a 1 [might] Recruit unit token to their base.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Black Rose Sanctum")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 9))
    bf.add_unit("B", _unit("D1", 1))
    bf.add_unit("B", _unit("D2", 1))
    _fight(loop)
    assert [u.card.name for u in b.base_units] == ["Recruit"]


def test_sigil_of_the_storm_recycles_a_rune_not_a_card():
    """'When you conquer here, you must recycle one of your runes.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Sigil of the Storm")
    a.rune_pool = {Domain.FURY: [Rune(Domain.FURY), Rune(Domain.FURY)]}
    a.hand = [UnitCard(name="Keep", might=1)]
    loop.gs.battlefields[0].add_unit("A", _unit("Conqueror", 1))
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert len(a.rune_pool[Domain.FURY]) == 1 and len(a.rune_deck.runes) == 1
    assert [c.name for c in a.hand] == ["Keep"]


def test_the_papertree_makes_each_player_channel():
    """'When you hold here, each player channels 1 rune exhausted.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "The Papertree")
    a.rune_deck, b.rune_deck = RuneDeck([Rune(Domain.FURY)]), RuneDeck([Rune(Domain.CALM)])
    before = a.total_runes_in_play(), b.total_runes_in_play()
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    assert (a.total_runes_in_play(), b.total_runes_in_play()) == (before[0] + 1, before[1] + 1)


def test_veiled_temple_readies_a_chosen_gear_and_may_detach_it():
    """'When you conquer here, you may ready a friendly gear. If it's an
    equipment, you may detach it.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Veiled Temple")
    holder = _unit("Holder", 1)
    blade = GearCard(name="Blade")
    blade.tapped = True
    holder.gear.append(blade)
    loop.gs.battlefields[0].add_unit("A", holder)
    loop.chooser = _always(True)
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert not blade.tapped and blade in a.base_gear and not holder.gear


def test_dusk_rose_lab_may_kill_any_unit_you_control_there_to_draw():
    """'At the start of your Beginning Phase, you may kill a unit you control here
    to draw 1.' Baseline: only with a token there."""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Dusk Rose Lab")
    bf = loop.gs.battlefields[0]
    unit = _unit("Unit", 3)
    bf.add_unit("A", unit)
    a.deck.cards = [UnitCard(name="D", might=1)]
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert unit in bf.units_A and not a.hand               # baseline declines
    loop.chooser = _always(True)
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert unit not in bf.units_A and len(a.hand) == 1


def test_hallowed_tomb_returns_your_champion_from_the_trash():
    """'When you hold here, you may return your Chosen Champion from your trash to
    your Champion Zone if it is empty.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hallowed Tomb")
    champ = UnitCard(name="Champ", might=3)
    loop.gs.champion_A, loop.gs.champion_A_deployed = champ, True
    a.trash.append(champ)
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    assert champ not in a.trash and not loop.gs.champion_A_deployed


def test_the_academy_gives_your_next_spell_repeat():
    """'When you hold here, give your next spell this turn REPEAT equal to its base
    cost.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "The Academy")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    _spec("Test Drawer", category="Spell", cost_energy=2,
          effects=[{"effect": "draw_cards", "trigger": "on_cast", "count": 1}])
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    _play_spell(loop, a, "Test Drawer")
    assert a.energy == 16 and len(a.hand) == 2


def test_vaults_of_helia_makes_your_units_cost_one_more_this_turn():
    """'When you hold here, your non-token units cost [1] more to play this turn.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Vaults of Helia")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    a.hand.append(UnitCard(name="U", might=1, cost_energy=2))
    loop._apply_action(a, ("UNIT", 0, 0))
    assert a.energy == 17
    loop.gs.turn += 1
    a.hand.append(UnitCard(name="U2", might=1, cost_energy=2))
    loop._apply_action(a, ("UNIT", 0, 0))
    assert a.energy == 15


def test_ruined_monastery_may_discard_and_channel():
    """'When you conquer here, you may discard 1 and channel 1 rune exhausted.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Ruined Monastery")
    a.hand = [UnitCard(name="Spare", might=1)]
    a.rune_deck = RuneDeck([Rune(Domain.FURY)])
    loop.gs.battlefields[0].add_unit("A", _unit("Conqueror", 1))
    loop.chooser = _always(False)
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert len(a.hand) == 1                                # declined
    loop.chooser = None
    runes = a.total_runes_in_play()
    loop._fire_scoring_trigger("on_conquer", loop.gs.battlefields[0], "A")
    assert not a.hand and a.total_runes_in_play() == runes + 1


def test_a_unit_returned_to_hand_leaves_its_equipment_in_base():
    """§436.4.b: an attached card detaches where its unit was."""
    from riftbound.core.effects import _unit_leaves_to
    from riftbound.core.loop import EffectContext
    loop, a, b = _setup()
    unit = _unit("Bounced", 2)
    blade = GearCard(name="Blade")
    unit.gear.append(blade)
    loop.gs.battlefields[0].add_unit("B", unit)
    ctx = EffectContext(loop, SpellCard(name="Bounce"), a, b, loop.gs.battlefields[0], {})
    _unit_leaves_to(ctx, unit, "B", "hand")
    assert unit.card in b.hand and blade in b.base_gear and blade not in b.hand


# -- The other battlefields, each sentence played once --------------------------

def _hold(loop, name, side="A", unit=None):
    _battlefield(loop, 0, name)
    bf = loop.gs.battlefields[0]
    bf.add_unit(side, unit or _unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", bf, side)
    return bf


def _conquer(loop, name, side="A", unit=None):
    _battlefield(loop, 0, name)
    bf = loop.gs.battlefields[0]
    bf.add_unit(side, unit or _unit("Conqueror", 1))
    loop._fire_scoring_trigger("on_conquer", bf, side)
    return bf


def test_altar_to_unity_makes_a_recruit_in_base_when_you_hold():
    """'When you hold here, play a 1 [might] Recruit unit token in your base.'"""
    loop, a, b = _setup()
    _hold(loop, "Altar to Unity")
    assert [(u.card.name, u.might) for u in a.base_units] == [("Recruit", 1)]


def test_back_alley_bar_gives_a_unit_leaving_it_one():
    """'When a unit moves from here, give it +1 [might] this turn.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Back-Alley Bar")
    unit = _unit("Leaver", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    loop._apply_action(a, ("MOVE", 0, 0, 2))               # bf0 -> base
    assert unit in a.base_units and unit.might == 3


def test_monastery_of_hirana_spends_a_buff_to_draw():
    """'When you conquer here, you may spend a buff to draw 1.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="D", might=1)]
    buffed = _unit("Buffed", 2)
    buffed.might_counters = 1
    _conquer(loop, "Monastery of Hirana", unit=buffed)
    assert len(a.hand) == 1 and buffed.might_counters == 0


def test_navori_fighting_pit_buffs_a_unit_there_when_you_hold():
    """'When you hold here, buff a unit here.'"""
    loop, a, b = _setup()
    unit = _unit("Fighter", 2)
    _hold(loop, "Navori Fighting Pit", unit=unit)
    assert unit.might_counters == 1


def test_reckoners_arena_runs_the_conquer_effects_of_units_there_when_you_hold():
    """'When you hold here, activate the conquer effects of units here.'"""
    _spec("Test Conqueror", category="Unit", might=1,
          effects=[{"effect": "draw_cards", "trigger": "on_conquer", "count": 1}])
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="D", might=1)]
    _hold(loop, "Reckoner's Arena", unit=_unit("Test Conqueror"))
    assert len(a.hand) == 1


def test_startipped_peak_may_channel_when_you_hold():
    """'When you hold here, you may channel 1 rune exhausted.'"""
    loop, a, b = _setup()
    a.rune_deck = RuneDeck([Rune(Domain.FURY)])
    runes = a.total_runes_in_play()
    _hold(loop, "Startipped Peak")
    assert a.total_runes_in_play() == runes + 1
    assert not a.rune_pool[Domain.FURY][-1].ready


def test_the_arenas_greatest_gives_a_point_at_each_players_first_beginning_phase():
    """'At the start of each player's first Beginning Phase, that player gains 1
    point.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "The Arena's Greatest")
    loop.gs.turn = 1
    loop._fire_turn_trigger("on_start_of_turn", "A")
    loop.gs.turn = 2
    loop._fire_turn_trigger("on_start_of_turn", "B")
    loop.gs.turn = 3
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert (loop.gs.points_A, loop.gs.points_B) == (1, 1)


def test_the_candlelit_sanctum_recycles_what_you_pick_and_keeps_the_rest():
    """'When you conquer here, look at the top two cards of your Main Deck. You may
    recycle one or both of them. Put those you don't back in any order.' No card
    goes to the hand."""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name=n, might=1) for n in ("Bottom", "Second", "Top")]
    loop.chooser = lambda _l, kind, side, options, default, source: (
        options.index(True) if kind == "optional:recycle" and source.name == "Top" else None)
    _conquer(loop, "The Candlelit Sanctum")
    assert not a.hand and [c.name for c in a.deck.cards] == ["Top", "Bottom", "Second"]


def test_treasure_hoard_pays_one_for_an_exhausted_gold():
    """'When you conquer here, you may pay [1] to play a Gold gear token
    exhausted.'"""
    loop, a, b = _setup()
    _conquer(loop, "Treasure Hoard")
    gold = [g for g in a.base_gear if g.name == "Gold"]
    assert len(gold) == 1 and gold[0].tapped and a.energy == 19


def test_black_flame_altar_gives_temporary_units_there_shield():
    """'Units here with TEMPORARY have SHIELD.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Black Flame Altar")
    temp = UnitInPlay(card=UnitCard(name="Temp", might=1, keywords=["TEMPORARY"]))
    plain = _unit("Plain", 1)
    loop.gs.battlefields[0].add_unit("A", temp)
    loop.gs.battlefields[0].add_unit("A", plain)
    loop._recompute_passives()
    assert temp.has_keyword("SHIELD") and not plain.has_keyword("SHIELD")


def test_trapping_grounds_makes_a_bird_after_three_excess_damage():
    """'When you conquer here, if you assigned 3 or more excess damage, play a 1
    power Bird unit token with DEFLECT.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Trapping Grounds")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Big", 5))
    bf.add_unit("B", _unit("Small", 2))
    _fight(loop)                                            # 5 into 2: 3 excess
    birds = [u for u in a.base_units + bf.units_A if u.card.name == "Bird"]
    assert len(birds) == 1 and birds[0].has_keyword("DEFLECT") and birds[0].might == 1


def test_protective_sands_pays_one_to_draw_with_four_or_fewer_runes():
    """'When you conquer here, if you control 4 or fewer runes, you may pay [1] to
    draw 1.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="D", might=1)]
    _conquer(loop, "Protective Sands")
    assert len(a.hand) == 1 and a.energy == 19


def test_bandle_scouts_academy_makes_a_gold_when_you_hide_there():
    """'When you hide a card here, play a Gold gear token exhausted.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Bandle Scouts' Academy")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    a.hand = [CARD_REGISTRY["Pakaa Cub"].instantiate()]
    assert loop._hide_card("A", 0, 0)
    gold = [g for g in a.base_gear if g.name == "Gold"]
    assert len(gold) == 1 and gold[0].tapped


def test_cosmic_vista_scores_when_you_hold_with_an_empty_rune_deck():
    """'When you hold here, if your Rune Deck is empty, you score 1 point.'"""
    loop, a, b = _setup()
    _hold(loop, "Cosmic Vista")
    assert loop.gs.points_A == 1
    loop, a, b = _setup()
    a.rune_deck = RuneDeck([Rune(Domain.FURY)])
    _hold(loop, "Cosmic Vista")
    assert loop.gs.points_A == 0


def test_packed_amphitheater_gives_champions_there_one():
    """'Champion units here have +1 [might].'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Packed Amphitheater")
    champ, plain = _unit("Fiora Peerless"), _unit("Plain", 1)
    loop.gs.battlefields[0].add_unit("A", champ)
    loop.gs.battlefields[0].add_unit("A", plain)
    loop._recompute_passives()
    assert champ.might == champ.card.might + 1 and plain.might == 1


def test_emperors_dais_trades_a_unit_there_for_a_sand_soldier():
    """'When you conquer here, you may pay [1] and return a unit you control here
    to its owner's hand. If you do, play a 2 [might] Sand Soldier unit token
    here.'"""
    loop, a, b = _setup()
    unit = _unit("Returner", 1)
    bf = _conquer(loop, "Emperor's Dais", unit=unit)
    assert unit.card in a.hand and a.energy == 19
    assert [(u.card.name, u.might) for u in bf.units_A] == [("Sand Soldier", 2)]


def test_amateur_recital_may_move_a_unit_at_a_battlefield_to_its_base():
    """'When you hold here, you may move a unit at a battlefield to its base.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[1].add_unit("B", enemy)
    loop.chooser = _always(False)
    _hold(loop, "Amateur Recital")
    assert enemy in loop.gs.battlefields[1].units_B
    loop.chooser = None
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    assert enemy in b.base_units


# -- "Look at the top cards" -----------------------------------------------------

def _deck(p, *cards):
    """`cards` listed top first."""
    p.deck.cards = list(reversed(cards))


def _cast_now(loop, p, name):
    o = loop.gs.get_player(loop.gs.other(p.name))
    loop._resolve_card_effects(CARD_REGISTRY[name].instantiate(), loop.gs.battlefields[0], p, o)


def test_reinforce_plays_a_unit_from_the_top_five_five_cheaper():
    """'Look at the top 5 cards of your Main Deck. You may play a unit from among
    them. Its Energy cost is reduced by [5]. Then recycle the remaining cards.'"""
    loop, a, b = _setup()
    big = UnitCard(name="Big", might=6, cost_energy=7)
    _deck(a, SpellCard(name="S1"), big, SpellCard(name="S2"))
    _cast_now(loop, a, "Reinforce")
    assert any(u.card is big for u in a.base_units) and a.energy == 18
    assert not a.hand and len(a.deck.cards) == 2


def test_rek_sai_swarm_queen_banishes_one_and_plays_it_here():
    """'When I attack, you may reveal the top 2 cards of your Main Deck. You may
    banish one, then play it. If it is a unit, you may play it here. Recycle the
    rest.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    queen = _unit("Rek'Sai Swarm Queen")
    bf.add_unit("A", queen)
    bf.add_unit("B", _unit("Def", 9))
    drone = UnitCard(name="Drone", might=2, cost_energy=2)
    _deck(a, drone, SpellCard(name="Other"))
    loop._open_combat(bf, "A")
    assert any(u.card is drone for u in bf.units_A) and a.energy == 18
    assert [c.name for c in a.deck.cards] == ["Other"]


def test_lightning_rush_keeps_one_and_trashes_the_rest():
    """'Look at the top 3 cards of your Main Deck. You may choose a card from among
    them and draw it. Put the rest into your trash.'"""
    loop, a, b = _setup()
    _deck(a, UnitCard(name="A1", might=3), UnitCard(name="A2", might=1), UnitCard(name="A3", might=1))
    _cast_now(loop, a, "Lightning Rush")
    assert [c.name for c in a.hand] == ["A1"] and sorted(c.name for c in a.trash) == ["A2", "A3"]
    assert not a.deck.cards


def test_decree_of_strength_recycles_a_mind_card_from_the_opponents_hand():
    """'Choose an opponent. They reveal their hand and you choose a Mind card from
    it. They recycle that card.'"""
    loop, a, b = _setup()
    mind = UnitCard(name="Thinker", might=1, domain=Domain.MIND)
    fury = UnitCard(name="Brute", might=1, domain=Domain.FURY)
    b.hand = [fury, mind]
    _cast_now(loop, a, "Decree of Strength")
    assert b.hand == [fury] and b.deck.cards[0] is mind


def test_trifarian_captain_finds_a_cheap_unit_or_gear_only():
    """'... You may reveal from among them a unit or gear with Energy cost no more
    than [3] and with Power cost no more than [rune] and draw it.'"""
    loop, a, b = _setup()
    spell = SpellCard(name="Cheap Spell", cost_energy=1)
    pricey = UnitCard(name="Pricey", might=9, cost_energy=2, cost_power=2)
    gear = GearCard(name="Kit", cost_energy=3)
    _deck(a, spell, pricey, gear, UnitCard(name="Big", might=9, cost_energy=6))
    _cast_now(loop, a, "Trifarian Captain")                 # its "when you play me"
    assert [c.name for c in a.hand] == ["Kit"]


def test_ivern_nurturer_buffs_when_he_finds_a_pet_and_also_when_he_holds():
    """'When you play me or when I hold, look at the top 3 cards ... You may reveal
    a unit from among them and draw it. Recycle the rest. Then if you revealed a
    Bird, Cat, Dog, or Poro, do this: BUFF a friendly unit.'"""
    loop, a, b = _setup()
    ivern = _unit("Ivern Nurturer")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", ivern)
    _deck(a, UnitCard(name="Kitty", might=1, tags=["Cat"]))
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert [c.name for c in a.hand] == ["Kitty"] and ivern.might_counters == 1


def test_a_may_reveal_can_be_declined():
    """'You may reveal a spell ... and draw it' (Fate Weaver): no card is taken."""
    loop, a, b = _setup()
    _deck(a, SpellCard(name="Big Spell", cost_energy=5))
    loop.chooser = _always(False)
    loop._resolve_card_effects(CARD_REGISTRY["Fate Weaver"].instantiate(), loop.gs.battlefields[0], a, b)
    assert not a.hand and len(a.deck.cards) == 1


# -- The cards named in the old notes ----------------------------------------------

def test_mobilize_draws_when_no_rune_could_be_channelled():
    """'Channel 1 rune exhausted, if you couldn't, draw 1.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="D", might=1)]
    _cast_now(loop, a, "Mobilize")
    assert len(a.hand) == 1
    loop, a, b = _setup()
    a.rune_deck = RuneDeck([Rune(Domain.FURY)])
    a.deck.cards = [UnitCard(name="D", might=1)]
    _cast_now(loop, a, "Mobilize")
    assert not a.hand


def test_catalyst_of_aeons_draws_when_short_of_two_runes():
    """'Channel 2 rune exhausted. If you couldn't channel 2 runes this way, draw 1.'"""
    loop, a, b = _setup()
    a.rune_deck = RuneDeck([Rune(Domain.FURY)])
    a.deck.cards = [UnitCard(name="D", might=1)]
    runes = a.total_runes_in_play()
    _cast_now(loop, a, "Catalyst of Aeons")
    assert a.total_runes_in_play() == runes + 1 and len(a.hand) == 1


def test_temporal_breach_can_reset_an_enemy_unit_for_its_owner():
    """'Banish a unit, then its owner plays it to the same location, ignoring its
    cost.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    enemy = _unit("Enemy", 3)
    enemy.damage = 2
    bf.add_unit("B", enemy)
    _pick(loop, "Enemy")
    _cast_now(loop, a, "Temporal Breach")
    again = [u for u in bf.units_B if u.card is enemy.card]
    assert len(again) == 1 and again[0].damage == 0 and again[0] is not enemy


def test_legion_marauder_empowers_for_one_energy_or_one_body():
    """'EMPOWER - [1] or [body] (Pay either cost: Empower me.)'"""
    loop, a, b = _setup()
    marauder = _unit("Legion Marauder")
    a.base_units.append(marauder)
    costs = [e["eff"].cost for e in loop.activatable_abilities("A") if e["eff"].effect == "empower_self"]
    assert costs == [{"energy": 1}, {"power": 1, "domain": "BODY"}]


def test_renekton_brute_empowers_at_ten_might_and_then_has_deflect_and_ganking():
    """'When my Might becomes 10 or more, empower me. EMPOWERED I have DEFLECT and
    GANKING.'"""
    loop, a, b = _setup()
    ren = _unit("Renekton Brute")
    a.base_units.append(ren)
    loop._recompute_passives()
    assert not ren.empowered
    ren.temporary_might = 10 - ren.card.might
    loop._recompute_passives()
    assert ren.empowered and ren.has_keyword("DEFLECT") and ren.has_keyword("GANKING")


def test_kharox_burns_three_then_plays_a_unit_from_their_trash_they_still_own():
    """'When I become EMPOWERED, choose an opponent. They BURN 3. Then you may do
    this: Choose a unit in their trash and play it, ignoring its cost.'"""
    loop, a, b = _setup()
    kharox = _unit("Kharox")
    a.base_units.append(kharox)
    b.deck.cards = [SpellCard(name="S1"), UnitCard(name="Theirs", might=4), SpellCard(name="S3")]
    loop._empower(kharox.card, "A")
    stolen = [u for u in a.base_units if u.card.name == "Theirs"]
    assert len(stolen) == 1 and len(b.trash) == 2
    loop._route_deaths([(stolen[0], "A")], loop.gs.battlefields[0], in_base=True)
    assert stolen[0].card in b.trash and stolen[0].card not in a.trash   # its owner's


def test_detonation_amplifier_doubles_friendly_deathknells_here():
    """'Friendly DEATHKNELL effects here trigger an additional time.'"""
    _spec("Test Knell", category="Unit", might=1,
          effects=[{"effect": "draw_cards", "trigger": "on_death", "count": 1}])
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.gear_for("A").append(DeployedGear(card=CARD_REGISTRY["Detonation Amplifier"].instantiate()))
    knell = _unit("Test Knell")
    bf.add_unit("A", knell)
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    bf.remove_unit("A", knell)
    loop._route_deaths([(knell, "A")], bf)
    assert len(a.hand) == 2


def test_heartening_soul_gives_your_legend_a_pump():
    """'Friendly legends have "[tap]: Give a unit +3 [might] this turn."'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Volibear Relentless Storm")
    a.base_units.append(_unit("Heartening Soul"))
    target = _unit("Target", 2)
    loop.gs.battlefields[0].add_unit("A", target)
    _pick(loop, "Target")
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A"))
               if e["type"] == "ability" and e["unit"] is loop.gs.legend_unit_A
               and e["eff"].effect == "grant_temporary_might")
    loop._apply_activated_ability(a, b, idx)
    assert target.might == 5 and not loop.gs.legend_unit_A.ready


def test_jarvan_martial_paragon_lets_deploy_gear_be_played_in_showdowns():
    """'Your gear with DEPLOY have ACTION.'"""
    loop, a, b = _setup()
    bomb = CARD_REGISTRY["Detonation Amplifier"].instantiate()
    assert loop._play_timing(bomb, "A") is None
    a.base_units.append(_unit("Jarvan IV Martial Paragon"))
    assert loop._play_timing(bomb, "A") == "action"
    assert loop._play_timing(bomb, "B") is None


def test_sumpworks_map_is_offered_at_reaction_speed():
    """'REACTION (Play any time, even before spells and abilities resolve.)'"""
    from riftbound.core.legality import _reaction_actions
    loop, a, b = _setup()
    a.hand = [CARD_REGISTRY["Sumpworks Map"].instantiate()]
    assert any(ga.kind == "GEAR" for ga in _reaction_actions(loop, a))


def test_sivir_battle_mistress_makes_gold_when_you_recycle_a_rune():
    """'When you recycle a rune, you may exhaust me to play a Gold gear token
    exhausted.' Paying Power recycles runes."""
    loop, a, b = _setup()
    sivir = _unit("Sivir Battle Mistress")
    loop.gs.legend_unit_A = sivir
    a.power_pool, a.floating_power = {}, {}
    a.rune_pool = {Domain.FURY: [Rune(Domain.FURY)]}
    a.power_pool[Domain.FURY] = 1
    assert a.pay_cost(0, 1, Domain.FURY)
    loop._recompute_passives()
    assert [g.name for g in a.base_gear] == ["Gold"] and not sivir.ready


def test_call_to_battle_makes_the_opponent_follow_to_the_same_battlefield():
    """'Move a unit you control to a battlefield you control. Then, choose an
    opponent. They move a unit they control to the same battlefield.'"""
    loop, a, b = _setup()
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", _unit("Holder", 1))
    mine, theirs = _unit("Mine", 2), _unit("Theirs", 2)
    a.base_units.append(mine)
    b.base_units.append(theirs)
    _cast_now(loop, a, "Call to Battle")
    assert mine in bf0.units_A and theirs in bf0.units_B


def test_atakhan_makes_the_defender_kill_one_of_their_units_there():
    """'When I attack, the defender must kill one of their units here.' The
    defender chooses."""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atakhan"))
    big, small = _unit("Big", 5), _unit("Small", 1)
    bf.add_unit("B", big)
    bf.add_unit("B", small)
    asked = []
    loop.chooser = lambda _l, kind, side, options, default, source: (
        asked.append(side) or options.index(big) if kind.startswith("kill_own") else None)
    loop._open_combat(bf, "A")
    assert asked == ["B"] and big not in bf.units_B and small in bf.units_B


def test_akshan_steals_an_equipment_until_he_leaves():
    """'You may pay [body] [body] as an additional cost to play me. When you play
    me, if you paid the additional cost, move an enemy gear to your base. You
    control it until I leave the board. If it's an Equipment, attach it to me.'"""
    loop, a, b = _setup()
    blade = CARD_REGISTRY["Serrated Dirk"].instantiate()
    b.base_gear.append(blade)
    a.hand = [CARD_REGISTRY["Akshan Mischievous"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    akshan = next(u for u in a.base_units if u.card.name == "Akshan Mischievous")
    assert blade in akshan.gear and blade not in b.base_gear
    a.base_units.remove(akshan)
    loop._route_deaths([(akshan, "A")], loop.gs.battlefields[0], in_base=True)
    assert blade in b.base_gear and blade not in a.base_gear


def test_mel_empowered_spells_cant_be_countered_and_reduce_one_more():
    """'EMPOWERED Your spells and abilities can't be countered. If a spell or
    ability you control would give -[might] to a unit it chooses, it gives an
    additional -1 [might].'"""
    from riftbound.core.state import ChainItem
    loop, a, b = _setup()
    mel = _unit("Mel Newly Awakened", empowered=True)
    a.base_units.append(mel)
    mine = SpellCard(name="Mine")
    loop.gs.chain.append(ChainItem(player="A", card=mine, bf_idx=0))
    _cast_now(loop, b, "Wind Wall")
    assert loop.gs.chain and loop.gs.chain[-1].card is mine
    loop.gs.chain.clear()
    enemy = _unit("Enemy", 6)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _pick(loop, "Enemy")
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    ctx = EffectContext(loop, SpellCard(name="Shrink"), a, b, loop.gs.battlefields[0], {})
    REGISTRY["grant_temporary_might"](ctx, {"target": "chosen_unit", "amount": -2})
    assert enemy.might == 3


def test_akali_deadly_weapon_hits_where_she_moved_for_two_when_empowered():
    """'When I move, you may deal 1 to a unit at a battlefield I moved to or from.
    If I'm Empowered, deal 2 instead.'"""
    loop, a, b = _setup()
    akali = _unit("Akali Deadly Weapon")
    a.base_units.append(akali)
    far, near = _unit("Far", 5), _unit("Near", 5)
    loop.gs.battlefields[1].add_unit("B", far)
    loop.gs.battlefields[0].add_unit("B", near)
    _pick(loop, "Near")
    loop._move_unit_by_effect(akali, loop.gs.battlefields[0])
    assert near.damage == 1 and far.damage == 0
    akali.empowered = True
    loop._move_unit_by_effect(akali, None)
    assert near.damage == 3


def test_diana_lunari_predicts_then_reveals_for_one():
    """'When a showdown begins here, you may pay [1]. If you do, PREDICT, then
    reveal the top card of your Main Deck. If it's a spell, draw it.'"""
    loop, a, b = _setup()
    diana = _unit("Diana Lunari")
    a.base_units.append(diana)
    _deck(a, SpellCard(name="Top Spell"))
    loop._resolve_triggered_effects(diana.card, "on_showdown_begin", loop.gs.battlefields[0], a, b)
    assert [c.name for c in a.hand] == ["Top Spell"] and a.energy == 19


def test_curtain_call_repeats_three_times_each_a_new_mode():
    """'REPEAT - [1] / [rune] / [1][rune] ... Choose one you haven't already chosen
    - Draw 1. - Deal 2 to a unit at a battlefield. - Deal 3 to a unit at a base. -
    Give a unit at a battlefield -4 [might] this turn.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    at_bf, in_base = _unit("AtBf", 9), _unit("InBase", 9)
    loop.gs.battlefields[0].add_unit("B", at_bf)
    b.base_units.append(in_base)
    power = sum(a.power_pool.values())
    _play_spell(loop, a, "Curtain Call")
    assert a.energy == 20 - 4 - 1 - 1 and sum(a.power_pool.values()) == power - 2
    assert len(a.hand) == 1 and at_bf.damage == 2 and in_base.damage == 3
    assert at_bf.might == 5


def test_jinx_rebel_triggers_once_for_cards_discarded_together():
    """'When you discard one or more cards, ready me and give me +1 [might] this
    turn.'"""
    loop, a, b = _setup()
    jinx = _unit("Jinx Rebel")
    jinx.ready = False
    a.base_units.append(jinx)
    a.hand = [UnitCard(name="X", might=1), UnitCard(name="Y", might=1)]
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    REGISTRY["discard_card"](EffectContext(loop, SpellCard(name="Loot"), a, b, loop.gs.battlefields[0], {}),
                             {"count": 2})
    assert not a.hand and jinx.ready and jinx.might == jinx.card.might + 1


def test_mageseeker_warden_stops_enemy_gear_being_readied():
    """'While I'm at a battlefield, spells and abilities can't ready enemy units
    and gears.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Mageseeker Warden"))
    gear = GearCard(name="Kit")
    gear.tapped = True
    a.base_gear.append(gear)
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    REGISTRY["ready_gear"](EffectContext(loop, SpellCard(name="Ready"), a, b, loop.gs.battlefields[0], {}), {})
    assert gear.tapped


def test_showstopper_buffs_a_unit_in_base_then_moves_it_to_a_battlefield():
    """'Buff a friendly unit in your base, then move it to a battlefield.'"""
    loop, a, b = _setup()
    unit = _unit("Star", 2)
    a.base_units.append(unit)
    _cast_now(loop, a, "Showstopper")
    assert unit.might_counters == 1 and unit not in a.base_units
