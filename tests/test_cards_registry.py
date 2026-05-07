from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.cards_registry import CARD_REGISTRY
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
    assert "Caitlyn Patrolling" in CARD_REGISTRY
    assert "Chemtech Enforcer" in CARD_REGISTRY