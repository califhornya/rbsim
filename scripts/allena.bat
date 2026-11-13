@echo off
rem Double-click: self-play training on the two competitive decks, in
rem runs\competitive3 (it continues the run there, if any, for 60 more
rem iterations). 8 workers: one per core of a Ryzen 7 7800X3D; while using
rem the PC pass fewer, e.g.  allena.bat --workers 4
rem To stop it with everything saved: create a file named STOP in
rem runs\competitive3 (it stops after the current iteration).
cd /d "%~dp0.."
uv run python scripts\train_selfplay.py --decks riftbound\data\decks\competitive_kaisa.json riftbound\data\decks\competitive_kennen.json --iterations 60 --games-per-iter 48 --mcts-iters 100 --fast-iters 16 --full-fraction 0.25 --weight-decay 1e-4 --eval-games 40 --workers 8 --run-dir runs\competitive3 --resume %*
pause
