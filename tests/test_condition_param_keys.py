"""Regression tests for the condition-threshold param-key drift bug.

The corpus writes a conditioned effect's numeric threshold under inconsistent
keys (`amount` 26×, `n` 9×), but the engine's `_check_condition` reads `n`. A
gate like `{"amount": 4}` was therefore read as threshold 0 ("always true"),
silently disabling ~20 cards' gates. The loader now canonicalizes any alias to
`n`, and `_check_condition` reads through the alias list defensively.
"""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import EffectSpec


def make_loop() -> GameLoop:
    rng = random.Random(1)
    a = Player(name="A", deck=Deck([]))
    b = Player(name="B", deck=Deck([]))
    gs = GameState(rng=rng, A=a, B=b)
    gs.battlefields = [Battlefield(), Battlefield()]
    return GameLoop(gs)


# --- Loader canonicalization -------------------------------------------------

def test_from_dict_copies_amount_to_n():
    spec = EffectSpec.from_dict({
        "effect": "draw",
        "condition": {"type": "controller_has_xp_at_least", "params": {"amount": 3}},
    })
    assert spec.condition["params"]["n"] == 3
    # original key preserved (additive)
    assert spec.condition["params"]["amount"] == 3


def test_from_dict_prefers_existing_n():
    spec = EffectSpec.from_dict({
        "effect": "draw",
        "condition": {"type": "controller_has_xp_at_least", "params": {"n": 5, "amount": 99}},
    })
    assert spec.condition["params"]["n"] == 5


def test_from_dict_other_aliases():
    for alias in ("count", "value", "threshold"):
        spec = EffectSpec.from_dict({
            "effect": "draw",
            "condition": {"type": "card_in_trash_count_at_least", "params": {alias: 4}},
        })
        assert spec.condition["params"]["n"] == 4, alias


def test_from_dict_ignores_bool_and_missing():
    # No numeric threshold present -> no spurious `n`.
    spec = EffectSpec.from_dict({
        "effect": "draw",
        "condition": {"type": "friendly_unit_died_this_turn", "params": {"who": "self"}},
    })
    assert "n" not in spec.condition["params"]
    # bool is not a threshold
    spec2 = EffectSpec.from_dict({
        "effect": "draw",
        "condition": {"type": "controller_has_xp_at_least", "params": {"amount": True}},
    })
    assert "n" not in spec2.condition["params"]


# --- Engine parity: `amount` behaves identically to `n` ----------------------

def _spec(ctype: str, key: str, val: int) -> EffectSpec:
    return EffectSpec.from_dict({
        "effect": "draw",
        "condition": {"type": ctype, "params": {key: val}},
    })


def test_controller_has_xp_at_least_parity():
    loop = make_loop()
    loop.gs.xp_A = 3
    for key in ("amount", "n"):
        cond = _spec("controller_has_xp_at_least", key, 3).condition
        assert loop._check_condition(cond, None, loop.gs.A, loop.gs.B, None) is True
        cond4 = _spec("controller_has_xp_at_least", key, 4).condition
        assert loop._check_condition(cond4, None, loop.gs.A, loop.gs.B, None) is False


def test_you_have_n_or_more_units_here_parity():
    loop = make_loop()
    bf = Battlefield()
    bf.units_A = [object(), object(), object(), object()]  # 4 units; len is all that matters
    extra = {"battlefield": bf}
    for key in ("amount", "n"):
        cond4 = _spec("you_have_n_or_more_units_here", key, 4).condition
        assert loop._check_condition(cond4, None, loop.gs.A, loop.gs.B, extra) is True
        cond5 = _spec("you_have_n_or_more_units_here", key, 5).condition
        assert loop._check_condition(cond5, None, loop.gs.A, loop.gs.B, extra) is False


def test_spell_cost_at_least_parity():
    loop = make_loop()
    extra = {"triggering_spell_cost": 5}
    for key in ("amount", "n"):
        cond = _spec("spell_cost_at_least", key, 5).condition
        assert loop._check_condition(cond, None, loop.gs.A, loop.gs.B, extra) is True
        cond6 = _spec("spell_cost_at_least", key, 6).condition
        assert loop._check_condition(cond6, None, loop.gs.A, loop.gs.B, extra) is False


def test_you_played_n_spells_this_turn_parity():
    loop = make_loop()
    loop.gs.spells_played_this_turn["A"] = 2
    for key in ("amount", "n"):
        cond = _spec("you_played_n_spells_this_turn", key, 2).condition
        assert loop._check_condition(cond, None, loop.gs.A, loop.gs.B, None) is True
        cond3 = _spec("you_played_n_spells_this_turn", key, 3).condition
        assert loop._check_condition(cond3, None, loop.gs.A, loop.gs.B, None) is False


def test_card_in_trash_count_at_least_parity():
    loop = make_loop()
    loop.gs.A.trash = [object(), object(), object()]
    for key in ("amount", "n"):
        cond = _spec("card_in_trash_count_at_least", key, 3).condition
        assert loop._check_condition(cond, None, loop.gs.A, loop.gs.B, None) is True
        cond4 = _spec("card_in_trash_count_at_least", key, 4).condition
        assert loop._check_condition(cond4, None, loop.gs.A, loop.gs.B, None) is False


def test_score_within_n_of_victory_parity():
    loop = make_loop()
    loop.gs.victory_score = 8
    loop.gs.points_A = 6  # within 2 of victory
    for key in ("amount", "n"):
        cond = _spec("score_within_n_of_victory", key, 2).condition
        assert loop._check_condition(cond, None, loop.gs.A, loop.gs.B, None) is True
        cond1 = _spec("score_within_n_of_victory", key, 1).condition
        assert loop._check_condition(cond1, None, loop.gs.A, loop.gs.B, None) is False


def test_garen_gate_now_real():
    """End-to-end: Garen's `amount: 4` gate is a real threshold, not always-true."""
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get("Garen Might of Demacia")
    assert spec is not None
    gated = [e for e in spec.effects
             if isinstance(e.condition, dict)
             and e.condition.get("type") == "you_have_n_or_more_units_here"]
    assert gated, "expected Garen to have the units-here gate"
    assert gated[0].condition["params"]["n"] == 4
