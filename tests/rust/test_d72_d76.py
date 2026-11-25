"""D72-D76 corrected in Rust on the rules profile 6427b90+D72-D76 (decisions
of 25/11; docs/audit/AUDIT.md, "Deviations after the freeze"). Each from the
audit's minimal position, built in Python (tests/audit/audit_helpers.py),
imported into Rust from the canonical state and played by scripted seats.
The first decision or state that changes is measured; the historical
profile 6427b90 keeps the old outcome (the Python engine's)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))

from audit_helpers import card, legend, setup, unit  # noqa: E402

STORICHE, CORRETTE = "6427b90", "6427b90+D72-D76"


def rust(loop, regole, A=None, B=None):
    """The position on the Rust engine with the rules `regole`, both seats
    scripted (label prefixes; PASS once a script runs out), traced."""
    import riftbound_rs

    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.canon import canonical_state
    g = riftbound_rs.Game.from_canonical(rb.registry(regole), json.dumps(canonical_state(loop.gs)), 1)
    assert g.regole == regole
    for seat, script in (("A", A or {}), ("B", B or {})):
        g.set_script(seat, **script)
    g.set_side_chooser()
    g.trace_on()
    return g


def events(g, k):
    return [e for e in json.loads(g.events()) if e["k"] == k]


def units(g):
    return json.loads(g.units())


def _raw(e):
    raw = e["state_raw"]
    return json.loads(raw) if isinstance(raw, str) else raw


def unit_at(e, name):
    """The raw unit named `name` in a decision's state."""
    raw = _raw(e)
    for v in raw["objs"].values():
        if v.get("$t") == "UnitInPlay" and raw["objs"][v["card"]["$ref"]].get("name") == name:
            return v
    raise AssertionError(f"{name} not in play")


def option_names(e):
    """The card names of a choice's options (units)."""
    out = []
    for o in e["options_raw"]:
        objs = o["objs"]
        u = objs[o["root"]["o"]["$ref"]]
        out.append(objs[u["card"]["$ref"]]["name"])
    return out


# -- D72: Rengar Trophy Hunter where only enemy units are ------------------------

def _enemy_at_bf1(active="A"):
    loop, a, b = setup(active=active)
    loop.gs.battlefields[1].add_unit("B" if active == "A" else "A", unit("Pit Rookie"))
    return loop, a, b


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d72_rengar_from_hand_in_the_main_phase(regole):
    loop, a, _b = _enemy_at_bf1()
    a.hand.append(card("Rengar Trophy Hunter"))
    g = rust(loop, regole)
    g.run_segment(1)
    menu = events(g, "decision")[0]["menu"]
    assert "Play Rengar Trophy Hunter" in menu
    assert ("Play Rengar Trophy Hunter to BF1" in menu) == (regole == CORRETTE), menu
    assert not any("BF0" in m for m in menu if "Rengar" in m)          # empty: never


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d72_rengar_from_the_champion_zone_in_the_main_phase(regole):
    loop, _a, _b = _enemy_at_bf1()
    loop.gs.champion_A = card("Rengar Trophy Hunter")
    g = rust(loop, regole)
    g.run_segment(1)
    menu = [m for m in events(g, "decision")[0]["menu"] if "Rengar" in m]
    assert any("BF1" in m for m in menu) == (regole == CORRETTE), menu
    assert not any("BF0" in m for m in menu)


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d72_rengar_from_hand_at_reaction_speed(regole):
    # B casts Punch First on its own turn: A may react, with Rengar in hand
    # and no unit at a battlefield; B's Pit Rookie is at BF1.
    loop, a, b = _enemy_at_bf1(active="B")
    loop.gs.battlefields[1].units_A, loop.gs.battlefields[1].units_B = [], loop.gs.battlefields[1].units_A
    b.hand.append(card("Punch First"))
    a.hand.append(card("Rengar Trophy Hunter"))
    g = rust(loop, regole, B={"main": ["Cast Punch First"]})
    g.run_segment(1)
    react = [e["menu"] for e in events(g, "decision") if e["seat"] == "A" and e["point"] == "reaction"][0]
    assert ("AMBUSH Rengar Trophy Hunter @BF1" in react) == (regole == CORRETTE), react
    assert not any("@BF0" in m for m in react)


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d72_rengar_from_the_champion_zone_at_reaction_speed(regole):
    """Already right on both profiles (_ambush_legal_lanes had enemy_ok)."""
    loop, a, b = _enemy_at_bf1(active="B")
    loop.gs.battlefields[1].units_A, loop.gs.battlefields[1].units_B = [], loop.gs.battlefields[1].units_A
    b.hand.append(card("Punch First"))
    loop.gs.champion_A = card("Rengar Trophy Hunter")
    g = rust(loop, regole, B={"main": ["Cast Punch First"]})
    g.run_segment(1)
    react = [e["menu"] for e in events(g, "decision") if e["seat"] == "A" and e["point"] == "reaction"][0]
    assert any("Rengar" in m and "BF1" in m for m in react), react


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d72_rengar_played_where_only_enemies_are_contests_it(regole):
    """The corrected play: Rengar goes to BF1 and the battlefield is
    contested (its showdown is staged, as for any unit played there)."""
    if regole == STORICHE:
        pytest.skip("the historical profile has no such play")
    loop, a, _b = _enemy_at_bf1()
    a.hand.append(card("Rengar Trophy Hunter"))
    g = rust(loop, regole, A={"main": ["Play Rengar Trophy Hunter to BF1"]})
    g.run_segment(1)
    assert any(d["point"] == "showdown_action" for d in events(g, "decision")), \
        [(d["seat"], d["point"]) for d in events(g, "decision")]


