from __future__ import annotations
from dataclasses import dataclass
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

class GameLoop:
    """
    Loop with two Battlefields and scoring rules:
      - BEGINNING (Hold): For each battlefield you already control, if not scored yet this turn, +1 VP.
      - ACTION: Agent plays a card (UNIT -> choose battlefield; SPELL currently no effect).
        If UNIT placement creates/maintains both sides present, lane becomes contested; then we resolve simple combat (1-for-1).
        If after combat the active player *newly* controls the lane and it was contested this turn, they score CONQUER (+1 VP, once per battlefield per turn).
      - First to victory_score wins immediately.
      - Turn ends: switch active.
    """

    def __init__(self, gs: GameState):
        self.gs = gs
        self.units_played = 0
        self.spells_cast = 0

        # Link battlefields to agents so they can inspect distribution
        if hasattr(gs.A, "agent") and gs.A.agent:
            gs.A.agent.player.battlefields = gs.battlefields
        if hasattr(gs.B, "agent") and gs.B.agent:
            gs.B.agent.player.battlefields = gs.battlefields

    def _score_hold(self, active: str) -> int:
        """Apply Hold scoring at Beginning Phase. Returns VPs gained this phase."""
        vps = 0
        for bf in self.gs.battlefields:
            # reset per-turn flags/start-of-turn
            bf.begin_turn_reset()
        # Important: we reset first, THEN compute hold based on current control
        for bf in self.gs.battlefields:
            if bf.can_score_hold(active):
                vps += 1
                bf.mark_scored(active)
        return vps

    def start(self) -> Result:
        gs = self.gs

        # Opening draws
        for _ in range(5):
            gs.A.draw()
            gs.B.draw()

        while gs.turn <= gs.max_turns:
            # ===== BEGINNING PHASE: HOLD scoring =====
            hold_vps = self._score_hold(gs.active)
            if hold_vps:
                if gs.active == "A":
                    gs.points_A += hold_vps
                else:
                    gs.points_B += hold_vps
                if gs.points_A >= gs.victory_score:
                    return Result("A", gs.turn, self.units_played, self.spells_cast)
                if gs.points_B >= gs.victory_score:
                    return Result("B", gs.turn, self.units_played, self.spells_cast)

            # ===== MAIN TURN =====
            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))

            # Draw
            ap.draw()

            # Decision
            if ap.agent is None:
                action, idx, lane = ("PASS", None, None)
            else:
                action, idx, lane = ap.agent.decide_action(op)

            # Guard lane index
            if lane is not None:
                if not (0 <= lane < len(gs.battlefields)):
                    lane = 0  # fallback

            # Snapshot controllers for possible CONQUER checks
            lane_before: dict[int, str | None] = {}
            for i, bf in enumerate(gs.battlefields):
                lane_before[i] = bf.controller()

            # Apply action
            if action == "SPELL" and idx is not None and 0 <= idx < len(ap.hand):
                card = ap.hand[idx]
                if isinstance(card, SpellCard):
                    ap.remove_from_hand(idx)
                    self.spells_cast += 1
                # No effects yet; placeholder

            elif action == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
                card = ap.hand[idx]
                if isinstance(card, UnitCard):
                    tgt: Battlefield = gs.battlefields[lane if lane is not None else 0]
                    # Place unit
                    if gs.active == "A":
                        tgt.units_A += 1
                    else:
                        tgt.units_B += 1
                    ap.remove_from_hand(idx)
                    self.units_played += 1

                    # Mark contested if both sides present
                    tgt.mark_contested_if_needed()

                    # Snapshot last_controller for this lane (pre-combat)
                    tgt.last_controller = lane_before[gs.battlefields.index(tgt)]

                    # Resolve simplified combat now
                    tgt.resolve_combat_simple()

                    # After combat, if contested-this-turn and control changed in favor of active -> CONQUER
                    if tgt.can_score_conquer(gs.active):
                        if gs.active == "A":
                            gs.points_A += 1
                        else:
                            gs.points_B += 1
                        tgt.mark_scored(gs.active)

                        if gs.points_A >= gs.victory_score:
                            return Result("A", gs.turn, self.units_played, self.spells_cast)
                        if gs.points_B >= gs.victory_score:
                            return Result("B", gs.turn, self.units_played, self.spells_cast)

            # (No attack phase for now; combat already resolved on placement.)

            # ===== TURN END =====
            gs.active = gs.other(gs.active)
            gs.turn += 1

        # Turn limit: winner by points, else draw
        if gs.points_A > gs.points_B:
            w = "A"
        elif gs.points_B > gs.points_A:
            w = "B"
        else:
            w = "DRAW"
        return Result(w, gs.turn - 1, self.units_played, self.spells_cast)
