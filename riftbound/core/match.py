"""Best-of-N match harness.

A single :func:`build_game` produces one game. A *match* (Core Rules §488,
Tournament Rules 403-408) is a series of games between two decks until one side
has won a majority (two games in a best of 3):

- **Battlefields** (§488.3-6): each player brings three and selects one per
  game; the selections are simultaneous, so a chooser never sees the opponent's
  pick. Once played, a battlefield is out for the rest of the match. In a best of
  5, played battlefields come back once all three have been played, each at most
  twice. The chooser is pluggable (``ai/pregame.py`` has a net-guided one); the
  default takes the first battlefield still available.
- **Turn order** (TR 407): game 1's designated player is drawn at random; after
  that, the loser of the previous game chooses. "Play first or last" is a
  pluggable decision; the default plays first.
- **Sideboarding** (TR 403, 601.1.c): between games each player may swap cards
  with their sideboard (up to 10 cards, deck JSON ``sideboard``) 1 for 1, and may
  change their Chosen Champion. Never before game 1, and legend, runes and
  battlefields stay as registered. A plan is always relative to the registered
  list. The policy is pluggable; the default keeps the registered list, and
  :func:`plan_sideboarder` follows the decks' ``sideboard_plans``.
- **Time limit** (TR 408.2): Riftbound has no turn limit, only the round's clock:
  60 minutes for a best of 3. The simulator converts it to turns across the
  whole match at ``MINUTES_PER_TURN``, an estimate: real games are reported at
  20-40 minutes (under 25 for experienced players) and online best-of-3 rounds
  use 50-55 minutes, while simulated games that finish take about 14 turns, so a
  turn is taken as 1⅓ minutes and 60 minutes as 45 turns. Recalibrate it when
  real turn counts are known. When the clock runs out mid-game, the current turn finishes
  and three more turns are played; then a player leading by 2 or more points
  wins that game, otherwise it is a draw, and the match ends there. If it runs
  out between games, no new game starts. The side with more game wins takes the
  match; equal wins is a drawn match (TR 404.4-404.5, 408.3). That is how a 1-1
  match is usually decided in game 3.
- **Stall guard**: ``max_turns`` caps any single game so a stalled simulation
  can't run forever. A game that reaches it is treated as the time running out.

Since a game can only be drawn when time runs out, and that ends the match, the
rules for "the game after a draw" (TR 403.10, 406.1.b, 407.4) never come up.
Not modeled: the best-of-1 setup variant (TR 406.1.h) and game-loss penalties.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

from riftbound.core.drivers import SyncDriver
from riftbound.core.enums import CardType
from riftbound.core.game_factory import (
    DeckConfig,
    build_game,
    deck_battlefield_names,
    registered_deck_config,
)
from riftbound.registry.cards_registry import CARD_REGISTRY, load_deck_json, load_sideboard_json

# chooser(side, available_battlefield_names, game_index) -> chosen name (or None)
BattlefieldChooser = Callable[[str, list, int], Optional[str]]
# order_chooser(choosing_side, game_index) -> True to play first, False to play last
OrderChooser = Callable[[str, int], bool]

MATCH_MINUTES = 60          # best-of-3 round time
MINUTES_PER_TURN = 4 / 3    # estimate, see the module docstring
TIME_EXTRA_TURNS = 3        # TR 408.2.a
TIME_LEAD_TO_WIN = 2        # TR 408.2.b


def clock_turns(minutes: float, minutes_per_turn: float = MINUTES_PER_TURN) -> int:
    """How many turns a match clock of ``minutes`` holds (60 minutes -> 45)."""
    return math.floor(minutes / minutes_per_turn + 1e-9)


@dataclass(frozen=True)
class SideboardPlan:
    """Swaps relative to the registered main deck: ``ins`` come from the sideboard,
    ``outs`` leave the main deck, 1 for 1. ``champion`` optionally names a new
    Chosen Champion from the main deck or sideboard (TR 403.4.a)."""
    ins: Mapping[str, int] = field(default_factory=dict)
    outs: Mapping[str, int] = field(default_factory=dict)
    champion: Optional[str] = None


@dataclass(frozen=True)
class SideboardContext:
    """What a sideboarding policy may know between games: its own registered
    list, the opponent's legend (public), and how the match has gone so far."""
    side: str
    game_index: int            # the game about to be played
    deck_path: Path
    registered: DeckConfig
    opponent_legend: Optional[str]
    games: tuple = ()          # GameOutcome of every game played so far


# sideboarder(context) -> plan for the next game (None = the registered list)
Sideboarder = Callable[[SideboardContext], Optional[SideboardPlan]]


