from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import json
import re
import warnings

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


# Token "cards" are all filed as category "Token"; these are gear tokens
# (Core Rules §187.5 Gold, §187.12 Bomb), these battlefield tokens (§187.8
# Brush, §187.9 Baron Pit), the rest are unit tokens.
_GEAR_TOKENS = frozenset({"Gold", "Bomb"})
_BATTLEFIELD_TOKENS = frozenset({"Brush", "Baron Pit"})


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
        # Some specs nest their parameters under a "params" key (e.g. Treasure
        # Hunter's token_name); handlers read them flat, so lift them up (the
        # effect's own top-level keys win).
        nested = data.get("params")
        if isinstance(nested, Mapping):
            data = {**nested, **{k: v for k, v in data.items() if k != "params"}}
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
        # The verb, as a mode's or a sequence step's own dict carries it (the
        # name of a choice the effect makes: GameLoop.choose).
        merged.setdefault("effect", self.effect)
        if self.target is not None:
            merged["target"] = self.target
        if self.target_filter:
            # "a unit with 3 [might] or less": handlers read it from the spec
            # (it never reached them, so every filter was ignored).
            merged["target_filter"] = self.target_filter
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
        if category_str.lower() == "token" and name in _GEAR_TOKENS:
            category = CardType.GEAR
        if category_str.lower() == "token" and name in _BATTLEFIELD_TOKENS:
            category = CardType.BATTLEFIELD
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
        # Only keywords the card prints count: not one its abilities mention
        # ("give me ASSAULT 4", "Your Mechs have SHIELD", "EMPOWERED[>] I have
        # GANKING"). An Equipment's own text ("TANK" for its unit) counts too.
        printed_text = rules_text + "\n" + str(data.get("effect_equipped") or "")
        if printed_text.strip():
            heads = _printed_keyword_heads(printed_text)
            keywords = tuple(k for k in keywords
                             if any(k.upper() == h or k.upper().startswith(h + " ") for h in heads))
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
        if self.category in (CardType.UNIT, CardType.CHAMPION):
            # A champion is a unit (it fights, plays from the trash, ACTION in
            # showdowns) that keeps CHAMPION as its category for filters.
            might = self.might if self.might is not None else 0
            unit = UnitCard(
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
            unit.category = self.category
            return unit
        if self.category is CardType.SPELL:
            damage = self.damage if self.damage is not None else 0
            spell = SpellCard(
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
            text = str(self.raw.get("effect") or "")
            spell.repeat_cost = _repeat_cost(text)
            spell.flow_cost = _keyword_pip_cost("FLOW", text)
            return spell
        if self.category is CardType.GEAR:
            gear = GearCard(
                name=self.name,
                cost_energy=self.cost_energy,
                cost_power=self.cost_power,
                cost_power_domain=self.cost_power_domain,
                domain=self.domain,
                tags=list(self.tags),
                keywords=list(self.keywords),
                effects=effects,
                might=self.might,
            )
            # "I am a Mech." on an Equipment: the tag its unit gets.
            gear.grants_tags = tuple(str(e.params.get("tag")) for e in self.effects
                                     if e.effect == "grant_tag" and e.params.get("tag"))
            return gear
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
    "DEATHKNELL", "DEFLECT", "DEPLOY", "DISARM", "EMPOWER", "EMPOWERED",
    "EQUIP", "FLOW", "GANKING", "HIDDEN", "HUNT", "LEGION", "LEVEL",
    "PREDICT", "QUICK-DRAW", "REACTION", "REPEAT", "SHIELD", "SHOW OFF",
    "TANK", "TEMPORARY", "WEAPONMASTER",
})


_VALUED_KEYWORDS: frozenset[str] = frozenset({
    "ASSAULT", "SHIELD", "DEFLECT", "DISARM", "HUNT", "LEVEL", "PREDICT", "REPEAT",
})

