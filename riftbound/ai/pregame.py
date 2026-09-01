"""Learned pre-game choices: battlefield selection guided by the value network
(RL Chunk: learned mulligan/battlefield).

For each battlefield a deck may bring, build the opening (deal hands + place the
battlefield via `_setup`) and score it by the net's VALUE from the chooser's seat;
pick the highest. Like the learned mulligan, this uses the trained net, so it gets
better as the net does (e.g. learning to open the right battlefield). It plugs into
`match.play_match` via `bf_chooser`.

Requires the `rl` extra (torch). Note: this scores the *opening* position; a
stronger (heavier) variant would play a few net-guided games per candidate — see
DEFERRED.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from riftbound.ai.encoding import ACTION_DIM, encode_observation
from riftbound.ai.net import RiftboundNet, predict
from riftbound.core.decisions import Observation
from riftbound.core.game_factory import build_game, deck_battlefield_names
from riftbound.core.loop import GameLoop


def _opening_value(net: RiftboundNet, deck_a: Path, deck_b: Path, side: str,
                   bf_a, bf_b, seed: int) -> float:
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b,
                    ai_a=None, ai_b=None, bf_a=bf_a, bf_b=bf_b)
    GameLoop(gs)._setup()          # deal opening hands, place legends + battlefields
    vec = encode_observation(Observation.from_state(gs, side))
    _probs, value = predict(net, vec, np.ones(ACTION_DIM, dtype=bool))
    return value


def battlefield_values(net: RiftboundNet, deck_path: Path, opp_deck_path: Path,
                       side: str, *, candidates: Optional[list] = None,
                       seed: int = 0) -> dict:
    """Net opening-value for each battlefield ``side``'s deck could bring."""
    names = candidates if candidates is not None else deck_battlefield_names(deck_path)
    deck_a, deck_b = (deck_path, opp_deck_path) if side == "A" else (opp_deck_path, deck_path)
    out: dict = {}
    for name in names:
        bf_a, bf_b = (name, None) if side == "A" else (None, name)
        out[name] = _opening_value(net, deck_a, deck_b, side, bf_a, bf_b, seed)
    return out


def choose_battlefield(net: RiftboundNet, deck_path: Path, opp_deck_path: Path,
                       side: str, *, candidates: Optional[list] = None,
                       seed: int = 0) -> Optional[str]:
    """The highest net-value battlefield among ``candidates`` (deck's options)."""
    vals = battlefield_values(net, deck_path, opp_deck_path, side,
                              candidates=candidates, seed=seed)
    return max(vals, key=vals.get) if vals else None


def make_net_bf_chooser(net: RiftboundNet, deck_a_path: Path, deck_b_path: Path,
                        *, seed: int = 0):
    """A `bf_chooser` for `match.play_match`: each seat picks its highest net-value
    battlefield among those still available (no-reuse is enforced by the harness)."""
    def chooser(side: str, available: list, game_index: int) -> Optional[str]:
        if not available:
            return None
        deck = deck_a_path if side == "A" else deck_b_path
        opp = deck_b_path if side == "A" else deck_a_path
        return choose_battlefield(net, deck, opp, side, candidates=available,
                                  seed=seed + game_index)
    return chooser
