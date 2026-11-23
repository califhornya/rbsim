"""Prima consegna del porting (F2): due posizioni con Gold, giocate dal
motore Python e da quello Rust, con le tracce appaiate e i tempi.

- D59. Il giocatore A muove Traveling Merchant su un campo con un'unità di B
  (Standard Move in sospeso, campo conteso); il trigger "quando mi muovo"
  apre una catena; nella finestra di reazione A sceglie Gold. Si registra se
  l'abilità è eseguita, lo stato del movimento e se la finestra conta un pass.
- D59b. Lo stesso su un campo vuoto dove A ha già segnato in questo turno:
  chiudere il movimento non cambia nulla che l'impronta di
  `_use_ability_now` veda (nel D59 lo showdown e il combattimento la
  cambiano: la finestra lo prende per un'abilità Add e A tiene la priorità).
- D62. Il giocatore B (di turno) gioca Punch First (catena senza movimento in
  sospeso); B passa, A attiva Gold (abilità Add, eseguita), A passa: si
  registra se B riceve di nuovo priorità prima della risoluzione (nel
  riferimento no: è il difetto).
Ogni posizione è poi giocata fino al combattimento, al cleanup e al turno
successivo (segmento: azioni del turno, fine turno, inizio del turno dopo,
azioni, fine turno).

  python scripts/rust/consegna1.py [--ripetizioni 200] [--out docs/rust/misure/consegna1.json]
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "scripts/rust"))

GOLD = "Gear gain_power_any_domain (Gold)"


def _deck(names):
    from audit_helpers import card
    from riftbound.core.player import Deck
    return Deck(cards=[card(n) for n in names])


def position(case: str):
    """(loop, scripts {"A": {...}, "B": {...}}) for D59 or D62."""
    from audit_helpers import card, setup, unit
    filler = ["Punch First", "Rampage", "Gust", "Star-Crossed", "Hold 'Em", "Onslaught"]
    if case in ("D59", "D59b"):
        loop, a, b = setup(active="A")
        gs = loop.gs
        a.deck = _deck(filler)
        b.deck = _deck(filler)
        a.hand += [card("Gust"), card("Rampage")]
        merchant = unit("Traveling Merchant")
        a.base_units.append(merchant)
        if case == "D59":
            gs.battlefields[0].add_unit("B", unit("Vex Apathetic", ready=True))
            gs.battlefields[0].held_by = "B"
        else:
            gs.battlefields[0].scored_this_turn_A = True     # conquering it gives no point
        gold = card("Gold")
        gold.is_token = True
        a.base_gear.append(gold)
        scripts = {"A": {"main": ["Move Traveling Merchant base→BF0"], "reaction": [GOLD]},
                   "B": {}}
        return loop, scripts
    if case == "D62":
        loop, a, b = setup(active="B")
        gs = loop.gs
        a.deck = _deck(filler)
        b.deck = _deck(filler)
        b.hand += [card("Punch First")]
        b.base_units.append(unit("Momentary Companion"))
        a.base_units.append(unit("Traveling Merchant"))
        gold = card("Gold")
        gold.is_token = True
        a.base_gear.append(gold)
        scripts = {"A": {"reaction": [GOLD, "PASS"]},
                   "B": {"main": ["Cast Punch First @BF0"], "reaction": ["PASS"]}}
        return loop, scripts
    raise ValueError(case)


def segment_py(loop) -> None:
    """The segment: the active player's actions, end of turn, the next turn."""
    for _ in range(2):
        if loop._run_main_actions() is not None or loop._end_turn() is not None:
            return
        if loop._begin_turn() is not None:
            return


def run_python(case: str, traced: bool):
    from audit_helpers import Scripted
    from riftbound.rs.canon import canonical_state
    from riftbound.rs.trace_py import instrument
    loop, scripts = position(case)
    gs = loop.gs
    for s in ("A", "B"):
        p = gs.get_player(s)
        p.agent = Scripted(p, loop, **scripts[s])
        p.agent.loop, p.agent.gs = loop, gs
        p.agent.player.battlefields = gs.battlefields
    tr = None
    if traced:
        start_tree = canonical_state(gs)
        tr = instrument(gs, loop, with_obs=False, keep_states=True)
        tr.add({"k": "start", "state": tr.state()})
    if not traced:
        segment_py(loop)
        return loop, None, None
    from riftbound.rs.trace_py import _unhook_deepcopy
    try:
        segment_py(loop)
    finally:
        _unhook_deepcopy()          # the timed runs below play untraced
    tr.add({"k": "end", "state": tr.state()})
    return loop, tr, start_tree


