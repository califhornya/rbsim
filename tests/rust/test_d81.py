"""D81 (docs/audit/AUDIT.md): Call to Glory without the buff costs its printed
3 Energy, not 1 Power. Fixed in Rust on the profile 6427b90+D72-D81;
6427b90+D72-D80 keeps the old behaviour. Position from the audit, built in
Python (tests/audit/audit_helpers.py) and played on Rust."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import card, setup, unit  # noqa: E402
from riftbound.core.enums import Domain  # noqa: E402
from test_d72_d76 import _raw, events, rust, units  # noqa: E402

D72_D80 = "6427b90+D72-D80"
D72_D81 = "6427b90+D72-D81"
CAST = "Cast Call to Glory @BF0"


def _position(regole, energy, pick=None):
    """A: a buffed Trifarian Captain at BF0, Call to Glory in hand, `energy`
    ready Energy and 2 Power of every domain (a rune's worth). Seat A is a
    human callback casting the spell, taking option `pick` of the cost_extras
    choice (None: the default) and passing afterwards."""
    loop, a, _b = setup(active="A", rich=("B",))
    a.energy = energy
    for d in Domain:
        a.add_power(d, 2)
    cap = unit("Trifarian Captain")
    cap.might_counters = 1
    loop.gs.battlefields[0].add_unit("A", cap)
    a.hand.append(card("Call to Glory"))
    g = rust(loop, regole)
    asked = []

    def ask(ev):
        e = json.loads(ev)
        if e["k"] == "decision":
            return e["menu"].index(CAST if CAST in e["menu"] and not asked else "Pass")
        if e["kind"] == "cost_extras":
            asked.append(e)
            return e["default"] if pick is None else pick
        return e["default"]
    g.set_human_agent("A", ask)
    return g


def _options(e):
    """The cost_extras choice's options: [(extras, energy, power)]."""
    return [tuple(o["root"]["o"]) for o in e["options_raw"]]


def _extras_choice(g):
    return [e for e in events(g, "choice") if e["kind"] == "cost_extras"]


def _paid(g):
    """(ready Energy left, Power left in the pool, Captain's buffs, +Might it got) when the spell resolved."""
    t = [e for e in events(g, "choice") if e["kind"].startswith("target")][0]
    raw = _raw(t)
    p = raw["root"]["A"]["$v"]
    power = sum(n for _, n in p["power_pool"]["$dict"])
    cap = next(v for v in raw["objs"].values() if v.get("$t") == "UnitInPlay")
    return p["rune_energy"], power, cap["might_counters"]


@pytest.mark.parametrize("energy", [0, 3])
def test_d72_d80_keeps_the_option_priced_one_power(energy):
    g = _position(D72_D80, energy)
    g.run_segment(1)
    [e] = _extras_choice(g)
    opts = _options(e)
    assert len(opts) == 2
    assert opts[0] == ({"energy": 3, "power": 0, "buffs": 1}, 0, None)
    assert opts[1] == ({"energy": 3}, 0, 1)


def test_d81_no_energy_only_the_buff_option():
    import riftbound_rs
    g = _position(D72_D81, 0)
    riftbound_rs.azzera_correzioni()
    g.run_segment(1)
    opts = [o for e in _extras_choice(g) for o in _options(e)]
    assert len(opts) <= 1 and all(o[0].get("buffs") == 1 for o in opts)
    assert riftbound_rs.correzioni()["D81"] >= 1
    energy, power, buffs = _paid(g)
    assert (energy, power) == (0, 12) and buffs == 0  # the buff was spent, nothing else paid
    assert [u["buffs"] for u in units(g)] == [0]


def test_d81_with_energy_the_option_without_the_buff_costs_its_energy():
    g = _position(D72_D81, 3)
    g.run_segment(1)
    [e] = _extras_choice(g)
    opts = _options(e)
    assert len(opts) == 2
    assert opts[0] == ({"energy": 3, "power": 0, "buffs": 1}, 0, None)
    assert opts[1] == ({}, 3, None)  # 3 Energy, Power unchanged


def test_d81_casting_without_the_buff_pays_three_energy_and_keeps_it():
    g = _position(D72_D81, 3, pick=1)
    g.run_segment(1)
    energy, power, buffs = _paid(g)
    assert (energy, power, buffs) == (0, 12, 1)
    assert [u["buffs"] for u in units(g)] == [1]


def test_d81_casting_with_the_buff_is_free():
    g = _position(D72_D81, 3, pick=0)
    g.run_segment(1)
    assert _paid(g) == (3, 12, 0)
