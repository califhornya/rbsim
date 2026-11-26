"""Valutazione "accumulo" delle foglie della ricerca (SearchCore.valutazione, opt-in, default storica).
(a) il default e "storica" danno le stesse decisioni; (b)/(c) posizioni costruite (valore_costruito)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _vuota():
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import rust_bridge as rb
    return rb.build(1, Path(DECK_OF["E"]), Path(DECK_OF["K"]), "a", 10)


def _v(g, nome, bfs, my_base, opp_base):
    return g.valore_costruito(nome, bfs, my_base, opp_base, 3.0, 0.2)


# BF0: lo spettatore (A) lo controlla con Might 10 e nessun nemico; BF1: lo controlla l'avversario.
def _posizione(unita_su_bf0, opp_base):
    bf0 = [10, 3] if unita_su_bf0 else [10]
    return ([("me", bf0, []), ("opp", [], [4])], [] if unita_su_bf0 else [3], opp_base)


def test_b_base_vuota_avversaria_accumulo_preferisce_la_base():
    g = _vuota()
    su_bf, in_base = _posizione(True, []), _posizione(False, [])
    assert _v(g, "accumulo", *in_base) > _v(g, "accumulo", *su_bf)
    assert _v(g, "storica", *su_bf) > _v(g, "storica", *in_base)


def test_c_avversario_con_molta_base_il_rinforzo_vale_ancora():
    g = _vuota()
    su_bf, in_base = _posizione(True, [12]), _posizione(False, [12])
    assert _v(g, "accumulo", *su_bf) >= _v(g, "accumulo", *in_base)


def test_storica_coincide_con_il_default_su_posizioni_con_nemici():
    # campo conteso o dell'avversario: accumulo e storica danno lo stesso valore
    g = _vuota()
    p = ([("me", [10], [2]), ("opp", [], [4])], [3], [])
    assert _v(g, "accumulo", *p) == _v(g, "storica", *p)


def test_nome_sconosciuto():
    with pytest.raises(ValueError):
        _vuota().valore_costruito("boh", [], [], [])


def _log(valutazione, seed):
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import rust_bridge as rb
    g = rb.build(seed, Path(DECK_OF["E"]), Path(DECK_OF["K"]), "a", 12)
    for s in ("A", "B"):
        g.set_search_agent(s, 25, seed * 2 + (s == "B"), None, None, True)
        if valutazione:
            g.set_search_valutazione(s, *valutazione)
    g.set_side_chooser()
    g.start()
    # gli id di carta (#N) vengono da un contatore del processo: si tolgono
    return re.sub(r"#\d+", "#", g.search_log("A") + g.search_log("B"))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_storica_identica_al_default(seed):
    assert _log(None, seed) == _log(("storica", 3.0, 0.2), seed)


def test_accumulo_e_collegato():
    # su alcuni semi il log con accumulo differisce (altrimenti l'opzione non farebbe nulla)
    assert any(_log(None, s) != _log(("accumulo", 3.0, 0.2), s) for s in (1, 2, 3, 4))


# ---- minaccia / corsa (posizioni costruite; punti, chi e' attivo e GANKING nei parametri opzionali) ----

def _an(g, bfs, my_base=(), opp_base=(), punti=(0, 0), attivo="me", gank=()):
    return g.analisi_costruita(bfs, list(my_base), list(opp_base), punti, attivo, list(gank))


def _val(g, nome, bfs, my_base, opp_base, punti, attivo):
    return g.valore_costruito(nome, bfs, my_base, opp_base, 3.0, 0.2, punti, attivo)


UNO_CIASCUNO = [("me", [10], []), ("opp", [], [2])]


def test_corsa_6_6_tocca_all_avversario_perde():
    # attivo = io: la prossima Beginning Phase e' dell'avversario, che arriva a 8 per primo
    race, onw, _ = _an(_vuota(), UNO_CIASCUNO, punti=(6, 6), attivo="me")
    assert (race, onw) == (-1, False)


def test_corsa_7_6_tocca_a_me_vinco():
    race, onw, _ = _an(_vuota(), UNO_CIASCUNO, punti=(7, 6), attivo="opp")
    assert (race, onw) == (1, False)


def test_corsa_7_7_avversario_vince_subito():
    race, onw, _ = _an(_vuota(), UNO_CIASCUNO, punti=(7, 7), attivo="me")
    assert (race, onw) == (-1, True)


def test_corsa_nessuno_segna_e_minaccia_con_ganking():
    g = _vuota()
    assert _an(g, [(None, [], []), (None, [], [])])[0] == 0
    # nessun attaccante: minaccia 0; con una base di 5 contro D=2 e' > 0.5; un GANKING su un altro campo conta
    assert _an(g, UNO_CIASCUNO)[2] == 0.0
    assert _an(g, UNO_CIASCUNO, my_base=[5])[2] > 0.5
    t_base, t_gank = _an(g, UNO_CIASCUNO, my_base=[1])[2], _an(g, UNO_CIASCUNO, my_base=[1], gank=[(0, 4)])[2]
    assert t_gank > t_base


# Caso 1: perdo la corsa (6-6, tocca a loro) e posso contestare: l'unita' (3) in base fa A=3 > D=2.
def _caso(unita_su_bf, opp_base=()):
    bfs = [("me", [10, 3] if unita_su_bf else [10], []), ("opp", [], [2])]
    return bfs, ([] if unita_su_bf else [3]), list(opp_base)


@pytest.mark.parametrize("nome", ["minaccia", "corsa"])
def test_caso1_corsa_persa_unita_in_base_batte_unita_accumulata(nome):
    g = _vuota()
    punti, att = (6, 6), "me"
    su, base = _caso(True), _caso(False)
    assert _val(g, "storica", *su, punti, att) > _val(g, "storica", *base, punti, att)
    assert _val(g, nome, *base, punti, att) > _val(g, nome, *su, punti, att)


def test_caso2_corsa_vinta_il_rinforzo_regge_la_base():
    g = _vuota()
    punti, att = (7, 5), "opp"  # tocca a me: 8 per primo
    assert _an(g, _caso(False)[0], [3], [4], punti, att)[0] == 1
    su, base = _caso(True, [4]), _caso(False, [4])
    assert _val(g, "corsa", *su, punti, att) >= _val(g, "corsa", *base, punti, att)


@pytest.mark.parametrize("nome", ["minaccia", "corsa"])
def test_caso3_se_la_minaccia_non_cambia_l_esito_non_c_e_premio(nome):
    g = _vuota()
    punti, att = (7, 7), "me"  # l'avversario vince alla sua tenuta
    su, base = _caso(True), _caso(False)
    assert _an(g, base[0], [3], [], punti, att)[1:] == (True, 0.0)
    for p in (su, base):
        assert _val(g, nome, *p, punti, att) == _val(g, "storica", *p, punti, att)


def test_nomi_minaccia_corsa_collegati_alle_partite():
    assert any(_log(None, s) != _log(("minaccia", 3.0, 0.2), s) for s in (1, 2, 3, 4))
    assert any(_log(None, s) != _log(("corsa", 3.0, 0.2), s) for s in (1, 2, 3, 4))


def test_valutazione_orig_entra_nella_partita_autonoma():
    import sys
    sys.path.insert(0, str(ROOT / "scripts/rust"))
    import decisione
    import argparse
    a = argparse.Namespace(pagina=None, autonoma="ES:3:a", iter_orig=138, campione="A", ckpt=None, pesi_casuali=False,
                           valutazione_orig="accumulo:3.0:0.2")
    assert decisione.partita_da_args(a)["valutazione"] == ("accumulo", 3.0, 0.2)
    a.valutazione_orig = "corsa:3.0:0.2"
    assert decisione.partita_da_args(a)["valutazione"][0] == "corsa"
    a.valutazione_orig = None
    assert "valutazione" not in decisione.partita_da_args(a)


# ---- rimonta: attiva solo se si perde la corsa (race -1) e l'avversario non vince subito ----

def test_rimonta_fuori_dallo_stato_e_uguale_alla_storica():
    g = _vuota()
    su, base = _caso(True), _caso(False)
    for punti, att in (((7, 5), "opp"), ((7, 7), "me")):  # race +1, op_next_wins
        for p in (su, base, _caso(False, [4])):
            assert _val(g, "rimonta", *p, punti, att) == _val(g, "storica", *p, punti, att)
    assert _an(g, UNO_CIASCUNO, punti=(7, 5), attivo="opp")[0] == 1
    assert _an(g, UNO_CIASCUNO, punti=(7, 7), attivo="me")[1] is True
    nessuno = [(None, [], []), (None, [], [])]
    assert _val(g, "rimonta", nessuno, [3], [], (0, 0), "me") == _val(g, "storica", nessuno, [3], [], (0, 0), "me")


def test_rimonta_storica_invariata_e_default():
    g = _vuota()
    p = _caso(True)
    assert _val(g, "storica", *p, (6, 6), "me") == g.valore_costruito("storica", *p, 3.0, 0.2, (6, 6), "me")


def test_rimonta_corsa_persa_base_batte_accumulo_con_margine_gia_sufficiente():
    g = _vuota()
    punti, att = (6, 6), "me"
    su, base = _caso(True), _caso(False)  # opp_base vuota: need = 3, margine 10 >= 3
    assert _an(g, base[0], [3], [], punti, att)[:2] == (-1, False)
    assert _val(g, "storica", *su, punti, att) > _val(g, "storica", *base, punti, att)
    assert _val(g, "rimonta", *base, punti, att) > _val(g, "rimonta", *su, punti, att)


def test_rimonta_corsa_persa_campo_minacciato_il_rinforzo_regge():
    g = _vuota()
    punti, att = (6, 6), "me"
    su, base = _caso(True, [12]), _caso(False, [12])  # need = 15 > 10: il rinforzo conta per intero
    assert _val(g, "rimonta", *su, punti, att) >= _val(g, "rimonta", *base, punti, att)


def test_rifai_valutazione_storica_esplicita_e_un_override(monkeypatch):
    """Review PR 55: --valutazione storica esplicita con --valutazione-orig non storica rifa' la decisione con
    la storica (prima era ignorata); omessa, la decisione tiene la valutazione originale."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts/rust"))
    import decisione
    from riftbound.rs import decisione_rs as D
    viste = []

    def finta(P, k, n, posizione=True, valutazione=None, **_resto):
        viste.append((n, valutazione, P.get("valutazione")))
        return {"riproduce": True, "prefisso_ok": True, "dopo_sonda": False, "posizione": {}, "azione": "x", "uguale": True,
                "classifica": [], "iterazioni": n}

    monkeypatch.setattr(D, "rifai", finta)
    monkeypatch.setattr(D, "elenca", lambda P: [{"turn": 1, "point": "turn_action", "n_menu": 2, "action": "a"}])
    monkeypatch.setattr(D, "_prepara", lambda P: {"iterazioni": 138})
    monkeypatch.setattr(D, "testo_posizione", lambda p: [])
    base = ["rifai", "--autonoma", "ES:3:a", "--k", "0", "--valutazione-orig", "rimonta", "--iterazioni", "138", "200"]
    decisione.main(base + ["--valutazione", "storica"])
    esplicita = [v for n, v, _ in viste if n == 200]
    assert esplicita == [("storica", 3.0, 0.2)] and viste[-1][2][0] == "rimonta"   # prefisso: ancora rimonta
    viste.clear()
    decisione.main(base)
    assert [v for n, v, _ in viste if n == 200] == [None]
