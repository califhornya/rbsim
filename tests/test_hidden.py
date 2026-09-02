"""HIDDEN keyword (Core Rules §737 / §408 / §106.4).

Hide: on your turn, in an Open State, pay 1 power to place a Hidden card facedown
at a battlefield you control whose Facedown Zone is empty. From the NEXT turn it
gains Reaction and may be played for [0] to that battlefield. Behavior lives on
GameLoop._hide_card / _play_from_hidden and their legality enumeration.
"""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, FacedownCard
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState


def _loop(power: int = 2, turn: int = 1) -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]), energy=5)
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    a.power_pool[Domain.FURY] = power
    a.rune_pool[Domain.FURY] = [Rune(domain=Domain.FURY) for _ in range(power)]
    gs = GameState(rng=random.Random(1), A=a, B=b, active="A", turn=turn)
    return GameLoop(gs)


def _control(loop, side, lane):
    """Give `side` sole control of a battlefield lane (a lone friendly unit)."""
    who = loop.gs.battlefields[lane].units_A if side == "A" else loop.gs.battlefields[lane].units_B
    who.append(UnitInPlay(UnitCard(name="Holder", might=1), ready=True))


def _hidden_unit(name="Sneaky"):
    return UnitCard(name=name, might=3, keywords=["HIDDEN"])


def test_hide_requires_control_and_pays_power():
    loop = _loop(power=2)
    card = _hidden_unit()
    loop.gs.A.hand.append(card)
    _control(loop, "A", 0)                      # A controls BF0
    assert loop._hide_card("A", 0, 0) is True
    bf = loop.gs.battlefields[0]
    assert bf.facedown is not None and bf.facedown.card is card
    assert card not in loop.gs.A.hand           # left the hand
    assert loop.gs.A.power_pool.get(Domain.FURY, 0) == 1   # 1 power spent


def test_hide_illegal_without_control_or_when_occupied():
    loop = _loop()
    card = _hidden_unit()
    loop.gs.A.hand.append(card)
    # No control of BF1 → not a legal hide lane.
    assert 1 not in loop._hide_lanes("A")
    assert loop._hide_card("A", 0, 1) is False
    # Control BF0 but its facedown zone is already occupied.
    _control(loop, "A", 0)
    loop.gs.battlefields[0].facedown = FacedownCard(card=UnitCard(name="X"), owner="A", turn_hidden=1)
    assert 0 not in loop._hide_lanes("A")
    assert loop._hide_card("A", 0, 0) is False


def test_hidden_not_playable_same_turn_but_playable_next_turn():
    loop = _loop(turn=3)
    card = _hidden_unit()
    loop.gs.A.hand.append(card)
    _control(loop, "A", 0)
    loop._hide_card("A", 0, 0)
    # Same turn → not yet playable.
    assert loop._hidden_playable_lanes("A") == []
    assert loop._play_from_hidden("A", 0) is False
    # Next turn → playable for [0]; the unit enters at that battlefield.
    loop.gs.turn = 4
    assert 0 in loop._hidden_playable_lanes("A")
    assert loop._play_from_hidden("A", 0) is True
    bf = loop.gs.battlefields[0]
    assert bf.facedown is None
    assert any(u.card is card for u in bf.units_A)


def test_hidden_spell_plays_onto_chain():
    loop = _loop(turn=1)
    spell = SpellCard(name="Sneaky Bolt", damage=1, keywords=["HIDDEN"])
    loop.gs.A.hand.append(spell)
    _control(loop, "A", 1)
    loop._hide_card("A", 0, 1)
    loop.gs.turn = 2
    # An enemy unit at BF1 to receive the spell's printed damage on resolve.
    loop.gs.battlefields[1].units_B.append(UnitInPlay(UnitCard(name="Foe", might=1), ready=True))
    assert loop._play_from_hidden("A", 1) is True
    assert loop.gs.battlefields[1].facedown is None
    assert spell in loop.gs.A.trash              # resolved spell → trash (§19a)


def test_cleanup_removes_facedown_on_loss_of_control():
    """§106.4.d/§322.8: if the owner no longer controls the battlefield, the
    facedown card is trashed during cleanup; if still controlled, it stays."""
    loop = _loop()
    # BF0: A hid a card but B has since taken sole control → removed to A's trash.
    lost = UnitCard(name="Lost", might=1)
    loop.gs.battlefields[0].facedown = FacedownCard(card=lost, owner="A", turn_hidden=1)
    loop.gs.battlefields[0].units_B.append(UnitInPlay(UnitCard(name="Enemy", might=1), ready=True))
    # BF1: A hid a card and still controls it → stays.
    kept = UnitCard(name="Kept", might=1)
    loop.gs.battlefields[1].facedown = FacedownCard(card=kept, owner="A", turn_hidden=1)
    _control(loop, "A", 1)

    loop._cleanup_hidden_cards()
    assert loop.gs.battlefields[0].facedown is None
    assert lost in loop.gs.A.trash
    assert loop.gs.battlefields[1].facedown is not None
    assert kept not in loop.gs.A.trash


def test_determinize_randomizes_opponent_facedown_identity():
    """From the observer's seat, the opponent's facedown identity is resampled
    (preferring a HIDDEN card) while the slot stays occupied and card counts hold."""
    from riftbound.core.state import determinize

    loop = _loop()
    # B has a facedown card whose true identity is 'Secret'; B's deck holds two
    # other HIDDEN cards it could be, from A's (observer's) point of view.
    secret = UnitCard(name="Secret", might=9, keywords=["HIDDEN"])
    loop.gs.battlefields[0].facedown = FacedownCard(card=secret, owner="B", turn_hidden=1)
    loop.gs.B.deck.cards.extend([
        UnitCard(name="DecoyA", might=1, keywords=["HIDDEN"]),
        UnitCard(name="DecoyB", might=1, keywords=["HIDDEN"]),
        UnitCard(name="Plain", might=1),
    ])
    before = sorted(c.name for c in ([loop.gs.battlefields[0].facedown.card]
                                     + loop.gs.B.hand + loop.gs.B.deck.cards))
    determinize(loop.gs, observer="A", rng=random.Random(0))
    fd = loop.gs.battlefields[0].facedown
    assert fd is not None and fd.owner == "B"          # slot still occupied
    assert fd.card.has_keyword("HIDDEN")               # resampled to a HIDDEN identity
    after = sorted(c.name for c in ([fd.card] + loop.gs.B.hand + loop.gs.B.deck.cards))
    assert after == before                             # B's card multiset conserved


def test_legality_offers_hide_then_hidden_play():
    loop = _loop(turn=5)
    card = _hidden_unit()
    loop.gs.A.hand.append(card)
    _control(loop, "A", 0)
    acts = {a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")}
    assert ("HIDE", 0, 0) in acts
    # After hiding, next turn the reaction legality offers the [0] play.
    loop._hide_card("A", 0, 0)
    loop.gs.turn = 6
    react = {a.to_engine() for a in legal_actions(loop, DecisionPoint.REACTION, "A")}
    assert ("HIDDEN_PLAY", None, 0) in react
