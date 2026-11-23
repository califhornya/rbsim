#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: Ivern nel training
# (docs/PIANO_FORZA.md, 23/11; disegno della revisione esterna).
# Quattro reti dal campione a tre mazzi (runs/rengar/ekr_s8/ckpt_020032.pt),
# 30.016 partite ciascuna, stessa ricetta, semi PPO 9 e 10:
#   ekri_s9, ekri_s10: metà ai tre vecchi (Evelynn-Kha'Zix 25%, Evelynn-Rengar
#     e Kha'Zix-Rengar 12,5%), un sesto ciascuno a Evelynn-, Kha'Zix- e
#     Rengar-Ivern (Ivern in B);
#   ekr_s9, ekr_s10: il controllo, la miscela a tre mazzi.
# Pannello ogni 5.000 partite su tutti e sei i matchup, contro ekr_s8.
# Poi la verifica (scripts/diag/verifica_mazzi.py) sui checkpoint finali,
# contro ekr_s8 congelato, 1.000 coppie per matchup. Regole fissate prima:
#   Ivern entra se, sulla media a pesi uguali dei tre matchup con Ivern, la
#   prova fa >= 0,52 con limite inferiore > 0,50 e Δ sul controllo ha limite
#   inferiore > 0;
#   i vecchi tengono se su ciascuno di EK, ER e KR Δ ha limite inferiore > -0,03.
# Circa quattro ore. Si può fermare e rilanciare: riprende da dove era.
# Risultato: runs/ivern/VERIFICA.txt (e i PPO.txt delle quattro corse).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
R=runs/ivern
START=runs/rengar/ekr_s8/ckpt_020032.pt
[ -f "$START" ] || { echo "Manca $START"; exit 1; }
for seme in 9 10; do
  for v in ekri ekr; do
    caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "$R/${v}_s${seme}" --init "$START" \
        --mazzi "$v" --pannello-mazzi EK ER KR EI KI RI --ancore runs/ppo1/ckpt_030016.pt "$START" \
        --partite 30016 --tappa 5000 --allarme-bot 0 --seme "$seme" --workers "$workers" || exit 1
  done
done
caffeinate -i uv run --extra rl python scripts/diag/verifica_mazzi.py \
    --prova "$R/ekri_s9/ckpt_030016.pt" "$R/ekri_s10/ckpt_030016.pt" \
    --controllo "$R/ekr_s9/ckpt_030016.pt" "$R/ekr_s10/ckpt_030016.pt" \
    --ancora "$START" --vecchi EK ER KR --nuovi EI KI RI --coppie 1000 \
    --out "$R/VERIFICA.txt" --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
