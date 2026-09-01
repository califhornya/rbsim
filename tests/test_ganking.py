"""Ganking §736: a passive that adds a battlefield->battlefield option to a unit's
Standard Move ("I may move to a battlefield from another battlefield"). Without
Ganking a unit may only move battlefield->base (or base->battlefield); with Ganking
it may also move directly bf->bf.
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop_with_unit_at_bf0(keywords):
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b))
    loop.gs.active = "A"
    unit = UnitInPlay(UnitCard(name="Rover", might=2, keywords=list(keywords)), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)
    return loop


def _bf_to_bf_moves(loop):
    acts = legal_actions(loop, DecisionPoint.TURN_ACTION, "A")
    # MOVE: lane=src, dst_lane=dst; bf->bf = both < n_bf and src != dst.
    n_bf = len(loop.gs.battlefields)
    return [a for a in acts
            if a.kind == "MOVE" and a.lane < n_bf and a.dst_lane < n_bf
            and a.lane != a.dst_lane]


def test_no_ganking_no_bf_to_bf_move():
    loop = _loop_with_unit_at_bf0([])
    assert _bf_to_bf_moves(loop) == []          # only bf->base / base->bf allowed


def test_ganking_enables_bf_to_bf_move():
    loop = _loop_with_unit_at_bf0(["GANKING"])
    moves = _bf_to_bf_moves(loop)
    assert any(m.lane == 0 and m.dst_lane == 1 for m in moves)   # BF0 -> BF1 now legal
