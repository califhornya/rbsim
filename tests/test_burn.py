"""Vendetta BURN action: move top X cards of the Main Deck to the trash."""

from __future__ import annotations

import random

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.effects import REGISTRY as EFFECT_REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop_with_deck(n_cards: int) -> GameLoop:
    cards = [UnitCard(name=f"C{i}", might=1) for i in range(n_cards)]
    a = Player(name="A", deck=Deck(cards=cards), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def test_burn_moves_cards_deck_to_trash():
    loop = _loop_with_deck(5)
    a = loop.gs.A
    ctx = EffectContext(loop, SpellCard(name="Src"), a, loop.gs.B, loop.gs.battlefields[0])
    EFFECT_REGISTRY["burn"](ctx, {"amount": 2})
    assert len(a.deck.cards) == 3
    assert len(a.trash) == 2
    assert loop.gs.cards_burned_this_turn["A"] == 2


def test_burn_stops_at_empty_deck():
    loop = _loop_with_deck(1)
    a = loop.gs.A
    ctx = EffectContext(loop, SpellCard(name="Src"), a, loop.gs.B, loop.gs.battlefields[0])
    EFFECT_REGISTRY["burn"](ctx, {"amount": 3})
    assert len(a.deck.cards) == 0
    assert len(a.trash) == 1
    assert loop.gs.cards_burned_this_turn["A"] == 1


def test_cards_burned_condition():
    loop = _loop_with_deck(5)
    a = loop.gs.A
    ctx = EffectContext(loop, SpellCard(name="Src"), a, loop.gs.B, loop.gs.battlefields[0])
    cond = {"type": "cards_burned_this_turn_at_least", "params": {"amount": 2}}
    assert loop._check_condition(cond, ctx.card, a, loop.gs.B, None) is False
    EFFECT_REGISTRY["burn"](ctx, {"amount": 2})
    assert loop._check_condition(cond, ctx.card, a, loop.gs.B, None) is True
