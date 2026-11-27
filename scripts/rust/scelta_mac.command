#!/bin/bash
# Scelta finale (Astra, 27/11): la mossa piu' visitata contro quella con la Q piu' alta, dallo stesso albero del campione.
# Passo 1: le stesse 480 posizioni dei seguiti; dove le due mosse differiscono si giocano entrambe sugli stessi mondi.
# Passo 2 (solo se il limite inferiore dell'IC 95% e' > 0): arena, candidato con scelta per visite contro il campione.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/scelta_mac.command
# Variabili d'ambiente: COPPIE=100 PARTITE=6 PER_PARTITA=8 MONDI=32 PROCESSI=<n> CKPT=... OUT=...
# Rilanciato con OUT=<cartella> riprende: salta il lavoro gia' fatto.
# Prerequisiti: uv, Rust (https://rustup.rs).
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -z "${CKPT:-}" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
[ -f "$CKPT" ] || { echo "Manca il checkpoint del campione $CKPT"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: https://rustup.rs"; exit 1; }
COPPIE="${COPPIE:-100}"
PARTITE="${PARTITE:-6}"
PER_PARTITA="${PER_PARTITA:-8}"
MONDI="${MONDI:-32}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/scelta_$STAMP}"
mkdir -p "$OUT"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/scelta
# esegui <file di uscita completa> <filtro egrep> <comando...>: l'uscita completa va in runs/scelta/, a schermo e nel
# log solo le righe del filtro (ultime 30); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/scelta/${STAMP}_$1.out" filtro="$2"; shift 2
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
echo "processi: $PROCESSI; campione: $CKPT; $PARTITE partite x $PER_PARTITA decisioni x $MONDI mondi; $COPPIE coppie" | tee -a "$LOG"

T0=$(t)
passo "== 1. posizioni: piu' visitata contro Q piu' alta"
esegui posizioni "^== |^totale|^regola|Traceback|Error" python scripts/rust/scelta.py posizioni --ckpt "$CKPT" \
  --out "$OUT" --partite "$PARTITE" --per-partita "$PER_PARTITA" --mondi "$MONDI" --processi "$PROCESSI"
T1=$(t)

PASSA="$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['passa'])" "$OUT/esito.json")"
if [ "$PASSA" = "True" ]; then
  passo "== 2. arena ($COPPIE coppie per matchup)"
  esegui arena "^== |^totale|^criterio|Traceback|Error" python scripts/rust/scelta.py arena --ckpt "$CKPT" \
    --out "$OUT" --coppie "$COPPIE" --processi "$PROCESSI"
else
  passo "Regola di stop: niente arena, resta la scelta per Q."
fi
T2=$(t)

{
  echo "durata dei passi (s): posizioni $((T1 - T0)), arena $((T2 - T1)), totale $((T2 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"

echo
echo "--- $OUT/riepilogo.txt"; tail -15 "$OUT/riepilogo.txt"
[ -f "$OUT/arena.txt" ] && { echo "--- $OUT/arena.txt"; cat "$OUT/arena.txt"; }
echo
echo "== fatto. Per riprendere: OUT=$OUT bash scripts/rust/scelta_mac.command"
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Scelta finale: piu' visitata contro Q ($STAMP)\" && git push"
