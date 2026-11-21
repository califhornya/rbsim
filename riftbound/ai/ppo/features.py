"""What the PPO policy sees of a question and of each of its options (21/11,
docs/PIANO_FORZA.md; disegno della revisione esterna).

Every real choice is a menu: the main phase, a reaction, a showdown action,
the mulligan (one menu of subsets), and every choice the engine routes
through GameLoop.choose (a target, "you may", an order, a destination...).
The policy scores each option from its descriptor and the state; the menu's
position of an option and the baseline's suggestion are not features.

A descriptor: (type, three card ids, numeric features). Cards are ids of the
card vocabulary (encoding.card_id: 0 = none), embedded like the state's rows.
Locations are from the decider's view; whose a thing is: "mine" / "theirs".
"""
from __future__ import annotations

import itertools
from typing import Optional

import numpy as np

from riftbound.ai.encoding import N_TOKEN_FEATURES, _unit_features, card_id
from riftbound.core.decisions import Observation

QUESTIONS = ("main", "reaction", "showdown", "mulligan",
             "optional", "target", "trigger_order", "combat_damage_order", "keep", "discard",
             "destination", "card", "mode", "cost_extras", "battlefield", "domain", "player", "tag",
             "equip", "predict_recycle", "show_off", "token_location", "other")
_Q = {q: i for i, q in enumerate(QUESTIONS)}

OPTION_TYPES = ("PASS", "UNIT", "SPELL", "GEAR", "CHAMPION", "MOVE", "HIDE", "HIDDEN_PLAY", "ABILITY",
                "ACTION_OTHER", "mulligan", "unit", "card", "battlefield", "yes", "no", "me", "opponent",
                "domain", "number", "no_more", "chain_item", "trigger", "gear", "nothing", "other")
_T = {t: i for i, t in enumerate(OPTION_TYPES)}

LOCS = ("base", "bf0", "bf1", "bf2", "hand", "trash", "chain", "champion", "facedown", "deck", "none")
_L = {loc: i for i, loc in enumerate(LOCS)}
DOMAINS = ("FURY", "CALM", "MIND", "BODY", "CHAOS", "ORDER")

# Numeric features of an option: the subject's and the object's unit rows
# (zeros if not units), whose they are (mine, theirs) x 2, the source and the
# destination location, the domain, then: a number (mode, count) / 4, a slot
# / 4, how many cards a mulligan sends back / 2.
F_OPT = 2 * N_TOKEN_FEATURES + 4 + 2 * len(LOCS) + len(DOMAINS) + 3
# The question's context: options / 16, choices already made in it / 4, "up
# to" (NO_MORE offered), asked while a spell is declared.
F_CTX = 4


def question_of(kind: str) -> int:
    return _Q.get(kind.split(":")[0], _Q["other"])


def _bf_loc(i: Optional[int], n_bf: int) -> str:
    if i is None or i == n_bf:
        return "base"
    return f"bf{i}" if 0 <= i < 3 else "none"


class Descriptor:
    __slots__ = ("type", "cards", "feats")

    def __init__(self, type_: str):
        self.type = _T.get(type_, _T["other"])
        self.cards = [0, 0, 0]
        self.feats = np.zeros(F_OPT, dtype=np.float32)

    def unit(self, slot: int, u) -> None:
        """Subject (slot 0) or object (slot 1) is the unit in play `u`."""
        self.cards[slot] = card_id(u.card.name)
        off = slot * N_TOKEN_FEATURES
        self.feats[off:off + N_TOKEN_FEATURES] = _unit_features(Observation._uview(u))

    def owner(self, slot: int, mine: Optional[bool]) -> None:
        if mine is not None:
            self.feats[2 * N_TOKEN_FEATURES + 2 * slot + (0 if mine else 1)] = 1.0

    def loc(self, which: int, loc: str) -> None:
        self.feats[2 * N_TOKEN_FEATURES + 4 + which * len(LOCS) + _L.get(loc, _L["none"])] = 1.0

    def domain(self, name: str) -> None:
        if name in DOMAINS:
            self.feats[2 * N_TOKEN_FEATURES + 4 + 2 * len(LOCS) + DOMAINS.index(name)] = 1.0

    def scalars(self, number: float = 0.0, slot: float = 0.0, count: float = 0.0) -> None:
        base = 2 * N_TOKEN_FEATURES + 4 + 2 * len(LOCS) + len(DOMAINS)
        self.feats[base:base + 3] = (number / 4.0, slot / 4.0, count / 2.0)

    @property
    def unknown(self) -> bool:
        return self.type == _T["other"]


