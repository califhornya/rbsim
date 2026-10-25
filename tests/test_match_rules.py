"""Match rules beyond the basic Bo3: sideboarding (Tournament Rules 403, 601.1.c),
turn order choice (407), the time limit (408.2) and best-of-5 battlefield reuse
(Core Rules §488.6.a)."""

from __future__ import annotations

import json
import warnings
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from riftbound.core.game_factory import build_game, registered_deck_config
from riftbound.core.match import (
    SideboardPlan,
    _game_result,
    apply_sideboard,
    available_battlefields,
    clock_turns,
    plan_sideboarder,
    play_match,
)
from riftbound.registry.cards_registry import load_deck_json, load_sideboard_json

REPO = Path(__file__).resolve().parent.parent
DECKS = REPO / "riftbound" / "data" / "decks"
KENNEN = DECKS / "vendetta_kennen.json"
ORNN = DECKS / "vendetta_ornn.json"
ORNN_LEGEND = "Ornn Fire Below the Mountain"

SIDEBOARD = [{"name": "Wind Wall", "count": 2}, {"name": "Switcheroo", "count": 1},
             {"name": "Kennen Keeper of Balance", "count": 1}]
VS_ORNN = {"in": {"Wind Wall": 2}, "out": {"Lightning Rush": 2}}


@pytest.fixture(autouse=True)
def _quiet_banned_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _kennen_with(tmp_path: Path, **extra) -> Path:
    data = json.loads(KENNEN.read_text(encoding="utf-8"))
    data.update(extra)
    path = tmp_path / "kennen_sb.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- deck format -------------------------------------------------------------

def test_sideboard_loads_with_plans(tmp_path):
    path = _kennen_with(tmp_path, sideboard=SIDEBOARD, sideboard_plans={ORNN_LEGEND: VS_ORNN})
    load_deck_json(path)
    sideboard, plans = load_sideboard_json(path)
    assert sideboard == {"Wind Wall": 2, "Switcheroo": 1, "Kennen Keeper of Balance": 1}
    assert plans[ORNN_LEGEND]["in"] == {"Wind Wall": 2}
    assert registered_deck_config(path).sideboard.count("Wind Wall") == 2


def test_sideboard_over_ten_cards_rejected(tmp_path):
    path = _kennen_with(tmp_path, sideboard=[{"name": "Wind Wall", "count": 3},
                                             {"name": "Flash", "count": 2},
                                             {"name": "Hard Bargain", "count": 2},
                                             {"name": "Star-Crossed", "count": 2},
                                             {"name": "Tideturner", "count": 2}])
    with pytest.raises(ValueError, match="maximum is 10"):
        load_deck_json(path)


def test_copy_limit_counts_main_deck_and_sideboard(tmp_path):
    # Ride the Wind is already a 3-of in the main deck.
    path = _kennen_with(tmp_path, sideboard=[{"name": "Ride the Wind", "count": 1}])
    with pytest.raises(ValueError, match="across main deck and sideboard"):
        load_deck_json(path)


def test_plan_must_be_one_for_one_and_from_the_sideboard(tmp_path):
    uneven = _kennen_with(tmp_path, sideboard=SIDEBOARD,
                          sideboard_plans={"*": {"in": {"Wind Wall": 2}, "out": {"Lightning Rush": 1}}})
    with pytest.raises(ValueError, match="not 1 for 1"):
        load_deck_json(uneven)
    missing = _kennen_with(tmp_path, sideboard=SIDEBOARD,
                           sideboard_plans={"*": {"in": {"Flash": 1}, "out": {"Lightning Rush": 1}}})
    with pytest.raises(ValueError, match="sideboard has 0"):
        load_deck_json(missing)


# --- applying a plan ---------------------------------------------------------

def test_apply_sideboard_swaps_in_place(tmp_path):
    reg = registered_deck_config(_kennen_with(tmp_path, sideboard=SIDEBOARD))
    deck = apply_sideboard(reg, SideboardPlan(ins={"Wind Wall": 2}, outs={"Lightning Rush": 2}))
    assert len(deck.main) == len(reg.main) == 39
    main = Counter(deck.main)
    assert main["Wind Wall"] == 2 and main["Lightning Rush"] == 1
    assert Counter(deck.sideboard)["Lightning Rush"] == 2 and "Wind Wall" not in deck.sideboard
    # Untouched cards keep their positions.
    first_rush = reg.main.index("Lightning Rush")
    assert deck.main[first_rush] == "Wind Wall"
    assert [a for a, b in zip(reg.main, deck.main) if a != b] == ["Lightning Rush"] * 2


def test_champion_can_change_to_a_sideboard_card(tmp_path):
    reg = registered_deck_config(_kennen_with(tmp_path, sideboard=SIDEBOARD))
    deck = apply_sideboard(reg, SideboardPlan(champion="Kennen Keeper of Balance"),
                           legend="Kennen Heart of the Tempest")
    assert deck.champion == "Kennen Keeper of Balance"
    assert "Kennen Storm of Shuriken" in deck.sideboard
    assert deck.main == reg.main


def test_illegal_plans_raise(tmp_path):
    reg = registered_deck_config(_kennen_with(tmp_path, sideboard=SIDEBOARD))
    with pytest.raises(ValueError, match="not in the sideboard"):
        apply_sideboard(reg, SideboardPlan(ins={"Flash": 1}, outs={"Lightning Rush": 1}))
    with pytest.raises(ValueError, match="not a champion"):
        apply_sideboard(reg, SideboardPlan(champion="Wind Wall"))
    with pytest.raises(ValueError, match="doesn't match the legend"):
        apply_sideboard(reg, SideboardPlan(champion="Ornn Blacksmith"),
                        legend="Kennen Heart of the Tempest")


