#!/bin/bash
# Muovo prima contro schiero in base (Astra, 27/11): su posizioni dove un'unita' puo' andare su un campo libero e da li'
# un'altra unita' puo' essere schierata, "muovo prima" contro "schiero in base adesso", stessi mondi, campione a 138
# iterazioni con valutazione rimonta dopo la prima mossa. Replay salvati della pagina, esclusa la partita della scoperta.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/muovi_mac.command
# Avanzamento: tail -f runs/muovi/*_muovi.out
# Variabili d'ambiente: MONDI=100 PROCESSI=<n> CKPT=... OUT=...
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
MONDI="${MONDI:-100}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/muovi_$STAMP}"
mkdir -p "$OUT"
LOG="$OUT/log.txt"
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/muovi
# esegui <nome> <filtro egrep> <comando...>: l'uscita completa va in runs/muovi/, a schermo e nel log solo le righe del
# filtro (ultime 30); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/muovi/${STAMP}_$1.out" filtro="$2"; shift 2
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
echo "processi: $PROCESSI; campione: $CKPT; $MONDI mondi per posizione" | tee -a "$LOG"

passo "== muovo prima contro schiero in base"
esegui muovi "^== |^totale|Traceback|Error" python scripts/rust/muovi.py --ckpt "$CKPT" --out "$OUT" \
  --mondi "$MONDI" --processi "$PROCESSI"

echo
echo "--- $OUT/riepilogo.txt"; tail -15 "$OUT/riepilogo.txt"
echo
echo "== fatto. Per riprendere: OUT=$OUT bash scripts/rust/muovi_mac.command"
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Muovo prima contro schiero in base ($STAMP)\" && git push"
