"""The search's mulligan must not see the real order of its own deck (20/11,
external review: with boot1's net, changing only unseen deck cards changed the
mulligan in 22 openings of 32).

It used to send the cards back on the real deck (cloned) and only then
determinize, so the replacements were the real next cards. Now each world is
drawn first (determinize: the deck reshuffled, the hand kept), the same worlds
for every choice of cards, and the mulligan is played in them."""
import random
from pathlib import Path

from riftbound.ai.handwritten import HandwrittenAgent
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop

D = Path(__file__).resolve().parents[1] / "riftbound/data/decks"


class _HandValue(HandwrittenAgent):
    """A value that reads the hand's identities (as a net does)."""
    def _value_only(self, clone, side):
        hand = clone.get_player(side).hand
        return sum(len(c.name) % 7 for c in hand) / 100.0


def _values(deck_seed: int):
    gs = build_game(game_seed=5, deck_a_path=D / "competitive_evelynn.json",
                    deck_b_path=D / "competitive_khazix.json", ai_a=None, ai_b=None, max_turns=40)
    p = gs.A
    p.agent = _HandValue(p, rng=random.Random(1))
    GameLoop(gs)
    for _ in range(4):
        p.draw()
    # Only the unseen part changes: the deck below the opening hand, reordered.
    random.Random(deck_seed).shuffle(p.deck.cards)
    return p.agent.mulligan_values()


def test_mulligan_does_not_depend_on_the_real_deck_order():
    base = _values(0)
    assert len(base) > 1
    for s in (1, 2, 3):
        assert _values(s) == base
