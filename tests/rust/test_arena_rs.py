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


def test_arena_mista_lockstep():
    """arena_mista.game: the Python copy and the Rust copy of one game in
    step (each side's timed search repeated by the other copy with its count)
    stay the same game: trace and every search identical."""
    sys.path.insert(0, str(ROOT / "scripts/rust"))
    import arena_mista as AM
    for rust_seat in ("A", "B"):
        r = AM.game((70000, "a", rust_seat, "seme:1", 0.004, 0.02, True))
        assert "errore" not in r, r.get("errore")
        assert "divergenza" not in r, r["divergenza"]
        assert r["eventi"] > 50 and r["score"] in (0.0, 0.5, 1.0)
        assert any(k.startswith("rs ") for k in r["iterazioni"]) and any(k.startswith("py ") for k in r["iterazioni"])


def test_arena_mista_verdict_needs_the_whole_sample():
    """The verdict is SOSPESO unless every prescribed game is there, valid:
    a failed game (not in the rows: replayed on the next launch) or a
    divergence suspends it; one good pair out of two requested is no PROMOSSO."""
    sys.path.insert(0, str(ROOT / "scripts/rust"))
    import arena_mista as AM

    def row(seed, seat, score, **kw):
        return {"seed": seed, "rust_seat": seat, "score": score, "eventi": 100} | kw
    good = [row(1, "A", 1.0), row(1, "B", 1.0)]
    assert AM.valuta(good, range(1, 3), 2, 0.47)["esito"] == "SOSPESO"          # pair 2 failed: missing
    v = AM.valuta(good + [row(2, "A", 1.0), row(2, "B", 0.5)], range(1, 3), 2, 0.47)
    assert v["esito"] == "PROMOSSO" and v["completo"]
    div = {"seed": 2, "rust_seat": "B", "divergenza": [{"passo": "x"}]}
    assert AM.valuta(good + [row(2, "A", 1.0), div], range(1, 3), 2, 0.47)["esito"] == "SOSPESO"
    assert AM.valuta(good + [row(2, "A", 1.0), row(2, "B", 1.0, divergenza=[{}])], range(1, 3), 2,
                     0.47)["esito"] == "SOSPESO"
    # An explained divergence only in the searches' numbers counts; one in the trace does not.
    only_search = row(2, "B", 1.0, divergenza=[{"ricerca": {}}])
    rows = good + [row(2, "A", 1.0), only_search]
    assert AM.valuta(rows, range(1, 3), 2, 0.47)["esito"] == "SOSPESO"
    assert AM.valuta(rows, range(1, 3), 2, 0.47, frozenset({(2, "B")}))["esito"] == "PROMOSSO"
    in_trace = row(2, "B", 1.0, divergenza=[{"traccia": {}}])
    assert AM.valuta(good + [row(2, "A", 1.0), in_trace], range(1, 3), 2, 0.47,
                     frozenset({(2, "B")}))["esito"] == "SOSPESO"


def test_arena_mista_lockstep_mismatch_is_a_divergence(monkeypatch):
    """An identity mismatch at an exchange is recorded as a divergence (not
    as an error to replay)."""
    sys.path.insert(0, str(ROOT / "scripts/rust"))
    import arena_mista as AM
    hooks = AM.Link.hooks

    def skewed(self, engine):
        before, after = hooks(self, engine)
        if engine != "rs":
            return before, after
        return (lambda info: before(info | {"turn": info["turn"] + 100})), after
    monkeypatch.setattr(AM.Link, "hooks", skewed)
    r = AM.game((70000, "a", "A", "seme:1", 0.004, 0.02, False))
    assert "divergenza" in r and "errore" not in r and "score" not in r


def test_arena_mista_resume_ignores_unchecked_rows(tmp_path):
    """Rows of a run without checks are not reused by a run with checks."""
    import json
    import subprocess
    out = tmp_path / "A.txt"
    key = {"ckpt_sha": "seme:1", "budget_rust": 0.004, "budget_python": 0.02, "regole": "6427b90"}
    with open(out.with_suffix(".jsonl"), "w") as f:
        for seat in "AB":
            f.write(json.dumps({"seed": 70000, "starter": "a", "rust_seat": seat, "score": 1.0,
                                "controlli": False} | key) + "\n")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/rust/arena_mista.py"), "--ckpt", "seme:1",
                        "--coppie", "1", "--seed0", "70000", "--budget-rust", "0.004", "--budget-python", "0.02",
                        "--workers", "1", "--out", str(out)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "ripresa" not in r.stdout and "partite verificate a ogni passo: 2" in r.stdout, r.stdout
