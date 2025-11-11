from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player

# ("SPELL"|"UNIT"|"PASS", hand_index_or_None, battlefield_index_or_None)
Action = Tuple[str, Optional[int], Optional[int]]

class Agent(ABC):
    name: str = "Agent"

    def __init__(self, player: Player):
        self.player = player
        # GameLoop will inject: self.player.battlefields = list[Battlefield]

    @abstractmethod
    def decide_action(self, opponent: Player) -> Action:
        """Return ("SPELL"| "UNIT"| "PASS", hand_idx, battlefield_idx)."""
        ...
