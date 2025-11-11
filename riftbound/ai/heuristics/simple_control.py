from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player
from .base_agent import Agent, Action


class SimpleControl(Agent):
    
    """Defensive agent reinforcing the weakest lane."""

    name = "SimpleControl"

    def decide_action(self, opponent: Player) -> Action:
        bfs = getattr(self.player, "battlefields", [])
        am_A = self.player.name == "A"
        lane = 0
        if bfs:
            best = None
            for i, bf in enumerate(bfs):
                my = bf.count("A" if am_A else "B")
                opp = bf.count("B" if am_A else "A")
                diff = my - opp
                key = (diff, -i)
                if best is None or key < best[0]:
                    best = (key, i)
            lane = best[1] if best else 0


        affordable_units = [
            (i, c)
            for i, c in enumerate(self.player.hand)
            if isinstance(c, UnitCard) and self.player.can_pay_cost(c.cost_energy, c.cost_power)
        ]
        if affordable_units:
            idx, _ = min(affordable_units, key=lambda item: item[1].cost_energy)
            return ("UNIT", idx, lane)
        
        affordable_spells = [
            (i, c)
            for i, c in enumerate(self.player.hand)
            if isinstance(c, SpellCard) and self.player.can_pay_cost(c.cost_energy, c.cost_power)
        ]
        if affordable_spells:
            idx, _ = min(affordable_spells, key=lambda item: item[1].cost_energy)
            return ("SPELL", idx, lane)

        return ("PASS", None, None)
