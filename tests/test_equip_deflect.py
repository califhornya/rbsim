"""Equip §744 (attached gear buffs its host via grant_might) and Deflect §408/§809
(a spell targeting an opponent's battlefield costs extra energy = the max DEFLECT
value among enemy units there). Correctness checks for two MECHANICS.md PARTIAL rows.
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


# --- Deflect §809: opponent's DEFLECT units surcharge a targeted spell ---

BOLT = "TST Bolt"


@pytest.fixture
def bolt():
    CARD_REGISTRY[BOLT] = CardSpec.from_dict({
        "name": BOLT, "category": "SPELL",
        "effects": [{"effect": "deal_damage", "trigger": "on_cast",
                     "target": "enemy_unit", "amount": 2}],
    })
    yield CARD_REGISTRY[BOLT].instantiate()
    CARD_REGISTRY.pop(BOLT, None)


def test_deflect_surcharges_targeted_spell(bolt):
    loop = _loop(); loop.gs.active = "A"
    bf = loop.gs.battlefields[0]
    bf.units_B.append(UnitInPlay(UnitCard(name="Warded", might=2, keywords=["DEFLECT 2"])))
    assert loop._deflect_surcharge(bolt, 0) == 2         # pay +2 to target through DEFLECT


def test_no_deflect_no_surcharge(bolt):
    loop = _loop(); loop.gs.active = "A"
    bf = loop.gs.battlefields[0]
    bf.units_B.append(UnitInPlay(UnitCard(name="Plain", might=2)))
    assert loop._deflect_surcharge(bolt, 0) == 0


def test_deflect_only_charges_enemy_targeting_spells():
    # a friendly-targeting spell is not surcharged even if enemy DEFLECT is present
    name = "TST Buff"
    CARD_REGISTRY[name] = CardSpec.from_dict({
        "name": name, "category": "SPELL",
        "effects": [{"effect": "buff_unit", "trigger": "on_cast", "target": "friendly_unit"}],
    })
    try:
        loop = _loop(); loop.gs.active = "A"
        loop.gs.battlefields[0].units_B.append(
            UnitInPlay(UnitCard(name="Warded", might=2, keywords=["DEFLECT 3"])))
        assert loop._deflect_surcharge(CARD_REGISTRY[name].instantiate(), 0) == 0
    finally:
        CARD_REGISTRY.pop(name, None)
