"""The hand-written bot (PR #32): the search of `net_mcts` with equal priors and
`table_value`, a value written by hand (points, battlefields, Might, cards).

`scripts/diag/handwritten_value.py` measures it (0.80 against simple_trade,
0.97 against random, 18/11); `scripts/bootstrap_net.py` trains a net on its
games. `budget`: search for that many CPU seconds per decision instead of a
fixed number of iterations, to compare two bots at the same time per move.
"""

from __future__ import annotations

import math
import random
import time
from typing import Optional

from riftbound.ai.net_mcts import NetGuidedMCTSAgent, _Node
from riftbound.core.decisions import DecisionPoint, Observation


def _m(u) -> int:
    """The Might that lasts past this turn: the search values positions in the
    middle of a turn, where a "+5 this turn" with nothing to fight is no gain."""
    return u.might if u.lasting_might is None else u.lasting_might


def table_value(obs) -> float:
    me = obs.viewer
    s = 0.45 * (obs.my_points - obs.opp_points)
    for bf in obs.battlefields:
        mine = sum(_m(u) for u in getattr(bf, me)); theirs = sum(_m(u) for u in getattr(bf, 'B' if me == 'A' else 'A'))
        if bf.controller == me: s += 0.30
        elif bf.controller is not None: s -= 0.30
        s += 0.05 * (mine - theirs)
    s += 0.03 * (sum(_m(u) for u in obs.my_base_units) - sum(_m(u) for u in obs.opp_base_units))
    s += 0.03 * (len(obs.my_hand) - obs.opp_hand_count)
    return math.tanh(s)


class _Budget:
    """search(): `budget` CPU seconds per decision (at least one iteration)
    when set, else the agent's fixed iterations. `main_iters`: the iterations
    of each main-turn search."""
    budget: Optional[float] = None

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        if self.budget is None:
            return super().search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
        self._ensure_rng()
        side = self.player.name
        root = _Node()
        self._full = True
        t0, n = time.process_time(), 0
        while n < 1 or time.process_time() - t0 < self.budget:
            if point == DecisionPoint.TURN_ACTION:
                self._iterate(root, side, cards_played)
            else:
                self._iterate_now(root, side, point, legal, bf_idx)
            n += 1
        if point == DecisionPoint.TURN_ACTION:
            self.main_iters.append(n)
        return root


class HandwrittenAgent(_Budget, NetGuidedMCTSAgent):
    name = "handwritten"

    def __init__(self, player, iterations: int = 100, rng: Optional[random.Random] = None,
                 budget: Optional[float] = None, advance_forced_move: bool = False,
                 tie_break: str = "first"):
        super().__init__(player, None, iterations=iterations, rng=rng, backup="best",
                         advance_forced_move=advance_forced_move, tie_break=tie_break)
        self.budget = budget
        self.main_iters: list = []

    def _evaluate(self, clone, side, legal_ga):
        ts = [a.to_engine() for a in legal_ga]
        u = 1.0 / max(1, len(ts))
        return {t: u for t in ts}, table_value(Observation.from_state(clone, side))

    def _net_value(self, clone, side):
        return table_value(Observation.from_state(clone, side))
    _value_only = _net_value


class NetAgent(_Budget, NetGuidedMCTSAgent):
    """The net's search (priors and value from the net), optionally by time."""
    name = "net"

    def __init__(self, player, net, iterations: int = 100, rng: Optional[random.Random] = None,
                 budget: Optional[float] = None, advance_forced_move: bool = False):
        super().__init__(player, net, iterations=iterations, rng=rng, backup="best",
                         advance_forced_move=advance_forced_move)
        self.budget = budget
        self.main_iters: list = []


class NetValueAgent(NetAgent):
    """The hybrid of the boot1 arena (19/11): the hand-written bot's search
    (equal priors over the legal actions at every expansion) with the net's
    value instead of `table_value`, in the main turn, in showdowns and
    reactions, and for the mulligan."""
    name = "net_value"

    def _evaluate(self, clone, side, legal_ga):
        ts = [a.to_engine() for a in legal_ga]
        u = 1.0 / max(1, len(ts))
        return {t: u for t in ts}, self._value_only(clone, side)
