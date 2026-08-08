"""GameState.clone() + determinize() — the primitives search (MCTS) builds on."""

from __future__ import annotations

import random
import time
from pathlib import Path

from riftbound.core.game_factory import build_game, make_agent
from riftbound.core.loop import GameLoop
from riftbound.core.state import determinize

REPO_ROOT = Path(__file__).resolve().parent.parent
PYKE = REPO_ROOT / "riftbound" / "data" / "decks" / "fury_chaos_pyke.json"
DIANA = REPO_ROOT / "riftbound" / "data" / "decks" / "chaos_mind_diana.json"


def _fresh(seed=1):
    return build_game(game_seed=seed, deck_a_path=PYKE, deck_b_path=DIANA, ai_a="pyke", ai_b="diana")


def _deal(gs, na=5, nb=5):
    for _ in range(na):
        gs.A.draw()
    for _ in range(nb):
        gs.B.draw()


def _public_sig(gs):
    return (
        gs.points_A, gs.points_B, gs.A.energy, gs.B.energy, gs.turn, gs.active,
        [c.name for c in gs.A.hand], [c.name for c in gs.B.hand],
        len(gs.A.deck.cards), len(gs.B.deck.cards),
        [[u.card.name for u in bf.units_A] for bf in gs.battlefields],
        [[u.card.name for u in bf.units_B] for bf in gs.battlefields],
    )


def test_clone_drops_agents():
    gs = _fresh()
    clone = gs.clone()
    assert clone.A.agent is None and clone.B.agent is None
    assert gs.A.agent is not None and gs.B.agent is not None  # original untouched


def test_clone_is_independent():
    gs = _fresh()
    _deal(gs)
    clone = gs.clone()

    # Mutate the clone hard; the original must not move.
    clone.A.energy = 999
    clone.points_A = 7
    clone.A.hand.clear()
    clone.battlefields[0].units_A.append(clone.B)  # nonsense mutation, just to perturb

    assert gs.A.energy != 999
    assert gs.points_A == 0
    assert len(gs.A.hand) == 5

    # And the reverse: mutating the original leaves the clone alone.
    gs2 = _fresh()
    c2 = gs2.clone()
    gs2.B.energy = 123
    assert c2.B.energy != 123


def test_clone_preserves_public_state():
    gs = _fresh()
    _deal(gs)
    clone = gs.clone()
    assert _public_sig(gs) == _public_sig(clone)


def test_clone_then_full_game_leaves_original_untouched():
    gs = _fresh(seed=42)
    before = _public_sig(gs)

    clone = gs.clone()
    clone.A.agent = make_agent("pyke", clone.A)
    clone.B.agent = make_agent("diana", clone.B)
    result = GameLoop(clone).start()  # heavy mutation of the clone

    assert result.winner in ("A", "B", "DRAW")
    assert _public_sig(gs) == before  # original is exactly as it was


def test_clone_benchmark():
    gs = _fresh()
    _deal(gs)
    n = 200
    t0 = time.perf_counter()
    for _ in range(n):
        gs.clone()
    per_ms = (time.perf_counter() - t0) / n * 1000
    # Generous ceiling — just guards against an accidental order-of-magnitude
    # regression (a full clone is ~1 ms locally). Printed for the record.
    print(f"\nclone: {per_ms:.3f} ms/clone")
    assert per_ms < 15.0


def test_determinize_preserves_counts_and_observer_info():
    gs = _fresh()
    _deal(gs, na=5, nb=6)
    clone = gs.clone()

    a_hand_before = sorted(c.name for c in clone.A.hand)
    b_pool_before = sorted(c.name for c in clone.B.hand + clone.B.deck.cards)
    a_pool_before = sorted(c.name for c in clone.A.hand + clone.A.deck.cards)
    b_hand_size = len(clone.B.hand)

    determinize(clone, observer="A", rng=random.Random(7))

    # Observer's own hand is known → untouched.
    assert sorted(c.name for c in clone.A.hand) == a_hand_before
    # Opponent hand size fixed; hidden pool multiset conserved (just reshuffled).
    assert len(clone.B.hand) == b_hand_size
    assert sorted(c.name for c in clone.B.hand + clone.B.deck.cards) == b_pool_before
    # Observer's own card multiset conserved as well (only deck order changes).
    assert sorted(c.name for c in clone.A.hand + clone.A.deck.cards) == a_pool_before


def test_determinize_can_randomize_opponent_hand():
    gs = _fresh()
    # Give B a big hand from a large deck so a reshuffle almost surely reorders it.
    _deal(gs, na=2, nb=10)
    before = [c.name for c in gs.B.hand]

    changed = False
    for seed in range(10):
        clone = gs.clone()
        determinize(clone, observer="A", rng=random.Random(seed))
        if [c.name for c in clone.B.hand] != before:
            changed = True
            break
    assert changed, "determinize never altered the opponent's hidden hand"
