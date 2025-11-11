from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Battlefield:
    """
    Minimal battlefield model for Riftbound-like scoring:
      - units_A / units_B: counts of units currently present.
      - contested_this_turn: True if at any point this turn both sides had units here.
      - scored_this_turn_A/B: once-per-battlefield-per-turn guards.
      - last_controller: controller snapshot at the moment we enter Action on this battlefield,
        used to decide whether a post-combat control change is a valid CONQUER.
    """
    units_A: int = 0
    units_B: int = 0

    contested_this_turn: bool = False
    scored_this_turn_A: bool = False
    scored_this_turn_B: bool = False

    # We snapshot controller before resolving an action on this lane
    last_controller: str | None = None

    def controller(self) -> str | None:
        if self.units_A > 0 and self.units_B == 0:
            return "A"
        if self.units_B > 0 and self.units_A == 0:
            return "B"
        return None  # neutral or contested presence

    def begin_turn_reset(self) -> None:
        """Reset per-turn scoring guards and contested marker."""
        self.contested_this_turn = False
        self.scored_this_turn_A = False
        self.scored_this_turn_B = False
        self.last_controller = None

    def mark_contested_if_needed(self) -> None:
        if self.units_A > 0 and self.units_B > 0:
            self.contested_this_turn = True

    def resolve_combat_simple(self) -> None:
        """
        Extremely simplified combat: remove equal pairs 1-for-1.
        This produces a post-combat board where one side may control or the lane is empty.
        """
        if self.units_A > 0 and self.units_B > 0:
            m = min(self.units_A, self.units_B)
            self.units_A -= m
            self.units_B -= m
        # After this, either both 0 (neutral) or one side has >0 (control)

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
        """
        Conquer is valid if:
          - lane was contested at some point this turn,
          - control is now with 'active',
          - control changed compared to last_controller snapshot,
          - and this player hasn't scored this battlefield yet this turn.
        """
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
