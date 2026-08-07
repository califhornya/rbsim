import typer
from rich import print
import random
from pathlib import Path
from typing import Optional

from riftbound.core.models import GameConfig
from riftbound.core.state import GameState
from riftbound.core.loop import GameLoop
from riftbound.core.game_factory import AI_REGISTRY, build_game

# DB logging
from riftbound.data.analytics import summarize_session
from riftbound.data.session import make_session
from riftbound.data.writer import GameRecorder, record_game


app = typer.Typer(help="Riftbound Simulator CLI")

@app.command()
def analyze(
    db: str = typer.Option("results.db", help="Path to the SQLite database to inspect."),
    top: int = typer.Option(10, help="Number of top-played cards to display."),
) -> None:
    """Print aggregated statistics from a simulation database."""

    session = make_session(db)
    try:
        report = summarize_session(session, top_cards=top)
    except RuntimeError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        session.close()

    print("[bold magenta]Game Summary[/]")
    print(
        f"  Total Games: {report.games.total_games}\n"
        f"  Wins A/B: {report.games.wins_A}/{report.games.wins_B}\n"
        f"  Draws: {report.games.draws}\n"
        f"  Avg Turns: {report.games.avg_turns:.2f}\n"
        f"  Avg Units Played: {report.games.avg_units_played:.2f}\n"
        f"  Avg Spells Cast: {report.games.avg_spells_cast:.2f}"
    )

    print("\n[bold magenta]AI Performance[/]")
    if not report.ai_stats:
        print("  (no AI records found)")
    else:
        for stat in report.ai_stats:
            print(
                f"  {stat.ai_name}: games={stat.games} wins={stat.wins} "
                f"losses={stat.losses} draws={stat.draws} "
                f"win_rate={stat.win_rate:.2%} avg_turns={stat.avg_turns:.2f}"
            )

    print("\n[bold magenta]Top Cards[/]")
    if not report.top_cards:
        print("  (no card plays recorded)")
    else:
        for usage in report.top_cards:
            print(
                f"  {usage.card_name} ({usage.action}): {usage.plays} plays"
            )