# -- D73: an AMBUSH play into a showdown sees the battlefield's passives ------

def _amphitheater(champion: bool):
    loop, a, b = setup(active="B")
    bf = loop.gs.battlefields[0]
    bf.card = card("Packed Amphitheater")
    bf.add_unit("A", unit("Sett Kingpin"))
    bf.held_by = "A"
    b.base_units.append(unit("Fiora Victorious"))
    if champion:
        loop.gs.champion_B = card("Rengar Trophy Hunter")
    else:
        b.hand.append(card("Rengar Trophy Hunter"))
    return loop


@pytest.mark.parametrize("champion", [False, True])
@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d73_rengar_ambushed_into_a_showdown_has_the_amphitheater_might(regole, champion):
    """B moves Fiora to A's Packed Amphitheater (showdown), then ambushes
    Rengar there: at A's first showdown decision after it, Rengar (a champion
    unit) has the battlefield's +1."""
    loop = _amphitheater(champion)
    g = rust(loop, regole, B={"main": ["Move Fiora Victorious base→BF0"], "showdown": ["AMBUSH Rengar"]})
    g.run_segment(1)
    first = next(e for e in events(g, "decision")
                 if e["seat"] == "A" and e["point"] == "showdown_action")
    assert unit_at(first, "Rengar Trophy Hunter")["passive_might"] == (1 if regole == CORRETTE else 0)


# -- D74: Pillaged Armory buffs any friendly unit ------------------------------

@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d74_pillaged_armory_played(regole):
    loop, a, _b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("Vi Peacekeeper"))
    a.base_units.append(unit("Fiora Victorious"))
    loop.gs.battlefields[1].add_unit("A", unit("Pit Rookie"))
    a.hand.append(card("Pillaged Armory"))
    g = rust(loop, regole, A={"main": ["Play gear Pillaged Armory @BF0"]})
    g.run_segment(1)
    asked = [option_names(e) for e in events(g, "choice") if e["kind"] == "target:buff_unit"][0]
    want = {"Vi Peacekeeper", "Fiora Victorious", "Pit Rookie"} if regole == CORRETTE else {"Vi Peacekeeper"}
    assert set(asked) == want, asked


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d74_pillaged_armory_conquest(regole):
    from riftbound.core.battlefield import DeployedGear
    loop, a, _b = setup(active="A")
    loop.gs.battlefields[0].gear_A.append(DeployedGear(card("Pillaged Armory")))
    a.base_units += [unit("Vi Peacekeeper"), unit("Fiora Victorious")]
    loop.gs.battlefields[1].add_unit("A", unit("Pit Rookie"))
    loop.gs.battlefields[1].held_by = "A"
    g = rust(loop, regole, A={"main": ["Move Vi Peacekeeper base→BF0"]})
    g.run_segment(1)
    asked = [option_names(e) for e in events(g, "choice") if e["kind"] == "target:buff_unit"][0]
    want = {"Vi Peacekeeper", "Fiora Victorious", "Pit Rookie"} if regole == CORRETTE else {"Vi Peacekeeper"}
    assert set(asked) == want, asked


# -- D75: Sett Kingpin's +1 for each buffed friendly unit at its battlefield ----

def _kingpin(where="bf", buffed=True, other=False):
    loop, a, _b = setup(active="A")
    k = unit("Sett Kingpin")
    k.might_counters = int(buffed)
    bf = loop.gs.battlefields[0]
    if where == "bf":
        bf.add_unit("A", k)
        bf.held_by = "A"
    else:
        a.base_units.append(k)
    if other:
        r = unit("Pit Rookie")
        r.might_counters = 1
        bf.add_unit("A", r)
        bf.held_by = "A"
    return loop, a


def _kingpin_might(g):
    return next(u["might"] for u in units(g) if u["card"] == "Sett Kingpin")


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
@pytest.mark.parametrize("case,want", [(("bf", True, False), 7), (("bf", True, True), 8),
                                       (("base", True, False), 6), (("bf", False, False), 5),
                                       (("bf", False, True), 6)])
