"""B2 — new amount_source values in effects._amount."""

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import _amount
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def _ctx(loop) -> EffectContext:
    return EffectContext(loop, UnitCard(name="Src"), loop.gs.A, loop.gs.B,
                         loop.gs.battlefields[0])


def _u(name="U", might=2, tags=None) -> UnitInPlay:
    return UnitInPlay(card=UnitCard(name=name, might=might, tags=tags or []))


def test_controller_and_opponent_points():
    loop = _loop()
    loop.gs.points_A = 3
    loop.gs.points_B = 5
    ctx = _ctx(loop)
    assert _amount(ctx, {"amount_source": "controller_points"}) == 3
    assert _amount(ctx, {"amount_source": "opponent_points"}) == 5


def test_cards_in_hand():
    loop = _loop()
    loop.gs.A.hand = [UnitCard(name="a"), UnitCard(name="b"), UnitCard(name="c")]
    assert _amount(_ctx(loop), {"amount_source": "cards_in_hand"}) == 3


def test_highest_might_friendly():
    loop = _loop()
    loop.gs.battlefields[0].units_A.append(_u(might=4))
    loop.gs.A.base_units.append(_u(might=7))
    loop.gs.battlefields[0].units_B.append(_u(might=9))  # enemy, ignored
    assert _amount(_ctx(loop), {"amount_source": "highest_might_friendly"}) == 7


def test_enemies_and_friendly_units_here():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    bf.units_A.extend([_u(), _u()])
    bf.units_B.append(_u())
    ctx = _ctx(loop)
    assert _amount(ctx, {"amount_source": "friendly_units_here"}) == 2
    assert _amount(ctx, {"amount_source": "enemies_here"}) == 1


def test_n_friendly_with_tag():
    loop = _loop()
    loop.gs.battlefields[0].units_A.extend([
        _u(tags=["Zaun"]), _u(tags=["Zaun", "Pirate"]), _u(tags=["Noxus"]),
    ])
    ctx = _ctx(loop)
    spec = {"amount_source": "n_friendly_with_tag", "tag": "Zaun"}
    assert _amount(ctx, spec) == 2


def test_n_distinct_tags_among_friendlies():
    loop = _loop()
    loop.gs.battlefields[0].units_A.extend([
        _u(tags=["Zaun"]), _u(tags=["Zaun", "Pirate"]),
    ])
    loop.gs.A.base_units.append(_u(tags=["Noxus"]))
    assert _amount(_ctx(loop), {"amount_source": "n_distinct_tags_among_friendlies"}) == 3
