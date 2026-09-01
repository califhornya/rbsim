"""Deterministic game construction shared by the CLI, the golden-game fixture,
and (later) the web/search layers.

The RNG derivation here is byte-for-byte identical to what the CLI ``simulate``
command used to inline (see ``riftbound/cli/main.py`` history): given a per-game
seed we derive two rune RNGs, shuffle the rune decks, shuffle the main decks off
the game RNG, then draw the starter off the same RNG. Anything that consumes the
game RNG must keep this order so a given seed reproduces an identical game.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional

from riftbound.core.cards import Card
from riftbound.core.player import Player, Deck, RuneDeck, Rune
from riftbound.core.state import GameState
from riftbound.core.battlefield import Battlefield
from riftbound.registry.cards_registry import load_deck_json

# Agents. Imported here (not in the CLI) so every entry point builds games the
# same way. Agents only depend on Player, so there is no import cycle with core.
from riftbound.ai.heuristics.pyke_agent import PykeAgent
from riftbound.ai.heuristics.diana_agent import DianaAgent
from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.ai.search.random_agent import RandomAgent
from riftbound.ai.search.monte_carlo_agent import MonteCarloAgent
from riftbound.ai.search.ismcts_agent import ISMCTSAgent


AI_REGISTRY = {
    "pyke": PykeAgent,
    "diana": DianaAgent,
    "simple_trade": SimpleTradeAgent,
    "random": RandomAgent,
    "mc": MonteCarloAgent,
    "ismcts": ISMCTSAgent,
}


def make_deck_from_file(path: Path) -> tuple[Deck, RuneDeck, Optional[Card], Optional[Card], List[Card]]:
    """Load a deck, rune deck, champion, legend, and battlefield cards from JSON."""
    specs, rune_entries, champion_spec, legend_spec, bf_specs = load_deck_json(path)
    cards: List[Card] = [spec.instantiate() for spec in specs]
    runes: List[Rune] = []
    for domain, count in rune_entries:
        runes.extend(Rune(domain=domain) for _ in range(count))
    champion = champion_spec.instantiate() if champion_spec is not None else None
    legend = legend_spec.instantiate() if legend_spec is not None else None
    battlefields = [spec.instantiate() for spec in bf_specs]
    return Deck(cards=cards), RuneDeck(runes=runes), champion, legend, battlefields


def make_agent(name: str, player: Player):
    """Instantiate an agent by registry key. Raises ValueError on an unknown key
    (the CLI translates this into a typer.BadParameter for arg validation)."""
    key = name.strip().lower()
    if key not in AI_REGISTRY:
        raise ValueError(
            f"Unknown AI '{name}'. Available: {', '.join(AI_REGISTRY.keys())}"
        )
    return AI_REGISTRY[key](player)


def resolve_starter(rng: random.Random, first_player: str) -> str:
    """Pick the starting player. 'random' draws a seeded coin flip off ``rng``
    (must be called AFTER the deck shuffles so seat choice never perturbs deck
    order); 'a'/'b' force a seat; anything else defaults to A."""
    fp = first_player.strip().lower()
    if fp == "random":
        return rng.choice(["A", "B"])
    if fp in ("a", "b"):
        return fp.upper()
    return "A"


def _select_battlefield(bfs, choice, rng):
    """Pick one battlefield card from a deck's up-to-3. ``choice`` may be None
    (random, historical default), an int index, or a battlefield card name. An
    out-of-range / unknown choice falls back to random so callers can't crash a
    build on a bad selection."""
    if not bfs:
        return None
    if choice is None:
        return rng.choice(bfs)
    if isinstance(choice, int):
        return bfs[choice] if 0 <= choice < len(bfs) else rng.choice(bfs)
    for card in bfs:
        if card.name == choice:
            return card
    return rng.choice(bfs)


def deck_battlefield_names(path: Path) -> list[str]:
    """The battlefield card names a deck declares (its up-to-3 choices), for a
    match harness / UI to pick from."""
    _cards, _runes, _champ, _legend, bfs = make_deck_from_file(path)
    return [c.name for c in bfs]


def build_game(
    *,
    game_seed: int,
    deck_a_path: Path,
    deck_b_path: Path,
    ai_a: Optional[str],
    ai_b: Optional[str],
    victory_score: int = 8,
    starting_energy: int = 0,
    first_player: str = "random",
    max_turns: int = 40,
    bf_a: "Optional[object]" = None,
    bf_b: "Optional[object]" = None,
) -> GameState:
    """Build a fully-seeded :class:`GameState` from decks + agent names.

    ``ai_a``/``ai_b`` may be ``None`` to leave a seat agent-less (the loop treats
    a ``None`` agent as an always-PASS player — used by drivers that inject their
    own decisions). The RNG order matches the historical CLI exactly.

    ``bf_a``/``bf_b`` optionally force each seat's battlefield choice (a battlefield
    card name, or an index into the deck's up-to-3). Left as ``None`` the choice is
    random (historical behaviour, unchanged). Explicit selection is what the Bo3
    match harness uses to implement §458 "players choose, no reuse".
    """
    rng = random.Random(game_seed)

    rune_rng_a = random.Random(rng.randrange(1 << 30))
    rune_rng_b = random.Random(rng.randrange(1 << 30))

    deck_a, rune_deck_a, champion_a, legend_a, bfs_a = make_deck_from_file(deck_a_path)
    rune_rng_a.shuffle(rune_deck_a.runes)

    deck_b, rune_deck_b, champion_b, legend_b, bfs_b = make_deck_from_file(deck_b_path)
    rune_rng_b.shuffle(rune_deck_b.runes)

    deck_a.shuffle(rng)
    deck_b.shuffle(rng)

    A = Player(name="A", hp=10, deck=deck_a, energy=starting_energy, rune_deck=rune_deck_a)
    B = Player(name="B", hp=10, deck=deck_b, energy=starting_energy, rune_deck=rune_deck_b)

    if ai_a is not None:
        A.agent = make_agent(ai_a, A)
    if ai_b is not None:
        B.agent = make_agent(ai_b, B)

    starter = resolve_starter(rng, first_player)

    # Battlefields: a single game uses one per player, chosen from the deck's up-to-3.
    # Use an INDEPENDENT rng so the choice never perturbs deck/rune shuffles above
    # (keeps existing draw determinism); across many seeds all 3 get exercised.
    bf_rng = random.Random((game_seed * 2654435761) & 0xFFFFFFFF)
    bf_slot_A = _select_battlefield(bfs_a, bf_a, bf_rng)
    bf_slot_B = _select_battlefield(bfs_b, bf_b, bf_rng)
    battlefields = [Battlefield(card=bf_slot_A), Battlefield(card=bf_slot_B)]

    return GameState(
        rng=rng,
        A=A,
        B=B,
        turn=1,
        max_turns=max_turns,
        active=starter,
        victory_score=victory_score,
        champion_A=champion_a,
        champion_B=champion_b,
        legend_A=legend_a,
        legend_B=legend_b,
        battlefields=battlefields,
    )