def test_build_game_plays_the_sideboarded_list(tmp_path):
    path = _kennen_with(tmp_path, sideboard=SIDEBOARD)
    reg = registered_deck_config(path)
    deck = apply_sideboard(reg, SideboardPlan(ins={"Wind Wall": 2}, outs={"Lightning Rush": 2}))
    gs = build_game(game_seed=1, deck_a_path=path, deck_b_path=ORNN, ai_a=None, ai_b=None,
                    deck_a=deck)
    names = Counter(c.name for c in gs.A.deck.cards)
    assert names["Wind Wall"] == 2 and names["Lightning Rush"] == 1
    # An unchanged config builds exactly the game the file would.
    same = build_game(game_seed=1, deck_a_path=path, deck_b_path=ORNN, ai_a=None, ai_b=None,
                      deck_a=reg)
    plain = build_game(game_seed=1, deck_a_path=path, deck_b_path=ORNN, ai_a=None, ai_b=None)
    assert [c.name for c in same.A.deck.cards] == [c.name for c in plain.A.deck.cards]


# --- the match ---------------------------------------------------------------

def test_no_sideboarding_before_game_one_then_plan_applies(tmp_path):
    path = _kennen_with(tmp_path, sideboard=SIDEBOARD, sideboard_plans={ORNN_LEGEND: VS_ORNN})
    res = play_match(path, ORNN, "simple_trade", "simple_trade", seed=3,
                     sideboarder=plan_sideboarder(path, ORNN))
    assert len(res.games) >= 2
    assert res.games[0].sideboard_a is None
    assert res.games[1].sideboard_a.ins == {"Wind Wall": 2}
    assert res.games[1].sideboard_b is None          # Ornn's deck has no plans


def test_sideboarder_sees_opponent_legend_and_history(tmp_path):
    seen = []

    def spy(ctx):
        seen.append((ctx.side, ctx.game_index, ctx.opponent_legend, len(ctx.games)))
        return None

    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=3, sideboarder=spy)
    first_calls = [s for s in seen if s[1] == 1]
    assert ("A", 1, ORNN_LEGEND, 1) in first_calls
    assert all(s[1] >= 1 for s in seen)              # never asked before game 1
    assert len(seen) == 2 * (len(res.games) - 1)


def test_time_running_out_ends_the_match():
    calls = []
    # Victory is out of reach, so game 1 runs out of time: 2 turns on the clock,
    # then the 3 extra turns (TR 408.2.a), and no game 2.
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=5,
                     victory_score=50, time_limit_minutes=2, minutes_per_turn=1,
                     sideboarder=lambda ctx: calls.append(ctx) or None)
    assert len(res.games) == 1 and calls == []
    g = res.games[0]
    assert g.timed_out and g.turns == 2 + 3
    lead = g.points_a - g.points_b
    assert g.winner == ("A" if lead >= 2 else "B" if lead <= -2 else "DRAW")
    assert res.winner == g.winner


def test_sixty_minutes_is_forty_five_turns():
    assert clock_turns(60) == 45


def test_clock_runs_across_the_whole_match():
    for seed in range(6):
        res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=seed,
                         time_limit_minutes=25, minutes_per_turn=1)
        assert sum(g.turns for g in res.games) <= 25 + 3
        assert not any(g.timed_out for g in res.games[:-1])
        # Either someone clinched, or the clock stopped the match.
        assert max(res.wins_A, res.wins_B) == 2 or res.games[-1].timed_out \
            or sum(g.turns for g in res.games) >= 25


def test_stalled_game_counts_as_time_running_out():
    # The per-game stall guard is reached at turn 1: treated like the clock.
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=5,
                     max_turns=1, victory_score=50)
    assert len(res.games) == 1 and res.games[0].timed_out
    assert res.winner == "DRAW" and res.wins_A == res.wins_B == 0


def test_order_chooser_can_play_last():
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=3,
                     order_chooser=lambda side, i: False)
    for prev, cur in zip(res.games, res.games[1:]):
        if prev.winner in ("A", "B"):
            # The loser chose to play last, so the winner goes first.
            assert cur.first_player == prev.winner


def test_choosing_a_used_battlefield_raises():
    used = []

    def stubborn(side, available, game_index):
        if side == "A" and used:
            return used[0]
        pick = available[0]
        if side == "A":
            used.append(pick)
        return pick

    with pytest.raises(ValueError, match="not available"):
        play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=3, bf_chooser=stubborn)


def test_time_out_needs_a_two_point_lead():
    def outcome(a, b):
        gs = SimpleNamespace(points_A=a, points_B=b, victory_score=8)
        return _game_result(gs, SimpleNamespace(winner="?"))
    assert outcome(5, 4) == ("DRAW", True)
    assert outcome(6, 4) == ("A", True)
    assert outcome(2, 7) == ("B", True)
    assert outcome(8, 7) == ("?", False)             # a real win stands


def test_best_of_five_battlefield_reuse():
    pool = ["X", "Y", "Z"]
    assert available_battlefields(pool, {}) == pool
    assert available_battlefields(pool, {"X": 1}) == ["Y", "Z"]
    # All three played once: each may come back...
    assert available_battlefields(pool, {"X": 1, "Y": 1, "Z": 1}) == pool
    # ...but at most twice.
    assert available_battlefields(pool, {"X": 2, "Y": 1, "Z": 1}) == ["Y", "Z"]


def test_best_of_five_runs_to_three_wins():
    res = play_match(KENNEN, ORNN, "simple_trade", "simple_trade", seed=2, best_of=5,
                     time_limit_minutes=None)
    if res.winner in ("A", "B"):
        assert max(res.wins_A, res.wins_B) == 3
    counts = Counter(g.bf_a for g in res.games if g.winner != "DRAW")
    assert max(counts.values()) <= 2
