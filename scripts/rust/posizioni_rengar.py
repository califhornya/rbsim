"""Posizioni mirate per gli effetti di Rengar (porting Rust): rami che le
partite intere toccano poco o mai, giocati dal motore Python e da quello Rust
dalla stessa posizione (importata in Rust dallo stato canonico), con le stesse
mosse. Le tracce devono essere identiche evento per evento e ogni posizione
deve far eseguire davvero il ramo che prova (osservazioni sul gioco Python).

- thrill_gear: Thrill of the Hunt su un'unità con un equipaggiamento: l'unità
  è bandita e rigiocata, l'equipaggiamento resta in base (`_blink_unit`; nei
  matchup ER e KR Rengar non ha equipaggiamenti).
- brittle_deployed: Brittle Steel uccide un gear schierato su un campo
  (`_kill_gear` → `_kill_deployed_gear`).
- bilgewater_base: Bilgewater Tracker, "fino a due unità ovunque": l'unica
  nemica è in base e muore (`_deal_damage` con `up_to`, morti in base).
- ferrous_dies: Ferrous Forerunner muore in combattimento: due Mech in base.
- seat_of_power: conquista di Seat of Power controllando un altro campo:
  pesca 1 (`other_battlefields_controlled`).
- sunken_temple: conquista di Sunken Temple con un'unità MIGHTY, pagando 1:
  pesca 1 (`friendly_mighty_unit_here`, costo del trigger).
- acceptable_losses: Acceptable Losses (sideboard di Kha'Zix), "ogni giocatore
  uccide uno dei suoi gear": ognuno sceglie il suo meno caro (`_kill_gear`,
  `each_player`), un gear attaccato e uno in base.

  python scripts/rust/posizioni_rengar.py [--caso thrill_gear]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "scripts/rust"))

FILLER = ["Punch First", "Rampage", "Sabotage", "Inferna", "Pit Rookie", "Kinkou Initiate"]
CASI = ("thrill_gear", "brittle_deployed", "bilgewater_base", "ferrous_dies", "seat_of_power", "sunken_temple",
        "acceptable_losses")


def _deck(names):
    from audit_helpers import card
    from riftbound.core.player import Deck
    return Deck(cards=[card(n) for n in names])


def position(case: str):
    """(loop, scripts {"A": {...}, "B": {...}})."""
    from audit_helpers import card, setup, unit
    loop, a, b = setup(active="A")
    gs = loop.gs
    a.deck, b.deck = _deck(FILLER), _deck(FILLER)
    if case == "thrill_gear":
        rookie = unit("Pit Rookie")
        rookie.gear.append(card("Boots of Swiftness"))
        gs.battlefields[0].add_unit("A", rookie)
        gs.battlefields[0].held_by = "A"
        gs.battlefields[1].add_unit("B", unit("Irresistible Faefolk"))
        gs.battlefields[1].held_by = "B"
        a.hand.append(card("Thrill of the Hunt"))
        return loop, {"A": {"main": ["Cast Thrill of the Hunt @BF0"]}, "B": {}}
    if case == "brittle_deployed":
        loop._deploy_gear("B", gs.battlefields[1], card("The Good Stuff"))
        b.base_units.append(unit("Noxus Hopeful"))
        a.hand.append(card("Brittle Steel"))
        return loop, {"A": {"main": ["Cast Brittle Steel @BF0"]}, "B": {}}
    if case == "bilgewater_base":
        b.base_units.append(unit("Irresistible Faefolk"))
        a.base_units.append(unit("Noxus Hopeful"))
        a.hand.append(card("Bilgewater Tracker"))
        return loop, {"A": {"main": ["Play Bilgewater Tracker"]}, "B": {}}
    if case == "ferrous_dies":
        a.base_units.append(unit("Ferrous Forerunner"))
        gs.battlefields[0].add_unit("B", unit("Rengar Trophy Hunter"))
        gs.battlefields[0].add_unit("B", unit("Noxus Hopeful"))
        gs.battlefields[0].held_by = "B"
        return loop, {"A": {"main": ["Move Ferrous Forerunner base→BF0"]}, "B": {}}
    if case == "seat_of_power":
        gs.battlefields[0].card = card("Seat of Power")
        gs.battlefields[1].add_unit("A", unit("Kinkou Initiate"))
        gs.battlefields[1].held_by = "A"
        a.base_units.append(unit("Pit Rookie"))
        return loop, {"A": {"main": ["Move Pit Rookie base→BF0"]}, "B": {}}
    if case == "sunken_temple":
        gs.battlefields[1].card = card("Sunken Temple")
        a.base_units.append(unit("Ferrous Forerunner"))
        return loop, {"A": {"main": ["Move Ferrous Forerunner base→BF1"]}, "B": {}}
    if case == "acceptable_losses":
        rookie = unit("Pit Rookie")
        rookie.gear.append(card("Edge of Night"))
        a.base_units.append(rookie)
        a.base_gear.append(card("The Good Stuff"))
        b.base_gear += [card("Boots of Swiftness"), card("The Good Stuff")]
        a.hand.append(card("Acceptable Losses"))
        return loop, {"A": {"main": ["Cast Acceptable Losses @BF0"]}, "B": {}}
    raise ValueError(case)


def segment_py(loop) -> None:
    """The segment: the active player's actions, end of turn, the next turn (as consegna1)."""
    for _ in range(2):
        if loop._run_main_actions() is not None or loop._end_turn() is not None:
            return
        if loop._begin_turn() is not None:
            return


