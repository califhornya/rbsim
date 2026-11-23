#!/bin/bash
# Confronto ufficiale Python / Rust sul Mac (porting, EK). Doppio clic dal
# Finder o: bash scripts/rust/confronto_mac.command [checkpoint.pt]
# Prerequisiti: il worktree del ramo claude/peaceful-lamport-gynyab, uv, una
# toolchain Rust (https://rustup.rs). Niente training, niente Cherry: misura e basta.
# Uscite: docs/rust/misure/mac_*.json e un riassunto a schermo.
set -euo pipefail
cd "$(dirname "$0")/../.."
CKPT="${1:-runs/rengar/ekr_s8/ckpt_020032.pt}"
OUT=docs/rust/misure
STAMP=$(date +%Y%m%d_%H%M)
mkdir -p "$OUT"

echo "== ambiente"
uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
sysctl -n machdep.cpu.brand_string 2>/dev/null || true
rustc --version
git log --oneline -1

echo "== compilazione dell'estensione (release, tempo a parte)"
T0=$(date +%s)
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1)
echo "compilazione: $(( $(date +%s) - T0 )) s"

echo "== verifica (deve caricare davvero riftbound_rs)"
python -m pytest -q tests/rust 2>&1 | tail -1

INIT=()
if [ -f "$CKPT" ]; then INIT=(--init "$CKPT"); echo "checkpoint: $CKPT"; else echo "checkpoint assente ($CKPT): pesi dal seme 1"; fi

echo "== parità degli esempi PPO col checkpoint (Python contro Rust)"
python scripts/rust/parita_ppo.py --semi 1-20 "${INIT[@]}" --out "$OUT/mac_parita_$STAMP.json" | tail -1

echo "== raccolta su un core, ordine alternato (self-play e contro simple_trade)"
python scripts/rust/bench_raccolta.py --semi 1-100 "${INIT[@]}" --out "$OUT/mac_raccolta_self_$STAMP.json" | grep -E '"rapporto_totale"|"totale_s"'
python scripts/rust/bench_raccolta.py --semi 1-100 --avversario simple_trade "${INIT[@]}" --out "$OUT/mac_raccolta_st_$STAMP.json" | grep -E '"rapporto_totale"|"totale_s"'

echo "== ciclo PPO completo (raccolta + aggiornamento), motori alternati"
W=$(( $(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || sysctl -n hw.ncpu) ))
for M in python rust python rust; do
  python scripts/rust/bench_ppo_ciclo.py --cicli 3 --workers "$W" --seme 1 "${INIT[@]}" --motore "$M" \
    --out "$OUT/mac_ciclo_${M}_${STAMP}_$RANDOM.json" | tail -2
done
echo "== fatto: risultati in $OUT/mac_*_$STAMP*.json"
