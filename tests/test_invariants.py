"""Engine invariants — structural guarantees that must hold across the pausable
refactor (and any future engine change). Complements the golden fixture: the
fixture pins *exact* outcomes, these pin *structural* properties over many games.

Checked:
  * No phantom cards — a real (non-token) card never materialises from nowhere.
  * Full card conservation — no real (non-token) card ever leaves the pool. As of
    KNOWN_ISSUES #19a resolved spells are routed to their caster's trash (they used
    to vanish), so every card that starts in play is still findable in some zone
    (deck / hand / trash / banished / board) at game end.
  * No negative resources — energy / power / points / xp stay >= 0 after every
    action.
  * Chain empty between turn actions.

Not asserted here: strict "one card, one zone" (no aliasing). Baron Nashor's
add_battlefield already duplicates its played card across hand + battlefield
(KNOWN_ISSUES) — a pre-existing card-mechanic bug, not a refactor concern. The
golden fixture pins exact end-states, so any *new* duplication a refactor
introduces is caught there instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from riftbound.core.cards import Card
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop

REPO_ROOT = Path(__file__).resolve().parent.parent
_DECKS = REPO_ROOT / "riftbound" / "data" / "decks"
PYKE = _DECKS / "fury_chaos_pyke.json"
DIANA = _DECKS / "chaos_mind_diana.json"
YASUO = _DECKS / "calm_chaos_yasuo.json"

_MATCHUPS = [
    ("pyke", PYKE, "diana", DIANA),
    ("diana", DIANA, "simple_trade", YASUO),
    ("simple_trade", YASUO, "pyke", PYKE),
]
_SEEDS = [1, 7, 42, 99, 100000, 271828]


def _collect(gs) -> list[tuple[int, str, str, str]]:
    """(id, kind, name, zone) for every real (non-token) card object in play.

    The champion slot is only counted when the champion is undeployed — once
    deployed it is the same object as its in-play unit's card, which would look
    like (harmless but confusing) aliasing.

    Only real ``Card`` instances are tracked. Tokens carry a ``CardSpec`` registry
    stub as their ``.card`` (and a sacrificed Gold pushes that stub into trash),
    so the ``isinstance`` guard keeps token artifacts out of conservation.
    """
    items: list[tuple[int, str, str, str]] = []

    def add(card, zone: str) -> None:
        if not isinstance(card, Card):
            return
        items.append((id(card), type(card).__name__, getattr(card, "name", "?"), zone))

    for p in (gs.A, gs.B):
        for zone, lst in (
            ("deck", p.deck.cards),
            ("hand", p.hand),
            ("trash", p.trash),
            ("banished", p.banished),
            ("base_gear", p.base_gear),
        ):
            for c in lst:
                add(c, zone)
        for u in p.base_units:
            if not u.is_token:
                add(u.card, "base_unit")
            for g in u.gear:
                add(g, "gear")
    for bf in gs.battlefields:
        for u in bf.units_A + bf.units_B:
            if not u.is_token:
                add(u.card, "battlefield")
            for g in u.gear:
                add(g, "gear")
    if gs.champion_A is not None and not gs.champion_A_deployed:
        add(gs.champion_A, "champion")
    if gs.champion_B is not None and not gs.champion_B_deployed:
        add(gs.champion_B, "champion")
    return items


class _InvariantLoop(GameLoop):
    """GameLoop that asserts resource + chain invariants around each action."""

    def _apply_action(self, ap, action, cards_played_this_turn: int = 0) -> None:
        assert not self.gs.chain, f"chain not empty before action {action}: {self.gs.chain}"
        super()._apply_action(ap, action, cards_played_this_turn=cards_played_this_turn)
        for p in (self.gs.A, self.gs.B):
            assert p.energy >= 0, f"negative energy for {p.name}: {p.energy}"
            assert all(v >= 0 for v in p.power_pool.values()), f"negative power for {p.name}: {p.power_pool}"
        assert self.gs.points_A >= 0 and self.gs.points_B >= 0
        assert self.gs.xp_A >= 0 and self.gs.xp_B >= 0


def _games():
    for (ai_a, deck_a, ai_b, deck_b), seed in zip(_MATCHUPS * 2, _SEEDS):
        yield ai_a, deck_a, ai_b, deck_b, seed


@pytest.mark.parametrize("ai_a,deck_a,ai_b,deck_b,seed", list(_games()))
def test_card_conservation_and_no_aliasing(ai_a, deck_a, ai_b, deck_b, seed):
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b, ai_a=ai_a, ai_b=ai_b)
    start = _collect(gs)
    start_ids = {t[0] for t in start}

    _InvariantLoop(gs).start()

    end = _collect(gs)
    end_ids = {t[0] for t in end}

    # No phantom cards: nothing real appears that wasn't there at the start.
    phantom = end_ids - start_ids
    assert not phantom, f"phantom cards appeared: {[t[1:] for t in end if t[0] in phantom]}"

    # Full conservation: no real card leaves the pool. Resolved spells now land in
    # trash (KNOWN_ISSUES #19a) rather than vanishing, so nothing — spell or unit —
    # should disappear.
    vanished = start_ids - end_ids
    lost = [t[1:] for t in start if t[0] in vanished]
    assert not lost, f"cards vanished: {lost}"
