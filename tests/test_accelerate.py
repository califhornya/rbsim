"""ACCELERATE (Core Rules §731): an OPTIONAL additional cost ([1] + 1 Power of the
unit's domain) paid as you play the unit; if paid, the unit enters ready (§731.6).
§731.2: it is a *may* — the controller chooses. The engine routes that choice through
the agent's `decide_optional` (default yes preserves prior always-accelerate play).
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


class _RefuseAccelerate:
    """Agent stub that declines the optional Accelerate cost."""
    def decide_optional(self, card, effect_name) -> bool:
        return effect_name != "accelerate"


def _play_accel_unit(agent=None, energy=2):
    loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
    if agent is not None:
        ap.agent = agent
    # domainless ACCELERATE unit: engine charges the [1] energy (the [A] power is a
    # documented undercharge for domainless units — see MECHANICS.md Accelerate note).
    ap.hand.append(UnitCard(name="Swift Recruit", cost_energy=0, keywords=["ACCELERATE"]))
    ap.energy = energy
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    units = ap.base_units                       # units play to base (lane ignored)
    assert len(units) == 1
    return units[0], ap


def test_accelerate_enters_ready_when_paid_by_default():
    unit, ap = _play_accel_unit()             # no agent -> default yes
    assert unit.ready is True
    assert ap.energy == 1                      # 2 - 1 (accelerate) = 1


def test_accelerate_is_optional_agent_can_decline():
    unit, ap = _play_accel_unit(agent=_RefuseAccelerate())
    assert unit.ready is False                 # declined -> enters exhausted
    assert ap.energy == 2                       # nothing spent on accelerate


def test_accelerate_skipped_when_unaffordable():
    unit, ap = _play_accel_unit(energy=0)
    assert unit.ready is False
    assert ap.energy == 0
