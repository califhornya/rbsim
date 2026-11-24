"""Parità dell'arena (porting Rust, tappa A): la stessa partita EK giocata dal
bot a mano (HandwrittenAgent) o dal bot coi prior PPO (PPOPriorAgent) su
Python e su Rust, a lavoro fisso (--iterazioni, default 50), con i semi e i
posti dell'arena (generatore dell'agente seme*2 + posto B, chi comincia per
parità del seme, PPOChooser sotto le scelte).

Confronta:
- la traccia della partita reale (come autonome.py: stato canonico, finestra,
  menu, azione, scelte, estrazioni), fino alla prima differenza;
- ogni ricerca: menu, prior della radice, visite, Q e W di ogni figlio,
  valore della radice, mossa, numero di nodi; e il mulligan (valore di ogni
  scelta). Si ferma alla prima riga diversa.

  python scripts/rust/arena_parita.py --semi 40000-40003 [--bot mano|prior] [--iterazioni 50] [--ckpt f.pt | --seme-rete 1]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))


def agent_seed(seed: int, seat: str) -> int:
    return seed * 2 + (seat == "B")


def _alist(a) -> list:
    return list(a.to_engine() if hasattr(a, "to_engine") else a)


def _count(node) -> int:
    return 1 + sum(_count(c) for c in node.children.values()) + sum(_count(c) for c in node.choices.values())


def _sub(node, depth: int) -> list:
    """The choice nodes tried below a node (key, N, Q, W, below), `depth` levels."""
    if depth == 0:
        return []
    return [[list(k), c.N, c.Q, c.W, _sub(c, depth - 1)] for k, c in node.choices.items() if c.N > 0]


def hook_python(log: list) -> None:
    """Rows of the Python search (NetGuidedMCTSAgent._conclude, decide_mulligan)."""
    import riftbound.ai.net_mcts as M
    if getattr(M.NetGuidedMCTSAgent, "_parita", False):
        M._PARITA_LOG = log
        return
    M._PARITA_LOG = log
    conclude, mull = M.NetGuidedMCTSAgent._conclude, M.NetGuidedMCTSAgent.decide_mulligan

    def _conclude(self, root, side, legal, point=M.DecisionPoint.TURN_ACTION):
        key = conclude(self, root, side, legal, point)
        M._PARITA_LOG.append({
            "k": "search", "seat": side, "point": point.value, "turn": self.gs.turn,
            "menu": [_alist(a) for a in legal], "value": root.value,
            "P": [[list(a), p] for a, p in root.P.items()],
            "children": [[list(a), c.N, c.Q, c.W, _sub(c, 3)] for a, c in root.children.items()],
            "action": list(key), "nodes": _count(root)})
        return key

    def decide_mulligan(self):
        rows = self.mulligan_values()
        best_combo, best_v = [], -1e30
        for combo, v in rows:
            if v > best_v:
                best_v, best_combo = v, combo
        M._PARITA_LOG.append({"k": "mulligan", "seat": self.player.name,
                              "values": [[c, v] for c, v in rows], "chosen": best_combo})
        return best_combo

    M.NetGuidedMCTSAgent._conclude = _conclude
    M.NetGuidedMCTSAgent.decide_mulligan = decide_mulligan
    M.NetGuidedMCTSAgent._parita = True
    _ = mull


def make_probs(net):
    """PPOPriorAgent._evaluate's forward and softmax, on Rust's arrays."""
    import torch

    def probs(x, q, ctx, otype, ocards, ofeats):
        n = len(otype)
        with torch.no_grad():
            logits, _ = net(torch.as_tensor(x[None]), torch.tensor([q]), torch.tensor([0]),
                            torch.as_tensor(ctx[None]), torch.as_tensor(otype[None]), torch.as_tensor(ocards[None]),
                            torch.as_tensor(ofeats[None]), torch.ones(1, n, dtype=torch.bool))
            return torch.softmax(logits[0], dim=0).numpy()
    return probs


def python_game(seed: int, starter: str, bot: str, iters: int, net):
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.ai.ppo.collect import EVE, KHA
    from riftbound.rs.trace_py import traced_game
    log: list = []
    hook_python(log)

    def factory(seat):
        rng = random.Random(agent_seed(seed, seat))
        if bot == "prior":
            from riftbound.ai.ppo.prior_bot import PPOPriorAgent
            return lambda p: PPOPriorAgent(p, net, rng=rng, budget=None, iterations=iters)
        return lambda p: HandwrittenAgent(p, iterations=iters, rng=rng)
    res, tr = traced_game(seed, EVE, KHA, {s: factory(s) for s in "AB"}, starter=starter, chooser="ppo",
                          with_obs=False, keep_states=True)
    return res, tr, log


def rust_game(seed: int, starter: str, bot: str, iters: int, net):
    from riftbound.ai.ppo.collect import EVE, KHA
    from riftbound.rs import rust_bridge as rb
    g = rb.build(seed, EVE, KHA, starter, 40)
    probs = make_probs(net) if bot == "prior" else None
    for s in "AB":
        g.set_search_agent(s, iters, agent_seed(seed, s), None, probs, True)
    g.set_side_chooser()
    start = json.loads(g.raw_dump())
    g.trace_on()
    err = None
    try:
        res = g.start()
    except RuntimeError as e:
        res, err = None, str(e)
    return start, json.loads(g.events()), json.loads(g.raw_dump()), res, err, _merge(g)


def _merge(g) -> list:
    """Rust keeps one log per seat."""
    return {"A": json.loads(g.search_log("A")), "B": json.loads(g.search_log("B"))}


# Labels that are an object's repr (py: str(PendingTrigger(...)), DeployedGear,
# FacedownCard, ChainItem): Rust builds another text with the same equality
# (search.rs, *_repr); only the tree's shape and numbers are compared there.
_REPR = ("PendingTrigger(", "PT(", "DeployedGear(", "DG(", "FacedownCard(", "FD(", "ChainItem(", "CI(")


def _norm(x):
    if isinstance(x, str) and x.startswith(_REPR):
        return "<repr>"
    if isinstance(x, list):
        return [_norm(v) for v in x]
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    return x


def first_search_difference(py_log: list, rs_logs: dict):
    py_log = _norm(py_log)
    rs_logs = {k: _norm(v) for k, v in rs_logs.items()}
    by_seat = {"A": [r for r in py_log if r["seat"] == "A"], "B": [r for r in py_log if r["seat"] == "B"]}
    for seat in "AB":
        a, b = by_seat[seat], rs_logs[seat]
        for i in range(max(len(a), len(b))):
            ra = a[i] if i < len(a) else None
            rb_ = b[i] if i < len(b) else None
            if ra != rb_:
                field = None
                if ra and rb_:
                    field = next((k for k in ra if ra.get(k) != rb_.get(k)), None)
                return {"seat": seat, "row": i, "field": field,
                        "python": ra if field is None else ra.get(field),
                        "rust": rb_ if field is None else rb_.get(field),
                        "context": {k: (ra or rb_ or {}).get(k) for k in ("k", "point", "turn")}}
    return None


def compare(seed: int, starter: str, bot: str, iters: int, net) -> dict:
    from diff_trace import FIELDS, canonical_rust_events, first_difference
    t0 = time.perf_counter()
    res, tr, py_log = python_game(seed, starter, bot, iters, net)
    t_py = time.perf_counter() - t0
    t0 = time.perf_counter()
    start, events, end, rres, err, rs_logs = rust_game(seed, starter, bot, iters, net)
    t_rs = time.perf_counter() - t0
    rs, rs_trees = canonical_rust_events(start, events, end)
    py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
    d = first_difference(py, rs, tr.states, rs_trees)
    out = {"seed": seed, "starter": starter, "bot": bot, "iterazioni": iters, "py": [res.winner, res.turns],
           "rs": list(rres) if rres else None, "rust_error": err, "events": len(py),
           "ricerche": len([r for r in py_log if r["k"] == "search"]),
           "t_py": round(t_py, 2), "t_rs": round(t_rs, 2)}
    if d is not None:
        i, f, va, vb, detail = d
        out["first_difference"] = {"event": i, "field": f, "python": va, "rust": vb, "detail": detail,
                                   "python_event": {k: v for k, v in py[i].items() if k != "state"},
                                   "rust_event": {k: v for k, v in rs[i].items() if k != "state"} if i < len(rs) else None}
    s = first_search_difference(py_log, rs_logs)
    if s is not None:
        out["search_difference"] = s
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", nargs="+", required=True, help="semi o intervalli a-b")
    ap.add_argument("--bot", choices=("mano", "prior"), default="mano")
    ap.add_argument("--iterazioni", type=int, default=50)
    ap.add_argument("--ckpt", default=None, help="i pesi del prior (default: PPONet() da --seme-rete)")
    ap.add_argument("--seme-rete", type=int, default=1)
    ap.add_argument("--out", default=None)
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    seeds = []
    for s in args.semi:
        if "-" in s:
            a, b = s.split("-")
            seeds += list(range(int(a), int(b) + 1))
        else:
            seeds.append(int(s))
    net = None
    if args.bot == "prior":
        import torch
        torch.set_num_threads(1)
        from riftbound.ai.ppo.model import PPONet, load
        torch.manual_seed(args.seme_rete)
        net = (load(args.ckpt) if args.ckpt else PPONet()).eval()
    rows = []
    for seed in seeds:
        starter = "a" if seed % 2 == 0 else "b"
        r = compare(seed, starter, args.bot, args.iterazioni, net)
        rows.append(r)
        ok = "first_difference" not in r and "search_difference" not in r and not r["rust_error"]
        print(f"{seed}: identiche ({r['events']} eventi, {r['ricerche']} ricerche, {r['py']}, "
              f"py {r['t_py']} s, rs {r['t_rs']} s)" if ok else json.dumps(r, default=str)[:3000], flush=True)
        if args.stop and not ok:
            break
    ok = sum(1 for r in rows if "first_difference" not in r and "search_difference" not in r and not r["rust_error"])
    print(f"\n{ok}/{len(rows)} partite identiche (bot {args.bot}, {args.iterazioni} iterazioni)")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
