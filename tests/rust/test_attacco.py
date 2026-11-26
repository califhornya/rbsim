"""Attacco (riftbound/rs/attacco.py, scripts/rust/attacco.py): pesi casuali, poche iterazioni.
`Game.valuta` non perturba; generazione e deduplica delle proposte; `continua` per `campione` e per una sequenza;
`posizioni` trova candidati; `confronta` da capo a fondo con 2+2 mondi e un processo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_esp as E  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))

ITER = 8
# ES, seme 4, posto B: k=8 è la prima decisione di turno utile del turno 10 con un campo dell'avversario con unita' e un campo libero
PARTITA = D.autonoma("ES", 4, None, True, ITER, "B", valutazione=("rimonta", 3.0, 0.2))
K = 8


@pytest.fixture(scope="module")
def pos():
    return A.posizione(PARTITA, K)


def test_valuta_non_perturba(pos):
    P = pos["P"]
    g1 = E.gioco(P, pos["tree"], 5)
    g2 = E.gioco(P, pos["tree"], 5)
    prima = g1.raw_dump()
    v = [g1.valuta("B", "storica"), g1.valuta("B"), g1.valuta("A", "rimonta", 3.0, 0.2), g1.valuta("B", "accumulo", 3.0, 0.2)]
    assert all(isinstance(x, float) for x in v) and v[0] == v[1]
    assert g1.raw_dump() == prima
    with pytest.raises(ValueError):
        g1.valuta("B", "inesistente")
    with pytest.raises(RuntimeError):
        g1.valuta("C")
    # una continuazione dà lo stesso esito con e senza chiamate a `valuta`
    for g in (g1, g2):
        A.setup(g, P, 11)
    w1 = g1.run_actions_end()
    g1.valuta("B", "rimonta", 3.0, 0.2)
    w2 = g2.run_actions_end()
    assert w1 == w2 and g1.raw_dump() == g2.raw_dump()


def test_proposte_e_deduplica(pos):
    tutte = A.genera(pos, deduplica=False)
    campi = sorted({p["field"] for p in tutte})
    assert len(tutte) == 18 * len(campi) and campi == [1] and [p["nome"] for p in tutte][:2] == ["p00", "p01"]
    assert all(p["uguale_a"] is None for p in tutte)
    dedup = A.genera(pos, deduplica=True)
    assert [p["events"] for p in dedup] == [p["events"] for p in tutte]
    distinti = [p for p in dedup if p["uguale_a"] is None]
    assert 1 <= len(distinti) <= len(dedup)
    for p in dedup:
        if p["uguale_a"]:
            prima = next(q for q in dedup if q["nome"] == p["uguale_a"])
            assert prima["events"] == p["events"] and prima["indice"] < p["indice"]
    assert len(A.linee_da(dedup, "campione")) == 1 + len(distinti)


def test_continua_campione_e_sequenza(pos):
    P = pos["P"]
    for modo in ("ignote", "fisse"):
        st = A.mondo(pos, modo, pos["base"] + 2000)
        r = A.continua(pos, st, A.linea_campione(), 2000, modo)
        assert r["winner"] in ("A", "B", "DRAW") and r["returns"] in (0.0, 0.5, 1.0) and r["prefix_ok"]
        assert "storica" in (r["valori"]["fine_turno"] or {"storica": 0}) and r["t9"]["t"] == pos["turno"] + 1
        if r["valori"]["fine_turno"]:
            assert set(r["valori"]["fine_turno"]) == {"storica", "rimonta"}
    # una sequenza completa e una con un'etichetta assente (rilascio con prefisso incompleto)
    ok = A.continua(pos, st, A.linea_sequenza(["Play Trifarian Captain"]), 2000, "fisse")
    assert ok["prefix_ok"] and ok["fallback"] is None
    mancante = A.continua(pos, st, A.linea_sequenza(["Etichetta che non c'e'"]), 2000, "fisse")
    assert not mancante["prefix_ok"] and mancante["fallback"] == "Etichetta che non c'e'"
    # lo stesso mondo e lo stesso seme: stesso esito
    assert A.continua(pos, st, A.linea_campione(), 2000, "fisse")["end_A_B"] == \
        A.continua(pos, st, A.linea_campione(), 2000, "fisse")["end_A_B"]
    assert P["camp"] == "B"


def test_mondo_ignote_tiene_la_mano_del_campione(pos):
    a = A.mondo(pos, "ignote", 123)
    b = A.mondo(pos, "ignote", 124)
    assert a["root"]["B"]["$v"]["hand"] == b["root"]["B"]["$v"]["hand"] == pos["tree"]["root"]["B"]["$v"]["hand"]


def test_posizioni_trova_candidati():
    elenco = A.posizioni(PARTITA)
    assert any(x["k"] == K for x in elenco)
    assert len({x["turno"] for x in elenco}) == len(elenco)
    x = next(x for x in elenco if x["k"] == K)
    assert x["campi"] == [1] and x["punto_libero"] is True and len(x["punti"]) == 2
    assert len(A.scegli_posizioni(elenco, 2)) == min(2, len(elenco))


def test_confronta_da_capo_a_fondo(tmp_path):
    e = A.confronta(PARTITA, K, tmp_path, "campione", "ignote", (2000, 2), (4000, 2), True, 1, lambda *_: None)
    assert e["esito"] in ("attacco migliore", "riferimento migliore", "indeciso", "riferimento scelto")
    for f in ("proposte.json", "scelta.jsonl", "verifica.jsonl", "vista.json", "esito.json", "esito.txt"):
        assert (tmp_path / f).stat().st_size > 0, f
    scelta = [json.loads(x) for x in (tmp_path / "scelta.jsonl").read_text().splitlines()]
    assert [r[0]["world"] for r in scelta] == [2000, 2001] and scelta[0][0]["line"] == A.NOME_RIF
    verifica = [json.loads(x) for x in (tmp_path / "verifica.jsonl").read_text().splitlines()]
    assert [r[0]["world"] for r in verifica] == [4000, 4001]
    assert len(verifica[0]) == (1 if e["migliore"] == A.NOME_RIF else 2)
    proposte = json.loads((tmp_path / "proposte.json").read_text())
    assert all("visite" in p and "q" in p for p in proposte)
    assert (tmp_path / "esito.txt").read_text().count("\n") <= 8
    # il file di Astra con le stesse proposte si confronta con se stesso
    assert A.diff_proposte(proposte, proposte) == []


def test_cli_posizioni_e_proposte(tmp_path, capsys):
    import attacco
    f = tmp_path / "pos.json"
    sys.argv = ["attacco.py", "posizioni", "--autonoma", "ES:4:B", "--iterazioni", str(ITER), "--casuali", "--out", str(f)]
    assert attacco.main() == 0
    k = json.loads(f.read_text())[0]["k"]
    sys.argv = ["attacco.py", "proposte", "--autonoma", "ES:4:B", "--iterazioni", str(ITER), "--casuali", "--k", str(k)]
    assert attacco.main() == 0
    out = capsys.readouterr().out
    assert "p17" in out and "proposte," in out


def test_diff_proposte_ignora_le_chiavi_nuove_del_tavolo():
    """Le proposte di Astra contro sé stesse col tavolo di `tavolo` (base_camp, unita): nessuna differenza
    (Codex, PR 64); una differenza vera in una chiave di Astra resta."""
    pa = json.loads((ROOT / "docs/bot/esperimenti/t9_attacco/dati/proposte.json").read_text(encoding="utf-8"))
    pm = json.loads(json.dumps(pa))
    for p in pm:
        s = p["state"]
        s["base_camp"] = s.pop("base_B")
        s["unita"] = [{"campo": 0, "avversario": s["theirs"], "campione": s["ours"]}]
    assert A.diff_proposte(pm, pa) == []
    pm[3]["state"]["theirs"] = []
    assert len(A.diff_proposte(pm, pa)) == 1
