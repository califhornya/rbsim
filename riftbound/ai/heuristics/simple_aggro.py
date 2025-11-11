from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.player import Player
from .base_agent import Agent, Action


class SimpleAggro(Agent):

    """Aggressive baseline agent prioritising board presence."""

    name = "SimpleAggro"

    def decide_action(self, opponent: Player) -> Action:
        bfs = getattr(self.player, "battlefields", [])
        lane = 0
        if bfs:
            am_A = self.player.name == "A"
            best = None
            for i, bf in enumerate(bfs):
                opp_units = bf.count("B" if am_A else "A")
                my_units = bf.count("A" if am_A else "B")
                key = (opp_units == 0, -(my_units - opp_units))
                if best is None or key > best[0]:
                    best = (key, i)
            lane = best[1] if best else 0


        affordable_units = [
            (i, c)
            for i, c in enumerate(self.player.hand)
            if isinstance(c, UnitCard) and self.player.can_pay_cost(c.cost_energy, c.cost_power)
        ]
        if affordable_units:
            idx, _ = max(affordable_units, key=lambda item: item[1].cost_energy)
            return ("UNIT", idx, lane)

        # otherwise, play the most expensive affordable Spell if available
        affordable_spells = [
            (i, c)
            for i, c in enumerate(self.player.hand)
            if isinstance(c, SpellCard) and self.player.can_pay_cost(c.cost_energy, c.cost_power)
        ]
        if affordable_spells:
            idx, _ = max(affordable_spells, key=lambda item: item[1].cost_energy)
            return ("SPELL", idx, lane)

        return ("PASS", None, None)
