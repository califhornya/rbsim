#!/bin/bash
# Doppio clic nel Finder (Mac): la rete dal bot scritto a mano (docs/bot/RETE.md),
# in runs/boot1. 2.000 partite del bot contro se stesso (circa un'ora e mezza su
# un M1 Max), l'allenamento (pochi minuti), le misure (circa mezz'ora).
# Rilanciato, riprende da dove si era fermato: le partite salvate restano.
# Per fermarlo: un file chiamato STOP in runs/boot1 (poi cancellalo prima di
# rilanciare). Risultati: runs/boot1/RISULTATI.txt, da caricare in chat con
# runs/boot1/net_boot.pt. Un worker per core veloce (8 su un M1 Max); un altro
# numero con: scripts/rete.command --workers 4
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/bootstrap_net.py all --run-dir runs/boot1 \
    --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
