#!/bin/bash
# Double-click in Finder (macOS): self-play training on the two competitive
# decks, in runs/competitive3 (it continues the run there, if any, for 60 more
# iterations). One worker per performance core (4 on an M1, 8 on an M1 Max);
# pass another number with
#   scripts/allena.command --workers 2
# caffeinate keeps the Mac awake while it runs (the screen may still sleep).
# To stop it with everything saved: create a file named STOP in
# runs/competitive3 (it stops after the current iteration).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run python scripts/train_selfplay.py \
    --decks riftbound/data/decks/competitive_kaisa.json riftbound/data/decks/competitive_kennen.json \
    --iterations 60 --games-per-iter 48 --mcts-iters 100 --fast-iters 16 \
    --full-fraction 0.25 --weight-decay 1e-4 --eval-games 40 --workers "$workers" \
    --run-dir runs/competitive3 --resume "$@"
read -r -p "Done. Press Enter to close."
