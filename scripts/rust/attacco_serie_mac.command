#!/bin/bash
# Attacco, solo la serie (riftbound/rs/attacco.py): `serie` su un elenco di posizioni gia' trovato da
# attacco_mac.command (posizioni.json), senza rifare riproduzione del T9 e ricerca delle posizioni.
# Da lanciare con:  bash scripts/rust/attacco_serie_mac.command [posizioni.json] [checkpoint.pt]
# Predefiniti: l'ultimo docs/bot/esperimenti/attacco_*/posizioni.json; al piu' 24 posizioni (meta' con un punto libero).
# Uscite: docs/bot/esperimenti/attacco_<data_ora>_serie/ (riepilogo.txt con la riga "totale:"; una cartella per
# posizione con esito.txt/esito.json, proposte.json, scelta.jsonl, verifica.jsonl, vista.json): da versionare.
set -euo pipefail
POS="${1:-}"
CKPT="${2:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
if [ -n "$POS" ] && [ -f "$POS" ]; then POS="$(cd "$(dirname "$POS")" && pwd)/$(basename "$POS")"; fi
cd "$(dirname "$0")/../.."
if [ -z "$POS" ]; then
  POS=$(ls -d docs/bot/esperimenti/attacco_*/posizioni.json 2>/dev/null | sort | tail -1 || true)
fi
[ -n "$POS" ] && [ -f "$POS" ] || { echo "Manca posizioni.json (lancia prima attacco_mac.command o passalo come argomento)"; exit 1; }
if [ -z "$CKPT" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
[ -n "$CKPT" ] && [ -f "$CKPT" ] || { echo "Manca il checkpoint ckpt_040000.pt (passalo come secondo argomento)"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
MAX=24
STAMP=$(date +%Y%m%d_%H%M)
OUT="docs/bot/esperimenti/attacco_${STAMP}_serie"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Sul Mac (26/11, 9 processi) una posizione con 18 proposte costa circa 1,5 min (16 mondi x 19 linee + 100 x 2).
MIN=$(awk -v w="$W" -v n="$MAX" 'BEGIN { printf "%.0f", n * 1.5 * 9 / w }')
echo "== attacco, serie; posizioni $POS; al piu' $MAX; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, poi circa $MIN min"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "attacco_serie_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); posizioni $POS; al piu' $MAX"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/intestazione.txt"

python scripts/rust/attacco.py serie --posizioni "$POS" --max "$MAX" --ckpt "$CKPT" --processi "$W" \
  --out "$OUT" 2>&1 | grep -E "^== posizione|selezione:|Traceback|Error" || true
echo
cat "$OUT/riepilogo.txt" 2>/dev/null | tail -30
echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT."
echo "   Versiona:  git add docs/bot/esperimenti/attacco_${STAMP}_serie && git commit -m 'Attacco: serie' && git push"
