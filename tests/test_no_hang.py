"""Regression guard for the action-phase infinite loop.

A ready token in base used to make the Pyke agent propose a MOVE the engine
silently refused (tokens can't move to a battlefield), spinning the action loop
forever. Two defenses are covered here:

1. Full seeded games complete (integration smoke — would have caught the hang).
2. The engine's no-op guard ends the action phase when an action changes nothing,
   regardless of what an agent proposes.
"""

import random
from pathlib import Path

import pytest

from riftbound.core.combat import UnitInPlay
from riftbound.core.cards import UnitCard
from riftbound.core.loop import GameLoop
from riftbound.core.state import GameState
from riftbound.core.player import Deck, Player, RuneDeck

DECK_DIR = Path(__file__).resolve().parent.parent / "riftbound" / "data" / "decks"


def _build_game(seed: int) -> GameState:
    from riftbound.core.game_factory import make_deck_from_file, make_agent

    rng = random.Random(seed)
    dA, rA, cA, lA = make_deck_from_file(DECK_DIR / "fury_chaos_pyke.json")
    dB, rB, cB, lB = make_deck_from_file(DECK_DIR / "chaos_mind_diana.json")
    random.Random(seed + 1).shuffle(rA.runes)
    random.Random(seed + 2).shuffle(rB.runes)
    dA.shuffle(rng)
    dB.shuffle(rng)
    A = Player(name="A", hp=10, deck=dA, energy=0, rune_deck=rA)
    B = Player(name="B", hp=10, deck=dB, energy=0, rune_deck=rB)
    A.agent = make_agent("pyke", A)
    B.agent = make_agent("diana", B)
    return GameState(rng=rng, A=A, B=B, turn=1, max_turns=40, active="A",
                     victory_score=8, champion_A=cA, champion_B=cB)


@pytest.mark.parametrize("seed", [42, 7, 13, 100, 256])
def test_seeded_game_completes(seed):
    result = GameLoop(_build_game(seed), verbose=False).start()
    assert result.winner in ("A", "B", "DRAW")
    assert 1 <= result.turns <= 40


def test_noop_action_ends_action_phase():
    """An agent that always proposes the same no-op action must not hang: the
    engine's no-op guard ends the action phase after the first unchanged state."""

    class StuckAgent:
        def __init__(self, player):
            self.player = player
            self.calls = 0

        def decide_mulligan(self):
            return []

        def decide_action(self, opponent, cards_played=0):
            self.calls += 1
            # A MOVE from a nonexistent base slot: the engine refuses it, so the
            # state never changes. Without the guard this loops forever.
            return ("MOVE", None, 2, 1)

    player_a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    player_b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    # Give A a ready token in base so pop_base_unit finds nothing movable.
    player_a.base_units.append(
        UnitInPlay(UnitCard(name="Recruit", might=1), ready=True, is_token=True)
    )
    gs = GameState(rng=random.Random(1), A=player_a, B=player_b,
                   turn=1, max_turns=3, active="A", victory_score=8)
    player_a.agent = StuckAgent(player_a)
    player_b.agent = StuckAgent(player_b)

    result = GameLoop(gs, verbose=False).start()  # must return, not hang
    assert result.winner in ("A", "B", "DRAW")
    # The guard ends each action phase promptly rather than spinning to the cap.
    assert player_a.agent.calls < 50
