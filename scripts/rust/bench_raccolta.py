"""Raccolta PPO su un core, Python contro Rust (porting, F6): le stesse
partite (semi, rete, posti) giocate da collect.play e da collect_rs.play,
in ordine alternato (un seme Python poi Rust, il successivo Rust poi
Python), senza tracce. Per Rust separa il tempo della rete in Python
(AskPPO: forward e campionamento) dal resto (motore, osservazione,
descrittori, attraversamenti PyO3). Riporta tempi grezzi, mediana,
deviazione e il totale; il caricamento del modulo e della rete a parte.

  python scripts/rust/bench_raccolta.py --semi 1-60 [--avversario simple_trade] [--init ckpt.pt] [--out f.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import os  # noqa: E402
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", default="1-60")
    ap.add_argument("--avversario", default=None)
    ap.add_argument("--seme-rete", type=int, default=1)
    ap.add_argument("--init", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    t0 = time.perf_counter()
    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo import collect
    from riftbound.ai.ppo.model import PPONet
    from riftbound.rs import agent_rs, collect_rs
    from riftbound.rs import rust_bridge as rb
    rb.registry()
    torch.manual_seed(args.seme_rete)
    net = PPONet().eval()
    what = f"PPONet() dal seme {args.seme_rete}"
    if args.init:
        from riftbound.ai.ppo.model import load
        net = load(args.init).eval()
        what = args.init
    sha = hashlib.sha256(b"".join(v.numpy().tobytes() for v in net.state_dict().values())).hexdigest()[:16]
    t_load = time.perf_counter() - t0
    # Time spent in the net on the Rust path (AskPPO.__call__).
    net_time = [0.0]
    call = agent_rs.AskPPO.__call__

    def timed(self, *a):
        s = time.perf_counter()
        try:
            return call(self, *a)
        finally:
            net_time[0] += time.perf_counter() - s
    agent_rs.AskPPO.__call__ = timed
    a, _, b = args.semi.partition("-")
    seeds = list(range(int(a), int(b or a) + 1))
    nets = {"A": net, "B": None if args.avversario else net}
    learners = {"A": True, "B": not args.avversario}
    rows = []
    for k, seed in enumerate(seeds):
        times = {}
        order = ("python", "rust") if k % 2 == 0 else ("rust", "python")
        for eng in order:
            play = collect.play if eng == "python" else collect_rs.play
            net_time[0] = 0.0
            s = time.perf_counter()
            g = play(seed, nets, learners, sample=True, opponent=args.avversario)
            times[eng] = time.perf_counter() - s
            if eng == "rust":
                times["rust_rete"] = net_time[0]
            times[f"{eng}_esempi"] = sum(map(len, g["records"].values()))
        rows.append({"seme": seed, **{k2: round(v, 5) if isinstance(v, float) else v for k2, v in times.items()}})

    def st(xs):
        return {"totale_s": round(sum(xs), 3), "mediana_ms": round(1000 * statistics.median(xs), 2),
                "dev_std_ms": round(1000 * statistics.pstdev(xs), 2), "min_ms": round(1000 * min(xs), 2),
                "max_ms": round(1000 * max(xs), 2)}
    py = [r["python"] for r in rows]
    rs = [r["rust"] for r in rows]
    rs_net = [r["rust_rete"] for r in rows]
    rep = {"cosa": "bench_raccolta (un core, ordine alternato, senza tracce)",
           "macchina": platform.node(), "cpu": platform.processor() or platform.machine(),
           "versione_python": sys.version.split()[0], "torch": torch.__version__, "thread_torch": 1,
           "pesi": what, "pesi_sha256_16": sha, "avversario": args.avversario or "self-play",
           "semi": args.semi, "partite": len(rows), "caricamento_s": round(t_load, 3),
           "python": st(py), "rust": st(rs), "rust_rete": st(rs_net),
           "rust_motore_e_confine": st([x - y for x, y in zip(rs, rs_net)]),
           "rapporto_totale": round(sum(py) / sum(rs), 2), "esempi": sum(r["python_esempi"] for r in rows),
           "partite_grezze": rows}
    print(json.dumps({k: v for k, v in rep.items() if k != "partite_grezze"}, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(rep, indent=1) + "\n")


if __name__ == "__main__":
    main()
