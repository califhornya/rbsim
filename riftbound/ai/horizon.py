"""The hand-written bot that looks past the end of its turn (20/11, external
review; docs/bot/RETE.md, "Orizzonte").

The search values a PASS that ends the turn on the board before the turn
closes (net_mcts._iterate): what the opponent's turn will do is left to
table_value. s3012 is the case: defending and attacking with Zed have the same
Q, defending wins 23 worlds of 24 and attacking 8.

At a main-turn decision with no move being declared:
1. the usual search, with `root_share` of the time (0.20 s of 0.40; the review
   proposed 0.30, but then the look ahead ran out of time in 10 of 12 tries
   in s3012 and the move was the bot's, searched for less: 20/11);
2. finalists: the bot's move (the highest Q, as it would play) and the best
   other move by Q, both with at least `min_visits` visits and at most `gap`
   apart in Q. With no such pair, the rest of the time goes to the search;
3. in `worlds` paired worlds (determinized from our side), each finalist is
   played (its inner choices as the search would make them), then both sides
   go on with the hand-written bot at `rollout_iters` iterations: through the
   end of our turn, the opponent's start of turn, up to the opponent's first
   action of its turn; there table_value from our side (+1 / 0 / -1 for a
   game over);
4. the other move is played only if its mean paired advantage is above
   `margin`; if the time runs out before every rollout is done, the bot's move.
"""
from __future__ import annotations

import random
import time
from collections import Counter
from typing import Optional

from riftbound.ai.handwritten import HandwrittenAgent, table_value
from riftbound.ai.net_mcts import _Plan
from riftbound.core.decisions import DecisionPoint, Observation


class _Reached(BaseException):
    """The opponent's first action of its turn (not an Exception: the loop won't catch it)."""


def _best_key(root):
    """The move the bot plays at `root` (net_mcts._play, backup best, no exploration)."""
    items = [(k, c) for k, c in root.children.items() if c.N > 0] or list(root.children.items())
    return max(items, key=lambda kv: kv[1].Q)[0]


class HorizonAgent(HandwrittenAgent):
    name = "orizzonte"

    def __init__(self, player, rng: Optional[random.Random] = None, budget: float = 0.4,
                 root_share: float = 0.5, gap: float = 0.02, min_visits: int = 4,
                 worlds: int = 2, rollout_iters: int = 4, margin: float = 0.02, **kw):
        super().__init__(player, rng=rng, budget=budget, **kw)
        self.root_share, self.gap, self.min_visits = root_share, gap, min_visits
        self.worlds, self.rollout_iters, self.margin = worlds, rollout_iters, margin
        self.stats: Counter = Counter()
        self._pending_horizon = None

    # -- which decisions, and the finalists ----------------------------------

    def _finalists(self, root):
        key = _best_key(root)
        best = root.children.get(key)
        if best is None or best.N < self.min_visits:
            return None
        others = [(k, c) for k, c in root.children.items()
                  if k != key and c.N >= self.min_visits and best.Q - c.Q <= self.gap]
        if not others:
            return None
        alt = max(others, key=lambda kv: kv[1].Q)[0]
        return key, alt

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        self._pending_horizon = None
        if point != DecisionPoint.TURN_ACTION or self.gs.pending_move is not None or self.budget is None:
            return super().search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
        t0, full = time.process_time(), self.budget
        self.budget = full * self.root_share
        try:
            root = super().search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
        finally:
            self.budget = full
        self.stats["decisioni"] += 1
        fin = self._finalists(root)
        if fin is None:
            side = self.player.name
            while time.process_time() - t0 < full:
                self._iterate(root, side, cards_played, legal)
                self.main_iters[-1] += 1
        else:
            self.stats["con finaliste"] += 1
            self._pending_horizon = (t0 + full, fin)
        return root

    # -- the look past the turn ----------------------------------------------

    def _rollout(self, node, action, seed: int) -> float:
        from riftbound.core.loop import GameLoop
        from riftbound.core.state import determinize
        side = self.player.name
        gs = self.gs.clone()
        gs.rng = random.Random(seed)
        determinize(gs, observer=side, rng=gs.rng)
        iters = self.rollout_iters

        class Me(HandwrittenAgent):
            first = True

            def decide_action(self, opponent, cards_played: int = 0):
                if self.first:
                    self.first = False
                    self._ensure_rng()
                    self._ensure_fallback()
                    self._release_forced()
                    if node.choices:        # its inner choices as the search would make them
                        self.loop.chooser = _Plan(side, node, 0, self.loop, self.loop.chooser)
                    return action
                return super().decide_action(opponent, cards_played)

        class Them(HandwrittenAgent):
            def decide_action(self, opponent, cards_played: int = 0):
                raise _Reached()

        other = gs.other(side)
        for p, cls, k in ((gs.get_player(side), Me, 1), (gs.get_player(other), Them, 2)):
            p.agent = cls(p, iterations=iters, rng=random.Random(seed * 2 + k))
            p.agent.reaction_iterations = iters
        try:
            res = GameLoop(gs).resume_to_completion()
        except _Reached:
            return table_value(Observation.from_state(gs, side))
        return 1.0 if res.winner == side else 0.0 if res.winner == "DRAW" else -1.0

    def _play(self, root, side, point=DecisionPoint.TURN_ACTION):
        before = self.loop.chooser
        key = super()._play(root, side, point)
        pending, self._pending_horizon = self._pending_horizon, None
        if pending is None or point != DecisionPoint.TURN_ACTION:
            return key
        deadline, (bot, alt) = pending
        if key != bot:
            return key
        diffs = []
        for w in range(self.worlds):
            seed = self._rng.randrange(1 << 30)
            vb = self._rollout(root.children[bot], bot, seed)
            if time.process_time() > deadline:
                break
            va = self._rollout(root.children[alt], alt, seed)
            if time.process_time() > deadline:
                break
            diffs.append(va - vb)
        if len(diffs) < self.worlds:
            self.stats["tempo scaduto"] += 1
            return key
        self.stats["confronti"] += 1
        if sum(diffs) / len(diffs) <= self.margin:
            return key
        self.stats["cambi"] += 1
        # The plan installed for the bot's move goes; the other move's comes.
        self.loop.chooser = before
        node = root.children[alt]
        if node.choices:
            self.loop.chooser = _Plan(side, node, 0, self.loop, before)
        return alt
