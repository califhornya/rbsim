"""Legends are loaded from the deck and start in play (Legend Zone), so their
activated abilities (incl. EMPOWER) are reachable and they can be empowered."""

from __future__ import annotations

import random
from pathlib import Path

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec, load_deck_json

REPO = Path(__file__).resolve().parent.parent
AKALI = REPO / "riftbound" / "data" / "decks" / "vendetta_akali.json"


def test_load_deck_json_returns_legend():
    cards, runes, champion, legend = load_deck_json(AKALI)
    assert legend is not None
    assert legend.name == "Akali Rogue Assassin"


def test_build_game_places_legend():
    gs = build_game(game_seed=1, deck_a_path=AKALI, deck_b_path=AKALI,
                    ai_a="simple_trade", ai_b="simple_trade")
    assert gs.legend_A is not None and gs.legend_A.name == "Akali Rogue Assassin"
    assert gs.legend_B is not None


def test_legend_activated_ability_is_reachable():
    # Register a legend with an empower_self activated ability.
    spec = CardSpec.from_dict({
        "name": "Test Legend", "category": "Legend",
        "effects": [{"effect": "empower_self", "trigger": "activated", "cost": {"energy": 1}}],
    })
    CARD_REGISTRY[spec.name] = spec
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    from riftbound.core.cards import LegendCard
    gs = GameState(rng=random.Random(1), A=a, B=b, legend_A=LegendCard(name="Test Legend"))
    loop = GameLoop(gs)
    gs.legend_unit_A = UnitInPlay(card=gs.legend_A, ready=True)

    entries = [e for e in loop.activatable_abilities("A")
               if e.get("eff") and e["eff"].effect == "empower_self"]
    assert len(entries) == 1
    # find_unit_by_card locates the legend so empower_self can flip it
    assert loop._find_unit_by_card(gs.legend_A) is gs.legend_unit_A