# ------------------------------------------------------------- main actions

def describe_action(loop, side: str, a) -> Descriptor:
    """A GameAction of the main phase, a reaction or a showdown."""
    gs = loop.gs
    n_bf = len(gs.battlefields)
    me = gs.get_player(side)
    d = Descriptor(a.kind if a.kind in _T else "ACTION_OTHER")
    if a.kind in ("UNIT", "SPELL", "GEAR", "HIDE") and isinstance(a.index, int) and a.index < len(me.hand):
        d.cards[0] = card_id(me.hand[a.index].name)
        d.loc(0, "hand")
        dst = a.dst_lane if a.kind == "UNIT" else a.lane
        d.loc(1, _bf_loc(dst, n_bf) if a.kind != "GEAR" else "base")
    elif a.kind == "CHAMPION":
        champ = gs.champion_A if side == "A" else gs.champion_B
        if champ is not None:
            d.cards[0] = card_id(champ.name)
        d.loc(0, "champion")
        d.loc(1, _bf_loc(a.dst_lane, n_bf))
    elif a.kind == "MOVE":
        src, dst = a.lane, a.dst_lane
        units = me.base_units if src == n_bf else gs.battlefields[src]._units_for(side)
        u = None
        if a.index is not None and a.index < len(units):
            u = units[a.index]
        else:
            u = next((x for x in units if x.ready), None)
        if u is not None:
            d.unit(0, u)
        d.owner(0, True)
        d.loc(0, _bf_loc(src, n_bf))
        d.loc(1, _bf_loc(dst, n_bf))
    elif a.kind == "HIDDEN_PLAY":
        slot = a.index or 0
        if a.lane is not None and a.lane < n_bf:
            fds = [fd for fd in gs.battlefields[a.lane].facedowns]
            if slot < len(fds):
                d.cards[0] = card_id(fds[slot].card.name)
            d.loc(0, "facedown")
            d.loc(1, _bf_loc(a.lane, n_bf))
        d.scalars(slot=slot)
    elif a.kind == "ABILITY":
        entries = loop.activatable_abilities(side)
        e = entries[a.lane] if isinstance(a.lane, int) and a.lane < len(entries) else {}
        unit = e.get("unit")
        if unit is not None:
            d.unit(0, unit)
            where = loop._locate_unit(unit)
            d.loc(0, _bf_loc(gs.battlefields.index(where[1]) if where and where[1] is not None else None,
                             n_bf) if where else "none")
        src = e.get("gear") or e.get("card")
        if src is not None and unit is None:
            d.cards[0] = card_id(getattr(src, "name", None))
        d.scalars(number=float(["ability", "equip", "flow", "banished_play", "trash_play"].index(e["type"]))
                  if e.get("type") in ("ability", "equip", "flow", "banished_play", "trash_play") else 4.0)
    return d


# ------------------------------------------------------------- inner choices

def _card_loc(gs, side: str, card) -> tuple[str, Optional[bool]]:
    for who in (side, gs.other(side)):
        p = gs.get_player(who)
        if any(c is card for c in p.hand):
            return "hand", who == side
        if any(c is card for c in p.trash):
            return "trash", who == side
    for item in gs.chain:
        if item.card is card:
            return "chain", item.player == side
    return "none", None


