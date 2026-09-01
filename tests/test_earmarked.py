"""Earmarked resources (§ restricted-use): the Ornn / Diana Scorn legends tap to
ADD a resource that can only be spent in a specific context.
  - Diana Scorn: ADD [1] energy, spendable only during showdowns.
  - Ornn:        ADD [rune] power, spendable only to play/use gear.
Slice 1a covers generation (tapping the legend) + turn cleanup. Spending is 1b.
"""

from __future__ import annotations

import random

from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def test_effect_adds_earmarked_pools():
    loop = _loop()
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    ctx.add_earmarked_energy(1)
    ctx.add_earmarked_power(2)
    assert loop.gs.A.earmarked_energy_showdown == 1
    assert loop.gs.A.earmarked_power_gear == 2


def test_earmarked_pools_clear_each_turn():
    loop = _loop()
    loop.gs.A.earmarked_energy_showdown = 3
    loop.gs.A.earmarked_power_gear = 3
    loop._phase_beginning("A")
    assert loop.gs.A.earmarked_energy_showdown == 0
    assert loop.gs.A.earmarked_power_gear == 0


def test_diana_scorn_legend_tap_generates_showdown_energy():
    loop = _loop(); loop.gs.active = "A"
    loop.gs.legend_unit_A = UnitInPlay(
        card=CARD_REGISTRY["Diana Scorn of the Moon"].instantiate(), ready=True)
    abilities = loop.activatable_abilities("A")
    idx = next(i for i, e in enumerate(abilities)
               if e["type"] == "ability" and e["unit"] is loop.gs.legend_unit_A)
    loop._apply_activated_ability(loop.gs.A, loop.gs.B, idx)
    assert loop.gs.A.earmarked_energy_showdown == 1
    assert loop.gs.legend_unit_A.ready is False        # tapped


def test_ornn_legend_tap_generates_gear_power():
    loop = _loop(); loop.gs.active = "A"
    loop.gs.legend_unit_A = UnitInPlay(
        card=CARD_REGISTRY["Ornn Fire Below the Mountain"].instantiate(), ready=True)
    abilities = loop.activatable_abilities("A")
    idx = next(i for i, e in enumerate(abilities)
               if e["type"] == "ability" and e["unit"] is loop.gs.legend_unit_A)
    loop._apply_activated_ability(loop.gs.A, loop.gs.B, idx)
    assert loop.gs.A.earmarked_power_gear == 1
    assert loop.gs.legend_unit_A.ready is False


# --- 1b: spending. The earmark is usable ONLY in its context. ---

def test_showdown_energy_only_spends_in_showdown():
    loop = _loop(); a = loop.gs.A
    a.energy = 0
    a.earmarked_energy_showdown = 1
    # showdown spend can use it
    assert loop._can_pay_showdown(a, 1, None, None) is True
    # a normal (main-phase) spend cannot see the earmark
    assert a.can_pay_cost(1, None, None) is False
    # paying in showdown consumes the earmark
    assert loop._pay_showdown(a, 1, None, None) is True
    assert a.earmarked_energy_showdown == 0


def test_gear_power_only_spends_on_gear():
    from riftbound.core.enums import Domain
    loop = _loop(); a = loop.gs.A
    a.energy = 0
    a.earmarked_power_gear = 1               # generic gear-power
    # a gear cost of 1 power (any domain) is affordable via the earmark
    assert loop._can_pay_gear(a, 0, 1, Domain.FURY) is True
    # the same power for a NON-gear spend (a unit/spell) is not covered
    assert a.can_pay_cost(0, 1, Domain.FURY) is False
    # paying a gear cost consumes the earmark
    assert loop._pay_gear(a, 0, 1, Domain.FURY) is True
    assert a.earmarked_power_gear == 0


def test_gear_play_consumes_earmarked_power():
    from riftbound.core.cards import GearCard
    loop = _loop(); a = loop.gs.A; loop.gs.active = "A"
    a.hand.append(GearCard(name="TST Power Gear", cost_energy=0, cost_power=1,
                           cost_power_domain=None))
    a.earmarked_power_gear = 1               # covers the [rune] power
    loop._apply_action(a, ("GEAR", 0, 0, None))
    assert any(g.name == "TST Power Gear" for g in a.base_gear)   # played to base
    assert a.earmarked_power_gear == 0                            # earmark spent
