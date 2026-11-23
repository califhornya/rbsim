"""Porting, prima consegna: D59, D59b e D62 (Gold) giocati dal motore Python
e da quello Rust danno tracce identiche e le stesse osservazioni. Richiede
l'estensione riftbound_rs (maturin develop --release in rust/rbsim-py): se
manca il test fallisce, non salta."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))
sys.path.insert(0, str(ROOT / "tests/audit"))


@pytest.mark.parametrize("case", ["D59", "D59b", "D62"])
def test_gold_python_rust(case):
    import riftbound_rs
    import consegna1 as c
    from diff_trace import FIELDS, canonical_rust_events, first_difference
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.trace_py import _unhook_deepcopy
    try:
        loop, tr, start_tree = c.run_python(case, traced=True)
    finally:
        _unhook_deepcopy()
    g = riftbound_rs.Game.from_canonical(rb.registry(), json.dumps(start_tree), 1)
    g.set_replay(json.dumps(tr.events), False, False)
    start_raw = json.loads(g.raw_dump())
    g.trace_on()
    g.run_segment(2)
    rs, rs_trees = canonical_rust_events(start_raw, json.loads(g.events()), json.loads(g.raw_dump()))
    py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    assert first_difference(py, rs, tr.states, rs_trees) is None
    obs = c.observations(case, py, tr.states)
    assert obs == c.observations(case, rs, rs_trees)
    assert obs["gold_eseguito"] is (case == "D62")
    if case == "D59":
        assert obs["finestra_conta_un_pass"] is False      # the showdown changed the fingerprint: "kept"
    elif case == "D59b":
        assert obs["finestra_conta_un_pass"] is True
    else:
        assert obs["B_di_nuovo_priorita_dopo_gold"] is False   # D62, as at 6427b90
