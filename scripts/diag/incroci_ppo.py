#!/usr/bin/env python
"""Incroci tra checkpoint PPO (22/11): la rete ha continuato a migliorare
dopo che la misura contro simple_trade si è appiattita? Ogni coppia di
checkpoint gioca --pairs seed nuovi (da 4.000.000), due partite per seed con
la stessa apertura e i piloti scambiati, mossa col punteggio più alto.
Riporta il punteggio del checkpoint più recente con l'IC 95% per coppia.

  uv run --extra rl python scripts/diag/incroci_ppo.py runs/ppo1/ckpt_005056.pt runs/ppo1/ckpt_015040.pt runs/ppo1/ckpt_030016.pt
"""
from __future__ import annotations

import argparse
import itertools
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SEED0 = 4_000_000
_NETS: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _net(path):
    from riftbound.ai.ppo.model import load
    if path not in _NETS:
        _NETS[path] = load(path).eval()
    return _NETS[path]


def _game(task):
    from riftbound.ai.ppo.collect import play
    seed, seat, new, old = task
    other = "B" if seat == "A" else "A"
    g = play(seed, {seat: _net(new), other: _net(old)}, {}, sample=False)
    return new, old, seed, seat, 1.0 if g["winner"] == seat else 0.5 if g["winner"] == "DRAW" else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ckpts", nargs="+")
    ap.add_argument("--pairs", type=int, default=200)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=ROOT / "runs/ppo1/INCROCI.txt")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    say(f"\n== Incroci tra checkpoint PPO ({time.strftime('%d/%m %H:%M')}), {args.pairs} coppie per incrocio")
    t0 = time.time()
    tasks = [(SEED0 + k, seat, new, old) for old, new in itertools.combinations(args.ckpts, 2)
             for k in range(args.pairs) for seat in ("A", "B")]
    with Pool(args.workers, initializer=_init) as pool:
        rows = pool.map(_game, tasks, chunksize=16)
    for old, new in itertools.combinations(args.ckpts, 2):
        by: dict = {}
        for n, o, seed, seat, s in rows:
            if n == new and o == old:
                by.setdefault(seed, []).append(s)
        ps = [sum(v) / 2 for v in by.values()]
        m = sum(ps) / len(ps)
        h = 1.96 * math.sqrt(sum((x - m) ** 2 for x in ps) / max(1, len(ps) - 1)) / math.sqrt(len(ps))
        say(f"   {Path(new).stem} contro {Path(old).stem}: {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f})")
    say(f"   ({(time.time() - t0) / 60:.0f} min)")


if __name__ == "__main__":
    main()
