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

    def reset_damage(self) -> None:
        self.damage = 0
        self.bonus_might = 0

    @property
    def might(self) -> int:
        return max(0, int(self.card.might or 0) + self.bonus_might)

    def has_keyword(self, keyword: str) -> bool:
        return self.card.has_keyword(keyword)

    def keyword_value(self, keyword: str) -> int:
        return self.card.keyword_value(keyword)


@dataclass
class CombatStats:
    """Summary of a single combat step for logging or analytics."""

    kills_A: int = 0
    kills_B: int = 0
    deaths_A: int = 0
    deaths_B: int = 0
    damage_to_A: int = 0
    damage_to_B: int = 0


def _total_might(units: Iterable[UnitInPlay]) -> int:
    return sum(unit.might for unit in units)


def _ordered_targets(units: List[UnitInPlay]) -> List[UnitInPlay]:
    tanks = [u for u in units if u.has_keyword("TANK")]
    others = [u for u in units if not u.has_keyword("TANK")]
    return tanks + others


def _apply_damage(units: List[UnitInPlay], damage: int) -> tuple[int, int]:
    """Apply damage to the provided units; return (kills, damage_assigned)."""

    assigned = 0
    kills = 0
    for unit in _ordered_targets(units):
        if damage <= 0:
            break
        remaining = max(0, unit.might - unit.damage)
        if remaining <= 0:
            continue
        to_assign = min(remaining, damage)
        unit.damage += to_assign
        damage -= to_assign
        assigned += to_assign
        if unit.damage >= unit.might and unit.might > 0:
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

    # Remove defeated units (u.might == 0 with no damage is immortal by rule, keep them)
    units_a[:] = [u for u in units_a if u.damage < u.might or u.might == 0]
    units_b[:] = [u for u in units_b if u.damage < u.might or u.might == 0]

    # Survivors clear damage and combat bonuses
    for unit in units_a:
        unit.reset_damage()
    for unit in units_b:
        unit.reset_damage()

    return stats


def deal_direct_damage(units: List[UnitInPlay], damage: int) -> int:
    """Apply spell or ability damage to a unit group; returns kills."""

    kills, _ = _apply_damage(units, damage)
    units[:] = [u for u in units if u.damage < u.might or u.might == 0]
    for unit in units:
        unit.reset_damage()
    return kills