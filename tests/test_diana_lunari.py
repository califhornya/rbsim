"""Diana Lunari (§on_showdown_begin): when a showdown begins at her battlefield, the
controller may pay [1] to PREDICT + reveal the top card and draw it if it's a spell.
Covers the reveal_top_draw_if_spell effect and the on_showdown_begin trigger firing.
"""

from __future__ import annotations

import random

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def test_reveal_top_draws_a_spell_not_a_unit():
    loop = _loop()
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    loop.gs.A.deck.cards = [UnitCard(name="Filler", might=1), SpellCard(name="TST Bolt")]
    ctx.reveal_top_draw_if_spell()               # top is a spell -> drawn
    assert any(c.name == "TST Bolt" for c in loop.gs.A.hand)

    loop.gs.A.hand.clear()
    loop.gs.A.deck.cards = [SpellCard(name="Deep"), UnitCard(name="TopUnit", might=1)]
    ctx.reveal_top_draw_if_spell()               # top is a unit -> nothing drawn
    assert loop.gs.A.hand == []


def test_diana_lunari_showdown_begin_pays_and_draws():
    loop = _loop(); loop.gs.active = "A"
    lunari = UnitInPlay(card=CARD_REGISTRY["Diana Lunari"].instantiate(), ready=True)
    bf = loop.gs.battlefields[0]
    bf.units_A.append(lunari)
    loop.gs.A.deck.cards = [UnitCard(name="Filler", might=1), SpellCard(name="TST Bolt")]
    loop.gs.A.energy = 1

    loop._resolve_triggered_effects(lunari.card, "on_showdown_begin", bf,
                                    loop.gs.A, loop.gs.B, context_extra={"battlefield": bf})

    assert any(c.name == "TST Bolt" for c in loop.gs.A.hand)   # drew the spell
    assert loop.gs.A.energy == 0                                # paid [1]


def test_diana_lunari_does_nothing_when_unaffordable():
    loop = _loop(); loop.gs.active = "A"
    lunari = UnitInPlay(card=CARD_REGISTRY["Diana Lunari"].instantiate(), ready=True)
    bf = loop.gs.battlefields[0]
    bf.units_A.append(lunari)
    loop.gs.A.deck.cards = [SpellCard(name="TST Bolt")]
    loop.gs.A.energy = 0                          # can't pay [1]

    loop._resolve_triggered_effects(lunari.card, "on_showdown_begin", bf,
                                    loop.gs.A, loop.gs.B, context_extra={"battlefield": bf})

    assert loop.gs.A.hand == []                   # cost unaffordable -> no draw
    assert len(loop.gs.A.deck.cards) == 1
