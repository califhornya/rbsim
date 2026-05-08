from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import random
from .player import Player
from .battlefield import Battlefield
from .cards import Card


@dataclass
class GameState:
    rng: random.Random
    A: Player
    B: Player

    turn: int = 1
    max_turns: int = 40
    active: str = "A"

    # Champion Zone: the Chosen Champion card for each player (not in main deck)
    champion_A: Optional[Card] = None
    champion_B: Optional[Card] = None

    # Victory points via Hold/Conquer
    points_A: int = 0
    points_B: int = 0
    victory_score: int = 8  # Duel Mode default

    # Exactly two battlefields total in 1v1
    battlefields: list[Battlefield] = field(default_factory=lambda: [Battlefield(), Battlefield()])

    # Champion deployment state
    champion_A_deployed: bool = False
    champion_B_deployed: bool = False

    def other(self, who: str) -> str:
        return "B" if who == "A" else "A"

    def get_player(self, who: str) -> Player:
        return self.A if who == "A" else self.B
