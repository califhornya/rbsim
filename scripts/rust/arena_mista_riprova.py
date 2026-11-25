"""Riprova di una partita dell'arena mista (arena_mista.py) senza cronometro:
le due copie, Python e Rust, rigiocano la partita con i conteggi di
iterazioni registrati nella sua riga (`iterazioni`, per motore e tipo di
ricerca, in ordine), una dopo l'altra. Si confrontano traccia e ricerche come
nell'arena; per la prima ricerca diversa si indicano le simulazioni (valore
di ciascuna, `vals`) che differiscono.

  python scripts/rust/arena_mista_riprova.py --righe runs/budget/ARENA_MISTA.jsonl --seme 70113 --posto-rust A --ckpt f.pt
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import os  # noqa: E402
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))


def counts_of(row: dict) -> dict:
    """seat -> point -> the counts in order (the seat's leading engine's lists)."""
    rs_seat = row["rust_seat"]
    eng = {rs_seat: "rs", ("B" if rs_seat == "A" else "A"): "py"}
    out: dict = {}
    for seat, e in eng.items():
        out[seat] = {k.split(" ", 1)[1]: list(v) for k, v in row["iterazioni"].items() if k.startswith(e + " ")}
    return out


def feeder(counts: dict):
    """A `before` that gives each search the next recorded count of its seat and point."""
    pos: dict = {}

    def before(info: dict) -> int:
        key = (info["seat"], info["point"])
        i = pos.get(key, 0)
        pos[key] = i + 1
        xs = counts[info["seat"]].get(info["point"], [])
        if i >= len(xs):
            raise RuntimeError(f"nessun conteggio registrato per {info}")
        return xs[i]
    return before


def replay(row: dict, ckpt: str):
    import arena_mista as AM
    import arena_parita as AP
    from riftbound.ai.ppo.collect import EVE, KHA, MAX_TURNS
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.arena_rs import make_probs
    from riftbound.rs.trace_py import traced_game
    seed, starter = row["seed"], row["starter"]
    net = AM._net(ckpt)
    counts = counts_of(row)
    cls = AM._lockstep_class()
    log: list = []
    AP.hook_python(log)
    before_py = feeder(counts)
    fac = {s: (lambda p, s=s: cls(p, net, random.Random(seed * 2 + (s == "B")), 0.4, before_py,
                                  lambda info, n: None)) for s in "AB"}
    res, tr = traced_game(seed, EVE, KHA, fac, starter=starter, chooser="ppo", with_obs=False, keep_states=True)
    before_rs = feeder(counts)
    g = rb.build(seed, EVE, KHA, starter, MAX_TURNS)
    probs = make_probs(net)
    for s in "AB":
        g.set_search_agent(s, 100, seed * 2 + (s == "B"), 0.4, probs, True,
                           lambda info: before_rs(json.loads(info)), lambda info, n: None)
    g.set_side_chooser()
    start = json.loads(g.raw_dump())
    g.trace_on()
    rres = g.start()
    rs_logs = {"A": json.loads(g.search_log("A")), "B": json.loads(g.search_log("B"))}
    return res, tr, log, rres, start, json.loads(g.events()), json.loads(g.raw_dump()), rs_logs


def spiega(job) -> dict:
    """(row, ckpt): the game replayed with its recorded counts and the current
    code; `identica`: the two copies now give the same game and searches
    (the divergence recorded is explained by the fixes made since)."""
    row, ckpt = job
    import torch
    torch.set_num_threads(1)
    import arena_parita as AP
    from diff_trace import FIELDS, canonical_rust_events, first_difference
    out = {"seed": row["seed"], "rust_seat": row["rust_seat"]}
    try:
        res, tr, py_log, rres, start, events, end, rs_logs = replay(row, ckpt)
    except Exception as e:  # noqa: BLE001 — reported, the divergence stays unexplained
        return out | {"identica": False, "dettaglio": f"riprova fallita: {e!r}"}
    rs, rs_trees = canonical_rust_events(start, events, end)
    py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    d = first_difference(py, rs, tr.states, rs_trees)
    s = AP.first_search_difference(py_log, rs_logs)
    rr = list(rres)
    same = d is None and s is None and [res.winner, res.turns] == rr
    det = None if same else {"traccia": None if d is None else [d[0], d[1]],
                             "ricerca": None if s is None else {k: s[k] for k in ("seat", "row", "field", "context")},
                             "risultato": [[res.winner, res.turns], rr]}
    return out | {"identica": same, "dettaglio": det}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--righe", required=True)
    ap.add_argument("--seme", type=int, required=True)
    ap.add_argument("--posto-rust", required=True, choices=("A", "B"))
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", default=None, help="le due ricerche diverse, intere (JSON)")
    args = ap.parse_args()
    import torch
    torch.set_num_threads(1)
    import arena_parita as AP
    from diff_trace import FIELDS, canonical_rust_events, first_difference
    row = next(r for r in map(json.loads, open(args.righe))
               if r["seed"] == args.seme and r["rust_seat"] == args.posto_rust and "iterazioni" in r)
    res, tr, py_log, rres, start, events, end, rs_logs = replay(row, args.ckpt)
    print(f"risultato: Python {res.winner} in {res.turns} turni, Rust {rres}")
    rs, rs_trees = canonical_rust_events(start, events, end)
    py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    d = first_difference(py, rs, tr.states, rs_trees)
    print("traccia:", "identica" if d is None else f"diversa all'evento {d[0]} ({d[1]})")
    s = AP.first_search_difference(py_log, rs_logs)
    if s is None:
        print("ricerche: identiche")
        if d is None and "divergenza" in row:
            print(f"Con il codice attuale le due copie sono identiche: la divergenza registrata è spiegata dalle "
                  f"correzioni successive. Se era solo nei numeri delle ricerche, la partita conta: "
                  f"arena_mista.py --spiegata {row['seed']}:{row['rust_seat']}")
        return
    seat, i = s["seat"], s["row"]
    a = [r for r in py_log if r["seat"] == seat][i]
    b = rs_logs[seat][i]
    print(f"prima ricerca diversa: posto {seat}, riga {i}, campo {s['field']}, {s['context']}")
    va, vb = a.get("vals", []), b.get("vals", [])
    bad = [j for j in range(max(len(va), len(vb))) if j >= len(va) or j >= len(vb) or va[j] != vb[j]]
    print(f"simulazioni: {len(va)} Python, {len(vb)} Rust; diverse: {bad[:20]}")
    for j in bad[:5]:
        print(f"  simulazione {j}: Python {va[j] if j < len(va) else None}, Rust {vb[j] if j < len(vb) else None}")
    if args.out:
        Path(args.out).write_text(json.dumps({"python": a, "rust": b, "simulazioni_diverse": bad}, default=str))


if __name__ == "__main__":
    main()
