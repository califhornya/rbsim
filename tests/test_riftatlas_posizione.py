"""Tavolo RiftAtlas → GameState del motore → mossa del bot a mano
(scripts/riftatlas/posizione.py), sulla partita 82FAW alla seq finale
(turno 10, Main Phase di caarati, 5-4)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "riftatlas"))

import posizione  # noqa: E402
import stati  # noqa: E402

FILE = ROOT / "docs" / "bot" / "partite" / "riftatlas_82FAW_ivern_g1.json"


@pytest.fixture(scope="module")
def pos():
    return posizione.costruisci(stati.carica(FILE), 188)


def test_stato_del_motore(pos):
    gs = pos.gs
    assert (pos.side, gs.active, gs.turn) == ("A", "A", 10)
    assert (gs.points_A, gs.points_B) == (5, 4)
    bf0, bf1 = gs.battlefields
    assert bf0.card.name == "Bandle Scouts' Academy" and bf0.held_by == "A"
    assert [(u.card.name, u.might) for u in bf0.units_A] == [
        ("K'Sante Courageous", 4), ("Reckless Innovator", 5), ("Momentary Companion", 4)]
    assert [g.name for g in bf0.units_A[1].gear] == ["Boots of Swiftness"]
    assert [(f.card.name, f.owner, f.turn_hidden) for f in bf0.facedowns] == [("Edge of Night", "A", 8)]
    assert bf0.scored_this_turn_A and not bf0.units_B
    # Il Brush di Ivern al posto di Forbidding Waste, +1 ai Poro, ai cani...
    assert bf1.card.name == "Brush" and bf1.replaced.name == "Forbidding Waste"
    assert bf1.held_by == "B"
    assert [u.might for u in bf1.units_B] == [6, 4, 4, 3, 3, 6]
    A, B = gs.A, gs.B
    assert [c.name for c in A.hand] == ["Star-Crossed", "Hold 'Em"]
    assert (len(A.deck.cards), len(B.hand), len(B.deck.cards)) == (28, 5, 27)
    assert (A.energy, B.energy) == (9, 1)
    assert gs.champion_A.name == "Evelynn Entrancing" and not gs.champion_A_deployed
    assert gs.champion_B_deployed
    assert [g.name for g in A.base_gear] == ["Gold", "Gold"]


def test_avvisi(pos):
    testo = "\n".join(pos.avvisi)
    assert "lista non disponibile, 32 carte coperte" in testo   # il mazzo Ivern
    # Il segnalino di flamingo sul Poro col buff dice 3, il motore 2+1+1 (Brush).
    assert "Stalwart Poro (battlefieldB): Might 4 nel motore, segnalino RiftAtlas 3" in testo


def test_il_bot_propone_una_mossa_legale(pos):
    prop = posizione.proponi(pos, budget=0.2, seed=1)
    assert prop.etichetta in prop.legali
    assert prop.alternative and prop.alternative[0][0] == prop.etichetta
