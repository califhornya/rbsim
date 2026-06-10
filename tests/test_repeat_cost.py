"""REPEAT additional cost — bare keyword defaults to the spell's printed cost;
an explicit `REPEAT N` keeps overriding for rare exceptions."""

import random

import pytest

from riftbound.core.cards import SpellCard
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _make_loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def _reg(name: str, effects: list) -> None:
    CARD_REGISTRY[name] = CardSpec.from_dict(
        {"name": name, "category": "SPELL", "effects": effects}
    )


@pytest.fixture
def cleanup_registry():
    added: list[str] = []
    yield added
    for n in added:
        CARD_REGISTRY.pop(n, None)


def test_bare_repeat_defaults_to_spell_cost(cleanup_registry):
    name = "TST Repeat Bare"
    _reg(name, [{"effect": "gain_energy", "trigger": "on_cast",
                 "amount": 2, "target": "actor"}])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    spell = SpellCard(name=name, cost_energy=3, keywords=["REPEAT"])
    ap.hand.append(spell); ap.energy = 6
    loop._apply_action(ap, ("SPELL", 0, 0, None))
    # base 3 + REPEAT default 3 = 6 spent; effect runs twice -> +2 +2 = +4
    assert spell._repeat_paid is True
    assert ap.energy == 4


def test_explicit_repeat_value_overrides_default(cleanup_registry):
    name = "TST Repeat Two"
    _reg(name, [{"effect": "gain_energy", "trigger": "on_cast",
                 "amount": 2, "target": "actor"}])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    spell = SpellCard(name=name, cost_energy=4, keywords=["REPEAT 1"])
    ap.hand.append(spell); ap.energy = 6
    loop._apply_action(ap, ("SPELL", 0, 0, None))
    # base 4 + explicit REPEAT 1 = 5 spent (1 left); effect runs twice -> +4
    assert spell._repeat_paid is True
    assert ap.energy == 5  # 6 - 4 - 1 + 4


def test_bare_repeat_unaffordable_skipped(cleanup_registry):
    name = "TST Repeat Poor"
    _reg(name, [{"effect": "gain_energy", "trigger": "on_cast",
                 "amount": 2, "target": "actor"}])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    spell = SpellCard(name=name, cost_energy=3, keywords=["REPEAT"])
    ap.hand.append(spell); ap.energy = 4
    loop._apply_action(ap, ("SPELL", 0, 0, None))
    # base 3 spent -> 1 left; bare-REPEAT default cost 3 unaffordable; effect runs once -> +2
    assert spell._repeat_paid is False
    assert ap.energy == 3  # 4 - 3 + 2
