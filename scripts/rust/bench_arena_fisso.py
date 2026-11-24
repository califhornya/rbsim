"""F0 (porting Rust): l'arena EK con lo stesso bot nei due posti
(PPOPriorAgent, stesso checkpoint), a lavoro fisso (`--iterazioni N`, budget
None: costruito direttamente, non con arena_bot._make che rimette 0,4 s) o a
tempo (`--budget 0.4`). Semi appaiati, posti scambiati (ogni seme due volte),
chi comincia per parità del seme, come arena_bot._game.

Riporta tempo di parete e CPU per partita, decisioni di ricerca, iterazioni
per decisione principale e (in un processo) la quota del forward del prior,
di osservazione + descrittori e del resto (motore della ricerca).

  python scripts/rust/bench_arena_fisso.py --coppie 4 --iterazioni 50 [--ckpt f.pt | --seme 1] [--out f.json]
  python scripts/rust/bench_arena_fisso.py --coppie 4 --budget 0.4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))

from bench_ppo_split import Timer  # noqa: E402

SEED0 = 40_000      # arena_mazzi: --seed0 40000 + 1000 * ORDER.index("EK") (EK è il primo)


def weights_sha(net) -> str:
    return hashlib.sha256(b"".join(t.detach().cpu().numpy().tobytes()
                                   for t in net.state_dict().values())).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coppie", type=int, default=4)
    ap.add_argument("--seed0", type=int, default=SEED0)
    ap.add_argument("--iterazioni", type=int, default=None)
    ap.add_argument("--budget", type=float, default=None)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--seme", type=int, default=1, help="senza --ckpt: PPONet() dal seme")
    ap.add_argument("--out", default=None)
    ap.add_argument("--motore", choices=("python", "rust"), default="python",
                    help="rust: la ricerca su riftbound_rs (riftbound/rs/arena_rs.py), il prior in Python")
    args = ap.parse_args()
    assert (args.iterazioni is None) != (args.budget is None), "--iterazioni oppure --budget"

    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo import features as F
    from riftbound.ai.ppo import prior_bot as PB
    from riftbound.ai.ppo.agent import PPOChooser
    from riftbound.ai.ppo.collect import EVE, KHA, MAX_TURNS
    from riftbound.ai.ppo.model import PPONet, load
    from riftbound.core import decisions as D
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop

    torch.manual_seed(args.seme)
    net = (load(args.ckpt) if args.ckpt else PPONet()).eval()

    T = Timer()
    PB.encode_observation = T.wrap("osservazione", PB.encode_observation)
    D.Observation.from_state = classmethod(T.wrap("osservazione", D.Observation.from_state.__func__))
    F.describe_action = T.wrap("descrittori", F.describe_action)
    fwd = T.wrap("rete", net.__call__)

    class TimedNet:
        def __call__(self, *a, **kw):
            return fwd(*a, **kw)

        def eval(self):
            return self

    tnet = TimedNet()
    if args.motore == "rust":
        return rust_bench(args, net, T, torch)
    games = []
    for k in range(args.coppie):
        seed = args.seed0 + k
        starter = "a" if seed % 2 == 0 else "b"
        for cand in ("A", "B"):
            games.append((seed, starter, cand))
    rows = []
    t_all = time.perf_counter()
    for seed, starter, cand in games:
        gs = build_game(game_seed=seed, deck_a_path=EVE, deck_b_path=KHA, ai_a=None, ai_b=None,
                        max_turns=MAX_TURNS, first_player=starter)
        searches = {"n": 0}
        for seat in ("A", "B"):
            p = gs.get_player(seat)
            rng = random.Random(seed * 2 + (seat == "B"))
            ag = PB.PPOPriorAgent(p, tnet, rng=rng, budget=args.budget,
                                  **({"iterations": args.iterazioni} if args.iterazioni else {}))
            orig = ag.search

            def counted(*a, _orig=orig, **kw):
                searches["n"] += 1
                return _orig(*a, **kw)
            ag.search = counted
            p.agent = ag
        loop = GameLoop(gs)
        loop.chooser = PPOChooser(gs)
        w0, c0 = time.perf_counter(), time.process_time()
        res = T.wrap("partita", loop.start)()
        w, c = time.perf_counter() - w0, time.process_time() - c0
        iters = gs.A.agent.main_iters + gs.B.agent.main_iters
        rows.append({"seme": seed, "comincia": starter, "candidato": cand, "vincitore": res.winner,
                     "turni": gs.turn, "parete_s": round(w, 3), "cpu_s": round(c, 3), "ricerche": searches["n"],
                     "iter_medie_principali": round(statistics.mean(iters), 1) if iters else None})
        print(json.dumps(rows[-1]), flush=True)
    total = time.perf_counter() - t_all
    T.tot["motore e ricerca"] = T.tot.pop("partita", 0.0)
    walls = [r["parete_s"] for r in rows]
    out = {
        "cosa": "bench_arena_fisso", "motore": "python", "macchina": platform.node(),
        "cpu": platform.processor() or platform.machine(), "python": sys.version.split()[0],
        "torch": torch.__version__, "thread_torch": 1, "processi": 1, "mazzi": "EK",
        "bot": "PPOPriorAgent (stesso checkpoint nei due posti)",
        "pesi": args.ckpt or f"PPONet() dal seme {args.seme}", "pesi_sha256_16": weights_sha(net),
        "lavoro": {"iterazioni": args.iterazioni} if args.iterazioni else {"budget_cpu_s": args.budget},
        "semi": [args.seed0, args.seed0 + args.coppie - 1], "partite": len(rows),
        "totale_s": round(total, 3), "mediana_parete_s": statistics.median(walls),
        "minimo_parete_s": min(walls), "massimo_parete_s": max(walls),
        "quote": {k: round(v / total, 4) for k, v in sorted(T.tot.items(), key=lambda kv: -kv[1])},
        "chiamate": T.calls, "partite_dettaglio": rows,
    }
    print(json.dumps({k: v for k, v in out.items() if k != "partite_dettaglio"}, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1) + "\n")


def rust_bench(args, net, T, torch) -> None:
    """The same games on the Rust engine: the search in Rust, the prior's
    forward and softmax in Python (timed as "rete")."""
    from riftbound.ai.ppo.collect import EVE, KHA, MAX_TURNS
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.arena_rs import make_probs
    probs = T.wrap("rete", make_probs(net))
    rows = []
    t_all = time.perf_counter()
    for k in range(args.coppie):
        seed = args.seed0 + k
        starter = "a" if seed % 2 == 0 else "b"
        for cand in ("A", "B"):
            g = rb.build(seed, EVE, KHA, starter, MAX_TURNS)
            for seat in ("A", "B"):
                g.set_search_agent(seat, args.iterazioni or 100, seed * 2 + (seat == "B"), args.budget, probs, False)
            g.set_side_chooser()
            w0, c0 = time.perf_counter(), time.process_time()
            winner, turns = T.wrap("partita", g.start)()
            w, c = time.perf_counter() - w0, time.process_time() - c0
            iters = list(g.search_stats("A")[0]) + list(g.search_stats("B")[0])
            rows.append({"seme": seed, "comincia": starter, "candidato": cand, "vincitore": winner, "turni": turns,
                         "parete_s": round(w, 3), "cpu_s": round(c, 3),
                         "iter_medie_principali": round(statistics.mean(iters), 1) if iters else args.iterazioni})
            print(json.dumps(rows[-1]), flush=True)
    total = time.perf_counter() - t_all
    T.tot["motore e ricerca"] = T.tot.pop("partita", 0.0)
    walls = [r["parete_s"] for r in rows]
    out = {
        "cosa": "bench_arena_fisso", "motore": "rust", "macchina": platform.node(),
        "cpu": platform.processor() or platform.machine(), "python": sys.version.split()[0],
        "torch": torch.__version__, "thread_torch": 1, "processi": 1, "mazzi": "EK",
        "bot": "PPOPriorAgent su Rust (stesso checkpoint nei due posti)",
        "pesi": args.ckpt or f"PPONet() dal seme {args.seme}", "pesi_sha256_16": weights_sha(net),
        "lavoro": {"iterazioni": args.iterazioni} if args.iterazioni else {"budget_cpu_s": args.budget},
        "semi": [args.seed0, args.seed0 + args.coppie - 1], "partite": len(rows),
        "totale_s": round(total, 3), "mediana_parete_s": statistics.median(walls),
        "minimo_parete_s": min(walls), "massimo_parete_s": max(walls),
        "quote": {k: round(v / total, 4) for k, v in sorted(T.tot.items(), key=lambda kv: -kv[1])},
        "chiamate": T.calls, "partite_dettaglio": rows,
    }
    print(json.dumps({k: v for k, v in out.items() if k != "partite_dettaglio"}, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
