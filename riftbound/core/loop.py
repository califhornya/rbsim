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

class GameLoop:
    """
    Minimal loop:
      - Start: each player draws 5.
      - Each turn:
          1) Draw 1.
          2) Action: try to cast lethal spell; else play one spell; else play one unit (no costs).
          3) Attack: units deal 1 damage each to opponent.
      - Win: opponent HP <= 0 or max turns -> DRAW.
    """
    def __init__(self, gs: GameState):
        self.gs = gs

    def start(self) -> Result:
        gs = self.gs
        # opening draws
        for _ in range(5):
            gs.A.draw()
            gs.B.draw()

        while gs.turn <= gs.max_turns:
            # active player ref
            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))

            # 1) Draw
            ap.draw()

            # 2) Action: prioritize lethal spell, else spell, else unit
            # find first spell in hand
            spell_idx = next((i for i, c in enumerate(ap.hand) if isinstance(c, SpellCard)), None)
            unit_idx  = next((i for i, c in enumerate(ap.hand) if isinstance(c, UnitCard)), None)

            played_action = False
            if spell_idx is not None:
                spell = ap.hand[spell_idx]
                assert isinstance(spell, SpellCard)
                # lethal check
                if spell.damage >= op.hp:
                    op.hp -= spell.damage
                    ap.remove_from_hand(spell_idx)
                    played_action = True
                else:
                    # cast any spell anyway
                    op.hp -= spell.damage
                    ap.remove_from_hand(spell_idx)
                    played_action = True
            elif unit_idx is not None:
                # play a unit: adds 1 attacker permanently
                ap.board_units += 1
                ap.remove_from_hand(unit_idx)
                played_action = True

            # 3) Attack step: all current units attack for 1 each
            if ap.board_units > 0:
                op.hp -= ap.board_units

            # Win check
            if op.hp <= 0:
                return Result(winner=gs.active, turns=gs.turn)

            # Next turn
            gs.active = gs.other(gs.active)
            gs.turn += 1

        # turn limit -> draw; pick winner by HP tie-breaker to avoid too many draws
        A_hp, B_hp = self.gs.A.hp, self.gs.B.hp
        if A_hp > B_hp:
            return Result(winner="A", turns=self.gs.turn - 1)
        if B_hp > A_hp:
            return Result(winner="B", turns=self.gs.turn - 1)
        return Result(winner="DRAW", turns=self.gs.turn - 1)
