"""Seguiti (riftbound/rs/seguiti.py): riepilogo su dati finti, fase 2 su una decisione vera, corsa da capo a fondo
con prior e valore a pesi casuali."""
from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import seguiti as S  # noqa: E402


@pytest.fixture(scope="module")
def valore(tmp_path_factory):
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(1)
    p = tmp_path_factory.mktemp("valore") / "rete.pt"
    save(PPONet().eval(), p)
    return str(p)


def _r(mu, ok, dis, media, n=4):
    return {"matchup": mu, "prefisso_ok": ok, "disaccordo": dis, "media": media, "n_mondi": n if media is not None else 0}


def test_riassunto():
    rows = [_r("EK", True, True, 0.5), _r("EK", True, True, -0.25), _r("EK", True, False, None),
            _r("ES", True, True, 0.0), _r("ES", False, False, None), _r("ES", True, True, None, 0)]
    r = S.riassunto(rows, 2000)
    assert r["esaminate"] == 6 and r["escluse"] == 1 and r["disaccordi"] == 4 and r["n_decisioni"] == 3
    assert r["media"] == pytest.approx(0.25 / 3)
    assert r["ic95"][0] <= r["media"] <= r["ic95"][1]
    assert (r["a_favore"], r["contro"], r["pari"]) == (1, 1, 1)
    assert r["tasso_disaccordo"] == pytest.approx(4 / 5)
    assert r["per_matchup"]["EK"]["disaccordi"] == 2 and r["per_matchup"]["EK"]["media"] == pytest.approx(0.125)
    assert r["per_matchup"]["ES"]["escluse"] == 1 and r["per_matchup"]["ES"]["media"] == 0.0
    assert S.riassunto([], 10)["media"] is None


def test_fase_due_su_una_decisione(tmp_path):
    partita = D.autonoma("ES", 4, None, True, 8, "B", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
    P = D._prepara(partita)
    o = next(x for x in D.originale(partita) if x["seat"] == P["camp"] and x["point"] == "turn_action"
             and len(x["menu"]) >= 2)
    dec = {"partita": partita, "nome": A.nome_partita(partita), "k": o["k"], "turno": o["turn"], "menu": o["menu"],
           "campione": o["menu"][0], "d": o["menu"][1], "prefisso_ok": True, "classifica": []}
    res = S.gioca_decisione(dec, 2, tmp_path / "d", 1)
    assert len(res["deltas"]) + res["mondi_esclusi"] == 2 and res["n_mondi"] == len(res["deltas"])
    assert all(x in (-1.0, -0.5, 0.0, 0.5, 1.0) for x in res["deltas"])
    f = json.loads((tmp_path / "d" / "decisione.json").read_text())
    assert f["deltas"] == res["deltas"] and (tmp_path / "d" / "mondi.jsonl").exists()


def test_da_capo_a_fondo_e_ripresa(tmp_path, valore, monkeypatch):
    righe = S.seguiti(["EK"], 1, 2, 2, tmp_path, None, valore, casuali=True, iterazioni=20, n_boot=200,
                      print_=lambda *_: None)
    assert righe[-1].startswith("totale:")
    assert (tmp_path / "riepilogo.txt").read_text().splitlines()[-1].startswith("totale:")
    assert len((tmp_path / "decisioni.jsonl").read_text().splitlines()) == 1
    assert json.loads((tmp_path / "riepilogo.json").read_text())["riassunto"]["esaminate"] == 2

    def no(*_a, **_k):
        raise AssertionError("lavoro rifatto")
    monkeypatch.setattr(D, "rifai", no)
    monkeypatch.setattr(A, "esegui", no)
    righe2 = S.seguiti(["EK"], 1, 2, 2, tmp_path, None, valore, casuali=True, iterazioni=20, n_boot=200,
                       print_=lambda *_: None)
    assert righe2[-1].startswith("totale:")
