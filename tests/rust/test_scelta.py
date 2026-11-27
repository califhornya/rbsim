"""Scelta finale della ricerca (SearchCore.scelta_visite, spento di default; Astra 27/11): alle decisioni di turno
la piu' visitata (pari visite: Q piu' alta, poi l'ordine del menu) invece della Q piu' alta; reazioni e resto
restano a Q piu' alta."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytest.importorskip("riftbound_rs")
torch = pytest.importorskip("torch")

from riftbound.ai.ppo.collect import DECK_OF  # noqa: E402
from riftbound.rs import arena_rs, rust_bridge as rb  # noqa: E402

ITERS = 40


def _net():
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(0)
    return PPONet().eval()


def _partita(probs, seme, scelta=None, iters=ITERS):
    g = rb.build(seme, Path(DECK_OF["E"]), Path(DECK_OF["K"]), "a", 40, "6427b90+D72-D83")
    for seat in "AB":
        g.set_search_agent(seat, iters, seme * 2 + (seat == "B"), None, probs, True)
        if scelta is not None and seat == "A":
            g.set_search_scelta(seat, scelta)
    g.set_side_chooser()
    return g, g.start()


def _righe(g):
    return [r for r in json.loads(g.search_log("A")) if r.get("k") == "search"]


def _piu_visitato(ch):
    c = [x for x in ch if x[1] > 0]
    best = c[0]
    for x in c[1:]:
        if x[1] > best[1] or (x[1] == best[1] and x[2] > best[2]):
            best = x
    return best[0]


def _q_max(ch):
    c = [x for x in ch if x[1] > 0]
    best = c[0]
    for x in c[1:]:
        if x[2] > best[2]:
            best = x
    return best[0]


def test_q_esplicito_come_default():
    probs = arena_rs.make_probs(_net())
    g0, r0 = _partita(probs, 5)
    g1, r1 = _partita(probs, 5, "q")
    assert r0 == r1
    for seat in "AB":
        assert re.sub(r"#\d+", "#", g0.search_log(seat)) == re.sub(r"#\d+", "#", g1.search_log(seat))


def test_visite_alle_decisioni_di_turno_e_cambia_le_scelte():
    probs = arena_rs.make_probs(_net())
    turno = diverse = altre = 0
    for seme in range(1, 6):
        g, _ = _partita(probs, seme, "visite")
        for r in _righe(g):
            ch = r["children"]
            if not any(x[1] > 0 for x in ch):
                continue
            if r["point"] == "turn_action":
                turno += 1
                assert r["action"] == _piu_visitato(ch)
                diverse += _piu_visitato(ch) != _q_max(ch)
            else:
                altre += 1
                assert r["action"] == _q_max(ch)
    print("righe di turno", turno, "diverse da Q-max", diverse, "altre", altre)
    assert turno >= 3
    assert diverse >= 1


def test_arena_game_con_scelta_visite(tmp_path):
    from riftbound.ai.ppo.model import save
    ck = tmp_path / "rand.pt"
    save(_net(), ck)
    opz = {"iter_cand": 20, "iter_opp": 20, "scelta_cand": "visite"}
    r = arena_rs.game((3, "a", "A", "prior_ppo", str(ck), "prior_ppo", str(ck), "EK", None, None, opz))
    assert r is not None


def test_nome_non_valido():
    g, _ = _partita(arena_rs.make_probs(_net()), 2, iters=4)
    with pytest.raises(ValueError):
        g.set_search_scelta("A", "boh")
