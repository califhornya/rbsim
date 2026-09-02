"""Learned mulligan (NetGuidedMCTSAgent.decide_mulligan) + learned battlefield
selection (pregame.py). torch-gated. Uses a random net → asserts the decisions are
VALID and net-driven/deterministic, not optimal (optimality comes from training)."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.net import RiftboundNet  # noqa: E402
from riftbound.ai.net_mcts import NetGuidedMCTSAgent  # noqa: E402
from riftbound.ai.pregame import (  # noqa: E402
    battlefield_values,
    choose_battlefield,
    make_net_bf_chooser,
)
from riftbound.core.game_factory import build_game, deck_battlefield_names  # noqa: E402
from riftbound.core.loop import GameLoop  # noqa: E402
from riftbound.core.match import play_match  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"


def test_learned_mulligan_returns_valid_subset():
    torch.manual_seed(0)
    net = RiftboundNet()
    gs = build_game(game_seed=1, deck_a_path=KENNEN, deck_b_path=ORNN,
                    ai_a=None, ai_b="simple_trade", first_player="a")
    agent = NetGuidedMCTSAgent(gs.A, net, iterations=1, rng=random.Random(0),
                               mulligan_samples=2)
    gs.A.agent = agent
    loop = GameLoop(gs)
    # Deal an opening hand (draw 4) without running the engine's own mulligan.
    for _ in range(4):
        gs.A.draw()
    ret = agent.decide_mulligan()
    assert isinstance(ret, list)
    assert len(ret) <= 2                       # §117 cap
    assert len(set(ret)) == len(ret)           # no duplicate indices
    assert all(0 <= i < len(gs.A.hand) for i in ret)


def test_battlefield_values_and_choice_valid():
    torch.manual_seed(0)
    net = RiftboundNet()
    names = deck_battlefield_names(KENNEN)
    vals = battlefield_values(net, KENNEN, ORNN, "A", seed=3)
    assert set(vals) == set(names)
    assert all(-1.0 <= v <= 1.0 for v in vals.values())
    choice = choose_battlefield(net, KENNEN, ORNN, "A", seed=3)
    assert choice in names
    # Deterministic for a fixed net + seed.
    assert choice == choose_battlefield(net, KENNEN, ORNN, "A", seed=3)


def test_net_bf_chooser_in_match_respects_availability():
    torch.manual_seed(0)
    net = RiftboundNet()
    chooser = make_net_bf_chooser(net, KENNEN, ORNN, seed=0)
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=5,
                     bf_chooser=chooser)
    assert res.winner in ("A", "B", "DRAW")
    a_used = [g.bf_a for g in res.games]
    b_used = [g.bf_b for g in res.games]
    assert len(a_used) == len(set(a_used))     # no reuse
    assert len(b_used) == len(set(b_used))
    for g in res.games:
        assert g.bf_a in deck_battlefield_names(KENNEN)
        assert g.bf_b in deck_battlefield_names(ORNN)
