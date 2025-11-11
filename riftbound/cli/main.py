import typer
from rich import print
import random
from typing import List, Optional

from riftbound.core.models import GameConfig
from riftbound.core.cards import UnitCard, SpellCard, Card
from riftbound.core.enums import Domain
from riftbound.core.player import Player, Deck
from riftbound.core.state import GameState
from riftbound.core.loop import GameLoop

# DB logging
from riftbound.data.session import make_session
from riftbound.data.writer import record_game

# Agents
from riftbound.ai.heuristics.simple_aggro import SimpleAggro
from riftbound.ai.heuristics.simple_control import SimpleControl


app = typer.Typer(help="Riftbound Simulator CLI")

def make_simple_deck() -> Deck:
    """Create a 20-card toy deck: 10 Units, 10 Spells."""
    cards: List[Card] = []
    cards += [UnitCard("Recruit", cost_energy=1) for _ in range(10)]
    cards += [SpellCard("Bolt", cost_energy=2, damage=2) for _ in range(10)]
    return Deck(cards=cards)

AI_REGISTRY = {
    "aggro": SimpleAggro,
    "control": SimpleControl,
}

def make_agent(name: str, player: Player):
    key = name.strip().lower()
    if key not in AI_REGISTRY:
        raise typer.BadParameter(f"Unknown AI '{name}'. Available: {', '.join(AI_REGISTRY.keys())}")
    return AI_REGISTRY[key](player)

@app.command()
def simulate(
    games: int = typer.Option(100, help="Number of games to simulate"),
    seed: int = typer.Option(42, help="Random seed for reproducibility"),
    ai_a: str = typer.Option("aggro", "--aiA", help="Agent for Player A (aggro|control)"),
    ai_b: str = typer.Option("aggro", "--aiB", help="Agent for Player B (aggro|control)"),
    victory_score: int = typer.Option(8, help="Victory points needed to win via Hold/Conquer"),
    verbose: bool = typer.Option(True, help="Print a line per game"),
    db: Optional[str] = typer.Option(None, help="Optional path to SQLite database (e.g. results.db)"),
    channel_rate: int = typer.Option(1, help="Energy gained each CHANNEL phase"),
    max_energy: int = typer.Option(10, help="Energy cap per player"),
    starting_energy: int = typer.Option(0, help="Energy at the beginning of the match for each player"),
):
    """
    Two-battlefield Hold/Conquer scoring with simple combat and pluggable agents.
    Adds Rune Channeling/Energy & costs; COMBAT resolves after ACTION.
    """
    config = GameConfig(games=games, seed=seed, record_draws=False)
    typer.echo("=== Riftbound Simulator (Two-Battlefield + Energy + Combat Phase) ===")
    typer.echo(
        f"Games: {config.games} | Seed: {config.seed} | AIs: A={ai_a} B={ai_b} | "
        f"Victory Score: {victory_score} | Energy: +{channel_rate}/turn cap {max_energy}, start {starting_energy} | Per-game output: {verbose}"
    )
    if db:
        typer.echo(f"Database logging enabled -> {db}")

    session = make_session(db) if db else None

    wins_A = 0
    wins_B = 0
    draws = 0
    turns_total = 0

    base_rng = random.Random(config.seed)

    for i in range(config.games):
        # independent RNG per game
        game_seed = base_rng.randrange(1 << 30)
        rng = random.Random(game_seed)

        # Decks & shuffle
        deckA = make_simple_deck()
        deckB = make_simple_deck()
        deckA.shuffle(rng)
        deckB.shuffle(rng)

        # Players
        A = Player(name="A", hp=10, deck=deckA, energy=starting_energy)
        B = Player(name="B", hp=10, deck=deckB, energy=starting_energy)

        # Basic rune loadout so channeling can produce energy/power
        for player in (A, B):
            for domain in (Domain.CALM, Domain.FURY):
                player.add_rune(domain)


        # Agents
        A.agent = make_agent(ai_a, A)
        B.agent = make_agent(ai_b, B)

        # Game
        gs = GameState(
            rng=rng, A=A, B=B,
            turn=1, max_turns=40, active="A",
            victory_score=victory_score
        )
        result = GameLoop(gs).start()

        turns_total += result.turns
        if result.winner == "A":
            wins_A += 1
        elif result.winner == "B":
            wins_B += 1
        else:
            draws += 1

        if session:
            record_game(
                session=session,
                seed=game_seed,
                winner=result.winner,
                turns=result.turns,
                total_units=result.units_played,
                total_spells=result.spells_cast,
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
    typer.echo("")
    print(f"[bold magenta]Summary[/]: A {wins_A} | B {wins_B} | DRAW {draws} | Avg Turns {avg_turns:.2f}")

def main():
    app()

if __name__ == "__main__":
    main()
