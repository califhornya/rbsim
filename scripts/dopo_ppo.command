#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: due misure dopo il pilota PPO.
# 1. Incroci tra i checkpoint 5.000 / 15.000 / 30.000 (scripts/diag/incroci_ppo.py):
#    la rete ha continuato a migliorare dopo che simple_trade si è appiattito?
#    Pochi minuti.
# 2. Il bot a mano con i prior della rete PPO contro il bot a mano
#    (scripts/diag/arena_bot.py --candidato prior_ppo), 400 coppie, 0,4 s per
#    mossa ciascuno. Circa 45 minuti.
# Risultati: runs/ppo1/INCROCI.txt e runs/arena_prior_ppo/ARENA.txt.
cd "$(dirname "$0")/.." || exit 1
workers=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac
ck() { ls runs/ppo1/ckpt_0"$1"*.pt 2>/dev/null | head -1; }
uv run --extra rl python scripts/diag/incroci_ppo.py "$(ck 05)" "$(ck 15)" "$(ck 30)" --workers "$workers"
caffeinate -i uv run --extra rl python scripts/diag/arena_bot.py --candidato prior_ppo --pairs 400 --workers "$workers"
read -r -p "Fatto. Premi Invio per chiudere."