def describe_choice(loop, side: str, option) -> Descriptor:
    """An option of a GameLoop.choose (on `loop`: the game, or the copy a
    spell's choices are declared on)."""
    from riftbound.core.battlefield import Battlefield, FacedownCard
    from riftbound.core.cards import Card
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.enums import Domain
    from riftbound.core.loop import NO_MORE
    from riftbound.core.battlefield import DeployedGear
    from riftbound.core.state import ChainItem, PendingTrigger
    gs = loop.gs
    n_bf = len(gs.battlefields)
    where_first = None
    if isinstance(option, tuple) and option:
        # (location, object) pairs: the object is the last (GameLoop._put_on_chain).
        where_first = next((x for x in option[:-1] if isinstance(x, Battlefield)), None)
        option = option[-1]
    if option is NO_MORE:
        d = Descriptor("no_more")
    elif option is None:
        d = Descriptor("nothing")
    elif isinstance(option, PendingTrigger):
        # trigger_order: which of our triggered abilities goes on the chain first.
        d = Descriptor("trigger")
        d.cards[1] = card_id(option.card.name)
        d.owner(1, option.side == side)
        idx = next((i for i, b in enumerate(gs.battlefields) if b is option.bf), None)
        d.loc(1, _bf_loc(idx, n_bf) if idx is not None else "none")
    elif isinstance(option, DeployedGear):
        d = Descriptor("gear")
        d.cards[1] = card_id(option.card.name)
        for i, b in enumerate(gs.battlefields):
            for who, lst in (("A", b.gear_A), ("B", b.gear_B)):
                if any(g is option for g in lst):
                    d.owner(1, who == side)
                    d.loc(1, _bf_loc(i, n_bf))
    elif isinstance(option, bool):
        d = Descriptor("yes" if option else "no")
    elif isinstance(option, str) and option in ("A", "B"):
        d = Descriptor("me" if option == side else "opponent")
    elif isinstance(option, str) and option.lower() in ("yes", "no"):
        d = Descriptor(option.lower())
    elif isinstance(option, Domain):
        d = Descriptor("domain")
        d.domain(option.name)
    elif isinstance(option, int):
        d = Descriptor("number")
        d.scalars(number=float(option))
    elif isinstance(option, UnitInPlay):
        d = Descriptor("unit")
        d.unit(1, option)
        where = loop._locate_unit(option)
        if where is not None:
            d.owner(1, where[0] == side)
            d.loc(1, _bf_loc(gs.battlefields.index(where[1]) if where[1] is not None else None, n_bf))
        else:
            d.loc(1, "none")
    elif isinstance(option, Battlefield):
        d = Descriptor("battlefield")
        d.cards[1] = card_id(getattr(option.card, "name", None))
        idx = next((i for i, b in enumerate(gs.battlefields) if b is option), None)
        d.loc(1, _bf_loc(idx, n_bf))
        ctrl = option.controller()
        d.owner(1, None if ctrl is None else ctrl == side)
    elif isinstance(option, ChainItem):
        d = Descriptor("chain_item")
        d.cards[1] = card_id(option.card.name)
        d.owner(1, option.player == side)
        d.loc(1, "chain")
        depth = next((len(gs.chain) - 1 - i for i, it in enumerate(gs.chain) if it is option), 0)
        d.scalars(slot=float(depth))
    elif isinstance(option, FacedownCard):
        d = Descriptor("card")
        mine = option.owner == side
        d.cards[1] = card_id(option.card.name) if mine else 0
        d.owner(1, mine)
        d.loc(1, "facedown")
    elif isinstance(option, Card):
        d = Descriptor("card")
        d.cards[1] = card_id(option.name)
        loc, mine = _card_loc(gs, side, option)
        d.loc(1, loc)
        d.owner(1, mine)
    else:
        d = Descriptor("other")
    if where_first is not None:
        idx = next((i for i, b in enumerate(gs.battlefields) if b is where_first), None)
        d.loc(0, _bf_loc(idx, n_bf))
    return d


# ------------------------------------------------------------- the mulligan

def mulligan_menu(hand_size: int) -> list:
    """Every mulligan (§117: up to two cards back), keep-all first: one menu
    of subsets (1 + 4 + 6 = 11 with four cards)."""
    return [list(c) for r in range(3) for c in itertools.combinations(range(hand_size), r)]


def describe_mulligan(hand, subset: list) -> Descriptor:
    d = Descriptor("mulligan")
    for k, i in enumerate(subset[:2]):
        d.cards[1 + k] = card_id(hand[i].name)
    d.loc(1, "hand")
    d.scalars(count=float(len(subset)))
    return d


def context(n_options: int, made: int = 0, up_to: bool = False, declaring: bool = False) -> np.ndarray:
    return np.array([n_options / 16.0, made / 4.0, float(up_to), float(declaring)], dtype=np.float32)
