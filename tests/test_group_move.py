"""Standard Moves name their unit, and units moved to the same battlefield in a
row move together (Core Rules §144.3): the showdown waits until the player does
anything else, so they fight together."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _unit(name, might, **kw):
    return UnitInPlay(card=UnitCard(name=name, might=might, **kw), ready=True)


def test_move_names_its_unit():
    loop = _loop()
    a = loop.gs.A
    small, big = _unit("Small", 1), _unit("Big", 5)
    a.base_units.extend([small, big])
    loop._apply_action(a, ("MOVE", 1, 2, 0))
    assert loop.gs.battlefields[0].units_A == [big]
    assert a.base_units == [small]


def test_units_moved_together_fight_together():
    loop = _loop()
    a = loop.gs.A
    loop.gs.battlefields[0].add_unit("B", _unit("Wall", 4))
    a.base_units.extend([_unit("Two", 2), _unit("Three", 3)])
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    assert loop.gs.pending_move == (0, "A")            # held: no fight yet
    assert loop.gs.battlefields[0].units_B
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()                         # the player is done moving
    bf = loop.gs.battlefields[0]
    assert bf.units_B == []                            # 2 + 3 beat the 4-Might Wall
    # The Wall's 4 damage kills the mightiest unit it can (combat.kill_order).
    assert [u.card.name for u in bf.units_A] == ["Two"]


def test_any_other_action_starts_the_held_showdown():
    loop = _loop()
    a = loop.gs.A
    loop.gs.battlefields[0].add_unit("B", _unit("Wall", 1))
    a.base_units.extend([_unit("Hero", 3), _unit("Other", 1)])
    a.hand.append(SpellCard(name="Free", cost_energy=0))
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._apply_action(a, ("SPELL", 0, 1, None))
    assert loop.gs.pending_move is None
    assert loop.gs.battlefields[0].units_B == []


def test_legality_offers_one_move_per_ready_unit():
    loop = _loop()
    a = loop.gs.A
    a.base_units.extend([_unit("One", 1), _unit("Tired", 1)])
    a.base_units[1].ready = False
    loop.gs.battlefields[0].add_unit("A", _unit("Walker", 1))
    loop.gs.battlefields[0].add_unit("A", _unit("Ganker", 1, keywords=["GANKING"]))
    moves = {(ga.index, ga.lane, ga.dst_lane) for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")
             if ga.kind == "MOVE"}
    assert moves == {(0, 2, 0), (0, 2, 1),            # One: base -> either BF
                     (0, 0, 2),                        # Walker: BF0 -> base only
                     (1, 0, 2), (1, 0, 1)}             # Ganker: also BF0 -> BF1
