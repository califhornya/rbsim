"""B1 — optional additional cost (kicker) paid at play time.

Plays synthetic cards through GameLoop._apply_action (the real play path) and
checks that an effect gated on `condition: kicker_paid` fires only when the
`additional_cost` was actually paid. Policy under test: always pay if affordable.
"""

import random

import pytest

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _make_loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def _reg(name: str, category: str, effects: list, might: int = 2) -> None:
    CARD_REGISTRY[name] = CardSpec.from_dict(
        {"name": name, "category": category, "might": might, "effects": effects}
    )


@pytest.fixture
def cleanup_registry():
    added: list[str] = []
    yield added
    for name in added:
        CARD_REGISTRY.pop(name, None)


def test_energy_kicker_fires_when_affordable(cleanup_registry):
    name = "TST Kicker Energy"
    _reg(name, "UNIT", [{
        "effect": "gain_energy", "trigger": "on_play", "amount": 5, "target": "actor",
        "condition": {"type": "kicker_paid"}, "additional_cost": {"energy": 1},
    }])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    ap.hand.append(UnitCard(name=name, cost_energy=0)); ap.energy = 2
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    # 2 - 1 (kicker) + 5 (gated effect fires) = 6
    assert ap.energy == 6


def test_energy_kicker_skipped_when_unaffordable(cleanup_registry):
    name = "TST Kicker Energy Poor"
    _reg(name, "UNIT", [{
        "effect": "gain_energy", "trigger": "on_play", "amount": 5, "target": "actor",
        "condition": {"type": "kicker_paid"}, "additional_cost": {"energy": 1},
    }])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    ap.hand.append(UnitCard(name=name, cost_energy=0)); ap.energy = 0
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    # kicker unaffordable -> not paid -> gated effect skipped
    assert ap.energy == 0


def test_discard_kicker_pays_and_protects_played_card(cleanup_registry):
    name = "TST Kicker Discard"
    _reg(name, "UNIT", [{
        "effect": "gain_energy", "trigger": "on_play", "amount": 5, "target": "actor",
        "condition": {"type": "kicker_paid"}, "additional_cost": {"discard_cards": 1},
    }])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    played = UnitCard(name=name, cost_energy=0)
    filler = UnitCard(name="TST Filler", cost_energy=0)
    # filler at idx 0, played at idx 1 — exercises the index-shift recompute.
    ap.hand = [filler, played]; ap.energy = 0
    loop._apply_action(ap, ("UNIT", 1, 0, None))
    assert ap.energy == 5            # kicker paid -> effect fired
    assert filler in ap.trash        # filler was discarded for the kicker
    assert played not in ap.trash    # the played card was NOT discarded
    assert played not in ap.hand     # played card removed from hand at the right index


def test_discard_kicker_skipped_with_only_played_card(cleanup_registry):
    name = "TST Kicker Discard Solo"
    _reg(name, "UNIT", [{
        "effect": "gain_energy", "trigger": "on_play", "amount": 5, "target": "actor",
        "condition": {"type": "kicker_paid"}, "additional_cost": {"discard_cards": 1},
    }])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    ap.hand = [UnitCard(name=name, cost_energy=0)]; ap.energy = 0
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    # only the played card in hand -> nothing else to discard -> kicker not paid
    assert ap.energy == 0


def test_unconditional_effect_fires_even_when_kicker_unaffordable(cleanup_registry):
    name = "TST Two Effects"
    _reg(name, "UNIT", [
        {"effect": "gain_energy", "trigger": "on_play", "amount": 5, "target": "actor",
         "condition": {"type": "kicker_paid"}, "additional_cost": {"energy": 99}},
        {"effect": "gain_energy", "trigger": "on_play", "amount": 2, "target": "actor"},
    ])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    ap.hand.append(UnitCard(name=name, cost_energy=0)); ap.energy = 1
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    # kicker unaffordable -> gated effect skipped; unconditional effect still fires
    assert ap.energy == 3   # 1 + 2


def test_kicker_paid_flag_reset_after_resolution(cleanup_registry):
    name = "TST Kicker Reset"
    _reg(name, "UNIT", [{
        "effect": "gain_energy", "trigger": "on_play", "amount": 1, "target": "actor",
        "condition": {"type": "kicker_paid"}, "additional_cost": {"energy": 1},
    }])
    cleanup_registry.append(name)
    loop = _make_loop(); ap = loop.gs.A; loop.gs.active = "A"
    card = UnitCard(name=name, cost_energy=0)
    ap.hand.append(card); ap.energy = 2
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    # flag must not persist on the instance after resolution
    assert getattr(card, "_kicker_paid", False) is False
