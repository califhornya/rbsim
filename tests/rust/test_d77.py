"""D77 (docs/audit/AUDIT.md): a showdown staged by the trigger of a Standard
Move that is not held must run before the mover's next action. Fixed in the
Rust profile 6427b90+D72-D77; 6427b90+D72-D76 keeps the old behaviour.
Position from the audit, built in Python and played on the Rust engine."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import card, setup, unit  # noqa: E402
from test_d72_d76 import CORRETTE, events, rust  # noqa: E402

D72_D77 = "6427b90+D72-D77"


def test_d77_showdown_staged_by_faefolk_trigger_precedes_the_next_action():
    """B moves Irresistible Faefolk to BF0 (B controls it); the trigger moves
    A's Gutter Guardian there. The showdown at BF0 happens before B's next
    action: B cannot play the gear Pillaged Armory (no ACTION) before it."""
    import riftbound_rs
    loop, _a, b = setup(active="B")
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("B", unit("Pit Rookie"))
    bf0.add_unit("B", unit("First Mate"))
    bf0.held_by = "B"
    loop.gs.battlefields[1].add_unit("A", unit("Gutter Guardian"))
    b.base_units.append(unit("Irresistible Faefolk"))
    b.hand.append(card("Pillaged Armory"))
    g = rust(loop, D72_D77, B={"main": ["Move Irresistible Faefolk base→BF0", "Play gear Pillaged Armory"]})
    riftbound_rs.azzera_correzioni()
    g.run_segment(1)
    ds = events(g, "decision")
    shows = [i for i, d in enumerate(ds) if d["point"] == "showdown_action"]
    assert shows, [(d["seat"], d["point"]) for d in ds]
    before = ds[1:shows[0]]                      # after the move's decision
    assert not any("Play gear Pillaged Armory" in m for d in before for m in d["menu"]), \
        [(d["seat"], d["point"]) for d in ds]
    assert riftbound_rs.correzioni()["D77"] >= 1


def test_d77_not_applied_on_the_d72_d76_profile():
    """The audit's state is kept on 6427b90+D72-D76: the staged showdown still
    waits and Pillaged Armory is still offered; the D77 counter stays 0."""
    import riftbound_rs
    loop, _a, b = setup(active="B")
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("B", unit("Pit Rookie"))
    bf0.add_unit("B", unit("First Mate"))
    bf0.held_by = "B"
    loop.gs.battlefields[1].add_unit("A", unit("Gutter Guardian"))
    b.base_units.append(unit("Irresistible Faefolk"))
    b.hand.append(card("Pillaged Armory"))
    g = rust(loop, CORRETTE, B={"main": ["Move Irresistible Faefolk base→BF0", "Play gear Pillaged Armory"]})
    riftbound_rs.azzera_correzioni()
    g.run_segment(1)
    ds = events(g, "decision")
    shows = [i for i, d in enumerate(ds) if d["point"] == "showdown_action"]
    first = shows[0] if shows else len(ds)
    assert any("Play gear Pillaged Armory" in m for d in ds[1:first] for m in d["menu"]), \
        [(d["seat"], d["point"]) for d in ds]
    assert riftbound_rs.correzioni()["D77"] == 0
