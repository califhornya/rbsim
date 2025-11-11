from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from riftbound.core.player import Player

# Legacy action signature kept for backward-compat:
# ("SPELL"|"UNIT"|"MOVE"|"PASS", hand_index_or_None, lane_or_src, [lane_or_dst for MOVE])
# For UNIT/SPELL: (TYPE, hand_idx, target_lane)
# For MOVE: ("MOVE", None, src_lane, dst_lane)
Action = Tuple[str, Optional[int], Optional[int], Optional[int]]

class Agent(ABC):
    name: str = "Agent"

    def __init__(self, player: Player):
        self.player = player
        # GameLoop will inject: self.player.battlefields = list[Battlefield]

    @abstractmethod
    def decide_action(self, opponent: Player) -> Action:
        """Return a chosen action."""
        ...
