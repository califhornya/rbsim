"""Partite autonome Python / Rust dai semi (porting, F4): ogni motore gioca
la stessa partita (EK o un altro matchup, --matchup) da solo, con i propri agenti (simple_trade, random con
il suo generatore), senza decisioni né estrazioni registrate. Le tracce si
confrontano evento per evento (come diff_trace.py): così il replay non
nasconde differenze nel consumo di casualità o nelle euristiche.

  python scripts/rust/autonome.py --semi 1-50 --agenti simple_trade simple_trade
  python scripts/rust/autonome.py --semi 1-50 --agenti random random
  python scripts/rust/autonome.py --semi 1-50 --matchup ER --posti
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import os  # noqa: E402
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))


def agent_seed(seed: int, seat: str) -> int:
    return seed * 2 + (seat == "B")


def python_game(seed: int, kinds: dict, starter: str, mu: str = "EK", bf_a=None, bf_b=None):
    from riftbound.rs.mazzi import decks
    from riftbound.ai.search.random_agent import RandomAgent
    from riftbound.core.game_factory import make_agent
    from riftbound.rs.trace_py import traced_game

    def factory(seat):
        if kinds[seat] == "random":
            return lambda p: RandomAgent(p, random.Random(agent_seed(seed, seat)))
        return lambda p: make_agent(kinds[seat], p)
    return traced_game(seed, *decks(mu), {s: factory(s) for s in "AB"}, starter=starter, chooser="none",
                       with_obs=False, keep_states=True, bf_a=bf_a, bf_b=bf_b)


def rust_game(seed: int, kinds: dict, starter: str, mu: str = "EK", bf_a=None, bf_b=None):
    from riftbound.rs.mazzi import decks
    from riftbound.rs import rust_bridge as rb
    g = rb.build(seed, *decks(mu), starter, 40, bf_a=bf_a, bf_b=bf_b)
    for s in "AB":
        g.set_agent(s, kinds[s], agent_seed(seed, s))
    start = json.loads(g.raw_dump())
    g.trace_on()
    err = None
    try:
        res = g.start()
    except RuntimeError as e:
        res, err = None, str(e)
    return start, json.loads(g.events()), json.loads(g.raw_dump()), res, err


def compare(seed: int, kinds: dict, starter: str, mu: str = "EK", bf_a=None, bf_b=None) -> dict:
    from diff_trace import FIELDS, canonical_rust_events, first_difference
    t0 = time.perf_counter()
    res, tr = python_game(seed, kinds, starter, mu, bf_a, bf_b)
    t_py = time.perf_counter() - t0
    t0 = time.perf_counter()
    start, events, end, rres, err = rust_game(seed, kinds, starter, mu, bf_a, bf_b)
    t_rs = time.perf_counter() - t0
    rs, rs_trees = canonical_rust_events(start, events, end)
    py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    d = first_difference(py, rs, tr.states, rs_trees)
    out = {"seed": seed, "matchup": mu, "starter": starter, "agenti": [kinds["A"], kinds["B"]], "py": [res.winner, res.turns],
           "rs": list(rres) if rres else None, "rust_error": err, "events": len(py),
           "t_py_traced": round(t_py, 3), "t_rs_traced": round(t_rs, 3)}
    if d is not None:
        i, f, va, vb, detail = d
        ctx = [e for e in py[max(0, i - 4):i] if e["k"] != "rng"]
        out["first_difference"] = {"event": i, "field": f, "python": va, "rust": vb, "detail": detail,
                                   "python_event": {k: v for k, v in py[i].items() if k != "state"},
                                   "rust_event": {k: v for k, v in rs[i].items() if k != "state"} if i < len(rs) else None,
                                   "context": [{k: v for k, v in e.items() if k in ("k", "seat", "point", "kind", "action",
                                                                                     "chosen", "win")} for e in ctx]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", nargs="+", required=True, help="semi o intervalli a-b")
    ap.add_argument("--agenti", nargs=2, default=["simple_trade", "simple_trade"], metavar=("A", "B"))
    ap.add_argument("--matchup", default="EK", help="lettere di riftbound/rs/mazzi.py: il primo mazzo in A (EK, ER, KR; minuscola = con la sideboard: Er)")
    ap.add_argument("--posti", action="store_true", help="anche col matchup rovesciato (i mazzi ai due posti)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--stop", action="store_true", help="fermati alla prima partita diversa")
    args = ap.parse_args()
    seeds = []
    for s in args.semi:
        if "-" in s:
            a, b = s.split("-")
            seeds += list(range(int(a), int(b) + 1))
        else:
            seeds.append(int(s))
    kinds = {"A": args.agenti[0], "B": args.agenti[1]}
    rows = []
    mus = [args.matchup] + ([args.matchup[::-1]] if args.posti and args.matchup[0] != args.matchup[1] else [])
    for seed in seeds:
        starter = "a" if seed % 2 == 0 else "b"
        stop = False
        for mu in mus:
            r = compare(seed, kinds, starter, mu)
            rows.append(r)
            ok = "first_difference" not in r and not r["rust_error"]
            print(json.dumps(r, default=str)[:2500] if not ok else
                  f"{seed} {mu}: identiche ({r['events']} eventi, {r['py']})")
            stop = stop or (args.stop and not ok)
        if stop:
            break
    ok = sum(1 for r in rows if "first_difference" not in r and not r["rust_error"])
    print(f"\n{ok}/{len(rows)} partite identiche ({kinds['A']} contro {kinds['B']}, {'+'.join(mus)})")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
