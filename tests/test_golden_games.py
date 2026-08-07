"""Golden-game fixture — the parity oracle for the Step 2 pausable-engine work.

A fixed set of seeded agent-vs-agent games is run to completion and reduced to a
detailed end-state signature (winner, turns, points, per-zone counts, board unit
names). The signatures are frozen in ``tests/golden_games.json``. Any refactor of
the engine's control flow (making it pausable, driver-based, etc.) must keep this
byte-identical: if a signature drifts, the refactor changed observable behavior.

Regenerate intentionally with::

    RBSIM_REGEN_GOLDEN=1 uv run pytest tests/test_golden_games.py -q

Only regenerate when you *mean* to change behavior — never to "make it pass".
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop

REPO_ROOT = Path(__file__).resolve().parent.parent
_DECKS = REPO_ROOT / "riftbound" / "data" / "decks"
# Deck ids are stored relative in the fixture (portable); resolved via REPO_ROOT.
PYKE = Path("riftbound/data/decks/fury_chaos_pyke.json")
DIANA = Path("riftbound/data/decks/chaos_mind_diana.json")
YASUO = Path("riftbound/data/decks/calm_chaos_yasuo.json")

FIXTURE_PATH = Path(__file__).parent / "golden_games.json"


def _resolve_deck(rel: str) -> Path:
    return REPO_ROOT / rel

# (ai_a, deck_a, ai_b, deck_b, games) — seat-swapped matchups across all 3 decks
# and all 3 agents so the oracle exercises both seats and varied decision paths.
_MATCHUPS = [
    ("pyke", PYKE, "diana", DIANA, 4),
    ("diana", DIANA, "pyke", PYKE, 4),
    ("simple_trade", YASUO, "pyke", PYKE, 4),
    ("pyke", PYKE, "simple_trade", YASUO, 4),
    ("diana", DIANA, "simple_trade", YASUO, 4),
]

# Fixed master seed so the derived per-game seeds never move unless this changes.
_MASTER_SEED = 20260807


def _specs() -> list[dict]:
    """Deterministic list of game specs (matchup + per-game seed)."""
    import random

    base = random.Random(_MASTER_SEED)
    specs: list[dict] = []
    for ai_a, deck_a, ai_b, deck_b, n in _MATCHUPS:
        for k in range(n):
            specs.append(
                {
                    "id": f"{ai_a}:{deck_a.stem}__vs__{ai_b}:{deck_b.stem}#{k}",
                    "ai_a": ai_a,
                    "deck_a": str(deck_a),
                    "ai_b": ai_b,
                    "deck_b": str(deck_b),
                    "seed": base.randrange(1 << 30),
                }
            )
    return specs


def _bf_sig(bf) -> dict:
    return {
        "A": [u.card.name for u in bf.units_A],
        "B": [u.card.name for u in bf.units_B],
        "controller": bf.controller(),
        "last_controller": bf.last_controller,
    }


def _player_sig(p) -> dict:
    return {
        "hand": len(p.hand),
        "deck": len(p.deck.cards),
        "trash": len(p.trash),
        "banished": len(p.banished),
        "base_gear": len(p.base_gear),
        "base_units": [u.card.name for u in p.base_units],
        "energy": p.energy,
        "runes_in_play": p.total_runes_in_play(),
        "power_pool": {d.name: n for d, n in sorted(p.power_pool.items(), key=lambda kv: kv[0].name)},
    }


def _signature(spec: dict) -> dict:
    """Build + run one game to completion, reduce to a JSON-able signature."""
    gs = build_game(
        game_seed=spec["seed"],
        deck_a_path=_resolve_deck(spec["deck_a"]),
        deck_b_path=_resolve_deck(spec["deck_b"]),
        ai_a=spec["ai_a"],
        ai_b=spec["ai_b"],
    )
    result = GameLoop(gs).start()
    return {
        "winner": result.winner,
        "turns": result.turns,
        "units_played": result.units_played,
        "spells_cast": result.spells_cast,
        "points_A": gs.points_A,
        "points_B": gs.points_B,
        "xp_A": gs.xp_A,
        "xp_B": gs.xp_B,
        "final_active": gs.active,
        "battlefields": [_bf_sig(bf) for bf in gs.battlefields],
        "player_A": _player_sig(gs.A),
        "player_B": _player_sig(gs.B),
    }


def _generate() -> dict:
    return {spec["id"]: {"spec": spec, "signature": _signature(spec)} for spec in _specs()}


if os.environ.get("RBSIM_REGEN_GOLDEN"):
    # Regeneration mode: (re)write the fixture, then let the parity test confirm.
    FIXTURE_PATH.write_text(json.dumps(_generate(), indent=2, sort_keys=True) + "\n")


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="golden fixture not generated yet")
@pytest.mark.parametrize("game_id", [s["id"] for s in _specs()])
def test_golden_parity(game_id: str) -> None:
    """Each seeded game reproduces its frozen end-state signature exactly."""
    fixture = json.loads(FIXTURE_PATH.read_text())
    assert game_id in fixture, f"{game_id} missing from fixture — regenerate"
    expected = fixture[game_id]
    got = _signature(expected["spec"])
    assert got == expected["signature"]


def test_fixture_covers_all_specs() -> None:
    """The fixture must contain exactly the specs the suite declares."""
    if not FIXTURE_PATH.exists():
        pytest.skip("golden fixture not generated yet")
    fixture = json.loads(FIXTURE_PATH.read_text())
    assert sorted(fixture.keys()) == sorted(s["id"] for s in _specs())
