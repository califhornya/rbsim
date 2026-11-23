#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: l'arena finale a cinque mazzi
# (docs/PIANO_FORZA.md, 23/11; disegno della revisione esterna, sesto giro).
# Candidato fissato: il bot a mano con i prior di runs/sett/ekris_s12/ckpt_040000.pt.
# 0,4 s per mossa a entrambi, piloti scambiati, chi comincia bilanciato.
#
# A. Evelynn-Ivern contro il checkpoint intermedio: 800 coppie, avversario il
#    bot con i prior di runs/ivern/ekri_s10/ckpt_030016.pt (seed 53.000-53.799).
#    Passa se il limite inferiore dell'IC 95% è > 0,47. Se non passa, il
#    campione resta ekr_s8 e l'arena lunga non si gioca. (~1 ora e mezza)
# B. Se A passa: contro il campione, il bot con i prior di
#    runs/rengar/ekr_s8/ckpt_020032.pt. 800 coppie per Evelynn-Kha'Zix,
#    Evelynn-Rengar, Kha'Zix-Rengar; 300 per ciascun matchup con Ivern; 250
#    per ciascuno con Sett (seed da 40.000). Regole: ciascuno dei tre storici
#    limite inferiore > 0,47; blocco Ivern e blocco Sett, a pesi uguali,
#    ciascuno >= 0,52 con limite inferiore > 0,50; tutte -> promosso. (~8 ore)
# Si può fermare e rilanciare: riprende dalle partite già giocate.
# Risultati: runs/sett/ARENA_EI.txt e runs/sett/ARENA.txt
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
CAND=runs/sett/ekris_s12/ckpt_040000.pt
INTER=runs/ivern/ekri_s10/ckpt_030016.pt
CAMP=runs/rengar/ekr_s8/ckpt_020032.pt
for f in "$CAND" "$INTER" "$CAMP"; do [ -f "$f" ] || { echo "Manca $f"; exit 1; }; done
if ! grep -q "Esito: PASSA" runs/sett/ARENA_EI.txt 2>/dev/null; then
  caffeinate -i uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt "$CAND" --ckpt-avversario "$INTER" \
      --vecchi EI --blocchi --coppie EI=800 --seed0 50000 --esito-positivo PASSA \
      --out runs/sett/ARENA_EI.txt --workers "$workers" || exit 1
fi
if grep -q "Esito: PASSA" runs/sett/ARENA_EI.txt; then
  caffeinate -i uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt "$CAND" --ckpt-avversario "$CAMP" \
      --vecchi EK ER KR --blocchi EI,KI,RI ES,KS,RS,IS \
      --coppie EK=800 ER=800 KR=800 EI=300 KI=300 RI=300 ES=250 KS=250 RS=250 IS=250 \
      --seed0 40000 --out runs/sett/ARENA.txt --workers "$workers"
else
  echo "A non passa: il campione resta ekr_s8, l'arena lunga non si gioca."
fi
read -r -p "Fatto. Premi Invio per chiudere."
