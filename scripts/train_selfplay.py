#!/usr/bin/env python
"""Headless AlphaZero-style self-play training (RL Chunk 4).

After `uv sync --extra rl`:

    uv run python scripts/train_selfplay.py \
        --decks riftbound/data/decks/precon_zed.json riftbound/data/decks/precon_shen.json \
        --iterations 50 --games-per-iter 16 --mcts-iters 100 --run-dir runs/precons

Each game draws two decks from --decks (mirrors included). Games run in
--workers processes (default: a quarter of the cores, below-normal priority, one
thread each; riftbound/compute.py), with --pause seconds between iterations, so
the machine keeps plenty of headroom. Every --eval-every iterations the net plays
--eval-games games against each --eval-vs agent (simple_trade, and random as a
sanity check). The run directory holds the checkpoint (net.pt) and one JSON line
per iteration (log.jsonl); --resume continues it. A file named STOP in the run
directory ends the run after the current iteration, everything saved.
"""
from __future__ import annotations

import argparse
import functools
import glob
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Riftbound self-play training")
    ap.add_argument("--decks", nargs="+", required=True, help="Deck files or globs")
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument("--games-per-iter", type=int, default=16)
    ap.add_argument("--mcts-iters", type=int, default=100)
    ap.add_argument("--train-steps", type=int, default=0,
                    help="Gradient steps per iteration (0: each new example seen ~twice)")
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--buffer-size", type=int, default=50000)
    ap.add_argument("--workers", type=int, default=None,
                    help="Game processes (default: a quarter of the cores; 0: this process)")
    ap.add_argument("--eval-every", type=int, default=5)
    ap.add_argument("--eval-games", type=int, default=20, help="Games against each --eval-vs agent")
    ap.add_argument("--eval-vs", nargs="+", default=["simple_trade", "random"])
    ap.add_argument("--pause", type=float, default=10.0, help="Seconds of rest between iterations")
    ap.add_argument("--rest", type=float, default=0.0, help="Seconds of rest after each game")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--resume", action="store_true", help="Continue the run in --run-dir")
    args = ap.parse_args()

    decks = [Path(p) for pattern in args.decks for p in (sorted(glob.glob(pattern)) or [pattern])]
    # torch imports are inside main so `--help` works without the rl extra installed.
    from riftbound.ai.net import RiftboundNet, load_checkpoint
    from riftbound.ai.selfplay import train
    import torch

    args.run_dir.mkdir(parents=True, exist_ok=True)
    ckpt, log_path = args.run_dir / "net.pt", args.run_dir / "log.jsonl"
    start = 0
    if args.resume and ckpt.exists():
        net = load_checkpoint(ckpt, device=torch.device("cpu"))
        if log_path.exists():
            lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
            start = lines[-1]["iteration"] if lines else 0
    else:
        net = RiftboundNet()
    log = functools.partial(print, flush=True)       # a redirected log stays current
    log(f"decks={[d.name for d in decks]} start={start}")

    train(
        net, decks,
        iterations=args.iterations, games_per_iter=args.games_per_iter,
        mcts_iters=args.mcts_iters, train_steps=args.train_steps,
        batch_size=args.batch_size, lr=args.lr, buffer_size=args.buffer_size,
        checkpoint=ckpt, log_path=log_path, start_iteration=start, seed=args.seed + start,
        workers=args.workers, eval_every=args.eval_every, eval_games=args.eval_games,
        eval_vs=args.eval_vs,
        pause=args.pause, rest=args.rest, log=log,
    )
    log("done.")


if __name__ == "__main__":
    main()