def test_d75_sett_kingpin_might(regole, case, want):
    loop, _a = _kingpin(*case)
    g = rust(loop, regole)
    g.recompute_passives()
    first = _kingpin_might(g)
    g.recompute_passives()                       # twice: the same value
    assert _kingpin_might(g) == first
    historic = 5 + int(case[1])                  # its buff only
    assert first == (want if regole == CORRETTE else historic)


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d75_sett_kingpin_moving_between_battlefield_and_base(regole):
    loop, _a = _kingpin("bf", True)
    g = rust(loop, regole, A={"main": ["Move Sett Kingpin BF0→base"]})
    g.recompute_passives()
    assert _kingpin_might(g) == (7 if regole == CORRETTE else 6)
    g.run_segment(1)
    assert _kingpin_might(g) == 6                # in base: its buff only
    later = [e for e in events(g, "decision") if e["seat"] == "A"]
    assert unit_at(later[-1], "Sett Kingpin")["passive_might"] == 0


@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d75_sett_kingpin_spending_its_buff_alone(regole):
    """Call to Glory's additional cost spends the Kingpin's buff: at the next
    decision it has neither the buff nor the +1."""
    loop, a = _kingpin("bf", True)
    a.base_units.append(unit("Pit Rookie"))
    a.hand.append(card("Call to Glory"))
    g = rust(loop, regole, A={"main": ["Cast Call to Glory"]})
    g.recompute_passives()
    assert _kingpin_might(g) == (7 if regole == CORRETTE else 6)
    g.run_segment(1)
    after = next(e for e in events(g, "decision") if e["seat"] == "A" and e["point"] == "reaction")
    k = unit_at(after, "Sett Kingpin")
    assert (k["might_counters"], k["passive_might"]) == (0, 0)


# -- D76: Sett The Boss readies on its player's conquest -----------------------

@pytest.mark.parametrize("regole", [STORICHE, CORRETTE])
def test_d76_sett_the_boss_readies_when_its_player_conquers(regole):
    loop, a, _b = setup(active="A")
    boss = legend(loop, "A", "Sett The Boss")
    boss.ready = False
    a.base_units.append(unit("Pit Rookie"))
    g = rust(loop, regole, A={"main": ["Move Pit Rookie base→BF0"]})
    g.run_segment(1)
    us = units(g)
    assert ("Pit Rookie", "bf0") in [(u["card"], u["where"]) for u in us]
    legend_unit = next(u for u in us if u["where"] == "legend")
    assert legend_unit["ready"] == (regole == CORRETTE)


# -- the profile -----------------------------------------------------------------

def test_both_profiles_load_in_one_thread_in_both_orders():
    """rust_bridge.registry keeps one registry per thread and profile; the
    corrected one applies its data correction, the historical one doesn't."""
    import threading

    import riftbound_rs

    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.rust_bridge import REGISTRY_JSON
    out = {}

    def load(order):
        regs = [rb.registry(r) for r in order]
        out[order] = {r.regole: (r.impronta, r.correzione_dati) for r in regs}
        assert rb.registry(order[0]) is regs[0]               # cached
    for order in ((STORICHE, CORRETTE), (CORRETTE, STORICHE)):
        t = threading.Thread(target=load, args=(order,))
        t.start()
        t.join()
    a, b = out.values()
    assert a == b and a[STORICHE][1] is None and a[CORRETTE][1] == "D72-D76/1"
    assert a[STORICHE][0] != a[CORRETTE][0]
    # A new load of the base file reproduces the same correction.
    assert riftbound_rs.Registry(str(REGISTRY_JSON), CORRETTE).impronta == a[CORRETTE][0]
    with pytest.raises(Exception, match="regole sconosciute"):
        riftbound_rs.Registry(str(REGISTRY_JSON), "6427b90+D99")


def test_the_provenance_of_the_corrected_profile():
    """Each matchup's rules (Python: the historical ones) and the effective
    registry's fingerprint beside the base file's hash."""
    from riftbound.provenienza import provenienza
    from riftbound.rs import rust_bridge as rb
    p = provenienza(motore={"ES": "rust", "bot": "python"}, liste={}, checkpoint={}, regole=CORRETTE)
    assert p["regole"] == CORRETTE and p["regole_partite"] == {"ES": CORRETTE, "bot": STORICHE}
    assert p["registro"]["rust"] and p["registro"]["rust_effettivo"] == rb.registry(CORRETTE).impronta
    assert p["registro"]["correzione_dati"] == "D72-D76/1"
    assert "rust_effettivo" not in provenienza(motore={"EK": "rust"}, liste={}, checkpoint={},
                                               regole=STORICHE)["registro"]
