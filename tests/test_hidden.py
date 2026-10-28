"""HIDDEN keyword (Core Rules §737 / §408 / §106.4).

Hide: on your turn, in an Open State, pay 1 power to place a Hidden card facedown
at a battlefield you control whose Facedown Zone has room (one card; two at
Bandle Tree or with a Bushwhack Trap). From the NEXT turn it
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
from riftbound.registry.cards_registry import CARD_REGISTRY


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


# --- A Facedown Zone that holds more than one card (§107.3.b.1) --------------

def _named_bf(loop, lane, name):
    loop.gs.battlefields[lane].card = CARD_REGISTRY[name].instantiate()


def test_bandle_tree_holds_a_second_facedown_card():
    """Bandle Tree: 'You may hide an additional card here.'"""
    loop = _loop(power=3)
    _named_bf(loop, 0, "Bandle Tree")
    loop.gs.A.hand.extend([_hidden_unit("One"), _hidden_unit("Two"), _hidden_unit("Three")])
    _control(loop, "A", 0)
    _control(loop, "A", 1)
    assert loop._hide_card("A", 0, 0) and loop._hide_card("A", 0, 0)
    assert [fd.card.name for fd in loop.gs.battlefields[0].facedowns] == ["One", "Two"]
    assert loop._hide_lanes("A") == [1]                  # full here; one at a plain battlefield
    assert loop._hide_card("A", 0, 0) is False
    assert loop._hide_card("A", 0, 1) is True
    assert loop._hide_lanes("A") == []


def test_both_cards_at_bandle_tree_are_played_separately():
    loop = _loop(power=2, turn=3)
    _named_bf(loop, 0, "Bandle Tree")
    one, two = _hidden_unit("One"), _hidden_unit("Two")
    loop.gs.A.hand.extend([one, two])
    _control(loop, "A", 0)
    loop._hide_card("A", 0, 0)
    loop._hide_card("A", 0, 0)
    loop.gs.turn = 4
    react = {a.to_engine() for a in legal_actions(loop, DecisionPoint.REACTION, "A")}
    assert {("HIDDEN_PLAY", None, 0), ("HIDDEN_PLAY", 1, 0)} <= react
    # The second one (slot 1), by the reaction path; the first stays hidden.
    assert loop._reaction_step(loop.gs.A, "A", ("HIDDEN_PLAY", 1, 0)) == "acted"
    bf = loop.gs.battlefields[0]
    assert any(u.card is two for u in bf.units_A)
    assert [fd.card for fd in bf.facedowns] == [one]
    assert loop._hidden_playable("A") == [(0, 0)]


def test_cleanup_trashes_every_facedown_card_at_a_lost_bandle_tree():
    loop = _loop()
    _named_bf(loop, 0, "Bandle Tree")
    bf = loop.gs.battlefields[0]
    bf.facedowns = [FacedownCard(card=_hidden_unit("One"), owner="A", turn_hidden=1),
                    FacedownCard(card=_hidden_unit("Two"), owner="A", turn_hidden=1)]
    _control(loop, "B", 0)                                # B alone there: A lost it
    loop._cleanup_hidden_cards()
    assert bf.facedowns == []
    assert sorted(c.name for c in loop.gs.A.trash) == ["One", "Two"]


def test_bushwhack_trap_gives_its_controller_a_second_facedown_card():
    """Bushwhack Trap: 'While you or an ally control this battlefield, that
    player may hide an additional card here.' When it dies the zone holds one
    again and the newest card goes to the trash (§107.3.b.2)."""
    loop = _loop(power=2)
    loop.gs.A.hand.extend([_hidden_unit("One"), _hidden_unit("Two")])
    _control(loop, "A", 0)
    bf = loop.gs.battlefields[0]
    loop._deploy_gear("A", bf, CARD_REGISTRY["Bushwhack Trap"].instantiate())
    assert loop._facedown_capacity(bf) == 2
    assert loop._hide_card("A", 0, 0) and loop._hide_card("A", 0, 0)
    loop._kill_deployed_gear(bf, "A", list(bf.gear_A))
    assert [fd.card.name for fd in bf.facedowns] == ["One"]
    assert [c.name for c in loop.gs.A.trash] == ["Bushwhack Trap", "Two"]


def test_an_enemy_bushwhack_trap_gives_nothing():
    """The Trap's controller must control the battlefield: B's Trap at a
    battlefield A controls leaves A one facedown card."""
    loop = _loop()
    _control(loop, "A", 0)
    bf = loop.gs.battlefields[0]
    loop._deploy_gear("B", bf, CARD_REGISTRY["Bushwhack Trap"].instantiate())
    assert loop._facedown_capacity(bf) == 1


def test_the_coach_and_the_observation_see_both_facedown_cards():
    from riftbound.ai.coach import _board_extras, _card_ref
    from riftbound.core.decisions import Observation
    loop = _loop()
    _named_bf(loop, 0, "Bandle Tree")
    mine, theirs = _hidden_unit("Mine"), _hidden_unit("Theirs")
    loop.gs.battlefields[0].facedowns = [FacedownCard(card=mine, owner="A", turn_hidden=1),
                                         FacedownCard(card=theirs, owner="B", turn_hidden=1)]
    assert _board_extras(loop.gs, "A")["facedown_mine"] == {"0:0": "Mine"}
    assert _card_ref(loop.gs, "B", theirs) == "facedown:0:1"
    obs = Observation.from_state(loop.gs, "A")
    assert obs.battlefields[0].facedowns == ("A", "B")
