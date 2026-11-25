"""L'apertura della pagina (campo di battaglia coperto, d20, chi comincia) su entrambi i motori:
CoachSession.new_game(apertura=True) -> scegli_campo -> inizia, poi mulligan; il rewind tiene
gli stessi campi e lo stesso primo giocatore."""
from __future__ import annotations

import random
import time

import pytest

pytest.importorskip("torch")

from riftbound.ai import apertura as ap  # noqa: E402
from riftbound.ai.coach import CoachSession  # noqa: E402

MOTORI = ("rust", "python")


def _deck(letter):
    from riftbound.ai.ppo.collect import DECK_OF
    return DECK_OF[letter]


def _session(tmp_path, motore):
    return CoachSession(None, tmp_path / "coach", opponent_pause=0, motore=motore)


def _new(s, seed, seat="A"):
    s.new_game(_deck("E"), _deck("K"), seat=seat, opponent="simple_trade", seed=seed, apertura=True)


def _seed(tmp_path, motore, chi, seat="A"):
    """Un seme in cui il d20 lo vince `chi` ("io" / "avv")."""
    for seed in range(1, 80):
        s = _session(tmp_path / f"p{seed}", motore)
        _new(s, seed, seat)
        s.scegli_campo("random")
        if s.state()["apertura"]["chi_decide"] == chi:
            return seed
    raise AssertionError("nessun seme")


def _wait(s, timeout=120.0):
    end = time.time() + timeout
    while time.time() < end:
        st = s.state()
        if st["status"] == "over" or (st["status"] == "waiting" and st["pending"]):
            return st
        time.sleep(0.003)
    raise AssertionError("niente domanda")


def _campi(st):
    return sorted(b["named"] for b in st["observation"]["battlefields"])


def test_scelta_campo_coperta_e_tiro(tmp_path):
    s = _session(tmp_path, "rust")
    _new(s, 7)
    st = s.state()
    a = st["apertura"]
    assert st["status"] == "opening" and a["step"] == "campo" and len(a["mine"]) == 3
    assert a["opp"] is None and a["opp_n"] == 3 and a["bf_opp"] is None      # il suo campo e' coperto
    assert all(st["cards"][n]["img"] for n in a["mine"])
    with pytest.raises(ValueError):
        s.scegli_campo("Campo che non c'e'")
    s.scegli_campo(a["mine"][1])
    a = s.state()["apertura"]
    assert a["step"] == "tiro" and a["bf_mine"] == a["mine"][1] and a["bf_opp"] and a["opp"] == a["bf_opp"]
    t = a["tiri"]
    assert all(1 <= x <= 20 for r in t for x in r) and all(r[0] == r[1] for r in t[:-1]) and t[-1][0] != t[-1][1]
    assert a["chi_decide"] == ("io" if t[-1][0] > t[-1][1] else "avv")
    texts = [e["text"] for e in s.state()["events"]]
    assert any(x.startswith("Campi di battaglia") for x in texts) and any(x.startswith("d20") for x in texts)
    # riproducibile dal seme
    s2 = _session(tmp_path / "b", "rust")
    _new(s2, 7)
    s2.scegli_campo(a["mine"][1])
    assert s2.state()["apertura"]["tiri"] == t and s2.state()["apertura"]["bf_opp"] == a["bf_opp"]


def test_casuale_e_deterministico(tmp_path):
    out = []
    for k in range(2):
        s = _session(tmp_path / str(k), "rust")
        _new(s, 11)
        s.scegli_campo("random")
        out.append(s.state()["apertura"]["bf_mine"])
    assert out[0] == out[1]


@pytest.mark.parametrize("motore", MOTORI)
@pytest.mark.parametrize("seat", ["A", "B"])
def test_vinco_io_decido_io(tmp_path, motore, seat):
    seed = _seed(tmp_path, motore, "io", seat)
    for io in (True, False):
        s = _session(tmp_path / f"g{io}", motore)
        _new(s, seed, seat)
        scelto = s.state()["apertura"]["mine"][2]
        s.scegli_campo(scelto)
        assert s.state()["apertura"]["inizia"] is None
        with pytest.raises(ValueError):
            s.inizia()
        s.inizia(io)
        st = _wait(s)
        a_bf = s.state()["info"]
        assert st["pending"]["type"] == "mulligan" and st["apertura"] is None
        assert st["info"]["you_start"] is io and st["info"]["campo_mio"] == scelto and st["info"]["motore"] == motore
        assert scelto in _campi(st) and st["info"]["campo_avv"] in _campi(st)
        assert any("cominci" in e["text"] for e in st["events"])


@pytest.mark.parametrize("motore", MOTORI)
def test_vince_il_campione(tmp_path, monkeypatch, motore):
    seed = _seed(tmp_path, motore, "avv")
    for sceglie, you_start in ((True, False), (False, True)):
        monkeypatch.setattr(ap, "scegli_inizio", lambda *a, _v=sceglie: _v)
        s = _session(tmp_path / f"c{sceglie}", motore)
        _new(s, seed)
        s.scegli_campo("random")
        a = s.state()["apertura"]
        assert a["inizia"] == ("avv" if sceglie else "io")
        assert any("sceglie di" in e["text"] for e in s.state()["events"])
        s.inizia()                                   # solo "Continua"
        st = _wait(s)
        assert st["info"]["you_start"] is you_start and st["pending"]["type"] == "mulligan"


@pytest.mark.parametrize("motore", MOTORI)
def test_rewind_tiene_campi_e_primo_giocatore(tmp_path, motore):
    seed = _seed(tmp_path, motore, "io")
    s = _session(tmp_path / "r", motore)
    _new(s, seed)
    s.scegli_campo(s.state()["apertura"]["mine"][0])
    s.inizia(False)
    rng = random.Random(1)
    st = _wait(s)
    campi, info = _campi(st), dict(st["info"])
    n = 0
    while n < 6:                                      # il mulligan e qualche decisione
        s.answer({"return": []} if st["pending"]["type"] == "mulligan" else {"action": rng.randrange(len(st["pending"]["actions"]))}
                 if st["pending"]["type"] == "decision" else {"option": 0})
        st = _wait(s)
        n += 1
        if st["status"] == "over":
            break
    assert st["can_rewind"]
    for _ in range(3):
        if not s.state()["can_rewind"]:
            break
        s.rewind()
        st = _wait(s)
        assert _campi(st) == campi and st["info"]["you_start"] is False
        assert st["info"]["campo_mio"] == info["campo_mio"] and st["info"]["seed"] == seed
    # mai prima del mulligan: si torna al piu' al mulligan, con l'apertura gia' fatta
    while s.state()["can_rewind"]:
        s.rewind()
        st = _wait(s)
    assert st["pending"]["type"] == "mulligan" and st["apertura"] is None and _campi(st) == campi


def test_senza_apertura_come_prima(tmp_path):
    s = _session(tmp_path, "rust")
    s.new_game(_deck("E"), _deck("K"), seat="A", opponent="simple_trade", seed=5)
    st = _wait(s)
    assert st["apertura"] is None and st["pending"]["type"] == "mulligan"
