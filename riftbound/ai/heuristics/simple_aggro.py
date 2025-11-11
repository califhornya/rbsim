from __future__ import annotations
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

        energy = self.player.energy

        # play the most expensive affordable Unit in hand if any
        affordable_units = [
            (i, c) for i, c in enumerate(self.player.hand) if isinstance(c, UnitCard) and c.cost <= energy
        ]
        if affordable_units:
            idx, _ = max(affordable_units, key=lambda item: item[1].cost)
            return ("UNIT", idx, lane)

        # otherwise, play the most expensive affordable Spell if available
        affordable_spells = [
            (i, c) for i, c in enumerate(self.player.hand) if isinstance(c, SpellCard) and c.cost <= energy
        ]
        if affordable_spells:
            idx, _ = max(affordable_spells, key=lambda item: item[1].cost)
            return ("SPELL", idx, lane)

        return ("PASS", None, None)
