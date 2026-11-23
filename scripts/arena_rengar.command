#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: l'arena sui tre matchup
# (docs/PIANO_FORZA.md, 22/11). Il bot a mano con i prior della rete a tre
# mazzi runs/rengar/ekr_s8 (scelta prima: la media più alta nella verifica)
# contro il campione, il bot a mano con i prior 30.016; 0,4 s per mossa.
# 600 coppie Evelynn-Kha'Zix, 400 Evelynn-Rengar, 400 Kha'Zix-Rengar.
# Regole fissate prima: Rengar (ER e KR insieme) >= 0,52 e limite inferiore
# > 0,50; Evelynn-Kha'Zix limite inferiore > 0,47; entrambe -> promosso.
# Circa due ore e mezza.
# Risultato: runs/rengar/ARENA.txt
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
# (Il 22/11 con la prima versione dello script, commit 23fc0d2: ER e KR
# insieme sulle coppie.)
caffeinate -i uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt runs/rengar/ekr_s8/corrente.pt \
    --ckpt-avversario runs/ppo1/ckpt_030016.pt --vecchi EK --blocchi ER,KR --coppie EK=600 ER=400 KR=400 \
    --seed0 30000 --out runs/rengar/ARENA.txt --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
