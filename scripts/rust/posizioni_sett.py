"""Posizioni mirate per gli effetti di Sett (porting Rust): rami che le
partite intere toccano poco o mai, giocati dal motore Python e da quello Rust
dalla stessa posizione (importata in Rust dallo stato canonico), con le stesse
mosse. Le tracce devono essere identiche evento per evento e ogni posizione
deve far eseguire davvero il ramo che prova (osservazioni sul gioco Python).

- decree_gear: Decree of Unity senza unità Chaos nemiche uccide un gear Chaos
  (`_kill_unit_or_gear` → `_kill_gear` con `_only`: 4 volte in 320 partite).
- sett_save: un'unità con buff muore in combattimento; Sett The Boss paga una
  runa, si esaurisce, spende il buff e la rimanda in base (`sett_save`).
- monastery: conquista di Monastery of Hirana con un'unità con buff: spende il
  buff e pesca (costo `spend_buff` di un'abilità innescata).

  python scripts/rust/posizioni_sett.py [--caso decree_gear]
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

FILLER = ["Punch First", "Rampage", "Call to Glory", "Pit Rookie", "First Mate", "Kinkou Initiate"]
CASI = ("decree_gear", "sett_save", "monastery")


def _deck(names):
    from audit_helpers import card
    from riftbound.core.player import Deck
    return Deck(cards=[card(n) for n in names])


def position(case: str):
    """(loop, scripts {"A": {...}, "B": {...}}). A script entry "?label" is
    taken when legal, else that decision passes and the entry waits."""
    from audit_helpers import card, legend, setup, unit
    loop, a, b = setup(active="A")
    gs = loop.gs
    a.deck, b.deck = _deck(FILLER), _deck(FILLER)
    if case == "decree_gear":
        b.base_gear.append(card("Seal of Discord"))
        b.base_units.append(unit("Noxus Hopeful"))
        a.hand.append(card("Decree of Unity"))
        return loop, {"A": {"main": ["Cast Decree of Unity @BF0"]}, "B": {}}
    if case == "sett_save":
        # One domain only: the import from the canonical state sorts a dict's keys,
        # and the generic [rune] is paid from the pool's first domain.
        for d in list(a.power_pool):
            if d.name != "FURY":
                del a.power_pool[d]
        legend(loop, "A", "Sett The Boss")
        a.base_units.append(unit("Pit Rookie", might_counters=1))
        gs.battlefields[0].add_unit("B", unit("Rengar Trophy Hunter"))
        gs.battlefields[0].held_by = "B"
        return loop, {"A": {"main": ["Move Pit Rookie base→BF0"]}, "B": {}}
    if case == "monastery":
        gs.battlefields[1].card = card("Monastery of Hirana")
        a.base_units.append(unit("Pit Rookie", might_counters=1))
        return loop, {"A": {"main": ["Move Pit Rookie base→BF1"]}, "B": {}}
    raise ValueError(case)


class _IfLegal:
    """Scripted with "?label" entries: taken when legal, else PASS (the entry waits)."""

    def __new__(cls, player, loop, **scripts):
        from audit_helpers import Scripted
        from riftbound.core.decisions import DecisionPoint
        from riftbound.core.legality import legal_actions
        s = Scripted(player, loop, **scripts)
        pick = s._pick

        def _pick(point: DecisionPoint):
            script = s.scripts[point]
            if script and script[0].startswith("?"):
                want = script[0][1:]
                legal = legal_actions(loop, point, player.name)
                if any(g.label.startswith(want) for g in legal):
                    script[0] = want
                    return pick(point)
                s.log.append((point.value, [g.label for g in legal]))
                return ("PASS", None, None)
            return pick(point)
        s._pick = _pick
        return s


def segment_py(loop) -> None:
    """The segment: the active player's actions, end of turn, the next turn (as consegna1)."""
    for _ in range(2):
        if loop._run_main_actions() is not None or loop._end_turn() is not None:
            return
        if loop._begin_turn() is not None:
            return


def run_python(case: str):
    """The position played by Python, traced: (loop, trace, start tree, observations)."""
    from riftbound.core import effects as E
    from riftbound.core import loop as L
    from riftbound.rs.canon import canonical_state
    from riftbound.rs.trace_py import _unhook_deepcopy, instrument
    loop, scripts = position(case)
    gs = loop.gs
    for s in ("A", "B"):
        p = gs.get_player(s)
        p.agent = _IfLegal(p, loop, **scripts[s])
        p.battlefields = gs.battlefields          # as consegna1 (the player's view of the board)
    seen: dict = {"verbi": Counter(), "quantità": [], "veri": Counter(), "condizioni": Counter()}
    saved = dict(E.REGISTRY)
    for verb, fn in saved.items():
        def wrapped(ctx, spec, _fn=fn, _v=verb):
            seen["verbi"][_v] += 1
            real = ctx.loop is loop
            if real:
                seen["veri"][_v] += 1
            if _v == "heal_unit" and real:
                seen["danneggiate"] = sum(1 for bf in gs.battlefields for u in bf._units_for(ctx.actor_side) if u.damage)
            before = list(gs.chain)
            r = _fn(ctx, spec)
            if _v == "heal_unit" and real:
                seen["dopo"] = sum(1 for bf in gs.battlefields for u in bf._units_for(ctx.actor_side) if u.damage)
            if _v == "counter_spell" and real:
                seen["tolte"] = [("ability" if it.ability is not None else "spell") for it in before if it not in gs.chain]
            return r
        E.REGISTRY[verb] = wrapped
    check = L.GameLoop._check_condition

    def _check(self, cond, card, actor, opponent, extra=None):
        r = check(self, cond, card, actor, opponent, extra)
        if isinstance(cond, dict) and self is loop:
            seen["condizioni"][(cond.get("type"), r)] += 1
        return r
    L.GameLoop._check_condition = _check
    spend = L.GameLoop._spend_buff

    def _spend(self, unit, side=None):
        if self is loop and unit.might_counters > 0:
            seen["buff_spesi"] = seen.get("buff_spesi", 0) + 1
        return spend(self, unit, side)
    L.GameLoop._spend_buff = _spend
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
        L.GameLoop._check_condition = check
        L.GameLoop._spend_buff = spend
    tr.add({"k": "end", "state": tr.state()})
    return loop, tr, start_tree, observations(case, loop, seen)


def observations(case: str, loop, seen: dict) -> dict:
    """What each position must make happen (read off the Python game). A
    handler also runs on the copy a chain item's choices are declared on."""
    gs = loop.gs
    out = {"verbi": dict(seen["veri"]), "quantità": seen["quantità"],
           "condizioni": {f"{k[0]} {k[1]}": v for k, v in seen["condizioni"].items()}}
    a = gs.A
    if case == "decree_gear":
        out["ok"] = seen["veri"]["kill_unit_or_gear"] >= 1 and "Seal of Discord" in [c.name for c in gs.B.trash]
    elif case == "sett_save":
        rookie = [u for u in a.base_units if u.card.name == "Pit Rookie"]
        out["ok"] = (seen.get("buff_spesi", 0) >= 1 and len(rookie) == 1 and rookie[0].might_counters == 0
                     and "Pit Rookie" not in [c.name for c in a.trash])
    elif case == "monastery":
        out["ok"] = seen.get("buff_spesi", 0) >= 1 and seen["veri"]["draw_cards"] >= 1
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
