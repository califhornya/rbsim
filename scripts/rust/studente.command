#!/bin/bash
# Pilota «studente» (specifica docs/bot/STUDENTE.md; Astra/Matteo 27/11): un modello veloce impara da «Pensa» quale delle
# <=3 mosse candidate del campione scegliere, su entrambi i posti (chi inizia e chi risponde). Un solo passo: raccolta
# (tetto TETTO_RACCOLTA_MIN), addestramento e cancello, congelamento, verifica (tetto TETTO_VERIFICA_MIN), riepilogo.
# Soglia fissata: lo studente fa >= +1,0 pp con limite inferiore > 0 sui due ruoli insieme; se no ci si ferma.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/studente.command
#   (su un server: dentro tmux, dopo scripts/rust/server_prepara.sh)
# Avanzamento: tail -f runs/studente/*.out
# Variabili d'ambiente (default della specifica): PROCESSI=<ncpu-1> CKPT=... OUT=... DATI=... PER_POSTO=4
#   SEMI_RACCOLTA=60 SEMI_VERIFICA=40 SEMI_MAESTRO=1 MONDI_RACCOLTA=8 MONDI_VERIFICA=64 MONDI_MAESTRO=32
#   TETTO_RACCOLTA_MIN=50 TETTO_VERIFICA_MIN=55 ITERAZIONI=138 REGOLE=6427b90+D72-D83 N_BOOT=40000 EPOCHE=300
#   MATCHUP="EK ER ..." (default: i 10 matchup)  FORZA_CANCELLO=1 (SOLO per le prove: la verifica gira anche se lo
#   studente non impara). Le regole statistiche (semi, divisione, cancello, congelamento, soglia) non si cambiano.
# Prerequisiti: uv, Rust (https://rustup.rs). Un rilancio riparte da capo (usa un OUT nuovo).
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -z "${CKPT:-}" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
[ -f "$CKPT" ] || { echo "Manca il checkpoint del campione $CKPT"; exit 1; }
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
command -v rustc >/dev/null || { echo "manca Rust: https://rustup.rs"; exit 1; }
PER_POSTO="${PER_POSTO:-4}"
SEMI_RACCOLTA="${SEMI_RACCOLTA:-60}"
SEMI_VERIFICA="${SEMI_VERIFICA:-40}"
SEMI_MAESTRO="${SEMI_MAESTRO:-1}"
MONDI_RACCOLTA="${MONDI_RACCOLTA:-8}"
MONDI_VERIFICA="${MONDI_VERIFICA:-64}"
MONDI_MAESTRO="${MONDI_MAESTRO:-32}"
TETTO_RACCOLTA_MIN="${TETTO_RACCOLTA_MIN:-50}"
TETTO_VERIFICA_MIN="${TETTO_VERIFICA_MIN:-55}"
ITERAZIONI="${ITERAZIONI:-138}"
REGOLE="${REGOLE:-6427b90+D72-D83}"
N_BOOT="${N_BOOT:-40000}"
EPOCHE="${EPOCHE:-300}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/studente_$STAMP}"
DATI="${DATI:-runs/studente/$STAMP}"
mkdir -p "$OUT" "$DATI"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/studente
# esegui <nome> <filtro egrep> <comando...>: l'uscita completa va in runs/studente/, a schermo e nel log solo le righe
# del filtro (ultime 40); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/studente/${STAMP}_$1.out" filtro="$2"; shift 2
  if ! "$@" > "$f" 2>&1; then echo "ERRORE in $*"; tail -20 "$f"; exit 1; fi
  { grep -E "$filtro" "$f" || true; } | tail -40 | tee -a "$LOG"
}

passo "== ambiente"
uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) | tee -a "$LOG" || true
python -c "import riftbound_rs" || { echo "estensione Rust non caricata"; exit 1; }
git log --oneline -1 | tee -a "$LOG"
ARGOMENTI=()
[ -n "${MATCHUP:-}" ] && ARGOMENTI+=(--matchup $MATCHUP)
[ -n "${FORZA_CANCELLO:-}" ] && ARGOMENTI+=(--forza-cancello)
echo "processi: $PROCESSI su $NCPU core; campione: $CKPT; raccolta $TETTO_RACCOLTA_MIN min ($MONDI_RACCOLTA mondi), verifica $TETTO_VERIFICA_MIN min ($MONDI_VERIFICA mondi, maestro $SEMI_MAESTRO semi su $MONDI_MAESTRO mondi); $PER_POSTO posizioni per posto" | tee -a "$LOG"

T0=$(t)
passo "== 1. studente: raccolta, addestramento e cancello, congelamento, verifica"
esegui studente "^== |^totale|^soglia|^stima|^tempi|^cancello|^raccolta|^addestramento|^verifica|^studente|^maestro|^  ruolo|Traceback|Error" \
  python scripts/rust/studente.py --ckpt "$CKPT" --out "$OUT" --dati "$DATI" --processi "$PROCESSI" \
  --per-posto "$PER_POSTO" --semi-raccolta "$SEMI_RACCOLTA" --semi-verifica "$SEMI_VERIFICA" \
  --semi-maestro "$SEMI_MAESTRO" --mondi-raccolta "$MONDI_RACCOLTA" --mondi-verifica "$MONDI_VERIFICA" \
  --mondi-maestro "$MONDI_MAESTRO" --tetto-raccolta-min "$TETTO_RACCOLTA_MIN" --tetto-verifica-min "$TETTO_VERIFICA_MIN" \
  --iterazioni "$ITERAZIONI" --regole "$REGOLE" --n-boot "$N_BOOT" --epoche "$EPOCHE" ${ARGOMENTI[@]+"${ARGOMENTI[@]}"}
T1=$(t)

{
  echo "durata del passo (s): studente $((T1 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"

echo
echo "--- $OUT/riepilogo.txt"; tail -12 "$OUT/riepilogo.txt"
ESITO="$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['esito'])" "$OUT/esito.json")"
case "$ESITO" in
  PASSA) echo "ESITO: PASSA. Il candidato per l'arena e' lo studente veloce; il passo successivo si decide con Matteo." ;;
  "NON PASSA") echo "ESITO: NON PASSA. Si ferma la spesa, resta il campione." ;;
  *) echo "ESITO: NON IMPARA (cancello: guadagno di validazione <= 0). La verifica non e' partita, resta il campione." ;;
esac
echo
echo "== fatto. Risultati leggeri: $OUT; dati pesanti (input della rete): $DATI"
echo "Per portarli su GitHub (i dati pesanti in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Studente: raccolta e verifica ($STAMP)\" && git push"
