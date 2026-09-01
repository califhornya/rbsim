#!/usr/bin/env python
"""Headless AlphaZero-style self-play training (RL Chunk 4).

Run on a (rented, GPU) machine after `uv sync --extra rl`:

    uv run python scripts/train_selfplay.py \
        --deck-a riftbound/data/decks/vendetta_kennen.json \
        --deck-b riftbound/data/decks/vendetta_ornn.json \
        --iterations 50 --games-per-iter 16 --mcts-iters 200 \
        --checkpoint runs/net.pt

CUDA is used automatically when available. Resume by passing --resume <checkpoint>.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Riftbound self-play training")
    ap.add_argument("--deck-a", type=Path, required=True)
    ap.add_argument("--deck-b", type=Path, required=True)
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument("--games-per-iter", type=int, default=8)
    ap.add_argument("--mcts-iters", type=int, default=200)
    ap.add_argument("--train-steps", type=int, default=64)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--buffer-size", type=int, default=50000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--checkpoint", type=Path, default=None)
    ap.add_argument("--resume", type=Path, default=None)
    args = ap.parse_args()

    # torch imports are inside main so `--help` works without the rl extra installed.
    from riftbound.ai.net import RiftboundNet, default_device, load_checkpoint
    from riftbound.ai.selfplay import run_training

    device = default_device()
    net = load_checkpoint(args.resume, device=device) if args.resume else RiftboundNet()
    print(f"device={device}  resume={args.resume}")
    if args.checkpoint:
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    run_training(
        net, args.deck_a, args.deck_b,
        iterations=args.iterations, games_per_iter=args.games_per_iter,
        mcts_iters=args.mcts_iters, train_steps=args.train_steps,
        batch_size=args.batch_size, lr=args.lr, buffer_size=args.buffer_size,
        checkpoint=args.checkpoint, seed=args.seed, device=device,
    )
    print("done.")


if __name__ == "__main__":
    main()
