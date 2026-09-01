"""Best-of-N match harness (Stage 0.5).

A single :func:`build_game` produces one game (a Duel). A *match* is a best-of-3
between two decks (Core Rules §458): each player brings up to three battlefields
and **chooses** one per game, **without reusing** a battlefield across the games
of the match. The loser of the previous game chooses who goes first next.

What this harness does NOT yet do (deferred — see PROJECT_STATE / KNOWN_ISSUES):
- **Sideboarding** between games (fixed in/out per matchup). Decks are static here.
- **Strategic / searched battlefield selection.** The chooser is pluggable; the
  default just takes the first still-available battlefield. Making the choice a
  learned/searched decision is future work.
- The full §458 pre-game protocol (who reveals/picks in what order). We model the
  essential competitive facts: one battlefield per player per game, no reuse, and
  loser-chooses-first.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from riftbound.core.drivers import SyncDriver
from riftbound.core.game_factory import build_game, deck_battlefield_names

# chooser(side, available_battlefield_names, game_index) -> chosen name (or None)
BattlefieldChooser = Callable[[str, list, int], Optional[str]]


def _first_available(side: str, available: list, game_index: int) -> Optional[str]:
    """Default chooser: take the first still-available battlefield (deck order)."""
    return available[0] if available else None


@dataclass
class GameOutcome:
    game_index: int
    winner: str            # "A" / "B" / "DRAW"
    turns: int
    first_player: str
    bf_a: Optional[str]
    bf_b: Optional[str]


@dataclass
class MatchResult:
    winner: str            # "A" / "B" / "DRAW" (draw only if the match ties out)
    wins_A: int
    wins_B: int
    games: list = field(default_factory=list)


def play_match(
    deck_a_path: Path,
    deck_b_path: Path,
    ai_a: str,
    ai_b: str,
    *,
    seed: int = 0,
    best_of: int = 3,
    victory_score: int = 8,
    max_turns: int = 40,
    bf_chooser: Optional[BattlefieldChooser] = None,
) -> MatchResult:
    """Play a best-of-``best_of`` match and return the aggregate result."""
    chooser = bf_chooser or _first_available
    needed = best_of // 2 + 1               # games needed to clinch (2 for Bo3)
    pool_a = deck_battlefield_names(deck_a_path)
    pool_b = deck_battlefield_names(deck_b_path)
    used_a: set = set()
    used_b: set = set()
    wins_a = wins_b = 0
    games: list = []
    prev_loser: Optional[str] = None
    match_rng = random.Random(seed)

    for i in range(best_of):
        if wins_a >= needed or wins_b >= needed:
            break
        # §458: choose an unused battlefield; if the pool is exhausted (fewer than
        # `best_of` battlefields declared), reuse is allowed as a fallback.
        avail_a = [n for n in pool_a if n not in used_a] or pool_a
        avail_b = [n for n in pool_b if n not in used_b] or pool_b
        bf_a = chooser("A", list(avail_a), i)
        bf_b = chooser("B", list(avail_b), i)
        if bf_a is not None:
            used_a.add(bf_a)
        if bf_b is not None:
            used_b.add(bf_b)

        # Loser of the previous game chooses who goes first; game 1 is random.
        first = prev_loser if prev_loser in ("A", "B") else match_rng.choice(["A", "B"])

        gs = build_game(
            game_seed=match_rng.randrange(1 << 30),
            deck_a_path=deck_a_path, deck_b_path=deck_b_path,
            ai_a=ai_a, ai_b=ai_b,
            victory_score=victory_score, max_turns=max_turns,
            first_player=first, bf_a=bf_a, bf_b=bf_b,
        )
        result = SyncDriver(gs).run()
        games.append(GameOutcome(i, result.winner, result.turns, first, bf_a, bf_b))
        if result.winner == "A":
            wins_a += 1
            prev_loser = "B"
        elif result.winner == "B":
            wins_b += 1
            prev_loser = "A"
        else:
            prev_loser = None   # a draw doesn't set who chooses next

    winner = "A" if wins_a > wins_b else "B" if wins_b > wins_a else "DRAW"
    return MatchResult(winner=winner, wins_A=wins_a, wins_B=wins_b, games=games)