def run_python(case: str):
    """The position played by Python, traced: (loop, trace, start tree, observations)."""
    from audit_helpers import Scripted
    from riftbound.core import effects as E
    from riftbound.rs.canon import canonical_state
    from riftbound.rs.trace_py import _unhook_deepcopy, instrument
    loop, scripts = position(case)
    gs = loop.gs
    for s in ("A", "B"):
        p = gs.get_player(s)
        p.agent = Scripted(p, loop, **scripts[s])
        p.battlefields = gs.battlefields          # as consegna1 (the player's view of the board)
    seen: dict = {"verbi": Counter(), "quantità": []}
    saved = dict(E.REGISTRY)
    for verb, fn in saved.items():
        def wrapped(ctx, spec, _fn=fn, _v=verb):
            seen["verbi"][_v] += 1
            return _fn(ctx, spec)
        E.REGISTRY[verb] = wrapped
    amount = E._amount

    def _amount(ctx, spec):
        v = amount(ctx, spec)
        if spec.get("amount_source"):
            seen["quantità"].append([spec["amount_source"], v])
        return v
    E._amount = _amount
    start_tree = canonical_state(gs)
    tr = instrument(gs, loop, with_obs=False, keep_states=True)
    tr.add({"k": "start", "state": tr.state()})
    try:
        segment_py(loop)
    finally:
        _unhook_deepcopy()
        E.REGISTRY.clear()
        E.REGISTRY.update(saved)
        E._amount = amount
    tr.add({"k": "end", "state": tr.state()})
    return loop, tr, start_tree, observations(case, loop, seen)


def observations(case: str, loop, seen: dict) -> dict:
    """What each position must make happen (read off the Python game). A
    handler also runs on the copy a chain item's choices are declared on."""
    gs = loop.gs
    a, b = gs.A, gs.B
    names = lambda cs: [c.name for c in cs]
    units = lambda side: [u.card.name for bf in gs.battlefields for u in bf._units_for(side)] + \
        [u.card.name for u in gs.get_player(side).base_units]
    out = {"verbi": dict(seen["verbi"]), "quantità": seen["quantità"]}
    if case == "thrill_gear":
        out["ok"] = (seen["verbi"]["blink_unit"] >= 1 and "Boots of Swiftness" in names(a.base_gear)
                     and "Pit Rookie" in units("A"))
    elif case == "brittle_deployed":
        out["ok"] = (seen["verbi"]["kill_gear"] >= 1 and "The Good Stuff" in names(b.trash)
                     and not any(bf.gear_for("B") for bf in gs.battlefields))
    elif case == "bilgewater_base":
        out["ok"] = (seen["verbi"]["deal_damage"] >= 1 and "Irresistible Faefolk" in names(b.trash)
                     and "Noxus Hopeful" in units("A"))
    elif case == "ferrous_dies":
        out["ok"] = units("A").count("Mech") == 2 and "Ferrous Forerunner" in names(a.trash)
    elif case == "seat_of_power":
        out["ok"] = ["other_battlefields_controlled", 1] in seen["quantità"]
    elif case == "acceptable_losses":
        out["ok"] = (seen["verbi"]["kill_gear"] >= 1 and len(a.trash) + len(b.trash) >= 3
                     and len(names(a.base_gear)) + sum(len(u.gear) for u in a.base_units) == 1
                     and len(b.base_gear) == 1)
    elif case == "sunken_temple":
        out["ok"] = seen["verbi"]["draw_cards"] >= 1 and gs.battlefields[1].held_by == "A"
    return out


def compare(case: str) -> dict:
    """Python and Rust from the same position: first difference (None) and observations."""
    import riftbound_rs
    from diff_trace import FIELDS, canonical_rust_events, first_difference
    from riftbound.rs import rust_bridge as rb
    loop, tr, start_tree, obs = run_python(case)
    g = riftbound_rs.Game.from_canonical(rb.registry(), json.dumps(start_tree), 1)
    g.set_replay(json.dumps(tr.events), False, False)
    start_raw = json.loads(g.raw_dump())
    g.trace_on()
    err = None
    try:
        g.run_segment(2)
    except RuntimeError as e:
        err = str(e)
    rs, rs_trees = canonical_rust_events(start_raw, json.loads(g.events()), json.loads(g.raw_dump()))
    py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    d = first_difference(py, rs, tr.states, rs_trees)
    out = {"caso": case, "eventi": len(py), "rust_error": err, "osservazioni": obs}
    if d is not None:
        i, f, va, vb, detail = d
        out["first_difference"] = {"event": i, "field": f, "python": va, "rust": vb, "detail": detail,
                                   "python_event": {k: v for k, v in py[i].items() if k != "state"}}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--caso", nargs="*", default=list(CASI))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rows = [compare(c) for c in args.caso]
    for r in rows:
        ok = r["rust_error"] is None and "first_difference" not in r and r["osservazioni"]["ok"]
        print(f"{r['caso']}: {'identiche' if ok else 'DIVERSE o ramo non eseguito'} ({r['eventi']} eventi)"
              if ok else json.dumps(r, default=str)[:3000])
    n = sum(1 for r in rows if r["rust_error"] is None and "first_difference" not in r and r["osservazioni"]["ok"])
    print(f"\n{n}/{len(rows)} posizioni identiche, ramo eseguito")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
