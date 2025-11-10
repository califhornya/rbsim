from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player

Action = Tuple[str, Optional[int]]  # ("SPELL"|"UNIT"|"PASS", card_index_or_None)

class Agent(ABC):
    name: str = "Agent"

    def __init__(self, player: Player):
        self.player = player

    @abstractmethod
    def decide_action(self, opponent: Player) -> Action:
        """Return ("SPELL", idx) or ("UNIT", idx) or ("PASS", None)."""
        ...
