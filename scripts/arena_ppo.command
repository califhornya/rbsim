#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: la rete PPO contro il bot a
# mano (scripts/diag/arena_ppo.py), 200 coppie, il bot a 0,4 s per mossa.
# Circa 10-15 minuti su un M1 Max. Un checkpoint diverso da quello corrente:
#   scripts/arena_ppo.command --ckpt runs/ppo1/ckpt_005056.pt
# Risultato: runs/ppo1/ARENA_BOT.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/diag/arena_ppo.py --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
