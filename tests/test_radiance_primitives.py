"""Engine primitives added for the Radiance parse long tail: ADD [rune]
(gain_power_any_domain), "enter ready if ..." conditions, and cost reductions
that scale with an amount_source."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _ctx(loop, card=None):
    card = card or UnitCard(name="Source")
    return EffectContext(loop, card, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])


def test_gain_power_any_domain_picks_needed_domain():
    loop = _loop()
    a = loop.gs.A
    a.add_rune(Domain.FURY)
    a.hand.append(UnitCard(name="Needs Calm", cost_power=1, cost_power_domain=Domain.CALM))
    REGISTRY["gain_power_any_domain"](_ctx(loop), {"amount": 1})
    assert a.power_pool == {Domain.CALM: 1}


def test_gain_power_any_domain_defaults_to_rune_domain():
    loop = _loop()
    a = loop.gs.A
    a.add_rune(Domain.MIND)
    a.add_rune(Domain.MIND)
    a.add_rune(Domain.BODY)
    REGISTRY["gain_power_any_domain"](_ctx(loop), {"amount": 2})
    assert a.power_pool == {Domain.MIND: 2}


def test_enter_ready_conditions():
    loop = _loop()
    a = loop.gs.A
    me = UnitCard(name="Vayne Hunter")
    bf0, bf1 = loop.gs.battlefields
    check = lambda t: loop._check_condition({"type": t}, me, a, loop.gs.B, None)  # noqa: E731

    assert not check("opponent_controls_a_battlefield")
    bf1.add_unit("B", UnitInPlay(UnitCard(name="Holder")))
    assert check("opponent_controls_a_battlefield")

    a.base_units.append(UnitInPlay(me))
    assert check("you_control_no_other_units")      # only itself
    bf0.add_unit("A", UnitInPlay(UnitCard(name="Friend")))
    assert not check("you_control_no_other_units")

    assert not check("card_with_my_name_in_trash")
    a.trash.append(UnitCard(name="Vayne Hunter"))
    assert check("card_with_my_name_in_trash")

    assert not check("opponent_controls_stunned_unit")
    bf1.units_B[0].stunned = True
    assert check("opponent_controls_stunned_unit")


def test_scaling_cost_reduction(monkeypatch):
    spec = CardSpec.from_dict({
        "name": "Test Party Crasher", "category": "Unit", "cost_energy": 5, "might": 3,
        "effects": [{"effect": "reduce_cost", "trigger": "cost_modifier",
                     "amount_source": "friendly_exhausted_units"}]})
    monkeypatch.setitem(CARD_REGISTRY, spec.name, spec)
    loop = _loop()
    a = loop.gs.A
    card = UnitCard(name=spec.name, cost_energy=5)
    assert loop._cost_reduction(card, a) == 0
    a.base_units.append(UnitInPlay(UnitCard(name="Tired 1"), ready=False))
    a.base_units.append(UnitInPlay(UnitCard(name="Tired 2"), ready=False))
    a.base_units.append(UnitInPlay(UnitCard(name="Fresh"), ready=True))
    assert loop._cost_reduction(card, a) == 2


def test_cards_played_cost_reduction(monkeypatch):
    spec = CardSpec.from_dict({
        "name": "Test Battering Ram", "category": "Unit", "cost_energy": 6, "might": 6,
        "effects": [{"effect": "reduce_cost", "trigger": "cost_modifier", "amount": 1,
                     "amount_source": "cards_played_this_turn"}]})
    monkeypatch.setitem(CARD_REGISTRY, spec.name, spec)
    loop = _loop()
    loop.gs.cards_played_this_turn["A"] = 3
    assert loop._cost_reduction(UnitCard(name=spec.name, cost_energy=6), loop.gs.A) == 3


def test_you_control_this_battlefield():
    loop = _loop()
    a = loop.gs.A
    bf = loop.gs.battlefields[1]
    check = lambda: loop._check_condition(  # noqa: E731
        {"type": "you_control_this_battlefield"}, UnitCard(name="Extractor"), a, loop.gs.B,
        {"battlefield": bf})
    assert not check()
    bf.add_unit("A", UnitInPlay(UnitCard(name="Holder")))
    assert check()
