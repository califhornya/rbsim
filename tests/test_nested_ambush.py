"""Nested AMBUSH showdown (#22): an AMBUSH deploy into a CONTESTED lane now spawns a
showdown (mirroring the move-into-contested path). _run_showdown self-guards on
showdown_active, so a deploy made during an existing showdown does not nest — the
champion joins the current lane's combat instead.
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec

AMB = "TST Ambusher"


def _register_ambusher():
    CARD_REGISTRY[AMB] = CardSpec.from_dict({
        "name": AMB, "category": "Champion", "might": 3, "cost_energy": 0,
        "keywords": ["AMBUSH"],
        "effects": [{"effect": "ambush", "trigger": "passive", "enemy_ok": True}]})


def _loop_with_enemy_at_bf0():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b))
    loop.gs.active = "A"
    loop.gs.champion_A = CARD_REGISTRY[AMB].instantiate()
    loop.gs.champion_A_deployed = False
    loop.gs.battlefields[0].units_B.append(UnitInPlay(UnitCard(name="Defender", might=2), ready=True))
    return loop


def test_ambush_into_contested_lane_spawns_showdown():
    _register_ambusher()
    try:
        loop = _loop_with_enemy_at_bf0()
        ok = loop._deploy_ambush_champion("A", 0)
        assert ok is True
        bf = loop.gs.battlefields[0]
        assert any(u.card.name == AMB for u in bf.units_A)   # champion deployed
        assert bf.contested_this_turn is True                # showdown/combat engaged
        assert loop.gs.showdown_active is False              # the showdown ran + closed
    finally:
        CARD_REGISTRY.pop(AMB, None)


def test_ambush_during_showdown_does_not_nest():
    _register_ambusher()
    try:
        loop = _loop_with_enemy_at_bf0()
        loop.gs.showdown_active = True          # already in a showdown
        loop.gs.showdown_bf_idx = 0
        ok = loop._deploy_ambush_champion("A", 0)
        assert ok is True                        # deployed without nesting/recursion
        assert any(u.card.name == AMB for u in loop.gs.battlefields[0].units_A)
        assert loop.gs.showdown_active is True   # still the SAME showdown (not nested)
    finally:
        CARD_REGISTRY.pop(AMB, None)
