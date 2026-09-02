"""ACTION on units (§732.1.c.1): a unit with ACTION may be played during a showdown
(to base), not only spells. Verifies the showdown legality offers such a unit, and
that a non-ACTION unit is not offered.
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _showdown_loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b))
    loop.gs.active = "A"
    loop.gs.showdown_active = True
    loop.gs.showdown_bf_idx = 0
    return loop


def _unit_showdown_plays(loop, side="A"):
    acts = legal_actions(loop, DecisionPoint.SHOWDOWN_ACTION, side)
    return [a for a in acts if a.kind == "UNIT"]


def test_action_unit_is_offered_in_showdown():
    loop = _showdown_loop()
    loop.gs.A.hand.append(UnitCard(name="Vanguard", might=2, cost_energy=1, keywords=["ACTION"]))
    loop.gs.A.energy = 2
    plays = _unit_showdown_plays(loop)
    assert any(p.index == 0 for p in plays)          # the ACTION unit is playable


def test_non_action_unit_not_offered_in_showdown():
    loop = _showdown_loop()
    loop.gs.A.hand.append(UnitCard(name="Plain", might=2, cost_energy=1))  # no ACTION
    loop.gs.A.energy = 2
    assert _unit_showdown_plays(loop) == []


def test_action_unit_not_offered_when_unaffordable():
    loop = _showdown_loop()
    loop.gs.A.hand.append(UnitCard(name="Vanguard", might=2, cost_energy=3, keywords=["ACTION"]))
    loop.gs.A.energy = 0
    assert _unit_showdown_plays(loop) == []
