"""move_unit / move_units_to_base: units move where the effect says (an enemy to
its base or into "here", a friendly unit where it attacks best), moving doesn't
ready or exhaust, and the moved unit's move triggers fire."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _u(name, might, ready=False):
    return UnitInPlay(card=UnitCard(name=name, might=might), ready=ready)


def _cast(loop, card_name, lane=0):
    card = CARD_REGISTRY[card_name].instantiate()
    loop._resolve_card_effects(card, loop.gs.battlefields[lane], loop.gs.A, loop.gs.B)


def test_charm_sends_their_mightiest_battlefield_unit_home():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    small, big = _u("Small", 2), _u("Big", 6)
    bf0.add_unit("B", small)
    bf1.add_unit("B", big)
    loop.gs.B.base_units.append(_u("Home", 9))
    _cast(loop, "Charm")
    assert big in loop.gs.B.base_units and small in bf0.units_B


def test_ride_the_wind_attacks_where_it_wins_and_readies():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("B", _u("Wall", 9))
    bf1.add_unit("B", _u("Twig", 2))
    hero = _u("Hero", 4)
    loop.gs.A.base_units.append(hero)
    _cast(loop, "Ride the Wind")
    assert hero in bf1.units_A and hero.ready


def test_moonfall_pulls_their_weakest_unit_here():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", _u("Mine", 3))
    weak, strong = _u("Weak", 1), _u("Strong", 5)
    bf1.add_unit("B", strong)
    loop.gs.B.base_units.append(weak)
    _cast(loop, "Moonfall", lane=0)
    assert weak in bf0.units_B
    assert weak.might == 0                          # -2 this turn, floored at 0


def test_flash_returns_two_units_losing_their_fights_without_readying():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    losing1, losing2, winning = _u("L1", 1), _u("L2", 2), _u("W", 9)
    bf0.add_unit("A", losing1)
    bf0.add_unit("A", losing2)
    bf0.add_unit("B", _u("Bully", 8))
    bf1.add_unit("A", winning)
    _cast(loop, "Flash")
    assert {u.card.name for u in loop.gs.A.base_units} == {"L1", "L2"}
    assert winning in bf1.units_A
    assert not losing1.ready and not losing2.ready


def test_effect_move_fires_move_triggers():
    loop = _loop()
    herder = UnitInPlay(card=CARD_REGISTRY["Stellacorn Herder"].instantiate())
    loop.gs.A.base_units.append(herder)
    ctx = EffectContext(loop, UnitCard(name="Mover"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["move_unit"](ctx, {"target": "friendly_unit", "destination": "here"})
    assert herder in loop.gs.battlefields[0].units_A
    assert len(loop.gs.A.hand) == 1                  # "When I move, draw 1"
