from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from .cards import UnitCard


@dataclass(eq=False)
class UnitInPlay:
    """Runtime representation of a unit on the battlefield or at base.

    IDENTITY equality (``eq=False``): two UnitInPlay objects are equal only if they
    are the SAME object. This is load-bearing — a unit is a mutable runtime entity,
    and multiple copies of the same card produce field-identical objects. With the
    dataclass's default value-equality, ``unit in list`` / ``list.remove(unit)``
    (used throughout battlefield.py, effects.py, loop.py) would match/remove the
    WRONG duplicate, silently losing or duplicating a card (KNOWN_ISSUES #24).
    Identity equality makes those operations, and ``is`` checks, correct."""

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
    empowered: bool = False  # Vendetta EMPOWERED status — persists until the unit leaves the board or is disempowered
    # How many times it is EMPOWERED, for what may be empowered more than once
    # (§442.1.c.1: Kayle Justified, up to three times); 1 otherwise when empowered.
    empower_times: int = 0
    is_token: bool = False  # True for token units (Gold, Recruit, etc.) — cannot be moved to bf
    no_combat_damage: bool = False  # passive "I don't deal combat damage" (recomputed with passives)
    # Keywords effects gave this unit: until the end of the turn ("give it
    # ASSAULT 2 this turn") or while it stays on the board. The card's own
    # keyword list is never changed (it would follow the card to every zone).
    turn_keywords: list = field(default_factory=list)
    granted_keywords: list = field(default_factory=list)
    # "... this combat" (Fortified Position, Durand Memorial, Fiora Peerless):
    # cleared when the combat ends (§468.7).
    combat_keywords: list = field(default_factory=list)
    combat_might: int = 0
    doomed_turn: int = -1            # Noxian Guillotine: dies when it takes damage that turn
    ward_turn: int = -1              # Unlicensed Armory: may be saved the next time it would die
    prevent_next_turn: int = -1      # Counter Strike: the next damage to it this turn is prevented
    was_mighty: bool = False         # "When a unit you control becomes MIGHTY" (Fiora Worthy)
    ward_free: bool = False          # Tactical Retreat: the ward needs no payment
    banish_if_dies_turn: int = -1    # Smite: "If it would die this turn, banish it instead"
    gold_on_death: object = None     # Deadly Flourish: (side, turn) that plays a Gold when it dies
    win_xp_turn: int = -1            # Grim Resolve: "When it wins a combat this turn, gain 2 XP"
    cant_move_turn: int = -1   # "They can't move it this turn" (Vex): that turn number
    equip_bonus_mult: int = 1  # Gearhead: "Each Equipment attached to me gives double" (passive)
    base_might_override: object = None  # "Its base Might becomes 5 this turn": that value, this turn
    moves_this_turn: int = 0   # "The third time I move in a turn" (Yasuo Windrider)
    # Restrictions (recomputed passives, or this turn's): "I can't be chosen by
    # enemy spells and abilities", "can't move to base", "I can't be readied".
    unchoosable: bool = False
    cant_be_chosen_turn: int = -1
    no_move_to_base: bool = False
    cant_ready: bool = False
    spell_immune: bool = False       # Esteemed Hierophant: enemy spell/ability damage prevented
    double_damage_turn: int = -1     # Lotus Trap: "Double all damage dealt to it this turn"
    damage_shield: int = 0           # Ki Barrier: "Prevent the next 7 damage ... this turn"
    conquered_turn: int = -1         # Blighted Battleaxe: "if I didn't conquer this turn"
    # Sanction: "Empower a unit. Disempower it at end of turn" (and the reverse).
    empower_flip_at_end: bool = False
    # Hostile Takeover: (owner side, turn) — goes back to its owner's base at the
    # end of that turn.
    borrowed: Optional[tuple] = None
    extra_tags: list = field(default_factory=list)   # Ivern Friend to All: "I gain that tag"
    # Shady Spectacles: the unit's own card while it "becomes a copy" of another.
    copied_from: Optional[object] = None

    def reset_damage(self) -> None:
        self.damage = 0
        self.bonus_might = 0
        # gear, might_counters, aura_might, passives, hidden intentionally preserved

    def clear_combat_bonuses(self) -> None:
        self.combat_keywords = []
        self.combat_might = 0

    def clear_turn_end_bonuses(self) -> None:
        self.temporary_might = 0
        self.turn_keywords = []
        self.clear_combat_bonuses()
        self.base_might_override = None
        self.moves_this_turn = 0
        self.damage_shield = 0
        if self.empower_flip_at_end:
            self.empowered = not self.empowered
            self.empower_flip_at_end = False

    @property
    def might(self) -> int:
        gear_bonus = sum(
            int(e.get("amount", 0))
            for g in self.gear
            for e in getattr(g, "effects", []) or []
            if isinstance(e, dict) and e.get("effect") == "grant_might" and not e.get("condition")
        )
        # Each Equipment's printed Might bonus ("[might] +2").
        gear_bonus += self.equip_bonus_mult * sum(int(getattr(g, "might", 0) or 0) for g in self.gear)
        base = self.base_might_override if self.base_might_override is not None else int(self.card.might or 0)
        return max(0, base + self.bonus_might + self.temporary_might + self.combat_might
                   + self.might_counters + self.aura_might + self.passive_might + gear_bonus)

    @property
    def tags(self) -> list:
        """The unit's tags: its card's, plus those its Equipment gives ("I am a
        Mech": Experimental Hexplate, GearCard.grants_tags)."""
        return list(self.card.tags or []) + list(self.extra_tags) + \
            [t for g in self.gear for t in getattr(g, "grants_tags", ())]

    def has_keyword(self, keyword: str) -> bool:
        if self.card.has_keyword(keyword):
            return True
        kw = keyword.upper()
        return any(k.upper() == kw or k.upper().startswith(kw + " ")
                   for k in (*self.passive_keywords, *self.turn_keywords, *self.granted_keywords,
                             *self.combat_keywords))

    @staticmethod
    def _kw_amount(k: str, kw: str) -> int:
        """The value of keyword instance `k` if it is `kw` ("ASSAULT 2" -> 2,
        bare "ASSAULT" -> 1), else 0."""
        ku = k.upper()
        if ku == kw:
            return 1
        if ku.startswith(kw + " "):
            try:
                return int(ku[len(kw):].strip())
            except ValueError:
                return 1
        return 0

    def keyword_value(self, keyword: str) -> int:
        """Printed or passive value, plus every instance effects gave it (two
        "give it ASSAULT 2" add up, §807)."""
        base = self.card.keyword_value(keyword)
        kw = keyword.upper()
        passive = max((self._kw_amount(k, kw) for k in self.passive_keywords), default=0)
        given = sum(self._kw_amount(k, kw) for k in (*self.turn_keywords, *self.granted_keywords,
                                                      *self.combat_keywords))
        return max(base, passive) + given


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
    excess_by_A: int = 0   # damage A assigned beyond lethal to B's units
    excess_by_B: int = 0


