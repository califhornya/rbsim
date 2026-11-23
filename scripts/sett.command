#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: Sett nel training
# (docs/PIANO_FORZA.md, 23/11; disegno della revisione esterna, come Ivern).
# Quattro reti dal checkpoint a quattro mazzi runs/ivern/ekri_s10/ckpt_030016.pt
# (scelta: la media più alta contro l'ancora nella verifica di Ivern, sopra
# ekri_s9 in tutti e sei i matchup), 40.000 partite ciascuna, semi PPO 11 e 12:
#   ekris_s11, ekris_s12: metà la miscela a quattro mazzi, un ottavo ciascuno
#     a Evelynn-, Kha'Zix-, Rengar- e Ivern-Sett (Sett in B; 5.000 partite
#     per matchup nuovo, come Rengar e Ivern);
#   ekri_s11, ekri_s12: il controllo, la miscela a quattro mazzi.
# Checkpoint e archivio ogni 5.000 partite (la ricetta); pannello sui dieci
# matchup all'inizio, a 20.000 e alla fine.
# Poi la verifica sui checkpoint finali contro la partenza congelata, 1.000
# coppie per matchup, seed da 13.000.000. Regole fissate prima:
#   Sett entra se, sulla media a pesi uguali dei quattro matchup con Sett, la
#   prova fa >= 0,52 con limite inferiore > 0,50 e Δ sul controllo ha limite
#   inferiore > 0;
#   i vecchi tengono se su ciascuno dei sei (EK, ER, KR, EI, KI, RI) Δ ha
#   limite inferiore > -0,03.
# Circa quattro ore. Si può fermare e rilanciare: riprende da dove era.
# Risultato: runs/sett/VERIFICA.txt (e i PPO.txt delle quattro corse).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
R=runs/sett
START=runs/ivern/ekri_s10/ckpt_030016.pt
[ -f "$START" ] || { echo "Manca $START"; exit 1; }
for seme in 11 12; do
  for v in ekris ekri; do
    caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "$R/${v}_s${seme}" --init "$START" \
        --mazzi "$v" --pannello-mazzi EK ER KR EI KI RI ES KS RS IS \
        --ancore runs/rengar/ekr_s8/ckpt_020032.pt "$START" \
        --partite 40000 --tappa 5000 --pannello-ogni 20000 --allarme-bot 0 --seme "$seme" \
        --workers "$workers" || exit 1
  done
done
caffeinate -i uv run --extra rl python scripts/diag/verifica_mazzi.py \
    --prova "$R/ekris_s11/ckpt_040000.pt" "$R/ekris_s12/ckpt_040000.pt" \
    --controllo "$R/ekri_s11/ckpt_040000.pt" "$R/ekri_s12/ckpt_040000.pt" \
    --ancora "$START" --vecchi EK ER KR EI KI RI --nuovi ES KS RS IS --coppie 1000 --coppie-testa 200 \
    --seed0 13000000 --out "$R/VERIFICA.txt" --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
