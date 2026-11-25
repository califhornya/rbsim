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
from test_d72_d76 import events, rust, units  # noqa: E402

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


# -- D79: a face-down play outside a task splits its triggers ------------------------

def _stranger_at_a_showdown(regole, name="Bedeviling Stranger"):
    """B's turn: Kingpin moves to BF0, where A holds 3 units and the Stranger
    is face down since an earlier turn (4 units there in all); in the showdown
    A plays the Stranger from face down. Evelynn's legend is A's."""
    loop, a, _b = setup(active="B")
    loop.gs.turn = 6
    legend(loop, "A", "Evelynn Agony's Embrace")
    for _ in range(3):
        a.deck.cards.append(card("Pit Rookie"))
    hide(loop, "A", 0, name)
    bf0 = loop.gs.battlefields[0]
    for n in ("Pit Rookie", "First Mate", "Sea Monkey"):
        bf0.add_unit("A", unit(n))
    bf0.held_by = "A"
    loop.gs.battlefields[1]  # BF1 stays empty
    _b.base_units.append(unit("Sett Kingpin"))
    return rust(loop, regole, B={"main": ["Move Sett Kingpin base→BF0"]},
                A={"showdown": [f"Play {name} from Hidden"]})


def _chain_at_first_reaction(g, abilities=False):
    """The chain's length where A is first asked to respond after the play
    (with `abilities`: which items are abilities, bottom first)."""
    g.run_segment(1)
    d = next(d for d in events(g, "decision") if d["point"] == "reaction")
    raw = json.loads(d["state_raw"]) if isinstance(d["state_raw"], str) else d["state_raw"]
    root = raw["root"]
    chain = (raw["objs"][root["$ref"]] if "$ref" in root else root)["chain"]
    return [x["$v"]["ability"] is not None for x in chain] if abilities else len(chain)


def test_d79_play_from_face_down_puts_its_triggers_on_the_chain_together():
    import riftbound_rs
    g = _stranger_at_a_showdown(D72_D80)
    riftbound_rs.azzera_correzioni()
    assert _chain_at_first_reaction(g) == 2        # the Stranger's ability and the legend's
    assert riftbound_rs.correzioni()["D79"] >= 1


def test_d79_not_applied_on_the_d72_d77_profile():
    import riftbound_rs
    g = _stranger_at_a_showdown(D72_D77)
    riftbound_rs.azzera_correzioni()
    assert _chain_at_first_reaction(g) == 1        # the Stranger's ability alone: the legend triggers after it
    assert riftbound_rs.correzioni()["D79"] == 0


def test_d79_face_down_spell_is_on_the_chain_under_the_legend_trigger():
    """The audit's face-down spell case: Sprite Call. Before, the legend's
    trigger ran before the spell was put on the chain; now the spell is there
    and the trigger goes on top of it, as from the Main Phase."""
    g = _stranger_at_a_showdown(D72_D80, "Sprite Call")
    assert _chain_at_first_reaction(g, abilities=True) == [False, True]
    g = _stranger_at_a_showdown(D72_D77, "Sprite Call")
    assert _chain_at_first_reaction(g, abilities=True) == [True]


# -- D78: "can't move this turn" ignored by effect moves ------------------------------

def _kingpin_and_showstopper(regole):
    """A's Vex Apathetic is at BF1. B plays Sett Kingpin to base (Vex stuns it:
    it can't move this turn), then casts Showstopper on it ("Buff a friendly
    unit in your base, then move it to a battlefield")."""
    loop, _a, b = setup(active="B")
    loop.gs.turn = 6
    loop.gs.battlefields[1].add_unit("A", unit("Vex Apathetic"))
    loop.gs.battlefields[1].held_by = "A"
    b.hand.append(card("Sett Kingpin"))
    b.hand.append(card("Showstopper"))
    return rust(loop, regole, B={"main": ["Play Sett Kingpin", "Cast Showstopper"]})


def _showdowns_after_the_spell(g):
    """Showdown decisions (Kingpin moved to a battlefield: it is contested)
    and Kingpin's buffs."""
    g.run_segment(1)
    ds = events(g, "decision")
    k = next(u for u in units(g) if u["card"] == "Sett Kingpin")
    return sum(d["point"] == "showdown_action" for d in ds), k["buffs"]


def test_d78_effect_move_is_negated_on_a_unit_that_cant_move_this_turn():
    import riftbound_rs
    g = _kingpin_and_showstopper(D72_D80)
    riftbound_rs.azzera_correzioni()
    showdowns, buffs = _showdowns_after_the_spell(g)
    assert (showdowns, buffs) == (0, 1)            # buffed, the move negated: no showdown
    assert riftbound_rs.correzioni()["D78"] >= 1


def test_d78_not_applied_on_the_d72_d77_profile():
    import riftbound_rs
    g = _kingpin_and_showstopper(D72_D77)
    riftbound_rs.azzera_correzioni()
    showdowns, buffs = _showdowns_after_the_spell(g)
    assert showdowns >= 1 and buffs == 1           # the move still happens
    assert riftbound_rs.correzioni()["D78"] == 0


def _hunker_down_then_showstopper(regole):
    """B's own restriction: Hunker Down ("It can't move this turn") on First
    Mate in base, then Showstopper on it."""
    loop, _a, b = setup(active="B")
    loop.gs.turn = 6
    b.base_units.append(unit("First Mate"))
    b.hand.append(card("Hunker Down"))
    b.hand.append(card("Showstopper"))
    return rust(loop, regole, B={"main": ["Cast Hunker Down", "Cast Showstopper"]})


def test_d78_hunker_down_uses_the_same_restriction():
    g = _hunker_down_then_showstopper(D72_D80)
    g.run_segment(1)
    assert next(u for u in units(g) if u["card"] == "First Mate")["where"] == "base"
    g = _hunker_down_then_showstopper(D72_D77)
    g.run_segment(1)
    assert next(u for u in units(g) if u["card"] == "First Mate")["where"] != "base"


def _void_assault_on_enemy(regole, restricted_by):
    """A (Kha'Zix) casts Void Assault: its friendly unit and B's unit swap
    battlefields... B's First Mate sits at BF1 with "can't move this turn" set
    (`restricted_by`: "vex" = cant_move_turn only, what Vex Apathetic sets)."""
    loop, a, b = setup(active="A")
    loop.gs.turn = 6
    legend(loop, "A", "Kha'Zix Voidreaver")
    a.base_units.append(unit("Sett Kingpin"))
    enemy = unit("First Mate")
    enemy.cant_move_turn = loop.gs.turn
    loop.gs.battlefields[1].add_unit("B", enemy)
    a.hand.append(card("Void Assault"))
    return rust(loop, regole, A={"main": ["Cast Void Assault"]})


def test_d78_vex_restriction_binds_only_its_unit_controller():
    g = _void_assault_on_enemy(D72_D80, "vex")
    g.run_segment(1)
    fm = next(u for u in units(g) if u["card"] == "First Mate")
    assert fm["where"] == "base"                   # A's own effect moved B's Vex-stunned unit
