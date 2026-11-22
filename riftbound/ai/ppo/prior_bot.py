"""The hand-written bot guided by the PPO policy (22/11): the same search
(backup best, the move with the highest Q, table_value at the leaves), but the
priors of every expansion come from the PPO net's scores over that menu
instead of being equal (AlphaZero's use of a policy in a search). The PPO net
plays without search at 0.425 against the bot; here it only says which moves
to look at first."""
from __future__ import annotations

import random
from typing import Optional

import numpy as np
import torch

from riftbound.ai.encoding import encode_observation
from riftbound.ai.handwritten import HandwrittenAgent, table_value
from riftbound.ai.ppo import features as F
from riftbound.core.decisions import DecisionPoint, Observation

_Q = {DecisionPoint.TURN_ACTION: "main", DecisionPoint.REACTION: "reaction",
      DecisionPoint.SHOWDOWN_ACTION: "showdown"}


class PPOPriorAgent(HandwrittenAgent):
    name = "bot_prior_ppo"

    def __init__(self, player, net, rng: Optional[random.Random] = None, budget: Optional[float] = 0.4, **kw):
        super().__init__(player, rng=rng, budget=budget, **kw)
        self.ppo = net.eval()
        self._question = "main"

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        self._question = _Q.get(point, "main")
        return super().search(point, legal, cards_played=cards_played, bf_idx=bf_idx)

    def _evaluate(self, clone, side, legal_ga):
        from riftbound.core.loop import GameLoop
        obs = Observation.from_state(clone, side)
        tv = table_value(obs)
        ts = [a.to_engine() for a in legal_ga]
        if len(legal_ga) < 2:
            return {t: 1.0 for t in ts}, tv
        loop = GameLoop(clone)
        descs = [F.describe_action(loop, side, a) for a in legal_ga]
        otype = np.array([d.type for d in descs], dtype=np.int64)
        ocards = np.array([d.cards for d in descs], dtype=np.int64)
        ofeats = np.stack([d.feats for d in descs]).astype(np.float32)
        x = encode_observation(obs)
        with torch.no_grad():
            logits, _ = self.ppo(torch.as_tensor(x[None]), torch.tensor([F.question_of(self._question)]),
                                 torch.tensor([0]), torch.as_tensor(F.context(len(descs))[None]),
                                 torch.as_tensor(otype[None]), torch.as_tensor(ocards[None]),
                                 torch.as_tensor(ofeats[None]), torch.ones(1, len(descs), dtype=torch.bool))
            p = torch.softmax(logits[0], dim=0).numpy()
        priors: dict = {}
        for t, q in zip(ts, p):
            priors[t] = priors.get(t, 0.0) + float(q)
        return priors, tv
