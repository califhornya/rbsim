from __future__ import annotations
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player
from .base_agent import Agent, Action

class SimpleAggro(Agent):
    name = "SimpleAggro"

    def decide_action(self, opponent: Player) -> Action:
        # 1) If any spell is lethal, cast it.
        for i, c in enumerate(self.player.hand):
            if isinstance(c, SpellCard) and c.damage >= opponent.hp:
                return ("SPELL", i)
        # 2) Otherwise, cast the first spell you find.
        for i, c in enumerate(self.player.hand):
            if isinstance(c, SpellCard):
                return ("SPELL", i)
        # 3) Otherwise, play a unit if available.
        for i, c in enumerate(self.player.hand):
            if isinstance(c, UnitCard):
                return ("UNIT", i)
        # 4) Pass.
        return ("PASS", None)
