"""Riftbound mulligan (Core Rules §116-117): draw 4, then set aside up to TWO
cards, draw that many from the top, and recycle the set-aside cards to the bottom
(no shuffle). Resolution lives on Player.mulligan and is shared by the engine and
the search agent."""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.player import Deck, Player


def _player(hand_names, deck_names):
    # Deck.draw() pops the END, so deck_names[-1] is the TOP of the deck.
    p = Player(name="A", deck=Deck(cards=[UnitCard(name=n, might=1) for n in deck_names]))
    p.hand = [UnitCard(name=n, might=1) for n in hand_names]
    return p


def test_mulligan_draws_from_top_then_recycles_to_bottom():
    p = _player(["H0", "H1", "H2", "H3"], ["Dbot", "Dmid", "Dtop"])
    p.mulligan([1], random.Random(0))            # return H1
    assert len(p.hand) == 4                       # size preserved
    assert "H1" not in [c.name for c in p.hand]   # H1 left the hand
    assert "Dtop" in [c.name for c in p.hand]     # replacement came from the TOP
    assert p.deck.cards[0].name == "H1"           # H1 recycled to the BOTTOM (front)


def test_mulligan_caps_at_two():
    p = _player(["H0", "H1", "H2", "H3"], ["d0", "d1", "d2", "d3", "d4"])
    set_aside = p.mulligan([0, 1, 2, 3], random.Random(0))   # ask to return 4
    assert len(set_aside) == 2                    # §117.1: at most two
    assert len(p.hand) == 4


def test_mulligan_keep_all_is_noop():
    p = _player(["H0", "H1", "H2", "H3"], ["d0", "d1"])
    before_hand = [c.name for c in p.hand]
    before_deck = [c.name for c in p.deck.cards]
    p.mulligan([], random.Random(0))
    assert [c.name for c in p.hand] == before_hand
    assert [c.name for c in p.deck.cards] == before_deck


def test_mulligan_two_returned_cards_go_to_bottom():
    p = _player(["H0", "H1", "H2", "H3"], ["d0", "d1", "d2", "d3"])
    p.mulligan([0, 2], random.Random(0))          # return H0 and H2
    bottom_two = {c.name for c in p.deck.cards[:2]}
    assert bottom_two == {"H0", "H2"}             # both recycled to the bottom
    assert "H0" not in [c.name for c in p.hand] and "H2" not in [c.name for c in p.hand]
