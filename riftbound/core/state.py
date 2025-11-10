from __future__ import annotations
from dataclasses import dataclass
import random
from .player import Player

@dataclass
class GameState:
    rng: random.Random
    A: Player
    B: Player
    turn: int = 1
    max_turns: int = 20
    active: str = "A"  # "A" or "B"

    def other(self, who: str) -> str:
        return "B" if who == "A" else "A"

    def get_player(self, who: str) -> Player:
        return self.A if who == "A" else self.B
