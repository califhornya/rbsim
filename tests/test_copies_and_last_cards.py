"""Copies (Shady Spectacles while attached, Leblanc Deceiver's Reflection),
Ancient Henge, Chronobreak and Mystic Reversal."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import ChainItem, GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def test_shady_spectacles_copy_lasts_while_attached():
    loop = _loop()
    small = UnitInPlay(card=UnitCard(name="Small", might=1))
    model = UnitInPlay(card=_card("Ruin Runner"))                 # 5 Might
    loop.gs.A.base_units += [small, model]
    glasses = _card("Shady Spectacles")
    small.gear.append(glasses)
    loop._fire_attached(small, "A")
    assert small.card.name == "Ruin Runner" and small.might == 5
    small.gear.remove(glasses)
    loop._recompute_passives()
    assert small.card.name == "Small"


def test_leblanc_deceiver_makes_a_temporary_reflection():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Leblanc Deceiver"), ready=True)
    big = UnitInPlay(card=_card("Ruin Runner"))
    bf0.add_unit("B", big)
    loop.gs.A.hand = [UnitCard(name="Fodder")]
    loop._fire_scoring_trigger("on_hold", bf0, "A")
    reflection = next(u for u in bf0.units_A)
    assert reflection.card.name == "Ruin Runner" and reflection.is_token
    assert reflection.has_keyword("TEMPORARY") and not loop.gs.legend_unit_A.ready


def test_chronobreak_replays_a_damaged_unit():
    from riftbound.core.enums import Domain
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    hurt = UnitInPlay(card=UnitCard(name="Hurt", might=4))
    hurt.damage = 3
    bf0.add_unit("A", hurt)
    loop.gs.A.add_power(Domain.FURY, 1)
    loop._resolve_card_effects(_card("Chronobreak"), bf0, loop.gs.A, loop.gs.B)
    fresh = next(u for u in bf0.units_A)
    assert fresh is not hurt and fresh.card is hurt.card and fresh.damage == 0


def test_mystic_reversal_takes_over_the_opponents_spell():
    loop = _loop()
    theirs = SpellCard(name="Theirs")
    loop.gs.chain.append(ChainItem(player="B", card=theirs, bf_idx=0))
    REGISTRY["steal_spell"](EffectContext(loop, _card("Mystic Reversal"), loop.gs.A, loop.gs.B,
                                          loop.gs.battlefields[0], {}), {})
    assert loop.gs.chain[0].player == "A"