# Legacy keyword tokens normalized on load / during generation.
_KEYWORD_MIGRATIONS: dict[str, Optional[str]] = {
    "VISION": "PREDICT 1",
    "QUICK": "QUICK-DRAW",
    "MIGHTY": None,  # not a keyword — drop it
}


_REPEAT_DISCARD = re.compile(r"REPEAT\W+Discard (\d+)", re.IGNORECASE)


def _keyword_pip_cost(keyword: str, rules_text: str) -> Optional[Dict[str, Any]]:
    """A keyword's printed cost: "FLOW [4] [order] [order]" -> 4 Energy and two
    Order Power; "[rune]" is Power of any domain (domain None). None when the
    keyword carries no number. Also "[Flow] [2] [Mind]" (Iterative Design)."""
    m = re.search(r"\[?" + keyword + r"\]?\s*\[?(\d+)\]?((?:\s*\[[A-Za-z]+\])*)", rules_text,
                  re.IGNORECASE)
    if not m:
        return None
    pips = re.findall(r"\[([A-Za-z]+)\]", m.group(2))
    domains = [p.upper() for p in pips if p.upper() in Domain.__members__]
    return {"energy": int(m.group(1)), "power": len(pips),
            "domain": domains[0] if domains and len(domains) == len(pips) else None}


def _repeat_cost(rules_text: str) -> Optional[Dict[str, Any]]:
    """A spell's printed REPEAT cost: "REPEAT [2] [fury]" -> 2 Energy and one
    Fury Power, "[rune]" is Power of any domain, "REPEAT - Discard 1" a
    discard. None when the text has no such cost (the loop then charges the
    spell's Energy cost)."""
    m = _REPEAT_DISCARD.search(rules_text)
    if m:
        return {"discard_cards": int(m.group(1))}
    return _keyword_pip_cost("REPEAT", rules_text)


# Words a printed keyword line can chain through besides keywords: legacy
# names (_KEYWORD_MIGRATIONS) and UNIQUE.
_KEYWORD_LINE_WORDS = ("VISION", "QUICK", "MIGHTY", "UNIQUE")
_REMINDER = re.compile(r"\([^)]*\)")


def _printed_keyword_heads(rules_text: str) -> set[str]:
    """The keywords a card prints (after migrations, without values): those at
    the start of its text, at the start of a sentence ("Kill a gear. FLOW
    [4]"), or chained after another printed keyword ("ASSAULT 2, SHIELD 2",
    "EQUIP [rune] ... TEMPORARY"). Not a keyword mentioned inside a sentence
    ("I have ASSAULT and GANKING"), nor a conditional header ("LEVEL 6[>]",
    "EMPOWERED I have +1 [might]"), nor an ability's timing ("[tap]: REACTION")."""
    # A reminder becomes a marker: a boundary for chaining, never a value.
    t = _REMINDER.sub(" \u00b6 ", rules_text).upper()
    names = sorted(set(_KNOWN_KEYWORDS) | set(_KEYWORD_LINE_WORDS), key=len, reverse=True)
    pat = re.compile(r"\[?\b(" + "|".join(re.escape(k) for k in names) + r")\b\]?"
                     r"(?:[ \t]*\[?[ \t]*\d+[ \t]*\]?)?(?:[ \t]*\[[A-Za-z]+\])*")
    found: list[str] = []
    last_end = None
    for m in pat.finditer(t):
        prefix = t[:m.start()].rstrip(" \t\u00b6")
        chained = last_end is not None and \
            prefix.rstrip(",").rstrip(" \t\u00b6") == t[:last_end].rstrip(" \t\u00b6")
        start = prefix == "" or prefix.endswith((".", "\n", "!"))
        header = t[m.end():].lstrip(" \t").startswith(("[>]", ">"))
        kw = m.group(1)
        # "ACTION [1] [chaos]: Move me ..." / "ACTION Discard 1, [1] [fury]:
        # Banish me ...": the timing of the ability its sentence holds.
        sentence = re.split(r"[.\n¶]", t[m.end():], maxsplit=1)[0]
        ability = kw in ("ACTION", "REACTION") and ":" in sentence
        if not (start or chained) or header or ability or kw == "EMPOWERED":
            continue
        last_end = m.end()
        found.append(kw)
    return {k.split(" ")[0] if k.split(" ")[0] in ("PREDICT",) else k
            for k in _normalize_keywords(found)} - set(_KEYWORD_LINE_WORDS)


