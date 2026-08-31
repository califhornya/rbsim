"""RandomAgent — a uniform-random legal-move policy.

Two jobs:
- a weak baseline opponent, and
- the default *playout policy* for the Monte-Carlo / ISMCTS search agents (fast,
  unbiased simulation to the end of the game).

It picks uniformly among the engine's own `legal_actions` at each decision point,
so every move it makes is sound (never a no-op the engine would swallow). All
randomness flows through an injected/seeded `random.Random` for reproducibility.
"""

from __future__ import annotations

import random
from typing import Optional

from riftbound.ai.heuristics.base_agent import Action, Agent
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions

_PASS: Action = ("PASS", None, None)


class RandomAgent(Agent):
    name = "random"

    def __init__(self, player, rng: Optional[random.Random] = None):
        super().__init__(player)
        self.rng = rng or random.Random()
        # self.loop / self.gs are injected by GameLoop.__init__.

    def _pick(self, point: DecisionPoint) -> Action:
        loop = getattr(self, "loop", None)
        if loop is None:
            return _PASS
        options = legal_actions(loop, point, self.player.name)
        if not options:
            return _PASS
        return self.rng.choice(options).to_engine()

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        return self._pick(DecisionPoint.TURN_ACTION)

    def decide_mulligan(self) -> list:
        # Keep-all: mulligan search is out of scope for the playout policy.
        return []

    def decide_showdown_action(self, opponent, bf_idx: int) -> Action:
        return self._pick(DecisionPoint.SHOWDOWN_ACTION)

    def decide_reaction(self, opponent, chain) -> Action:
        return self._pick(DecisionPoint.REACTION)
