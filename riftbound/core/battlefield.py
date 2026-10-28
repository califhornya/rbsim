from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .combat import CombatStats, UnitInPlay, deal_direct_damage, resolve_might_combat

if TYPE_CHECKING:
    from .cards import Card


@dataclass
class FacedownCard:
    """A card in a battlefield's Facedown Zone (Core Rules §106.4), placed there by
    the Hidden keyword's Hide action. Max one per battlefield unless an effect
    raises it (§107.3.b.1: Bandle Tree, Bushwhack Trap); may only exist while
    ``owner`` controls the battlefield. ``turn_hidden`` gates the "playable from the
    NEXT turn onward" rule (§737.1.b)."""
    card: "Card"
    owner: str          # "A" / "B"
    turn_hidden: int


@dataclass(eq=False)
class DeployedGear:
    """A gear on a battlefield via DEPLOY (Core Rules §830). Compared by identity:
    several copies of the same card (e.g. Bomb tokens) can sit here at once.
    ``is_token`` gear cease to exist when killed instead of going to the trash."""
    card: "Card"
    is_token: bool = False


@dataclass(eq=False)
class Battlefield:

    """Battlefield model with Might-based combat and contest tracking. Compared
    by identity: two battlefields with the same card and no units (a mirror
    match) are still different lanes for `battlefields.index(bf)`."""

    units_A: List[UnitInPlay] = field(default_factory=list)
    units_B: List[UnitInPlay] = field(default_factory=list)

    contested_this_turn: bool = False
    scored_this_turn_A: bool = False
    scored_this_turn_B: bool = False
    # "First non-token unit played here this turn" per side (Star Spring trigger).
    first_unit_here_A: bool = False
    first_unit_here_B: bool = False
    # side -> (turn, unit or gear cards it played here that turn): "the first
    # unit or gear they play here on their turn" (Hunters' Circle).
    plays_here: dict = field(default_factory=dict)

    last_controller: Optional[str] = None
    held_by: Optional[str] = None      # control(): who controls it by the rules
    showdown_pending: bool = False
    card: Optional["Card"] = None  # reference card for named battlefields (Baron Pit etc.)
    # Facedown Zone occupants (Hidden keyword), oldest first. One at most unless
    # an effect raises the zone's capacity (GameLoop._facedown_capacity).
    facedowns: List[FacedownCard] = field(default_factory=list)
    # side -> the turn it last conquered here ("a battlefield you conquered this turn").
    conquered_turn: dict = field(default_factory=dict)
    # side -> (turn, excess combat damage it assigned here): "if you assigned 3
    # or more excess damage" (Vi Piltover Enforcer, Yeti Brawler).
    excess_damage: dict = field(default_factory=dict)
    # The combat here (§466.2): ids of units that got their Attacker/Defender
    # designation (their attack/defend triggers fired), and whether its start
    # of combat effects happened. Cleared when the combat ends.
    combat_designated: set = field(default_factory=set)
    combat_started: bool = False
    combat_attacker: Optional[str] = None
    # Gear deployed here (DEPLOY §830), per controlling side.
    gear_A: List[DeployedGear] = field(default_factory=list)
    gear_B: List[DeployedGear] = field(default_factory=list)

    kills_A: int = 0
    kills_B: int = 0
    deaths_A: int = 0
    deaths_B: int = 0

    def _units_for(self, who: str) -> List[UnitInPlay]:
        return self.units_A if who == "A" else self.units_B

    def gear_for(self, who: str) -> List[DeployedGear]:
        return self.gear_A if who == "A" else self.gear_B

    @property
    def facedown(self) -> Optional[FacedownCard]:
        """The first facedown card here, None if there is none. A single-slot
        shorthand: setting it replaces every facedown card here."""
        return self.facedowns[0] if self.facedowns else None

    @facedown.setter
    def facedown(self, fd: Optional[FacedownCard]) -> None:
        self.facedowns = [] if fd is None else [fd]

    def count(self, who: str) -> int:
        return len(self._units_for(who))

    def controller(self) -> Optional[str]:
        """The side alone here, None while both sides (or neither) have units:
        the contest state the showdown/combat machinery runs on. Effects that
        say "a battlefield you control" read control()."""
        if self.units_A and not self.units_B:
            return "A"
        if self.units_B and not self.units_A:
            return "B"
        return None

    def _note_control(self) -> None:
        sole = self.controller()
        if sole is not None or not (self.units_A or self.units_B):
            self.held_by = sole

    def control(self) -> Optional[str]:
        """Who controls this battlefield by the rules (§190.4): the side with
        units here; while both sides have units (a showdown or combat), the side
        that held it before, since control can't change mid-contest (§190.4.b).
        Approximation: a side moving alone onto an uncontrolled battlefield
        controls it at once, not after its showdown."""
        self._note_control()
        return self.held_by

    def begin_turn_reset(self) -> None:
        
        self.contested_this_turn = False
        self.scored_this_turn_A = False
        self.scored_this_turn_B = False
        self.first_unit_here_A = False
        self.first_unit_here_B = False
        self.showdown_pending = False

    def ready_side(self, who: str) -> None:
        for unit in self._units_for(who):
            unit.ready = True

    def add_unit(self, who: str, unit: UnitInPlay) -> None:
        unit_list = self._units_for(who)
        self._note_control()       # who held it before this arrival
        unit_list.append(unit)
        self._note_control()
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False

    def remove_unit(self, who: str, unit: UnitInPlay) -> None:
        unit_list = self._units_for(who)
        if unit in unit_list:
            unit_list.remove(unit)
        self._note_control()
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False

    def pop_unit_for_movement(self, who: str) -> Optional[UnitInPlay]:
        unit_list = self._units_for(who)
        for unit in unit_list:
            if unit.ready:
                unit_list.remove(unit)
                self._note_control()
                if self.units_A and self.units_B:
                    self.contested_this_turn = True
                    if self.controller() is None:
                        self.showdown_pending = True
                else:
                    self.showdown_pending = False
                return unit
        return None

    def resolve_combat_might(self, *, attacker_side: str = "A", **mods) -> CombatStats:
        stats = resolve_might_combat(self.units_A, self.units_B, attacker_side=attacker_side, **mods)
        self.kills_A += stats.kills_A
        self.kills_B += stats.kills_B
        self.deaths_A += stats.deaths_A
        self.deaths_B += stats.deaths_B
        self._note_control()
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False
        return stats

    def can_score_hold(self, active: str) -> bool:
        ctl = self.controller()
        if ctl != active:
            return False
        if active == "A" and self.scored_this_turn_A:
            return False
        if active == "B" and self.scored_this_turn_B:
            return False
        return True

    def mark_scored(self, who: str) -> None:
        if who == "A":
            self.scored_this_turn_A = True
        else:
            self.scored_this_turn_B = True

    def can_score_conquer(self, active: str) -> bool:
        ctl_now = self.controller()
        if ctl_now != active:
            return False
        if self.last_controller == ctl_now:
            return False
        if not self.contested_this_turn:
            return False
        if active == "A" and self.scored_this_turn_A:
            return False
        if active == "B" and self.scored_this_turn_B:
            return False
        return True
    
    def apply_spell_damage(self, target: str, damage: int, take=None) -> tuple[int, list]:
        """Deal direct damage to the target side; returns (kills, dead_units)."""

        units = self._units_for(target)
        kills, dead = deal_direct_damage(units, damage, take)
        self._note_control()
        if self.units_A and self.units_B:
            self.contested_this_turn = True
            if self.controller() is None:
                self.showdown_pending = True
        else:
            self.showdown_pending = False
        return kills, dead
