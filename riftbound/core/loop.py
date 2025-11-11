from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .state import GameState
from .cards import SpellCard, UnitCard
from .combat import UnitInPlay
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
    """Core turn structure, extended with Might combat, rune channeling and movement."""

    def __init__(self, gs: GameState):
        self.gs = gs
        self.units_played = 0
        self.spells_cast = 0

        if hasattr(gs.A, "agent") and gs.A.agent:
            gs.A.agent.player.battlefields = gs.battlefields
        if hasattr(gs.B, "agent") and gs.B.agent:
            gs.B.agent.player.battlefields = gs.battlefields

    # ====== PHASE HELPERS ======

    def _ready_active_units(self, active: str) -> None:
        player = self.gs.get_player(active)
        player.ready_base_units()
        for bf in self.gs.battlefields:
            bf.ready_side(active)

    def _phase_beginning(self, active: str) -> int:
        for bf in self.gs.battlefields:
            bf.begin_turn_reset()
        for bf in self.gs.battlefields:
            bf.last_controller = bf.controller()
        for bf in self.gs.battlefields:
            if bf.units_A and bf.units_B:
                bf.contested_this_turn = True
                if bf.controller() is None:
                    bf.showdown_pending = True

        self._ready_active_units(active)

        active_player = self.gs.get_player(active)
        active_player.channel()
        opposing_player = self.gs.get_player(self.gs.other(active))
        opposing_player.channel()


        vps = 0
        for bf in self.gs.battlefields:
            if bf.can_score_hold(active):
                vps += 1
                bf.mark_scored(active)
        return vps

    def _phase_draw(self, ap: Player) -> None:
        ap.draw()

    def _apply_action(self, ap: Player, action: Action) -> None:
        if len(action) == 3:  # type: ignore[arg-type]
            kind, idx, lane = action  # type: ignore[misc]
            dst_lane = None
        else:
            kind, idx, lane, dst_lane = action

        if lane is not None and not (0 <= lane < len(self.gs.battlefields)):
            lane = 0
        if dst_lane is not None and not (0 <= dst_lane < len(self.gs.battlefields) + 1):
            dst_lane = None

        base_index = len(self.gs.battlefields)           

        if kind == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, UnitCard):
                if not ap.can_pay_cost(card.cost_energy, card.cost_power):
                    return
                if not ap.pay_cost(card.cost_energy, card.cost_power):
                    return
                target: Battlefield = self.gs.battlefields[lane if lane is not None else 0]
                unit = UnitInPlay(card=card, ready=card.has_keyword("ACCELERATE"))
                target.add_unit(self.gs.active, unit)
                if not unit.ready:
                    unit.ready = False
                ap.remove_from_hand(idx)
                self.units_played += 1
                

        elif kind == "SPELL" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, SpellCard):
                if not ap.can_pay_cost(card.cost_energy, card.cost_power):
                    return
                if not ap.pay_cost(card.cost_energy, card.cost_power):
                    return
                target: Battlefield = self.gs.battlefields[lane if lane is not None else 0]
                if self.gs.active == "A":
                    target.apply_spell_damage("B", card.damage)
                else:
                    target.apply_spell_damage("A", card.damage)
                ap.remove_from_hand(idx)
                self.spells_cast += 1

        elif kind == "MOVE":
            src = lane
            dst = dst_lane
            if src is None or dst is None or src == dst:
                return
            if src not in range(len(self.gs.battlefields) + 1):
                return
            if dst not in range(len(self.gs.battlefields) + 1):
                return
            
            side = self.gs.active
            base = ap.base_units

            if src == base_index:
                if dst == base_index:
                    return
                unit = ap.pop_base_unit()
                if unit is None:
                    return
                unit.ready = False
                target_bf = self.gs.battlefields[dst]
                target_bf.add_unit(side, unit)
            elif dst == base_index:
                src_bf = self.gs.battlefields[src]
                unit = src_bf.pop_unit_for_movement(side)
                if unit is None:
                    return
                unit.ready = True
                base.append(unit)
            else:
                src_bf = self.gs.battlefields[src]
                dst_bf = self.gs.battlefields[dst]
                unit = src_bf.pop_unit_for_movement(side)
                if unit is None:
                    return
                if not unit.has_keyword("GANKING"):
                    src_bf.add_unit(side, unit)
                    unit.ready = True
                    return
                unit.ready = False
                dst_bf.add_unit(side, unit)    

    def _phase_showdown(self, active: str, opponent: str) -> None:
        for bf in self.gs.battlefields:
            if bf.showdown_pending and bf.controller() is None:
                # Placeholder: acknowledge showdown without additional actions
                bf.showdown_pending = False

    def _phase_combat_and_conquer(self, active: str) -> None:

        for bf in self.gs.battlefields:
            if bf.contested_this_turn:
                bf.resolve_combat_might()
                if bf.can_score_conquer(active):
                    if active == "A":
                        self.gs.points_A += 1
                    else:
                        self.gs.points_B += 1
                    bf.mark_scored(active)


    # ====== MAIN LOOP ======

    def start(self) -> Result:
        gs = self.gs

        for _ in range(5):
            gs.A.draw()
            gs.B.draw()

        while gs.turn <= gs.max_turns:
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


            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))
            self._phase_draw(ap)


            if ap.agent is None:
                act: Action = ("PASS", None, None)
            else:
                act = ap.agent.decide_action(op)
            self._apply_action(ap, act)

            self._phase_showdown(gs.active, gs.other(gs.active))

            self._phase_combat_and_conquer(gs.active)
            if gs.points_A >= gs.victory_score:
                return Result("A", gs.turn, self.units_played, self.spells_cast)
            if gs.points_B >= gs.victory_score:
                return Result("B", gs.turn, self.units_played, self.spells_cast)


            gs.active = gs.other(gs.active)
            gs.turn += 1

        if gs.points_A > gs.points_B:
            winner = "A"
        elif gs.points_B > gs.points_A:
            winner = "B"
        else:
            winner = "DRAW"
        return Result(winner, gs.turn - 1, self.units_played, self.spells_cast)
