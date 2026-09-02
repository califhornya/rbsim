"""Star Spring battlefield: 'The first time a player plays a non-token unit here
each turn, they may move another unit they control here to its base.' Fires once
per side per turn from the base→battlefield MOVE path; optional via decide_optional.
"""

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


def test_star_spring_retreats_lowest_might_ally_on_first_unit():
    loop = _loop_with_star_spring(0)
    bf = loop.gs.battlefields[0]
    # An ally already here; a fresh non-token unit is then played here.
    weak = UnitInPlay(UnitCard(name="Weak", might=1), ready=True)
    bf.units_A.append(weak)
    newcomer = UnitInPlay(UnitCard(name="Newcomer", might=4), ready=False)
    total_before = len(bf.units_A) + len(loop.gs.A.base_units)

    loop._fire_first_unit_here("A", bf, newcomer)  # newcomer just entered

    assert bf.first_unit_here_A is True
    assert weak not in bf.units_A                 # lowest-might ally retreated
    assert weak in loop.gs.A.base_units
    # Conservation: nothing created or lost.
    assert len(bf.units_A) + len(loop.gs.A.base_units) == total_before


def test_star_spring_fires_once_per_turn():
    loop = _loop_with_star_spring(0)
    bf = loop.gs.battlefields[0]
    ally = UnitInPlay(UnitCard(name="Ally", might=2), ready=True)
    bf.units_A.append(ally)
    n1 = UnitInPlay(UnitCard(name="N1", might=3), ready=False)
    loop._fire_first_unit_here("A", bf, n1)
    assert ally in loop.gs.A.base_units           # first fired
    # A second unit the same turn does not fire again.
    ally2 = UnitInPlay(UnitCard(name="Ally2", might=2), ready=True)
    bf.units_A.append(ally2)
    n2 = UnitInPlay(UnitCard(name="N2", might=3), ready=False)
    loop._fire_first_unit_here("A", bf, n2)
    assert ally2 in bf.units_A                     # NOT retreated
    # Reset at begin-turn re-arms it.
    bf.begin_turn_reset()
    assert bf.first_unit_here_A is False


def test_star_spring_via_move_action_end_to_end():
    """The trigger fires through the real base→BF MOVE path and conserves cards."""
    loop = _loop_with_star_spring(0)
    bf = loop.gs.battlefields[0]
    resident = UnitInPlay(UnitCard(name="Resident", might=1), ready=True)
    bf.units_A.append(resident)
    mover = UnitInPlay(UnitCard(name="Mover", might=5), ready=True)
    loop.gs.A.base_units.append(mover)
    base_index = len(loop.gs.battlefields)
    loop._apply_action(loop.gs.A, ("MOVE", None, base_index, 0))
    # Mover entered BF0; Resident (lower might) retreated to base.
    assert any(u.card.name == "Mover" for u in bf.units_A)
    assert any(u.card.name == "Resident" for u in loop.gs.A.base_units)
