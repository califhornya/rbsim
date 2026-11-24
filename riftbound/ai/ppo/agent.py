"""The PPO agent (21/11): every real choice by the net, sampled while training,
the highest score when measuring.

- main phase, reactions, showdowns: legal_actions, one option per action;
- the mulligan: one menu of subsets (features.mulligan_menu);
- every GameLoop.choose (targets, "you may", orders, destinations...):
  through PPOChooser, the loop's chooser, which asks the agent of the side
  that chooses. A spell's declared choices are asked once, on the copy they
  are declared on, and replayed as it resolves (GameLoop._declare_choices):
  one example each. The state is always the real game's, seen by the decider
  (a declaration's copy may already have run later instructions).

A menu with one option is not a decision: no example, no draw from the
agent's generator. With `record` a list, each decision appends an example:
state, question, options, the option played, its log-probability, the value.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np
import torch

from riftbound.ai.encoding import card_id, encode_observation
from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.ai.ppo import features as F
from riftbound.core.decisions import DecisionPoint, Observation
from riftbound.core.legality import legal_actions

_PASS = ("PASS", None, None)


def _arrays(descs: list) -> tuple:
    otype = np.array([d.type for d in descs], dtype=np.int64)
    ocards = np.array([d.cards for d in descs], dtype=np.int64)
    ofeats = np.stack([d.feats for d in descs]).astype(np.float32)
    return otype, ocards, ofeats


class PPOAgent(SimpleTradeAgent):
    def __init__(self, player, net, sample: bool = True, seed: int = 0, record: Optional[list] = None):
        super().__init__(player)
        self.net = net
        self.sample = sample
        self.gen = torch.Generator().manual_seed(seed)
        self.record = record
        self.counts: Counter = Counter()
        self._many = (None, 0)

    # -- one decision --------------------------------------------------------

    def _ask(self, question: str, descs: list, source=None, ctx=None) -> int:
        self.counts[question] += 1
        if len(descs) < 2:
            return 0
        self.counts["decisioni"] += 1
        self.counts["opzioni"] += len(descs)
        self.counts["opzioni sconosciute"] += sum(d.unknown for d in descs)
        side = self.player.name
        x = encode_observation(Observation.from_state(self.loop.gs, side))
        q = F.question_of(question)
        src = card_id(getattr(source, "name", None)) if source is not None else 0
        c = ctx if ctx is not None else F.context(len(descs))
        otype, ocards, ofeats = _arrays(descs)
        with torch.no_grad():
            logits, v = self.net(torch.as_tensor(x[None]), torch.tensor([q]), torch.tensor([src]),
                                 torch.as_tensor(c[None]), torch.as_tensor(otype[None]),
                                 torch.as_tensor(ocards[None]), torch.as_tensor(ofeats[None]),
                                 torch.ones(1, len(descs), dtype=torch.bool))
            logp = torch.log_softmax(logits[0], dim=0)
            if self.sample:
                i = int(torch.multinomial(logp.exp(), 1, generator=self.gen).item())
            else:
                i = int(torch.argmax(logp).item())
        if self.record is not None:
            self.record.append({"x": x.astype(np.float16), "q": q, "src": src, "ctx": c, "otype": otype,
                                "ocards": ocards, "ofeats": ofeats.astype(np.float16), "a": i,
                                "logp": float(logp[i]), "v": float(v[0]), "seat": side,
                                "turn": self.loop.gs.turn})
        return i

    def _menu(self, point, question: str):
        side = self.player.name
        legal = legal_actions(self.loop, point, side)
        if not legal:
            return _PASS
        descs = [F.describe_action(self.loop, side, a) for a in legal]
        return legal[self._ask(question, descs)].to_engine()

    def decide_action(self, opponent, cards_played: int = 0):
        return self._menu(DecisionPoint.TURN_ACTION, "main")

    def decide_reaction(self, opponent, chain):
        return self._menu(DecisionPoint.REACTION, "reaction")

    def decide_showdown_action(self, opponent, bf_idx: int):
        return self._menu(DecisionPoint.SHOWDOWN_ACTION, "showdown")

    def decide_mulligan(self) -> list:
        hand = self.player.hand
        menu = F.mulligan_menu(len(hand))
        descs = [F.describe_mulligan(hand, s) for s in menu]
        return menu[self._ask("mulligan", descs)]

    # The engine asks these, then offers the answer through choose (where the
    # net decides); counted to see how often an answer would stay heuristic.
    def decide_optional(self, card, effect_name: str) -> bool:
        self.counts["euristica: optional"] += 1
        return super().decide_optional(card, effect_name)

    def decide_mode(self, card, n_modes: int):
        self.counts["euristica: mode"] += 1
        return super().decide_mode(card, n_modes)

    def decide_predict_recycle(self, card) -> bool:
        self.counts["euristica: predict_recycle"] += 1
        return super().decide_predict_recycle(card)

    # -- a choice the engine routes through choose ---------------------------

    def inner(self, loop, kind: str, options: list, default: int, source) -> Optional[int]:
        from riftbound.core.loop import NO_MORE
        side = self.player.name
        # The key holds the loop and the source themselves, not their id(): a
        # declaration's copy, once freed, can leave its address to the next
        # one, which would count as the same loop (tests/test_ppo_many_key.py).
        prev = self._many[0]
        same = prev is not None and prev[0] is loop and prev[1] == kind and prev[2] is source
        made = self._many[1] + 1 if getattr(loop, "_in_many", False) and same else 0
        self._many = ((loop, kind, source), made)
        descs = [F.describe_choice(loop, side, o) for o in options]
        ctx = F.context(len(options), made=made, up_to=any(o is NO_MORE for o in options),
                        declaring=loop is not self.loop)
        if len(options) < 2:
            return None
        return self._ask(kind, descs, source=source, ctx=ctx)


class PPOChooser:
    """The loop's chooser: each choice goes to the agent of the side making it
    (the baseline for an agent that isn't a PPOAgent). Shared, not copied, by
    the copies a declaration makes of the loop."""

    def __init__(self, gs):
        self.gs = gs

    def __call__(self, loop, kind, side, options, default, source):
        agent = self.gs.get_player(side).agent
        if isinstance(agent, PPOAgent):
            return agent.inner(loop, kind, options, default, source)
        return None

    def __deepcopy__(self, memo):
        return self
