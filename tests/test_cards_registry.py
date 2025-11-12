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


def test_registry_loads_core_cards():
    assert "Stalwart Recruit" in CARD_REGISTRY
    assert "Bolt" in CARD_REGISTRY
    assert "Iron Shield" in CARD_REGISTRY


def test_bolt_spell_resolves_via_effect():
    loop = make_game()
    gs = loop.gs
    battlefield = gs.battlefields[0]
    battlefield.add_unit("B", UnitInPlay(UnitCard(name="Target", might=2)))

    bolt_spec = CARD_REGISTRY["Bolt"]
    bolt_card = bolt_spec.instantiate()

    player_a = gs.A
    player_a.hand.append(bolt_card)
    player_a.energy = 5

    loop._apply_action(player_a, ("SPELL", 0, 0, None))

    assert len(battlefield.units_B) == 0


def test_iron_shield_grants_might_to_allies():
    loop = make_game()
    gs = loop.gs
    battlefield = gs.battlefields[0]
    unit = UnitInPlay(UnitCard(name="Ally", might=1))
    battlefield.add_unit("A", unit)

    gear_spec = CARD_REGISTRY["Iron Shield"]
    gear_card = gear_spec.instantiate()

    player_a = gs.A
    player_a.hand.append(gear_card)
    player_a.energy = 5

    loop._apply_action(player_a, ("GEAR", 0, 0, None))

    assert unit.card.might == 2
