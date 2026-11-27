#!/bin/bash
# Fondo (Matteo, 27/11; Astra non disponibile): misura di «Pensa». Sulle 480 posizioni di sviluppo, a ogni decisione fino a 3 mosse candidate
# dall'albero del campione si giocano fino in fondo sugli stessi MONDI_SCELTA mondi e si sceglie la migliore; dove la
# scelta differisce dal campione, verifica su MONDI_VERIFICA mondi diversi. Un solo passo, niente arena.
# Regola di stop: limite inferiore di Pensa - campione > 0 e almeno 20 posizioni cambiano mossa.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/fondo.command
#   (su un server: dentro tmux, dopo scripts/rust/server_prepara.sh)
# Avanzamento: tail -f runs/fondo/*.out
# Variabili d'ambiente: PARTITE=6 PER_PARTITA=8 MONDI_SCELTA=32 MONDI_VERIFICA=100 PROCESSI=<ncpu-1> CKPT=... OUT=...
# Rilanciato con OUT=<cartella> riprende: salta il lavoro gia' fatto.
# Prerequisiti: uv, Rust (https://rustup.rs).
set -euo pipefail
export PYTHONUNBUFFERED=1   # avanzamento visibile subito in runs/fondo/*.out
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
PARTITE="${PARTITE:-6}"
PER_PARTITA="${PER_PARTITA:-8}"
MONDI_SCELTA="${MONDI_SCELTA:-32}"
MONDI_VERIFICA="${MONDI_VERIFICA:-100}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/fondo_$STAMP}"
mkdir -p "$OUT"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/fondo
# esegui <nome> <filtro egrep> <comando...>: l'uscita completa va in runs/fondo/, a schermo e nel log solo le righe
# del filtro (ultime 30); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/fondo/${STAMP}_$1.out" filtro="$2"; shift 2
  if ! "$@" > "$f" 2>&1; then echo "ERRORE in $*"; tail -20 "$f"; exit 1; fi
  { grep -E "$filtro" "$f" || true; } | tail -30 | tee -a "$LOG"
}

passo "== ambiente"
uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) | tee -a "$LOG" || true
python -c "import riftbound_rs" || { echo "estensione Rust non caricata"; exit 1; }
git log --oneline -1 | tee -a "$LOG"
echo "processi: $PROCESSI; campione: $CKPT; $PARTITE partite x 10 matchup x $PER_PARTITA decisioni; $MONDI_SCELTA mondi di scelta, $MONDI_VERIFICA di verifica" | tee -a "$LOG"

T0=$(t)
passo "== 1. fondo: candidati giocati fino in fondo, scelta e verifica"
esegui fondo "^== |^totale|^regola|^stima|^tempo|Traceback|Error" python scripts/rust/fondo.py --ckpt "$CKPT" \
  --partite "$PARTITE" --per-partita "$PER_PARTITA" --mondi-scelta "$MONDI_SCELTA" --mondi-verifica "$MONDI_VERIFICA" \
  --processi "$PROCESSI" --out "$OUT/fondo"
T1=$(t)

{
  echo "durata del passo (s): fondo $((T1 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"

echo
echo "--- $OUT/fondo/riepilogo.txt"; tail -15 "$OUT/fondo/riepilogo.txt"
PASSA="$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['passa'])" "$OUT/fondo/esito.json")"
if [ "$PASSA" = "True" ]; then
  echo "Regola di stop passata: il passo successivo («Pensa» nella pagina e arena) si decide con Matteo."
else
  echo "Regola di stop: non passa, il campione resta com'e'."
fi
echo
echo "== fatto. Per riprendere: OUT=$OUT bash scripts/rust/fondo.command"
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Fondo: misura di Pensa ($STAMP)\" && git push"
