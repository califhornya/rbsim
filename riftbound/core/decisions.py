"""Typed decision protocol for the pausable engine, search agents, and web UI.

Nothing here mutates game state or changes how existing agents run — it is an
additive layer that gives a *typed* view of "whose turn is it, what can they
legally do, and what can they see". The heuristic agents keep using raw action
tuples and the full opponent ``Player``; new consumers (Greedy / ISMCTS / the web
server) use these structures instead.

Three pieces:
  * :class:`DecisionPoint` — the kinds of choice the engine pauses on.
  * :class:`GameAction`    — a typed, engine-round-trippable action.
  * :class:`Observation`   — an information-set view for one player (own hand +
    all public board state; the opponent's hand and both deck orders appear only
    as counts, never contents — the info-leak the raw ``Player`` handoff has).
  * :class:`DecisionRequest` — point + acting player + observation + legal actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .state import GameState


class DecisionPoint(str, Enum):
    """A point at which the engine needs a choice from a player."""

    MULLIGAN = "mulligan"
    TURN_ACTION = "turn_action"
    REACTION = "reaction"
    SHOWDOWN_ACTION = "showdown_action"


# --- actions -----------------------------------------------------------------

@dataclass(frozen=True)
class GameAction:
    """A single choice, round-trippable to the raw tuple the engine consumes.

    ``kind`` is one of PASS / UNIT / SPELL / GEAR / CHAMPION / MOVE / ABILITY.
    Field meaning depends on kind (matches the historical tuple grammar):
      * UNIT/SPELL/GEAR : index=hand_idx, lane=target battlefield; a UNIT's
                          dst_lane is the battlefield it is played to (None: base)
      * CHAMPION        : lane=target battlefield (index unused)
      * MOVE            : index=the unit's position in its location's list (None:
                          the first ready unit there), lane=src, dst_lane=dst
      * ABILITY         : index=ability_id ("ACTIVATED"), lane=ability index
    """

    kind: str
    index: Optional[Any] = None
    lane: Optional[Any] = None
    dst_lane: Optional[int] = None
    label: str = ""

    def to_engine(self) -> tuple:
        """The raw action tuple ``GameLoop._apply_action`` expects."""
        if self.kind == "MOVE" or (self.kind == "UNIT" and self.dst_lane is not None):
            return (self.kind, self.index, self.lane, self.dst_lane)
        return (self.kind, self.index, self.lane)

    @classmethod
    def from_engine(cls, t: tuple, label: str = "") -> "GameAction":
        if len(t) == 4:
            return cls(t[0], t[1], t[2], t[3], label)
        return cls(t[0], t[1], t[2], None, label)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "index": self.index,
            "lane": self.lane,
            "dst_lane": self.dst_lane,
            "label": self.label,
        }

    # Convenience constructors keep call sites in legality.py readable.
    @classmethod
    def pass_(cls) -> "GameAction":
        return cls("PASS", None, None, None, "Pass")

    @classmethod
    def play(cls, kind: str, hand_idx: int, lane: int, label: str) -> "GameAction":
        return cls(kind, hand_idx, lane, None, label)

    @classmethod
    def champion(cls, lane: int, label: str) -> "GameAction":
        return cls("CHAMPION", None, lane, None, label)

    @classmethod
    def hide(cls, hand_idx: int, lane: int, label: str) -> "GameAction":
        return cls("HIDE", hand_idx, lane, None, label)

    @classmethod
    def hidden_play(cls, lane: int, label: str) -> "GameAction":
        return cls("HIDDEN_PLAY", None, lane, None, label)

    @classmethod
    def move(cls, src: int, dst: int, label: str, unit: Optional[int] = None) -> "GameAction":
        return cls("MOVE", unit, src, dst, label)

    @classmethod
    def ability(cls, ability_id: str, arg: Any, label: str) -> "GameAction":
        return cls("ABILITY", ability_id, arg, None, label)


# --- observation (information set for one player) -----------------------------

# Keywords a unit view reports as in effect (printed, granted or passive): the
# ones that change how it fights, moves or can be chosen.
UNIT_KEYWORDS = ("ASSAULT", "SHIELD", "TANK", "BACKLINE", "DEFLECT", "GANKING",
                 "TEMPORARY", "HIDDEN")


@dataclass(frozen=True)
class UnitView:
    name: str
    might: int
    ready: bool
    stunned: bool
    is_token: bool
    gear: tuple[str, ...]
    damage: int = 0
    buffed: bool = False
    empowered: bool = False
    keywords: tuple[str, ...] = ()       # of UNIT_KEYWORDS, in effect now

    def to_dict(self) -> dict:
        return {
            "name": self.name, "might": self.might, "ready": self.ready,
            "stunned": self.stunned, "is_token": self.is_token, "gear": list(self.gear),
            "damage": self.damage, "buffed": self.buffed, "empowered": self.empowered,
            "keywords": list(self.keywords),
        }


@dataclass(frozen=True)
class BattlefieldView:
    A: tuple[UnitView, ...]
    B: tuple[UnitView, ...]
    controller: Optional[str]
    named: Optional[str]
    # Gear deployed here (DEPLOY §830), by name, per controlling side. Public.
    gear_A: tuple[str, ...] = ()
    gear_B: tuple[str, ...] = ()
    # Who has scored here this turn, who has a facedown card here (not which).
    scored_A: bool = False
    scored_B: bool = False
    facedown: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "A": [u.to_dict() for u in self.A],
            "B": [u.to_dict() for u in self.B],
            "controller": self.controller,
            "named": self.named,
            "gear_A": list(self.gear_A),
            "gear_B": list(self.gear_B),
            "scored_A": self.scored_A,
            "scored_B": self.scored_B,
            "facedown": self.facedown,
        }


@dataclass(frozen=True)
class Observation:
    """What ``viewer`` can legitimately see. The opponent's hand appears only as
    ``opp_hand_count`` and neither deck's order is exposed (counts only), so an
    agent built on this can't cheat by reading hidden information."""

    viewer: str
    turn: int
    active: str
    victory_score: int
    my_points: int
    opp_points: int
    my_energy: int
    opp_energy: int
    my_power: dict[str, int]
    opp_power: dict[str, int]
    my_xp: int
    opp_xp: int
    my_hand: tuple[str, ...]
    opp_hand_count: int
    my_deck_count: int
    opp_deck_count: int
    my_trash: tuple[str, ...]
    opp_trash: tuple[str, ...]
    my_base_units: tuple[UnitView, ...]
    opp_base_units: tuple[UnitView, ...]
    my_runes: int
    opp_runes: int
    battlefields: tuple[BattlefieldView, ...] = field(default_factory=tuple)
    # The battlefield a showdown is running at (None: no showdown), and the
    # spells on the chain (public), the viewer's and the opponent's.
    showdown_bf: Optional[int] = None
    my_chain: tuple[str, ...] = ()
    opp_chain: tuple[str, ...] = ()
    # What else is public (or known to the viewer): the cards left in the
    # viewer's own Main Deck (sorted: the order stays hidden), banished cards,
    # legends (and whether they're ready), champions still in the Champion Zone,
    # unattached gear in base, ready runes and runes by domain, cards played
    # this turn.
    my_deck: tuple[str, ...] = ()
    my_banished: tuple[str, ...] = ()
    opp_banished: tuple[str, ...] = ()
    my_legend: Optional[str] = None
    opp_legend: Optional[str] = None
    my_legend_ready: bool = False
    opp_legend_ready: bool = False
    my_champion: Optional[str] = None
    opp_champion: Optional[str] = None
    my_base_gear: tuple[str, ...] = ()
    opp_base_gear: tuple[str, ...] = ()
    my_runes_ready: int = 0
    opp_runes_ready: int = 0
    my_rune_domains: dict = field(default_factory=dict)
    opp_rune_domains: dict = field(default_factory=dict)
    my_cards_played: int = 0
    opp_cards_played: int = 0

    @staticmethod
    def _uview(u) -> "UnitView":
        return UnitView(
            name=u.card.name,
            might=u.might,
            ready=u.ready,
            stunned=u.stunned,
            is_token=u.is_token,
            gear=tuple(getattr(g, "name", "?") for g in u.gear),
            damage=int(u.damage or 0),
            buffed=u.might_counters > 0,
            empowered=bool(getattr(u, "empowered", False)),
            keywords=tuple(k for k in UNIT_KEYWORDS if u.has_keyword(k)),
        )

    @classmethod
    def from_state(cls, gs: "GameState", viewer: str) -> "Observation":
        me = gs.get_player(viewer)
        opp = gs.get_player(gs.other(viewer))

        def bview(bf) -> BattlefieldView:
            return BattlefieldView(
                A=tuple(cls._uview(u) for u in bf.units_A),
                B=tuple(cls._uview(u) for u in bf.units_B),
                controller=bf.control(),
                named=getattr(bf.card, "name", None) if bf.card else None,
                gear_A=tuple(dg.card.name for dg in bf.gear_A),
                gear_B=tuple(dg.card.name for dg in bf.gear_B),
                scored_A=bool(bf.scored_this_turn_A),
                scored_B=bool(bf.scored_this_turn_B),
                facedown=bf.facedown.owner if bf.facedown is not None else None,
            )

        def legend(side):
            unit = gs.legend_unit_A if side == "A" else gs.legend_unit_B
            card = gs.legend_A if side == "A" else gs.legend_B
            name = unit.card.name if unit is not None else getattr(card, "name", None)
            return name, bool(unit.ready) if unit is not None else False

        def champion(side):
            card = gs.champion_A if side == "A" else gs.champion_B
            deployed = gs.champion_A_deployed if side == "A" else gs.champion_B_deployed
            return None if card is None or deployed else card.name

        def runes(p):
            return (sum(1 for rs in p.rune_pool.values() for r in rs if r.ready),
                    {d.name: len(rs) for d, rs in p.rune_pool.items() if rs})

        other = gs.other(viewer)
        my_leg, opp_leg = legend(viewer), legend(other)
        my_ready, my_doms = runes(me)
        opp_ready, opp_doms = runes(opp)

        my_pts, opp_pts = (gs.points_A, gs.points_B) if viewer == "A" else (gs.points_B, gs.points_A)
        return cls(
            viewer=viewer,
            turn=gs.turn,
            active=gs.active,
            victory_score=gs.victory_score,
            my_points=my_pts,
            opp_points=opp_pts,
            my_energy=me.energy,
            opp_energy=opp.energy,
            my_power={d.name: n for d, n in me.power_pool.items()},
            opp_power={d.name: n for d, n in opp.power_pool.items()},
            my_xp=gs.get_xp(viewer),
            opp_xp=gs.get_xp(gs.other(viewer)),
            my_hand=tuple(c.name for c in me.hand),
            opp_hand_count=len(opp.hand),
            my_deck_count=len(me.deck.cards),
            opp_deck_count=len(opp.deck.cards),
            my_trash=tuple(c.name for c in me.trash),
            opp_trash=tuple(c.name for c in opp.trash),
            my_base_units=tuple(cls._uview(u) for u in me.base_units),
            opp_base_units=tuple(cls._uview(u) for u in opp.base_units),
            my_runes=me.total_runes_in_play(),
            opp_runes=opp.total_runes_in_play(),
            battlefields=tuple(bview(bf) for bf in gs.battlefields),
            showdown_bf=gs.showdown_bf_idx if gs.showdown_active else None,
            my_chain=tuple(i.card.name for i in gs.chain if i.player == viewer),
            opp_chain=tuple(i.card.name for i in gs.chain if i.player != viewer),
            my_deck=tuple(sorted(c.name for c in me.deck.cards)),
            my_banished=tuple(c.name for c in me.banished),
            opp_banished=tuple(c.name for c in opp.banished),
            my_legend=my_leg[0], opp_legend=opp_leg[0],
            my_legend_ready=my_leg[1], opp_legend_ready=opp_leg[1],
            my_champion=champion(viewer), opp_champion=champion(other),
            my_base_gear=tuple(g.name for g in me.base_gear),
            opp_base_gear=tuple(g.name for g in opp.base_gear),
            my_runes_ready=my_ready, opp_runes_ready=opp_ready,
            my_rune_domains=my_doms, opp_rune_domains=opp_doms,
            my_cards_played=int(gs.cards_played_this_turn.get(viewer, 0)),
            opp_cards_played=int(gs.cards_played_this_turn.get(other, 0)),
        )

    def to_dict(self) -> dict:
        return {
            "viewer": self.viewer,
            "turn": self.turn,
            "active": self.active,
            "victory_score": self.victory_score,
            "my_points": self.my_points,
            "opp_points": self.opp_points,
            "my_energy": self.my_energy,
            "opp_energy": self.opp_energy,
            "my_power": dict(self.my_power),
            "opp_power": dict(self.opp_power),
            "my_xp": self.my_xp,
            "opp_xp": self.opp_xp,
            "my_hand": list(self.my_hand),
            "opp_hand_count": self.opp_hand_count,
            "my_deck_count": self.my_deck_count,
            "opp_deck_count": self.opp_deck_count,
            "my_trash": list(self.my_trash),
            "opp_trash": list(self.opp_trash),
            "my_base_units": [u.to_dict() for u in self.my_base_units],
            "opp_base_units": [u.to_dict() for u in self.opp_base_units],
            "my_runes": self.my_runes,
            "opp_runes": self.opp_runes,
            "battlefields": [b.to_dict() for b in self.battlefields],
            "showdown_bf": self.showdown_bf,
            "my_chain": list(self.my_chain),
            "opp_chain": list(self.opp_chain),
            "my_deck_size": len(self.my_deck),
            "my_banished": list(self.my_banished),
            "opp_banished": list(self.opp_banished),
            "my_legend": self.my_legend, "opp_legend": self.opp_legend,
            "my_legend_ready": self.my_legend_ready, "opp_legend_ready": self.opp_legend_ready,
            "my_champion": self.my_champion, "opp_champion": self.opp_champion,
            "my_base_gear": list(self.my_base_gear), "opp_base_gear": list(self.opp_base_gear),
            "my_runes_ready": self.my_runes_ready, "opp_runes_ready": self.opp_runes_ready,
            "my_rune_domains": dict(self.my_rune_domains),
            "opp_rune_domains": dict(self.opp_rune_domains),
            "my_cards_played": self.my_cards_played, "opp_cards_played": self.opp_cards_played,
        }


