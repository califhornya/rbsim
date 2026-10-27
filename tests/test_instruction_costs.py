"""A cost inside a played card's instruction ("spend a buff to ...", "banish a
card from any trash to ...") is paid, and without it the effect doesn't happen.
These costs were never charged for "When you play me" and spell effects."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _play_wildclaw(buffed: bool):
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    loop = GameLoop(gs)
    other = UnitInPlay(card=UnitCard(name="Other", might=2), ready=True)
    other.might_counters = 1 if buffed else 0
    a.base_units.append(other)
    a.energy = 10
    a.hand = [CARD_REGISTRY["Wildclaw Shaman"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    shaman = next(u for u in a.base_units if u.card.name == "Wildclaw Shaman")
    return other, shaman


def test_wildclaw_shaman_spends_another_units_buff():
    """'When you play me, you may spend a buff to buff me and ready me.'"""
    other, shaman = _play_wildclaw(buffed=True)
    assert other.might_counters == 0
    assert shaman.might_counters == 1 and shaman.ready


def test_wildclaw_shaman_without_a_buff_to_spend_does_nothing():
    other, shaman = _play_wildclaw(buffed=False)
    assert shaman.might_counters == 0 and not shaman.ready
