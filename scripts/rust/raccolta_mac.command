#!/bin/bash
# Raccolta pilota del campione contro se stesso (riftbound/rs/raccolta.py): partite con esplorazione e registro per
# riallenare la rete con la ricerca. Rilanciato riprende dalle partite gia' fatte.
# Da lanciare con:  bash scripts/rust/raccolta_mac.command [nome] [partite-per-matchup] [checkpoint.pt]
# Predefiniti: nome "pilota", 200 partite per matchup (2.000 in tutto), runs/sett/ekris_s12/ckpt_040000.pt.
# Uscite: runs/raccolta/<nome>/ (partite/, indice.jsonl, provenienza.json, misura.txt, intestazione.txt). Stampa la
# misura (partite/ora, secondi, byte, stima per 100.000 partite) dopo le prime 200 partite e alla fine.
set -euo pipefail
NOME="${1:-pilota}"
PPM="${2:-200}"
CKPT="${3:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
cd "$(dirname "$0")/../.."
if [ -z "$CKPT" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
[ -n "$CKPT" ] && [ -f "$CKPT" ] || { echo "Manca il checkpoint ckpt_040000.pt (passalo come terzo argomento)"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
OUT="runs/raccolta/${NOME}"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
echo "== raccolta ${NOME}: ${PPM} partite per matchup (10 matchup), checkpoint $CKPT, $W processi"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "raccolta_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); ${PPM} partite per matchup"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/intestazione.txt"

python scripts/rust/raccolta.py --nome "$NOME" --partite-per-matchup "$PPM" --ckpt "$CKPT" --processi "$W" 2>&1 \
  | grep -vE "unsendable|^$" || true
echo
cat "$OUT/misura.txt" 2>/dev/null | tail -10
echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT (non versionare: sono dati grandi)."
