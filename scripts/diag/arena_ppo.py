#!/usr/bin/env python
"""Arena della rete PPO contro il bot a mano (21/11, docs/PIANO_FORZA.md).

La rete (--ckpt, default runs/ppo1/corrente.pt) gioca senza ricerca, la
mossa col punteggio più alto; il bot a mano 0,4 s di CPU per mossa. Evelynn
(A) contro Kha'Zix (B), --pairs seed nuovi (da 3.000.000), per seed due
partite con la stessa apertura e i piloti scambiati, chi comincia alternato.
Regola (la solita): punteggio >= 0,52 e limite inferiore dell'IC 95% sulle
medie di coppia > 0,50 -> la rete batte il bot a mano.

  uv run --extra rl python scripts/diag/arena_ppo.py --pairs 200
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SEED0 = 3_000_000
_NET: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _game(task):
    from riftbound.ai.ppo.collect import play
    from riftbound.ai.ppo.model import load
    seed, seat, ckpt = task
    if ckpt not in _NET:
        _NET[ckpt] = load(ckpt).eval()
    other = "B" if seat == "A" else "A"
    g = play(seed, {seat: _NET[ckpt], other: None}, {}, sample=False, opponent="bot")
    return seed, seat, 1.0 if g["winner"] == seat else 0.5 if g["winner"] == "DRAW" else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", default=str(ROOT / "runs/ppo1/corrente.pt"))
    ap.add_argument("--pairs", type=int, default=200)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=ROOT / "runs/ppo1/ARENA_BOT.txt")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    say(f"\n== Rete PPO contro il bot a mano ({time.strftime('%d/%m %H:%M')}): {args.ckpt}")
    say("regola fissata prima: punteggio >= 0.52 e limite inferiore dell'IC 95% per coppia > 0.50")
    tasks = [(SEED0 + k, seat, args.ckpt) for k in range(args.pairs) for seat in ("A", "B")]
    t0, rows = time.time(), []
    with Pool(args.workers, initializer=_init) as pool:
        for r in pool.imap_unordered(_game, tasks):
            rows.append(r)
            if len(rows) % 50 == 0:
                print(f"   ... {len(rows)}/{len(tasks)} partite, {(time.time() - t0) / 60:.0f} min", flush=True)
    by: dict = {}
    for seed, _, s in rows:
        by.setdefault(seed, []).append(s)
    ps = [sum(v) / 2 for v in by.values()]
    m = sum(ps) / len(ps)
    h = 1.96 * math.sqrt(sum((x - m) ** 2 for x in ps) / max(1, len(ps) - 1)) / math.sqrt(len(ps))
    say(f"   punteggio della rete {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f}, {len(ps)} coppie); "
        f"vinte {sum(r[2] == 1.0 for r in rows)}, perse {sum(r[2] == 0.0 for r in rows)}")
    cells = []
    for seat, deck in (("A", "Evelynn"), ("B", "Kha'Zix")):
        for parity, who in ((0, "comincia Evelynn"), (1, "comincia Kha'Zix")):
            xs = [s for seed, se, s in rows if se == seat and seed % 2 == parity]
            cells.append(f"{deck}, {who} {sum(xs) / max(1, len(xs)):.2f}")
    say("   " + "; ".join(cells) + f"; {(time.time() - t0) / 60:.0f} min")
    ok = m >= 0.52 and m - h > 0.50
    say(f"   Esito: {'LA RETE BATTE IL BOT A MANO' if ok else 'non ancora'} "
        f"(punteggio {m:.3f}, limite inferiore {m - h:.3f})")


if __name__ == "__main__":
    main()
