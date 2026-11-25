"""D77 (open, to be fixed in Rust; docs/audit/AUDIT.md): a showdown staged by
the trigger of a Standard Move that is not held must run before the mover's
next action. Position from the audit, built in Python and played on the Rust
engine with the rules profile 6427b90+D72-D76."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import card, setup, unit  # noqa: E402
from test_d72_d76 import CORRETTE, events, rust  # noqa: E402


@pytest.mark.xfail(strict=True, reason="D77 aperto: da correggere in Rust")
def test_d77_showdown_staged_by_faefolk_trigger_precedes_the_next_action():
    """B moves Irresistible Faefolk to BF0 (B controls it); the trigger moves
    A's Gutter Guardian there. The showdown at BF0 happens before B's next
    action: B cannot play the gear Pillaged Armory (no ACTION) before it."""
    loop, _a, b = setup(active="B")
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("B", unit("Pit Rookie"))
    bf0.add_unit("B", unit("First Mate"))
    bf0.held_by = "B"
    loop.gs.battlefields[1].add_unit("A", unit("Gutter Guardian"))
    b.base_units.append(unit("Irresistible Faefolk"))
    b.hand.append(card("Pillaged Armory"))
    g = rust(loop, CORRETTE, B={"main": ["Move Irresistible Faefolk base→BF0", "Play gear Pillaged Armory"]})
    g.run_segment(1)
    ds = events(g, "decision")
    shows = [i for i, d in enumerate(ds) if d["point"] == "showdown_action"]
    assert shows, [(d["seat"], d["point"]) for d in ds]
    before = ds[1:shows[0]]                      # after the move's decision
    assert not any("Play gear Pillaged Armory" in m for d in before for m in d["menu"]), \
        [(d["seat"], d["point"]) for d in ds]
