"""What the search may know about hidden cards (state.determinize).

Two holes found after the RiftAtlas games of 17/11 (docs/bot/GIUDIZI.md):
- a card the opponent knows is in a hand (a unit Star-Crossed returned there,
  a hand Sabotage revealed) was redealt like any unseen card;
- the world drawn depended on the order the unseen cards really lay in, so
  the search's choice could change when only that order changed.
"""
from __future__ import annotations

import random
from pathlib import Path

from riftbound.ai.net_mcts import NetGuidedMCTSAgent
from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.game_factory import build_game
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import FacedownCard, GameState, determinize

DECKS = Path(__file__).resolve().parent.parent / "riftbound" / "data" / "decks"


def _bare_game():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(8)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(8)]), rune_deck=RuneDeck([]))
    b.hand = [UnitCard(name=f"H{i}") for i in range(3)]
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return gs, a, b


def _ctx(loop, actor, opponent):
    return EffectContext(loop=loop, card=SpellCard(name="Test"),
                         actor=actor, opponent=opponent, battlefield=loop.gs.battlefields[0])


def _b_hands(gs, seeds=range(20)):
    out = []
    for seed in seeds:
        c = gs.clone()
        determinize(c, observer="A", rng=random.Random(seed))
        out.append([x.name for x in c.B.hand])
    return out


def test_a_unit_returned_to_hand_stays_known_to_the_opponent():
    """Star-Crossed returns the Kingpin to its owner's hand: from A's seat it
    stays in B's hand in every determinized world, in its slot; the rest of
    the hand is still redealt."""
    gs, a, b = _bare_game()
    kingpin = UnitInPlay(UnitCard(name="Kingpin", might=4))
    gs.battlefields[0].add_unit("B", kingpin)
    loop = GameLoop(gs)
    REGISTRY["recall_unit"](_ctx(loop, a, b), {"effect": "recall_unit", "target": "enemy_unit", "where": "anywhere"})
    assert [c.name for c in b.hand][-1] == "Kingpin"
    assert [c.name for c in b.hand_known()] == ["Kingpin"]
    hands = _b_hands(gs)
    assert all(h[-1] == "Kingpin" and len(h) == 4 for h in hands)
    assert len({tuple(h[:3]) for h in hands}) > 1     # the unknown slots move
    # B's own seat: its whole hand is known to it, nothing changes there.
    c = gs.clone()
    determinize(c, observer="B", rng=random.Random(0))
    assert [x.name for x in c.B.hand] == [x.name for x in b.hand]


def test_a_revealed_hand_stays_known_until_a_new_draw():
    """Sabotage: B reveals its hand, A recycles a non-unit card. The rest is
    known; a card B draws afterwards is not."""
    gs, a, b = _bare_game()
    b.hand.append(SpellCard(name="Rebuke"))
    loop = GameLoop(gs)
    REGISTRY["recycle_from_opponent_hand"](_ctx(loop, a, b),
                                           {"effect": "recycle_from_opponent_hand", "non_unit": True})
    assert [c.name for c in b.hand] == ["H0", "H1", "H2"]
    assert all(h == ["H0", "H1", "H2"] for h in _b_hands(gs))
    b.draw()
    hands = _b_hands(gs)
    assert all(h[:3] == ["H0", "H1", "H2"] for h in hands)
    assert len({h[3] for h in hands}) > 1


def test_a_known_card_that_comes_back_from_a_hidden_zone_is_unknown():
    """A known card hidden facedown and returned to hand by an effect: the
    opponent can't tell which card came back."""
    gs, a, b = _bare_game()
    card = b.hand[0]
    b.mark_hand_public([card])
    b.hand.remove(card)
    gs.battlefields[0].facedowns.append(FacedownCard(card=card, owner="B", turn_hidden=0))
    loop = GameLoop(gs)
    REGISTRY["return_friendly_to_hand"](_ctx(loop, b, a), {"effect": "return_friendly_to_hand"})
    assert any(c is card for c in b.hand)
    assert b.hand_known() == []


def _twin_with_hidden_order_changed(gs):
    """The same game, only the hidden order changed: A's deck below what A
    knows, B's deck, and which unseen cards sit in B's hand."""
    t = gs.clone()
    t.A.deck.cards.reverse()
    pool = t.B.hand + t.B.deck.cards
    random.Random(99).shuffle(pool)
    t.B.hand, t.B.deck.cards = pool[:len(t.B.hand)], pool[len(t.B.hand):]
    return t


def test_determinize_depends_only_on_what_the_observer_knows():
    gs, a, b = _bare_game()
    twin = _twin_with_hidden_order_changed(gs)
    assert [c.name for c in twin.A.deck.cards] != [c.name for c in gs.A.deck.cards]
    for seed in range(5):
        x, y = gs.clone(), twin.clone()
        determinize(x, observer="A", rng=random.Random(seed))
        determinize(y, observer="A", rng=random.Random(seed))
        for p in ("A", "B"):
            px, py = x.get_player(p), y.get_player(p)
            assert [c.name for c in px.hand] == [c.name for c in py.hand]
            assert [c.name for c in px.deck.cards] == [c.name for c in py.deck.cards]


class _BoardValue(NetGuidedMCTSAgent):
    """Uniform priors, the board as the value: no network needed."""

    def _evaluate(self, clone, side, legal_ga):
        return {a.to_engine(): 1.0 / len(legal_ga) for a in legal_ga}, self._net_value(clone, side)

    def _net_value(self, clone, side):
        from riftbound.core.effects import _position_value
        return max(-1.0, min(1.0, _position_value(clone, side) / 20))

    _value_only = _net_value


def _first_choice(gs):
    gs.A.agent = _BoardValue(gs.A, None, iterations=60, rng=random.Random(0))
    GameLoop(gs)
    act = gs.A.agent.decide_action(gs.B)
    return act, dict(gs.A.agent.last_visits)


def test_the_search_does_not_peek_at_hidden_order():
    """Test proposed by the outside review (chat of 17-18/11): change in
    secret the top of A's deck and B's hidden cards; with the same
    information and the same agent seed, the search's first choice and its
    visits stay the same. A holds The Good Stuff ("discard 1, then draw 3")
    and can pay for what it draws, so the search's lines draw from the deck:
    with the old determinize the visits changed in 7 seeds out of 8."""
    from riftbound.core.enums import Domain
    from riftbound.registry.cards_registry import CARD_REGISTRY
    gs = build_game(game_seed=3, deck_a_path=DECKS / "competitive_evelynn.json",
                    deck_b_path=DECKS / "competitive_khazix.json", ai_a=None, ai_b="simple_trade",
                    first_player="a", max_turns=40)
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()
    gs.A.hand = [CARD_REGISTRY["The Good Stuff"].instantiate()] + gs.A.hand[:2]
    gs.A.energy = 9
    for d in Domain:
        gs.A.add_power(d, 2)
    twin = _twin_with_hidden_order_changed(gs)
    assert twin.A.deck.cards[-1].name != gs.A.deck.cards[-1].name
    assert _first_choice(gs) == _first_choice(twin)
