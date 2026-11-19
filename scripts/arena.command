#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: l'arena di boot1 (docs/bot/RETE.md).
# Il valore di runs/boot1/net_boot.pt con prior uguali contro il bot a mano:
# 230 coppie di seed nuovi (7000-7229) a posti scambiati, 0,4 s di CPU per mossa,
# backup best e mossa col Q massimo. Circa mezz'ora su un M1 Max.
# Regola fissata prima: punteggio >= 0,55 → si promuove l'ibrido; sotto → boot1 chiuso.
# Risultato: runs/boot1/ARENA.txt (anche a schermo). Opzioni in coda, per esempio
# --avanza (il PASS forzato che chiude un movimento si gioca subito, per entrambi).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/bootstrap_net.py arena --run-dir runs/boot1 \
    --pairs 230 --budget 0.4 --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
