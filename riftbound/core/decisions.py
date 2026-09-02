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
      * UNIT/SPELL/GEAR : index=hand_idx, lane=target battlefield
      * CHAMPION        : lane=target battlefield (index unused)
      * MOVE            : lane=src, dst_lane=dst (index is None)
      * ABILITY         : index=ability_id ("PYKE_LEGEND"/"GOLD_SACRIFICE"/
                          "ACTIVATED"), lane=arg (domain / ability index)
    """

    kind: str
    index: Optional[Any] = None
    lane: Optional[Any] = None
    dst_lane: Optional[int] = None
    label: str = ""

    def to_engine(self) -> tuple:
        """The raw action tuple ``GameLoop._apply_action`` expects."""
        if self.kind == "MOVE":
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
    def move(cls, src: int, dst: int, label: str) -> "GameAction":
        return cls("MOVE", None, src, dst, label)

    @classmethod
    def ability(cls, ability_id: str, arg: Any, label: str) -> "GameAction":
        return cls("ABILITY", ability_id, arg, None, label)


# --- observation (information set for one player) -----------------------------

@dataclass(frozen=True)
class UnitView:
    name: str
    might: int
    ready: bool
    stunned: bool
    is_token: bool
    gear: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "name": self.name, "might": self.might, "ready": self.ready,
            "stunned": self.stunned, "is_token": self.is_token, "gear": list(self.gear),
        }


@dataclass(frozen=True)
class BattlefieldView:
    A: tuple[UnitView, ...]
    B: tuple[UnitView, ...]
    controller: Optional[str]
    named: Optional[str]

    def to_dict(self) -> dict:
        return {
            "A": [u.to_dict() for u in self.A],
            "B": [u.to_dict() for u in self.B],
            "controller": self.controller,
            "named": self.named,
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

    @staticmethod
    def _uview(u) -> "UnitView":
        return UnitView(
            name=u.card.name,
            might=u.might,
            ready=u.ready,
            stunned=u.stunned,
            is_token=u.is_token,
            gear=tuple(getattr(g, "name", "?") for g in u.gear),
        )

    @classmethod
    def from_state(cls, gs: "GameState", viewer: str) -> "Observation":
        me = gs.get_player(viewer)
        opp = gs.get_player(gs.other(viewer))

        def bview(bf) -> BattlefieldView:
            return BattlefieldView(
                A=tuple(cls._uview(u) for u in bf.units_A),
                B=tuple(cls._uview(u) for u in bf.units_B),
                controller=bf.controller(),
                named=getattr(bf.card, "name", None) if bf.card else None,
            )

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
