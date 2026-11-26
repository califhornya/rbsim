"""Responso (riftbound/rs/responso.py): la linea `primo` gioca davvero l'etichetta chiesta; disaccordi e confronti
su dati finti; la corsa da capo a fondo con pesi casuali, 1 partita, 2 mondi."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("torch")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import responso as R  # noqa: E402

ITER = 8
PARTITA = D.autonoma("ES", 4, None, True, ITER, "B", valutazione=("rimonta", 3.0, 0.2))
K = 8


def test_primo_gioca_l_etichetta_chiesta():
    pos = A.posizione(PARTITA, K)
    menu = pos["menu"]
    assert len(menu) >= 3
    st = A.mondo(pos, "ignote", pos["base"])
    # la prima, una in mezzo e l'ultima voce (di solito Pass) del menu
    for j in sorted({0, len(menu) // 2, len(menu) - 1}):
        riga = A.continua(pos, st, A.linea_primo("x", menu[j]), 0, "ignote")
        assert riga["primo_giocata"] == menu[j] and riga["primo_ok"], (j, menu[j], riga["primo_giocata"])
    # le linee esistenti non portano le chiavi nuove
    assert "primo_ok" not in A.continua(pos, st, A.linea_campione(), 0, "ignote")


def _classifica(voci):
    return [{"i": i, "azione": a, "n": n, "q": q, "P": p, "rango": 0} for i, (a, n, q, p) in enumerate(voci)]


def _dec(c138, g138, c512, g512):
    return {"rifai": {"138": {"classifica": _classifica(c138), "azione": g138},
                      "512": {"classifica": _classifica(c512), "azione": g512}}}


def test_mosse_disaccordi_e_pari_merito():
    # prior su a e b (pari), visite su b, Q su c: prior≠Q, visite≠Q, ma prior∩visite = {b}
    d = _dec([("a", 10, 0.1, 0.4), ("b", 50, 0.2, 0.4), ("c", 5, 0.9, 0.2)], "c",
             [("a", 10, 0.1, 0.4), ("b", 50, 0.2, 0.4), ("c", 5, 0.9, 0.2)], "c")
    m = R.mosse(d)["138"]
    assert m["insiemi"] == {"prior": [0, 1], "visite": [1], "q": [2]}
    assert m["disaccordo"] == {"visite_prior": False, "q_visite": True, "q_prior": True}
    assert m["rapp"] == {"prior": "a", "visite": "b", "q": "c"}
    # Q ignora le mosse non visitate
    d = _dec([("a", 0, None, 0.9), ("b", 3, 0.2, 0.1)], "b", [("a", 0, None, 0.9), ("b", 3, 0.2, 0.1)], "b")
    m = R.mosse(d)["138"]
    assert m["insiemi"]["q"] == [1] and m["disaccordo"]["q_prior"] and m["disaccordo"]["visite_prior"]
    assert R.linee_decisione(R.mosse(d), (138, 512)) == ["b", "a"]
    c = R._confronti(R.mosse(d), (138, 512))
    assert c["visite_prior@138"] == ("b", "a") and "scelta512_138" not in c


def test_stat():
    s = R.stat([1.0, 0.0, 0.5, 0.5])
    assert s["n"] == 4 and s["media"] == 0.5 and s["intervallo_95"][0] < 0.5 < s["intervallo_95"][1]
    assert R.stat([])["n"] == 0


def test_responso_da_capo_a_fondo(tmp_path):
    righe = R.responso(["EK"], [300], 2, (20, 60), 2, tmp_path, None, True, 1, print_=lambda *_: None)
    assert righe[-1].startswith("totale: 2 decisioni")
    assert (tmp_path / "riepilogo.txt").exists()
    cart = sorted(p for p in tmp_path.iterdir() if p.is_dir())
    assert len(cart) == 2 and all((c / "decisione.json").exists() for c in cart)
    con = [c for c in cart if (c / "mondi.jsonl").exists()]
    assert con, "almeno una decisione con disaccordo"
    righe_mondi = [json.loads(x) for x in (con[0] / "mondi.jsonl").read_text().splitlines()]
    assert len(righe_mondi) == 2 and all(r["primo_ok"] for rows in righe_mondi for r in rows)
