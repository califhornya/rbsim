"""D78, D79, D80 (docs/audit/AUDIT.md): fixed in Rust on the profile
6427b90+D72-D80; 6427b90+D72-D77 keeps the old behaviour. Positions from the
audit, built in Python (tests/audit/audit_helpers.py) and played on Rust."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import card, hide, legend, setup, unit  # noqa: E402
from test_d72_d76 import events, rust  # noqa: E402

D72_D77 = "6427b90+D72-D77"
D72_D80 = "6427b90+D72-D80"


def _points(g):
    raw = g.raw_dump()
    return tuple(int(re.search(rf'"points_{s}":(\d+)', raw).group(1)) for s in "AB")


# -- D80: points after the winning one ---------------------------------------------

def _two_held_at_seven(regole):
    """B at 7/8 holds both battlefields; A passes; B's Beginning Phase scores."""
    loop, _a, _b = setup(active="A")
    loop.gs.points_A, loop.gs.points_B = 4, 7
    loop.gs.victory_score = 8
    for i in (0, 1):
        loop.gs.battlefields[i].add_unit("B", unit("First Mate"))
        loop.gs.battlefields[i].held_by = "B"
    return rust(loop, regole)


def test_d80_no_points_after_the_winning_one():
    import riftbound_rs
    g = _two_held_at_seven(D72_D80)
    riftbound_rs.azzera_correzioni()
    assert g.run_segment(1) == "B"
    assert _points(g) == (4, 8)
    assert riftbound_rs.correzioni()["D80"] >= 1


def test_d80_not_applied_on_the_d72_d77_profile():
    import riftbound_rs
    g = _two_held_at_seven(D72_D77)
    riftbound_rs.azzera_correzioni()
    assert g.run_segment(1) == "B"
    assert _points(g) == (4, 9)
    assert riftbound_rs.correzioni()["D80"] == 0
