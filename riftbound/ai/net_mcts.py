"""NetGuidedMCTSAgent — AlphaZero-style, network-guided MCTS (RL Chunk 3).

Where `ISMCTSAgent` explores with random/heuristic rollouts, this agent uses the
policy+value network (`net.py`) instead:
- **priors** P(a) from the network's policy steer selection (PUCT), and
- a **leaf is evaluated by the network's value** — no random playout.

Per decision it runs N simulations over the active player's turn on a determinized
clone (hidden opponent info resampled per iteration, as in ISMCTS), then plays the
**most-visited** root action. This is the search half of AlphaZero; the self-play
training loop (next chunk) will feed the visit distributions back as policy targets.

Requires the optional `rl` extra (torch), via `net.py`. Search focuses on the main
turn action (like ISMCTS); mulligan/showdown/reaction stay simple in v1 (documented
deferrals — folding them into the learned policy is later work).
"""

from __future__ import annotations

import math
import random
from typing import Optional

import numpy as np

from riftbound.ai.encoding import (
    action_to_index,
    encode_observation,
    legal_mask,
)
from riftbound.ai.heuristics.base_agent import Action, Agent
from riftbound.ai.net import RiftboundNet, predict
from riftbound.core.decisions import DecisionPoint, Observation
from riftbound.core.legality import legal_actions

_PASS: Action = ("PASS", None, None)
_MAX_TURN_ACTIONS = 30


class _Node:
    __slots__ = ("N", "W", "P", "children", "expanded", "value")

    def __init__(self):
        self.N = 0
        self.W = 0.0
        self.P: dict = {}          # action_tuple -> prior
        self.children: dict = {}   # action_tuple -> _Node
        self.expanded = False
        self.value = 0.0


class NetGuidedMCTSAgent(Agent):
    name = "net_mcts"

    def __init__(self, player, net: RiftboundNet, iterations: int = 100,
                 c_puct: float = 1.5, rng: Optional[random.Random] = None):
        super().__init__(player)
        self.net = net
        self.iterations = iterations
        self.c_puct = c_puct
        self._rng = rng
        # Last root visit distribution (action_tuple -> visit share), for the
        # self-play trainer's policy target and for debugging.
        self.last_visits: dict = {}

    def _ensure_rng(self) -> None:
        if self._rng is None:
            base = getattr(self, "gs", None)
            seed = base.rng.randrange(1 << 30) if base is not None else random.randrange(1 << 30)
            self._rng = random.Random(seed)

    # -- network evaluation of a determinized state --------------------------

    def _evaluate(self, clone, side: str, legal_ga: list) -> tuple[dict, float]:
        """Run the net on ``clone`` from ``side``'s view. Returns (priors over the
        legal engine-tuples, value in [-1,1]). Uniform priors if the net puts no
        mass on any legal slot."""
        obs = Observation.from_state(clone, side)
        vec = encode_observation(obs)
        mask = legal_mask(legal_ga)
        probs, value = predict(self.net, vec, mask)
        priors: dict = {}
        total = 0.0
        for a in legal_ga:
            t = a.to_engine()
            idx = action_to_index(a)
            p = float(probs[idx]) if idx is not None else 0.0
            priors[t] = p
            total += p
        if total > 1e-8:
            for t in priors:
                priors[t] /= total
        else:
            u = 1.0 / max(1, len(priors))
            priors = {t: u for t in priors}
        return priors, value

    def _net_value(self, clone, side: str) -> float:
        obs = Observation.from_state(clone, side)
        vec = encode_observation(obs)
        # value is independent of the mask; pass the current legal mask for cheapness.
        legal_ga = legal_actions(self._loop_for(clone), DecisionPoint.TURN_ACTION, side)
        _probs, value = predict(self.net, vec, legal_mask(legal_ga))
        return value

    @staticmethod
    def _loop_for(clone):
        from riftbound.core.loop import GameLoop
        return GameLoop(clone)

    # -- search --------------------------------------------------------------

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._ensure_rng()
        side = self.player.name
        root_legal = legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)
        if len(root_legal) <= 1:
            return root_legal[0].to_engine() if root_legal else _PASS

        root = _Node()
        for _ in range(self.iterations):
            self._iterate(root, side, cards_played)

        if not root.children:
            return _PASS
        total = sum(c.N for c in root.children.values()) or 1
        self.last_visits = {a: c.N / total for a, c in root.children.items()}
        # Most-visited action (AlphaZero's move choice).
        best = max(root.children.items(), key=lambda kv: kv[1].N)[0]
        return best

    def _iterate(self, root: _Node, side: str, cards_played: int) -> None:
        from riftbound.core.loop import GameLoop
        from riftbound.core.state import determinize
        clone = self.gs.clone()
        clone.rng = random.Random(self._rng.randrange(1 << 30))
        determinize(clone, observer=side, rng=clone.rng)
        loop = GameLoop(clone)

        node = root
        path = [root]
        cpt = cards_played
        value = 0.0
        vs = clone.victory_score

        for _ in range(_MAX_TURN_ACTIONS):
            # Decided game → exact terminal value from `side`'s perspective.
            if clone.points_A >= vs or clone.points_B >= vs:
                pa, pb = clone.points_A, clone.points_B
                win = (pa > pb) if side == "A" else (pb > pa)
                value = 1.0 if win else (-1.0 if pa != pb else 0.0)
                break
            if clone.active != side:
                value = self._net_value(clone, side)   # opponent to move → net estimate
                break

            legal_ga = legal_actions(loop, DecisionPoint.TURN_ACTION, side)
            if not legal_ga:
                value = self._net_value(clone, side)
                break

            if not node.expanded:
                priors, v = self._evaluate(clone, side, legal_ga)
                node.P = priors
                node.children = {t: _Node() for t in priors}
                node.expanded = True
                node.value = v
                value = v
                break

            action = self._puct_select(node, [a.to_engine() for a in legal_ga])
            if action is None:
                value = self._net_value(clone, side)
                break
            path.append(node.children[action])
            if action == _PASS:
                # Stop-here: evaluate the position where we choose to end acting.
                value = self._net_value(clone, side)
                break
            ap = clone.get_player(side)
            loop._apply_action(ap, action, cards_played_this_turn=cpt)
            loop._recompute_passives()
            cpt += 1
            node = node.children[action]
        else:
            value = self._net_value(clone, side)

        for n in path:
            n.N += 1
            n.W += value

    def _puct_select(self, node: _Node, legal: list):
        """PUCT over children that are currently legal:
        argmax  Q(a) + c_puct * P(a) * sqrt(sum_b N_b) / (1 + N_a)."""
        legal_set = set(legal)
        candidates = [(a, c) for a, c in node.children.items() if a in legal_set]
        if not candidates:
            return None
        sqrt_total = math.sqrt(max(1, node.N))
        best, best_val = None, -1e30
        for a, child in candidates:
            q = (child.W / child.N) if child.N > 0 else 0.0
            u = self.c_puct * node.P.get(a, 0.0) * sqrt_total / (1 + child.N)
            val = q + u
            if val > best_val:
                best_val, best = val, a
        return best

    # -- other decision points (simple in v1; documented deferral) -----------

    def decide_mulligan(self) -> list:
        return []   # keep all — learned mulligan is deferred (DEFERRED.md)

    def decide_showdown_action(self, opponent, bf_idx: int) -> Action:
        return _PASS

    def decide_reaction(self, opponent, chain) -> Action:
        return _PASS
