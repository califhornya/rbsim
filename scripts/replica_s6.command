#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: la replica della distillazione
# con il seme PPO 6 (docs/PIANO_FORZA.md; richiesta della revisione esterna).
# Due reti, 5.056 partite ciascuna con la ricetta del pilota: una da
# runs/distilla/studente_interne.pt, una da runs/ppo1/ckpt_030016.pt. Poi i due
# checkpoint finali, senza ricerca, su 600 coppie a posti scambiati (seed
# 8.600.000-8.600.599). Regola fissata prima: >= 0,52 e limite inferiore > 0,50
# -> vantaggio replicato. Circa mezz'ora.
# Risultato: runs/distilla/replica_s6/INCROCI.txt (e i PPO.txt delle due corse).
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
R=runs/distilla/replica_s6
for v in controllo interne; do
  init=runs/ppo1/ckpt_030016.pt; [ "$v" = interne ] && init=runs/distilla/studente_interne.pt
  caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "$R/ppo_${v}" --init "$init" \
      --partite 5056 --tappa 2500 --allarme-bot 0 --seme 6 --workers "$workers"
done
uv run --extra rl python scripts/diag/incroci_ppo.py "$R/ppo_controllo/corrente.pt" "$R/ppo_interne/corrente.pt" \
    --pairs 600 --seed0 8600000 --regola --out "$R/INCROCI.txt" --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
