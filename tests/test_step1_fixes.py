"""Regression tests for the Step 1 fixes: the six malformed-spec offenders
(KNOWN_ISSUES / RECAP §3) plus the new channel_rune and kill_gear handlers
and the recall-to-hand semantic."""

import random

import pytest

from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.effects import REGISTRY
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState


def _make_loop() -> GameLoop:
    player_a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    player_b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=player_a, B=player_b)
    return GameLoop(gs)


def _ctx(loop: GameLoop, card=None) -> EffectContext:
    card = card or SpellCard(name="TST Spell")
    return EffectContext(loop, card, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])


def test_channel_rune_ready():
    loop = _make_loop()
    loop.gs.A.rune_deck = RuneDeck([Rune(domain=Domain.FURY), Rune(domain=Domain.CHAOS)])
    REGISTRY["channel_rune"](_ctx(loop), {"target": "actor", "amount": 2})
    assert loop.gs.A.total_runes_in_play() == 2
    assert all(r.ready for runes in loop.gs.A.rune_pool.values() for r in runes)


def test_channel_rune_exhausted():
    # Retreat: "Its owner channels 1 rune exhausted."
    loop = _make_loop()
    loop.gs.A.rune_deck = RuneDeck([Rune(domain=Domain.FURY)])
    REGISTRY["channel_rune"](_ctx(loop), {"target": "actor", "amount": 1, "exhausted": True})
    runes = [r for rs in loop.gs.A.rune_pool.values() for r in rs]
    assert len(runes) == 1
    assert not runes[0].ready


def test_kill_gear_destroys_attached_and_base_gear():
    # Thermo Beam: "Kill all gear."
    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    sword = GearCard(name="TST Sword")
    shield = GearCard(name="TST Shield")
    unit_a = UnitInPlay(UnitCard(name="TST A", might=2), ready=True, gear=[sword])
    unit_b = UnitInPlay(UnitCard(name="TST B", might=2), ready=True)
    bf.units_A.append(unit_a)
    bf.units_B.append(unit_b)
    loop.gs.B.base_gear.append(shield)

    REGISTRY["kill_gear"](_ctx(loop), {"scope": "all"})

    assert unit_a.gear == []
    assert sword in loop.gs.A.trash
    assert loop.gs.B.base_gear == []
    assert shield in loop.gs.B.trash
    # Units themselves survive.
    assert unit_a in bf.units_A and unit_b in bf.units_B


def test_recall_unit_returns_to_hand():
    # Retreat / Rebuke: "Return a ... unit to its owner's hand."
    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    gear = GearCard(name="TST Gear")
    card = UnitCard(name="TST Unit", might=3)
    unit = UnitInPlay(card, ready=True, gear=[gear])
    bf.units_A.append(unit)

    REGISTRY["recall_unit"](_ctx(loop), {"target": "friendly_unit"})

    assert bf.units_A == []
    assert card in loop.gs.A.hand
    assert gear in loop.gs.A.base_gear  # gear is recovered, not bounced


def test_recall_token_ceases_to_exist():
    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    token = UnitInPlay(UnitCard(name="TST Token", might=1), ready=True, is_token=True)
    bf.units_A.append(token)

    REGISTRY["recall_unit"](_ctx(loop), {"target": "friendly_unit"})

    assert bf.units_A == []
    assert loop.gs.A.hand == []


def test_kill_all_units_both_sides():
    # The Ruination: "Kill all units." (target: battlefield, scope: all)
    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    card_a = UnitCard(name="TST Mine", might=2)
    card_b = UnitCard(name="TST Theirs", might=4)
    bf.units_A.append(UnitInPlay(card_a, ready=True))
    bf.units_B.append(UnitInPlay(card_b, ready=True))

    REGISTRY["kill_unit"](_ctx(loop), {"target": "battlefield", "scope": "all"})

    assert bf.units_A == [] and bf.units_B == []
    assert card_a in loop.gs.A.trash
    assert card_b in loop.gs.B.trash


def test_recall_both_sides_with_might_filter():
    # Angler Beast: "return all units with 2 [might] or less to their owners' hands."
    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    small_a = UnitCard(name="TST Small A", might=2)
    big_a = UnitCard(name="TST Big A", might=5)
    small_b = UnitCard(name="TST Small B", might=1)
    bf.units_A.extend([UnitInPlay(small_a, ready=True), UnitInPlay(big_a, ready=True)])
    bf.units_B.append(UnitInPlay(small_b, ready=True))

    REGISTRY["recall_unit"](_ctx(loop), {
        "target": "battlefield", "scope": "all",
        "target_filter": {"might_at_most": 2, "is_unit": True},
    })

    assert [u.card for u in bf.units_A] == [big_a]
    assert bf.units_B == []
    assert small_a in loop.gs.A.hand
    assert small_b in loop.gs.B.hand


def test_return_from_trash_spell_filter():
    # Annie Stubborn: "return a spell from your trash to your hand."
    loop = _make_loop()
    unit_card = UnitCard(name="TST Dead Unit", might=2)
    spell_card = SpellCard(name="TST Dead Spell")
    loop.gs.A.trash.extend([unit_card, spell_card])

    REGISTRY["return_from_trash"](_ctx(loop), {
        "target": "actor", "count": 1, "target_filter": {"is_spell": True},
    })

    assert spell_card in loop.gs.A.hand
    assert unit_card in loop.gs.A.trash
