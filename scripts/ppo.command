#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: un allenamento PPO
# (scripts/ppo.py, docs/PIANO_FORZA.md). Una rete che gioca senza ricerca impara
# giocando contro se stessa, Evelynn contro Kha'Zix; ogni 1.000 partite un
# checkpoint e il pannello (ancore del pilota, simple_trade; il bot a mano ogni
# 5.000). 20.000 partite di default, circa mezz'ora su un M1 Max.
# Per continuare oltre, rilancia con più partite, per esempio:
#   scripts/ppo.command --partite 30000
# Riprende dall'ultimo checkpoint; per fermarlo: un file STOP in runs/ppo2.
# Risultato: runs/ppo2/PPO.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir runs/ppo2 --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
