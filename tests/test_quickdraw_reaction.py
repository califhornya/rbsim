"""QUICK-DRAW (§745): gear with Quick-Draw has Reaction inherently, so it can be
played at reaction speed — in a reaction window and during a showdown — not only in
the main phase. (Attach-on-play itself is covered by test_gear_play.)
"""

from __future__ import annotations

import random

from riftbound.core.cards import GearCard
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b))
    loop.gs.active = "A"
    return loop


def _gear_plays(acts):
    return [a for a in acts if a.kind == "GEAR"]


def test_quickdraw_gear_offered_at_reaction():
    loop = _loop()
    loop.gs.A.hand.append(GearCard(name="Fast Blade", cost_energy=1, keywords=["QUICK-DRAW"]))
    loop.gs.A.energy = 2
    plays = _gear_plays(legal_actions(loop, DecisionPoint.REACTION, "A"))
    assert any(p.index == 0 for p in plays)


def test_non_quickdraw_gear_not_offered_at_reaction():
    loop = _loop()
    loop.gs.A.hand.append(GearCard(name="Slow Blade", cost_energy=1))   # no QUICK-DRAW
    loop.gs.A.energy = 2
    assert _gear_plays(legal_actions(loop, DecisionPoint.REACTION, "A")) == []


def test_quickdraw_gear_offered_in_showdown():
    loop = _loop()
    loop.gs.showdown_active = True
    loop.gs.showdown_bf_idx = 0
    loop.gs.A.hand.append(GearCard(name="Fast Blade", cost_energy=1, keywords=["QUICK-DRAW"]))
    loop.gs.A.energy = 2
    plays = _gear_plays(legal_actions(loop, DecisionPoint.SHOWDOWN_ACTION, "A"))
    assert any(p.index == 0 for p in plays)
