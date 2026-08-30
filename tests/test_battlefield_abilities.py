"""Deck battlefields are placed in play and their own triggered abilities fire.

A single game uses one battlefield per player (chosen from the deck's up to 3).
The in-play Battlefield carries its identity card, so its on_conquer / on_hold /
on_start_of_turn abilities resolve for the scoring/active player.
"""

from __future__ import annotations

import random
from pathlib import Path

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import BattlefieldCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"


def test_build_game_places_deck_battlefields():
    gs = build_game(game_seed=3, deck_a_path=KENNEN, deck_b_path=KENNEN,
                    ai_a="simple_trade", ai_b="simple_trade")
    # Both in-play battlefields carry an identity card from the decks.
    assert all(bf.card is not None for bf in gs.battlefields)
    assert all(bf.card.category.name == "BATTLEFIELD" for bf in gs.battlefields)


def test_battlefield_on_conquer_fires():
    spec = CardSpec.from_dict({
        "name": "Test BF Draw", "category": "Battlefield",
        "effects": [{"effect": "draw_cards", "trigger": "on_conquer", "target": "actor", "count": 1}],
    })
    CARD_REGISTRY[spec.name] = spec

    deck = Deck(cards=[UnitCard(name=f"C{i}", might=1) for i in range(5)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b,
                   battlefields=[Battlefield(card=BattlefieldCard(name="Test BF Draw")), Battlefield()])
    loop = GameLoop(gs)

    hand_before = len(a.hand)
    loop._fire_scoring_trigger("on_conquer", gs.battlefields[0], "A")
    assert len(a.hand) == hand_before + 1  # the battlefield drew for the conqueror


def test_battlefield_without_card_is_noop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b)  # default: cardless battlefields
    loop = GameLoop(gs)
    loop._fire_scoring_trigger("on_conquer", gs.battlefields[0], "A")  # must not raise
