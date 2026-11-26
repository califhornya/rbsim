"""Raccolta pilota (riftbound/rs/raccolta.py): esplorazione e registro della ricerca su Rust, `osserva`, il gioco turno
per turno (`setup` + `play_turn`). Rete a pesi casuali, poche iterazioni. Con le opzioni spente la ricerca resta quella
di prima (il confronto col search_log di prima della modifica e' stato fatto a mano sul registro delle partite EK e RS)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytest.importorskip("riftbound_rs")
torch = pytest.importorskip("torch")

from riftbound.ai.ppo.collect import DECK_OF  # noqa: E402
from riftbound.rs import decisione_rs, raccolta, rust_bridge as rb  # noqa: E402

ITER = 6
REGOLE = raccolta.REGOLE_DEFAULT


def partita(seme, mu="EK", esplora=False, registro=False, osserva=False, a_turni=False, iters=ITER):
    probs = decisione_rs.rete(None, True)
    g = rb.build(seme, Path(DECK_OF[mu[0]]), Path(DECK_OF[mu[1]]), "a", 40, REGOLE)
    for seat in "AB":
        g.set_search_agent(seat, iters, seme * 2 + (seat == "B"), None, probs, True)
        g.set_search_win_probe(seat, True)
        g.set_search_valutazione(seat, "rimonta", 3.0, 0.2)
        if esplora:
            g.set_search_esplorazione(seat, 0.3, 0.25, 4)
        if registro:
            g.set_search_registro(seat, True)
    g.set_side_chooser()
    if not a_turni:
        return g, g.start()
    g.setup()
    res = None
    while res is None:
        res = g.play_turn()
        if res is None and osserva:
            g.osserva("A"), g.osserva("B")
    return g, res


def logs(g):
    """I search_log dei due posti; gli uid delle carte (`#n`) in una stessa processo ripartono da dove erano: tolti."""
    return [json.loads(re.sub(r"#\d+", "#", g.search_log(s))) for s in "AB"]


def test_registro_e_osserva_non_cambiano_la_partita():
    for esplora in (False, True):
        g0, r0 = partita(31, esplora=esplora)
        g1, r1 = partita(31, esplora=esplora, registro=True, osserva=True, a_turni=True)
        assert r0 == r1 and logs(g0) == logs(g1)


def test_stesso_seme_stessa_partita_semi_diversi_no():
    g0, r0 = partita(41, esplora=True)
    g1, r1 = partita(41, esplora=True)
    assert r0 == r1 and logs(g0) == logs(g1)
    g2, _ = partita(42, esplora=True)
    assert logs(g0) != logs(g2)


def test_registro_coerente_col_search_log_e_il_rumore():
    g, _ = partita(43, esplora=True, registro=True)
    for seat, log in zip("AB", logs(g)):
        recs = g.search_registro(seat)
        cerc = [r for r in recs if r["kind"] == "cercata"]
        righe = [r for r in log if r["k"] == "search"]
        assert len(cerc) == len(righe) and len(recs) > len(cerc)
        sampled = 0
        for r, row in zip(cerc, righe):
            n = len(r["menu"])
            assert r["point"] == row["point"] and r["turn"] == row["turn"]
            for k in ("P", "N", "Q"):
                assert len(r[k]) == n
            assert 0 <= r["giocata"] < n
            if n < 2:            # una voce con scelte davanti: la rete non e' stata interrogata
                assert "x" not in r
                continue
            assert len(r["otype"]) == n and r["ocards"].shape == (n, 3) and r["ofeats"].shape[0] == n
            assert r["x"].dtype == np.float32 and len(r["ctx"]) == 4
            if r["point"] == "turn_action":
                # `P` del search_log e' quello dopo il rumore; il registro tiene prima e dopo
                assert r["P_rumore"] is not None and len(r["P_rumore"]) == n
                post = [p for _, p in row["P"]]
                assert np.allclose(sorted(post), sorted(r["P_rumore"].tolist()), atol=1e-5)
                assert abs(float(r["P"].sum()) - 1.0) < 1e-4 and abs(float(r["P_rumore"].sum()) - 1.0) < 1e-4
            else:
                assert r["P_rumore"] is None
                assert np.allclose([p for _, p in row["P"]], r["P"], atol=1e-5)
                assert not r["campionata"]
            sampled += r["campionata"]
            assert r["campionata"] <= (r["point"] == "turn_action")
        turn_recs = [r for r in cerc if r["point"] == "turn_action"]
        assert [r["campionata"] for r in turn_recs[:4]] == [True] * min(4, len(turn_recs))
        assert sampled == min(4, len(turn_recs)) or sampled <= 4


def test_senza_esplorazione_P_non_ha_rumore_e_coincide():
    g, _ = partita(44, registro=True)
    for seat, log in zip("AB", logs(g)):
        cerc = [r for r in g.search_registro(seat) if r["kind"] == "cercata"]
        for r, row in zip(cerc, [x for x in log if x["k"] == "search"]):
            assert r["P_rumore"] is None and not r["campionata"]
            assert np.allclose([p for _, p in row["P"]], r["P"], atol=1e-5)


def test_osserva_non_tocca_la_partita_e_ha_le_dimensioni_giuste():
    g, _ = partita(45, registro=True)
    x, q, ctx = g.osserva("A")
    cerc = next(r for r in g.search_registro("A") if r["kind"] == "cercata")
    assert x.shape == cerc["x"].shape and x.dtype == np.float32 and ctx.shape == (4,) and q == cerc["q"]
    assert np.array_equal(g.osserva("A")[0], x)


def test_partita_scritta_e_riletta(tmp_path):
    out = tmp_path / "r"
    out.mkdir()
    task = {"mu": "EK", "seme": 30_000_003, "comincia": "b", "scambio": True, "iterazioni": 4, "ckpt": None,
            "regole": REGOLE, "esplorazione": [0.3, 0.25, 4], "insieme": raccolta.insieme(3), "out": str(out)}
    riga = raccolta._lavora(task)
    d = raccolta.carica(out / riga["file"])
    assert d["posti"] == {"A": "K", "B": "E"} and d["vincitore"] in ("A", "B", "DRAW")
    assert {r["esito"] for r in d["record"]} <= {-1, 0, 1} and len(d["stati"]) > 0
    assert all(s["esito"] == d["esito"][s["seat"]] for s in d["stati"])
    assert riga["byte"] > 0 and len(raccolta.indice(out)) == 1
    assert raccolta.piano(["EK"], 4)[2][4] == "b" and raccolta.insieme(8) == "sviluppo"


def test_ripresa_controlla_la_provenienza_prima_di_scrivere(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSIM_REGOLE", REGOLE)
    ckpt = tmp_path / "originale.pt"
    ckpt.write_bytes(b"pesi originali")
    copia = tmp_path / "copia.pt"
    copia.write_bytes(ckpt.read_bytes())
    out = tmp_path / "raccolta"

    # Una partita preesistente nel formato precedente, completa per il piano richiesto.
    seed = raccolta.piano(["EK"], 1)[0][3]
    file_partita = raccolta.percorso(out, "EK", seed)
    file_partita.parent.mkdir(parents=True)
    file_partita.touch()
    (out / "indice.jsonl").write_text(json.dumps({"seme": seed, "file": str(file_partita.relative_to(out))}) + "\n")
    args = dict(regole=REGOLE, iterazioni=6, esplorazione=raccolta.ESPLORAZIONE, matchup=["EK"], per_matchup=1)
    manifest = out / "provenienza.json"
    manifest.write_text(json.dumps(raccolta.provenienza(args, out, ckpt), indent=1))

    def avvia(**opzioni):
        args = dict(ckpt=copia, regole=REGOLE, iterazioni=6, esplorazione=raccolta.ESPLORAZIONE)
        args.update(opzioni)
        raccolta.esegui(out, ["EK"], 1, 1, **args)

    prima = manifest.read_bytes()
    avvia()  # gli stessi pesi in un altro percorso
    assert manifest.read_bytes() == prima
    for modifiche in ({"regole": "6427b90"}, {"iterazioni": 7}, {"esplorazione": (0.3, 0.0, 4)}, {"ckpt": None}):
        with pytest.raises(ValueError, match="incompatibile"):
            avvia(**modifiche)
    copia.write_bytes(b"pesi diversi")
    with pytest.raises(ValueError, match="checkpoint"):
        avvia()
    assert manifest.read_bytes() == prima


def test_raccolta_precedente_senza_provenienza(tmp_path):
    (tmp_path / "indice.jsonl").write_text('{"seme": 0, "file": "vecchia.pkl.gz"}\n')
    with pytest.raises(ValueError, match="senza provenienza"):
        raccolta.esegui(tmp_path, ["EK"], 0, 1, None, REGOLE)
    assert not (tmp_path / "provenienza.json").exists()
