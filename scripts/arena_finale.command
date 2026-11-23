#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: l'arena finale sui dieci
# matchup (docs/PIANO_FORZA.md, 23/11; disegno della revisione esterna).
# Il bot a mano con i prior della rete a cinque mazzi runs/sett/ekris_s12
# (scelta: la media più alta contro la partenza nella verifica di Sett, e
# sopra la partenza in tutti e dieci i matchup) contro il campione, il bot a
# mano con i prior di ekr_s8; 0,4 s per mossa.
# Coppie: 800 per Evelynn-Kha'Zix, Evelynn-Rengar, Kha'Zix-Rengar; 300 per
# ciascun matchup con Ivern; 250 per ciascuno con Sett. Seed da 40.000.
# Regole fissate prima: ciascuno dei tre storici limite inferiore > 0,47;
# blocco Ivern (EI, KI, RI) e blocco Sett (ES, KS, RS, IS), a pesi uguali,
# ciascuno >= 0,52 con limite inferiore > 0,50; tutte -> promosso.
# Circa otto ore. Si può fermare e rilanciare: riprende dalle partite già
# giocate (runs/sett/ARENA.jsonl).
# Risultato: runs/sett/ARENA.txt
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
CAND=runs/sett/ekris_s12/ckpt_040000.pt
CAMP=runs/rengar/ekr_s8/ckpt_020032.pt
for f in "$CAND" "$CAMP"; do [ -f "$f" ] || { echo "Manca $f"; exit 1; }; done
caffeinate -i uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt "$CAND" --ckpt-avversario "$CAMP" \
    --vecchi EK ER KR --blocchi EI,KI,RI ES,KS,RS,IS \
    --coppie EK=800 ER=800 KR=800 EI=300 KI=300 RI=300 ES=250 KS=250 RS=250 IS=250 \
    --seed0 40000 --out runs/sett/ARENA.txt --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
