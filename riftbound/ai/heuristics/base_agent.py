from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from riftbound.core.player import Player

# Action signature supports multiple action types:
# ("SPELL"|"UNIT"|"MOVE"|"PASS"|"ABILITY", ...)
# For UNIT/SPELL: (TYPE, hand_idx, target_lane)
# For MOVE: ("MOVE", None, src_lane, dst_lane)
# For ABILITY: ("ABILITY", ability_id, arg)
Action = tuple

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

    def decide_optional(self, card, effect_name: str) -> bool:
        """Whether to take an optional ("you may ...") effect. Default: yes — this
        preserves the engine's historical "optional effects always resolve"
        behavior. Agents (esp. search) may override to decline or branch."""
        return True

    def decide_predict_recycle(self, card) -> bool:
        """VISION / PREDICT 1: whether to recycle the revealed top card to the
        bottom of the deck. Default: no (keep it, the neutral null action). Search
        / learning agents may override to recycle a bad top card."""
        return False

    def decide_mode(self, card, n_modes: int) -> int:
        """Modal "choose one": pick which mode (0..n_modes-1) to resolve. Default:
        the first mode. Search / learning agents may override to branch."""
        return 0