# --- request -----------------------------------------------------------------

@dataclass(frozen=True)
class DecisionRequest:
    """A paused game asking ``player`` to choose. ``legal_actions`` is empty for
    MULLIGAN (the choice is a subset of hand indices, not a tuple action — the
    driver reads ``observation.my_hand`` and returns indices directly)."""

    point: DecisionPoint
    player: str
    observation: Observation
    legal_actions: tuple[GameAction, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "point": self.point.value,
            "player": self.player,
            "observation": self.observation.to_dict(),
            "legal_actions": [a.to_dict() for a in self.legal_actions],
        }


def describe_option(loop, side: str, option) -> str:
    """A short label for one option of a GameLoop.choose choice, as `side` sees
    it: a unit (yours or theirs, Might, where), a card (type, cost), a
    battlefield, a domain, a mode, yes / no."""
    from .battlefield import Battlefield
    from .combat import UnitInPlay
    if isinstance(option, tuple) and option and isinstance(option[-1], UnitInPlay):
        option = option[-1]                    # (side, unit) in effect moves
    if isinstance(option, UnitInPlay):
        where = loop._locate_unit(option)
        whose = "yours" if where and where[0] == side else "theirs"
        at = "base" if where is None or where[1] is None else \
            f"battlefield {loop.gs.battlefields.index(where[1])}"
        token = ", token" if option.is_token else ""
        return f"{option.card.name} ({whose}, Might {option.might}, {at}{token})"
    if isinstance(option, Battlefield):
        i = loop.gs.battlefields.index(option)
        return f"battlefield {i}" + (f" ({option.card.name})" if option.card is not None else "")
    if isinstance(option, bool):
        return "yes" if option else "no"
    if hasattr(option, "cost_energy"):
        cat = getattr(getattr(option, "category", None), "name", "card")
        return f"{option.name} ({cat.lower()}, {option.cost_energy or 0} energy)"
    if isinstance(option, tuple):
        return str(getattr(option[0], "name", option[0]))
    if isinstance(option, int):
        return f"mode {option + 1}"
    return str(getattr(option, "name", option))
