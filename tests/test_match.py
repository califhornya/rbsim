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
    # Bo3 clinches at 2 wins: never more than 3 games, and the leader has >= 2
    # unless the match clock ran out first.
    assert len(res.games) <= 3
    if res.winner in ("A", "B") and not res.games[-1].timed_out:
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


def test_a_single_game_at_the_turn_guard_needs_a_two_point_lead():
    """The turn guard counts as the time running out (Riftbound has no turn
    limit): a 2+ point lead wins, else a draw (TR 408.2.b); any lead won."""
    import random
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.loop import GameLoop
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    for points, winner in (((5, 4), "DRAW"), ((6, 4), "A"), ((3, 5), "B")):
        a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
        b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
        gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
        gs.points_A, gs.points_B = points
        assert GameLoop(gs)._final_result().winner == winner


def test_bo1_altered_setup_sideboards_before_the_only_game():
    """TR 406.1.h: in the head judge's best-of-1 setup, players sideboard as if
    between games of a best of 3 (before game 1)."""
    seen = []

    def sideboarder(ctx):
        seen.append((ctx.side, ctx.game_index))
        return None
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=5, best_of=1,
                     sideboarder=sideboarder, bo1_altered_setup=True)
    assert len(res.games) == 1 and sorted(seen) == [("A", 0), ("B", 0)]
