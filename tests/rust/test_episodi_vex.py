"""§9 di scripts/rust/episodi.py: la classificazione (Vex Apathetic su un campo quando il campione gioca un'unita')
su sequenze di decisioni costruite a mano, senza motore."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/rust"))
import episodi  # noqa: E402

UNITA = {"Fizz Trickster", "Vi Peacekeeper", "Sett Kingpin"}


def ev(turn, label, vex_bf, vex_tot=None, point="turn_action", k=0, proprio=True):
    return {"turn": turn, "proprio": proprio, "vex_bf": vex_bf, "vex_tot": vex_bf if vex_tot is None else vex_tot,
            "gioca": episodi.gioca_unita(label, UNITA), "label": label, "point": point, "k": k}


def test_etichette_che_giocano_unita():
    g = lambda s: episodi.gioca_unita(s, UNITA)  # noqa: E731
    assert g("Play Fizz Trickster") and g("Play Fizz Trickster to BF1") and g("AMBUSH Vi Peacekeeper @BF0")
    assert g("Deploy champion Sett Kingpin")
    assert not g("Play gear Pillaged Armory @BF0") and not g("Cast Rampage @BF1") and not g("Pass")
    assert not g("Play Up from the Deep from trash (FLOW)")


def test_uccisa_dopo_e_sopravvive():
    r = episodi.classifica_vex([
        ev(5, "Play Fizz Trickster to BF0", 1, k=1),
        ev(5, "Move Sett Kingpin base→BF1", 1, k=2),
        ev(5, "Pass", 0, point="showdown_action", k=3),          # la Vex non c'e' piu'
        ev(7, "Play Vi Peacekeeper", 1, k=4),
        ev(7, "Pass", 1, k=5),                                    # c'e' ancora a fine turno
    ])
    assert r["turni_vex"] == 2 and len(r["occasioni"]) == 2
    a, b = r["occasioni"]
    assert (a["esito"], a["tolta"], a["k"]) == ("uccisa", "Move Sett Kingpin base→BF1", 1)
    assert b["esito"] == "sopravvive" and r["ordine_giusto"] == []


def test_ordine_giusto_e_non_osservabile():
    r = episodi.classifica_vex([
        ev(8, "Cast Rampage @BF0", 1, k=7),
        ev(8, "Pass", 0, point="showdown_action", k=8),
        ev(8, "Play Fizz Trickster", 0, k=9),
        ev(10, "Play Vi Peacekeeper", 1, k=10),                  # ultima decisione del turno
    ])
    assert r["ordine_giusto"] == [{"turn": 8, "k": 9, "label": "Play Fizz Trickster"}]
    assert [o["esito"] for o in r["occasioni"]] == ["nd"]


def test_senza_vex_o_giocata_prima_non_e_ordine_giusto():
    r = episodi.classifica_vex([ev(2, "Play Fizz Trickster", 0), ev(2, "Pass", 0)])
    assert r == {"turni_vex": 0, "occasioni": [], "ordine_giusto": []}
    r = episodi.classifica_vex([ev(4, "Play Fizz Trickster", 1), ev(4, "Pass", 0), ev(4, "Play Vi Peacekeeper", 0)])
    assert len(r["occasioni"]) == 1 and r["ordine_giusto"] == []


def test_reazione_in_turno_avversario_e_sonda():
    r = episodi.classifica_vex([ev(6, "AMBUSH Vi Peacekeeper @BF0", 1, proprio=False, point="showdown_action", k=None),
                                ev(6, "Pass", 1, proprio=False, point="showdown_action", k=None)])
    assert r["turni_vex"] == 0 and r["occasioni"][0]["proprio"] is False and r["occasioni"][0]["k"] is None
