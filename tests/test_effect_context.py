import random

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _make_loop() -> GameLoop:
    deck_a = Deck(cards=[SpellCard(name="Bolt", damage=2) for _ in range(3)])
    deck_b = Deck(cards=[])
    player_a = Player(name="A", deck=deck_a, rune_deck=RuneDeck([]))
    player_b = Player(name="B", deck=deck_b, rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=player_a, B=player_b)
    return GameLoop(gs)


def _make_context(loop: GameLoop) -> EffectContext:
    battlefield = loop.gs.battlefields[0]
    card = SpellCard(name="Test Bolt")
    return EffectContext(loop, card, loop.gs.A, loop.gs.B, battlefield)


def test_draw_cards_effect_context():
    loop = _make_loop()
    ctx = _make_context(loop)
    ctx.draw_cards(2)
    assert len(loop.gs.A.hand) == 2
    assert len(loop.gs.A.deck.cards) == 1


def test_gain_energy_effect_context():
    loop = _make_loop()
    ctx = _make_context(loop)
    loop.gs.A.energy = 1
    ctx.gain_energy(3)
    assert loop.gs.A.energy == 4


def test_ready_units_effect_context():
    loop = _make_loop()
    battlefield = loop.gs.battlefields[0]
    unit_one = UnitInPlay(UnitCard(name="Soldier", might=2), ready=False)
    unit_two = UnitInPlay(UnitCard(name="Archer", might=1), ready=False)
    battlefield.units_A.extend([unit_one, unit_two])
    enemy_unit = UnitInPlay(UnitCard(name="Raider", might=3), ready=False)
    battlefield.units_B.append(enemy_unit)
    ctx = _make_context(loop)

    ctx.ready_units(scope="single")
    assert unit_one.ready is True
    assert unit_two.ready is False

    ctx.ready_units(target="opponent")
    assert enemy_unit.ready is True


def test_add_rune_effect_context():
    loop = _make_loop()
    ctx = _make_context(loop)
    ctx.add_rune("CALM")
    assert Domain.CALM in loop.gs.A.rune_pool
    rune = loop.gs.A.rune_pool[Domain.CALM][0]
    assert rune.ready is True

    ctx.add_rune("R", ready=False)
    assert Domain.FURY in loop.gs.A.rune_pool
    assert loop.gs.A.rune_pool[Domain.FURY][0].ready is False


def test_add_rune_invalid_domain():
    loop = _make_loop()
    ctx = _make_context(loop)
    try:
        ctx.add_rune("UNKNOWN")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid domain")