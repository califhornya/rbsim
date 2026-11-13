from __future__ import annotations

import json

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

def test_banned_cards_listed_and_warned(tmp_path):
    import warnings
    from pathlib import Path

    from riftbound.registry.cards_registry import BANNED_CARDS, load_deck_json

    assert {"Ekko Recurrent", "Stacked Deck"} <= BANNED_CARDS
    # Bans announced 2026-11-13, effective 2026-11-23 (eight cards, two battlefields).
    assert {"Riven Broken Blade", "Zhonya's Hourglass", "Stellacorn Herder", "Nocturne Horrifying",
            "Rhasa the Sunderer", "Brynhir Thundersong", "Dazzling Aurora", "Baited Hook",
            "Emperor's Dais", "Star Spring"} <= BANNED_CARDS
    assert all(name in CARD_REGISTRY for name in BANNED_CARDS)
    zed = Path(__file__).resolve().parent.parent / "riftbound/data/decks/precon_zed.json"
    data = json.loads(zed.read_text(encoding="utf-8"))
    data["cards"] = list(data["cards"]) + [{"name": "Stacked Deck", "count": 1}]
    deck = tmp_path / "with_banned.json"
    deck.write_text(json.dumps(data), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_deck_json(deck)
    assert any("Stacked Deck" in str(w.message) for w in caught)


def test_banned_battlefield_and_champion_warned(tmp_path):
    import warnings
    from pathlib import Path

    from riftbound.registry.cards_registry import load_deck_json

    zed = Path(__file__).resolve().parent.parent / "riftbound/data/decks/precon_zed.json"
    data = json.loads(zed.read_text(encoding="utf-8"))
    data["battlefields"] = [{"name": "Star Spring"}] + list(data["battlefields"])[1:]
    data["champion"] = "Riven Broken Blade"
    deck = tmp_path / "with_banned_bf.json"
    deck.write_text(json.dumps(data), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_deck_json(deck)
    messages = [str(w.message) for w in caught]
    assert any("battlefield 'Star Spring'" in m for m in messages)
    assert any("champion 'Riven Broken Blade'" in m for m in messages)
