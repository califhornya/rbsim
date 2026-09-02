"""Deathknell (Core Rules §734): "when I die, [Effect]" fires when the permanent
is killed and sent to the trash — but NOT if the kill was replaced (e.g. by a
recall / Guardian Angel), per §734.1.d.1. Exercises the combat death-routing path
`_route_combat_deaths`.
"""

from __future__ import annotations

import random

import pytest

from riftbound.core.cards import UnitCard
from riftbound.core.combat import CombatStats, UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec

DK = "DK Drawer"


def _loop_with_deck(n_cards: int) -> GameLoop:
    deck = Deck(cards=[UnitCard(name=f"Filler{i}", might=1) for i in range(n_cards)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


@pytest.fixture
def dk_card():
    CARD_REGISTRY[DK] = CardSpec.from_dict({
        "name": DK, "category": "UNIT", "might": 3,
        "effects": [{"effect": "draw_cards", "trigger": "on_death",
                     "target": "actor", "count": 1}],
    })
    yield
    CARD_REGISTRY.pop(DK, None)


def test_deathknell_fires_on_true_death(dk_card):
    loop = _loop_with_deck(3)
    unit = UnitInPlay(CARD_REGISTRY[DK].instantiate())
    bf = loop.gs.battlefields[0]
    before = len(loop.gs.A.hand)

    loop._route_combat_deaths(CombatStats(dead_A=[unit]), bf)

    assert unit.card in loop.gs.A.trash            # truly dead
    assert len(loop.gs.A.hand) == before + 1        # Deathknell drew 1


def test_deathknell_suppressed_when_death_replaced(dk_card):
    loop = _loop_with_deck(3)
    unit = UnitInPlay(CARD_REGISTRY[DK].instantiate())
    unit.gear.append(CARD_REGISTRY["Guardian Angel"].instantiate())  # death replacer
    bf = loop.gs.battlefields[0]
    before = len(loop.gs.A.hand)

    loop._route_combat_deaths(CombatStats(dead_A=[unit]), bf)

    assert unit in loop.gs.A.base_units             # recalled, not dead
    assert unit.card not in loop.gs.A.trash
    assert len(loop.gs.A.hand) == before            # Deathknell did NOT fire
