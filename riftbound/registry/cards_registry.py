from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import json
import re

from riftbound.core.cards import (
    Card,
    BattlefieldCard,
    GearCard,
    LegendCard,
    RuneCard,
    SpellCard,
    UnitCard,
)
from riftbound.core.enums import CardType, Domain


# Domain and type mappings (used by parsing functions)
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
    key = value.strip().lower()
    # First try the mapping (handles "signature spell", "token", etc.)
    if key in _MASTER_TYPE_MAP:
        return _MASTER_TYPE_MAP[key]
    # Then try direct enum lookup
    key_upper = key.upper()
    if key_upper in CardType.__members__:
        return CardType[key_upper]
    raise ValueError(f"Unknown card category '{value}'")


# Top-level EffectSpec fields (everything else in a raw effect dict → params).
_EFFECT_TOP_LEVEL_FIELDS = (
    "trigger", "timing", "condition", "target", "target_filter",
    "scope", "duration", "optional", "cost", "scaling", "additional_cost",
)

# A conditioned effect's numeric threshold is written under any of these keys in
# the corpus (parser drift: `amount` 26×, `n` 9×). The engine reads it as `n`,
# so canonicalize to `n` at load time. Additive: the original key is preserved so
# anything still reading `amount`/`count`/... keeps working.
_COND_THRESHOLD_ALIASES = ("n", "amount", "count", "value", "threshold")


def _normalize_condition(cond: Any) -> Any:
    """Copy a condition's numeric threshold to the canonical `n` key.

    The corpus writes the threshold inconsistently (`amount`, `count`, ...). The
    engine's `_check_condition` reads `params.get("n", 0)`, so a gate like
    `{"amount": 4}` was silently read as threshold 0 ("always true"). This copies
    the first alias found to `n` without dropping the original key."""
    if not isinstance(cond, dict):
        return cond
    params = dict(cond.get("params") or {})
    if "n" not in params:
        for k in _COND_THRESHOLD_ALIASES[1:]:
            if isinstance(params.get(k), (int, float)) and not isinstance(params.get(k), bool):
                params["n"] = params[k]
                break
    return {**cond, "params": params}


@dataclass(frozen=True)
class EffectSpec:
    effect: str
    trigger: str = "on_play"
    timing: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None
    # target/scope/duration default to None meaning "defer to the handler's own
    # default" — this preserves backward compat (e.g. deal_damage defaults to
    # opponent, grant_might defaults to actor/all). Only passed through to the
    # handler when explicitly set on the effect.
    target: Optional[str] = None
    target_filter: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None
    duration: Optional[str] = None
    optional: bool = False
    cost: Optional[Dict[str, Any]] = None
    scaling: Optional[Dict[str, Any]] = None
    # Optional additional cost paid at play time (kicker). Read by
    # Loop._try_pay_additional_costs; gates effects with condition kicker_paid.
    additional_cost: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EffectSpec":
        if "effect" not in data:
            raise ValueError("Effect specification requires an 'effect' field")
        effect = str(data["effect"]).strip()
        if not effect:
            raise ValueError("Effect name cannot be blank")
        top = {k: data[k] for k in _EFFECT_TOP_LEVEL_FIELDS if k in data}
        if "condition" in top:
            top["condition"] = _normalize_condition(top["condition"])
        params = {
            k: v for k, v in data.items()
            if k != "effect" and k not in _EFFECT_TOP_LEVEL_FIELDS
        }
        return cls(effect=effect, params=dict(params), **top)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"effect": self.effect}
        defaults = EffectSpec(effect=self.effect)
        for fname in _EFFECT_TOP_LEVEL_FIELDS:
            value = getattr(self, fname)
            if value != getattr(defaults, fname):
                out[fname] = value
        out.update(self.params)
        return out

    def merged_params(self) -> Dict[str, Any]:
        """Params merged with the resolution-relevant top-level fields, for
        passing to a handler. target/scope/duration are only included when set,
        so unset values defer to each handler's own default (backward compat)."""
        merged = dict(self.params)
        if self.target is not None:
            merged["target"] = self.target
        if self.scope is not None:
            merged["scope"] = self.scope
        if self.duration is not None:
            merged["duration"] = self.duration
        return merged


