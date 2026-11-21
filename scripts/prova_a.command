#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: la prova A, gruppo di sviluppo
# (scripts/diag/prova_a.py, docs/PIANO_FORZA.md). Su 128 posizioni nuove, una
# ricerca che gioca tutto il turno dell'avversario sceglie mosse migliori del
# bot a mano? Due varianti: valutare alla nostra decisione successiva, o
# giocare fino alla fine. Poi la velocità di una rete senza ricerca (prova B).
# Circa un'ora su un M1 Max. Rilanciato, riprende; per fermarlo: un file STOP
# nella cartella della variante in corso (runs/prova_a/prossima/sviluppo o
# runs/prova_a/fine/sviluppo). Risultati: PROVA_A.txt in quelle cartelle.
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run python scripts/diag/prova_a.py --gruppo sviluppo --arresto prossima --workers "$workers"
caffeinate -i uv run python scripts/diag/prova_a.py --gruppo sviluppo --arresto fine --workers "$workers"
uv run --extra rl python scripts/diag/rete_veloce.py --partite 40
read -r -p "Fatto. Premi Invio per chiudere."
