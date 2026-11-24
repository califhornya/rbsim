#!/bin/bash
# Arena EK su Rust, verifica sul Mac (porting, tappa A). Doppio clic dal Finder o:
#   bash scripts/rust/arena_mac.command [checkpoint.pt]
# Default: il campione, runs/sett/ekris_s12/ckpt_040000.pt (anche da un altro checkout:
#   bash scripts/rust/arena_mac.command ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt).
# Prerequisiti: il ramo rust, uv, una toolchain Rust (https://rustup.rs).
# Cosa fa (niente training, niente arena di promozione):
#  1. parità Python / Rust del bot coi prior del checkpoint a 50 iterazioni (semi 40000-40019,
#     posti scambiati): traccia e ogni ricerca identiche;
#  2. tempo per partita a lavoro fisso (50 iterazioni), Python e Rust, un processo, stessi semi.
# Uscite: docs/rust/misure/mac_arena_*.json e un riassunto a schermo.
set -euo pipefail
CKPT="${1:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
cd "$(dirname "$0")/../.."
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
[ -f "$CKPT" ] || { echo "Manca il checkpoint $CKPT"; exit 1; }
OUT=docs/rust/misure
STAMP=$(date +%Y%m%d_%H%M)
mkdir -p "$OUT"
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }

echo "== ambiente"
uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
sysctl -n machdep.cpu.brand_string 2>/dev/null || true
rustc --version
git log --oneline -1
echo "checkpoint: $CKPT"

echo "== compilazione dell'estensione (release)"
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1)

echo "== verifica (deve caricare davvero riftbound_rs)"
python -m pytest -q tests/rust 2>&1 | tail -1

echo "== 1. parità dell'arena col checkpoint, 50 iterazioni"
python scripts/rust/arena_parita.py --semi 40000-40019 --bot prior --iterazioni 50 --ckpt "$CKPT" \
  --out "$OUT/mac_arena_parita_$STAMP.json" | tail -1

echo "== 2. tempo per partita a 50 iterazioni (Python, Rust, Python, Rust)"
for M in python rust python rust; do
  python scripts/rust/bench_arena_fisso.py --coppie 4 --iterazioni 50 --ckpt "$CKPT" --motore "$M" \
    --out "$OUT/mac_arena_fisso_${M}_${STAMP}_$RANDOM.json" | grep -E '"motore"|"mediana_parete_s"|"totale_s"'
done
echo "== fatto: risultati in $OUT/mac_arena_*_$STAMP*.json"
read -r -p "Premi Invio per chiudere."
