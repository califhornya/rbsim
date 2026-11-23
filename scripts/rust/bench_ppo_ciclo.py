"""F0 (porting Rust): il tempo di un ciclo PPO (raccolta + aggiornamento),
con le funzioni di `scripts/ppo.py` (batch_games, _collect, update) ma
cronometrato al millisecondo e senza pannelli. Stessi semi, stessi pesi dal
seme (`--seme`) o `--init`. Il primo ciclo è il riscaldamento (riportato a
parte). `--motore` sceglie il motore della raccolta (python | rust).

  python scripts/rust/bench_ppo_ciclo.py --cicli 4 --workers 4 --seme 1 [--init ckpt] [--out f.json]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import random
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _ppo():
    spec = importlib.util.spec_from_file_location("ppo_script", ROOT / "scripts/ppo.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ppo_script"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cicli", type=int, default=4, help="cicli misurati, dopo uno di riscaldamento")
    ap.add_argument("--per-aggiornamento", type=int, default=64)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--seme", type=int, default=1)
    ap.add_argument("--init", default=None)
    ap.add_argument("--motore", choices=("python", "rust"), default="python")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.motore == "rust":
        os.environ["RBSIM_MOTORE"] = "rust"

    P = _ppo()
    import torch
    from riftbound.ai.ppo.model import PPONet, load
    from riftbound.ai.ppo.train import update

    torch.manual_seed(args.seme)
    net = load(args.init) if args.init else PPONet()
    wsha = hashlib.sha256(b"".join(t.detach().cpu().numpy().tobytes() for t in net.state_dict().values())).hexdigest()[:16]
    torch.set_num_threads(max(1, args.workers))
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)
    rng = random.Random(args.seme * 1_000_003)
    t_start = time.perf_counter()
    pool = Pool(args.workers, initializer=P._init)
    t_pool = time.perf_counter() - t_start
    rows = []
    done = 0
    for c in range(args.cicli + 1):
        cur = (f"w{c}", P._blob(net))
        games = P.batch_games(done, args.per_aggiornamento, args.seme, [], rng, "bilanciata", "recenti", "ek")
        t1 = time.perf_counter()
        res = pool.map(P._collect, [(ch, cur, {}, 0.98) for ch in P._chunks(games, args.workers)])
        recs = [r for rs, _ in res for r in rs]
        info = [o for _, out in res for o in out]
        t_col = time.perf_counter() - t1
        torch.manual_seed(args.seme * 100_003 + c)
        t1 = time.perf_counter()
        update(net, opt, recs)
        t_upd = time.perf_counter() - t1
        done += len(games)
        rows.append({"ciclo": c, "raccolta_s": round(t_col, 3), "aggiornamento_s": round(t_upd, 3),
                     "esempi": len(recs), "turni_medi": round(sum(o["turns"] for o in info) / len(info), 2)})
        print(json.dumps(rows[-1]), flush=True)
    pool.close()
    meas = rows[1:]
    col = [r["raccolta_s"] for r in meas]
    upd = [r["aggiornamento_s"] for r in meas]
    cyc = [a + b for a, b in zip(col, upd)]
    out = {
        "cosa": "bench_ppo_ciclo", "motore": args.motore, "macchina": platform.node(),
        "cpu": platform.processor() or platform.machine(), "python": sys.version.split()[0],
        "torch": torch.__version__, "processi": args.workers, "thread_torch_aggiornamento": torch.get_num_threads(),
        "thread_torch_raccolta": 1, "mazzi": "EK", "seme": args.seme,
        "pesi": args.init or f"PPONet() dal seme {args.seme}", "pesi_sha256_16": wsha,
        "partite_per_ciclo": args.per_aggiornamento, "avvio_pool_s": round(t_pool, 3),
        "riscaldamento": rows[0], "cicli": meas,
        "mediana": {"raccolta_s": statistics.median(col), "aggiornamento_s": statistics.median(upd),
                    "ciclo_s": statistics.median(cyc)},
        "quota_aggiornamento": round(statistics.median(upd) / statistics.median(cyc), 3),
        "partite_ora_raccolta": round(3600 * args.per_aggiornamento / statistics.median(col)),
        "partite_ora_ciclo": round(3600 * args.per_aggiornamento / statistics.median(cyc)),
    }
    print(json.dumps({k: v for k, v in out.items() if k not in ("cicli",)}, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
