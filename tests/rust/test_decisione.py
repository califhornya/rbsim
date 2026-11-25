"""Rifare una decisione del campione (riftbound/rs/decisione_rs.py, scripts/rust/decisione.py, episodi.py):
pesi casuali, poche iterazioni. A iterazioni originali la ricerca rifatta riproduce la mossa originale (autonoma e
partita della pagina); una variante a più iterazioni gira; episodi e concordanza girano su 2 semi."""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("torch")

from riftbound.rs import decisione_rs as D  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))

ITER = 8


def _auto(seed=3, mu="ES"):
    return D.autonoma(mu, seed, None, True, ITER)


def test_autonoma_riproduce_la_mossa_originale():
    P = _auto()
    elenco = D.elenca(P)
    assert len(elenco) > 10 and [r["k"] for r in elenco] == list(range(len(elenco)))
    assert {r["point"] for r in elenco} <= {"turn_action", "reaction", "showdown_action"}
    for k in (0, len(elenco) // 2, len(elenco) - 1):
        r = D.rifai(P, k, None)
        assert r["prefisso_ok"] and r["riproduce"] and r["azione"] == elenco[k]["action"], (k, r["azione"])
        assert r["posizione"]["campi"] and r["classifica"][0]["rango"] == 1


def test_una_variante_a_piu_iterazioni_gira():
    P = _auto()
    k = next(r["k"] for r in D.elenca(P) if r["point"] == "turn_action" and r["n_menu"] > 3)
    r = D.rifai(P, k, 40)
    assert r["prefisso_ok"] and r["iterazioni"] == 40
    assert sum(x["n"] for x in r["classifica"]) >= 30 and r["azione"] in [x["azione"] for x in r["classifica"]]
    with pytest.raises(ValueError):
        D.rifai(P, 10_000, None)


def _partita_pagina(tmp_path) -> Path:
    from test_coach_rs import _answer, _campione, _deck, _session, _wait
    s = _session(tmp_path, campione_path=_campione(tmp_path), iterazioni=ITER)
    s.new_game(_deck("E"), _deck("S"), seat="B", opponent="campione", seed=4)
    rng, n = random.Random(4), 0
    while n < 40:
        st = _wait(s)
        if st["status"] == "over":
            break
        s.answer(_answer(st["pending"], rng))
        n += 1
    s.abandon()
    s._thread.join(timeout=120)
    return next((tmp_path / "coach" / "partite").glob("*.json"))


def test_pagina_riproduce_la_partita(tmp_path):
    f = _partita_pagina(tmp_path)
    d = json.loads(f.read_text())
    assert d["replay"]["answers"] and d["replay"]["opponent"] == "campione"
    P = {"tipo": "pagina", "file": str(f), "casuali": True}
    elenco = D.elenca(P)
    assert len(elenco) > 5
    # la sequenza delle mosse del campione e' quella che la pagina ha mostrato (testi in italiano)
    giocate = [e["text"] for e in d["events"] if e.get("who") == "opp" and e.get("move")]
    assert abs(len(giocate) - len([r for r in elenco if r["action"] != "Pass"])) <= 1, (len(giocate), len(elenco))
    for k in (0, len(elenco) // 2, len(elenco) - 1):
        r = D.rifai(P, k, None)
        assert r["riproduce"], (k, r["azione"], r["azione_originale"])
    v = D.rifai(P, len(elenco) // 2, 30, posizione=False)
    assert v["prefisso_ok"] and v["classifica"]


def test_episodi_e_concordanza_su_due_semi(capsys):
    import episodi
    t0 = time.time()
    assert episodi.main(["--matchup", "ES", "--semi", "1-2", "--pesi-casuali", "--iterazioni", str(ITER)]) == 0
    out = capsys.readouterr().out
    assert "2 partite" in out and "§8 accumulo" in out and "§7 spreco" in out
    r = D.concordanza("ES", [1, 2], ITER, per_tipo=3, casuali=True, iter_orig=ITER)
    assert set(r) == {"turno", "reazione", "showdown"}
    tot = sum(x["decisioni"] for x in r.values())
    assert tot >= 3
    # alle iterazioni originali la mossa e' sempre la stessa
    assert all(x["uguali"] == x["decisioni"] for x in r.values()), r
    r2 = D.concordanza("ES", [1, 2], 3 * ITER, per_tipo=3, casuali=True, iter_orig=ITER)
    assert sum(x["decisioni"] + x["escluse"] for x in r2.values()) >= 3
    print(f"episodi+concordanza: {time.time() - t0:.0f} s")


def test_override_con_la_sonda_riproduce_la_vittoria():
    """Posizione di test_vittoria.py in cui la sonda trova la vittoria: l'override sulla ricerca k non spegne la
    sonda (a differenza dei ganci lockstep) e non cambia l'indice delle ricerche."""
    from test_vittoria import _game
    ref = _game(seed=0, probe=True, log=True)
    assert ref.run_segment(1) == "B"
    righe_ref = ref.search_log("B")
    assert '"vittoria"' in righe_ref
    g = _game(seed=0, probe=True, log=True)
    g.set_search_override("B", 0, 300)
    assert g.run_segment(1) == "B" and '"vittoria"' in g.search_log("B")    # la sonda trova ancora la vittoria
    assert g.search_log("B")[:300] == righe_ref[:300]                        # e le righe prima di k sono le stesse
    # senza vittoria (5 punti) la ricerca 0 fa esattamente le iterazioni chieste, sonda accesa
    g = _game(points_b=5, seed=0, probe=True, log=True)
    g.set_search_timing("B", True)
    g.set_search_override("B", 0, 7)
    g.run_segment(1)
    righe = [r for r in json.loads(g.search_log("B")) if r["k"] == "search"]
    assert righe and righe[0]["iters"] == 7 and all(r["iters"] == 42 for r in righe[1:] if r["point"] == "turn_action")
