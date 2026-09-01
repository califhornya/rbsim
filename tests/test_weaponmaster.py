"""WEAPONMASTER (§747): when you play a unit with WEAPONMASTER, you may choose an
Equipment you control and pay its Equip cost reduced by [A] (1 Power of any domain)
to attach it to that unit.
"""

from __future__ import annotations

import random

from riftbound.core.cards import GearCard, UnitCard
from riftbound.core.enums import Domain
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec

EQUIP = "TST WM Equip"


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def test_equip_cost_minus_A_drops_one_power():
    loop = _loop()
    # "[1] [fury]" -> energy 1 + 1 Fury; minus [A] drops the Fury.
    cost = {"energy": 1, "domain_power": {"fury": 1}, "generic": 0, "complex": False}
    assert loop._equip_cost_minus_A(cost) == {
        "energy": 1, "domain_power": {}, "generic": 0, "complex": False}
    # "[rune]" -> generic 1; minus [A] drops the generic.
    assert loop._equip_cost_minus_A(
        {"energy": 0, "domain_power": {}, "generic": 1, "complex": False}
    )["generic"] == 0


def test_weaponmaster_attaches_equipment_at_discount():
    CARD_REGISTRY[EQUIP] = CardSpec.from_dict({
        "name": EQUIP, "category": "Gear", "cost_energy": 3,
        "effect": "Equip [1] [fury] ([1] [fury]: Attach this to a unit you control.)"})
    try:
        loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
        ap.base_gear.append(GearCard(name=EQUIP, cost_energy=3))
        ap.hand.append(UnitCard(name="WM Hero", cost_energy=0, keywords=["WEAPONMASTER"]))
        ap.energy = 1                              # equip cost [1][fury] minus [A] = [1]
        loop._apply_action(ap, ("UNIT", 0, 0, None))

        wm = ap.base_units[0]
        assert any(g.name == EQUIP for g in wm.gear)   # attached at the [A] discount
        assert not any(g.name == EQUIP for g in ap.base_gear)
        assert ap.energy == 0                          # paid the reduced [1] only
    finally:
        CARD_REGISTRY.pop(EQUIP, None)


def test_weaponmaster_skips_when_unaffordable():
    CARD_REGISTRY[EQUIP] = CardSpec.from_dict({
        "name": EQUIP, "category": "Gear", "cost_energy": 3,
        "effect": "Equip [2] [fury] ([2] [fury]: Attach this to a unit you control.)"})
    try:
        loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
        ap.base_gear.append(GearCard(name=EQUIP, cost_energy=3))
        ap.hand.append(UnitCard(name="WM Hero", cost_energy=0, keywords=["WEAPONMASTER"]))
        ap.energy = 0                              # cannot pay the reduced [2]
        loop._apply_action(ap, ("UNIT", 0, 0, None))

        wm = ap.base_units[0]
        assert not any(g.name == EQUIP for g in wm.gear)      # not attached
        assert any(g.name == EQUIP for g in ap.base_gear)     # stays at base
    finally:
        CARD_REGISTRY.pop(EQUIP, None)