@dataclass
class GameOutcome:
    game_index: int
    winner: str            # "A" / "B" / "DRAW"
    turns: int
    first_player: str
    bf_a: Optional[str]
    bf_b: Optional[str]
    points_a: int = 0
    points_b: int = 0
    timed_out: bool = False                      # decided by the time-limit rule
    sideboard_a: Optional[SideboardPlan] = None  # plan each seat played (None = registered)
    sideboard_b: Optional[SideboardPlan] = None


@dataclass
class MatchResult:
    winner: str            # "A" / "B" / "DRAW" (draw only if the match ties out)
    wins_A: int
    wins_B: int
    games: list = field(default_factory=list)


def _first_available(side: str, available: list, game_index: int) -> Optional[str]:
    """Default chooser: take the first still-available battlefield (deck order)."""
    return available[0] if available else None


def _play_first(side: str, game_index: int) -> bool:
    return True


def _keep_registered(ctx: SideboardContext) -> Optional[SideboardPlan]:
    return None


def _other(side: str) -> str:
    return "B" if side == "A" else "A"


def available_battlefields(pool: list, plays: Mapping[str, int]) -> list:
    """§488.5-6: battlefields not yet played this match come first; once all have
    been, each may come back while it has been played fewer than twice. A deck
    with too few battlefields falls back to its whole pool."""
    fresh = [n for n in pool if plays.get(n, 0) == 0]
    if fresh:
        return fresh
    return [n for n in pool if plays.get(n, 0) < 2] or list(pool)


def apply_sideboard(registered: DeckConfig, plan: Optional[SideboardPlan], *,
                    legend: Optional[str] = None) -> DeckConfig:
    """The deck a seat plays after sideboarding with ``plan`` (TR 403.4). Each
    swapped-in card takes the place of the card it replaces, so the result keeps
    the registered order. Raises ValueError on an illegal plan."""
    if plan is None:
        return registered
    main = list(registered.main)
    side = list(registered.sideboard)
    outs = [n for n, count in plan.outs.items() for _ in range(count)]
    ins = [n for n, count in plan.ins.items() for _ in range(count)]
    if len(outs) != len(ins):
        raise ValueError(f"sideboard plan is not 1 for 1 ({len(ins)} in, {len(outs)} out)")
    for out, card in zip(outs, ins):
        if out not in main:
            raise ValueError(f"sideboard plan takes out '{out}', which is not in the main deck")
        if card not in side:
            raise ValueError(f"sideboard plan brings in '{card}', which is not in the sideboard")
        main[main.index(out)] = card
        side.remove(card)
        side.append(out)

    champion = registered.champion
    new = plan.champion
    if new and new != champion:
        spec = CARD_REGISTRY.get(new)
        if spec is None or spec.category != CardType.CHAMPION:
            raise ValueError(f"'{new}' is not a champion unit")
        legend_spec = CARD_REGISTRY.get(legend) if legend else None
        if legend_spec is not None and legend_spec.tags and not set(legend_spec.tags) & set(spec.tags):
            raise ValueError(f"'{new}' doesn't match the legend '{legend}'")
        if champion is None:
            raise ValueError("the deck has no Chosen Champion to change")
        if new in main:
            main[main.index(new)] = champion
        elif new in side:
            side.remove(new)
            side.append(champion)
        else:
            raise ValueError(f"new champion '{new}' is in neither the main deck nor the sideboard")
        champion = new
    return DeckConfig(main=tuple(main), champion=champion, sideboard=tuple(side))


def _legend_name(path: Path) -> Optional[str]:
    _specs, _runes, _champ, legend, _bfs = load_deck_json(path)
    return legend.name if legend is not None else None


def plan_sideboarder(deck_a_path: Path, deck_b_path: Path) -> Sideboarder:
    """A sideboarder that follows each deck's ``sideboard_plans``: the plan keyed
    by the opponent's legend, else the ``"*"`` plan, else the registered list."""
    plans = {"A": load_sideboard_json(deck_a_path)[1], "B": load_sideboard_json(deck_b_path)[1]}

    def sideboarder(ctx: SideboardContext) -> Optional[SideboardPlan]:
        raw = plans[ctx.side].get(ctx.opponent_legend or "") or plans[ctx.side].get("*")
        if raw is None:
            return None
        return SideboardPlan(ins=raw["in"], outs=raw["out"], champion=raw.get("champion"))
    return sideboarder


