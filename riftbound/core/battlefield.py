from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Battlefield:
    """
    Battlefield model focused on scoring and post-contest combat:

      - units_A / units_B: counts of units currently present.
      - contested_this_turn: True if at any point this turn both sides had units here.
      - scored_this_turn_A/B: once-per-battlefield-per-turn guards (for Hold/Conquer).
      - last_controller: controller snapshot at BEGINNING (start of active player's turn),
        used to evaluate whether a post-combat control change qualifies for CONQUER.
    """
    units_A: int = 0
    units_B: int = 0

    contested_this_turn: bool = False
    scored_this_turn_A: bool = False
    scored_this_turn_B: bool = False

    last_controller: str | None = None

    def controller(self) -> str | None:
        """Return 'A', 'B', or None (neutral/contested)."""
        if self.units_A > 0 and self.units_B == 0:
            return "A"
        if self.units_B > 0 and self.units_A == 0:
            return "B"
        return None

    def begin_turn_reset(self) -> None:
        """Reset per-turn markers; the loop will set last_controller after reset."""
        self.contested_this_turn = False
        self.scored_this_turn_A = False
        self.scored_this_turn_B = False
        # last_controller is set by the GameLoop at the start of the turn.

    def mark_contested_if_needed(self) -> None:
        """Mark lane contested if both sides are present at this moment."""
        if self.units_A > 0 and self.units_B > 0:
            self.contested_this_turn = True

    def resolve_combat_simple(self) -> None:
        """
        Minimal Combat resolution: remove equal pairs 1-for-1.
        After this, the lane is either neutral (both 0) or controlled by one side (>0 vs 0).
        """
        if self.units_A > 0 and self.units_B > 0:
            m = min(self.units_A, self.units_B)
            self.units_A -= m
            self.units_B -= m

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
        Conquer is valid if, after Combat:
          - control is now with 'active',
          - control changed compared to last_controller snapshot,
          - the lane was contested at some point this turn,
          - and 'active' hasn't already scored this battlefield this turn.
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
