"""Helpers for the rules-audit tests (docs/audit/AUDIT.md): a board set up by
hand, cards from the registry, and players scripted by the labels of the legal
actions they take."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, FacedownCard
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def setup(active: str = "A", rich=("A", "B")):
    """Two players, two empty battlefields, `active`'s Main Phase; the `rich`
    sides can pay for anything."""
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = active
    for p in (a, b):
        if p.name in rich:
            p.energy = 20
            for d in Domain:
                p.add_power(d, 5)
    return GameLoop(gs), a, b


def card(name: str):
    return CARD_REGISTRY[name].instantiate()


def unit(name: str, might=None, **kw) -> UnitInPlay:
    """A ready unit: the registry's card, or a vanilla unit of that Might."""
    c = card(name) if name in CARD_REGISTRY else UnitCard(name=name, might=might)
    kw.setdefault("ready", True)
    return UnitInPlay(card=c, **kw)


def legend(loop: GameLoop, side: str, name: str) -> UnitInPlay:
    c = card(name)
    setattr(loop.gs, f"legend_{side}", c)
    u = UnitInPlay(card=c, ready=True)
    setattr(loop.gs, f"legend_unit_{side}", u)
    return u


def hide(loop: GameLoop, side: str, lane: int, name: str, turns_ago: int = 2):
    """`name` facedown at battlefield `lane`, hidden `turns_ago` turns ago."""
    c = card(name)
    loop.gs.battlefields[lane].facedowns.append(
        FacedownCard(card=c, owner=side, turn_hidden=loop.gs.turn - turns_ago))
    return c


def labels(loop: GameLoop, side: str, point: DecisionPoint = DecisionPoint.TURN_ACTION) -> list:
    return [ga.label for ga in legal_actions(loop, point, side)]


def act(loop: GameLoop, side: str, label: str, point: DecisionPoint = DecisionPoint.TURN_ACTION) -> None:
    """`side` takes the legal action whose label starts with `label`."""
    for ga in legal_actions(loop, point, side):
        if ga.label.startswith(label):
            loop._apply_action(loop.gs.get_player(side), ga.to_engine())
            loop._recompute_passives()
            return
    raise AssertionError(f"{label!r} is not legal: {labels(loop, side, point)}")


def choices(loop: GameLoop, picks: dict) -> list:
    """Answer the engine's choices by kind prefix: picks = {prefix: f(loop,
    options) -> index}. Returns the log of (kind, side, option names) asked."""
    seen: list = []

    def name(o):
        return getattr(getattr(o, "card", None), "name", None) or getattr(o, "name", o)

    def chooser(_loop, kind, side, options, default, source):
        seen.append((kind, side, [name(o) for o in options]))
        for prefix, f in picks.items():
            if kind.startswith(prefix):
                return f(_loop, options)
        return None
    loop.chooser = chooser
    return seen


class Scripted:
    """A player taking, at each kind of decision, the next label of its script
    (a prefix of a legal action's label, or "PASS"); PASS once it runs out. It
    keeps what it was offered: `log` = [(decision point, labels)]."""

    def __init__(self, player, loop, main=(), showdown=(), reaction=()):
        self.player, self.loop, self.gs = player, loop, loop.gs
        self.scripts = {DecisionPoint.TURN_ACTION: list(main),
                        DecisionPoint.SHOWDOWN_ACTION: list(showdown),
                        DecisionPoint.REACTION: list(reaction)}
        self.log: list = []

    def _pick(self, point: DecisionPoint):
        legal = legal_actions(self.loop, point, self.player.name)
        self.log.append((point.value, [g.label for g in legal]))
        script = self.scripts[point]
        want = script.pop(0) if script else "PASS"
        if want == "PASS":
            return ("PASS", None, None)
        for g in legal:
            if g.label.startswith(want):
                return g.to_engine()
        raise AssertionError(f"{self.player.name}: {want!r} is not legal at {point.value}: "
                             f"{[g.label for g in legal]}")

    def offered(self, point: str) -> list:
        return [lbl for p, lbls in self.log if p == point for lbl in lbls]

    def decide_action(self, opponent, cards_played: int = 0):
        return self._pick(DecisionPoint.TURN_ACTION)

    def decide_showdown_action(self, opponent, bf_idx: int):
        return self._pick(DecisionPoint.SHOWDOWN_ACTION)

    def decide_reaction(self, opponent, chain):
        return self._pick(DecisionPoint.REACTION)

    def decide_mulligan(self):
        return []


def scripted(loop: GameLoop, a: Player, b: Player, A: dict | None = None, B: dict | None = None):
    a.agent = Scripted(a, loop, **(A or {}))
    b.agent = Scripted(b, loop, **(B or {}))
    return a.agent, b.agent
