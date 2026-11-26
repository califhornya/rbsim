#!/bin/bash
# Prior del campione + valore della rete nuova (Astra, 26/11): arena di sviluppo (d) e "seguiti" sulle posizioni nuove.
# Combinazione (d): prior di ckpt_040000, valore della rete nuova al 20% nelle foglie (80% valutazione a mano).
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/valore_mac.command
# Serve la rete nuova del pilota (runs/allena/generazione_20261126_1810/rete.pt, o RETE=...). Variabili d'ambiente:
#   COPPIE=100 PARTITE=6 PER_PARTITA=8 MONDI=32 PROCESSI=<n> CKPT=... RETE=... PILOTA=... OUT=...
# Rilanciato con OUT=<cartella> riprende: l'arena e i seguiti saltano il lavoro gia' fatto.
# Prerequisiti: uv, Rust (https://rustup.rs).
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -z "${CKPT:-}" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
PILOTA="${PILOTA:-docs/bot/esperimenti/generazione_20261126_1810}"
if [ -z "${RETE:-}" ]; then
  for c in runs/allena/generazione_20261126_1810/rete.pt ../rbsim/runs/allena/generazione_20261126_1810/rete.pt; do
    [ -f "$c" ] && { RETE="$c"; break; }
  done
fi
[ -f "$CKPT" ] || { echo "Manca il checkpoint del campione $CKPT"; exit 1; }
[ -n "${RETE:-}" ] && [ -f "$RETE" ] || { echo "Manca la rete nuova (rete.pt del pilota generazione_20261126_1810): indica RETE=<file>"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: https://rustup.rs"; exit 1; }
COPPIE="${COPPIE:-100}"
PARTITE="${PARTITE:-6}"
PER_PARTITA="${PER_PARTITA:-8}"
MONDI="${MONDI:-32}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="${OUT:-docs/bot/esperimenti/valore_$STAMP}"
mkdir -p "$OUT"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/valore
# esegui <file di uscita completa> <filtro egrep> <comando...>: l'uscita completa va in runs/valore/, a schermo e nel
# log solo le righe del filtro (ultime 30); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/valore/${STAMP}_$1.out" filtro="$2"; shift 2
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

# la rete deve essere quella del pilota
python - "$RETE" "$PILOTA" <<'PY' || exit 1
import json, sys
from pathlib import Path
from riftbound.provenienza import checkpoint_sha256
rete, pil = sys.argv[1], Path(sys.argv[2])
atteso = json.loads((pil / "arena_righe.jsonl.provenienza.json").read_text())["rete_sha256"]
if checkpoint_sha256(rete) != atteso:
    print(f"ERRORE: {rete} non e' la rete del pilota (sha256 diverso da quello in {pil})")
    raise SystemExit(1)
try:
    ep = json.loads((pil / "allenamento" / "misure.json").read_text()).get("epoca_scelta")
    print(f"rete del pilota verificata; epoca scelta {ep}" + ("" if ep == 5 else "  ATTENZIONE: attesa 5"))
except Exception as e:
    print(f"rete del pilota verificata; misure.json non leggibile ({e})")
PY
echo "processi: $PROCESSI; campione: $CKPT; rete nuova: $RETE; $COPPIE coppie; $PARTITE partite x $PER_PARTITA decisioni x $MONDI mondi" | tee -a "$LOG"
if [ -f "$PILOTA/durata.txt" ]; then
  SA="$(grep -oE 'arena [0-9]+' "$PILOTA/durata.txt" | head -1 | awk '{print $2}' || true)"
  [ -n "$SA" ] && echo "previsione arena: circa $((SA * 13 / 20)) s ($SA s del pilota x 0,5 x 1,3)" | tee -a "$LOG"
fi

T0=$(t)
passo "== 1. arena di sviluppo, combinazione (d) ($COPPIE coppie per matchup)"
esegui arena "^\(|^   |^Arena|^durata|^==" python scripts/rust/generazione.py arena --rete "$RETE" --campione "$CKPT" \
  --varianti d --out "$OUT" --coppie "$COPPIE" --processi "$PROCESSI"
T1=$(t)

passo "== 2. confronto con l'arena del pilota"
esegui confronto "." python scripts/rust/generazione.py confronto --righe "$OUT/arena_righe.jsonl" \
  --pilota "$PILOTA/arena_righe.jsonl" --out "$OUT"
T2=$(t)

passo "== 3. seguiti"
esegui seguiti "^== |^totale|Traceback|Error" python scripts/rust/seguiti.py --ckpt "$CKPT" --valore "$RETE" \
  --out "$OUT/seguiti" --partite "$PARTITE" --per-partita "$PER_PARTITA" --mondi "$MONDI" --processi "$PROCESSI"
T3=$(t)

{
  echo "durata dei passi (s): arena $((T1 - T0)), confronto $((T2 - T1)), seguiti $((T3 - T2)), totale $((T3 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"

echo
for f in "$OUT/arena.txt" "$OUT/confronto.txt"; do [ -f "$f" ] && { echo "--- $f"; cat "$f"; }; done
echo "--- $OUT/seguiti/riepilogo.txt"; tail -15 "$OUT/seguiti/riepilogo.txt"
echo
echo "== fatto. Per riprendere: OUT=$OUT bash scripts/rust/valore_mac.command"
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Prior del campione e valore della rete nuova: arena (d) e seguiti ($STAMP)\" && git push"
