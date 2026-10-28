"""Corpus cards, sentence by sentence (BACKLOG.md section D): each fix is
played through the engine and checked against the printed text."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, DeployedGear
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
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
