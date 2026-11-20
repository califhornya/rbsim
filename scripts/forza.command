#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: due prove di forza contro il
# bot a mano (scripts/diag/arena_bot.py), una dopo l'altra.
# 1. tempo: il bot con 0,8 s per mossa contro 0,4 s, 200 coppie (circa mezz'ora);
# 2. orizzonte: il bot che guarda oltre la fine del turno, 0,4 s per mossa
#    come l'avversario, 800 coppie (circa un'ora e mezza).
# Regola fissata prima, per ciascuna: punteggio >= 0,52 e limite inferiore
# dell'IC 95% > 0,50. Risultati: runs/arena_tempo/ARENA.txt e
# runs/arena_orizzonte/ARENA.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run python scripts/diag/arena_bot.py --candidato tempo --pairs 200 --workers "$workers"
caffeinate -i uv run python scripts/diag/arena_bot.py --candidato orizzonte --pairs 800 --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
