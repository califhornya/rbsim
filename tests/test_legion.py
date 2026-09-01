"""LEGION (Core Rules §738): "if you've already played another card this turn,
apply [Text]". For a cost-reducing Legion ("I cost [2] less"), the reduction must
apply ONCE. Regression: it was applied twice — once by a hardcoded legion path and
again by the generic `_cost_reduction` (both keyed on the same condition) — making
Noxus Hopeful cost 0 instead of 2.
"""

from __future__ import annotations

import random

from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def test_legion_cost_reduction_applies_once():
    loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
    ap.hand.append(CARD_REGISTRY["Noxus Hopeful"].instantiate())   # cost 4, LEGION -2
    ap.energy = 4
    loop.gs.cards_played_this_turn["A"] = 1                        # a card already played
    loop._apply_action(ap, ("UNIT", 0, 0, None), cards_played_this_turn=1)
    assert ap.energy == 2          # 4 - 2 once (not 4 - 2 - 2 = 0)


def test_legion_no_reduction_when_first_card():
    loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
    ap.hand.append(CARD_REGISTRY["Noxus Hopeful"].instantiate())
    ap.energy = 4
    # no prior card this turn -> Legion condition false -> full cost.
    loop._apply_action(ap, ("UNIT", 0, 0, None), cards_played_this_turn=0)
    assert ap.energy == 0          # paid full 4
