#!/bin/bash
# Ivern su Rust, verifica col checkpoint vero sul Mac (porting, tappa Ivern). Doppio clic dal Finder o:
#   bash scripts/rust/ivern_mac.command [checkpoint.pt]
# Default: il campione, runs/sett/ekris_s12/ckpt_040000.pt (anche da un altro checkout:
#   bash scripts/rust/ivern_mac.command ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt).
# Prerequisiti: il ramo rust, uv, una toolchain Rust (https://rustup.rs).
# Cosa fa (niente training, niente arena di promozione), su EI, KI e RI nei due posti:
#  1. esempi PPO bit per bit col checkpoint (self-play e contro simple_trade, semi 1-20);
#  2. parità dell'arena col bot coi prior del checkpoint a 50 iterazioni (semi 40000-40009):
#     traccia e ogni ricerca identiche.
# Uscite: docs/rust/misure/mac_ivern_*.json e un riassunto a schermo.
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

for MU in EI KI RI; do
  echo "== 1. $MU: esempi PPO bit per bit col checkpoint (self-play, contro simple_trade)"
  python scripts/rust/parita_ppo.py --semi 1-20 --matchup "$MU" --posti --init "$CKPT" \
    --out "$OUT/mac_ivern_ppo_${MU}_self_$STAMP.json" | tail -1
  python scripts/rust/parita_ppo.py --semi 1-20 --matchup "$MU" --posti --init "$CKPT" --avversario simple_trade \
    --out "$OUT/mac_ivern_ppo_${MU}_simple_trade_$STAMP.json" | tail -1
done
for MU in EI KI RI; do
  echo "== 2. $MU: parità dell'arena col checkpoint, 50 iterazioni"
  python scripts/rust/arena_parita.py --semi 40000-40009 --matchup "$MU" --posti --bot prior --iterazioni 50 \
    --ckpt "$CKPT" --out "$OUT/mac_ivern_arena_${MU}_$STAMP.json" | tail -1
done
echo "== fatto: risultati in $OUT/mac_ivern_*_$STAMP.json"
read -r -p "Premi Invio per chiudere."
