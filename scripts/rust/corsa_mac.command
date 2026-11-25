#!/bin/bash
# §8 minaccia e corsa: due arene una dopo l'altra, ciascun candidato (valutazione "minaccia", poi "corsa") contro il
# campione attuale (valutazione storica). Doppio clic dal Finder o:  bash scripts/rust/corsa_mac.command [checkpoint.pt]
# Stessa rete (ckpt_040000) e stessi prior per entrambi, 138 iterazioni per lato, ricerca della vittoria nel turno
# accesa per entrambi, regole 6427b90+D72-D80, semi nuovi (da 80000), posti scambiati: 800 coppie per ES e per EK.
# Uscite: docs/bot/accumulo/arena_corsa_<data>/ (riepilogo.txt con entrambi i riepiloghi) e uno zip sulla Scrivania.
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
OUT="docs/bot/accumulo/arena_corsa_$STAMP"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Una partita a 138 iterazioni: circa 2,3 s di un core (misura del 25/11 nel cloud; sul Mac di solito meno).
MIN=$(awk -v g=6400 -v w="$W" 'BEGIN { printf "%.0f", g * 2.3 / w / 60 + 0.5 }')
echo "== §8 minaccia e corsa: due candidati contro il campione; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, due arene circa $MIN min in tutto (6.400 partite)"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "corsa_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); regole 6427b90+D72-D80"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/riepilogo.txt"

for CAND in minaccia corsa; do
  echo "arena $CAND ($(date +%H:%M))"
  python scripts/diag/arena_mazzi.py --motore rust --regole 6427b90+D72-D80 \
    --ckpt "$CKPT" --ckpt-avversario "$CKPT" \
    --vecchi EK --blocchi ES --coppie EK=800 ES=800 --seed0 80000 --workers "$W" \
    --iterazioni-candidato 138 --iterazioni-avversario 138 --win-probe-candidato --win-probe-avversario \
    --valutazione-c "$CAND" \
    --out "$OUT/arena_$CAND.txt" > "$OUT/arena_${CAND}_schermo.txt" 2>&1 || { tail -5 "$OUT/arena_${CAND}_schermo.txt"; }
  { echo; echo "== candidato $CAND contro il campione (storica)"; } >> "$OUT/riepilogo.txt"
  tail -25 "$OUT/arena_$CAND.txt" >> "$OUT/riepilogo.txt" 2>/dev/null || tail -25 "$OUT/arena_${CAND}_schermo.txt" >> "$OUT/riepilogo.txt"
done

ZIP="$HOME/Desktop/arena_corsa_$STAMP.zip"
zip -q -r "$ZIP" "$OUT"
echo
echo "== fatto ($(date +%H:%M)). Trascina in chat: $ZIP"
echo "   (le righe PROMOSSO/no stampate dall'arena non contano: conta il punteggio per matchup con l'IC al 95% per ciascun candidato)"
