"""Gear's own activated [tap] abilities (Seals, Iron Ballista, Orb of Regret, …)
must be usable from base. They were previously unreachable — activatable_abilities
built only Equip entries for base gear, never ability entries. A [tap] ability taps
the gear (single use per turn) and the gear untaps at the start of its controller's
turn.
"""

from __future__ import annotations

import random

from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec

TAP = "TST Tap Gear"


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def _register():
    CARD_REGISTRY[TAP] = CardSpec.from_dict({
        "name": TAP, "category": "Gear",
        "effects": [{"effect": "gain_energy", "trigger": "activated",
                     "target": "actor", "amount": 3, "cost": {"tap": True}}]})


def _equip_idx(loop, gear, kind="gear_ability"):
    for i, e in enumerate(loop.activatable_abilities("A")):
        if e["type"] == kind and e.get("gear") is gear:
            return i
    return None


def test_gear_tap_ability_is_reachable_and_resolves():
    _register()
    try:
        loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
        gear = CARD_REGISTRY[TAP].instantiate()
        ap.base_gear.append(gear)
        ap.energy = 0

        idx = _equip_idx(loop, gear)
        assert idx is not None                       # the tap ability is offered
        loop._apply_activated_ability(ap, loop.gs.B, idx)
        assert ap.energy == 3                        # effect resolved
        assert gear.tapped is True                   # gear is now tapped
    finally:
        CARD_REGISTRY.pop(TAP, None)


def test_tapped_gear_cannot_reactivate_until_untap():
    _register()
    try:
        loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
        gear = CARD_REGISTRY[TAP].instantiate()
        ap.base_gear.append(gear)
        ap.energy = 0

        idx = _equip_idx(loop, gear)
        loop._apply_activated_ability(ap, loop.gs.B, idx)      # tap once
        assert ap.energy == 3
        loop._apply_activated_ability(ap, loop.gs.B, idx)      # tapped -> no-op
        assert ap.energy == 3

        loop._ready_active_units("A")                          # start-of-turn untap
        assert gear.tapped is False
        idx = _equip_idx(loop, gear)
        loop._apply_activated_ability(ap, loop.gs.B, idx)      # usable again
        assert ap.energy == 6
    finally:
        CARD_REGISTRY.pop(TAP, None)


def test_attached_gear_tap_ability_is_usable():
    _register()
    try:
        from riftbound.core.cards import UnitCard
        from riftbound.core.combat import UnitInPlay
        loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
        unit = UnitInPlay(UnitCard(name="Host", might=2), ready=True)
        loop.gs.battlefields[0].units_A.append(unit)
        gear = CARD_REGISTRY[TAP].instantiate()
        unit.gear.append(gear)                       # gear attached to a controlled unit
        ap.energy = 0

        idx = _equip_idx(loop, gear)                 # gear_ability entry exists
        assert idx is not None
        loop._apply_activated_ability(ap, loop.gs.B, idx)
        assert ap.energy == 3                        # resolved from attached gear
        assert gear.tapped is True
    finally:
        CARD_REGISTRY.pop(TAP, None)


def test_enters_exhausted_gear_taps_on_play():
    name = "TST Enters Exhausted"
    CARD_REGISTRY[name] = CardSpec.from_dict({
        "name": name, "category": "Gear", "cost_energy": 0,
        "effect": "This enters exhausted. [tap]: ADD energy.",
        "effects": [{"effect": "gain_energy", "trigger": "activated",
                     "target": "actor", "amount": 3, "cost": {"tap": True}}]})
    try:
        loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
        ap.hand.append(CARD_REGISTRY[name].instantiate())
        ap.energy = 1
        loop._apply_action(ap, ("GEAR", 0, 0, None))           # play to base
        gear = ap.base_gear[0]
        assert gear.tapped is True                             # entered exhausted
        # its tap ability is present but not usable this turn
        idx = _equip_idx(loop, gear)
        ap.energy = 0
        loop._apply_activated_ability(ap, loop.gs.B, idx)
        assert ap.energy == 0                                  # tapped -> no-op
    finally:
        CARD_REGISTRY.pop(name, None)
