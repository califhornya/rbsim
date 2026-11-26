"""Valore della rete nelle foglie della ricerca (SearchCore.peso_valore_rete, spento di default): (a) con peso 0 la
partita e il search_log restano quelli di prima, anche se la funzione dei prior restituisce (probs, valore);
(b) peso 0,2: la partita gira e le chiamate in piu' (menu di una voce, solo valore) sono contate; (c) la prospettiva
del valore: il valore e' dal posto di chi decide (B a 6/8, una posizione in cui vince subito: l'osservazione che la
rete riceve ha i punti di B per primi)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

pytest.importorskip("riftbound_rs")
torch = pytest.importorskip("torch")

from riftbound.ai.ppo.collect import DECK_OF  # noqa: E402
from riftbound.rs import arena_rs, rust_bridge as rb  # noqa: E402


def _net():
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(0)
    return PPONet().eval()


def _partita(probs, peso=None, seme=31, iters=6):
    g = rb.build(seme, Path(DECK_OF["E"]), Path(DECK_OF["K"]), "a", 40, "6427b90+D72-D82")
    for seat in "AB":
        g.set_search_agent(seat, iters, seme * 2 + (seat == "B"), None, probs, True)
        g.set_search_win_probe(seat, True)
        g.set_search_valutazione(seat, "rimonta", 3.0, 0.2)
        if peso is not None:
            g.set_search_valore_rete(seat, peso)
    g.set_side_chooser()
    return g, g.start()


def _logs(g):
    return [json.loads(re.sub(r"#\d+", "#", g.search_log(s))) for s in "AB"]


def test_peso_zero_non_cambia_la_partita():
    net = _net()
    g0, r0 = _partita(arena_rs.make_probs(net))
    for peso in (None, 0.0):
        g1, r1 = _partita(arena_rs.make_probs_valore(net), peso)
        assert r0 == r1 and _logs(g0) == _logs(g1)


def test_peso_020_gira_e_conta_le_chiamate():
    net = _net()
    g0, _ = _partita(arena_rs.make_probs_valore(net), 0.0)
    g1, r1 = _partita(arena_rs.make_probs_valore(net), 0.2)
    assert r1[0] in ("A", "B", "DRAW")
    for s in "AB":
        tot0, solo0 = g0.search_valore_rete_stats(s)
        tot1, solo1 = g1.search_valore_rete_stats(s)
        assert solo0 == 0 and tot0 > 0 and tot1 > 0 and 0 <= solo1 <= tot1
    print("chiamate (totali, solo valore):", [g1.search_valore_rete_stats(s) for s in "AB"])
    # con una funzione senza valore il peso non fa nulla: stessa partita
    g2, r2 = _partita(arena_rs.make_probs(net), 0.2)
    g3, r3 = _partita(arena_rs.make_probs(net))
    assert r2 == r3 and _logs(g2) == _logs(g3)


def _posizione_b(probs, iters=60):
    from test_vittoria import _game
    g = _game(seed=0)
    g.set_search_agent("B", iters, 0, None, probs, False)
    g.set_search_registro("B", True)
    g.set_search_valore_rete("B", 1.0)
    return g


def test_prospettiva_del_valore_e_del_lato_che_decide():
    """B a 6/8 contro A a 4/8, vince subito: la rete vede i punti di B come "miei" (x[1] > x[2]); un valore che
    segue questa differenza sale per B, e i Q alla radice salgono con il valore (peso 1) invece di scendere."""
    visti = []

    def probs_di(segno):
        def f(x, q, ctx, otype, ocards, ofeats):
            visti.append((float(x[1]), float(x[2])))
            n = len(otype)
            return np.full(n, 1.0 / n, dtype=np.float32), segno * float(np.tanh(4 * (x[1] - x[2])))
        return f

    q_medi = {}
    for segno in (1, -1):
        visti.clear()
        g = _posizione_b(probs_di(segno))
        g.run_segment(1)
        assert visti and all(m > o for m, o in visti)       # i punti di B (6/8 e piu') per primi: "miei"
        qs = [q for r in g.search_registro("B") if r["kind"] == "cercata" for q in r["Q"] if q == q]
        q_medi[segno] = float(np.mean(qs))
    assert q_medi[1] > q_medi[-1]
