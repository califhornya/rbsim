#!/bin/bash
# §8 rimonta, tenuta: il candidato "rimonta" contro il campione (storica) sugli otto matchup fra E, K, R, I, S
# che l'arena precedente non copriva (ER EI KR KI KS RI RS IS), come controlli di tenuta.
# Da lanciare con:  bash scripts/rust/rimonta_tenuta_mac.command [checkpoint.pt]
# Stessa rete (ckpt_040000) e stessi prior per entrambi, 138 iterazioni per lato, ricerca della vittoria nel turno
# accesa per entrambi, regole 6427b90+D72-D80, semi nuovi (da 100000), posti scambiati: 300 coppie per ciascuno degli otto matchup.
# Uscite: runs/arene/rimonta_tenuta_<data>/ (riepilogo.txt, fuori dai file versionati) e uno zip sulla Scrivania.
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
OUT="runs/arene/rimonta_tenuta_$STAMP"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Una partita a 138 iterazioni: circa 2,3 s di un core (misura del 25/11 nel cloud; sul Mac di solito meno).
MIN=$(awk -v g=4800 -v w="$W" 'BEGIN { printf "%.0f", g * 2.3 / w / 60 + 0.5 }')
echo "== §8 rimonta, tenuta: candidato rimonta contro il campione; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, arena circa $MIN min (4.800 partite)"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "rimonta_tenuta_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); regole 6427b90+D72-D80"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/riepilogo.txt"

CAND=rimonta
echo "arena $CAND ($(date +%H:%M))"
python scripts/diag/arena_mazzi.py --motore rust --regole 6427b90+D72-D80 \
  --ckpt "$CKPT" --ckpt-avversario "$CKPT" \
  --vecchi ER EI KR KI KS RI RS IS --blocchi --coppie ER=300 EI=300 KR=300 KI=300 KS=300 RI=300 RS=300 IS=300 --seed0 100000 --workers "$W" \
  --iterazioni-candidato 138 --iterazioni-avversario 138 --win-probe-candidato --win-probe-avversario \
  --valutazione-c "$CAND" \
  --out "$OUT/arena_$CAND.txt" > "$OUT/arena_${CAND}_schermo.txt" 2>&1 || { tail -5 "$OUT/arena_${CAND}_schermo.txt"; }
{ echo; echo "== candidato $CAND contro il campione (storica), tenuta sugli otto matchup"; } >> "$OUT/riepilogo.txt"
tail -25 "$OUT/arena_$CAND.txt" >> "$OUT/riepilogo.txt" 2>/dev/null || tail -25 "$OUT/arena_${CAND}_schermo.txt" >> "$OUT/riepilogo.txt"

ZIP="$HOME/Desktop/arena_rimonta_tenuta_$STAMP.zip"
zip -q -r "$ZIP" "$OUT"
echo
echo "== fatto ($(date +%H:%M)). Trascina in chat: $ZIP"
echo "   (le righe PROMOSSO/no stampate dall'arena non contano: conta il punteggio per matchup con l'IC al 95%)"
