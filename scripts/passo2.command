#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: il passo 2 (scripts/passo2.py).
# 1.600 posizioni da partite diverse (1.000 per allenare, 200 per scegliere
# l'epoca, 400 di prova), le mosse sorelle giocate fino alla fine, il valore
# "bot + correzione" allenato, poi la soglia sulle 400 di prova.
# Circa 6-8 ore su un M1 Max: una notte. Rilanciato, riprende; per fermarlo:
# un file STOP in runs/passo2 (poi cancellalo prima di rilanciare).
# Risultato: runs/passo2/PASSO2.txt (anche a schermo).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/passo2.py tutto --run-dir runs/passo2 \
    --workers "$workers" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
