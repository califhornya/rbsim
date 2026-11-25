#!/bin/bash
# Calibrare il campione della pagina, sul Mac col checkpoint vero. Doppio clic dal Finder o:
#   bash scripts/rust/calibra_mac.command [checkpoint.pt]
# Default: il campione, runs/sett/ekris_s12/ckpt_040000.pt.
# Prerequisiti: il ramo rust, uv, una toolchain Rust (https://rustup.rs).
# Cosa fa (regole 6427b90+D72-D77, matchup ES ed EK), in ordine:
#  1. misura: campione@42+probe contro campione@0,030 s+probe, 20 partite per matchup; iterazioni a
#     0,030 s e secondi a 42 iterazioni per tipo di punto; N suggerito = mediana del turno;
#  2. concordanza delle mosse (scripts/rust/decisione.py) alle iterazioni N suggerite per il turno;
#  3. forza: campione@N+probe contro campione@0,030 s+probe, 400 coppie per matchup,
#     non inferiore se il limite inferiore dell'IC 95% > 0,47;
#  4. profilo: campione@0,030 s contro il bot a mano senza prior @0,030 s, 200 coppie per matchup.
# Uscite: docs/rust/misure/calibra_<data>/ (file completi) e un riassunto a schermo da copiare.
set -euo pipefail
CKPT="${1:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
cd "$(dirname "$0")/../.."
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
[ -f "$CKPT" ] || { echo "Manca il checkpoint $CKPT"; exit 1; }
OUT="docs/rust/misure/calibra_$(date +%Y%m%d_%H%M)"
mkdir -p "$OUT"
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Una partita a 0,030 s dura circa 2,4 s (misura del 24/11 sul Mac); le partite vanno in W processi.
stima() { awk -v g="$1" -v w="$W" 'BEGIN { printf "%.0f", g * 2.4 / w / 60 + 0.5 }'; }
M_MISURA=$(stima 40); M_FORZA=$(stima 1600); M_PROFILO=$(stima 800)
echo "== calibra il campione: checkpoint $CKPT, $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min; 1 misura ~${M_MISURA} min; 2 concordanza ~3-6 min;"
echo "   3 forza ~${M_FORZA} min; 4 profilo ~${M_PROFILO} min; in tutto circa $(( M_MISURA + M_FORZA + M_PROFILO + 8 )) min"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "calibra_campione $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); regole 6427b90+D72-D77"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/riepilogo.txt"

echo "[1/4] misura ($(date +%H:%M), ~${M_MISURA} min)"
python scripts/rust/calibra_campione.py misura --ckpt "$CKPT" --matchup ES EK --partite 20 --workers "$W" \
  --out "$OUT" > "$OUT/misura.txt" 2>&1 || { tail -5 "$OUT/misura.txt"; exit 1; }
N=$(python -c "import json,sys; print(json.load(open('$OUT/misura.json'))['N_suggerito']['turno'])")
grep -E '^misura' "$OUT/misura.txt" >> "$OUT/riepilogo.txt"

echo "[2/4] concordanza delle mosse a $N iterazioni ($(date +%H:%M), ~3-6 min)"
python scripts/rust/decisione.py concordanza --matchup ES EK --semi 10 --iterazioni "$N" \
  > "$OUT/concordanza.txt" 2>&1 || echo "concordanza: fallita (vedi $OUT/concordanza.txt)" >> "$OUT/riepilogo.txt"
{ echo "concordanza (N=$N):"; tail -4 "$OUT/concordanza.txt"; } >> "$OUT/riepilogo.txt"

echo "[3/4] forza a $N iterazioni ($(date +%H:%M), ~${M_FORZA} min)"
python scripts/rust/calibra_campione.py forza --ckpt "$CKPT" --coppie ES=400 EK=400 --iterazioni "$N" --workers "$W" \
  --out "$OUT" > "$OUT/forza_schermo.txt" 2>&1 || { tail -5 "$OUT/forza_schermo.txt"; }
grep -E '^forza' "$OUT/forza_schermo.txt" >> "$OUT/riepilogo.txt" || true

echo "[4/4] profilo ($(date +%H:%M), ~${M_PROFILO} min)"
python scripts/rust/calibra_campione.py profilo --ckpt "$CKPT" --coppie ES=200 EK=200 --workers "$W" \
  --out "$OUT" > "$OUT/profilo_schermo.txt" 2>&1 || { tail -5 "$OUT/profilo_schermo.txt"; }
grep -E '^profilo' "$OUT/profilo_schermo.txt" >> "$OUT/riepilogo.txt" || true

echo
echo "===== RIASSUNTO (da copiare) ====="
cat "$OUT/riepilogo.txt"
echo "file completi in $OUT"
read -r -p "Premi Invio per chiudere."
