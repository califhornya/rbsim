"""ISMCTSAgent — Single-Observer Information-Set Monte-Carlo Tree Search.

The strong version of the search agent. Where MonteCarloAgent does a 1-ply
lookahead (evaluate each first action by rollouts), ISMCTS builds a *tree* over
the active player's whole action sequence this turn, sharing statistics across
many determinized worlds, and only rolls out the rest of the game.

Each iteration (one determinized world):
  1. Determinize the opponent's hidden hand (clone + determinize).
  2. SELECT/EXPAND: descend the shared tree, applying one action at a time to the
     clone via GameLoop._apply_action (single-step, synchronous — no rewrite), by
     UCT until an unexpanded action, which we expand.
  3. ROLLOUT: finish the game from there with the fast playout policy
     (resume_to_completion, or _end_turn+_play_all_turns after a PASS).
  4. BACKPROP the win/draw/loss up the visited path.
Return the most-visited root action.

It encodes no strategy — like MonteCarloAgent it learns to play from the rules by
simulating. Reuses MonteCarloAgent for the (searched) mulligan, the playout
policy, and RNG seeding. Env knobs: RBSIM_ISMCTS_ITERS (default 80),
RBSIM_ISMCTS_C (exploration constant, default 1.4).
"""

from __future__ import annotations

import math
import os
import random
from typing import Optional

from riftbound.ai.heuristics.base_agent import Action
from riftbound.ai.search.monte_carlo_agent import MonteCarloAgent
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions

_PASS: Action = ("PASS", None, None)
_MAX_TURN_ACTIONS = 30  # safety cap on one turn's action sequence during a descent


class _Node:
    __slots__ = ("N", "W", "children", "untried")

    def __init__(self):
        self.N = 0
        self.W = 0.0
        self.children: dict = {}   # action_tuple -> _Node
        self.untried: Optional[list] = None  # set lazily to legal actions on first visit


class ISMCTSAgent(MonteCarloAgent):
    name = "ismcts"

    def __init__(self, player, iterations: Optional[int] = None, c: Optional[float] = None, **kw):
        super().__init__(player, **kw)
        self.iterations = iterations if iterations is not None else int(os.environ.get("RBSIM_ISMCTS_ITERS", "80"))
        self.c = c if c is not None else float(os.environ.get("RBSIM_ISMCTS_C", "1.4"))

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._ensure_rng()
        self.last_eval = []
        side = self.player.name
        root_legal = legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)
        if len(root_legal) <= 1:
            return root_legal[0].to_engine() if root_legal else _PASS

        root = _Node()
        for _ in range(self.iterations):
            self._iterate(root, side, cards_played)

        # Most-visited root action wins; expose visit shares for the tracer.
        if not root.children:
            return _PASS
        ranked = sorted(root.children.items(), key=lambda kv: -kv[1].N)
        self.last_eval = [(self._label(root_legal, a), n.W / n.N if n.N else 0.0) for a, n in ranked]
        return ranked[0][0]

    @staticmethod
    def _label(legal, action_tuple) -> str:
        for a in legal:
            if a.to_engine() == action_tuple:
                return a.label or a.kind
        return str(action_tuple)

    def _reward(self, result, side: str) -> float:
        if result.winner == side:
            return 1.0
        if result.winner == "DRAW":
            return 0.5
        return 0.0

    def _iterate(self, root: _Node, side: str, cards_played: int) -> None:
        from riftbound.core.loop import GameLoop  # local import avoids a cycle
        clone = self.gs.clone()
        clone.rng = random.Random(self._rng.randrange(1 << 30))
        from riftbound.core.state import determinize
        determinize(clone, observer=side, rng=clone.rng)
        clone.A.agent = self._policy(clone.A)
        clone.B.agent = self._policy(clone.B)
        loop = GameLoop(clone)

        node = root
        path = [root]
        cpt = cards_played
        reward = None

        for _ in range(_MAX_TURN_ACTIONS):
            ap = clone.get_player(clone.active)
            # Our turn ended (combat/opponent took over) — stop descending, roll out.
            if clone.active != side:
                reward = self._reward(loop.resume_to_completion(), side)
                break
            legal = [a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, side)]
            if node.untried is None:
                node.untried = [a for a in legal if a not in node.children]

            if node.untried:
                action = node.untried.pop(self._rng.randrange(len(node.untried)))
                child = _Node()
                node.children[action] = child
                path.append(child)
                reward = self._reward(self._apply_and_rollout(loop, clone, ap, action, side, cpt), side)
                break

            if not node.children:  # nothing to do (only happens if legal shrank) → roll out
                reward = self._reward(loop.resume_to_completion(), side)
                break

            action = self._uct_select(node)
            path.append(node.children[action])
            if action == _PASS:
                reward = self._reward(loop._end_turn() or loop._play_all_turns(), side)
                break
            loop._apply_action(ap, action, cards_played_this_turn=cpt)
            loop._recompute_passives()
            cpt += 1
            node = node.children[action]
        else:
            # Hit the depth cap — roll out whatever remains.
            reward = self._reward(loop.resume_to_completion(), side)

        for n in path:
            n.N += 1
            n.W += reward

    def _apply_and_rollout(self, loop, clone, ap, action, side, cpt) -> "object":
        """Apply an expanded action then finish the game with the playout policy."""
        if action == _PASS:
            # Active player is done this turn → skip their main phase in the rollout.
            return loop._end_turn() or loop._play_all_turns()
        loop._apply_action(ap, action, cards_played_this_turn=cpt)
        loop._recompute_passives()
        return loop.resume_to_completion()

    def _uct_select(self, node: _Node):
        logN = math.log(node.N + 1)
        best, best_val = None, -1.0
        for action, child in node.children.items():
            if child.N == 0:
                return action
            val = child.W / child.N + self.c * math.sqrt(logN / child.N)
            if val > best_val:
                best_val, best = val, action
        return best