@app.command()
def simulate(
    games: int = typer.Option(100, help="Number of games to simulate"),
    seed: Optional[int] = typer.Option(None, help="Random seed for reproducibility (default: random each run)"),
    ai_a: str = typer.Option("aggro", "--aiA", help="Agent for Player A (aggro|control)"),
    ai_b: str = typer.Option("aggro", "--aiB", help="Agent for Player B (aggro|control)"),
    deck_a: Path = typer.Option(..., "--deckA", help="Path to deck JSON for Player A"),
    deck_b: Path = typer.Option(..., "--deckB", help="Path to deck JSON for Player B"),
    victory_score: int = typer.Option(8, help="Victory points needed to win via Hold/Conquer"),
    verbose: bool = typer.Option(True, help="Print a line per game"),
    db: Optional[str] = typer.Option(None, help="Optional path to SQLite database (e.g. results.db)"),
    starting_energy: int = typer.Option(0, help="Energy at the beginning of the match for each player"),
    first_player: str = typer.Option(
        "random", "--first-player",
        help="Who takes turn 1: 'a', 'b', or 'random' (per-game coin flip, seeded)",
    ),
):
    """
    Two-battlefield Hold/Conquer scoring with simple combat and pluggable agents.
    Adds Rune Channeling/Energy & costs; COMBAT resolves after ACTION.
    """
    for label, name in (("--aiA", ai_a), ("--aiB", ai_b)):
        if name.strip().lower() not in AI_REGISTRY:
            raise typer.BadParameter(
                f"Unknown AI '{name}'. Available: {', '.join(AI_REGISTRY.keys())}",
                param_hint=label,
            )
    if seed is None:
        seed = random.randrange(1 << 30)  # fresh game each run; echoed below for replay
    config = GameConfig(games=games, seed=seed, record_draws=False)
    typer.echo("=== Riftbound Simulator (Two-Battlefield + Energy + Combat Phase) ===")
    deck_a_label = deck_a.stem
    deck_b_label = deck_b.stem
    typer.echo(
        f"Games: {config.games} | Seed: {config.seed} | AIs: A={ai_a} B={ai_b} | "
        f"Decks: A={deck_a_label} B={deck_b_label} | "
        f"Victory Score: {victory_score} | Starting Energy: {starting_energy} | "
        f"First player: {first_player} | Per-game output: {verbose}"
    )
    if db:
        typer.echo(f"Database logging enabled -> {db}")

    session = make_session(db) if db else None

    wins_A = 0
    wins_B = 0
    draws = 0
    turns_total = 0
    starts = {"A": 0, "B": 0}
    first_player_wins = 0

    base_rng = random.Random(config.seed)

    for i in range(config.games):
        # independent RNG per game, derived off the master seed
        game_seed = base_rng.randrange(1 << 30)

        # Build a fully-seeded game via the shared factory. The RNG derivation
        # (rune RNGs, deck shuffles, seeded starter) lives there so the CLI, the
        # golden-game fixture, and the web layer all construct games identically.
        gs = build_game(
            game_seed=game_seed,
            deck_a_path=deck_a,
            deck_b_path=deck_b,
            ai_a=ai_a,
            ai_b=ai_b,
            victory_score=victory_score,
            starting_energy=starting_energy,
            first_player=first_player,
            max_turns=40,
        )
        starter = gs.active

        recorder = None
        game_id = None
        if session:
            game_id = record_game(
                session=session,
                seed=game_seed,
                winner="?",
                turns=0,
                total_units=0,
                total_spells=0,
            )
            recorder = GameRecorder(session, game_id)
            recorder.record_deck("A", gs.A.deck.cards, ai_name=ai_a)
            recorder.record_deck("B", gs.B.deck.cards, ai_name=ai_b)

        result = GameLoop(gs, recorder=recorder, verbose=verbose).start()

        turns_total += result.turns
        if result.winner == "A":
            wins_A += 1
        elif result.winner == "B":
            wins_B += 1
        else:
            draws += 1

        # Track first-player advantage independently of which deck won.
        starts[starter] += 1
        if result.winner == starter:
            first_player_wins += 1

        if session and game_id is not None:
            record_game(
                session=session,
                seed=game_seed,
                winner=result.winner,
                turns=result.turns,
                total_units=result.units_played,
                total_spells=result.spells_cast,
                game_id=game_id,
            )

        if verbose:
            print("\n" + "=" * 90)
            print(
                f"[bold cyan]Game[/] {i+1}: "
                f"Winner {result.winner} in {result.turns} turns "
                f"(seed={game_seed}) "
                f"[units={result.units_played}, spells={result.spells_cast}, "
                f"VP_A={gs.points_A}, VP_B={gs.points_B}]"
            )


            if i < 5:  # mostra solo le prime 5 partite per non spammare
                for idx, bf in enumerate(gs.battlefields):
                    typer.echo(
                        f"  Battlefield {idx}: "
                        f"A={len(bf.units_A)} B={len(bf.units_B)} ctl={bf.controller()}"
                    )
            typer.echo(f"  Energy A={gs.A.energy}, Energy B={gs.B.energy}")
            typer.echo(f"  Points: A={gs.points_A} | B={gs.points_B}")
            typer.echo("=" * 90)

    if session:
        session.commit()
        session.close()

    total = config.games
    avg_turns = turns_total / total if total else 0.0
    decided = wins_A + wins_B
    fp_pct = (100.0 * first_player_wins / decided) if decided else 0.0
    typer.echo("")
    print(f"[bold magenta]Summary[/]: A {wins_A} | B {wins_B} | DRAW {draws} | Avg Turns {avg_turns:.2f}")
    print(
        f"  Starts: A={starts['A']} B={starts['B']} | "
        f"First-player wins: {first_player_wins}/{decided} ({fp_pct:.0f}%)"
    )

def main():
    app()

if __name__ == "__main__":
    main()
