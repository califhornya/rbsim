"""Porting, tappa A: la ricerca dell'arena su Rust. Il bot a mano e il bot coi
prior PPO giocano la stessa partita EK su Python e su Rust, a lavoro fisso:
traccia della partita reale e ogni ricerca (menu, prior, visite, Q, mossa)
identiche. Richiede l'estensione riftbound_rs: se manca il test fallisce."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))


@pytest.mark.parametrize("seed,bot,iters", [(40000, "mano", 8), (40003, "prior", 6)])
def test_arena_python_rust(seed, bot, iters):
    import riftbound_rs  # noqa: F401
    import arena_parita as ap
    net = None
    if bot == "prior":
        import torch
        from riftbound.ai.ppo.model import PPONet
        torch.manual_seed(1)
        net = PPONet().eval()
    r = ap.compare(seed, "a" if seed % 2 == 0 else "b", bot, iters, net)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r["first_difference"]
    assert "search_difference" not in r, r["search_difference"]
    assert r["ricerche"] > 20


def test_arena_rs_game_budget():
    """arena_rs.game: a game under a CPU budget, the arena's return shape."""
    import torch
    from riftbound.ai.ppo.model import PPONet, save
    from riftbound.rs import arena_rs
    torch.manual_seed(1)
    path = ROOT / "tests/rust/__pycache__/net_arena_rs.pt"
    path.parent.mkdir(exist_ok=True)
    save(PPONet(), path)
    r = arena_rs.game((40000, "a", "A", "prior_ppo", str(path), "mano", None, "EK", 0.02, 0.02))
    assert r[0] == 40000 and r[3] in (0.0, 0.5, 1.0)
    assert r[4] and min(r[4]) >= 1 and r[5]
    with pytest.raises(ValueError):
        arena_rs.game((40000, "a", "A", "mano", None, "mano", None, "ER", 0.02, 0.02))


def test_arena_rs_frees_agents():
    """A finished game, dropped, frees its search agents (no reference cycle
    between an agent and the choosers it puts on the loop)."""
    import gc
    import riftbound_rs
    from riftbound.rs import arena_rs
    gc.collect()
    before = riftbound_rs.live_search_agents()
    for seed in (40000, 40001):
        arena_rs.game((seed, "a" if seed % 2 == 0 else "b", "A", "mano", None, "mano", None, "EK", 0.01, 0.01))
    gc.collect()
    assert riftbound_rs.live_search_agents() == before
