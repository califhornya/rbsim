"""Partite EK in Python per l'inventario (coverage) e per le tracce: PPO a
pesi dal seme (self-play, `collect.play` come la raccolta) oppure PPO contro
simple_trade / random, semi da `--primo` per `--partite`.

  python scripts/rust/partite_ek.py --modo self --primo 0 --partite 50 [--seme 1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=("self", "simple_trade", "random", "bot"), default="self")
    ap.add_argument("--primo", type=int, default=0)
    ap.add_argument("--partite", type=int, default=50)
    ap.add_argument("--seme", type=int, default=1)
    args = ap.parse_args()
    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo.collect import play
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(args.seme)
    net = PPONet().eval()
    wins = {}
    for i in range(args.primo, args.primo + args.partite):
        seed = 1_000_000 + args.seme * 10_000_000 + i
        if args.modo == "self":
            g = play(seed, {"A": net, "B": net}, {"A": True, "B": True}, sample=True,
                     starter="a" if i % 2 == 0 else "b")
        else:
            seat = "A" if i % 2 == 0 else "B"
            g = play(seed, {seat: net}, {}, sample=False, starter="a" if (i // 2) % 2 == 0 else "b",
                     opponent=args.modo)
        wins[g["winner"]] = wins.get(g["winner"], 0) + 1
    print(args.modo, wins)


if __name__ == "__main__":
    main()
