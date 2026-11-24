"""Confronto Python / Rust di una partita (porting, F1): la partita Python è
tracciata (riftbound/rs/trace_py.py); Rust la rigioca con le stesse scelte
(agente e chooser di replay, che controllano che l'opzione registrata sia
legale nel menu Rust) e produce la sua traccia; le due tracce si confrontano
evento per evento (chi agisce, finestra, stato canonico, menu, azione,
scelte interne, estrazioni casuali). Si ferma alla PRIMA differenza e stampa
il minimo per riprodurla.

  python scripts/rust/diff_trace.py --semi 1000001 1000002 --modo self [--seme-rete 1]
  python scripts/rust/diff_trace.py --semi 1000001-1000020 --modo self
  python scripts/rust/diff_trace.py --semi 1000001-1000020 --modo self --matchup KR --posti
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs.canon import Canon, first_diff  # noqa: E402


def _digest(tree) -> str:
    return hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest()[:16]


def python_game(seed: int, modo: str, net=None, starter: str = "a", mu: str = "EK"):
    """A traced Python game: PPO self-play (seeded net) or PPO vs simple_trade."""
    from riftbound.ai.ppo.agent import PPOAgent
    from riftbound.rs.mazzi import decks
    from riftbound.rs.trace_py import traced_game
    from riftbound.core.game_factory import make_agent
    if modo == "self":
        agents = {s: (lambda p, s=s: PPOAgent(p, net, sample=True, seed=seed * 2 + (s == "B"))) for s in "AB"}
    elif modo == "simple_trade":
        agents = {"A": lambda p: PPOAgent(p, net, sample=True, seed=seed * 2),
                  "B": lambda p: make_agent("simple_trade", p)}
    else:
        raise ValueError(modo)
    res, tr = traced_game(seed, *decks(mu), agents, starter=starter, with_obs=False,
                          keep_states=True)
    return res, tr


def rust_events(seed: int, py_events: list, starter: str = "a", mu: str = "EK"):
    """Rust replays the Python game: -> (start raw, events, end raw, result or error)."""
    from riftbound.rs.mazzi import decks
    from riftbound.rs import rust_bridge as rb
    g = rb.build(seed, *decks(mu), starter, 40)
    has_choice = any(e["k"] == "choice" for e in py_events)
    g.set_replay(json.dumps(py_events), True, True)
    start = json.loads(g.raw_dump())
    g.trace_on()
    err = None
    try:
        res = g.start()
    except RuntimeError as e:          # a replay mismatch or NotPorted
        res, err = None, str(e)
    events = json.loads(g.events())
    end = json.loads(g.raw_dump())
    return start, events, end, res, err, has_choice


def canonical_rust_events(start, events, end):
    """Rust events canonicalized in trace_py's order (state, then options,
    then source; a simple event's args after its state)."""
    canon = Canon()
    out = []
    trees = {}

    def state(raw):
        t = canon.canonical(raw)
        h = _digest(t)
        trees[h] = t
        return h

    def opt(raw):
        return canon.canonical(raw)["root"]["o"]
    out.append({"k": "start", "state": state(start)})
    for e in events:
        k = e["k"]
        if k == "rng":
            out.append({"k": "rng", "op": e["op"], "n": e["n"], "r": e["r"]})
        elif k == "decision":
            out.append({"k": k, "seat": e["seat"], "point": e["point"], "win": e["win"], "state": state(e["state_raw"]),
                        "menu": e["menu"], "action": e["action"], "index": e["index"]})
        elif k == "choice":
            st = state(e["state_raw"])
            opts = [opt(o) for o in e["options_raw"]]
            src = opt(e["source_raw"]) if e["source_raw"] is not None else None
            out.append({"k": k, "seat": e["seat"], "kind": e["kind"], "options": opts, "default": e["default"],
                        "chosen": e["chosen"], "by": e["by"], "declaring": e["declaring"], "source": src, "state": st})
        else:
            st = state(e["state_raw"])
            args = [opt(a) if isinstance(a, dict) and "root" in a else a for a in e["args"]]
            out.append({"k": k, "seat": e["seat"], "win": e["win"], "state": st, "args": args, "out": e["out"]})
    out.append({"k": "end", "state": state(end)})
    return out, trees


