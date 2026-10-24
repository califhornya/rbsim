from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.registry.cards_registry import CARD_REGISTRY
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player
from riftbound.core.state import GameState


def make_game() -> GameLoop:
    rng = random.Random(1)
    player_a = Player(name="A", deck=Deck([]))
    player_b = Player(name="B", deck=Deck([]))
    gs = GameState(rng=rng, A=player_a, B=player_b)
    gs.battlefields = [Battlefield(), Battlefield()]
    return GameLoop(gs)


def test_registry_loads_master_data():
    assert len(CARD_REGISTRY) > 100
    assert "Vi Destructive" in CARD_REGISTRY
    assert "Darius Trifarian" in CARD_REGISTRY
    assert "Chemtech Enforcer" in CARD_REGISTRY

def test_banned_cards_listed_and_warned():
    import warnings
    from pathlib import Path

    from riftbound.registry.cards_registry import BANNED_CARDS, load_deck_json

    assert {"Ekko Recurrent", "Stacked Deck"} <= BANNED_CARDS
    assert all(name in CARD_REGISTRY for name in BANNED_CARDS)
    deck = Path(__file__).resolve().parent.parent / "riftbound/data/decks/fury_chaos_pyke.json"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_deck_json(deck)
    assert any("Stacked Deck" in str(w.message) for w in caught)
