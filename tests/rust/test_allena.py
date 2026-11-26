"""Allenamento pilota (riftbound/rs/allena.py) e arena di sviluppo (riftbound/rs/generazione.py): mini raccolta (2 matchup
x 2 partite, 6 iterazioni, pesi casuali), un'epoca da pesi casuali, la rete scritta si ricarica e gioca."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytest.importorskip("riftbound_rs")
torch = pytest.importorskip("torch")

from riftbound.rs import allena, arena_rs, generazione, raccolta  # noqa: E402


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    out = tmp_path_factory.mktemp("mini")
    prima = os.environ.get("RBSIM_REGOLE")
    try:
        raccolta.esegui(out / "raccolta", ["EK", "RS"], 2, 2, None, raccolta.REGOLE_DEFAULT, 6, raccolta.ESPLORAZIONE,
                        200, lambda t: None)
    finally:       # `esegui` scrive l'ambiente: non lo lasciamo ai test dopo
        os.environ.pop("RBSIM_REGOLE", None) if prima is None else os.environ.__setitem__("RBSIM_REGOLE", prima)
    allena.allena(out / "raccolta", out / "allena", None, True, 1, 1e-4, 64, 1.0, 0, "cpu", True, lambda t: None)
    return out


def test_allenamento_scrive_misure_e_rete(mini):
    a = mini / "allena"
    assert (a / "rete.pt").is_file() and (a / "provenienza.json").is_file()
    righe = (a / "misure.txt").read_text().strip().splitlines()
    assert righe[-1].startswith("totale:")
    m = json.loads((a / "misure.json").read_text())
    f = m["finale"]["verifica"]
    assert {"politica_ce", "kl", "top1_con_la_piu_visitata", "valore_eqm", "valore_segno"} <= set(f["decisioni"])
    assert {"valore_eqm", "valore_segno"} <= set(f["stati_fine_turno"]) and "decisioni_partenza" in f


def test_la_rete_si_ricarica_e_gioca(mini, monkeypatch):
    monkeypatch.setenv("RBSIM_REGOLE", raccolta.REGOLE_DEFAULT)
    rete = str(mini / "allena" / "rete.pt")
    for vr in (0.0, 0.2):
        r = arena_rs.game((31, "a", "A", "prior_ppo", rete, "prior_ppo", rete, "EK", None, None,
                           {"iter_cand": 6, "iter_opp": 6, "vr_cand": vr}))
        assert r[3] in (0.0, 0.5, 1.0)


def test_arena_di_sviluppo_registra_avanzamento(mini, monkeypatch):
    monkeypatch.setenv("RBSIM_REGOLE", raccolta.REGOLE_DEFAULT)
    rete = str(mini / "allena" / "rete.pt")
    messaggi = []
    res = generazione.arena(rete, rete, ["EK", "RS"], 3, raccolta.REGOLE_DEFAULT, mini / "righe.jsonl", 2, 6,
                            ("b", "c"), messaggi.append)
    assert any("20/24 partite" in riga for riga in messaggi)
    assert set(res["varianti"]) == {"b", "c"} and 0.0 <= res["varianti"]["c"]["totale"][0] <= 1.0
    assert res["varianti"]["c"]["chiamate_rete"]["candidato"][0] > 0
    assert generazione.testo_arena(res)[-1].startswith("durata")


@pytest.mark.parametrize("vuoto", ["sviluppo", "verifica"])
def test_allenamento_richiede_entrambi_gli_insiemi(tmp_path, monkeypatch, vuoto):
    # Anche con stati per il valore, senza decisioni non si puo' misurare la politica.
    dati = {k: {"dec": [] if k == vuoto else [object()], "stati": {"x": [object()]}}
            for k in ("allenamento", "sviluppo", "verifica")}
    monkeypatch.setattr(allena, "carica_dati", lambda *a, **kw: dati)
    with pytest.raises(SystemExit, match=vuoto):
        allena.allena(tmp_path, tmp_path, None, casuali=True, scegli_dispositivo="cpu")
    assert not (tmp_path / "rete.pt").exists()


def test_arena_ripresa_solo_con_gli_stessi_pesi_e_impostazioni(mini, tmp_path):
    rete = mini / "allena" / "rete.pt"
    altra = tmp_path / "copia.pt"
    altra.write_bytes(rete.read_bytes())
    righe = tmp_path / "arena.jsonl"

    def avvia(**opzioni):
        args = dict(rete=str(altra), campione=str(rete), matchup=["EK"], coppie=1,
                    regole=raccolta.REGOLE_DEFAULT, righe=righe, processi=1, iterazioni=6, varianti=("b",))
        args.update(opzioni)
        return generazione.arena(**args)

    prima = avvia()
    partite = righe.read_bytes()
    # Zero worker costringe la prova a fallire se si tenta di rigiocare una partita.
    seconda = avvia(rete=str(rete), campione=str(altra), processi=0)
    assert seconda["varianti"] == prima["varianti"]
    for modifiche in ({"regole": "6427b90"}, {"iterazioni": 8}):
        with pytest.raises(ValueError, match="incompatibile"):
            avvia(**modifiche)
    altra.write_bytes(b"checkpoint cambiato allo stesso percorso")
    for modifiche in ({}, {"rete": str(rete), "campione": str(altra)}):
        with pytest.raises(ValueError, match="incompatibile"):
            avvia(**modifiche)
    assert righe.read_bytes() == partite
    righe.with_name(righe.name + ".provenienza.json").unlink()
    with pytest.raises(ValueError, match="senza provenienza"):
        avvia()
    assert righe.read_bytes() == partite