FIELDS = {"decision": ("seat", "point", "win", "state", "menu", "action", "index"),
          "choice": ("seat", "kind", "options", "default", "chosen", "by", "declaring", "source", "state"),
          "rng": ("op", "n", "r"),
          "start": ("state",), "end": ("state",)}


def first_difference(py: list, rs: list, py_trees: dict, rs_trees: dict):
    """(index, field, python value, rust value, detail) of the first difference, or None."""
    for i, (a, b) in enumerate(zip(py, rs)):
        if a["k"] != b["k"]:
            return i, "k", a["k"], b["k"], None
        fields = FIELDS.get(a["k"], ("seat", "win", "state", "args", "out"))
        for f in fields:
            va, vb = a.get(f), b.get(f)
            if f == "args" and a["k"] != "decision":
                va = [x for x in (va or [])]
            if va != vb:
                detail = None
                if f == "state" and va in py_trees and vb in rs_trees:
                    detail = first_diff(py_trees[va], rs_trees[vb])
                elif f == "options":
                    detail = first_diff(va, vb)
                return i, f, va, vb, detail
    if len(py) != len(rs):
        return min(len(py), len(rs)), "len", len(py), len(rs), None
    return None


def compare_seed(seed: int, modo: str, net, starter: str = "a", verbose: bool = True, mu: str = "EK") -> dict:
    t0 = time.perf_counter()
    res, tr = python_game(seed, modo, net, starter, mu)
    t_py = time.perf_counter() - t0
    py_events = tr.events
    t0 = time.perf_counter()
    start, events, end, rres, err, _ = rust_events(seed, py_events, starter, mu)
    t_rs = time.perf_counter() - t0
    rs, rs_trees = canonical_rust_events(start, events, end)
    py_cmp = [e for e in py_events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    d = first_difference(py_cmp, rs, tr.states, rs_trees)
    out = {"seed": seed, "matchup": mu, "modo": modo, "starter": starter, "py": [res.winner, res.turns],
           "rs": list(rres) if rres else None, "rust_error": err, "events": len(py_cmp),
           "t_py_traced": round(t_py, 3), "t_rs_traced": round(t_rs, 3)}
    if d is not None:
        i, f, va, vb, detail = d
        ctx = [e for e in py_cmp[max(0, i - 3):i] if e["k"] != "rng"]
        out["first_difference"] = {"event": i, "field": f, "python": va, "rust": vb, "detail": detail,
                                   "python_event": {k: v for k, v in py_cmp[i].items() if k != "state"},
                                   "context": [{k: v for k, v in e.items() if k in ("k", "seat", "point", "kind", "action", "chosen", "win")} for e in ctx]}
    if verbose:
        print(json.dumps(out, default=str)[:3000])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", nargs="+", required=True, help="semi o intervalli a-b")
    ap.add_argument("--modo", choices=("self", "simple_trade"), default="self")
    ap.add_argument("--seme-rete", type=int, default=1)
    ap.add_argument("--matchup", default="EK", help="lettere di riftbound/rs/mazzi.py: il primo mazzo in A (EK, ER, KR; minuscola = con la sideboard: Er)")
    ap.add_argument("--posti", action="store_true", help="anche col matchup rovesciato (i mazzi ai due posti)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(args.seme_rete)
    net = PPONet().eval()
    seeds = []
    for s in args.semi:
        if "-" in s:
            a, b = s.split("-")
            seeds += list(range(int(a), int(b) + 1))
        else:
            seeds.append(int(s))
    rows = []
    mus = [args.matchup] + ([args.matchup[::-1]] if args.posti and args.matchup[0] != args.matchup[1] else [])
    for seed in seeds:
        starter = "a" if seed % 2 == 0 else "b"
        for mu in mus:
            rows.append(compare_seed(seed, args.modo, net, starter, verbose=True, mu=mu))
    ok = sum(1 for r in rows if "first_difference" not in r and not r["rust_error"])
    print(f"\n{ok}/{len(rows)} partite identiche")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
