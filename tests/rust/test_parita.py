"""Porting Rust: parità Python / Rust su partite EK intere. Richiede
l'estensione riftbound_rs (maturin develop --release in rust/rbsim-py): se
manca i test falliscono, non saltano.
- partite autonome dai semi (agenti Rust random e simple_trade): tracce
  identiche evento per evento, senza nulla di registrato;
- raccolta PPO (collect.play contro collect_rs.play): esempi identici bit per bit;
- replay di una partita PPO tracciata: identica evento per evento."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))


def test_extension_loaded():
    import riftbound_rs
    from riftbound.rs import rust_bridge as rb
    assert rb.available() and len(rb.registry()) > 1000
    assert hasattr(riftbound_rs.Game, "set_ppo_agent")


@pytest.mark.parametrize("seed,agents", [(3, ("simple_trade", "simple_trade")), (79, ("simple_trade", "simple_trade")),
                                         (5, ("random", "random")), (6, ("simple_trade", "random"))])
def test_autonomous_game(seed, agents):
    import autonome
    r = autonome.compare(seed, {"A": agents[0], "B": agents[1]}, "a" if seed % 2 == 0 else "b")
    assert r["rust_error"] is None
    assert "first_difference" not in r, r.get("first_difference")
    assert r["py"] == r["rs"]


@pytest.fixture(scope="module")
def net():
    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(1)
    return PPONet().eval()


@pytest.mark.parametrize("seed,opponent", [(59, None), (2, None), (7, "simple_trade"), (8, "random")])
def test_ppo_examples_identical(net, seed, opponent):
    import parita_ppo
    from riftbound.ai.ppo import collect
    from riftbound.rs import collect_rs
    nets = {"A": net, "B": None if opponent else net}
    learners = {"A": True, "B": not opponent}
    py = collect.play(seed, nets, learners, sample=True, opponent=opponent)
    rs = collect_rs.play(seed, nets, learners, sample=True, opponent=opponent)
    assert parita_ppo.first_record_difference(py, rs) is None
    assert (py["winner"], py["turns"], dict(py["counts"])) == (rs["winner"], rs["turns"], dict(rs["counts"]))


def test_ppo_replay_identical(net):
    import diff_trace
    r = diff_trace.compare_seed(1000003, "self", net, "b", verbose=False)
    assert r["rust_error"] is None and "first_difference" not in r
