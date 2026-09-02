"""Bo3 match harness (Stage 0.5): best-of-3, one battlefield per player per game,
no reuse within the match (§458), loser chooses who goes first."""

from __future__ import annotations

from pathlib import Path

from riftbound.core.match import MatchResult, play_match

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"


def test_match_produces_a_winner_and_clinches_early():
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=3)
    assert isinstance(res, MatchResult)
    assert res.winner in ("A", "B", "DRAW")
    # Bo3 clinches at 2 wins: never more than 3 games, and the leader has >= 2.
    assert len(res.games) <= 3
    if res.winner in ("A", "B"):
        assert max(res.wins_A, res.wins_B) >= 2
    # Games actually assigned battlefields from each deck.
    for g in res.games:
        assert g.bf_a is not None and g.bf_b is not None
        assert g.first_player in ("A", "B")


def test_battlefields_not_reused_within_match():
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=7)
    a_used = [g.bf_a for g in res.games]
    b_used = [g.bf_b for g in res.games]
    # Kennen and Ornn each declare 3 battlefields, so a Bo3 never needs to reuse.
    assert len(a_used) == len(set(a_used))
    assert len(b_used) == len(set(b_used))


def test_loser_chooses_first_next_game():
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=11)
    for prev, cur in zip(res.games, res.games[1:]):
        if prev.winner in ("A", "B"):
            loser = "B" if prev.winner == "A" else "A"
            assert cur.first_player == loser
