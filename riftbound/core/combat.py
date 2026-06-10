from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from .cards import UnitCard


@dataclass
class UnitInPlay:
    """Runtime representation of a unit on the battlefield or at base."""

    card: UnitCard
    damage: int = 0
    ready: bool = False
    bonus_might: int = 0  # temporary combat bonus (ASSAULT/SHIELD)
    temporary_might: int = 0  # temporary this-turn bonus (REACTION spells like Discipline)
    gear: list = field(default_factory=list)  # List[GearCard] attached to this unit
    stunned: bool = False
    might_counters: int = 0  # BUFF counters — persistent, max 1 per unit per application
    aura_might: int = 0  # external aura bonus (e.g. Baron Nashor)
    passive_might: int = 0  # overlay recomputed each cycle by passive (continuous) abilities
    passive_keywords: set = field(default_factory=set)  # keywords granted by passive abilities
    hidden: bool = False  # reserved for future HIDDEN keyword
    is_token: bool = False  # True for token units (Gold, Recruit, etc.) — cannot be moved to bf

    def reset_damage(self) -> None:
        self.damage = 0
        self.bonus_might = 0
        # gear, might_counters, aura_might, passives, hidden intentionally preserved

    def clear_turn_end_bonuses(self) -> None:
        self.temporary_might = 0

    @property
    def might(self) -> int:
        gear_bonus = sum(
            int(e.get("amount", 0))
            for g in self.gear
            for e in getattr(g, "effects", []) or []
            if isinstance(e, dict) and e.get("effect") == "grant_might"
        )
        return max(0, int(self.card.might or 0) + self.bonus_might + self.temporary_might + self.might_counters + self.aura_might + self.passive_might + gear_bonus)

    def has_keyword(self, keyword: str) -> bool:
        if self.card.has_keyword(keyword):
            return True
        kw = keyword.upper()
        return any(k.upper() == kw or k.upper().startswith(kw + " ")
                   for k in self.passive_keywords)

    def keyword_value(self, keyword: str) -> int:
        base = self.card.keyword_value(keyword)
        kw = keyword.upper()
        passive = 0
        for k in self.passive_keywords:
            ku = k.upper()
            if ku == kw:
                passive = max(passive, 1)
            elif ku.startswith(kw + " "):
                try:
                    passive = max(passive, int(ku[len(kw):].strip()))
                except ValueError:
                    passive = max(passive, 1)
        return max(base, passive)


@dataclass
class CombatStats:
    """Summary of a single combat step for logging or analytics."""

    kills_A: int = 0
    kills_B: int = 0
    deaths_A: int = 0
    deaths_B: int = 0
    damage_to_A: int = 0
    damage_to_B: int = 0
    dead_A: list = field(default_factory=list)  # List[UnitInPlay] that died
    dead_B: list = field(default_factory=list)  # List[UnitInPlay] that died


def _total_might(units: Iterable[UnitInPlay]) -> int:
    return sum(unit.might for unit in units if not unit.stunned)


def _ordered_targets(units: List[UnitInPlay]) -> List[UnitInPlay]:
    """Damage-assignment order (§460.2.c): TANK units must take lethal first,
    BACKLINE units last, everyone else in between. On a Tank+Backline conflict
    the controller chooses — we resolve deterministically as Tank (take first)."""
    tanks: List[UnitInPlay] = []
    normal: List[UnitInPlay] = []
    backline: List[UnitInPlay] = []
    for u in units:
        if u.has_keyword("TANK"):
            tanks.append(u)
        elif u.has_keyword("BACKLINE"):
            backline.append(u)
        else:
            normal.append(u)
    return tanks + normal + backline


def _is_dead(unit: UnitInPlay) -> bool:
    """A unit is dead when it has taken damage that meets or exceeds its might.
    For 0-might units, this means receiving any positive damage (lethal=0 per
    RAW, so the first point of damage assigned to them registers as a kill)."""
    if unit.might == 0:
        return unit.damage > 0
    return unit.damage >= unit.might


def _apply_damage(units: List[UnitInPlay], damage: int) -> tuple[int, int]:
    """Apply damage to the provided units; return (kills, damage_assigned).

    Lethal-first per §460.2.c: assign each unit its lethal amount before moving
    to the next. For positive-might units, lethal = remaining might. For 0-might
    units, lethal is 0 — but to register a kill (and to honor "you can dump
    excess on the last unit if no other targets") we assign 1 point of damage.
    """

    assigned = 0
    kills = 0
    for unit in _ordered_targets(units):
        if damage <= 0:
            break
        if _is_dead(unit):
            continue  # already dead this combat — skip
        if unit.might == 0:
            # 0-might unit: any damage kills. Assign 1 to register the kill.
            unit.damage += 1
            damage -= 1
            assigned += 1
            kills += 1
            continue
        remaining = unit.might - unit.damage
        to_assign = min(remaining, damage)
        unit.damage += to_assign
        damage -= to_assign
        assigned += to_assign
        if _is_dead(unit):
            kills += 1
    return kills, assigned


def resolve_might_combat(
    units_a: List[UnitInPlay],
    units_b: List[UnitInPlay],
    *,
    attacker_side: str = "A",
) -> CombatStats:
    """Resolve simultaneous combat between two unit groups.

    attacker_side: "A" if A is attacking (Turn Player), "B" otherwise.
    Attackers gain ASSAULT bonus; defenders gain SHIELD bonus.
    """
    stats = CombatStats()

    a_attacks = attacker_side == "A"

    # Apply combat bonuses before resolving damage
    for u in units_a:
        u.bonus_might = u.keyword_value("ASSAULT") if a_attacks else u.keyword_value("SHIELD")
    for u in units_b:
        u.bonus_might = u.keyword_value("ASSAULT") if not a_attacks else u.keyword_value("SHIELD")

    damage_to_a = _total_might(units_b)
    damage_to_b = _total_might(units_a)

    kills_a, assigned_a = _apply_damage(units_a, damage_to_a)
    kills_b, assigned_b = _apply_damage(units_b, damage_to_b)

    stats.kills_A = kills_a
    stats.kills_B = kills_b
    stats.deaths_A = kills_a
    stats.deaths_B = kills_b
    stats.damage_to_A = assigned_a
    stats.damage_to_B = assigned_b

    # Capture dead units before filtering them out. A 0-might unit dies the
    # moment it receives any positive damage; a positive-might unit dies when
    # accumulated damage >= its might.
    stats.dead_A = [u for u in units_a if _is_dead(u)]
    stats.dead_B = [u for u in units_b if _is_dead(u)]

    # Remove defeated units. Untouched 0-might units (damage == 0) survive.
    units_a[:] = [u for u in units_a if not _is_dead(u)]
    units_b[:] = [u for u in units_b if not _is_dead(u)]

    # Survivors clear damage and combat bonuses
    for unit in units_a:
        unit.reset_damage()
    for unit in units_b:
        unit.reset_damage()

    return stats


def deal_direct_damage(units: List[UnitInPlay], damage: int) -> tuple[int, list[UnitInPlay]]:
    """Apply spell or ability damage to a unit group; returns (kills, dead_units)."""

    kills, _ = _apply_damage(units, damage)
    dead = [u for u in units if _is_dead(u)]
    units[:] = [u for u in units if not _is_dead(u)]
    for unit in units:
        unit.reset_damage()
    return kills, dead