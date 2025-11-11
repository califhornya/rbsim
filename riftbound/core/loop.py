from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

from .state import GameState
from .cards import SpellCard, UnitCard
from .player import Player
from .battlefield import Battlefield

@dataclass
class Result:
    winner: str  # "A" | "B" | "DRAW"
    turns: int
    units_played: int
    spells_cast: int

# Legacy 3-tuple action signature retained for agents:
# ("SPELL"|"UNIT"|"PASS", hand_index_or_None, battlefield_index_or_None)
Action = Tuple[str, Optional[int], Optional[int]]

class GameLoop:
    """
    Turn structure matching the simulator's Phase 1 goals:

      BEGINNING:
        - Reset per-turn markers on each Battlefield.
        - Snapshot last_controller for CONQUER comparison.
        - Apply HOLD scoring for the active player (once per battlefield per turn).

      DRAW:
        - Active player draws 1 card.

      ACTION:
        - Agent plays a card or passes.
          * UNIT: place a unit onto a chosen battlefield.
          * SPELL: placeholder (no effects yet), reserved for Phase 2 extensions.
        - Placement may cause a lane to become contested (if both sides have units).
        - IMPORTANT: Do NOT decide control changes or score CONQUER in this phase.

      COMBAT:
        - For each lane that became contested at any time this turn, resolve 1-for-1 removal.
        - After Combat, if control is established and differs from last_controller,
          award CONQUER to the active player (once per battlefield per turn).

      END:
        - Check victory by VP then pass the turn.
    """

    def __init__(self, gs: GameState):
        self.gs = gs
        self.units_played = 0
        self.spells_cast = 0

        # Allow agents to inspect lanes
        if hasattr(gs.A, "agent") and gs.A.agent:
            gs.A.agent.player.battlefields = gs.battlefields
        if hasattr(gs.B, "agent") and gs.B.agent:
            gs.B.agent.player.battlefields = gs.battlefields

    # ====== PHASE HELPERS ======

    def _phase_beginning(self, active: str) -> int:
        """Reset per-turn flags, snapshot controllers, then apply HOLD scoring; return VP gained."""
        # Reset per-turn markers
        for bf in self.gs.battlefields:
            bf.begin_turn_reset()
        # Snapshot controllers (state at start of turn)
        for bf in self.gs.battlefields:
            bf.last_controller = bf.controller()

        # HOLD scoring (once per battlefield per turn)
        vps = 0
        for bf in self.gs.battlefields:
            if bf.can_score_hold(active):
                vps += 1
                bf.mark_scored(active)
        return vps

    def _phase_draw(self, ap: Player) -> None:
        ap.draw()

    def _apply_action(self, ap: Player, action: Action) -> None:
        """Execute a UNIT / SPELL / PASS during ACTION; no combat resolution here."""
        kind, idx, lane = action

        # Normalize lane index
        if lane is not None:
            if not (0 <= lane < len(self.gs.battlefields)):
                lane = 0

        if kind == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, UnitCard):
                tgt: Battlefield = self.gs.battlefields[lane if lane is not None else 0]
                if self.gs.active == "A":
                    tgt.units_A += 1
                else:
                    tgt.units_B += 1
                ap.remove_from_hand(idx)
                self.units_played += 1
                # Lane may become contested now; control is not reassigned yet.
                tgt.mark_contested_if_needed()

        elif kind == "SPELL" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, SpellCard):
                # Placeholder: no effects yet (Phase 2 will add effects/costs)
                ap.remove_from_hand(idx)
                self.spells_cast += 1

        # PASS or invalid: do nothing

    def _phase_combat_and_conquer(self, active: str) -> None:
        """Resolve combat on contested lanes, then award CONQUER where applicable."""
        for bf in self.gs.battlefields:
            if bf.contested_this_turn:
                # 1) Resolve Combat
                bf.resolve_combat_simple()
                # 2) Post-Combat: if control newly established by 'active' -> CONQUER
                if bf.can_score_conquer(active):
                    if active == "A":
                        self.gs.points_A += 1
                    else:
                        self.gs.points_B += 1
                    bf.mark_scored(active)
                # 3) Clear contested flag for next turn is handled by begin_turn_reset()

    # ====== MAIN LOOP ======

    def start(self) -> Result:
        gs = self.gs

        # Opening draws
        for _ in range(5):
            gs.A.draw()
            gs.B.draw()

        while gs.turn <= gs.max_turns:
            # ===== BEGINNING =====
            gained = self._phase_beginning(gs.active)
            if gained:
                if gs.active == "A":
                    gs.points_A += gained
                else:
                    gs.points_B += gained
                if gs.points_A >= gs.victory_score:
                    return Result("A", gs.turn, self.units_played, self.spells_cast)
                if gs.points_B >= gs.victory_score:
                    return Result("B", gs.turn, self.units_played, self.spells_cast)

            # ===== DRAW =====
            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))
            self._phase_draw(ap)

            # ===== ACTION =====
            if ap.agent is None:
                act: Action = ("PASS", None, None)
            else:
                act = ap.agent.decide_action(op)
            self._apply_action(ap, act)

            # ===== COMBAT =====
            self._phase_combat_and_conquer(gs.active)
            if gs.points_A >= gs.victory_score:
                return Result("A", gs.turn, self.units_played, self.spells_cast)
            if gs.points_B >= gs.victory_score:
                return Result("B", gs.turn, self.units_played, self.spells_cast)

            # ===== END =====
            gs.active = gs.other(gs.active)
            gs.turn += 1

        # If we reach the turn limit, decide by points; ties are draws
        if gs.points_A > gs.points_B:
            winner = "A"
        elif gs.points_B > gs.points_A:
            winner = "B"
        else:
            winner = "DRAW"
        return Result(winner, gs.turn - 1, self.units_played, self.spells_cast)
