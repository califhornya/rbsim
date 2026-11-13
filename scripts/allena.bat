@echo off
rem Double-click: self-play training on the two competitive decks, in
rem runs\competitive (it continues the run there, if any, for 50 more
rem iterations), mixing in the games coached in runs\coach (scripts\coach.py). 8 workers: one per core of a Ryzen 7 7800X3D; while using
rem the PC pass fewer, e.g.  allena.bat --workers 4
rem To stop it with everything saved: create a file named STOP in
rem runs\competitive (it stops after the current iteration).
cd /d "%~dp0.."
uv run python scripts\train_selfplay.py --decks riftbound\data\decks\competitive_kaisa.json riftbound\data\decks\competitive_kennen.json --iterations 50 --games-per-iter 16 --mcts-iters 100 --workers 8 --run-dir runs\competitive --coach-dir runs\coach --resume %*
pause
