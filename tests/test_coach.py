"""Coach mode: the net searches, a coach decides; coached decisions are saved as
training examples. torch-gated."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.coach import CoachSession, load_coach_examples  # noqa: E402
from riftbound.ai.encoding import ACTION_DIM, OBS_DIM  # noqa: E402
from riftbound.ai.net import RiftboundNet, save_checkpoint  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ZED = REPO / "riftbound" / "data" / "decks" / "precon_zed.json"
SHEN = REPO / "riftbound" / "data" / "decks" / "precon_shen.json"


def _session(tmp_path) -> CoachSession:
    torch.manual_seed(0)
    save_checkpoint(RiftboundNet(), tmp_path / "net.pt")
    return CoachSession(tmp_path / "net.pt", tmp_path / "coach", iterations=4)


def _play(session: CoachSession, pick, timeout: float = 120.0) -> None:
    """Answer every request with pick(pending) until the game is over."""
    end = time.time() + timeout
    while time.time() < end:
        st = session.state()
        if st["status"] == "over":
            return
        if st["status"] == "waiting" and st["pending"] is not None:
            session.answer(pick(st["pending"]))
        time.sleep(0.005)
    raise AssertionError("the coached game didn't end")


def test_a_coached_game_saves_its_decisions(tmp_path):
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="A", opponent="simple_trade", seed=3)
    seen = []

    def pick(pending):
        seen.append(pending["type"])
        if pending["type"] == "choice":
            return {"option": pending["default"]}
        # Mostly the net's move; now and then the last legal action instead.
        if len(seen) % 4 == 0:
            return {"action": len(pending["actions"]) - 1}
        return {"suggestion": 0}

    _play(session, pick)
    st = session.state()
    assert st["result"] and "error" not in st["result"], st["result"]
    assert "decision" in seen
    files = list((tmp_path / "coach").glob("coach_*.npz"))
    assert len(files) == 1
    examples = load_coach_examples(tmp_path / "coach")
    assert len(examples) == st["decisions"] > 0
    for e in examples:
        assert e["state"].shape == (OBS_DIM,) and e["policy"].shape == (ACTION_DIM,)
        assert e["policy"].sum() == 1.0 and e["mask"][e["policy"].argmax()]
        assert e["z"] in (-1.0, 0.0, 1.0)
    assert st["corrections"] > 0
    assert st["observation"]["my_hand"] is not None and st["log"]


def test_an_abandoned_game_saves_nothing_and_a_report_is_kept(tmp_path):
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="B", opponent="simple_trade", seed=5)
    end = time.time() + 60
    while session.state()["status"] != "waiting" and time.time() < end:
        time.sleep(0.005)
    path = session.report("Questo Shen non dovrebbe poter attaccare")
    assert path.exists() and "Shen" in path.read_text(encoding="utf-8")
    session.abandon()
    while session.state()["status"] != "over" and time.time() < end + 60:
        time.sleep(0.01)
    assert session.state()["status"] == "over"
    assert not list((tmp_path / "coach").glob("coach_*.npz"))


def test_training_mixes_in_the_coached_decisions(tmp_path):
    import json
    from riftbound.ai.selfplay import train
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="A", opponent="simple_trade", seed=3)
    _play(session, lambda p: {"option": p["default"]} if p["type"] == "choice" else {"suggestion": 0})
    net = RiftboundNet()
    train(net, [ZED, SHEN], iterations=1, games_per_iter=1, mcts_iters=2, batch_size=8,
          checkpoint=tmp_path / "run" / "net.pt", log_path=tmp_path / "log.jsonl", workers=0,
          eval_every=0, max_turns=8, pause=0, device=torch.device("cpu"),
          coach_dir=tmp_path / "coach", coach_fraction=0.25, log=lambda *a, **k: None)
    record = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[-1])
    assert record["coached"] == session.state()["decisions"] > 0
