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


def test_a_stop_file_ends_the_run(tmp_path):
    torch.manual_seed(0)
    net = RiftboundNet()
    (tmp_path / "STOP").write_text("")
    logs = []
    run_training(net, KENNEN, ORNN, iterations=3, games_per_iter=1, mcts_iters=2,
                 train_steps=1, batch_size=4, checkpoint=tmp_path / "net.pt", seed=0,
                 device=torch.device("cpu"), log=logs.append)
    assert sum(1 for line in logs if line.startswith("[iter")) == 1


def test_training_keeps_a_copy_at_each_evaluation_and_the_best(tmp_path):
    from riftbound.ai.selfplay import train
    torch.manual_seed(0)
    net = RiftboundNet()
    train(net, [KENNEN, ORNN], iterations=2, games_per_iter=1, mcts_iters=2, batch_size=4,
          checkpoint=tmp_path / "net.pt", log_path=tmp_path / "log.jsonl", workers=0,
          eval_every=1, eval_games=1, eval_vs=("random",), max_turns=8, pause=0,
          device=torch.device("cpu"), log=lambda *a, **k: None)
    assert (tmp_path / "net_0001.pt").exists() and (tmp_path / "net_0002.pt").exists()
    assert (tmp_path / "net_best.pt").exists()
    lines = (tmp_path / "log.jsonl").read_text().splitlines()
    import json
    rates = [json.loads(line)["lr"] for line in lines]
    assert rates[0] > rates[1]                       # the learning rate decays
