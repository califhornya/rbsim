"""TEMPORARY keyword (Core Rules §742): at the start of the permanent's
controller's Beginning Phase, kill it. Units are removed; UNATTACHED gear at base
is killed too (e.g. Spinning Axe "if unattached, kill it"); ATTACHED gear rides its
host and is left alone.
"""

from __future__ import annotations

import random

from riftbound.core.cards import GearCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def test_unattached_temporary_gear_killed_at_beginning_phase():
    loop = _loop()
    temp = GearCard(name="Ephemeral Blade", keywords=["TEMPORARY"])
    keep = GearCard(name="Sturdy Blade")
    loop.gs.A.base_gear.extend([temp, keep])

    loop._phase_beginning("A")

    assert temp not in loop.gs.A.base_gear      # killed
    assert temp in loop.gs.A.trash
    assert keep in loop.gs.A.base_gear          # non-TEMPORARY survives


def test_temporary_gear_only_killed_on_its_controllers_turn():
    loop = _loop()
    temp = GearCard(name="Ephemeral Blade", keywords=["TEMPORARY"])
    loop.gs.B.base_gear.append(temp)

    loop._phase_beginning("A")                  # A's beginning phase

    assert temp in loop.gs.B.base_gear          # B's gear untouched on A's turn


def test_attached_temporary_gear_survives():
    loop = _loop()
    unit = UnitInPlay(UnitCard(name="Bearer", might=3))
    temp = GearCard(name="Ephemeral Blade", keywords=["TEMPORARY"])
    unit.gear.append(temp)                      # attached to a host
    loop.gs.battlefields[0].units_A.append(unit)

    loop._phase_beginning("A")

    assert temp in unit.gear                    # attached gear is left alone
    assert temp not in loop.gs.A.trash
