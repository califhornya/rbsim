"""Parità del ciclo PPO Python / Rust col pool (porting): gli stessi cicli di
scripts/rust/bench_ppo_ciclo.py (raccolta con i processi di ppo.py, poi
aggiornamento), con l'hash degli esempi e dei pesi dopo ogni ciclo. Con
motori equivalenti gli hash coincidono a ogni ciclo, non solo al primo: è
la prova che l'aggiornamento riceve lo stesso input.

  python scripts/rust/parita_ciclo.py --motore python --cicli 3 --workers 4
  python scripts/rust/parita_ciclo.py --motore rust --cicli 3 --workers 4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "scripts"))


def records_digest(recs: list) -> str:
    import numpy as np
    h = hashlib.sha256()
    for r in recs:
        for k in sorted(r):
            v = r[k]
            h.update(k.encode())
            h.update(np.asarray(v).tobytes() if hasattr(v, "shape") else repr(v).encode())
    return h.hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--motore", choices=("python", "rust"), required=True)
    ap.add_argument("--cicli", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-aggiornamento", type=int, default=64)
    ap.add_argument("--seme", type=int, default=1)
    ap.add_argument("--init", default=None)
    args = ap.parse_args()
    os.environ["RBSIM_MOTORE"] = args.motore
    import ppo as P
    import torch
    from riftbound.ai.ppo.model import PPONet, load
    from riftbound.ai.ppo.train import update
    torch.manual_seed(args.seme)
    net = load(args.init) if args.init else PPONet()
    torch.set_num_threads(args.workers)
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)
    rng = random.Random(args.seme * 1_000_003)
    pool = Pool(args.workers, initializer=P._init)
    done = 0
    for c in range(args.cicli):
        cur = (f"w{c}", P._blob(net))
        games = P.batch_games(done, args.per_aggiornamento, args.seme, [], rng, "bilanciata", "recenti", "ek")
        res = pool.map(P._collect, [(ch, cur, {}, 0.98) for ch in P._chunks(games, args.workers)])
        recs = [r for rs, _ in res for r in rs]
        torch.manual_seed(args.seme * 100_003 + c)
        update(net, opt, recs)
        done += len(games)
        w = hashlib.sha256(b"".join(t.detach().numpy().tobytes() for t in net.state_dict().values())).hexdigest()[:16]
        print(json.dumps({"motore": args.motore, "ciclo": c, "esempi": len(recs), "esempi_sha": records_digest(recs),
                          "pesi_sha": w}), flush=True)
    pool.close()


if __name__ == "__main__":
    main()
