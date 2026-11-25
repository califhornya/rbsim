"""Posizioni mirate per gli effetti di Ivern (porting Rust): rami che le
partite intere toccano poco o mai, giocati dal motore Python e da quello Rust
dalla stessa posizione (importata in Rust dallo stato canonico), con le stesse
mosse. Le tracce devono essere identiche evento per evento e ogni posizione
deve far eseguire davvero il ramo che prova (osservazioni sul gioco Python).

- janna_heal: Janna Savior giocata come REACTION su un campo controllato, con
  un'unità amica danneggiata: la cura (`heal_unit`, nelle partite intere mai su
  un'unità danneggiata); nessun nemico lì da spostare (`move_unit`, up_to).
- daisy_pets: Daisy! attacca con Bird, Cat, Dog e Poro fra le unità amiche:
  stordisce un nemico (`has_all_pet_tags` vera: 3 volte in 360 partite).
- nsf_ability: Not So Fast contro l'abilità di Daisy! che sceglie un'unità
  nemica: il counter toglie dalla pila un'abilità, non una magia
  (`_counter_spell`, ramo `ability`).

  python scripts/rust/posizioni_ivern.py [--caso janna_heal]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import os  # noqa: E402
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "scripts/rust"))

FILLER = ["Friendship", "Block", "Defy", "Stalwart Poro", "Mutated Mouser", "Trusty Ramhound"]
CASI = ("janna_heal", "daisy_pets", "nsf_ability")
PETS = ("Iridescent Avian", "Mutated Mouser", "Trusty Ramhound", "Stalwart Poro")


def _deck(names):
    from audit_helpers import card
    from riftbound.core.player import Deck
    return Deck(cards=[card(n) for n in names])


def position(case: str):
    """(loop, scripts {"A": {...}, "B": {...}}). A script entry "?label" is
    taken when legal, else that decision passes and the entry waits."""
    from audit_helpers import card, setup, unit
    loop, a, b = setup(active="B" if case == "janna_heal" else "A")
    gs = loop.gs
    a.deck, b.deck = _deck(FILLER), _deck(FILLER)
    if case == "janna_heal":
        poro = unit("Stalwart Poro")
        poro.damage = 1
        gs.battlefields[0].add_unit("A", poro)
        gs.battlefields[0].held_by = "A"
        gs.battlefields[1].add_unit("B", unit("Pit Rookie"))
        gs.battlefields[1].held_by = "B"
        a.hand.append(card("Janna Savior"))
        b.hand.append(card("Friendship"))
        return loop, {"A": {"reaction": ["?AMBUSH Janna Savior @BF0"]}, "B": {"main": ["Cast Friendship @BF1"]}}
    if case in ("daisy_pets", "nsf_ability"):
        a.base_units += [unit("Daisy!")] + [unit(n) for n in PETS]
        gs.battlefields[0].add_unit("B", unit("Noxus Hopeful"))
        gs.battlefields[0].held_by = "B"
        if case == "nsf_ability":
            b.hand.append(card("Not So Fast"))
            return loop, {"A": {"main": ["Move Daisy! base→BF0"]}, "B": {"reaction": ["?React Not So Fast"]}}
        return loop, {"A": {"main": ["Move Daisy! base→BF0"]}, "B": {}}
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
    tr.add({"k": "end", "state": tr.state()})
    return loop, tr, start_tree, observations(case, loop, seen)


def observations(case: str, loop, seen: dict) -> dict:
    """What each position must make happen (read off the Python game). A
    handler also runs on the copy a chain item's choices are declared on."""
    gs = loop.gs
    out = {"verbi": dict(seen["veri"]), "quantità": seen["quantità"],
           "condizioni": {f"{k[0]} {k[1]}": v for k, v in seen["condizioni"].items()}}
    if case == "janna_heal":
        out["ok"] = seen["veri"]["heal_unit"] >= 1 and seen.get("danneggiate", 0) >= 1 and seen.get("dopo") == 0
    elif case == "daisy_pets":
        out["ok"] = seen["condizioni"][("has_all_pet_tags", True)] >= 1 and seen["veri"]["stun_unit"] >= 1
    elif case == "nsf_ability":
        out["ok"] = seen.get("tolte") == ["ability"] and seen["veri"]["stun_unit"] == 0
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
