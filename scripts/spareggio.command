#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: l'arena dello spareggio
# (scripts/diag/arena_spareggio.py). Il bot a mano che tra mosse con lo stesso Q
# sceglie quella col W/N più alto, contro il bot a mano di adesso: 800 coppie di
# seed nuovi (12000-12799), stessa apertura a piloti scambiati, primo giocatore
# bilanciato, 0,4 s di CPU per mossa. Circa un'ora e tre quarti su un M1 Max.
# Regola fissata prima: punteggio >= 0,52 e limite inferiore dell'IC 95% > 0,50.
# Risultato: runs/spareggio/ARENA.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run python scripts/diag/arena_spareggio.py --pairs 800 --budget 0.4 \
    --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
