"""Baseline policies for choices the engine makes for a player, as fixed after
the choice audit (scripts/choice_audit.py): "return a unit" and "-N Might" aim
at an enemy, costs give up what the player misses least, a "you may" cost is a
choice, modes are compared on a copy of the game, combat damage kills the most
Might it can; and cards are compared by identity."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _u(name, might=2, **kw):
    card = UnitCard(name=name, might=might)
    card.is_token = kw.get("is_token", False)     # as GameLoop._play_token makes them
    return UnitInPlay(card=card, **kw)


def _cast(loop, name, bf_idx=0):
    card = CARD_REGISTRY[name].instantiate()
    loop._resolve_card_effects(card, loop.gs.battlefields[bf_idx], loop.gs.A, loop.gs.B)
    return card


def _mine_and_theirs(loop, mine=3, theirs=3):
    bf = loop.gs.battlefields[0]
    friend, enemy = _u("Friend", mine), _u("Enemy", theirs)
    bf.add_unit("A", friend)
    bf.add_unit("B", enemy)
    return bf, friend, enemy


def test_rebuke_returns_an_enemy_unit():
    loop = _loop()
    bf, friend, enemy = _mine_and_theirs(loop)
    _cast(loop, "Rebuke")
    assert bf.units_A == [friend] and bf.units_B == []
    assert loop.gs.B.hand == [enemy.card]


def test_minus_might_on_a_unit_hits_an_enemy():
    loop = _loop()
    bf, friend, enemy = _mine_and_theirs(loop, 5, 5)
    _cast(loop, "Frigid Touch")
    assert enemy.temporary_might < 0 and friend.temporary_might == 0


def test_kill_cost_gives_up_a_token_first():
    loop = _loop()
    ap = loop.gs.A
    big = _u("Big", 8)
    loop.gs.battlefields[0].add_unit("A", big)
    token = _u("Recruit", 1, is_token=True)
    ap.base_units.append(token)
    card = CARD_REGISTRY["Dune Devourer"].instantiate()
    assert loop._pay_one_additional_cost(card, ap, {"kill_friendly_unit": True})
    assert ap.base_units == [] and loop.gs.battlefields[0].units_A == [big]
    assert ap.trash == []                         # a token ceases to exist


def test_kill_cost_kills_a_base_unit_before_a_fighting_one():
    loop = _loop()
    ap = loop.gs.A
    loop.gs.battlefields[0].add_unit("A", _u("Fighter", 2))
    waiting = _u("Waiting", 4)
    ap.base_units.append(waiting)
    card = CARD_REGISTRY["Dune Devourer"].instantiate()
    assert loop._pay_one_additional_cost(card, ap, {"kill_friendly_unit": True})
    assert ap.trash == [waiting.card]             # it died (to the trash)


def test_sacrifice_needs_a_mighty_unit():
    loop = _loop()
    ap = loop.gs.A
    card = CARD_REGISTRY["Sacrifice"].instantiate()
    ap.base_units.append(_u("Small", 4))
    assert loop._play_forbidden(ap, card)
    ap.base_units.append(_u("Mighty", 5))
    assert not loop._play_forbidden(ap, card)


def test_zaun_punk_kills_a_friendly_gear_not_a_unit():
    loop = _loop()
    ap = loop.gs.A
    unit = _u("Unit", 3)
    ap.base_units.append(unit)
    gear = GearCard(name="Old Gear", cost_energy=1)
    ap.base_gear.append(gear)
    card = CARD_REGISTRY["Zaun Punk"].instantiate()
    spec = next(es for es in CARD_REGISTRY["Zaun Punk"].effects if es.additional_cost)
    assert loop._pay_one_additional_cost(card, ap, spec.additional_cost)
    assert ap.base_gear == [] and ap.trash == [gear] and ap.base_units == [unit]


def test_a_you_may_additional_cost_is_a_choice():
    loop = _loop()
    ap = loop.gs.A
    token = _u("Recruit", 1, is_token=True)
    ap.base_units.append(token)
    seen = []

    def decline(loop, kind, side, options, default, source):
        seen.append(kind)
        return 1 if kind == "optional:additional_cost" else None
    loop.chooser = decline
    card = CARD_REGISTRY["Dune Devourer"].instantiate()
    assert not loop._try_pay_additional_costs(card, ap)
    assert seen == ["optional:additional_cost"] and ap.base_units == [token]


def test_modes_are_compared_on_a_copy_of_the_game():
    # Mesmerize: "return a friendly unit to hand" or "give an enemy -2": the second.
    loop = _loop()
    bf, friend, enemy = _mine_and_theirs(loop)
    _cast(loop, "Mesmerize")
    assert bf.units_A == [friend] and enemy.temporary_might == -2
    # Disposal Order: recycle cards from the opponent's trash, or draw 1: draw.
    loop = _loop()
    loop.gs.B.trash.extend(UnitCard(name=f"T{i}") for i in range(3))
    _cast(loop, "Disposal Order")
    assert len(loop.gs.A.hand) == 1 and len(loop.gs.B.trash) == 3


def test_recycling_a_spell_played_from_the_trash_keeps_both_copies():
    # Fizz Trickster with two copies of a spell in the trash: the played copy
    # is recycled, the other stays (value equality moved one and lost the other).
    loop = _loop()
    ap = loop.gs.A
    first, second = SpellCard(name="Zap", cost_energy=1), SpellCard(name="Zap", cost_energy=1)
    assert first != second
    ap.trash.extend([first, second])
    ctx = EffectContext(loop, UnitCard(name="Fizz Trickster"), ap, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["play_from_trash"](ctx, {"pay_power": True, "then": "recycle",
                                      "target_filter": {"is_spell": True}})
    assert ap.trash == [second] and ap.deck.cards[0] is first


def test_ready_and_buff_skip_units_they_would_do_nothing_to():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    ready, tired = _u("Ready", 3, ready=True), _u("Tired", 3, ready=False)
    bf.add_unit("A", ready)
    bf.add_unit("A", tired)
    ctx = EffectContext(loop, UnitCard(name="Src"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["ready_unit"](ctx, {"effect": "ready_unit", "target": "friendly_unit"})
    assert tired.ready
    ready.might_counters = 1
    REGISTRY["buff_unit"](ctx, {"effect": "buff_unit", "target": "friendly_unit"})
    assert tired.might_counters == 1
