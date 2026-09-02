"""VISION / PREDICT 1 (§743): look at the top card of your Main Deck; you MAY
recycle it to the bottom. Default (heuristic / no agent) is to keep it; a learning
agent can override decide_predict_recycle. (Top of deck = end of the cards list.)
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


class _Recycler:
    def decide_predict_recycle(self, card) -> bool:
        return True


def _predict1(loop):
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["predict"](ctx, {"amount": 1})


def test_predict1_keeps_top_by_default():
    loop = _loop()
    loop.gs.A.deck.cards = [UnitCard(name="Bottom", might=1), UnitCard(name="Top", might=1)]
    _predict1(loop)                                  # no agent -> keep
    assert loop.gs.A.deck.cards[-1].name == "Top"    # top unchanged


def test_predict1_recycles_top_when_agent_wants():
    loop = _loop()
    loop.gs.A.agent = _Recycler()
    loop.gs.A.deck.cards = [UnitCard(name="Bottom", might=1), UnitCard(name="Top", might=1)]
    _predict1(loop)                                  # recycle the top to the bottom
    assert loop.gs.A.deck.cards[-1].name == "Bottom"  # new top
    assert loop.gs.A.deck.cards[0].name == "Top"      # recycled to bottom


def test_predict1_noop_on_empty_deck():
    loop = _loop()
    loop.gs.A.deck.cards = []
    _predict1(loop)                                  # must not raise
    assert loop.gs.A.deck.cards == []
