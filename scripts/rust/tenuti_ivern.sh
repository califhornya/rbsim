#!/bin/bash
# Semi tenuti da parte (900001-900040) per la tappa Ivern: EI, KI e RI nei due posti (--posti),
# primo giocatore bilanciato (parità del seme); le liste con la sideboard (Ei, Ki, Ri) nelle partite
# autonome. Di nuovo EK, ER e KR (arena col bot a mano, esempi PPO, autonome): la pila con
# l'identità degli elementi (ChainItem.uid) tocca tutti i matchup. Quattro prove alla volta; un file
# per prova in docs/rust/misure/tenuti_ivern_*.json.
#   bash scripts/rust/tenuti_ivern.sh [processi]
set -uo pipefail
cd "$(dirname "$0")/../.."
P="${1:-4}"
[ -f .venv/bin/activate ] && source .venv/bin/activate
OUT=docs/rust/misure
LOG=${TMPDIR:-/tmp}/tenuti_ivern
mkdir -p "$OUT" "$LOG"
SEMI=900001-900040
{
  for MU in EI KI RI; do
    echo "arena_parita.py --semi $SEMI --matchup $MU --posti --bot prior --iterazioni 50 --out $OUT/tenuti_ivern_arena_prior_$MU.json"
    echo "arena_parita.py --semi $SEMI --matchup $MU --posti --bot mano --iterazioni 50 --out $OUT/tenuti_ivern_arena_mano_$MU.json"
  done
  for MU in EK ER KR; do
    echo "arena_parita.py --semi $SEMI --matchup $MU --posti --bot mano --iterazioni 50 --out $OUT/tenuti_ivern_arena_mano_$MU.json"
  done
  for MU in EI KI RI; do
    echo "parita_ppo.py --semi $SEMI --matchup $MU --posti --out $OUT/tenuti_ivern_ppo_self_$MU.json"
    echo "parita_ppo.py --semi $SEMI --matchup $MU --posti --avversario simple_trade --out $OUT/tenuti_ivern_ppo_simple_trade_$MU.json"
    echo "diff_trace.py --semi $SEMI --matchup $MU --posti --modo self --out $OUT/tenuti_ivern_replay_self_$MU.json"
  done
  for MU in EK ER KR; do
    echo "parita_ppo.py --semi $SEMI --matchup $MU --posti --out $OUT/tenuti_ivern_ppo_self_$MU.json"
  done
  for MU in EI KI RI Ei Ki Ri EK ER KR; do
    echo "autonome.py --semi $SEMI --matchup $MU --posti --agenti simple_trade simple_trade --out $OUT/tenuti_ivern_autonome_st_$MU.json"
    echo "autonome.py --semi $SEMI --matchup $MU --posti --agenti random random --out $OUT/tenuti_ivern_autonome_random_$MU.json"
  done
} | xargs -P "$P" -I{} bash -c 'n=$(echo "{}" | sed "s/.*--out [^ ]*tenuti_ivern_\([^ ]*\)\.json/\1/"); python scripts/rust/{} > '"$LOG"'/$n.log 2>&1; echo "$n: $(tail -n 1 '"$LOG"'/$n.log)"'
