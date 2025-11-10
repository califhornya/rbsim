import typer
import random
from typing import List, Optional

from riftbound.core.models import GameConfig
from riftbound.core.cards import UnitCard, SpellCard, Card
from riftbound.core.player import Player, Deck
from riftbound.core.state import GameState
from riftbound.core.loop import GameLoop

# New imports for database logging
from riftbound.data.session import make_session
from riftbound.data.writer import record_game

app = typer.Typer(help="Riftbound Simulator CLI")


def make_simple_deck() -> Deck:
    """Create a 20-card toy deck: 10 units, 10 spells."""
    cards: List[Card] = []
    cards += [UnitCard("Recruit") for _ in range(10)]
    cards += [SpellCard("Bolt", damage=2) for _ in range(10)]
    return Deck(cards=cards)


@app.command()
def simulate(
    games: int = typer.Option(100, help="Number of games to simulate"),
    seed: int = typer.Option(42, help="Random seed for reproducibility"),
    record_draws: bool = typer.Option(False, "--record-draws", help="Reserved; not used in minimal loop"),
    verbose: bool = typer.Option(True, help="Print a line per game"),
    db: Optional[str] = typer.Option(None, help="Optional path to SQLite database (e.g. results.db)"),
):
    """
    Run a batch of minimal-rule simulated games (no energy/costs) and optionally log to SQLite.
    """
    config = GameConfig(games=games, seed=seed, record_draws=record_draws)
    typer.echo("=== Riftbound Simulator (Minimal Prototype) ===")
    typer.echo(f"Games: {config.games} | Seed: {config.seed} | Per-game output: {verbose}")
    if db:
        typer.echo(f"Database logging enabled -> {db}")

    # optional DB session
    session = make_session(db) if db else None

    wins_A = 0
    wins_B = 0
    draws = 0
    turns_total = 0

    base_rng = random.Random(config.seed)

    for i in range(config.games):
        # independent RNG per game for determinism
        game_seed = base_rng.randrange(1 << 30)
        rng = random.Random(game_seed)

        # Build decks and shuffle
        deckA = make_simple_deck()
        deckB = make_simple_deck()
        deckA.shuffle(rng)
        deckB.shuffle(rng)

        # Create players
        A = Player(name="A", hp=10, deck=deckA)
        B = Player(name="B", hp=10, deck=deckB)

        # Game state + loop
        gs = GameState(rng=rng, A=A, B=B, turn=1, max_turns=20, active="A")
        result = GameLoop(gs).start()

        # track stats
        turns_total += result.turns
        if result.winner == "A":
            wins_A += 1
        elif result.winner == "B":
            wins_B += 1
        else:
            draws += 1

        # write to database
        if session:
            total_units = A.board_units + B.board_units
            total_spells = 20 - len(A.deck.cards) - len(B.deck.cards) - total_units
            record_game(
                session=session,
                seed=game_seed,
                winner=result.winner,
                turns=result.turns,
                total_units=total_units,
                total_spells=total_spells,
            )

        # print to console
        if verbose:
            typer.echo(f"Game {i+1}: Winner {result.winner} in {result.turns} turns (seed={game_seed})")

    if session:
        session.commit()
        session.close()

    # print summary
    total = config.games
    avg_turns = turns_total / total if total else 0.0
    typer.echo("")
    typer.echo(f"Summary: A {wins_A} | B {wins_B} | DRAW {draws} | Avg Turns {avg_turns:.2f}")


def main():
    """Entry point for Typer CLI."""
    app()


if __name__ == "__main__":
    main()
