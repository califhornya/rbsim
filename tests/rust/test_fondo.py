"""Fondo (riftbound/rs/fondo.py): candidati, scelta e delta su dati finti, regola di stop, stime di tempo, la corsa da
capo a fondo con ripresa e una verifica su una posizione vera."""
from __future__ import annotations

import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import fondo as F  # noqa: E402
from riftbound.rs import scelta as C  # noqa: E402
from riftbound.rs import seguiti as S  # noqa: E402


def _o(children, giocata, etichette=("x", "y", "z", "w")):
    """Riga finta: i figli sono (indice nel menu, n, q); il menu ha azioni 'a0'.. e le etichette date."""
    menu = [f"a{i}" for i in range(len(etichette))]
    ch = [[menu[i], n, q, 0.0, []] for i, n, q in children]
    return {"k": 3, "turn": 2, "action": giocata, "menu": list(etichette), "riga": {"menu": menu, "children": ch}}


def test_candidati_campione_primo_e_ordine():
    # il campione (x, scelta per Q) non e' il piu' visitato: resta primo; poi per visite, a pari visite per q
    r = F.candidati(_o([(0, 3, 0.9), (1, 5, 0.4), (2, 5, 0.6), (3, 1, 0.1)], "x"))
    assert r["candidati"] == ["x", "z", "y"] and r["coerente"] and r["campione"] == "x"
    assert r["n"] == [3, 5, 5] and r["q"] == [0.9, 0.6, 0.4] and (r["k"], r["turno"]) == (3, 2)
    # a pari visite e pari q: l'indice nel menu, anche con i figli in ordine diverso dal menu
    r = F.candidati(_o([(3, 4, 0.5), (2, 4, 0.5), (1, 4, 0.5), (0, 9, 0.9)], "x"))
    assert r["candidati"] == ["x", "y", "z"]
    # n = 0 esclusi (anche con q alta); n piu' grande: 2 candidati
    r = F.candidati(_o([(2, 0, 0.99), (1, 2, 0.1), (0, 1, 0.3)], "x"), n=2)
    assert r["candidati"] == ["x", "y"] and r["coerente"]
    assert F.candidati(_o([(0, 1, 0.3), (1, 6, 0.2), (2, 5, 0.1)], "x"), n=2)["candidati"] == ["x", "y"]


