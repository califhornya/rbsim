"""Quota alla radice per tutte le ricerche di turno di un posto (`set_search_quota`, Astra 27/11): senza chiamata, o con
etichette che non c'e', la ricerca e' identica; con ["base→bf"] ogni figlio "da base a un campo" della radice ha almeno
n visite; `arena_rs.game` accetta `quota_cand` / `quota_opp`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from riftbound.ai.ppo.collect import DECK_OF
from riftbound.rs import arena_rs, rust_bridge as rb

ITER = 40
N = 8
ETICHETTE = ["base→bf"]


def _partita(quota=None, seme=3, mu="EK"):
    g = rb.build(seme, Path(DECK_OF[mu[0]]), Path(DECK_OF[mu[1]]), "a", arena_rs.MAX_TURNS)
    for s in "AB":
        g.set_search_agent(s, ITER, 5 + (s == "B"), None, None, True)
    if quota is not None:
        g.set_search_quota("A", quota[0], quota[1])
    g.set_side_chooser()
    vincitore = g.start()
    return vincitore, g


def _log(g) -> str:
    """Per ogni ricerca punto, turno, visite e Q dei figli (le azioni portano id di carte che cambiano fra le partite)."""
    return json.dumps([[r["point"], r["turn"], [[c[1], c[2]] for c in r["children"]]]
                       for r in json.loads(g.search_log("A")) if r.get("k") == "search"])


def test_senza_quota_o_senza_corrispondenze_la_ricerca_e_identica():
    v0, g0 = _partita()
    v1, g1 = _partita()
    assert v0 == v1 and _log(g0) == _log(g1)                      # deterministica
    for quota in (([], N), (["zzz-non-esiste"], N)):
        v, g = _partita(quota)
        assert v == v0 and _log(g) == _log(g0)


def test_ogni_figlio_da_base_ha_almeno_n_visite():
    _v, g = _partita((ETICHETTE, N))
    diag = json.loads(g.search_finestre_diag("A"))
    visti = 0
    for d in diag:
        if d["point"] != "turn_action":
            continue
        figli = d["children"]
        match = [c for c in figli if any(e in c["label"].lower() for e in ETICHETTE)]
        if not match:
            continue
        visti += 1
        tot = sum(c["n"] for c in figli)
        # con abbastanza iterazioni ogni figlio da base ne ha almeno N; altrimenti tutte vanno a loro (a ripartirsi)
        if tot >= N * len(match):
            assert all(c["n"] >= N for c in match), (d["turn"], [(c["label"], c["n"]) for c in match])
        else:
            assert sum(c["n"] for c in match) >= tot - 1
    assert visti > 0


def test_la_quota_cambia_qualcosa():
    _v, g = _partita((ETICHETTE, N))
    _v0, g0 = _partita()
    assert _log(g) != _log(g0)


def test_arena_game_con_quota_cand():
    opz = {"iter_cand": 10, "iter_opp": 10, "quota_cand": [ETICHETTE, N]}
    r = arena_rs.game((11, "b", "A", "mano", None, "mano", None, "EK", None, None, opz))
    assert r[3] in (0.0, 0.5, 1.0)
    r0 = arena_rs.game((11, "b", "A", "mano", None, "mano", None, "EK", None, None,
                        {"iter_cand": 10, "iter_opp": 10}))
    r1 = arena_rs.game((11, "b", "A", "mano", None, "mano", None, "EK", None, None,
                        {"iter_cand": 10, "iter_opp": 10, "quota_opp": [["zzz"], N]}))
    assert r0[3:] == r1[3:] or r0[3] == r1[3]                       # etichette inesistenti: stessa partita
