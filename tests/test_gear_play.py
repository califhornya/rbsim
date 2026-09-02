"""Gear is played to BASE (§146.1.a.1), unattached — it does NOT auto-attach to a
unit for free on play. Equipment attaches later via its Equip ability (a separate
action paying the Equip cost). EXCEPTION: QUICK-DRAW (§745.1.d) attaches on play.
"""

from __future__ import annotations

import random

from riftbound.core.cards import GearCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop_with_friendly_unit_at_bf0():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b))
    loop.gs.active = "A"
    unit = UnitInPlay(UnitCard(name="Ally", might=2), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)
    return loop, unit


def test_normal_gear_plays_to_base_not_attached():
    loop, unit = _loop_with_friendly_unit_at_bf0()
    ap = loop.gs.A
    ap.hand.append(GearCard(name="Plain Blade", cost_energy=0))
    ap.energy = 1
    loop._apply_action(ap, ("GEAR", 0, 0, None))
    assert len(unit.gear) == 0                 # NOT auto-attached (would be a free equip)
    assert any(g.name == "Plain Blade" for g in ap.base_gear)   # lands at base


def test_quick_draw_gear_attaches_on_play():
    loop, unit = _loop_with_friendly_unit_at_bf0()
    ap = loop.gs.A
    ap.hand.append(GearCard(name="Fast Blade", cost_energy=0, keywords=["QUICK-DRAW"]))
    ap.energy = 1
    loop._apply_action(ap, ("GEAR", 0, 0, None))
    assert any(g.name == "Fast Blade" for g in unit.gear)       # attached on play
    assert not any(g.name == "Fast Blade" for g in ap.base_gear)


def test_quick_draw_gear_goes_to_base_when_no_unit():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b)); loop.gs.active = "A"
    a.hand.append(GearCard(name="Fast Blade", cost_energy=0, keywords=["QUICK-DRAW"]))
    a.energy = 1
    loop._apply_action(a, ("GEAR", 0, 0, None))
    assert any(g.name == "Fast Blade" for g in a.base_gear)     # nothing to attach to
