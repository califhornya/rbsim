#!/bin/bash
# Double-click in Finder (macOS): self-play training on the two competitive
# decks, in runs/competitive (it continues the run there, if any, for 50 more
# iterations), mixing in the games coached in runs/coach (scripts/coach.py). 4 workers: the performance cores of an M1; pass others with
#   scripts/allena.command --workers 2
# caffeinate keeps the Mac awake while it runs (the screen may still sleep).
# To stop it with everything saved: create a file named STOP in
# runs/competitive (it stops after the current iteration).
cd "$(dirname "$0")/.." || exit 1
caffeinate -i uv run python scripts/train_selfplay.py \
    --decks riftbound/data/decks/competitive_kaisa.json riftbound/data/decks/competitive_kennen.json \
    --iterations 50 --games-per-iter 16 --mcts-iters 100 --workers 4 \
    --run-dir runs/competitive --coach-dir runs/coach --resume "$@"
read -r -p "Done. Press Enter to close."
