"""Scelta finale (riftbound/rs/scelta.py): scelte e riepilogo su dati finti, una partita vera con pesi casuali, la
corsa da capo a fondo con ripresa, l'arena piccola con rifiuto di impostazioni diverse."""
from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import scelta as C  # noqa: E402
from riftbound.rs import seguiti as S  # noqa: E402


def _o(children, giocata, etichette=("x", "y", "z", "w")):
    """Riga finta: i figli sono (indice nel menu, n, q); il menu ha azioni 'a0'.. e le etichette date."""
    menu = [f"a{i}" for i in range(len(etichette))]
    ch = [[menu[i], n, q, 0.0, []] for i, n, q in children]
    return {"k": 3, "turn": 2, "action": giocata, "menu": list(etichette), "riga": {"menu": menu, "children": ch}}


def test_scelte_pareggi_e_coerenza():
    # Q: pari massimo fra x e z -> il primo (x); visite: y e z pari (5), q piu' alta -> z
    r = C.scelte(_o([(0, 3, 0.6), (1, 5, 0.4), (2, 5, 0.6)], "x"))
    assert (r["q"], r["visite"]) == ("x", "z") and r["coerente"] and r["disaccordo"]
    # visite pari e q pari: il primo
    r = C.scelte(_o([(0, 4, 0.5), (1, 4, 0.5)], "x"))
    assert (r["q"], r["visite"]) == ("x", "x") and not r["disaccordo"]
    # figli con n = 0 ignorati, anche se con q alta; ordine dei figli != ordine del menu
    r = C.scelte(_o([(2, 0, 0.99), (1, 2, 0.1), (0, 1, 0.3)], "x"))
    assert (r["q"], r["visite"]) == ("x", "y") and r["n_q"] == 1 and r["n_v"] == 2 and r["disaccordo"]
    # incoerente: la mossa giocata non e' la scelta per Q -> niente disaccordo contato
    r = C.scelte(_o([(0, 3, 0.6), (1, 5, 0.4)], "y"))
    assert not r["coerente"] and not r["disaccordo"]


def _r(mu, nome, dis, media, coerente=True, n=4):
    return {"matchup": mu, "nome": nome, "coerente": coerente, "disaccordo": dis, "media": media,
            "n_mondi": n if media is not None else 0, "mondi_esclusi": 0}


def _righe():
    rows = []
    for g in range(6):      # EK: 6 partite, un disaccordo a favore in meta' delle partite, il resto accordi
        rows += [_r("EK", f"EK{g}", g % 2 == 0, 0.5 if g % 2 == 0 else None), _r("EK", f"EK{g}", False, None)]
    for g in range(4):      # ES: solo accordi (zeri) piu' un disaccordo contro
        rows += [_r("ES", f"ES{g}", False, None)]
    rows += [_r("ES", "ES0", True, -0.25), _r("ES", "ES1", True, None, n=0), _r("ES", "ES2", False, None, coerente=False)]
    return rows


def test_riassunto_pesi_zeri_e_cluster():
    rows = _righe()
    r = C.riassunto(rows, 2000)
    # EK: 12 decisioni, somma 1.5 -> 0.125; ES: 5 valide (4 accordi + 1 contro) somma -0.25 -> -0.05
    assert r["per_matchup"]["EK"]["media"] == pytest.approx(1.5 / 12)
    assert r["per_matchup"]["ES"]["media"] == pytest.approx(-0.25 / 5)
    assert r["totale"][0] == pytest.approx((1.5 / 12 - 0.05) / 2)
    assert r["incoerenti"] == 1 and r["senza_mondi"] == 1 and r["n_decisioni"] == 17
    assert r["totale"][1] <= r["totale"][0] <= r["totale"][2]
    assert r["media_disaccordi"] == pytest.approx((1.5 - 0.25) / 4)
    assert (r["a_favore"], r["contro"], r["pari"]) == (3, 1, 0)
    assert r == C.riassunto(rows, 2000)                      # deterministico
    assert r["per_matchup"]["EK"]["tasso_disaccordo"] == pytest.approx(3 / 12)


