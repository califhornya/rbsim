from __future__ import annotations
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player
from .base_agent import Agent, Action

class SimpleAggro(Agent):
    """
    Aggro agent: prefers to play Units in the lane where it's behind
    or where the opponent has no presence. Spells are secondary (no effects yet).
    """

    name = "SimpleAggro"

    def decide_action(self, opponent: Player) -> Action:
        bfs = getattr(self.player, "battlefields", [])
        lane = 0
        if bfs:
            am_A = (self.player.name == "A")
            best = None
            for i, bf in enumerate(bfs):
                opp_units = bf.units_B if am_A else bf.units_A
                my_units = bf.units_A if am_A else bf.units_B
                # prefer lanes where opponent is absent, then where we're behind
                key = (opp_units == 0, -(my_units - opp_units))
                if best is None or key > best[0]:
                    best = (key, i)
            lane = best[1] if best else 0

        # play first Unit in hand if any
        for i, c in enumerate(self.player.hand):
            if isinstance(c, UnitCard):
                return ("UNIT", i, lane)

        # otherwise, play a Spell if available
        for i, c in enumerate(self.player.hand):
            if isinstance(c, SpellCard):
                return ("SPELL", i, lane)

        return ("PASS", None, None)