def _game_result(gs, result) -> tuple[str, bool]:
    """(winner, timed_out). A game nobody won outright ran out of time: a player
    leading by TIME_LEAD_TO_WIN or more points wins it, otherwise it is a draw
    (TR 408.2.b)."""
    if max(gs.points_A, gs.points_B) >= gs.victory_score:
        return result.winner, False
    lead = gs.points_A - gs.points_B
    if lead >= TIME_LEAD_TO_WIN:
        return "A", True
    if lead <= -TIME_LEAD_TO_WIN:
        return "B", True
    return "DRAW", True


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
    time_limit_minutes: Optional[float] = MATCH_MINUTES,
    minutes_per_turn: float = MINUTES_PER_TURN,
    bf_chooser: Optional[BattlefieldChooser] = None,
    order_chooser: Optional[OrderChooser] = None,
    sideboarder: Optional[Sideboarder] = None,
) -> MatchResult:
    """Play a best-of-``best_of`` match and return the aggregate result.

    ``time_limit_minutes`` is the round's clock (``None``: no clock, games play
    out; a best of 5 needs a longer one than the default), converted to turns
    across the whole match at ``minutes_per_turn``. ``max_turns`` is the per-game
    stall guard; reaching it counts as the time running out.
    """
    time_limit_turns = (clock_turns(time_limit_minutes, minutes_per_turn)
                        if time_limit_minutes is not None else None)
    choose_bf = bf_chooser or _first_available
    choose_order = order_chooser or _play_first
    sideboard = sideboarder or _keep_registered
    needed = best_of // 2 + 1
    paths = {"A": deck_a_path, "B": deck_b_path}
    pools = {s: deck_battlefield_names(paths[s]) for s in "AB"}
    registered = {s: registered_deck_config(paths[s]) for s in "AB"}
    legends = {s: _legend_name(paths[s]) for s in "AB"}
    decks = dict(registered)
    plans: dict = {"A": None, "B": None}
    plays: dict = {"A": {}, "B": {}}     # battlefield -> games it was played in
    wins = {"A": 0, "B": 0}
    games: list = []
    turns_used = 0
    match_rng = random.Random(seed)

    for i in range(best_of):
        if max(wins.values()) >= needed:
            break
        cap = max_turns
        if time_limit_turns is not None:
            remaining = time_limit_turns - turns_used
            if remaining <= 0:
                break                                 # time is up between games (TR 408.2.d)
            cap = min(max_turns, remaining + TIME_EXTRA_TURNS)

        bfs = {}
        for s in "AB":
            avail = available_battlefields(pools[s], plays[s])
            pick = choose_bf(s, list(avail), i)
            if pick is None and avail:
                pick = avail[0]
            if pick is not None and pick not in avail:
                raise ValueError(f"seat {s} chose battlefield '{pick}', not available "
                                 f"in game {i + 1} (available: {avail})")
            bfs[s] = pick

        if not games:
            designated = match_rng.choice(["A", "B"])
        else:
            designated = _other(games[-1].winner)     # the loser chooses
            for s in "AB":
                ctx = SideboardContext(side=s, game_index=i, deck_path=paths[s],
                                       registered=registered[s],
                                       opponent_legend=legends[_other(s)],
                                       games=tuple(games))
                plans[s] = sideboard(ctx)
                decks[s] = apply_sideboard(registered[s], plans[s], legend=legends[s])
        first = designated if choose_order(designated, i) else _other(designated)

        gs = build_game(
            game_seed=match_rng.randrange(1 << 30),
            deck_a_path=deck_a_path, deck_b_path=deck_b_path,
            ai_a=ai_a, ai_b=ai_b,
            victory_score=victory_score, max_turns=cap,
            first_player=first, bf_a=bfs["A"], bf_b=bfs["B"],
            deck_a=decks["A"], deck_b=decks["B"],
        )
        result = SyncDriver(gs).run()
        winner, timed_out = _game_result(gs, result)
        games.append(GameOutcome(i, winner, result.turns, first, bfs["A"], bfs["B"],
                                 points_a=gs.points_A, points_b=gs.points_B,
                                 timed_out=timed_out,
                                 sideboard_a=plans["A"], sideboard_b=plans["B"]))
        turns_used += result.turns
        if winner in ("A", "B"):
            wins[winner] += 1
        for s in "AB":
            plays[s][bfs[s]] = plays[s].get(bfs[s], 0) + 1
        if timed_out:
            break                                     # time is up: the match ends here

    winner = "A" if wins["A"] > wins["B"] else "B" if wins["B"] > wins["A"] else "DRAW"
    return MatchResult(winner=winner, wins_A=wins["A"], wins_B=wins["B"], games=games)
