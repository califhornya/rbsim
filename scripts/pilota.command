#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: il pilota del passo 2
# (scripts/diag/pilota_sorelle.py). 128 posizioni da partite diverse, fino a 3
# mosse sorelle giocate fino alla fine sugli stessi mondi: si ripetono le
# differenze su mondi nuovi? Bastano 32 iterazioni per le etichette?
# Circa 2-3 ore su un M1 Max. Rilanciato, riprende; per fermarlo: un file STOP
# in runs/pilota (poi cancellalo prima di rilanciare).
# Risultato: runs/pilota/RISULTATO.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run python scripts/diag/pilota_sorelle.py --run-dir runs/pilota \
    --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
