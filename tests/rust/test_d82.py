"""D82 (docs/audit/AUDIT.md): a gear played from face down (Edge of Night, the
only non-unit `on_self_played`) triggers at the battlefield it was hidden at,
not at 0. Fixed in Rust on the profile 6427b90+D72-D82; 6427b90+D72-D81 keeps
the old behaviour (the unit at BF0). Position built in Python
(tests/audit/audit_helpers.py) and played on Rust."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import hide, setup, unit  # noqa: E402
from test_d72_d76 import events, option_names, rust, units  # noqa: E402

D72_D81 = "6427b90+D72-D81"
D72_D82 = "6427b90+D72-D82"
PLAY = "Play Edge of Night from Hidden"


def _game(regole, lane):
    """A: a unit at BF0 (Pit Rookie), one at BF1 (First Mate), Edge of Night face down at
    battlefield `lane`, playable now; seat A is a human callback playing it
    (default answers afterwards, then passing)."""
    import riftbound_rs
    loop, _a, _b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("Pit Rookie"))
    loop.gs.battlefields[1].add_unit("A", unit("First Mate"))
    hide(loop, "A", lane, "Edge of Night")
    g = rust(loop, regole)
    played = []

    def ask(ev):
        e = json.loads(ev)
        if e["k"] == "decision":
            hit = [i for i, m in enumerate(e["menu"]) if m.startswith(PLAY) and not played]
            if hit:
                played.append(1)
                return hit[0]
            return e["menu"].index("Pass")
        return e["default"]
    g.set_human_agent("A", ask)
    riftbound_rs.azzera_correzioni()
    before = {u["card"]: u["might"] for u in units(g)}
    g.run_segment(1)
    assert played
    return g, before


def _attached(game):
    """The units that carry Edge of Night (it gives +2 Might)."""
    g, before = game
    return sorted(u["card"] for u in units(g) if u["might"] == before[u["card"]] + 2)


def _offered(game):
    g, _ = game
    return [option_names(e) for e in events(g, "choice") if e["kind"].startswith("target")]


def test_d82_hidden_at_bf1_attaches_to_the_unit_at_bf1():
    import riftbound_rs
    g = _game(D72_D82, 1)
    assert _attached(g) == ["First Mate"]
    assert all(set(o) == {"First Mate"} for o in _offered(g))
    assert riftbound_rs.correzioni()["D82"] >= 1


def test_d72_d81_hidden_at_bf1_keeps_the_unit_at_bf0():
    import riftbound_rs
    g = _game(D72_D81, 1)
    assert _attached(g) == ["Pit Rookie"]
    assert all(set(o) == {"Pit Rookie"} for o in _offered(g))
    assert riftbound_rs.correzioni()["D82"] == 0


@pytest.mark.parametrize("regole", [D72_D81, D72_D82])
def test_hidden_at_bf0_is_the_same_on_both_profiles(regole):
    import riftbound_rs
    g = _game(regole, 0)
    assert _attached(g) == ["Pit Rookie"]
    assert all(set(o) == {"Pit Rookie"} for o in _offered(g))
    assert riftbound_rs.correzioni()["D82"] == 0
