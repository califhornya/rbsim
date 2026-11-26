"""Prior da una rete e valore da un'altra (arena_rs.make_probs_misto, Astra 26/11) e peso del valore solo alla
ricerca k (set_search_valore_rete_at, decisione_rs.rifai(valore_rete=...)); opzione `entrambi` delle partite autonome."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/rust"))

pytest.importorskip("riftbound_rs")
torch = pytest.importorskip("torch")

from riftbound.ai.ppo.collect import DECK_OF  # noqa: E402
from riftbound.rs import arena_rs, decisione_rs as D, rust_bridge as rb  # noqa: E402

REGOLE = "6427b90+D72-D83"


def _net(seme):
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(seme)
    return PPONet().eval()


@pytest.fixture(scope="module")
def reti(tmp_path_factory):
    from riftbound.ai.ppo.model import save
    d = tmp_path_factory.mktemp("reti")
    a, b = _net(0), _net(1)
    save(a, d / "a.pt")
    save(b, d / "b.pt")
    return a, b, str(d / "a.pt"), str(d / "b.pt")


def _partita(probs, peso=None, at=None, seme=31, iters=6):
    g = rb.build(seme, Path(DECK_OF["E"]), Path(DECK_OF["K"]), "a", 40, REGOLE)
    for seat in "AB":
        g.set_search_agent(seat, iters, seme * 2 + (seat == "B"), None, probs, True)
        g.set_search_win_probe(seat, True)
        g.set_search_valutazione(seat, "rimonta", 3.0, 0.2)
        if peso is not None:
            g.set_search_valore_rete(seat, peso)
        if at is not None:
            g.set_search_valore_rete_at(seat, *at)
    g.set_side_chooser()
    return g, g.start()


def _logs(g):
    return [json.loads(re.sub(r"#\d+", "#", g.search_log(s))) for s in "AB"]


def test_misto_stessa_rete_uguale_a_valore(reti):
    a = reti[0]
    g0, r0 = _partita(arena_rs.make_probs_valore(a), 0.2)
    g1, r1 = _partita(arena_rs.make_probs_misto(a, a), 0.2)
    assert r0 == r1 and _logs(g0) == _logs(g1)


def test_misto_peso_zero_uguale_a_prior(reti):
    a, b = reti[:2]
    g0, r0 = _partita(arena_rs.make_probs(a))
    g1, r1 = _partita(arena_rs.make_probs_misto(a, b))
    assert r0 == r1 and _logs(g0) == _logs(g1)


def test_misto_usa_il_valore_dell_altra_rete(reti):
    a, b = reti[:2]
    g0, _ = _partita(arena_rs.make_probs_misto(a, a), 0.2)
    g1, _ = _partita(arena_rs.make_probs_misto(a, b), 0.2)
    assert all(g1.search_valore_rete_stats(s)[0] > 0 for s in "AB")
    assert _logs(g0) != _logs(g1)


def test_valore_rete_at(reti):
    a, b = reti[:2]
    probs = arena_rs.make_probs_misto(a, b)
    g0, r0 = _partita(probs)
    g1, r1 = _partita(probs, at=(1000, 0.2))      # k mai raggiunto
    assert r0 == r1 and _logs(g0) == _logs(g1)
    g2, _ = _partita(probs, at=(2, 0.0))
    assert _logs(g0) == _logs(g2)
    g3, r3 = _partita(probs, at=(2, 0.2))
    assert r3[0] in ("A", "B", "DRAW")
    for s, l0, l3 in zip("AB", _logs(g0), _logs(g3)):
        rows0 = [x for x in l0 if x["k"] == "search"]
        rows3 = [x for x in l3 if x["k"] == "search"]
        # la ricerca k=2 e' la terza ricerca del posto che la fa: quelle prima restano identiche
        assert rows0[:2] == rows3[:2]


def _autonoma(ckpt, **extra):
    return D.autonoma("EK", 300, ckpt=ckpt, iterazioni=8, regole=REGOLE,
                      valutazione=D._valutazione_registrata("rimonta"), **extra)


def test_decisione_rifai_valore_rete(reti):
    pa, pb = reti[2:]
    partita = _autonoma(pa)
    orig = D.originale(partita)
    ks = [o["k"] for o in orig if o["point"] == "turn_action" and len(o["menu"]) >= 2]
    assert ks
    k = ks[0]
    r = D.rifai(partita, k, posizione=False, valore_rete=(0.2, pb))
    assert r["prefisso_ok"]
    r0 = D.rifai(partita, k, posizione=False, valore_rete=(0.0, pb))
    assert r0["prefisso_ok"] and r0["azione"] == r0["azione_originale"]


def test_entrambi(reti):
    pa = reti[2]
    base = _autonoma(pa)
    assert "entrambi" not in D._prepara(base)
    assert "entrambi" in D._prepara(_autonoma(pa, entrambi=True))
    assert D.originale(_autonoma(pa, entrambi=True))
