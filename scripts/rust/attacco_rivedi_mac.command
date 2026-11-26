#!/bin/bash
# Attacco, verifiche in piu' su una serie gia' fatta (riftbound/rs/attacco.py, `rivedi`): sonde della valutazione a
# fine turno e dopo l'avversario, migliore per vittorie, ricerca del campione con finestre e quota.
# Da lanciare con:  bash scripts/rust/attacco_rivedi_mac.command [serie_dir] [checkpoint.pt]
# Predefinito: l'ultimo docs/bot/esperimenti/attacco_*_serie (quello fatto da attacco_serie_mac.command).
# Uscite: <serie_dir>/rivedi_<data_ora>/ (rivedi.txt con la riga "totale:"; una cartella per posizione con
# rivedi.json e verifica_extra.jsonl): da versionare.
set -euo pipefail
SERIE="${1:-}"
CKPT="${2:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
if [ -n "$SERIE" ] && [ -d "$SERIE" ]; then SERIE="$(cd "$SERIE" && pwd)"; fi
cd "$(dirname "$0")/../.."
if [ -z "$SERIE" ]; then
  SERIE=$(ls -d docs/bot/esperimenti/attacco_*_serie 2>/dev/null | sort | tail -1 || true)
fi
[ -n "$SERIE" ] && [ -d "$SERIE" ] || { echo "Manca la serie (lancia prima attacco_serie_mac.command o passala come argomento)"; exit 1; }
if [ -z "$CKPT" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
[ -n "$CKPT" ] && [ -f "$CKPT" ] || { echo "Manca il checkpoint ckpt_040000.pt (passalo come secondo argomento)"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M)
OUT="$SERIE/rivedi_${STAMP}"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
NPOS=$(ls -d "$SERIE"/*/esito.json 2>/dev/null | wc -l | tr -d ' ')
# Circa 1,5 s di un core per continuazione, 100 continuazioni per ogni linea in piu' (di solito 1-3 per posizione
# con qualcosa da verificare); una ricerca con le finestre costa il doppio (5 ricerche per ogni attacco migliore).
MIN=$(awk -v w="$W" -v n="$NPOS" 'BEGIN { printf "%.0f", n * 2 * 100 * 1.5 / 60 / w }')
echo "== attacco, rivedi; serie $SERIE ($NPOS posizioni); checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, poi circa $MIN min (circa 1,5 s di un core per continuazione,"
echo "   100 per linea in piu'; le ricerche con le finestre costano x2)"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "attacco_rivedi_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); serie $SERIE"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/intestazione.txt"

python scripts/rust/attacco.py rivedi --serie "$SERIE" --ckpt "$CKPT" --processi "$W" --out "$OUT" \
  2>&1 | grep -E "^== |Traceback|Error|^totale" || true
echo
cat "$OUT/rivedi.txt" 2>/dev/null | tail -40
echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT."
echo "   Versiona:  git add $OUT && git commit -m 'Attacco: rivedi' && git push"
