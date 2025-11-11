from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from .enums import CardType, Domain


@dataclass
class Card:
    """Base Riftbound card model used by the simulator."""
    name: str
    category: CardType
    cost_energy: int = 0
    cost_power: Optional[Domain] = None
    domain: Optional[Domain] = None
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    might: Optional[int] = None
    uuid: str = field(default_factory=lambda: str(uuid4()), compare=False)

    def has_keyword(self, keyword: str) -> bool:
        return keyword.upper() in {k.upper() for k in self.keywords}   

@dataclass
class UnitCard(Card):
    """Unit cards represent creatures that can contest battlefields."""

    def __init__(
        self,
        name: str = "Recruit",
        *,
        cost_energy: int = 1,
        cost_power: Optional[Domain] = None,
        domain: Optional[Domain] = None,
        might: int = 1,
        tags: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            category=CardType.UNIT,
            cost_energy=cost_energy,
            cost_power=cost_power,
            domain=domain,
            tags=list(tags or []),
            keywords=list(keywords or []),
            might=might,
        )

@dataclass
class SpellCard(Card):
    """Spell cards resolve an immediate effect when cast."""

    damage: int = 2
    
    def __init__(
        self,
        name: str = "Bolt",
        *,
        cost_energy: int = 2,
        cost_power: Optional[Domain] = None,
        domain: Optional[Domain] = None,
        damage: int = 2,
        tags: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            category=CardType.SPELL,
            cost_energy=cost_energy,
            cost_power=cost_power,
            domain=domain,
            tags=list(tags or []),
            keywords=list(keywords or []),
        )
        self.damage = damage


@dataclass
class GearCard(Card):
    def __init__(
        self,
        name: str,
        *,
        cost_energy: int = 0,
        cost_power: Optional[Domain] = None,
        domain: Optional[Domain] = None,
        tags: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            category=CardType.GEAR,
            cost_energy=cost_energy,
            cost_power=cost_power,
            domain=domain,
            tags=list(tags or []),
            keywords=list(keywords or []),
        )


@dataclass
class RuneCard(Card):
    def __init__(
        self,
        name: str,
        *,
        domain: Domain,
        tags: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            category=CardType.RUNE,
            cost_energy=0,
            cost_power=None,
            domain=domain,
            tags=list(tags or []),
            keywords=list(keywords or []),
        )


@dataclass
class LegendCard(Card):
    def __init__(
        self,
        name: str,
        *,
        cost_energy: int = 0,
        cost_power: Optional[Domain] = None,
        domain: Optional[Domain] = None,
        tags: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
        might: Optional[int] = None,
    ) -> None:
        super().__init__(
            name=name,
            category=CardType.LEGEND,
            cost_energy=cost_energy,
            cost_power=cost_power,
            domain=domain,
            tags=list(tags or []),
            keywords=list(keywords or []),
            might=might,
        )


@dataclass
class BattlefieldCard(Card):
    def __init__(
        self,
        name: str,
        *,
        tags: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            category=CardType.BATTLEFIELD,
            tags=list(tags or []),
            keywords=list(keywords or []),
        )
