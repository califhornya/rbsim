"""The PPO agent's Python half on the Rust engine (porting, F5): Rust builds
each question (the real game's observation and turn, the options'
descriptors, the context: riftbound_rs, rust/rbsim-py/src/ppo.rs); AskPPO
does what PPOAgent._ask does with them: the net's forward, the draw from the
agent's torch generator (or the highest score), the example for PPO.
Rust calls it only for menus of two options or more, as PPOAgent._ask
draws nothing below two."""
from __future__ import annotations

from typing import Optional

import numpy as np
import torch


class AskPPO:
    def __init__(self, net, seat: str, sample: bool = True, seed: int = 0, record: Optional[list] = None):
        self.net = net
        self.seat = seat
        self.sample = sample
        self.gen = torch.Generator().manual_seed(seed)
        self.record = record

    def __call__(self, x, q: int, src: int, c, otype, ocards, ofeats, turn: int) -> int:
        n = len(otype)
        with torch.no_grad():
            logits, v = self.net(torch.as_tensor(x[None]), torch.tensor([q]), torch.tensor([src]),
                                 torch.as_tensor(c[None]), torch.as_tensor(otype[None]),
                                 torch.as_tensor(ocards[None]), torch.as_tensor(ofeats[None]),
                                 torch.ones(1, n, dtype=torch.bool))
            logp = torch.log_softmax(logits[0], dim=0)
            if self.sample:
                i = int(torch.multinomial(logp.exp(), 1, generator=self.gen).item())
            else:
                i = int(torch.argmax(logp).item())
        if self.record is not None:
            self.record.append({"x": x.astype(np.float16), "q": q, "src": src, "ctx": c, "otype": otype,
                                "ocards": ocards, "ofeats": ofeats.astype(np.float16), "a": i,
                                "logp": float(logp[i]), "v": float(v[0]), "seat": self.seat, "turn": turn})
        return i