def _extract_keywords(rules_text: str) -> tuple[str, ...]:
    # Parenthesized reminder text only explains keywords ("(It has DEPLOY ...)",
    # "(... even before spells and abilities resolve.)"); it never prints the
    # card's own, so drop it before matching. The marker keeps a value from
    # being read across it ("DEFLECT (...) [2] [fury]: ...").
    upper = _REMINDER.sub(" \u00b6 ", rules_text.upper())
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

_BANNED_PATH = Path(__file__).resolve().parent.parent / "data" / "banned_cards.json"


def load_banned_cards() -> frozenset[str]:
    """Names of cards banned in competitive play (riftbound/data/banned_cards.json)."""
    if not _BANNED_PATH.exists():
        return frozenset()
    with _BANNED_PATH.open("r", encoding="utf-8") as fh:
        return frozenset(json.load(fh).get("cards", []))


BANNED_CARDS: frozenset[str] = load_banned_cards()

SIDEBOARD_MAX = 10   # Tournament Rules 601.1.c.1 (constructed)


def _name_counts(entries, what: str, path: Path) -> dict[str, int]:
    """[{"name", "count"}] (or {name: count}) -> {name: count}, every name known."""
    items = entries.items() if isinstance(entries, Mapping) else (
        (str(e.get("name", "")).strip(), int(e.get("count", 1))) for e in entries)
    out: dict[str, int] = {}
    for name, count in items:
        name = str(name).strip()
        if not name:
            continue
        if CARD_REGISTRY.get(name) is None:
            raise ValueError(f"Deck '{path.name}' {what} references unknown card '{name}'")
        out[name] = out.get(name, 0) + int(count)
    return out


def _parse_sideboard(data: Mapping, path: Path) -> tuple[dict[str, int], dict[str, dict]]:
    """Validate and return a deck's sideboard {name: count} and its per-matchup plans.

    A plan is relative to the registered main deck: {"in": {name: n}, "out":
    {name: n}, "champion": optional new Chosen Champion}. Swaps are 1 for 1
    (Tournament Rules 403.4), so "in" and "out" must have the same size.
    """
    sideboard = _name_counts(data.get("sideboard", []), "sideboard", path)
    total = sum(sideboard.values())
    if total > SIDEBOARD_MAX:
        raise ValueError(f"Deck '{path.name}' sideboard has {total} cards — maximum is {SIDEBOARD_MAX}.")
    for name in sideboard:
        if name in BANNED_CARDS:
            warnings.warn(f"Deck '{path.name}' sideboard contains banned card '{name}'", stacklevel=3)
    main = _name_counts(data.get("cards", []), "cards", path)

    plans: dict[str, dict] = {}
    for key, raw in (data.get("sideboard_plans") or {}).items():
        ins = _name_counts(raw.get("in", {}), f"plan '{key}'", path)
        outs = _name_counts(raw.get("out", {}), f"plan '{key}'", path)
        for name, n in ins.items():
            if n > sideboard.get(name, 0):
                raise ValueError(f"Deck '{path.name}' plan '{key}' brings in {n} '{name}' "
                                 f"but the sideboard has {sideboard.get(name, 0)}")
        for name, n in outs.items():
            if n > main.get(name, 0):
                raise ValueError(f"Deck '{path.name}' plan '{key}' takes out {n} '{name}' "
                                 f"but the main deck has {main.get(name, 0)}")
        if sum(ins.values()) != sum(outs.values()):
            raise ValueError(f"Deck '{path.name}' plan '{key}' is not 1 for 1 "
                             f"({sum(ins.values())} in, {sum(outs.values())} out)")
        plans[str(key)] = {"in": ins, "out": outs, "champion": raw.get("champion")}
    return sideboard, plans


