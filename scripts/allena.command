#!/bin/bash
# Double-click in Finder (macOS): self-play training on the two competitive
# decks, in runs/competitive4: 30 iterations starting from run 3's last net
# (runs/competitive3/net_0060.pt), the policy learning from the search's
# values (--policy-target q) instead of its visits. Launched again, it
# continues the run there for 30 more iterations. One worker per performance
# core (4 on an M1, 8 on an M1 Max); pass another number with
#   scripts/allena.command --workers 2
# caffeinate keeps the Mac awake while it runs (the screen may still sleep).
# To stop it with everything saved: create a file named STOP in
# runs/competitive4 (it stops after the current iteration).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run python scripts/train_selfplay.py \
    --decks riftbound/data/decks/competitive_kaisa.json riftbound/data/decks/competitive_kennen.json \
    --iterations 30 --games-per-iter 48 --mcts-iters 100 --fast-iters 16 \
    --full-fraction 0.25 --weight-decay 1e-4 --eval-games 40 --workers "$workers" \
    --policy-target q --init runs/competitive3/net_0060.pt \
    --run-dir runs/competitive4 --resume "$@"
read -r -p "Done. Press Enter to close."
