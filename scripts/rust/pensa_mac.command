#!/bin/bash
# Pensare piu' a lungo (Astra, 27/11): il campione a 1.000 iterazioni per ricerca contro il campione a 138.
# Stesso checkpoint, regole 6427b90+D72-D83, scelta per Q, rimonta e win_probe sui due lati; aperture nuove (semi 70M),
# posti scambiati, 10 matchup a pari peso, 100 coppie. Riporta punteggio, IC 95% per coppie e latenza per decisione e
# per turno (media, mediana, 95° e 99° percentile, massimo). Pagina a 1.000 solo se il limite inferiore supera il 50%
# e i turni difficili restano nei 3-5 minuti.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/pensa_mac.command
# Avanzamento, da un altro Terminale:  tail -f runs/pensa/*_arena.out
# Variabili d'ambiente: COPPIE=100 ITER_PENSA=1000 ITER_BASE=138 PROCESSI=<n> CKPT=... OUT=...
# Rilanciato con OUT=<cartella> riprende: salta le partite gia' giocate.
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
ITER_PENSA="${ITER_PENSA:-1000}"
ITER_BASE="${ITER_BASE:-138}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/pensa_$STAMP}"
mkdir -p "$OUT"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/pensa
# esegui <file di uscita completa> <filtro egrep> <comando...>: l'uscita completa va in runs/pensa/, a schermo e nel
# log solo le righe del filtro (ultime 40); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/pensa/${STAMP}_$1.out" filtro="$2"; shift 2
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
echo "processi: $PROCESSI; campione: $CKPT; $ITER_PENSA contro $ITER_BASE iterazioni; $COPPIE coppie per matchup" \
  | tee -a "$LOG"
echo "durata prevista: circa 40 minuti con 9 processi (piu' con meno core). Avanzamento: tail -f runs/pensa/${STAMP}_arena.out"

T0=$(t)
passo "== arena: $ITER_PENSA contro $ITER_BASE iterazioni"
esegui arena "." python scripts/rust/pensa.py --ckpt "$CKPT" --out "$OUT" --coppie "$COPPIE" \
  --iter-pensa "$ITER_PENSA" --iter-base "$ITER_BASE" --processi "$PROCESSI"
T1=$(t)
{
  echo "durata (s): arena $((T1 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"
echo
[ -f "$OUT/arena.txt" ] && { echo "--- $OUT/arena.txt"; cat "$OUT/arena.txt"; }
echo
echo "== fatto. Per riprendere: OUT=$OUT bash scripts/rust/pensa_mac.command"
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Pensare piu' a lungo: $ITER_PENSA contro $ITER_BASE iterazioni ($STAMP)\" && git push"