def _tree_side(tree, side, field):
    return [x for x in tree["root"][side]["$v"][field]]


def observations(case: str, events: list, trees: dict) -> dict:
    """What D59 / D62 ask, read off one engine's trace (Python's or Rust's)."""
    dec = [e for e in events if e["k"] == "decision"]
    label = lambda e: e["menu"][e["index"]] if e["index"] is not None else e["action"][0]
    gi = next(i for i, e in enumerate(dec) if label(e) == GOLD)
    gold = dec[gi]
    nxt = dec[gi + 1]
    nxt_reaction = next(e for e in dec[gi + 1:] if e["point"] == "reaction")
    gear_after = _tree_side(trees[nxt["state"]], gold["seat"], "base_gear")
    out = {"gold_scelto_da": gold["seat"], "finestra_gold": gold["point"],
           "movimento_in_sospeso_alla_scelta": gold["win"]["pending_move"],
           "gold_eseguito": not any("Gold" in str(g) for g in gear_after),
           "movimento_dopo": nxt["win"]["pending_move"],
           "decisione_dopo": [nxt["seat"], nxt["point"]],
           "prossima_reazione_a": nxt_reaction["seat"]}
    if case.startswith("D59"):
        # A keeps priority ("kept": the window saw a change) or it passes to B ("pass").
        out["finestra_conta_un_pass"] = nxt_reaction["seat"] != gold["seat"]
        out["showdown_nella_finestra"] = any(e["point"] == "showdown_action" for e in dec[gi + 1:]
                                             if e["win"]["chain"] > 0)
    else:
        # From the chain's opening to its resolution: who was asked, in order.
        start = next(i for i, e in enumerate(dec) if e["win"]["chain"] > 0)
        end = next(i for i, e in enumerate(dec) if i > start and e["win"]["chain"] == 0)
        seq = [[e["seat"], label(e)] for e in dec[start:end]]
        last_b = max(i for i, (s, _) in enumerate(seq) if s == "B")
        out["finestra"] = seq
        out["B_di_nuovo_priorita_dopo_gold"] = last_b > next(i for i, (s, a) in enumerate(seq) if a == GOLD)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ripetizioni", type=int, default=200)
    ap.add_argument("--out", default=str(ROOT / "docs/rust/misure/consegna1.json"))
    ap.add_argument("--tracce", default=str(ROOT / "docs/rust/consegna1"),
                    help="dove scrivere le tracce appaiate (un evento canonico per riga)")
    args = ap.parse_args()
    import riftbound_rs
    from diff_trace import canonical_rust_events, first_difference, FIELDS
    from riftbound.rs import rust_bridge as rb
    report = {"cosa": "consegna1 (D59, D62 con Gold)", "macchina": platform.node(),
              "cpu": platform.processor() or platform.machine(), "python": sys.version.split()[0], "casi": {}}
    import subprocess
    report["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                      text=True).stdout.strip()
    report["comando"] = "python " + " ".join(sys.argv)
    for case in ("D59", "D59b", "D62"):
        loop, tr, start_tree = run_python(case, traced=True)
        py_events = tr.events
        g = riftbound_rs.Game.from_canonical(rb.registry(), json.dumps(start_tree), 1)
        g.set_replay(json.dumps(py_events), False, False)
        start_raw = json.loads(g.raw_dump())
        g.trace_on()
        err = None
        try:
            g.run_segment(2)
        except RuntimeError as e:
            err = str(e)
        rs, rs_trees = canonical_rust_events(start_raw, json.loads(g.events()), json.loads(g.raw_dump()))
        py_cmp = [e for e in py_events if e["k"] in FIELDS or e["k"].startswith("decide_")]
        d = first_difference(py_cmp, rs, tr.states, rs_trees)
        # What the windows saw: who was asked at each reaction / showdown, and the move.
        asks = [(e["seat"], e["point"], e["menu"][e["index"]] if e["index"] is not None else e["action"][0],
                 e["win"]["chain"], e["win"]["pending_move"]) for e in py_cmp if e["k"] == "decision"]
        rs_asks = [(e["seat"], e["point"], e["menu"][e["index"]] if e["index"] is not None else e["action"][0],
                    e["win"]["chain"], e["win"]["pending_move"]) for e in rs if e["k"] == "decision"]
        tdir = Path(args.tracce)
        tdir.mkdir(parents=True, exist_ok=True)
        for name, evs in (("python", py_cmp), ("rust", rs)):
            (tdir / f"{case}_{name}.jsonl").write_text(
                "".join(json.dumps({k: v for k, v in e.items() if k not in ("i", "obs")}, sort_keys=True) + "\n"
                        for e in evs))
        final = loop.gs
        row = {"eventi": len(py_cmp), "identiche": d is None and err is None, "errore_rust": err,
               "prima_differenza": None if d is None else {"evento": d[0], "campo": d[1], "python": d[2], "rust": d[3],
                                                          "dettaglio": d[4]},
               "osservazioni_python": observations(case, py_cmp, tr.states),
               "osservazioni_rust": observations(case, rs, rs_trees) if err is None else None,
               "decisioni_python": asks, "decisioni_rust": rs_asks,
               "stato_finale_python": {"turno": final.turn, "punti": [final.points_A, final.points_B],
                                       "gold_A_in_base": [c.name for c in final.A.base_gear],
                                       "pending_move": final.pending_move}}
        # Timing: the segment on one core, position loading apart.
        n = args.ripetizioni
        t_load_py, t_seg_py, t_load_rs, t_seg_rs = [], [], [], []
        tree_json = json.dumps(start_tree)
        for _ in range(n):
            t0 = time.perf_counter()
            from audit_helpers import Scripted
            lp, scripts = position(case)
            for s in ("A", "B"):
                p = lp.gs.get_player(s)
                p.agent = Scripted(p, lp, **scripts[s])
                p.agent.player.battlefields = lp.gs.battlefields
            t1 = time.perf_counter()
            segment_py(lp)
            t2 = time.perf_counter()
            t_load_py.append(t1 - t0)
            t_seg_py.append(t2 - t1)
            t0 = time.perf_counter()
            g = riftbound_rs.Game.from_canonical(rb.registry(), tree_json, 1)
            g.set_replay(json.dumps(py_events), False, False)
            t1 = time.perf_counter()
            g.run_segment(2)
            t2 = time.perf_counter()
            t_load_rs.append(t1 - t0)
            t_seg_rs.append(t2 - t1)

        def st(xs):
            return {"mediana_ms": round(1000 * statistics.median(xs), 4), "min_ms": round(1000 * min(xs), 4),
                    "max_ms": round(1000 * max(xs), 4), "dev_std_ms": round(1000 * statistics.pstdev(xs), 4)}
        row["tempi"] = {"ripetizioni": n, "python_caricamento": st(t_load_py), "python_segmento": st(t_seg_py),
                        "rust_caricamento": st(t_load_rs), "rust_segmento": st(t_seg_rs),
                        "rapporto_segmento": round(statistics.median(t_seg_py) / statistics.median(t_seg_rs), 2)}
        report["casi"][case] = row
        t = row["tempi"]
        print(f"{case}: tracce identiche={row['identiche']} eventi={row['eventi']} "
              f"prima_differenza={row['prima_differenza']} errore_rust={err}")
        print(f"  osservazioni Python: {row['osservazioni_python']}")
        print(f"  osservazioni Rust:   {row['osservazioni_rust']}")
        print(f"  segmento (mediana su {n}): Python {t['python_segmento']['mediana_ms']} ms, "
              f"Rust {t['rust_segmento']['mediana_ms']} ms (x{t['rapporto_segmento']}); caricamento: "
              f"Python {t['python_caricamento']['mediana_ms']} ms, Rust {t['rust_caricamento']['mediana_ms']} ms")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
