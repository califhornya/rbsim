"""Porting Rust, Ivern: parità Python / Rust sui matchup con Ivern (EI, KI, RI,
nei due posti) e con la sua sideboard nel mazzo (lettera minuscola,
riftbound/rs/mazzi.py). Richiede l'estensione riftbound_rs (maturin develop
--release in rust/rbsim-py): se manca i test falliscono, non saltano.
- partite autonome dai semi (agenti Rust random e simple_trade): tracce
  identiche evento per evento, senza nulla di registrato;
- raccolta PPO (collect.play contro collect_rs.play): esempi identici bit per bit;
- replay di partite PPO tracciate;
- arena a lavoro fisso (bot a mano e bot coi prior): traccia e ricerche identiche;
- posizioni mirate (scripts/rust/posizioni_ivern.py) e perimetro."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))


def test_sideboard_list():
    """La lista di Ivern con la sideboard: 39 carte più il campione, tutta la
    sideboard dentro, niente sideboard; il file scritto è stabile."""
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.registry.cards_registry import load_deck_json
    from riftbound.rs.mazzi import deck_path
    ivern = DECK_OF["I"]
    p = deck_path("i")
    assert deck_path("I") == ivern and p != ivern
    text = p.read_text()
    assert deck_path("i").read_text() == text
    d, base = json.loads(text), json.loads(Path(ivern).read_text())
    got = {c["name"]: c["count"] for c in d["cards"]}
    assert sum(got.values()) == 39 and d["sideboard"] == []
    for c in base["sideboard"]:
        assert got[c["name"]] >= c["count"]
    specs, _runes, champion, legend, _bfs = load_deck_json(p)
    assert len(specs) == 39 and champion.name == "Ivern Nurturer" and legend.name == "Ivern Green Father"


@pytest.mark.parametrize("seed,mu,agents", [
    # two counters on one spell: the first one's target left the chain (ChainItem.uid, chain_gone)
    (5, "EI", ("random", "random")), (1, "EI", ("random", "random")), (11, "IE", ("random", "random")),
    (3, "KI", ("simple_trade", "simple_trade")), (4, "IR", ("random", "simple_trade")),
    (7, "Ei", ("random", "random")), (8, "iK", ("simple_trade", "simple_trade")), (9, "Ri", ("simple_trade", "random")),
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


@pytest.mark.parametrize("seed,mu,opponent", [(1, "EI", None), (2, "IK", None), (3, "RI", "simple_trade"),
                                              (4, "iE", "random"), (5, "Ri", None)])
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


# 1000013 IR: a PPO choice on a declaration's copy notes control on the real
# board (Observation.from_state: bf.control()); the replay does it too.
@pytest.mark.parametrize("seed,mu", [(1000013, "IR"), (1000004, "EI"), (1000003, "KI")])
def test_ppo_replay_identical(net, seed, mu):
    import diff_trace
    r = diff_trace.compare_seed(seed, "self", net, "a" if seed % 2 == 0 else "b", verbose=False, mu=mu)
    assert r["rust_error"] is None and "first_difference" not in r


@pytest.mark.parametrize("seed,mu,bot,iters", [(40000, "EI", "mano", 8), (40001, "IR", "prior", 6)])
def test_arena_python_rust(net, seed, mu, bot, iters):
    import arena_parita as ap
    r = ap.compare(seed, "a" if seed % 2 == 0 else "b", bot, iters, net if bot == "prior" else None, mu)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r["first_difference"]
    assert "search_difference" not in r, r["search_difference"]
    assert r["ricerche"] > 20


def test_perimeter(monkeypatch):
    """The Rust engine plays Ivern's matchups (EI, KI, RI), in
    both seats (lists recognised by their content): the arena and the PPO
    training; the sideboard lists stay on Python (Sett: test_sett.py)."""
    import importlib.util
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import arena_rs
    from riftbound.rs.mazzi import deck_path
    for mu in ("EI", "IE", "KI", "IK", "RI", "IR"):
        assert arena_rs.coperto(mu), mu
    assert not arena_rs.coperte(deck_path("i"), DECK_OF["E"])
    spec = importlib.util.spec_from_file_location("ppo_script", ROOT / "scripts/ppo.py")
    ppo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ppo)
    monkeypatch.setenv("RBSIM_MOTORE", "rust")
    for mu, want in (("EI", "rust"), ("IK", "rust"), ("RI", "rust"), ("IS", "rust")):
        assert ppo._motore({"deck_a": DECK_OF[mu[0]], "deck_b": DECK_OF[mu[1]]}) == want, mu


@pytest.mark.parametrize("case", ["janna_heal", "daisy_pets", "nsf_ability"])
def test_position(case):
    """Rare branches (scripts/rust/posizioni_ivern.py): the same position
    played by Python and by Rust gives the same trace, and the branch runs."""
    import posizioni_ivern as P
    r = P.compare(case)
    assert r["rust_error"] is None
    assert "first_difference" not in r, r.get("first_difference")
    assert r["osservazioni"]["ok"], r["osservazioni"]
