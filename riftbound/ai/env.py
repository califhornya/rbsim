"""RiftboundEnv — a gym-style single-agent reinforcement-learning environment
(Stage 1 toward self-play).

The learner controls one seat; the opponent plays a fixed policy from the agent
registry (``simple_trade`` / ``mc`` / ``ismcts`` / ``random`` / …). Each ``step``
advances the real game to the learner's next decision and returns the same
information-set ``Observation`` the web/UI sees (no hidden-info leak) plus the
legal actions at that point. Reward is sparse: 0 during play, then +1 / -1 / 0 for
a win / loss / draw at the end (from the learner's perspective).

It is a thin wrapper over the existing, tested primitives:
- :class:`SessionDriver` (drivers.py) runs the ordinary game loop on a background
  thread and surfaces one :class:`DecisionRequest` at a time — exactly the
  step/observe/act cadence an RL env needs, with no engine rewrite.
- :func:`build_game` (game_factory.py) seeds the game; :class:`Observation`
  (decisions.py) is the per-seat view; :func:`legal_actions` gates moves.

Usage::

    env = RiftboundEnv(deck_a_path=A, deck_b_path=B, agent_side="A", opponent="mc")
    obs, info = env.reset(seed=0)
    while not info["done"]:
        action = my_policy(obs, info["legal_actions"])   # a GameAction, tuple,
                                                          # or (mulligan) list[int]
        obs, reward, done, info = env.step(action)

**Deferred (see PROJECT_STATE / KNOWN_ISSUES) — this is the env skeleton, not the
whole learner:**
- **Tensor encoding.** ``obs`` is the structured :class:`Observation`; a fixed-size
  numeric encoding (for a neural net) is future work. ``info["decision_point"]``
  tells the policy which of TURN_ACTION / MULLIGAN / SHOWDOWN_ACTION / REACTION it
  faces (a mulligan action is a ``list[int]`` of hand indices, not a GameAction).
- **Policy / value network + network-guided MCTS + the self-play training loop.**
- **True self-play** (both seats the learning policy sharing weights) needs a
  two-controller driver; this env is single-agent-vs-fixed, the standard first step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from riftbound.core.decisions import DecisionRequest, GameAction, Observation
from riftbound.core.drivers import SessionDriver
from riftbound.core.game_factory import build_game


class RiftboundEnv:
    def __init__(
        self,
        *,
        deck_a_path: Path,
        deck_b_path: Path,
        agent_side: str = "A",
        opponent: str = "simple_trade",
        seed: int = 0,
        victory_score: int = 8,
        max_turns: int = 40,
        first_player: str = "random",
    ):
        if agent_side not in ("A", "B"):
            raise ValueError("agent_side must be 'A' or 'B'")
        self.deck_a_path = deck_a_path
        self.deck_b_path = deck_b_path
        self.agent_side = agent_side
        self.opponent = opponent
        self.seed = seed
        self.victory_score = victory_score
        self.max_turns = max_turns
        self.first_player = first_player

        self._driver: Optional[SessionDriver] = None
        self._pending: Optional[DecisionRequest] = None

    # -- lifecycle -----------------------------------------------------------

    def reset(self, seed: Optional[int] = None) -> tuple[Observation, dict]:
        """Start a fresh game and advance to the learner's first decision."""
        if seed is not None:
            self.seed = seed
        opp_side = "B" if self.agent_side == "A" else "A"
        # The opponent seat gets a fixed policy; the learner's seat is driven
        # remotely (SessionDriver.make_remote installs a RemoteAgent there).
        ai_a = self.opponent if opp_side == "A" else None
        ai_b = self.opponent if opp_side == "B" else None
        gs = build_game(
            game_seed=self.seed,
            deck_a_path=self.deck_a_path, deck_b_path=self.deck_b_path,
            ai_a=ai_a, ai_b=ai_b,
            victory_score=self.victory_score, max_turns=self.max_turns,
            first_player=self.first_player,
        )
        self._driver = SessionDriver(gs)
        self._driver.make_remote(self.agent_side)
        self._driver.start()
        self._pending = self._driver.pending()
        return self._observe(), self._info(0.0, False)

    def step(self, action: Any) -> tuple[Observation, float, bool, dict]:
        """Submit the learner's action and advance to its next decision (or the
        game end). ``action`` is a GameAction / raw tuple, or a ``list[int]`` of
        hand indices for a MULLIGAN decision."""
        if self._driver is None:
            raise RuntimeError("call reset() before step()")
        if self._driver.is_over():
            raise RuntimeError("game is over; call reset()")
        self._driver.submit(action)
        self._pending = self._driver.pending()
        if self._driver.is_over():
            reward = self._terminal_reward()
            return self._observe(), reward, True, self._info(reward, True)
        return self._observe(), 0.0, False, self._info(0.0, False)

    # -- accessors -----------------------------------------------------------

    def legal_actions(self) -> list[GameAction]:
        """Legal actions at the current decision. Empty for a MULLIGAN point (the
        action there is a ``list[int]`` of hand indices to return, up to two)."""
        return list(self._pending.legal_actions) if self._pending is not None else []

    @property
    def done(self) -> bool:
        return self._driver is not None and self._driver.is_over()

    @property
    def result(self):
        return self._driver.result if self._driver is not None else None

    # -- internals -----------------------------------------------------------

    def _observe(self) -> Observation:
        if self._pending is not None:
            return self._pending.observation
        # Terminal: no pending decision — snapshot the (now-stable) final state.
        return Observation.from_state(self._driver.gs, self.agent_side)

    def _terminal_reward(self) -> float:
        res = self._driver.result
        if res is None or res.winner == "DRAW":
            return 0.0
        return 1.0 if res.winner == self.agent_side else -1.0

    def _info(self, reward: float, done: bool) -> dict:
        point = self._pending.point.value if self._pending is not None else None
        return {
            "done": done,
            "reward": reward,
            "decision_point": point,
            "legal_actions": self.legal_actions(),
            "result": self._driver.result if (done and self._driver) else None,
        }
