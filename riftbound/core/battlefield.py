from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .combat import CombatStats, UnitInPlay, deal_direct_damage, resolve_might_combat

@dataclass
class Battlefield:

    """Battlefield model with Might-based combat and contest tracking."""

    units_A: List[UnitInPlay] = field(default_factory=list)
    units_B: List[UnitInPlay] = field(default_factory=list)

    contested_this_turn: bool = False
    scored_this_turn_A: bool = False
    scored_this_turn_B: bool = False

    last_controller: Optional[str] = None
    showdown_pending: bool = False

    kills_A: int = 0
    kills_B: int = 0
    deaths_A: int = 0
    deaths_B: int = 0

    def _units_for(self, who: str) -> List[UnitInPlay]:
        return self.units_A if who == "A" else self.units_B

    def count(self, who: str) -> int:
        return len(self._units_for(who))

    def controller(self) -> Optional[str]:
        if self.units_A and not self.units_B:
            return "A"
        if self.units_B and not self.units_A:
            return "B"
        return None

    def begin_turn_reset(self) -> None:
        
        self.contested_this_turn = False
        self.scored_this_turn_A = False
        self.scored_this_turn_B = False
        self.showdown_pending = False

    def ready_side(self, who: str) -> None:
        for unit in self._units_for(who):
            unit.ready = True

    def mark_contested_if_needed(self) -> None:
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
    
    def add_unit(self, who: str, unit: UnitInPlay) -> None:
        unit_list = self._units_for(who)
        unit_list.append(unit)
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False

    def remove_unit(self, who: str, unit: UnitInPlay) -> None:
        unit_list = self._units_for(who)
        if unit in unit_list:
            unit_list.remove(unit)
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False

    def pop_unit_for_movement(self, who: str) -> Optional[UnitInPlay]:
        unit_list = self._units_for(who)
        for unit in unit_list:
            if unit.ready:
                unit_list.remove(unit)
                if self.units_A and self.units_B:
                    self.contested_this_turn = True
                    if self.controller() is None:
                        self.showdown_pending = True
                else:
                    self.showdown_pending = False
                return unit
        return None

    def resolve_combat_might(self) -> CombatStats:
        stats = resolve_might_combat(self.units_A, self.units_B)
        self.kills_A += stats.kills_A
        self.kills_B += stats.kills_B
        self.deaths_A += stats.deaths_A
        self.deaths_B += stats.deaths_B
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False
        return stats

    def can_score_hold(self, active: str) -> bool:
        ctl = self.controller()
        if ctl != active:
            return False
        if active == "A" and self.scored_this_turn_A:
            return False
        if active == "B" and self.scored_this_turn_B:
            return False
        return True

    def mark_scored(self, who: str) -> None:
        if who == "A":
            self.scored_this_turn_A = True
        else:
            self.scored_this_turn_B = True

    def can_score_conquer(self, active: str) -> bool:
        ctl_now = self.controller()
        if ctl_now != active:
            return False
        if self.last_controller == ctl_now:
            return False
        if not self.contested_this_turn:
            return False
        if active == "A" and self.scored_this_turn_A:
            return False
        if active == "B" and self.scored_this_turn_B:
            return False
        return True
    
    def apply_spell_damage(self, target: str, damage: int) -> int:
        """Deal direct damage to the target side; returns kills."""

        units = self._units_for(target)
        kills = deal_direct_damage(units, damage)
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False
        return kills