def _total_might(units: Iterable[UnitInPlay]) -> int:
    return sum(unit.might for unit in units if not unit.stunned and not unit.no_combat_damage)


def _ordered_targets(units: List[UnitInPlay], ignore_tank: bool = False,
                     first=None, damage: int = 0) -> List[UnitInPlay]:
    """Damage-assignment order (§467.2.c): TANK units must take lethal first,
    BACKLINE units last, everyone else in between. On a Tank+Backline conflict
    the controller chooses — we resolve deterministically as Tank (take first).
    `ignore_tank`: the assigner ignores TANK here (Dune Surfer). Within each
    group the assigner orders the units while the damage left can't kill them
    all: `first(units, damage)` picks the next one to take lethal (one choice
    per unit; see kill_order for the baseline); without it, list order."""
    tanks: List[UnitInPlay] = []
    normal: List[UnitInPlay] = []
    backline: List[UnitInPlay] = []
    for u in units:
        if u.has_keyword("TANK") and not ignore_tank:
            tanks.append(u)
        elif u.has_keyword("BACKLINE"):
            backline.append(u)
        else:
            normal.append(u)
    if ignore_tank:
        # Free to choose the order: the most kills first.
        normal.sort(key=lambda u: u.might - u.damage)
    if first is None:
        return tanks + normal + backline
    out: List[UnitInPlay] = []
    for group in (tanks, normal, backline):
        ordered, damage = _chosen_order(group, damage, first)
        out += ordered
    return out


def _chosen_order(group: List[UnitInPlay], damage: int, first) -> tuple:
    """`group` in the assigner's order and the damage left after it: one choice
    per next unit while `damage` can't kill all the living ones, the rest in
    kill_order (the dead last)."""
    alive = [u for u in group if not _is_dead(u)]
    dead = [u for u in group if _is_dead(u)]
    order: List[UnitInPlay] = []
    while len(alive) > 1 and 0 < damage < sum(_lethal(u) for u in alive):
        pick = first(alive, damage)
        order.append(pick)
        alive = [u for u in alive if u is not pick]
        damage -= _lethal(pick)
    if damage > 0:
        rest = kill_order(alive, damage) if alive else []
        damage -= sum(_lethal(u) for u in alive)
    else:
        rest = alive
    return order + rest + dead, max(0, damage)


def kill_order(units: List[UnitInPlay], damage: int) -> List[UnitInPlay]:
    """The order to assign `damage` to `units` in (lethal first, one by one) that
    kills the most enemy Might, then the most units: the best set it can kill,
    mightiest first, then the others in list order. Exact for up to 10 units."""
    if len(units) > 10:
        return sorted(units, key=lambda u: _lethal(u))
    best, best_value = [], (0, 0)
    for mask in range(1, 1 << len(units)):
        pick = [u for i, u in enumerate(units) if mask >> i & 1]
        if sum(_lethal(u) for u in pick) > damage:
            continue
        value = (sum(u.might for u in pick), len(pick))
        if value > best_value:
            best, best_value = pick, value
    best = sorted(best, key=lambda u: -u.might)
    return best + [u for u in units if not any(u is b for b in best)]


