"""Porting Rust, Rengar: parità Python / Rust sui matchup con Rengar (ER e KR,
nei due posti) e con la sua sideboard nel mazzo (lettera minuscola,
riftbound/rs/mazzi.py). Richiede l'estensione riftbound_rs (maturin develop
--release in rust/rbsim-py): se manca i test falliscono, non saltano.
- partite autonome dai semi (agenti Rust random e simple_trade): tracce
  identiche evento per evento, senza nulla di registrato;
- raccolta PPO (collect.play contro collect_rs.play): esempi identici bit per bit;
- replay di una partita PPO tracciata;
- arena a lavoro fisso (bot a mano e bot coi prior): traccia e ricerche identiche."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))


def test_sideboard_list():
    """La lista di Rengar con la sideboard: 39 carte più il campione, tutta la
    sideboard dentro, niente sideboard; il file scritto è stabile."""
    from riftbound.ai.ppo.collect import RENGAR
    from riftbound.registry.cards_registry import load_deck_json
    from riftbound.rs.mazzi import deck_path
    p = deck_path("r")
    assert deck_path("R") == RENGAR and p != RENGAR
    text = p.read_text()
    assert deck_path("r").read_text() == text
    d, base = json.loads(text), json.loads(RENGAR.read_text())
    got = {c["name"]: c["count"] for c in d["cards"]}
    assert sum(got.values()) == 39 and d["sideboard"] == []
    for c in base["sideboard"]:
        assert got[c["name"]] >= c["count"]
    specs, _runes, champion, legend, bfs = load_deck_json(p)
    assert len(specs) == 39 and champion.name == "Rengar Trophy Hunter" and legend.name == "Rengar Pridestalker"


@pytest.mark.parametrize("seed,mu,agents", [
    (3, "ER", ("simple_trade", "simple_trade")), (4, "RE", ("random", "random")),
    (5, "KR", ("simple_trade", "random")), (6, "RK", ("random", "simple_trade")),
    (7, "Er", ("random", "random")), (8, "rK", ("simple_trade", "simple_trade")),
    # decide_mode on a declaration's copy: the trace names the real card (trace_py._to_real_any)
    (78, "Er", ("simple_trade", "random")),
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


@pytest.mark.parametrize("seed,mu,opponent", [(1, "ER", None), (2, "RK", None), (3, "KR", "simple_trade"),
                                              (4, "rE", "random"), (5, "Kr", None)])
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


# 1000011 RE: Grim Apothecary played with AMBUSH and blinked by Thrill of the Hunt while
# its play trigger is still in _trigger: `_kicker_paid` None, not absent (Card.kicker_set).
@pytest.mark.parametrize("seed,mu", [(1000003, "KR"), (1000004, "RE"), (1000011, "RE")])
def test_ppo_replay_identical(net, seed, mu):
    import diff_trace
    r = diff_trace.compare_seed(seed, "self", net, "a" if seed % 2 == 0 else "b", verbose=False, mu=mu)
    assert r["rust_error"] is None and "first_difference" not in r


@pytest.mark.parametrize("seed,mu,bot,iters", [(40000, "ER", "mano", 8), (40001, "RK", "prior", 6)])
def test_arena_python_rust(net, seed, mu, bot, iters):
    import arena_parita as ap
    r = ap.compare(seed, "a" if seed % 2 == 0 else "b", bot, iters, net if bot == "prior" else None, mu)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r["first_difference"]
    assert "search_difference" not in r, r["search_difference"]
    assert r["ricerche"] > 20


def test_perimeter(monkeypatch):
    """The Rust engine plays EK, ER and KR in both seats (lists recognised by
    their content): the arena (arena_rs.coperto) and the PPO training
    (scripts/ppo.py _motore); the sideboard list and the games against the
    hand-written bot stay on Python (Ivern, Sett: test_ivern.py, test_sett.py)."""
    import importlib.util
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import arena_rs
    from riftbound.rs.mazzi import deck_path
    for mu in ("EK", "KE", "ER", "RE", "KR", "RK"):
        assert arena_rs.coperto(mu), mu
    assert not arena_rs.coperte(deck_path("r"), DECK_OF["E"])
    spec = importlib.util.spec_from_file_location("ppo_script", ROOT / "scripts/ppo.py")
    ppo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ppo)
    monkeypatch.setenv("RBSIM_MOTORE", "rust")
    for mu, want in (("EK", "rust"), ("ER", "rust"), ("KR", "rust"), ("RE", "rust"), ("RS", "rust")):
        assert ppo._motore({"deck_a": DECK_OF[mu[0]], "deck_b": DECK_OF[mu[1]]}) == want, mu
    assert ppo._motore({"deck_a": DECK_OF["E"], "deck_b": DECK_OF["R"], "opponent": "bot"}) == "python"
    assert ppo._motore({}) == "rust"
    monkeypatch.setenv("RBSIM_MOTORE", "python")
    assert ppo._motore({"deck_a": DECK_OF["E"], "deck_b": DECK_OF["R"]}) == "python"


@pytest.mark.parametrize("case", ["thrill_gear", "brittle_deployed", "bilgewater_base", "ferrous_dies",
                                  "seat_of_power", "sunken_temple", "acceptable_losses"])
def test_position(case):
    """Rare branches (scripts/rust/posizioni_rengar.py): the same position
    played by Python and by Rust gives the same trace, and the branch runs."""
    import posizioni_rengar as P
    r = P.compare(case)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r.get("first_difference")
    assert r["osservazioni"]["ok"], r["osservazioni"]
