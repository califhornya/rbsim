from __future__ import annotations
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player
from .base_agent import Agent, Action

class SimpleControl(Agent):
    name = "SimpleControl"

    def decide_action(self, opponent: Player) -> Action:
        # 1) Build board first: play a unit if you have fewer than 3 units.
        if self.player.board_units < 3:
            for i, c in enumerate(self.player.hand):
                if isinstance(c, UnitCard):
                    return ("UNIT", i)
        # 2) If any spell is lethal, cast it.
        for i, c in enumerate(self.player.hand):
            if isinstance(c, SpellCard) and c.damage >= opponent.hp:
                return ("SPELL", i)
        # 3) If you already have 3+ units, cast a spell.
        for i, c in enumerate(self.player.hand):
            if isinstance(c, SpellCard):
                return ("SPELL", i)
        # 4) Otherwise, play a unit if still available.
        for i, c in enumerate(self.player.hand):
            if isinstance(c, UnitCard):
                return ("UNIT", i)
        # 5) Pass.
        return ("PASS", None)