def _lethal(unit: UnitInPlay) -> int:
    """Damage that kills `unit` as _apply_damage assigns it (1 for a 0-might
    unit), plus what its damage shield would prevent (Ki Barrier: "Opponents
    can assign it extra combat damage to kill it")."""
    return (1 if unit.might == 0 else max(0, unit.might - unit.damage)) + unit.damage_shield


def _is_dead(unit: UnitInPlay) -> bool:
    """A unit is dead when it has taken damage that meets or exceeds its might.
    For 0-might units, this means receiving any positive damage (lethal=0 per
    RAW, so the first point of damage assigned to them registers as a kill)."""
    if unit.might == 0:
        return unit.damage > 0
    return unit.damage >= unit.might


def _apply_damage(units: List[UnitInPlay], damage: int, take=None,
                  ignore_tank: bool = False, first=None) -> tuple[int, int]:
    """Apply damage to the provided units; return (kills, damage_assigned).

    Lethal-first per §460.2.c: assign each unit its lethal amount before moving
    to the next. For positive-might units, lethal = remaining might. For 0-might
    units, lethal is 0 — but to register a kill (and to honor "you can dump
    excess on the last unit if no other targets") we assign 1 point of damage.
    `take(unit, amount)` is the damage the unit actually takes (prevention,
    doubling: GameLoop._take_damage); the assignment itself is unchanged.
    """

    take = take or (lambda unit, amount: amount)
    assigned = 0
    kills = 0
    for unit in _ordered_targets(units, ignore_tank, first, damage):
        if damage <= 0:
            break
        if _is_dead(unit):
            continue  # already dead this combat — skip
        if unit.might == 0:
            # 0-might unit: any damage kills. Assign 1 to register the kill
            # (more through a damage shield).
            n = min(1 + unit.damage_shield, damage)
            unit.damage += take(unit, n)
            damage -= n
            assigned += n
            if _is_dead(unit):
                kills += 1
            continue
        remaining = unit.might - unit.damage + unit.damage_shield
        to_assign = min(remaining, damage)
        unit.damage += take(unit, to_assign)
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
    take=None,
    ignore_tank_a: bool = False,
    ignore_tank_b: bool = False,
    might_mods: Optional[dict] = None,
    first_a=None,
    first_b=None,
) -> CombatStats:
    """Resolve simultaneous combat between two unit groups.

    attacker_side: "A" if A is attacking (Turn Player), "B" otherwise.
    Attackers gain ASSAULT bonus; defenders gain SHIELD bonus.
    `first_a` / `first_b`: which of A's / B's units its opponent kills first
    (see _ordered_targets).
    """
    stats = CombatStats()

    a_attacks = attacker_side == "A"

    # Apply combat bonuses before resolving damage
    for u in units_a:
        u.bonus_might = u.keyword_value("ASSAULT") if a_attacks else u.keyword_value("SHIELD")
    for u in units_b:
        u.bonus_might = u.keyword_value("ASSAULT") if not a_attacks else u.keyword_value("SHIELD")
    # Combat-only Might changes (Forbidding Waste, Crimson Pigeons): id -> amount.
    for u in list(units_a) + list(units_b):
        u.bonus_might += (might_mods or {}).get(id(u), 0)

    damage_to_a = _total_might(units_b)
    damage_to_b = _total_might(units_a)

    kills_a, assigned_a = _apply_damage(units_a, damage_to_a, take, ignore_tank_a, first_a)
    kills_b, assigned_b = _apply_damage(units_b, damage_to_b, take, ignore_tank_b, first_b)

    stats.kills_A = kills_a
    stats.kills_B = kills_b
    stats.deaths_A = kills_a
    stats.deaths_B = kills_b
    stats.damage_to_A = assigned_a
    stats.damage_to_B = assigned_b
    stats.excess_by_B = max(0, damage_to_a - assigned_a)
    stats.excess_by_A = max(0, damage_to_b - assigned_b)

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


def deal_direct_damage(units: List[UnitInPlay], damage: int, take=None) -> tuple[int, list[UnitInPlay]]:
    """Apply spell or ability damage to a unit group; returns (kills, dead_units)."""

    kills, _ = _apply_damage(units, damage, take)
    dead = [u for u in units if _is_dead(u)]
    units[:] = [u for u in units if not _is_dead(u)]
    # Survivors keep the damage until a combat ends or the turn ends (Core
    # Rules §468.1.a.1 / §317.2.b), so spell and combat damage add up.
    return kills, dead