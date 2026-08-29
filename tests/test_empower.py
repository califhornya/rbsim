"""Vendetta EMPOWER / EMPOWERED mechanic.

EMPOWER is an activated ability that pays a cost to give the source unit the
`empowered` status (one-shot: only usable while not already empowered). EMPOWERED
is a dependent ability, modeled as a passive effect gated on the
`this_is_empowered` condition, so its bonus (might / keyword) applies only while
the unit carries the status.
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY as EFFECT_REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


# A Vendetta-style empower unit: EMPOWER [2] -> EMPOWERED +3 might and DEFLECT.
_EMPOWER_SPEC = {
    "name": "Test Empower Unit",
    "category": "Unit",
    "cost_energy": 3,
    "might": 3,
    "effects": [
        {"effect": "empower_self", "trigger": "activated", "cost": {"energy": 2}},
        {"effect": "grant_might", "trigger": "passive",
         "condition": {"type": "this_is_empowered"}, "target": "self", "amount": 3},
        {"effect": "give_keyword", "trigger": "passive",
         "condition": {"type": "this_is_empowered"}, "target": "self", "keyword": "DEFLECT"},
    ],
}


def _register(spec_dict) -> CardSpec:
    spec = CardSpec.from_dict(spec_dict)
    CARD_REGISTRY[spec.name] = spec
    return spec


def test_empower_condition_gates_on_status():
    loop = _loop()
    card = UnitCard(name="X", might=3)
    unit = UnitInPlay(card=card)
    loop.gs.battlefields[0].units_A.append(unit)
    cond = {"type": "this_is_empowered"}
    assert loop._check_condition(cond, card, loop.gs.A, loop.gs.B, None) is False
    unit.empowered = True
    assert loop._check_condition(cond, card, loop.gs.A, loop.gs.B, None) is True


def test_empowered_passive_bonus_applies_only_when_empowered():
    _register(_EMPOWER_SPEC)
    loop = _loop()
    card = UnitCard(name="Test Empower Unit", might=3)
    unit = UnitInPlay(card=card)
    loop.gs.battlefields[0].units_A.append(unit)

    loop._recompute_passives()
    assert unit.might == 3            # not empowered -> base
    assert not unit.has_keyword("DEFLECT")

    unit.empowered = True
    loop._recompute_passives()
    assert unit.might == 6            # +3 from the empowered passive
    assert unit.has_keyword("DEFLECT")


def test_empower_self_handler_sets_status():
    loop = _loop()
    card = UnitCard(name="Y", might=2)
    unit = UnitInPlay(card=card)
    loop.gs.battlefields[0].units_A.append(unit)
    ctx = EffectContext(loop, card, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    assert unit.empowered is False
    EFFECT_REGISTRY["empower_self"](ctx, {})
    assert unit.empowered is True


def test_empower_ability_is_one_shot():
    _register(_EMPOWER_SPEC)
    loop = _loop()
    card = UnitCard(name="Test Empower Unit", might=3)
    unit = UnitInPlay(card=card, ready=True)
    loop.gs.battlefields[0].units_A.append(unit)

    def empower_entries():
        return [e for e in loop.activatable_abilities("A")
                if e.get("eff") and e["eff"].effect == "empower_self"]

    assert len(empower_entries()) == 1     # available before empowering
    unit.empowered = True
    assert len(empower_entries()) == 0     # gone once empowered


def test_disempower_removes_status():
    loop = _loop()
    card = UnitCard(name="Z", might=4)
    unit = UnitInPlay(card=card, empowered=True)
    loop.gs.battlefields[0].units_B.append(unit)  # enemy unit
    ctx = EffectContext(loop, UnitCard(name="Src"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    EFFECT_REGISTRY["disempower"](ctx, {"target": "enemy_unit"})
    assert unit.empowered is False
