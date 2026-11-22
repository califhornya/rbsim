#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: la seconda notte della ricetta
# PPO (docs/PIANO_FORZA.md). Circa 3 ore.
# Controllo: assegnazione bilanciata, lr costante 3e-4, archivio recenti.
# Nuova: assegnazione bilanciata, lr che scende da 3e-4 a 1e-4, archivio misto
# (10% ultimi 5 checkpoint, 10% più vecchi). Semi 3 e 4, 20.000 partite.
# Regola fissata prima: la nuova ricetta diventa quella standard se, su
# entrambi i semi, la media del pannello dalle 14.000 partite in poi è più
# alta di quella del controllo, e l'incrocio finale nuova contro controllo dello
# stesso seme fa almeno 0,50.
# Risultati: runs/ricetta2/RIASSUNTO.txt, runs/ricetta2/INCROCI.txt,
# runs/ricetta2/*/PPO.txt.
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
for seme in 3 4; do
  caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "runs/ricetta2/controllo_s${seme}" \
      --partite 20000 --tappa 2000 --allarme-bot 10000 --seme "$seme" --workers "$workers"
  caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "runs/ricetta2/nuova_s${seme}" \
      --partite 20000 --tappa 2000 --allarme-bot 10000 --seme "$seme" --archivio misto \
      --lr 3e-4 --lr-finale 1e-4 --workers "$workers"
done
uv run --extra rl python scripts/diag/incroci_ppo.py runs/ricetta2/controllo_s3/corrente.pt \
    runs/ricetta2/nuova_s3/corrente.pt runs/ricetta2/controllo_s4/corrente.pt runs/ricetta2/nuova_s4/corrente.pt \
    --out runs/ricetta2/INCROCI.txt --workers "$workers"
uv run python scripts/diag/riassunto_ppo.py runs/ricetta2/controllo_s3 runs/ricetta2/nuova_s3 \
    runs/ricetta2/controllo_s4 runs/ricetta2/nuova_s4 --da 14000 --out runs/ricetta2/RIASSUNTO.txt
read -r -p "Fatto. Premi Invio per chiudere."
