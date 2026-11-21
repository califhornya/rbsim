#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: il pilota PPO (scripts/ppo.py,
# docs/PIANO_FORZA.md). Una rete che gioca senza ricerca impara giocando contro
# se stessa, Evelynn contro Kha'Zix; ogni 1.000 partite un checkpoint e due
# misure (contro simple_trade e contro la rete iniziale). Prima tappa: 5.000
# partite, circa 15-30 minuti su un M1 Max.
# Per continuare oltre, rilancia con più partite, per esempio:
#   scripts/ppo.command --partite 15000
# Riprende dall'ultimo checkpoint; per fermarlo: un file STOP in runs/ppo1.
# Risultato: runs/ppo1/PPO.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir runs/ppo1 --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
