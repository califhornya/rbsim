"""RL Chunk 4: self-play generation + training loop. torch-gated (runs after
`uv sync --extra rl`). Tiny budgets — asserts the pipeline works, not strength."""

from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

import numpy as np  # noqa: E402

from riftbound.ai.encoding import ACTION_DIM, OBS_DIM  # noqa: E402
from riftbound.ai.net import RiftboundNet  # noqa: E402
from riftbound.ai.selfplay import play_selfplay_game, run_training, train_step  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"


def test_selfplay_generates_labeled_examples():
    torch.manual_seed(0)
    net = RiftboundNet()
    ex = play_selfplay_game(net, KENNEN, ORNN, seed=1, iterations=4, max_turns=12)
    assert len(ex) > 0
    for e in ex:
        assert e["state"].shape == (OBS_DIM,)
        assert e["policy"].shape == (ACTION_DIM,)
        assert e["mask"].shape == (ACTION_DIM,)
        assert e["player"] in ("A", "B")
        assert e["z"] in (-1.0, 0.0, 1.0)
        # policy mass sits only on legal slots.
        assert float(e["policy"][~e["mask"]].sum()) < 1e-6


def test_train_step_updates_params_and_finite_loss():
    torch.manual_seed(0)
    net = RiftboundNet()
    ex = play_selfplay_game(net, KENNEN, ORNN, seed=2, iterations=4, max_turns=12)
    assert ex
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    before = [p.detach().clone() for p in net.parameters()]
    stats = train_step(net, opt, ex)
    assert np.isfinite(stats["loss"])
    assert stats["policy_loss"] >= 0 and stats["value_loss"] >= 0
    after = list(net.parameters())
    assert any(not torch.equal(b, a) for b, a in zip(before, after))  # learned something


def test_run_training_smoke(tmp_path):
    torch.manual_seed(0)
    net = RiftboundNet()
    ckpt = tmp_path / "net.pt"
    run_training(net, KENNEN, ORNN, iterations=1, games_per_iter=1, mcts_iters=4,
                 train_steps=2, batch_size=4, checkpoint=ckpt, seed=0,
                 device=torch.device("cpu"), log=lambda *a, **k: None)
    assert ckpt.exists()
