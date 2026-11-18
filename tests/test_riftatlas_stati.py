"""Registrazione RiftAtlas → stato del tavolo (scripts/riftatlas/stati.py),
sulla partita 82FAW (Evelynn contro Ivern, 18/11, gara 1)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "riftatlas"))

import stati  # noqa: E402

FILE = ROOT / "docs" / "bot" / "partite" / "riftatlas_82FAW_ivern_g1.json"
IO, IVERN = "plr_7e9d652d", "plr_e3982505"


@pytest.fixture(scope="module")
def partita():
    return stati.carica(FILE)


def nomi(zona):
    return [c.get("name") for c in zona]


def test_tutte_le_patch_si_applicano(partita):
    seqs = [s for s, _ in stati.stati(partita)]
    assert seqs == list(range(0, 189))


def test_seq_finale(partita):
    t = stati.stato_a(partita)
    assert t.seq == 188
    assert t.player(IO)["board"]["score"] == 5
    assert t.player(IVERN)["board"]["score"] == 4
    assert dict(stati.campi(t))["battlefieldA"] == "Bandle Scouts' Academy"
    accademia = t.zona(IO, "battlefieldA")
    visibili = [c for c in accademia if not stati.nascosta(c)]
    assert nomi(visibili) == ["K'Sante, Courageous", "Reckless Innovator",
                              "Boots of Swiftness", "Momentary Companion"]
    boots = visibili[2]
    assert boots["attachedToCardId"] == visibili[1]["id"]
    assert stati.might(visibili[1], [boots]) == 5  # 3 + Boots 2, come il segnalino
    assert sum(stati.nascosta(c) for c in accademia) == 1
    assert t.zona(IVERN, "battlefieldA") == []
    assert len(t.zona(IVERN, "hand")) == 5
    assert all(c["isPlaceholder"] for c in t.zona(IVERN, "hand"))
    assert nomi(t.zona(IO, "hand")) == ["Star-Crossed", "Hold 'Em"]
    rune = t.zona(IO, "runeArea")
    assert (sum(not c["exhausted"] for c in rune), sum(c["exhausted"] for c in rune)) == (9, 1)
    assert stati.controllo(t) == {"battlefieldA": IO, "battlefieldB": IVERN}


def test_vista_pubblica_non_svela_le_coperte(partita):
    t = stati.stato_a(partita)
    testo_io = stati.descrivi(t, IO)
    testo_altro = stati.descrivi(t, IVERN)
    assert "coperta (Edge of Night)" in testo_io
    assert "Edge of Night" not in testo_altro
    assert "Punteggio: caarati 5 – flamingo 4" in testo_io
