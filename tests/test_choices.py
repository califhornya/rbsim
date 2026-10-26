"""GameLoop.choose: every choice the engine makes for a player (targets, modes,
"you may"s, the unit combat damage kills first...) can be seen and replaced by
a chooser; without one the baseline policy decides, unchanged."""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


class _Force:
    """Records each choice; takes option `j` for the choices named `kind`."""

    def __init__(self, kind=None, j=None):
        self.kind, self.j, self.seen = kind, j, []

    def __call__(self, loop, kind, side, options, default, source):
        self.seen.append((kind, side, len(options), default))
        return self.j if kind == self.kind else None


def _two_enemies(loop):
    bf = loop.gs.battlefields[0]
    first = UnitInPlay(UnitCard(name="First", might=2))
    second = UnitInPlay(UnitCard(name="Second", might=4))
    bf.add_unit("B", first)
    bf.add_unit("B", second)
    return bf, first, second


def test_no_chooser_keeps_the_baseline_pick():
    loop = _loop()
    bf, first, second = _two_enemies(loop)
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, bf)
    REGISTRY["kill_unit"](ctx, {"effect": "kill_unit", "target": "enemy_unit"})
    assert bf.units_B == [second]                # the first unit there


def test_chooser_sees_and_replaces_a_target():
    loop = _loop()
    bf, first, second = _two_enemies(loop)
    loop.chooser = _Force("target:kill_unit", 1)
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, bf)
    REGISTRY["kill_unit"](ctx, {"effect": "kill_unit", "target": "enemy_unit"})
    assert bf.units_B == [first]
    assert loop.chooser.seen == [("target:kill_unit", "A", 2, 0)]


def test_chooser_picks_a_mode():
    loop = _loop()
    loop.chooser = _Force("mode", 1)
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["mode_choice"](ctx, {"modes": [
        {"effect": "draw_cards", "count": 1},
        {"effect": "gain_energy", "amount": 5},
    ]})
    assert loop.gs.A.energy == 5


def test_combat_damage_order_is_asked_only_when_it_matters():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", UnitInPlay(UnitCard(name="Attacker", might=3)))
    small = UnitInPlay(UnitCard(name="Small", might=1))
    big = UnitInPlay(UnitCard(name="Big", might=3))
    bf.add_unit("B", small)
    bf.add_unit("B", big)
    loop.chooser = _Force("combat_damage_order", 1)      # A kills the 3 first
    bf.resolve_combat_might(attacker_side="A", **loop._combat_mods(bf, "A"))
    assert bf.units_B == [small]
    # B's 4 damage kills A's only unit whatever the order: no choice asked.
    assert [k for k, *_ in loop.chooser.seen] == ["combat_damage_order"]
    assert loop.chooser.seen[0][1] == "A"
