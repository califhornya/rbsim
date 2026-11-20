"""determinize and the rune decks (20/11, external review: over 32 worlds the
opponent's next rune always followed the real hidden order).

§108.5.d: the order of the runes in the Rune Deck is secret. The search now
reshuffles the runes nobody has seen, in both rune decks; the ones recycled to
the bottom stay in the order they came back (RuneDeck.unseen)."""
import random
from pathlib import Path

from riftbound.core.game_factory import build_game
from riftbound.core.state import determinize

D = Path(__file__).resolve().parents[1] / "riftbound/data/decks"


def _game():
    return build_game(game_seed=11, deck_a_path=D / "competitive_evelynn.json",
                      deck_b_path=D / "competitive_khazix.json", ai_a=None, ai_b=None, max_turns=40)


def _runes(gs, side):
    return [r.domain.name for r in gs.get_player(side).rune_deck.runes]


def test_worlds_do_not_depend_on_the_real_rune_order():
    gs = _game()
    other = gs.clone()
    for side in ("A", "B"):
        random.Random(side).shuffle(other.get_player(side).rune_deck.runes)
    assert any(_runes(gs, s) != _runes(other, s) for s in ("A", "B"))
    w1 = determinize(gs.clone(), observer="A", rng=random.Random(9))
    w2 = determinize(other.clone(), observer="A", rng=random.Random(9))
    for side in ("A", "B"):
        assert _runes(w1, side) == _runes(w2, side)


def test_the_runes_are_reshuffled_and_the_recycled_ones_stay():
    gs = _game()
    rd = gs.get_player("B").rune_deck
    n = len(rd.runes)
    drawn = [rd.draw(), rd.draw()]
    for r in drawn:
        rd.recycle(r)
    assert rd.unseen == n - 2
    bottom = _runes(gs, "B")[-2:]
    worlds = [_runes(determinize(gs.clone(), observer="A", rng=random.Random(s)), "B") for s in range(8)]
    assert len({tuple(w[:-2]) for w in worlds}) > 1          # the unseen top varies
    assert all(w[-2:] == bottom for w in worlds)             # the recycled bottom doesn't
    assert all(sorted(w) == sorted(_runes(gs, "B")) for w in worlds)
