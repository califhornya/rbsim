#!/bin/bash
# Movimento dalla base (Astra, 27/11): partite NUOVE del campione, posizioni dove si puo' muovere prima di schierare,
# controllo offline della quota alla radice (8 visite iniziali ai figli "base→bf"), poi l'arena solo se passa.
# Passo 1: PARTITE partite per matchup (10 matchup); per ogni posizione quattro linee sugli stessi MONDI mondi:
#   campione (mossa originale), muovo prima, schiero in base, con quota. Regola di stop: limite inferiore di
#   Q - campione > 0.
# Passo 2 (solo se passa): arena, campione con quota contro campione, COPPIE coppie per matchup, semi nuovi.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/movimento.command
#   (su un server: dentro tmux, dopo scripts/rust/server_prepara.sh)
# Avanzamento: tail -f runs/movimento/*.out
# Variabili d'ambiente: PARTITE=6 MONDI=100 COPPIE=100 PROCESSI=<ncpu-1> CKPT=... OUT=...
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
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
command -v rustc >/dev/null || { echo "manca Rust: https://rustup.rs"; exit 1; }
PARTITE="${PARTITE:-6}"
MONDI="${MONDI:-100}"
COPPIE="${COPPIE:-100}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/movimento_$STAMP}"
mkdir -p "$OUT"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/movimento
# esegui <nome> <filtro egrep> <comando...>: l'uscita completa va in runs/movimento/, a schermo e nel log solo le righe
# del filtro (ultime 30); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/movimento/${STAMP}_$1.out" filtro="$2"; shift 2
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
echo "processi: $PROCESSI; campione: $CKPT; $PARTITE partite x 10 matchup x $MONDI mondi; $COPPIE coppie" | tee -a "$LOG"

T0=$(t)
passo "== 1. posizioni: partite nuove, muovo prima / schiero in base / con quota"
esegui posizioni "^== |^totale|^regola|Traceback|Error" python scripts/rust/muovi.py --autonome-nuove "$PARTITE" --quota \
  --ckpt "$CKPT" --mondi "$MONDI" --processi "$PROCESSI" --out "$OUT/posizioni"
T1=$(t)

PASSA="$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['passa'])" "$OUT/posizioni/esito.json")"
if [ "$PASSA" = "True" ]; then
  passo "== 2. arena ($COPPIE coppie per matchup)"
  esegui arena "^== |^totale|^criterio|Traceback|Error" python scripts/rust/movimento_arena.py --ckpt "$CKPT" \
    --out "$OUT/arena" --coppie "$COPPIE" --processi "$PROCESSI"
else
  passo "Regola di stop: niente arena, il campione resta com'è."
fi
T2=$(t)

{
  echo "durata dei passi (s): posizioni $((T1 - T0)), arena $((T2 - T1)), totale $((T2 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"

echo
echo "--- $OUT/posizioni/riepilogo.txt"; tail -15 "$OUT/posizioni/riepilogo.txt"
[ -f "$OUT/arena/arena.txt" ] && { echo "--- $OUT/arena/arena.txt"; cat "$OUT/arena/arena.txt"; }
echo
echo "== fatto. Per riprendere: OUT=$OUT bash scripts/rust/movimento.command"
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Movimento dalla base: posizioni e arena ($STAMP)\" && git push"
