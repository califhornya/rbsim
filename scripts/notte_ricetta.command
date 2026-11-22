#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: la notte della ricetta PPO
# (docs/PIANO_FORZA.md, secondo giro della revisione esterna). Circa 3 ore.
# 1. Sfida diretta: bot con i prior PPO 15.040 contro bot con i prior 30.016
#    (il campione), 400 coppie di seed nuovi (16000-16399), 0,4 s per mossa.
#    Regola: >= 0,52 e limite inferiore > 0,50 -> il 15.040 diventa il campione.
# 2. Ricetta: quattro allenamenti da 20.000 partite, assegnazione bilanciata
#    (corretta) e vecchia (il difetto del pilota), semi 1 e 2; pannello ogni
#    2.000 partite contro le ancore 5.056 / 15.040 / 30.016 del pilota.
# 3. Incroci tra le quattro reti finali (200 coppie).
# Risultati: runs/arena_prior_ppo_ckpt_015040_contro_ckpt_030016/ARENA.txt,
# runs/ricetta/*/PPO.txt, runs/ricetta/INCROCI.txt.
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
caffeinate -i uv run --extra rl python scripts/diag/arena_bot.py --candidato prior_ppo \
    --ckpt runs/ppo1/ckpt_015040.pt --avversario prior_ppo --ckpt-avversario runs/ppo1/ckpt_030016.pt \
    --pairs 400 --seed0 16000 --workers "$workers"
for seme in 1 2; do
  for ass in vecchia bilanciata; do
    caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "runs/ricetta/${ass}_s${seme}" \
        --partite 20000 --tappa 2000 --allarme-bot 10000 --seme "$seme" --assegnazione "$ass" --workers "$workers"
  done
done
uv run --extra rl python scripts/diag/incroci_ppo.py runs/ricetta/vecchia_s1/corrente.pt \
    runs/ricetta/bilanciata_s1/corrente.pt runs/ricetta/vecchia_s2/corrente.pt runs/ricetta/bilanciata_s2/corrente.pt \
    --out runs/ricetta/INCROCI.txt --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
