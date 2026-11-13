@echo off
rem Double-click: self-play training on the two competitive decks, in
rem runs\competitive4: 30 iterations starting from run 3's last net
rem (runs\competitive3\net_0060.pt, run on the Mac: copy it here first), the
rem policy learning from the search's values (--policy-target q) instead of
rem its visits. Launched again, it continues the run there for 30 more
rem iterations. 8 workers: one per core of a Ryzen 7 7800X3D; while using
rem the PC pass fewer, e.g.  allena.bat --workers 4
rem To stop it with everything saved: create a file named STOP in
rem runs\competitive4 (it stops after the current iteration).
cd /d "%~dp0.."
uv run python scripts\train_selfplay.py --decks riftbound\data\decks\competitive_kaisa.json riftbound\data\decks\competitive_kennen.json --iterations 30 --games-per-iter 48 --mcts-iters 100 --fast-iters 16 --full-fraction 0.25 --weight-decay 1e-4 --eval-games 40 --workers 8 --policy-target q --init runs\competitive3\net_0060.pt --run-dir runs\competitive4 --resume %*
pause
