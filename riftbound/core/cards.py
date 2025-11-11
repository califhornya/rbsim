from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

CardKind = Literal["UNIT", "SPELL"]

@dataclass(frozen=True)
class Card:
    name: str
    kind: CardKind
    cost: int        

@dataclass(frozen=True)
class UnitCard(Card):
    def __init__(self, name: str = "Recruit", cost: int = 1):
        super().__init__(name=name, kind="UNIT", cost=cost)

@dataclass(frozen=True)
class SpellCard(Card):
    damage: int = 2
    
    def __init__(self, name: str = "Bolt", cost: int = 2, damage: int = 2):
        super().__init__(name=name, kind="SPELL", cost=cost)
        object.__setattr__(self, "damage", damage)
