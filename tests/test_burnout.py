"""Burn Out (Core Rules §418 / §315.4.b): when a player must draw from an empty
Main Deck, they recycle their trash into the deck (randomized), an opponent gains
1 point, then the draw completes. A fully decked-out player (deck AND trash empty)
still hands the opponent a point each draw — the deck-out loss vector.
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


def test_burn_out_recycles_trash_and_awards_opponent_point():
    loop = _loop(); a = loop.gs.A
    a.deck.cards.clear()                                   # empty Main Deck
    a.trash.extend([UnitCard(name="T1", might=1), UnitCard(name="T2", might=1)])
    assert loop.gs.points_B == 0

    loop._phase_draw(a)

    assert loop.gs.points_B == 1          # opponent gained 1 point (§418.2.c)
    assert a.trash == []                  # trash recycled into deck (§418.2.b)
    assert len(a.hand) == 1               # the draw still completes (§315.4.b.2)
    assert len(a.deck.cards) == 1         # 2 recycled - 1 drawn


def test_fully_decked_out_still_awards_point():
    loop = _loop(); a = loop.gs.A
    a.deck.cards.clear(); a.trash.clear()                  # deck AND trash empty

    loop._phase_draw(a)

    assert loop.gs.points_B == 1          # opponent still gains a point
    assert len(a.hand) == 0               # nothing to draw


def test_burn_out_via_draw_effect():
    loop = _loop(); a = loop.gs.A
    a.deck.cards.clear()
    a.trash.append(UnitCard(name="T1", might=1))
    from riftbound.core.loop import EffectContext
    ctx = EffectContext(loop, UnitCard(name="Src", might=1), a, loop.gs.B, loop.gs.battlefields[0])

    ctx.draw_cards(1, target="actor")

    assert loop.gs.points_B == 1
    assert len(a.hand) == 1
