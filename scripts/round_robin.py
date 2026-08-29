#!/usr/bin/env python
"""Seat-swapped round-robin win-rate harness for deck-vs-deck balance testing.

The `simulate` CLI attributes wins by SEAT (A/B), which conflates deck strength
with the engine's first/second-player advantage. This harness plays every deck
pair in BOTH seat orientations and attributes each win to the DECK, cancelling
seat bias, then prints a win-rate matrix and an overall ranking.

For each unordered pair (X, Y) it plays `--games` games with X in seat A and
`--games` games with X in seat B (2*games total per pair), all seeded off
`--seed` for reproducibility. Draws are counted but excluded from win-rate
denominators (win% = wins / decided).

Usage:
  uv run python scripts/round_robin.py                       # all decks/vendetta_*.json, 50 games/side
  uv run python scripts/round_robin.py --games 100 --seed 7
  uv run python scripts/round_robin.py --glob "riftbound/data/decks/*.json"
  uv run python scripts/round_robin.py --agent simple_trade --csv out.csv
"""
from __future__ import annotations

import csv as csvmod
import glob as globmod
import itertools
import random
from pathlib import Path

import typer

from riftbound.core.game_factory import build_game, AI_REGISTRY
from riftbound.core.loop import GameLoop

app = typer.Typer(add_completion=False)


def _play(deck_a: Path, deck_b: Path, agent: str, seed: int, victory_score: int, max_turns: int) -> str:
    gs = build_game(
        game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b,
        ai_a=agent, ai_b=agent, victory_score=victory_score,
        first_player="random", max_turns=max_turns,
    )
    return GameLoop(gs, verbose=False).start().winner  # "A" | "B" | "DRAW"


@app.command()
def main(
    glob: str = typer.Option("riftbound/data/decks/vendetta_*.json", "--glob",
                             help="Glob for deck files (ignored if --decks given)"),
    decks: str = typer.Option("", "--decks", help="Comma-separated deck paths (overrides --glob)"),
    games: int = typer.Option(50, "--games", help="Games per seat orientation per pair (total per pair = 2x)"),
    seed: int = typer.Option(42, "--seed", help="Master seed"),
    agent: str = typer.Option("simple_trade", "--agent", help=f"Agent for both seats ({'|'.join(AI_REGISTRY)})"),
    victory_score: int = typer.Option(8, "--victory-score"),
    max_turns: int = typer.Option(40, "--max-turns"),
    csv: Path = typer.Option(None, "--csv", help="Optional: write the pair results to CSV"),
) -> None:
    if agent.strip().lower() not in AI_REGISTRY:
        raise typer.BadParameter(f"Unknown agent '{agent}'. Available: {', '.join(AI_REGISTRY)}")

    if decks.strip():
        paths = [Path(p.strip()) for p in decks.split(",") if p.strip()]
    else:
        paths = [Path(p) for p in sorted(globmod.glob(glob))]
    if len(paths) < 2:
        raise typer.BadParameter(f"Need >=2 decks; found {len(paths)} for {glob!r}")
    for p in paths:
        if not p.exists():
            raise typer.BadParameter(f"deck not found: {p}")

    names = [p.stem for p in paths]
    typer.echo(f"Round-robin: {len(paths)} decks, {games} games/side ({2*games}/pair), "
               f"agent={agent}, seed={seed}\n")

    master = random.Random(seed)
    # wins[(i,j)] = games deck i won against deck j (both orientations aggregated)
    wins = {i: {j: 0 for j in range(len(paths))} for i in range(len(paths))}
    decided = {i: {j: 0 for j in range(len(paths))} for i in range(len(paths))}
    draws_total = 0
    rows = []

    for i, j in itertools.combinations(range(len(paths)), 2):
        wi = wj = dr = 0
        # Orientation 1: i in seat A, j in seat B.
        for _ in range(games):
            w = _play(paths[i], paths[j], agent, master.randrange(1 << 30), victory_score, max_turns)
            if w == "A": wi += 1
            elif w == "B": wj += 1
            else: dr += 1
        # Orientation 2: j in seat A, i in seat B (seat swap).
        for _ in range(games):
            w = _play(paths[j], paths[i], agent, master.randrange(1 << 30), victory_score, max_turns)
            if w == "A": wj += 1
            elif w == "B": wi += 1
            else: dr += 1
        dec = wi + wj
        wins[i][j], wins[j][i] = wi, wj
        decided[i][j] = decided[j][i] = dec
        draws_total += dr
        rate = 100.0 * wi / dec if dec else 0.0
        rows.append((names[i], names[j], wi, wj, dr, rate))
        typer.echo(f"  {names[i]:20} vs {names[j]:20}  {wi:3}-{wj:<3} "
                   f"(draws {dr:2})  {names[i]} {rate:5.1f}%")

    # Win-rate matrix.
    typer.echo("\n=== Win-rate matrix (row deck's win% vs column deck) ===")
    hdr = " " * 22 + "".join(f"{n[:10]:>11}" for n in names)
    typer.echo(hdr)
    for i in range(len(paths)):
        cells = []
        for j in range(len(paths)):
            if i == j:
                cells.append(f"{'—':>11}")
            else:
                dec = decided[i][j]
                cells.append(f"{(100.0*wins[i][j]/dec if dec else 0):>10.1f}%")
        typer.echo(f"{names[i]:22}" + "".join(cells))

    # Overall ranking (aggregate win% across all decided games).
    typer.echo("\n=== Overall ranking (aggregate win% across all opponents) ===")
    agg = []
    for i in range(len(paths)):
        w = sum(wins[i][j] for j in range(len(paths)) if j != i)
        d = sum(decided[i][j] for j in range(len(paths)) if j != i)
        agg.append((names[i], w, d, 100.0 * w / d if d else 0.0))
    for name, w, d, pct in sorted(agg, key=lambda x: -x[3]):
        typer.echo(f"  {name:22} {pct:5.1f}%  ({w}/{d})")
    if draws_total:
        typer.echo(f"\n(draws across all games: {draws_total})")

    if csv:
        with csv.open("w", newline="", encoding="utf-8") as fh:
            w = csvmod.writer(fh)
            w.writerow(["deck_a", "deck_b", "wins_a", "wins_b", "draws", "a_winrate_pct"])
            w.writerows(rows)
        typer.echo(f"\nWrote {csv}")


if __name__ == "__main__":
    app()
