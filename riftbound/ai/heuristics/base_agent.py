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
    def decide_action(self, opponent: Player, cards_played: int = 0) -> Action:
        """Return a chosen action. cards_played is the number of cards played this turn (for LEGION cost reduction)."""
        ...

    @abstractmethod
    def decide_mulligan(self) -> list[int]:
        """Return indices of hand cards to send back. Empty list = keep all."""
        ...

    def decide_showdown_action(self, opponent: Player, bf_idx: int) -> Action:
        """Return ACTION or REACTION spell to play during showdown, or PASS."""
        return ("PASS", None, None)

    def decide_reaction(self, opponent: Player, chain: list) -> Action:
        """Return REACTION spell to play in response to chain, or PASS."""
        return ("PASS", None, None)
