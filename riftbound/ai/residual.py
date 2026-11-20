"""The value of step 2 (20/11, docs/bot/RETE.md): the hand-written value
`table_value` plus a learned correction, in the hand-written bot's search
(equal priors, backup best, the move with the highest Q).

The correction is a small RiftboundNet's value r in (-1, 1), added to the
hand-written value in tanh space: V = tanh(atanh(tv) + atanh(r)) =
(tv + r) / (1 + tv * r). With the value head at zero (r = 0) V is exactly
`table_value`: the net starts as the bot and learns only what to change.

It learns from sibling moves (scripts/passo2.py): at a root, two or three
moves each played to the end in the same 8 worlds; the net sees the position
after each move and learns both its result and the difference between
siblings (the move to choose)."""
from __future__ import annotations

import random
from typing import Optional

import numpy as np

from riftbound.ai.encoding import encode_observation
from riftbound.ai.handwritten import HandwrittenAgent, table_value
from riftbound.core.decisions import Observation


def combine(tv, r):
    """tanh(atanh(tv) + atanh(r)), for floats or tensors."""
    return (tv + r) / (1 + tv * r)


def make_net(hidden: tuple = (64,), card_dim: int = 16):
    """A small net whose correction starts at zero."""
    import torch.nn as nn
    from riftbound.ai.net import RiftboundNet
    net = RiftboundNet(hidden=hidden, card_dim=card_dim)
    nn.init.zeros_(net.value_head.weight)
    nn.init.zeros_(net.value_head.bias)
    return net


def correction(net, vecs: np.ndarray):
    """The net's r for a batch of encoded observations (numpy [B, OBS_DIM])."""
    import torch
    with torch.no_grad():
        _, v = net(torch.as_tensor(np.asarray(vecs, dtype=np.float32)))
    return v.squeeze(1).numpy()


class ResidualAgent(HandwrittenAgent):
    """The hand-written bot whose leaves are valued table_value + correction."""
    name = "residual"

    def __init__(self, player, net, iterations: int = 100, rng: Optional[random.Random] = None,
                 budget: Optional[float] = None, **kw):
        super().__init__(player, iterations=iterations, rng=rng, budget=budget, **kw)
        self.value_net = net.eval()

    def _value(self, clone, side) -> float:
        obs = Observation.from_state(clone, side)
        r = float(correction(self.value_net, encode_observation(obs)[None])[0])
        return float(combine(table_value(obs), r))

    def _evaluate(self, clone, side, legal_ga):
        ts = [a.to_engine() for a in legal_ga]
        u = 1.0 / max(1, len(ts))
        return {t: u for t in ts}, self._value(clone, side)

    def _net_value(self, clone, side):
        return self._value(clone, side)
    _value_only = _net_value
