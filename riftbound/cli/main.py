import typer
from rich import print
import random
from typing import List, Optional

from riftbound.core.models import GameConfig
from riftbound.core.cards import Card
from riftbound.core.enums import Domain
from riftbound.core.player import Player, Deck, RuneDeck, Rune
from riftbound.core.state import GameState
from riftbound.core.loop import GameLoop
from riftbound.core.cards_registry import CARD_REGISTRY

# DB logging
from riftbound.data.session import make_session
from riftbound.data.writer import GameRecorder, record_game

# Agents
from riftbound.ai.heuristics.simple_aggro import SimpleAggro
from riftbound.ai.heuristics.simple_control import SimpleControl


app = typer.Typer(help="Riftbound Simulator CLI")

def make_simple_deck() -> Deck:
    """Create a 20-card toy deck: 10 Units, 10 Spells."""
    recruit = CARD_REGISTRY.get("Stalwart Recruit")
    bolt = CARD_REGISTRY.get("Bolt")
    if recruit is None or bolt is None:
        raise RuntimeError("Core cards not found in registry")
    cards: List[Card] = []
    cards += [recruit.instantiate() for _ in range(10)]
    cards += [bolt.instantiate() for _ in range(10)]
    return Deck(cards=cards)

def make_basic_rune_deck(rng: Optional[random.Random] = None) -> RuneDeck:
    """Create a basic rune deck with Calm and Fury runes."""

    runes = [Rune(domain=Domain.CALM) for _ in range(6)]
    runes += [Rune(domain=Domain.FURY) for _ in range(6)]
    if rng is not None:
        rng.shuffle(runes)
    return RuneDeck(runes=runes)

AI_REGISTRY = {
    "aggro": SimpleAggro,
    "control": SimpleControl,
    "ahri": SimpleControl,
    "jynx": SimpleAggro,
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
        rune_rng_a = random.Random(rng.randrange(1 << 30))
        rune_rng_b = random.Random(rng.randrange(1 << 30))

        A = Player(
            name="A",
            hp=10,
            deck=deckA,
            energy=starting_energy,
            rune_deck=make_basic_rune_deck(rune_rng_a),
        )
        B = Player(
            name="B",
            hp=10,
            deck=deckB,
            energy=starting_energy,
            rune_deck=make_basic_rune_deck(rune_rng_b),
        )

        # Agents
        A.agent = make_agent(ai_a, A)
        B.agent = make_agent(ai_b, B)

        # Game
        gs = GameState(
            rng=rng, A=A, B=B,
            turn=1, max_turns=40, active="A",
            victory_score=victory_score
        )
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
            recorder.record_deck("A", deckA.cards, ai_name=ai_a)
            recorder.record_deck("B", deckB.cards, ai_name=ai_b)

        result = GameLoop(gs, recorder=recorder).start()

        turns_total += result.turns
        if result.winner == "A":
            wins_A += 1
        elif result.winner == "B":
            wins_B += 1
        else:
            draws += 1

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
    typer.echo("")
    print(f"[bold magenta]Summary[/]: A {wins_A} | B {wins_B} | DRAW {draws} | Avg Turns {avg_turns:.2f}")

def main():
    app()

if __name__ == "__main__":
    main()
