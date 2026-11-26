#!/bin/bash
# Sonda A a un'ondata (riftbound/rs/sonda.py), prototipo offline: congelamento sulle 24 della serie, prova fuori
# campione su partite nuove e caso diagnostico del T9.
# Da lanciare con:  bash scripts/rust/sonda_mac.command [checkpoint.pt]
# Uscite: docs/bot/esperimenti/sonda_<data_ora>/  congela/ (congela.txt, riga "totale:"), posizioni.json, fuori/
# (riepilogo.txt, una cartella per posizione), t9_foglia/ (diagnosi_t9.txt): da versionare.
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
SERIE=docs/bot/esperimenti/attacco_20261126_1352_serie
[ -d "$SERIE" ] || { echo "Manca la serie $SERIE"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M)
OUT="docs/bot/esperimenti/sonda_${STAMP}"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Stima: sonda ~20 s cpu per posizione, verifica 100 mondi x 2 linee ~2 s ciascuna; 72 posizioni; congela ~24 x 20 s;
# t9-foglia 100 mondi x 2 modi x 5 linee ~2 s; la ricerca delle posizioni ~1 min per partita (14 partite autonome).
MIN=$(awk -v w="$W" 'BEGIN { printf "%.0f", (72 * (20 + 400) + 24 * 20 + 2000 + 14 * 60) / 60 / w }')
echo "== sonda A; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, poi circa $MIN min"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "sonda_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1)"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/intestazione.txt"

FILTRO="^== |^totale:|^gruppo |^differenza media|Traceback|Error|ERRORE"

echo "== 1/4 congela (la sonda sulle 24 della serie)"
python scripts/rust/attacco.py congela --serie "$SERIE" --out "$OUT/congela" --ckpt "$CKPT" --processi "$W" 2>&1 \
  | grep -E "$FILTRO" || true
echo "== 2/4 posizioni su partite nuove (ES ed EK semi 100-107, ER KR EI KI semi 100-101)"
AUT=""
for mu in ES EK; do
  for s in 100 101 102 103 104 105 106 107; do
    P=A; [ $((s % 2)) -eq 1 ] && P=B
    AUT="$AUT $mu:$s:$P"
  done
done
for mu in ER KR EI KI; do AUT="$AUT $mu:100:A $mu:101:B"; done
# shellcheck disable=SC2086
python scripts/rust/attacco.py posizioni --autonoma $AUT --regole 6427b90+D72-D82 --valutazione rimonta \
  --iterazioni 138 --ckpt "$CKPT" --out "$OUT/posizioni.json" 2>&1 | grep -E "posizioni|Traceback|Error" || true
echo "== 3/4 fuori campione"
python scripts/rust/attacco.py fuori --posizioni "$OUT/posizioni.json" --out "$OUT/fuori" \
  --per-matchup ES=24,EK=24,ER=6,KR=6,EI=6,KI=6 --ckpt "$CKPT" --processi "$W" 2>&1 | grep -E "$FILTRO" || true
echo "== 4/4 t9-foglia (caso diagnostico)"
python scripts/rust/attacco.py t9-foglia --out "$OUT/t9_foglia" --ckpt "$CKPT" --processi "$W" 2>&1 \
  | grep -E "$FILTRO" || true
echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT."
echo "   Versiona:  git add $OUT && git commit -m 'Sonda A: congela, fuori campione, T9' && git push"
