#!/bin/bash
# Primo responso (riftbound/rs/responso.py): quando prior, visite e Q indicano mosse diverse, quale vince di piu'?
# 10 matchup x semi 300 e 301 (partite campione contro campione, regole 6427b90+D72-D83, valutazione rimonta, 138
# iterazioni), fino a 4 decisioni di turno per partita rifatte a 138 e 512 iterazioni; dove c'e' disaccordo ogni mossa
# e' giocata fino alla fine su 32 mondi `ignote` (indici da 7000).
# Da lanciare con:  bash scripts/rust/responso_mac.command [checkpoint.pt]
# Uscite: docs/bot/esperimenti/responso_<data_ora>/ (riepilogo.txt con la riga "totale:"; una cartella per decisione
# con decisione.json e mondi.jsonl): da versionare.
set -euo pipefail
CKPT="${1:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
cd "$(dirname "$0")/../.."
if [ -z "$CKPT" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
[ -n "$CKPT" ] && [ -f "$CKPT" ] || { echo "Manca il checkpoint ckpt_040000.pt (passalo come argomento)"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M)
OUT="docs/bot/esperimenti/responso_${STAMP}"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Stima (prove 26/11 con pesi casuali, 1 core): ~2 s per linea e mondo da meta' partita; 80 decisioni, ~40% con
# disaccordo, ~3 linee, 32 mondi; raddoppiata per la rete vera. Sul Mac con 8-9 processi: circa 30-40 min.
MIN=$(awk -v w="$W" 'BEGIN { printf "%.0f", 80 * 0.4 * 3 * 32 * 4 / 60 / w + 5 }')
echo "== responso; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, poi circa $MIN min"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "responso_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1)"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/intestazione.txt"

python scripts/rust/responso.py --ckpt "$CKPT" --processi "$W" --out "$OUT" 2>&1 \
  | grep -E "^== decisioni|^== decisione|Traceback|Error" || true
echo
tail -30 "$OUT/riepilogo.txt" 2>/dev/null
echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT."
echo "   Versiona:  git add docs/bot/esperimenti/responso_${STAMP} && git commit -m 'Responso: primo' && git push"
