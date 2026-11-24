"""Porting Rust, Sett: parità Python / Rust sui matchup con Sett (ES, KS, RS, IS,
nei due posti) e con la sua sideboard nel mazzo (lettera minuscola,
riftbound/rs/mazzi.py). Richiede l'estensione riftbound_rs (maturin develop
--release in rust/rbsim-py): se manca i test falliscono, non saltano.
- partite autonome dai semi (agenti Rust random e simple_trade): tracce
  identiche evento per evento, senza nulla di registrato;
- raccolta PPO (collect.play contro collect_rs.play): esempi identici bit per bit;
- replay di partite PPO tracciate;
- arena a lavoro fisso (bot a mano e bot coi prior): traccia e ricerche identiche;
- posizioni mirate (scripts/rust/posizioni_sett.py) e perimetro."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))


def test_sideboard_list():
    """La lista di Sett con la sideboard: 39 carte più il campione, tutta la
    sideboard dentro, niente sideboard; il file scritto è stabile."""
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.registry.cards_registry import load_deck_json
    from riftbound.rs.mazzi import deck_path
    sett = DECK_OF["S"]
    p = deck_path("s")
    assert deck_path("S") == sett and p != sett
    text = p.read_text()
    assert deck_path("s").read_text() == text
    d, base = json.loads(text), json.loads(Path(sett).read_text())
    got = {c["name"]: c["count"] for c in d["cards"]}
    assert sum(got.values()) == 39 and d["sideboard"] == []
    for c in base["sideboard"]:
        assert got[c["name"]] >= c["count"]
    specs, _runes, champion, legend, _bfs = load_deck_json(p)
    assert len(specs) == 39 and champion.name == "Sett Kingpin" and legend.name == "Sett The Boss"


@pytest.mark.parametrize("seed,mu,agents", [
    (1, "ES", ("random", "random")), (2, "SE", ("random", "random")), (3, "KS", ("simple_trade", "simple_trade")),
    (4, "SR", ("random", "simple_trade")), (5, "IS", ("simple_trade", "random")),
    (7, "Es", ("random", "random")), (8, "sK", ("simple_trade", "simple_trade")), (9, "Is", ("simple_trade", "random")),
])
def test_autonomous_game(seed, mu, agents):
    import autonome
    r = autonome.compare(seed, {"A": agents[0], "B": agents[1]}, "a" if seed % 2 == 0 else "b", mu)
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


@pytest.mark.parametrize("seed,mu,opponent", [(1, "ES", None), (2, "SK", None), (3, "RS", "simple_trade"),
                                              (4, "sI", "random"), (5, "Rs", None)])
def test_ppo_examples_identical(net, seed, mu, opponent):
    import parita_ppo
    from riftbound.ai.ppo import collect
    from riftbound.rs import collect_rs
    from riftbound.rs.mazzi import decks
    da, db = decks(mu)
    nets = {"A": net, "B": None if opponent else net}
    learners = {"A": True, "B": not opponent}
    py = collect.play(seed, nets, learners, sample=True, opponent=opponent, deck_a=da, deck_b=db)
    rs = collect_rs.play(seed, nets, learners, sample=True, opponent=opponent, deck_a=da, deck_b=db)
    assert parita_ppo.first_record_difference(py, rs) is None
    assert (py["winner"], py["turns"], dict(py["counts"])) == (rs["winner"], rs["turns"], dict(rs["counts"]))


@pytest.mark.parametrize("seed,mu", [(1000001, "SE"), (1000002, "KS"), (1000003, "IS")])
def test_ppo_replay_identical(net, seed, mu):
    import diff_trace
    r = diff_trace.compare_seed(seed, "self", net, "a" if seed % 2 == 0 else "b", verbose=False, mu=mu)
    assert r["rust_error"] is None and "first_difference" not in r


@pytest.mark.parametrize("seed,mu,bot,iters", [(40000, "ES", "mano", 8), (40001, "SR", "prior", 6)])
def test_arena_python_rust(net, seed, mu, bot, iters):
    import arena_parita as ap
    r = ap.compare(seed, "a" if seed % 2 == 0 else "b", bot, iters, net if bot == "prior" else None, mu)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r["first_difference"]
    assert "search_difference" not in r, r["search_difference"]
    assert r["ricerche"] > 20


def test_perimeter(monkeypatch):
    """The Rust engine plays the five lists (Evelynn, Kha'Zix, Rengar, Ivern,
    Sett) among them, in both seats (lists recognised by their content): the
    arena and the PPO training; the sideboard lists and the games against the
    hand-written bot stay on Python."""
    import importlib.util
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import arena_rs
    from riftbound.rs.mazzi import deck_path
    for mu in ("ES", "SE", "KS", "SK", "RS", "SR", "IS", "SI"):
        assert arena_rs.coperto(mu), mu
    assert not arena_rs.coperte(deck_path("s"), DECK_OF["E"])
    spec = importlib.util.spec_from_file_location("ppo_script", ROOT / "scripts/ppo.py")
    ppo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ppo)
    monkeypatch.setenv("RBSIM_MOTORE", "rust")
    for mu in ("ES", "SK", "RS", "IS"):
        assert ppo._motore({"deck_a": DECK_OF[mu[0]], "deck_b": DECK_OF[mu[1]]}) == "rust", mu
    assert ppo._motore({"deck_a": DECK_OF["S"], "deck_b": DECK_OF["I"], "opponent": "bot"}) == "python"


@pytest.mark.parametrize("case", ["decree_gear", "sett_save", "monastery"])
def test_position(case):
    """Rare branches (scripts/rust/posizioni_sett.py): the same position
    played by Python and by Rust gives the same trace, and the branch runs."""
    import posizioni_sett as P
    r = P.compare(case)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r.get("first_difference")
    assert r["osservazioni"]["ok"], r["osservazioni"]
