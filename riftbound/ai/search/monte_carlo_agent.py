"""MonteCarloAgent — the first no-heuristics search agent (flat Monte Carlo).

At its turn it does a 1-ply lookahead: for every legal action it plays many
determinized playouts to the end and keeps the action with the best win rate. It
encodes NO strategy — it discovers good play (empower timing, battlefield
contests, sequencing) purely by simulating the rules.

Built entirely on primitives that already exist:
- `legal_actions` (legality.py) — the moves to evaluate,
- `GameState.clone` + `determinize` (state.py) — an independent, hidden-info-fair
  world per playout,
- `GameLoop.resume_to_completion` (loop.py, Step 1) — play a mid-turn clone out.

Tuning (env overrides so batch sims need no code change):
- RBSIM_MC_K            rollouts per candidate action (default 20)
- RBSIM_MC_ROLLOUT      playout policy: "random" (default) or "simple_trade"
- RBSIM_MC_MAXCANDS     cap on candidate actions evaluated (default 0 = no cap)
"""

from __future__ import annotations

import os
import random
from typing import Optional

from riftbound.ai.heuristics.base_agent import Action, Agent
from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.ai.search.random_agent import RandomAgent
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.state import determinize

_PASS: Action = ("PASS", None, None)


class _RolloutWrapper(Agent):
    """Wraps a playout policy: optionally plays one forced first action (the
    candidate being evaluated), then delegates every decision to the policy. Keeps
    the inner policy's loop/gs in sync with its own (which GameLoop injects)."""

    name = "rollout-wrapper"

    def __init__(self, player, policy: Agent, first_action: Optional[Action] = None):
        super().__init__(player)
        self._policy = policy
        self._first = first_action
        self._used = first_action is None

    def _sync(self) -> None:
        self._policy.loop = getattr(self, "loop", None)
        self._policy.gs = getattr(self, "gs", None)

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._sync()
        if not self._used:
            self._used = True
            return self._first  # PASS candidate → ends the action phase immediately
        return self._policy.decide_action(opponent, cards_played)

    def decide_mulligan(self) -> list:
        self._sync()
        return self._policy.decide_mulligan()

    def decide_showdown_action(self, opponent, bf_idx: int) -> Action:
        self._sync()
        return self._policy.decide_showdown_action(opponent, bf_idx)

    def decide_reaction(self, opponent, chain) -> Action:
        self._sync()
        return self._policy.decide_reaction(opponent, chain)


class MonteCarloAgent(Agent):
    name = "mc"

    def __init__(self, player, k: Optional[int] = None, rollout: Optional[str] = None,
                 max_candidates: Optional[int] = None, rng: Optional[random.Random] = None):
        super().__init__(player)
        self.k = k if k is not None else int(os.environ.get("RBSIM_MC_K", "5"))
        # simple_trade rollouts give a much stronger, faster-terminating signal
        # than uniform-random (validated: mc beats simple_trade 12/12 head-to-head).
        self.rollout = rollout or os.environ.get("RBSIM_MC_ROLLOUT", "simple_trade")
        self.max_candidates = (max_candidates if max_candidates is not None
                               else int(os.environ.get("RBSIM_MC_MAXCANDS", "10")))
        self._rng = rng  # seeded lazily from the live game rng (reproducible)

    def _ensure_rng(self) -> None:
        if self._rng is None:
            base = getattr(self, "gs", None)
            seed = base.rng.randrange(1 << 30) if base is not None else random.randrange(1 << 30)
            self._rng = random.Random(seed)

    def _policy(self, player):
        if self.rollout == "simple_trade":
            return SimpleTradeAgent(player)
        return RandomAgent(player, rng=random.Random(self._rng.randrange(1 << 30)))

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._ensure_rng()
        gs, side = self.gs, self.player.name
        other = gs.other(side)
        cands = legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)
        if len(cands) <= 1:
            return cands[0].to_engine() if cands else _PASS

        # Optionally sample a subset of candidates to bound compute (always keep PASS).
        if self.max_candidates and len(cands) > self.max_candidates:
            pass_actions = [c for c in cands if c.to_engine()[0] == "PASS"]
            rest = [c for c in cands if c.to_engine()[0] != "PASS"]
            self._rng.shuffle(rest)
            cands = pass_actions + rest[: max(1, self.max_candidates - len(pass_actions))]

        def evaluate(cand) -> float:
            return sum(self._rollout_once(side, other, cand.to_engine())
                       for _ in range(self.k)) / self.k

        # Evaluate PASS as the baseline, then the best non-PASS action. Only pass
        # if passing is STRICTLY better — otherwise act. This breaks the noisy-tie
        # case toward developing the board instead of stalling to the turn cap.
        pass_cand = next((c for c in cands if c.to_engine()[0] == "PASS"), None)
        pass_score = evaluate(pass_cand) if pass_cand is not None else -1.0

        best_action, best_action_score = None, -1.0
        for cand in cands:
            if cand is pass_cand:
                continue
            score = evaluate(cand)
            if score > best_action_score:
                best_action_score, best_action = score, cand

        if best_action is not None and best_action_score >= pass_score:
            return best_action.to_engine()
        return pass_cand.to_engine() if pass_cand is not None else _PASS

    def _rollout_once(self, side: str, other: str, cand: Action) -> float:
        from riftbound.core.loop import GameLoop  # local import avoids a cycle
        clone = self.gs.clone()
        clone.rng = random.Random(self._rng.randrange(1 << 30))
        determinize(clone, observer=side, rng=clone.rng)
        clone.get_player(side).agent = _RolloutWrapper(
            clone.get_player(side), self._policy(clone.get_player(side)), first_action=cand)
        clone.get_player(other).agent = _RolloutWrapper(
            clone.get_player(other), self._policy(clone.get_player(other)))
        result = GameLoop(clone).resume_to_completion()
        if result.winner == side:
            return 1.0
        if result.winner == "DRAW":
            return 0.5
        return 0.0

    # A search agent doesn't search the mulligan yet — keep all (baseline).
    def decide_mulligan(self) -> list:
        return []

    def decide_showdown_action(self, opponent, bf_idx: int) -> Action:
        # Showdown/reaction stay policy-simple for now; the turn-action search is
        # where the leverage is. Random-legal keeps them sound.
        opts = legal_actions(self.loop, DecisionPoint.SHOWDOWN_ACTION, self.player.name)
        return _PASS if len(opts) <= 1 else opts[0].to_engine()

    def decide_reaction(self, opponent, chain) -> Action:
        opts = legal_actions(self.loop, DecisionPoint.REACTION, self.player.name)
        return _PASS if len(opts) <= 1 else opts[0].to_engine()