def test_regola_di_stop():
    su = [_r("EK", f"EK{g}", True, 0.5) for g in range(8)]
    assert C.riassunto(su, 500)["passa"] is True
    giu = [_r("EK", f"EK{g}", True, -0.5) for g in range(8)] + [_r("EK", "EKx", False, None)]
    assert C.riassunto(giu, 500)["passa"] is False
    misto = [_r("EK", f"EK{g}", True, 0.5 if g % 2 else -0.5) for g in range(8)]
    assert C.riassunto(misto, 500)["passa"] is False         # IC a cavallo di zero


def test_partita_vera_coerente_e_stesse_posizioni():
    partita = D.autonoma("EK", 4, None, True, 40, "A", valutazione=D._valutazione_registrata("rimonta"), entrambi=True)
    sel = S.selezionate(partita, 4)
    ds = C.decisioni(partita, 4)
    assert [d["k"] for d in ds] == [o["k"] for o in sel] and len(ds) >= 1
    assert all(d["coerente"] for d in ds)
    assert all(d["q"] in d["menu"] and d["visite"] in d["menu"] for d in ds)


@pytest.fixture(scope="module")
def corsa(tmp_path_factory):
    out = tmp_path_factory.mktemp("scelta")
    righe = C.posizioni(["EK"], 1, 4, 2, out, None, casuali=True, iterazioni=40, n_boot=200, print_=lambda *_: None)
    return out, righe


def test_da_capo_a_fondo_e_ripresa(corsa, monkeypatch):
    out, righe = corsa
    assert righe[-1].startswith("totale:")
    assert (out / "riepilogo.txt").read_text().splitlines()[-1].startswith("totale:")
    esito = json.loads((out / "esito.json").read_text())
    assert isinstance(esito["passa"], bool) and len(esito["totale"]) == 3
    assert any(x.startswith("regola di stop:") for x in righe)
    assert json.loads((out / "riepilogo.json").read_text())["riassunto"]["esaminate"] >= 1

    def no(*_a, **_k):
        raise AssertionError("lavoro rifatto")
    monkeypatch.setattr(D, "originale", no)
    monkeypatch.setattr(A, "esegui", no)
    righe2 = C.posizioni(["EK"], 1, 4, 2, out, None, casuali=True, iterazioni=40, n_boot=200, print_=lambda *_: None)
    assert righe2[-1].startswith("totale:")
    with pytest.raises(ValueError):
        C.posizioni(["EK"], 1, 4, 3, out, None, casuali=True, iterazioni=40, print_=lambda *_: None)


def test_fase_due_diretta(tmp_path):
    """Con etichette distinte forzate (come test_seguiti), anche se la corsa non ha avuto disaccordi."""
    partita = D.autonoma("ES", 4, None, True, 8, "B", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
    o = S.selezionate(partita, 1)[0]
    dec = {"partita": partita, "nome": A.nome_partita(partita), "k": o["k"], "turno": o["turn"], "menu": o["menu"],
           "q": o["menu"][0], "visite": o["menu"][1], "n_q": 1, "q_q": 0.0, "n_v": 2, "q_v": 0.0}
    res = C.gioca_decisione(dec, 2, tmp_path / "d", 1)
    assert len(res["deltas"]) + res["mondi_esclusi"] == 2 and res["n_mondi"] == len(res["deltas"])
    assert all(x in (-1.0, -0.5, 0.0, 0.5, 1.0) for x in res["deltas"])
    assert json.loads((tmp_path / "d" / "decisione.json").read_text())["deltas"] == res["deltas"]


def test_arena_piccola(tmp_path):
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(2)
    ck = tmp_path / "rete.pt"
    save(PPONet().eval(), ck)
    righe = C.arena(["EK"], 1, tmp_path / "arena", ck, iterazioni=10, n_boot=100, print_=lambda *_: None)
    assert (tmp_path / "arena" / "arena.txt").exists() and any(x.startswith("criterio:") for x in righe)
    assert len((tmp_path / "arena" / "arena_righe.jsonl").read_text().splitlines()) == 2
    assert isinstance(json.loads((tmp_path / "arena" / "arena.json").read_text())["promuovibile"], bool)
    with pytest.raises(ValueError):
        C.arena(["EK"], 1, tmp_path / "arena", ck, iterazioni=11, print_=lambda *_: None)
