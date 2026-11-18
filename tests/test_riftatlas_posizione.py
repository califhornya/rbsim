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
IO = "plr_7e9d652d"


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


def test_con_la_lista_di_ivern():
    """La lista di flamingo (dall'utente, 18/11): mano e mazzo di Ivern sono
    la lista meno le 7 carte del mazzo viste (5 unità sul Brush, Iridescent
    Avian in base, Defy nel cimitero). Ivern Nurturer è anche nel mazzo
    principale, oltre al campione scelto (§103.3.b.1)."""
    lista = ROOT / "docs" / "bot" / "partite" / "82FAW_ivern_lista.txt"
    pos = posizione.costruisci(stati.carica(FILE), 188, mazzo_avversario=lista)
    assert not [a for a in pos.avvisi if "flamingo:" in a]
    from collections import Counter
    nascoste = Counter(c.name for c in pos.gs.B.hand + pos.gs.B.deck.cards)
    assert sum(nascoste.values()) == 32
    assert (nascoste["Stalwart Poro"], nascoste["Ivern Nurturer"], nascoste["Defy"],
            nascoste["Iridescent Avian"], nascoste["Back Off"]) == (1, 0, 2, 2, 3)


def test_carte_giocate_a_meta_turno():
    """Seq 151, turno 8 di caarati: Momentary Companion scoperta (seq 141) e
    K'Sante dalla mano, entrambe all'Academy; il Gold token e la carta
    nascosta (seq 148) non contano come giocate."""
    pos = posizione.costruisci(stati.carica(FILE), 151)
    gs = pos.gs
    assert [c.name for c in gs.played_cards_this_turn["A"]] == ["Momentary Companion",
                                                                "K'Sante Courageous"]
    assert gs.cards_played_this_turn == {"A": 2, "B": 0}
    assert gs.battlefields[0].plays_here == {"A": (8, 2)}
    assert any(a.startswith("a metà turno") for a in pos.avvisi)
    # La carta giocata è quella sul campo, non una copia.
    assert gs.played_cards_this_turn["A"][1] is gs.battlefields[0].units_A[0].card


def test_coperta_ricoperta_riparte_dal_turno_nuovo():
    """Edge of Night, coperta al turno 8, torna in mano al turno 11 e si copre
    di nuovo al 12: può essere giocata dal turno dopo il 12, non dal 9."""
    import dataclasses
    p = stati.carica(FILE)
    t = stati.stato_a(p)
    io = IO
    eon = next(c["id"] for c in t.zona(io, "battlefieldA") if c.get("hidden"))
    extra = [
        {"baseSequence": 188, "sequence": 189, "patch": {"operations": [
            {"op": "set_room_fields", "fields": {"turnNumber": 11}},
            {"op": "zone_move", "cardId": eon, "from": {"playerId": io, "zone": "battlefieldA"},
             "to": {"playerId": io, "zone": "hand", "index": 0}},
            {"op": "unset_card_fields", "playerId": io, "zone": "hand", "cardId": eon,
             "fields": ["hidden"]}]}},
        {"baseSequence": 189, "sequence": 190, "patch": {"operations": [
            {"op": "set_room_fields", "fields": {"turnNumber": 12}},
            {"op": "patch_card_fields", "playerId": io, "zone": "hand", "cardId": eon,
             "fields": {"hidden": True}},
            {"op": "zone_move", "cardId": eon, "from": {"playerId": io, "zone": "hand"},
             "to": {"playerId": io, "zone": "battlefieldA", "index": 3}}]}},
    ]
    p2 = dataclasses.replace(p, patches=p.patches + extra)
    gs = posizione.costruisci(p2, 190).gs
    assert [(f.card.name, f.turn_hidden) for f in gs.battlefields[0].facedowns] == [("Edge of Night", 12)]

