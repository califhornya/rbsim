from __future__ import annotations
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player
from .base_agent import Agent, Action

class SimpleControl(Agent):
    """
    Control agent: reinforces lanes where it's behind the most.
    Plays Units first; Spells are secondary (no effects yet).
    """

    name = "SimpleControl"

    def decide_action(self, opponent: Player) -> Action:
        bfs = getattr(self.player, "battlefields", [])
        am_A = (self.player.name == "A")
        lane = 0
        if bfs:
            best = None
            for i, bf in enumerate(bfs):
                my = bf.units_A if am_A else bf.units_B
                opp = bf.units_B if am_A else bf.units_A
                diff = my - opp  # negative means we're behind
                key = (diff, -i)
                if best is None or key < best[0]:
                    best = (key, i)
            lane = best[1] if best else 0

        for i, c in enumerate(self.player.hand):
            if isinstance(c, UnitCard):
                return ("UNIT", i, lane)

        for i, c in enumerate(self.player.hand):
            if isinstance(c, SpellCard):
                return ("SPELL", i, lane)

        return ("PASS", None, None)
