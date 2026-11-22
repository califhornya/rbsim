#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: il ramo a tre mazzi
# (docs/PIANO_FORZA.md, 22/11; disegno della revisione esterna).
# Quattro reti dalla stessa partenza (runs/ppo1/ckpt_030016.pt), 20.032
# partite ciascuna con la ricetta del pilota, semi PPO 7 e 8:
#   ekr_s7, ekr_s8: 50% Evelynn-Kha'Zix, 25% Evelynn-Rengar, 25% Kha'Zix-Rengar;
#   ek_s7, ek_s8:   solo Evelynn-Kha'Zix (il controllo, per attribuire l'effetto).
# Pannello ogni 5.000 partite su tutti e tre i matchup (simple_trade e ancore).
# Poi la verifica (scripts/diag/verifica_mazzi.py), regole fissate prima:
#   Rengar entra se su ER e KR la prova contro la partenza fa >= 0,52 con
#   limite inferiore > 0,50 e batte il controllo (limite inferiore > 0);
#   Evelynn-Kha'Zix tiene se il limite inferiore della differenza appaiata
#   con il controllo è > -0,03.
# Circa due ore. Si può fermare e rilanciare: riprende da dove era.
# Risultato: runs/rengar/VERIFICA.txt (e i PPO.txt delle quattro corse).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
R=runs/rengar
for seme in 7 8; do
  for v in ekr ek; do
    caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "$R/${v}_s${seme}" \
        --init runs/ppo1/ckpt_030016.pt --mazzi "$v" --pannello-mazzi EK ER KR \
        --partite 20032 --tappa 5000 --allarme-bot 0 --seme "$seme" --workers "$workers" || exit 1
  done
done
caffeinate -i uv run --extra rl python scripts/diag/verifica_mazzi.py \
    --prova "$R/ekr_s7/corrente.pt" "$R/ekr_s8/corrente.pt" \
    --controllo "$R/ek_s7/corrente.pt" "$R/ek_s8/corrente.pt" \
    --out "$R/VERIFICA.txt" --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
