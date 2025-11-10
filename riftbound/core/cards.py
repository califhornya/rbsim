from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

CardKind = Literal["UNIT", "SPELL"]

@dataclass(frozen=True)
class Card:
    name: str
    kind: CardKind

@dataclass(frozen=True)
class UnitCard(Card):
    def __init__(self, name: str = "Recruit"):
        super().__init__(name=name, kind="UNIT")

@dataclass(frozen=True)
class SpellCard(Card):
    damage: int = 2
    def __init__(self, name: str = "Bolt", damage: int = 2):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", "SPELL")
        object.__setattr__(self, "damage", damage)
