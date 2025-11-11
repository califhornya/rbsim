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

# Legacy action signature retained for agents:
# ("SPELL"|"UNIT"|"MOVE"|"PASS", hand_index_or_None, battlefield_index_or_src, optional_dst)
# Agents implemented before MOVE support still emit 3-tuples; the loop normalises them.
Action = Tuple[str, Optional[int], Optional[int], Optional[int]]

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
          * SPELL: spend energy to remove opposing units on the chosen battlefield.
          * MOVE: relocate one of the active player's units between battlefields.
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
        # Any lane already containing both sides immediately triggers a showdown flag.
        for bf in self.gs.battlefields:
            bf.mark_contested_if_needed()

        # Rune Channeling (active player first, then opponent)
        active_player = self.gs.get_player(active)
        active_player.channel()
        opposing_player = self.gs.get_player(self.gs.other(active))
        opposing_player.channel()


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
        """Execute a UNIT / SPELL / MOVE / PASS during ACTION; no combat resolution here."""
        # Support historical 3-tuple actions by padding a None destination.
        if len(action) == 3:  # type: ignore[arg-type]
            kind, idx, lane = action  # type: ignore[misc]
            dst_lane = None
        else:
            kind, idx, lane, dst_lane = action

        # Normalize lane index
        if lane is not None:
            if not (0 <= lane < len(self.gs.battlefields)):
                lane = 0
        if dst_lane is not None and not (0 <= dst_lane < len(self.gs.battlefields)):
            dst_lane = None        

        if kind == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, UnitCard):
                if not ap.can_pay(card.cost):
                    return
                if not ap.pay(card.cost):
                    return
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
                if not ap.can_pay(card.cost):
                    return
                if not ap.pay(card.cost):
                    return
                tgt: Battlefield = self.gs.battlefields[lane if lane is not None else 0]
                # Simple damage model: remove opposing units up to damage amount.
                if self.gs.active == "A":
                    tgt.units_B = max(0, tgt.units_B - card.damage)
                else:
                    tgt.units_A = max(0, tgt.units_A - card.damage)
                ap.remove_from_hand(idx)
                self.spells_cast += 1
                # Spell effects may keep a lane contested if both sides remain.
                tgt.mark_contested_if_needed()
                
        elif kind == "MOVE":
            src = lane
            dst = dst_lane
            if src is None or dst is None or src == dst:
                return
            if not (0 <= src < len(self.gs.battlefields)) or not (0 <= dst < len(self.gs.battlefields)):
                return
            src_bf = self.gs.battlefields[src]
            dst_bf = self.gs.battlefields[dst]
            if self.gs.active == "A":
                if src_bf.units_A <= 0:
                    return
                src_bf.units_A -= 1
                dst_bf.units_A += 1
            else:
                if src_bf.units_B <= 0:
                    return
                src_bf.units_B -= 1
                dst_bf.units_B += 1
            # Moving can cause (or maintain) contests on either lane.
            src_bf.mark_contested_if_needed()
            dst_bf.mark_contested_if_needed()        

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
