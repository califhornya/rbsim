"""Win probe of the search bot (SearchCore.win_probe, opt-in): B at 6/8 with two
ready units in base and two empty battlefields wins this turn by Move X base->BF0,
Pass (commit, conquer), Move Y base->BF1, Pass (conquer, 8th point). The plain
42-iteration bot may miss it; without a win the probe changes nothing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import card, setup, unit  # noqa: E402
from test_d72_d76 import rust  # noqa: E402

D72_D77 = "6427b90+D72-D77"
SEEDS = range(10)


def _game(points_b=6, units=2, seed=0, probe=False, log=False):
    loop, _a, b = setup(active="B", rich=("B",))
    loop.gs.points_A, loop.gs.points_B = 4, points_b
    loop.gs.victory_score = 8
    for name in ("First Mate", "Pit Rookie")[:units]:
        b.base_units.append(unit(name))
    b.energy = 8                                   # wide root: ~3 playable cards besides the moves
    for name in ("Crackshot Corsair", "Sea Monkey", "Grim Resolve"):
        b.hand.append(card(name))
    g = rust(loop, D72_D77)
    g.set_search_agent("B", 42, seed, None, None, log)
    if probe:
        g.set_search_win_probe("B", True)
    return g


def _wins(**kw):
    n = 0
    for s in SEEDS:
        g = _game(seed=s, **kw)
        if g.run_segment(1) == "B":
            n += 1
    return n


def test_probe_wins_this_turn():
    assert _wins(probe=True) == len(SEEDS)
    g = _game(seed=0, probe=True, log=True)
    assert g.run_segment(1) == "B"
    assert '"vittoria"' in g.search_log("B")      # the probe found the line


def test_without_probe_report():
    n = _wins(probe=False)
    print(f"WITHOUT PROBE: {n}/{len(SEEDS)}")
    if n == len(SEEDS):
        return  # the uniform-prior bot finds it; the test only documents the probe


def _same_without_win(**kw):
    for s in SEEDS:
        outs = []
        for probe in (False, True):
            g = _game(seed=s, probe=probe, log=True, **kw)
            w = g.run_segment(1)
            outs.append((w, g.search_log("B"), json.dumps([(e.get("seat"), e.get("menu"), e.get("choice"))
                                                          for e in json.loads(g.events())
                                                          if e["k"] == "decision"])))
        assert outs[0] == outs[1], s
        assert '"vittoria"' not in outs[1][1]


def test_probe_changes_nothing_at_five_points():
    _same_without_win(points_b=5)


def test_probe_changes_nothing_with_one_unit():
    _same_without_win(units=1)
