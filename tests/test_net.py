"""RL Chunk 2: PyTorch policy+value network.

These tests require the optional 'rl' extra (torch) and are SKIPPED where torch is
not installed (e.g. the light engine CI / this dev box). They run on the training
machine after `uv sync --extra rl`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")  # skip the whole module if torch is absent

from riftbound.ai.encoding import (  # noqa: E402
    ACTION_DIM,
    OBS_DIM,
    action_to_index,
    encode_observation,
    index_to_legal_action,
    legal_mask,
)
from riftbound.ai.env import RiftboundEnv  # noqa: E402
from riftbound.ai.net import (  # noqa: E402
    RiftboundNet,
    default_device,
    load_checkpoint,
    masked_log_softmax,
    predict,
    save_checkpoint,
)
from riftbound.core.decisions import DecisionPoint  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"


def test_forward_shapes_and_value_range():
    net = RiftboundNet()
    x = torch.zeros(4, OBS_DIM)
    logits, value = net(x)
    assert logits.shape == (4, ACTION_DIM)
    assert value.shape == (4, 1)
    assert torch.all(value >= -1) and torch.all(value <= 1)


def test_masked_log_softmax_zeros_illegal():
    net = RiftboundNet()
    logits = torch.randn(1, ACTION_DIM)
    mask = torch.zeros(1, ACTION_DIM, dtype=torch.bool)
    mask[0, [0, 5, 10]] = True                       # only 3 legal slots
    probs = masked_log_softmax(logits, mask).exp().squeeze(0)
    assert pytest.approx(float(probs.sum()), abs=1e-4) == 1.0
    illegal = [i for i in range(ACTION_DIM) if i not in (0, 5, 10)]
    assert float(probs[illegal].sum()) < 1e-5


def test_predict_returns_legal_distribution_and_value():
    net = RiftboundNet().to(default_device())
    env = RiftboundEnv(deck_a_path=KENNEN, deck_b_path=ORNN, agent_side="A",
                       opponent="simple_trade", seed=5)
    obs, info = env.reset()
    while info["decision_point"] == DecisionPoint.MULLIGAN.value:
        obs, _r, done, info = env.step([])
        assert not done
    mask = legal_mask(info["legal_actions"])
    probs, value = predict(net, encode_observation(obs), mask)
    assert probs.shape == (ACTION_DIM,)
    assert -1.0 <= value <= 1.0
    assert abs(probs.sum() - 1.0) < 1e-4
    # All probability sits on legal slots, and argmax maps back to a legal action.
    assert float(probs[~mask].sum()) < 1e-5
    best = int(np.argmax(probs))
    assert index_to_legal_action(best, info["legal_actions"]) is not None


def test_checkpoint_round_trip(tmp_path):
    net = RiftboundNet()
    x = torch.randn(2, OBS_DIM)
    net.eval()
    with torch.no_grad():
        before = net(x)
    p = tmp_path / "ckpt.pt"
    save_checkpoint(net, p)
    net2 = load_checkpoint(p, device=torch.device("cpu"))
    net2.eval()
    with torch.no_grad():
        after = net2(x)
    assert torch.allclose(before[0], after[0], atol=1e-6)
    assert torch.allclose(before[1], after[1], atol=1e-6)
