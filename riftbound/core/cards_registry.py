from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import json

from .cards import (
    Card,
    BattlefieldCard,
    GearCard,
    LegendCard,
    RuneCard,
    SpellCard,
    UnitCard,
)
from .enums import CardType, Domain


def _parse_domain(value: Optional[str]) -> Optional[Domain]:
    if value is None:
        return None
    key = value.strip().upper()
    if not key:
        return None
    if key in Domain.__members__:
        return Domain[key]
    for domain in Domain:
        if domain.value == key:
            return domain
    raise ValueError(f"Unknown domain '{value}'")


def _parse_card_type(value: str) -> CardType:
    key = value.strip().upper()
    if key in CardType.__members__:
        return CardType[key]
    raise ValueError(f"Unknown card category '{value}'")


@dataclass(frozen=True)
class EffectSpec:
    effect: str
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EffectSpec":
        if "effect" not in data:
            raise ValueError("Effect specification requires an 'effect' field")
        effect = str(data["effect"]).strip()
        if not effect:
            raise ValueError("Effect name cannot be blank")
        params = {k: v for k, v in data.items() if k != "effect"}
        return cls(effect=effect, params=dict(params))

    def to_dict(self) -> Dict[str, Any]:
        return {"effect": self.effect, **self.params}


@dataclass(frozen=True)
class CardSpec:
    name: str
    category: CardType
    domain: Optional[Domain] = None
    cost_energy: int = 0
    cost_power: Optional[Domain] = None
    might: Optional[int] = None
    damage: Optional[int] = None
    keywords: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    effects: tuple[EffectSpec, ...] = ()
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CardSpec":
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Card specification requires a name")
        category = _parse_card_type(str(data.get("category", "")))
        domain = _parse_domain(data.get("domain")) if "domain" in data else None
        cost_energy = int(data.get("cost_energy", 0))
        cost_power = _parse_domain(data.get("cost_power")) if data.get("cost_power") else None
        might = data.get("might")
        damage = data.get("damage")
        keywords = tuple(str(k) for k in data.get("keywords", []))
        tags = tuple(str(t) for t in data.get("tags", []))
        effects_data = data.get("effects", [])
        effects = tuple(EffectSpec.from_dict(e) for e in effects_data)
        return cls(
            name=name,
            category=category,
            domain=domain,
            cost_energy=cost_energy,
            cost_power=cost_power,
            might=int(might) if might is not None else None,
            damage=int(damage) if damage is not None else None,
            keywords=keywords,
            tags=tags,
            effects=effects,
            raw=dict(data),
        )

    def instantiate(self) -> Card:
        effects = [effect.to_dict() for effect in self.effects]
        if self.category is CardType.UNIT:
            might = self.might if self.might is not None else 0
            return UnitCard(
                name=self.name,
                cost_energy=self.cost_energy,
                cost_power=self.cost_power,
                domain=self.domain,
                might=might,
                tags=list(self.tags),
                keywords=list(self.keywords),
                effects=effects,
            )
        if self.category is CardType.SPELL:
            damage = self.damage if self.damage is not None else 0
            return SpellCard(
                name=self.name,
                cost_energy=self.cost_energy,
                cost_power=self.cost_power,
                domain=self.domain,
                damage=damage,
                tags=list(self.tags),
                keywords=list(self.keywords),
                effects=effects,
            )
        if self.category is CardType.GEAR:
            return GearCard(
                name=self.name,
                cost_energy=self.cost_energy,
                cost_power=self.cost_power,
                domain=self.domain,
                tags=list(self.tags),
                keywords=list(self.keywords),
                effects=effects,
            )
        if self.category is CardType.RUNE:
            if self.domain is None:
                raise ValueError(f"Rune card '{self.name}' requires a domain")
            return RuneCard(
                name=self.name,
                domain=self.domain,
                tags=list(self.tags),
                keywords=list(self.keywords),
                effects=effects,
            )
        if self.category is CardType.LEGEND:
            return LegendCard(
                name=self.name,
                cost_energy=self.cost_energy,
                cost_power=self.cost_power,
                domain=self.domain,
                tags=list(self.tags),
                keywords=list(self.keywords),
                might=self.might,
                effects=effects,
            )
        if self.category is CardType.BATTLEFIELD:
            return BattlefieldCard(
                name=self.name,
                tags=list(self.tags),
                keywords=list(self.keywords),
                effects=effects,
            )
        raise ValueError(f"Unsupported card category for '{self.name}'")


def load_cards_json(base_path: Optional[Path] = None) -> dict[str, CardSpec]:
    """Load every card specification from the data directory."""

    if base_path is None:
        base_path = Path(__file__).resolve().parent.parent / "data" / "cards"
    registry: dict[str, CardSpec] = {}
    if not base_path.exists():
        return registry

    for json_path in sorted(base_path.rglob("*.json")):
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError(f"Card file '{json_path}' must contain a list of card specs")
        for entry in payload:
            spec = CardSpec.from_dict(entry)
            registry[spec.name] = spec
    return registry


CARD_REGISTRY: dict[str, CardSpec] = load_cards_json()


def iter_cards() -> Iterable[CardSpec]:
    return CARD_REGISTRY.values()