def test_candidati_ripetuti_pochi_e_incoerente():
    # etichette ripetute: y compare due volte nel menu, solo la prima nell'ordinamento; il campione non si ripete
    r = F.candidati(_o([(0, 5, 0.9), (1, 4, 0.3), (2, 3, 0.2), (3, 2, 0.1)], "x", etichette=("x", "y", "y", "x")))
    assert r["candidati"] == ["x", "y"]
    # meno di 3: quelli che ci sono
    r = F.candidati(_o([(0, 5, 0.9)], "x"))
    assert r["candidati"] == ["x"] and r["n"] == [5] and r["q"] == [0.9]
    # incoerente: la scelta per Q (y) non e' la mossa giocata (x); il campione e' comunque il primo
    r = F.candidati(_o([(0, 3, 0.2), (1, 5, 0.8)], "x"))
    assert not r["coerente"] and r["candidati"] == ["x", "y"]
    # campione senza figlio valido: n e q None
    r = F.candidati(_o([(1, 5, 0.8)], "x"))
    assert not r["coerente"] and r["n"][0] is None and r["q"][0] is None
    # con la partita: in testa nome e matchup
    p = D.autonoma("EK", 4, None, True, 8, "A", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
    c = F.candidati(_o([(0, 1, 0.1)], "x"), p)
    assert c["matchup"] == "EK" and c["nome"] == A.nome_partita(p) and c["partita"] is p and list(c)[0] == "partita"


def test_scegli_e_valuta_scelta():
    assert F.scegli([0.5, 0.5, 0.2]) == 0
    assert F.scegli([0.1, 0.6, 0.6]) == 1
    assert F.scegli([None, None, None]) == 0
    assert F.scegli([0.2, None, 0.7]) == 2

    def rows(w, ret, ok=(True, True, True)):
        return [{"line": f"c{j}", "world": w, "returns": r, "primo_ok": o} for j, (r, o) in enumerate(zip(ret, ok))]
    dati = [rows(0, (0.0, 1.0, 0.5)), rows(1, (1.0, 1.0, 0.0), ok=(True, False, True)), rows(2, (0.5, 1.0, 0.0))]
    v = F.valuta_scelta(dati, ["c0", "c1", "c2"])
    assert v["ritorni"] == [[0.0, 0.5], [1.0, 1.0], [0.5, 0.0]]
    assert v["n_mondi"] == 2 and v["mondi_esclusi"] == 1 and v["medie"] == [0.25, 1.0, 0.25] and v["scelta"] == 1
    tutti_esclusi = F.valuta_scelta([rows(0, (1, 1, 1), ok=(False, True, True))], ["c0", "c1", "c2"])
    assert tutti_esclusi["medie"] == [None] * 3 and tutti_esclusi["scelta"] == 0 and tutti_esclusi["n_mondi"] == 0


def test_delta_verifica():
    def w(c, s, ok_c=True, ok_s=True):
        return [{"line": "campione", "returns": c, "primo_ok": ok_c}, {"line": "scelta", "returns": s, "primo_ok": ok_s}]
    d = F.delta_verifica([w(0.0, 1.0), w(1.0, 0.5), w(0.5, 1.0, ok_s=False), w(0.5, 0.5)])
    assert d["deltas"] == [1.0, -0.5, 0.0] and d["media"] == pytest.approx(1 / 6)
    assert d["n_mondi"] == 3 and d["mondi_esclusi"] == 1
    assert F.delta_verifica([])["media"] is None


def test_zero_esatto_e_riga():
    dec = {"nome": "EK0", "matchup": "EK", "k": 3, "turno": 2, "coerente": True, "candidati": ["x", "y"]}
    r = F.riga(dec, {"scelta": 0}, None)
    assert r["disaccordo"] is False and r["media"] is None and r["n_mondi"] == 0 and C._valore(r) == 0.0
    r = F.riga(dec, {"scelta": 1}, {"media": 0.25, "n_mondi": 4, "mondi_esclusi": 1, "deltas": [0.5, 0, 0.5, 0]})
    assert r["disaccordo"] and C._valore(r) == 0.25 and r["scelta"] == "y" and r["mondi_esclusi"] == 1
    r = F.riga(dec | {"coerente": False}, None, None)
    assert not r["coerente"] and C._valore(r) is None and r["scelta"] is None


def test_mondi_disgiunti():
    a, b = F.mondi(32, 100)
    assert (a.start, len(a), b.start, len(b)) == (40_000, 32, 50_000, 100) and not set(a) & set(b)
    with pytest.raises(ValueError):
        F.mondi(10_001, 100)
    with pytest.raises(ValueError):
        F.mondi(0, 100)
    with pytest.raises(ValueError):
        F.mondi(32, 0)


def _rs(lo, cambi):
    return {"totale": [0.1, lo, 0.2], "n_disaccordi_validi": cambi}


def test_regola_di_stop():
    assert F.regola_stop(_rs(0.01, 20)) is True
    assert F.regola_stop(_rs(0.01, 19)) is False
    assert F.regola_stop(_rs(0.0, 30)) is False
    assert F.regola_stop(_rs(-0.05, 30)) is False
    assert F.regola_stop(_rs(0.01, 5), minimo=5) is True


def test_tempi_valori_esatti():
    t = F.tempi([1.0, 2.0, 3.0, 10.0], [1, 1, 3], [4, 6], 2, 100, 10, 50)
    assert t["cpu"] == {"mediana": 2.5, "p95": pytest.approx(np.percentile([1, 2, 3, 10], 95)), "massimo": 10.0, "n": 4}
    assert t["per_turno"]["media"] == pytest.approx(5 / 3) and t["per_turno"]["p95"] == pytest.approx(2.8)
    # 2 * 100 coppie * 10 matchup * 5 decisioni * 4 s / 3600 = 11.11 ore di cpu
    assert t["arena"]["ore_cpu"] == pytest.approx(2 * 100 * 10 * 5 * 4.0 / 3600)
    assert t["arena"]["ore_server"] == pytest.approx(t["arena"]["ore_cpu"] / 50)
    assert t["arena"]["decisioni_per_partita"] == 5.0 and t["arena"]["coppie"] == 100
    # Monte Carlo: deterministico, con tutti i cpu uguali e turni di 1 decisione il tempo e' cpu / processi
    m = F.tempi([4.0, 4.0], [1, 1], [3], 4, 10, 1, 5)["mac_turno"]
    assert m == {"mediana": 1.0, "p95": 1.0}
    assert F.tempi([1.0, 2.0], [1, 2], [3], 3, 1, 1, 1) == F.tempi([1.0, 2.0], [1, 2], [3], 3, 1, 1, 1)
    vuoto = F.tempi([], [], [], 9, 100, 10, 47)
    assert vuoto["cpu"]["mediana"] is None and vuoto["cpu"]["n"] == 0 and vuoto["per_turno"]["media"] is None
    assert vuoto["mac_turno"] == {"mediana": None, "p95": None}
    assert vuoto["arena"]["ore_cpu"] is None and vuoto["arena"]["ore_server"] is None


@pytest.fixture(scope="module")
def corsa(tmp_path_factory):
    out = tmp_path_factory.mktemp("fondo")
    righe = F.posizioni(["EK"], 1, 2, 2, 2, out, None, casuali=True, iterazioni=40, n_boot=200, print_=lambda *_: None)
    return out, righe


def test_da_capo_a_fondo_e_ripresa(corsa, monkeypatch):
    out, righe = corsa
    assert righe[-1].startswith("totale:")
    assert (out / "riepilogo.txt").read_text().splitlines()[-1].startswith("totale:")
    assert sum(x.startswith("regola di stop:") for x in righe) == 1
    assert any(x.startswith("tempo di cpu per decisione") for x in righe)
    assert any(x.startswith("stima per turno sul Mac") for x in righe)
    assert any(x.startswith("stima dell'arena") for x in righe)
    esito = json.loads((out / "esito.json").read_text())
    assert isinstance(esito["passa"], bool) and esito["minimo_cambi"] == F.MINIMO_CAMBI and len(esito["totale"]) == 3
    rj = json.loads((out / "riepilogo.json").read_text())
    assert rj["riassunto"]["esaminate"] >= 1 and set(rj) == {"impostazioni", "riassunto", "tempi", "decisioni"}

    # zero esatto: nessuna verifica dove la scelta resta il campione; indici di mondo disgiunti
    scelte = sorted(out.glob("*/scelta.json"))
    assert scelte
    for f in scelte:
        sc = json.loads(f.read_text())
        assert (f.parent / "verifica.json").exists() == (sc["scelta"] != 0)
        if sc.get("un_candidato"):
            assert sc["n_mondi"] == 0 and sc["cpu"] is None
            assert not (f.parent / "scelta_mondi.jsonl").exists()
            continue
        mondi_s = [r[0]["world"] for r in map(json.loads, (f.parent / "scelta_mondi.jsonl").read_text().splitlines())]
        assert mondi_s == [40_000, 40_001] and sc["mondi"] == [40_000, 2] and len(sc["cpu_mondi"]) == 2
        assert "ritorni" not in sc and sc["mossa"] == sc["candidati"][sc["scelta"]]
        assert set(json.loads((f.parent / "scelta_mondi.jsonl").read_text().splitlines()[0])[0]) <= set(F._CHIAVI_MONDO)
        if sc["scelta"] != 0:
            ve = json.loads((f.parent / "verifica.json").read_text())
            mondi_v = [r[0]["world"] for r in map(json.loads, (f.parent / "verifica_mondi.jsonl").read_text().splitlines())]
            assert mondi_v == [50_000, 50_001] and ve["mondi"] == [50_000, 2] and len(ve["deltas"]) == ve["n_mondi"]

    def no(*_a, **_k):
        raise AssertionError("lavoro rifatto")
    monkeypatch.setattr(D, "originale", no)
    monkeypatch.setattr(A, "_lavoro", no)
    righe2 = F.posizioni(["EK"], 1, 2, 2, 2, out, None, casuali=True, iterazioni=40, n_boot=200, print_=lambda *_: None)
    assert righe2[-1].startswith("totale:")
    with pytest.raises(ValueError):
        F.posizioni(["EK"], 1, 2, 3, 2, out, None, casuali=True, iterazioni=40, print_=lambda *_: None)


def test_gioca_fase_verifica_diretta(tmp_path):
    """Candidati distinti forzati (come test_scelta_posizioni), anche se la corsa non ha cambiato mossa."""
    partita = D.autonoma("ES", 4, None, True, 8, "B", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
    o = S.selezionate(partita, 1)[0]
    dec = {"partita": partita, "nome": A.nome_partita(partita), "matchup": "ES", "k": o["k"], "turno": o["turn"],
           "menu": o["menu"], "campione": o["menu"][0], "candidati": [o["menu"][0], o["menu"][1]], "n": [1, 2],
           "q": [0.0, 0.0], "coerente": True}
    res = F.gioca_fase(dec, "verifica", tmp_path / "d", 2, scelta=1)
    assert len(res["deltas"]) + res["mondi_esclusi"] == 2 and res["n_mondi"] == len(res["deltas"])
    assert all(x in (-1.0, -0.5, 0.0, 0.5, 1.0) for x in res["deltas"]) and res["mondi"] == [50_000, 2]
    assert json.loads((tmp_path / "d" / "verifica.json").read_text()) == res
    righe = [json.loads(x) for x in (tmp_path / "d" / "verifica_mondi.jsonl").read_text().splitlines()]
    assert [r[0]["world"] for r in righe] == [50_000, 50_001] and {x["line"] for x in righe[0]} == {"campione", "scelta"}


def _fondo_sintetico(tmp_path, incoerente=True):
    """Una decisione coerente (c1 batte il campione di +0,5 su tutti i 32 mondi) e una incoerente senza cartella."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "fondo_ridotto", Path(__file__).resolve().parents[2] / "scripts" / "rust" / "fondo_ridotto.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    dec = lambda nome, coer: {"nome": nome, "k": 0, "matchup": "EK", "turno": 1, "coerente": coer,
                              "candidati": ["a", "b"], "n": [100, 38], "q": [0.5, 0.4]}
    decs = [dec("p1", True)] + ([dec("p2", False)] if incoerente else [])
    (tmp_path / "decisioni.jsonl").write_text(json.dumps({"decisioni": decs}) + "\n")
    c = tmp_path / "000_p1_k0"
    c.mkdir()
    (c / "scelta.json").write_text(json.dumps({"scelta": 1}))
    righe = [[{"line": "c0", "returns": 0.0, "primo_ok": True, "secondi": 1.0},
              {"line": "c1", "returns": 0.5, "primo_ok": True, "secondi": 1.0}] for _ in range(32)]
    (c / "scelta_mondi.jsonl").write_text("\n".join(json.dumps(r) for r in righe) + "\n")
    (c / "verifica.json").write_text(json.dumps({"media": 0.5, "deltas": [0.5] * 10}))
    return R


def test_ridotto_decisione_incoerente_senza_cartella(tmp_path):
    R = _fondo_sintetico(tmp_path)
    es = R.carica(tmp_path)
    assert len(es) == 2 and es[1]["sc"] is None and es[1]["dati"] == [] and es[1]["ve"] is None
    rows, *_ = R.variante(es, 32, 2, None, {})
    assert rows[1]["coerente"] is False and C.riassunto(rows)["totale"][0] == pytest.approx(0.5)


def test_ridotto_mondi_rimasti_indipendenti_dalla_scelta_piena(tmp_path):
    R = _fondo_sintetico(tmp_path, incoerente=False)
    es = R.carica(tmp_path)
    es[0]["ve"]["media"] = 9.0  # la verifica della scelta piena non deve influire per m < 32
    r, _, info = R.valuta(es[0], 8, 2, None, {})
    assert r["media"] == pytest.approx(0.5) and r["n_mondi"] == 24 and not info["nonver"]
    r, _, info = R.valuta(es[0], 8, 2, None, {}, mista=True)
    assert r["media"] == 9.0 and not info["distorta"]  # mista: scelta uguale alla piena -> verifica
    es[0]["sc"]["scelta"] = 0
    r, _, info = R.valuta(es[0], 8, 2, None, {}, mista=True)
    assert info["nonver"] and info["distorta"]
    r, _, info = R.valuta(es[0], 32, 2, None, {})  # m = 32 come prima
    assert info["nonver"] and info["distorta"]
