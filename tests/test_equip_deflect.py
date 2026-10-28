"""Equip §744 (attached gear buffs its host via grant_might) and Deflect §408/§809
(choosing an enemy unit with DEFLECT N costs N [rune] more, paid as the choice
is made). Correctness checks for two MECHANICS.md PARTIAL rows.
"""

from __future__ import annotations

import random

import pytest

from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


# --- Equip §744: attached gear grants might ---

def test_attached_gear_grants_might():
    unit = UnitInPlay(UnitCard(name="Bearer", might=2))
    assert unit.might == 2
    unit.gear.append(GearCard(name="Big Sword",
                              effects=[{"effect": "grant_might", "amount": 3}]))
    assert unit.might == 5          # 2 + 3 from the equipped gear


# --- Deflect §809: "Opponents must pay [rune] to choose me with a spell or ability" ---

def _warded(loop, side="B", keywords=("DEFLECT 2",)):
    unit = UnitInPlay(UnitCard(name="Warded", might=2, keywords=list(keywords)))
    loop.gs.battlefields[0]._units_for(side).append(unit)
    return unit


def test_choosing_an_enemy_deflect_unit_costs_its_value_in_power():
    loop = _loop(); loop.gs.active = "A"
    assert loop._deflect_tax(_warded(loop), "A", None) == 2


def test_no_deflect_no_tax():
    loop = _loop(); loop.gs.active = "A"
    assert loop._deflect_tax(_warded(loop, keywords=()), "A", None) == 0


def test_your_own_deflect_unit_costs_you_nothing():
    loop = _loop(); loop.gs.active = "A"
    assert loop._deflect_tax(_warded(loop, side="A"), "A", None) == 0


def test_a_deflect_unit_you_cannot_pay_for_cannot_be_chosen():
    from riftbound.core.enums import Domain
    loop = _loop(); loop.gs.active = "A"
    warded = _warded(loop)
    assert not loop._can_choose(warded, "A")
    loop.gs.A.add_power(Domain.FURY, 2)
    assert loop._can_choose(warded, "A")
