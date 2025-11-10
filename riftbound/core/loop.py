from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
from .state import GameState
from .cards import SpellCard, UnitCard
from .player import Player

@dataclass
class Result:
    winner: str  # "A" | "B" | "DRAW"
    turns: int
    units_played: int
    spells_cast: int

class GameLoop:
    """
    Minimal loop with pluggable agents:
      - Start: each player draws 5.
      - Each turn:
          1) Draw 1.
          2) Agent decides action: SPELL / UNIT / PASS (no costs in this prototype).
          3) Attack: active player's units deal 1 each to opponent.
      - Win: opponent HP <= 0 or max turns -> HP tiebreak, else DRAW.
    """
    def __init__(self, gs: GameState):
        self.gs = gs
        self.units_played = 0
        self.spells_cast = 0

    def start(self) -> Result:
        gs = self.gs
        # opening draws
        for _ in range(5):
            gs.A.draw()
            gs.B.draw()

        while gs.turn <= gs.max_turns:
            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))

            # 1) Draw
            ap.draw()

            # 2) Agent decision
            if ap.agent is None:
                # fallback: do nothing if unassigned
                action, idx = ("PASS", None)
            else:
                action, idx = ap.agent.decide_action(op)

            if action == "SPELL" and idx is not None and 0 <= idx < len(ap.hand):
                card = ap.hand[idx]
                if isinstance(card, SpellCard):
                    op.hp -= card.damage
                    ap.remove_from_hand(idx)
                    self.spells_cast += 1
                # else ignore invalid index/type
            elif action == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
                card = ap.hand[idx]
                if isinstance(card, UnitCard):
                    ap.board_units += 1
                    ap.remove_from_hand(idx)
                    self.units_played += 1
            # PASS does nothing

            # 3) Attack step
            if ap.board_units > 0:
                op.hp -= ap.board_units

            # Win check
            if op.hp <= 0:
                return Result(
                    winner=gs.active,
                    turns=gs.turn,
                    units_played=self.units_played,
                    spells_cast=self.spells_cast,
                )

            # Next turn
            gs.active = gs.other(gs.active)
            gs.turn += 1

        # turn limit -> pick winner by HP tiebreaker; else DRAW
        A_hp, B_hp = gs.A.hp, gs.B.hp
        if A_hp > B_hp:
            w = "A"
        elif B_hp > A_hp:
            w = "B"
        else:
            w = "DRAW"

        return Result(
            winner=w,
            turns=self.gs.turn - 1,
            units_played=self.units_played,
            spells_cast=self.spells_cast,
        )
