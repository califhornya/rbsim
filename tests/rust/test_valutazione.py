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
