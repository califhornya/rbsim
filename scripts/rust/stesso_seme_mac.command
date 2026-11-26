#!/bin/bash
# Serie «stesso seme» (riftbound/rs/stesso_seme.py): la partita di Matteo (Evelynn contro Sett) rifatta dal Mac da sola,
# dal turno 1, con lo stesso seme, fino alla prima vittoria di Sett nella simulazione (al piu' X partite).
# Da lanciare con:  bash scripts/rust/stesso_seme_mac.command [partita.json] [X] [checkpoint.pt]
# Predefiniti: l'ultima runs/coach/partite/*evelynn*sett*.json (quella salvata dalla pagina); X = 500.
# Uscite: docs/bot/esperimenti/stesso_seme_<data_ora>/ (riepilogo.txt con la riga "totale:", tentativi.jsonl,
# vittoria.json, sconfitta.json, matteo.json, la partita base): da versionare.
set -euo pipefail
PARTITA="${1:-}"
X="${2:-500}"
CKPT="${3:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
if [ -n "$PARTITA" ] && [ -f "$PARTITA" ]; then PARTITA="$(cd "$(dirname "$PARTITA")" && pwd)/$(basename "$PARTITA")"; fi
cd "$(dirname "$0")/../.."
if [ -z "$PARTITA" ]; then
  PARTITA=$(ls runs/coach/partite/*evelynn*sett*.json 2>/dev/null | sort | tail -1 || true)
fi
[ -n "$PARTITA" ] && [ -f "$PARTITA" ] || { echo "Manca la partita (runs/coach/partite/*evelynn*sett*.json: giocala nella pagina o passala come argomento)"; exit 1; }
if [ -z "$CKPT" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
[ -n "$CKPT" ] && [ -f "$CKPT" ] || { echo "Manca il checkpoint ckpt_040000.pt (passalo come terzo argomento)"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M)
OUT="docs/bot/esperimenti/stesso_seme_${STAMP}"
mkdir -p "$OUT" docs/bot/partite/coach
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Una partita completa campione contro campione costa circa 3 s su un processo (Mac, 26/11): al piu' X*3/W secondi,
# meno se Sett vince prima.
MAXMIN=$(awk -v w="$W" -v n="$X" 'BEGIN { printf "%.0f", n * 3 / w / 60 + 1 }')
echo "== stesso seme; partita $PARTITA; al piu' $X tentativi; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, poi al piu' circa $MAXMIN min (si ferma alla prima vittoria di Sett)"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
# La partita base resta con i risultati e fra le partite della pagina versionate.
cp -n "$PARTITA" "$OUT/" && cp -n "$PARTITA" docs/bot/partite/coach/ || true
{
  echo "stesso_seme_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); partita $(basename "$PARTITA"); al piu' $X"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/intestazione.txt"

python scripts/rust/stesso_seme.py --partita "$PARTITA" --x "$X" --processi "$W" --ckpt "$CKPT" --out "$OUT" 2>&1 \
  | grep -E "partita di Matteo|tentativi:|Traceback|Error|^  File" || true
echo
tail -25 "$OUT/riepilogo.txt" 2>/dev/null | cut -c1-200
echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT."
echo "   Versiona:  git add $OUT docs/bot/partite/coach && git commit -m 'Stesso seme: serie' && git push"