def load_sideboard_json(path: Path) -> tuple[dict[str, int], dict[str, dict]]:
    """A deck's sideboard ({name: count}) and its sideboard plans (keyed by the
    opponent's legend name, "*" for any opponent). Both empty if the deck has none."""
    with path.open("r", encoding="utf-8") as fh:
        return _parse_sideboard(json.load(fh), path)


def load_deck_json(path: Path) -> tuple[list[CardSpec], list[tuple[Domain, int]], Optional[CardSpec], Optional[CardSpec], list[CardSpec]]:
    """Load a deck JSON file.

    Returns (main_deck_specs, [(domain, count)] rune entries, champion_spec_or_None,
    legend_spec_or_None, battlefield_specs). The deck may name up to 3 battlefields;
    a single game uses one per player (chosen at build time).

    Deck format:
      {
        "name": "...",
        "legend": "Vi",          # optional legend name (identity card)
        "champion": "Vi Destructive",  # chosen champion (goes to Champion Zone, NOT in cards list)
        "runes": [{"domain": "FURY", "count": 6}, ...],
        "cards": [{"name": "...", "count": N}, ...],   # exactly 39 cards
        "sideboard": [{"name": "...", "count": N}, ...],  # optional, ≤10 cards
        "sideboard_plans": {"<opponent legend>": {"in": {...}, "out": {...}}}  # optional
      }
    Rules enforced: ≥39 main deck cards, ≤3 copies per named card (main deck and
    sideboard combined, Tournament Rules 403.3), champion not in cards list,
    sideboard ≤10 cards (601.1.c.1). The sideboard is read by `load_sideboard_json`.
    Banned cards (BANNED_CARDS) only raise a warning, so older decks still load.
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

    # --- Legend (identity card, starts in play) ---
    legend_spec: Optional[CardSpec] = None
    legend_name = str(data.get("legend") or "").strip()
    if legend_name:
        legend_spec = CARD_REGISTRY.get(legend_name)
        if legend_spec is None:
            raise ValueError(f"Deck legend '{legend_name}' not found in registry")

    # --- Battlefields (the deck names up to 3; one per player is used per game) ---
    battlefield_specs: list[CardSpec] = []
    for entry in data.get("battlefields", []):
        bf_name = str(entry.get("name", "")).strip() if isinstance(entry, dict) else str(entry).strip()
        if not bf_name:
            continue
        bf_spec = CARD_REGISTRY.get(bf_name)
        if bf_spec is None:
            raise ValueError(f"Deck battlefield '{bf_name}' not found in registry")
        battlefield_specs.append(bf_spec)

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
        if name in BANNED_CARDS:
            warnings.warn(f"Deck '{path.name}' contains banned card '{name}'", stacklevel=2)
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

    # --- Sideboard (validated here so a bad one fails with the deck) ---
    sideboard, _plans = _parse_sideboard(data, path)
    for name, count in sideboard.items():
        copy_counts[name] = copy_counts.get(name, 0) + count
        if copy_counts[name] > 3:
            raise ValueError(
                f"Deck has {copy_counts[name]} copies of '{name}' across main deck "
                "and sideboard — maximum is 3."
            )

    # --- Runes ---
    runes: list[tuple[Domain, int]] = []
    for entry in data.get("runes", []):
        domain = _parse_domain(str(entry.get("domain", "")))
        if domain is None:
            raise ValueError(f"Deck has rune with unknown domain '{entry.get('domain')}'")
        count = int(entry.get("count", 1))
        runes.append((domain, count))

    return cards, runes, champion_spec, legend_spec, battlefield_specs


def iter_cards() -> Iterable[CardSpec]:
    return CARD_REGISTRY.values()