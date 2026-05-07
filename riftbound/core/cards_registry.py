from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import json
import re

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
        if self.category in (CardType.LEGEND, CardType.CHAMPION):
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


_KNOWN_KEYWORDS: frozenset[str] = frozenset({
    "ACCELERATE", "ACTION", "ASSAULT", "DEATHKNELL", "DEFLECT",
    "EQUIP", "GANKING", "HIDDEN", "LEGION", "MIGHTY", "QUICK",
    "REACTION", "SHIELD", "TANK", "TEMPORARY", "VISION", "WEAPONMASTER",
})

_MASTER_TYPE_MAP: dict[str, CardType] = {
    "champion": CardType.CHAMPION,
    "unit": CardType.UNIT,
    "signature unit": CardType.UNIT,
    "token": CardType.UNIT,
    "spell": CardType.SPELL,
    "signature spell": CardType.SPELL,
    "gear": CardType.GEAR,
    "signature gear": CardType.GEAR,
    "rune": CardType.RUNE,
    "legend": CardType.LEGEND,
    "battlefield": CardType.BATTLEFIELD,
}

_DOMAIN_NAMES: dict[str, Domain] = {
    "fury": Domain.FURY,
    "calm": Domain.CALM,
    "mind": Domain.MIND,
    "body": Domain.BODY,
    "chaos": Domain.CHAOS,
    "order": Domain.ORDER,
}


_VALUED_KEYWORDS: frozenset[str] = frozenset({"ASSAULT", "SHIELD", "DEFLECT"})


def _extract_keywords(rules_text: str) -> tuple[str, ...]:
    upper = rules_text.upper()
    found = []
    for kw in _KNOWN_KEYWORDS:
        if kw in _VALUED_KEYWORDS:
            m = re.search(r"\b" + kw + r"(?:\s+(\d+))?", upper)
            if m:
                n = m.group(1)
                found.append(f"{kw} {n}" if n else kw)
        else:
            if re.search(r"\b" + kw + r"\b", upper):
                found.append(kw)
    return tuple(sorted(found))


def _parse_primary_domain(domain_str: str) -> Optional[Domain]:
    first = (domain_str or "").strip().split()[0].lower() if (domain_str or "").strip() else ""
    return _DOMAIN_NAMES.get(first)


def master_entry_to_spec(entry: Mapping[str, Any]) -> Optional[CardSpec]:
    type_str = str(entry.get("type", "")).strip()
    category = _MASTER_TYPE_MAP.get(type_str.lower())
    if category is None:
        return None
    name = str(entry.get("name", "")).strip()
    if not name:
        return None
    domain = _parse_primary_domain(str(entry.get("domain") or ""))
    if category is CardType.RUNE and domain is None:
        return None
    cost: Mapping[str, Any] = entry.get("cost") or {}
    cost_energy = int(cost.get("energy") or 0)
    cost_power_count = cost.get("power") or 0
    cost_power = domain if cost_power_count and int(cost_power_count) > 0 else None
    might = entry.get("might")
    keywords = _extract_keywords(str(entry.get("rules_text") or ""))
    return CardSpec(
        name=name,
        category=category,
        domain=domain,
        cost_energy=cost_energy,
        cost_power=cost_power,
        might=int(might) if might is not None else None,
        keywords=keywords,
        tags=(),
        effects=(),
        raw=dict(entry),
    )


def load_master_data(path: Optional[Path] = None) -> dict[str, CardSpec]:
    if path is None:
        path = Path(__file__).resolve().parent / "master_data_cards.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        entries = json.load(fh)
    registry: dict[str, CardSpec] = {}
    for entry in entries:
        spec = master_entry_to_spec(entry)
        if spec is not None:
            registry[spec.name] = spec
    return registry


# Master data is the base; hand-crafted cards in data/cards/ override (they have explicit effects).
CARD_REGISTRY: dict[str, CardSpec] = {**load_master_data(), **load_cards_json()}


def load_deck_json(path: Path) -> tuple[list[CardSpec], list[tuple[Domain, int]], Optional[CardSpec]]:
    """Load a deck JSON file.

    Returns (main_deck_specs, [(domain, count)] rune entries, champion_spec_or_None).

    Deck format:
      {
        "name": "...",
        "legend": "Vi",          # optional legend name (identity card)
        "champion": "Vi Destructive",  # chosen champion (goes to Champion Zone, NOT in cards list)
        "runes": [{"domain": "FURY", "count": 6}, ...],
        "cards": [{"name": "...", "count": N}, ...]   # exactly 39 cards
      }
    Rules enforced: ≥39 main deck cards, ≤3 copies per named card, champion not in cards list.
    """
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    # --- Champion ---
    champion_spec: Optional[CardSpec] = None
    champion_name = str(data.get("champion") or "").strip()
    if champion_name:
        champion_spec = CARD_REGISTRY.get(champion_name)
        if champion_spec is None:
            raise ValueError(f"Deck champion '{champion_name}' not found in registry")

    # --- Main deck cards ---
    cards: list[CardSpec] = []
    copy_counts: dict[str, int] = {}
    for entry in data.get("cards", []):
        name = str(entry.get("name", "")).strip()
        count = int(entry.get("count", 1))
        if name == champion_name:
            raise ValueError(
                f"Champion '{champion_name}' must not appear in the cards list — "
                "it starts in the Champion Zone."
            )
        spec = CARD_REGISTRY.get(name)
        if spec is None:
            raise ValueError(f"Deck references unknown card '{name}'")
        copy_counts[name] = copy_counts.get(name, 0) + count
        if copy_counts[name] > 3:
            raise ValueError(
                f"Deck has {copy_counts[name]} copies of '{name}' — maximum is 3."
            )
        for _ in range(count):
            cards.append(spec)

    if len(cards) < 39:
        raise ValueError(
            f"Main deck has {len(cards)} cards — must have at least 39 "
            "(plus 1 champion in the Champion Zone for a legal 40-card deck)."
        )

    # --- Runes ---
    runes: list[tuple[Domain, int]] = []
    for entry in data.get("runes", []):
        domain = _parse_domain(str(entry.get("domain", "")))
        if domain is None:
            raise ValueError(f"Deck has rune with unknown domain '{entry.get('domain')}'")
        count = int(entry.get("count", 1))
        runes.append((domain, count))

    return cards, runes, champion_spec


def iter_cards() -> Iterable[CardSpec]:
    return CARD_REGISTRY.values()