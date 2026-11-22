#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: il pilota di distillazione
# (scripts/distilla.py, docs/PIANO_FORZA.md). Circa un'ora.
# 1. Il margine del maestro: bot con prior 30.016 contro la rete 30.016 da sola,
#    200 coppie (seed 18000-18199).
# 2. Radici: 1.000 partite di allenamento e 200 di sviluppo, due decisioni
#    ciascuna etichettate dal maestro (mossa e scelte interne del suo piano).
# 3. Due studenti dagli stessi pesi (30.016): solo la mossa / mossa e scelte
#    interne. Subito dopo, contro la partenza (200 coppie).
# 4. Stesso budget PPO (5.000 partite, seme 5) a controllo e studenti; incroci.
# Regola fissata prima: si sale a 10.000 radici se il maestro batte lo studente
# (>= 0,52, limite inferiore > 0,50) e uno studente, dopo il PPO, batte il
# controllo (>= 0,52, limite inferiore > 0,50).
# Risultati: runs/distilla/ (DISTILLA.txt, INCROCI*.txt, ppo_*/PPO.txt) e
# runs/arena_prior_ppo_ckpt_030016_contro_ckpt_030016/ARENA.txt.
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
P=runs/ppo1/ckpt_030016.pt
caffeinate -i uv run --extra rl python scripts/diag/arena_bot.py --candidato prior_ppo --ckpt "$P" \
    --avversario rete_ppo --ckpt-avversario "$P" --pairs 200 --seed0 18000 --workers "$workers"
caffeinate -i uv run --extra rl python scripts/distilla.py radici --workers "$workers"
uv run --extra rl python scripts/distilla.py allena
uv run --extra rl python scripts/diag/incroci_ppo.py "$P" runs/distilla/studente_mossa.pt \
    runs/distilla/studente_interne.pt --out runs/distilla/INCROCI_SUBITO.txt --workers "$workers"
for v in controllo mossa interne; do
  init="$P"; [ "$v" != controllo ] && init="runs/distilla/studente_${v}.pt"
  caffeinate -i uv run --extra rl python scripts/ppo.py --run-dir "runs/distilla/ppo_${v}" --init "$init" \
      --partite 5000 --tappa 2500 --allarme-bot 0 --seme 5 --workers "$workers"
done
uv run --extra rl python scripts/diag/incroci_ppo.py runs/distilla/ppo_controllo/corrente.pt \
    runs/distilla/ppo_mossa/corrente.pt runs/distilla/ppo_interne/corrente.pt \
    --out runs/distilla/INCROCI_DOPO_PPO.txt --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
