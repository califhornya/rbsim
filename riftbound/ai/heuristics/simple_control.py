from __future__ import annotations
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

        energy = self.player.energy
        affordable_units = [
            (i, c) for i, c in enumerate(self.player.hand) if isinstance(c, UnitCard) and c.cost <= energy
        ]
        if affordable_units:
            # Control prefers to conserve energy; choose the cheapest viable Unit
            idx, _ = min(affordable_units, key=lambda item: item[1].cost)
            return ("UNIT", idx, lane)
        
        affordable_spells = [
            (i, c) for i, c in enumerate(self.player.hand) if isinstance(c, SpellCard) and c.cost <= energy
        ]
        if affordable_spells:
            idx, _ = min(affordable_spells, key=lambda item: item[1].cost)
            return ("SPELL", idx, lane)

        return ("PASS", None, None)
