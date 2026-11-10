"""Star Spring battlefield: 'The first time a player plays a non-token unit here
each turn, they may move another unit they control here to its base.' Fires on
plays (a unit card played to the battlefield), not moves, once per player per
turn; optional via decide_optional."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import BattlefieldCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop_with_star_spring(lane=0):
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, active="A")
    gs.battlefields[lane] = Battlefield(card=BattlefieldCard(name="Star Spring"))
    return GameLoop(gs)


def _play_here(loop, name, might, bf):
    return loop._play_unit(UnitCard(name=name, might=might), "A", bf=bf)


def test_star_spring_moves_the_lowest_might_ally_to_base_on_the_first_play():
    loop = _loop_with_star_spring(0)
    bf = loop.gs.battlefields[0]
    weak = UnitInPlay(UnitCard(name="Weak", might=1), ready=True)
    bf.add_unit("A", weak)
    newcomer = _play_here(loop, "Newcomer", 4, bf)
    assert bf.first_unit_here_A is True
    assert weak in loop.gs.A.base_units and newcomer in bf.units_A


def test_star_spring_fires_once_per_turn():
    loop = _loop_with_star_spring(0)
    bf = loop.gs.battlefields[0]
    ally = UnitInPlay(UnitCard(name="Ally", might=2), ready=True)
    bf.add_unit("A", ally)
    _play_here(loop, "N1", 3, bf)
    assert ally in loop.gs.A.base_units           # first fired
    ally2 = UnitInPlay(UnitCard(name="Ally2", might=1), ready=True)
    bf.add_unit("A", ally2)
    _play_here(loop, "N2", 3, bf)
    assert ally2 in bf.units_A                     # not again this turn
    bf.begin_turn_reset()
    assert bf.first_unit_here_A is False


def test_star_spring_ignores_moves_and_tokens():
    loop = _loop_with_star_spring(0)
    bf = loop.gs.battlefields[0]
    resident = UnitInPlay(UnitCard(name="Resident", might=1), ready=True)
    bf.add_unit("A", resident)
    mover = UnitInPlay(UnitCard(name="Mover", might=5), ready=True)
    loop.gs.A.base_units.append(mover)
    loop._apply_action(loop.gs.A, ("MOVE", None, len(loop.gs.battlefields), 0))
    loop._flush_pending_move()
    assert resident in bf.units_A                  # a move isn't a play
    loop._play_token("Recruit", "A", bf=bf)
    assert resident in bf.units_A and bf.first_unit_here_A is False