@dataclass(frozen=True)
class CardSpec:
    name: str
    category: CardType
    domain: Optional[Domain] = None
    cost_energy: int = 0
    cost_power: Optional[int] = None
    cost_power_domain: Optional[Domain] = None
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
        category_str = str(data.get("category", "")).strip()
        category = _parse_card_type(category_str)
        domain_raw = data.get("domain")
        # Handle multi-domain strings (e.g. "FURY MIND") by taking primary domain
        if domain_raw:
            domain_raw = str(domain_raw).strip()
            first_word = domain_raw.split()[0].lower() if domain_raw else ""
            domain = _DOMAIN_NAMES.get(first_word)
        else:
            domain = None
        cost_energy = int(data.get("cost_energy") or 0)
        cost_power_raw = data.get("cost_power")

        cost_power = None
        cost_power_domain = None
        cost_power_domain_raw = data.get("cost_power_domain")

        # Parse cost_power: can be int (numeric cost) or string (domain name from old format)
        if cost_power_raw:
            try:
                cost_power = int(cost_power_raw)
            except (ValueError, TypeError):
                # If not numeric, treat as domain string and assume cost of 1
                domain_str = str(cost_power_raw).strip().lower()
                if domain_str in _DOMAIN_NAMES:
                    cost_power = 1
                    cost_power_domain = _DOMAIN_NAMES[domain_str]

        # cost_power_domain can also be explicitly specified
        if cost_power_domain_raw:
            domain_str = str(cost_power_domain_raw).strip().lower()
            cost_power_domain = _DOMAIN_NAMES.get(domain_str)
        elif cost_power and cost_power_domain is None:
            # If cost_power exists but no domain specified, use card's domain
            cost_power_domain = domain

        might = data.get("might")
        damage = data.get("damage")
        # Rules text source: `effect` is the cleaned field in all_cards.json;
        # fall back to legacy `rules_text`.
        rules_text = str(data.get("rules_text") or data.get("effect") or "")
        raw_keywords = data.get("keywords") or []
        if raw_keywords:
            # Explicit keywords win; normalize legacy tokens.
            keywords = _normalize_keywords(raw_keywords)
        else:
            # No explicit keywords — extract them from the printed rules text so
            # timing keywords (REACTION/ACTION) and combat keywords are tagged
            # even before the card corpus is populated.
            keywords = _extract_keywords(rules_text)
        # Tags: explicit `tags` plus `sub_type` (comma-joined, e.g. "Mech, Piltover").
        tag_list = [str(t) for t in data.get("tags", [])]
        sub_type = data.get("sub_type")
        if sub_type:
            tag_list.extend(t.strip() for t in str(sub_type).split(",") if t.strip())
        tags = tuple(tag_list)
        effects_data = data.get("effects", [])
        effects = tuple(EffectSpec.from_dict(e) for e in effects_data)
        return cls(
            name=name,
            category=category,
            domain=domain,
            cost_energy=cost_energy,
            cost_power=cost_power,
            cost_power_domain=cost_power_domain,
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
                cost_power_domain=self.cost_power_domain,
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
                cost_power_domain=self.cost_power_domain,
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
                cost_power_domain=self.cost_power_domain,
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
                cost_power_domain=self.cost_power_domain,
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
    "ACCELERATE", "ACTION", "AMBUSH", "ASSAULT", "BACKLINE",
    "DEATHKNELL", "DEFLECT", "EQUIP", "GANKING", "HIDDEN",
    "HUNT", "LEGION", "LEVEL", "PREDICT", "QUICK-DRAW",
    "REACTION", "REPEAT", "SHIELD", "TANK", "TEMPORARY",
    "WEAPONMASTER",
})


_VALUED_KEYWORDS: frozenset[str] = frozenset({
    "ASSAULT", "SHIELD", "DEFLECT", "HUNT", "LEVEL", "PREDICT", "REPEAT",
})

# Legacy keyword tokens normalized on load / during generation.
_KEYWORD_MIGRATIONS: dict[str, Optional[str]] = {
    "VISION": "PREDICT 1",
    "QUICK": "QUICK-DRAW",
    "MIGHTY": None,  # not a keyword — drop it
}


def _extract_keywords(rules_text: str) -> tuple[str, ...]:
    upper = rules_text.upper()
    found = []
    for kw in _KNOWN_KEYWORDS:
        # \b around the (escaped) keyword prevents false matches like ACTION
        # inside REACTION. The internal hyphen in QUICK-DRAW is matched literally
        # and still terminates on a \b at each end.
        escaped = re.escape(kw)
        if kw in _VALUED_KEYWORDS:
            # Capture the value in either "KW 2" or bracketed "KW [2]" form.
            m = re.search(r"\b" + escaped + r"\b(?:\s*\[?\s*(\d+)\s*\]?)?", upper)
            if m:
                n = m.group(1)
                found.append(f"{kw} {n}" if n else kw)
        else:
            if re.search(r"\b" + escaped + r"\b", upper):
                found.append(kw)
    return tuple(sorted(found))


def _normalize_keywords(raw_keywords: Iterable[str]) -> tuple[str, ...]:
    """Apply legacy keyword migrations (VISION->PREDICT 1, QUICK->QUICK-DRAW,
    drop MIGHTY) to an explicit keyword list."""
    out: list[str] = []
    for k in raw_keywords:
        token = str(k).strip()
        if not token:
            continue
        head = token.split()[0].upper()
        if head in _KEYWORD_MIGRATIONS:
            replacement = _KEYWORD_MIGRATIONS[head]
            if replacement is not None:
                out.append(replacement)
        else:
            out.append(token)
    return tuple(out)


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
    cost_power = int(cost_power_count) if cost_power_count else None
    cost_power_domain = domain if cost_power else None
    might = entry.get("might")
    keywords = _extract_keywords(str(entry.get("rules_text") or ""))
    return CardSpec(
        name=name,
        category=category,
        domain=domain,
        cost_energy=cost_energy,
        cost_power=cost_power,
        cost_power_domain=cost_power_domain,
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
# Load all card data from /data/cards/ (origins.json, unleashed.json, spiritforged.json, and overlays/)
CARD_REGISTRY: dict[str, CardSpec] = load_cards_json()


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