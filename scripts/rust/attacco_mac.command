#!/bin/bash
# Attacco: il campione contro linee di attacco proposte (riftbound/rs/attacco.py, scripts/rust/attacco.py).
# Da lanciare con:  bash scripts/rust/attacco_mac.command [checkpoint.pt]
# 1. riproduci-t9: la prova di Astra sul T9 (partita 013325, k=10) rifatta e confrontata mondo per mondo coi suoi dati
#    (docs/bot/esperimenti/t9_attacco/dati): IDENTICO oppure le prime differenze (se non e' identico lo dice e prosegue);
# 2. il T9 con riferimento `campione` (nessun controllo forzato) -> t9_campione/;
# 3. posizioni: sulle 5 partite di docs/bot/partite/coach/*.json e su partite autonome ES ed EK (semi 0-9, posto A/B
#    alterni, regole 6427b90+D72-D82, valutazione rimonta, 138 iterazioni, win probe: come la pagina) -> posizioni.json;
# 4. serie su al piu' 12 posizioni (meta' con un punto libero, se ce ne sono) -> serie/ (riepilogo.txt: una riga per
#    posizione; per ognuna esito.txt/esito.json, proposte.json, scelta.jsonl, verifica.jsonl, vista.json).
# Uscite: docs/bot/esperimenti/attacco_<data>/  (da versionare).
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
STAMP=$(date +%Y%m%d)
OUT="docs/bot/esperimenti/attacco_$STAMP"
T9="docs/bot/partite/coach/20261126_013325_competitive_evelynn_vs_competitive_sett.json"
DATI="docs/bot/esperimenti/t9_attacco/dati"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# Una continuazione costa circa 1,5 s di un core. Per posizione: 16 mondi di scelta x (1 + proposte distinte, da 8 a 36)
# + 100 mondi di verifica x 2; il T9 (riproduzione e riferimento campione): 16 x 19 + 100 x 2 = 504 ciascuno.
MIN_T9=$(awk -v w="$W" 'BEGIN { printf "%.0f", 2 * 504 * 1.5 / w / 60 }')
MIN_A=$(awk -v w="$W" 'BEGIN { printf "%.0f", (2 * 504 + 12 * (16 * 9 + 200)) * 1.5 / w / 60 }')
MIN_B=$(awk -v w="$W" 'BEGIN { printf "%.0f", (2 * 504 + 12 * (16 * 37 + 200)) * 1.5 / w / 60 }')
echo "== attacco; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, poi da circa $MIN_A a circa $MIN_B min (T9 da solo circa $MIN_T9 min)"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "attacco_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); posizioni con regole 6427b90+D72-D82, rimonta, 138 iterazioni"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi"
} | tee "$OUT/riepilogo.txt"

echo "1. riproduzione del T9 di Astra ($(date +%H:%M))"
python scripts/rust/attacco.py riproduci-t9 --dati "$DATI" --ckpt "$CKPT" --processi "$W" --out "$OUT/riproduzione_t9" \
  > "$OUT/riproduzione.txt" 2>&1 || true
tail -3 "$OUT/riproduzione.txt"
grep -q "^IDENTICO" "$OUT/riproduzione.txt" || echo "ATTENZIONE: la riproduzione NON e' identica ai dati di Astra (vedi $OUT/riproduzione.txt); proseguo."

echo "2. T9 con riferimento campione ($(date +%H:%M))"
python scripts/rust/attacco.py confronta --pagina "$T9" --k 10 --ckpt "$CKPT" --processi "$W" \
  --riferimento campione --out "$OUT/t9_campione" 2>&1 | tail -6

echo "3. posizioni ($(date +%H:%M))"
PAGINE=$(ls docs/bot/partite/coach/*.json)
AUTO=""
for mu in ES EK; do
  for s in 0 1 2 3 4 5 6 7 8 9; do
    posto=A; [ $(( s % 2 )) -eq 1 ] && posto=B
    AUTO="$AUTO $mu:$s:$posto"
  done
done
# shellcheck disable=SC2086
python scripts/rust/attacco.py posizioni --pagina $PAGINE --autonoma $AUTO --ckpt "$CKPT" \
  --regole 6427b90+D72-D82 --valutazione rimonta --iterazioni 138 --out "$OUT/posizioni.json" 2>&1 | tail -30
python -c "import json,sys; p=json.load(open('$OUT/posizioni.json')); print(len(p),'posizioni,',sum(x['punto_libero'] for x in p),'con punto libero')"

echo "4. serie ($(date +%H:%M))"
python scripts/rust/attacco.py serie --posizioni "$OUT/posizioni.json" --max 12 --ckpt "$CKPT" --processi "$W" \
  --out "$OUT/serie" 2>&1 | tail -15
{ echo; echo "== riproduzione T9"; tail -3 "$OUT/riproduzione.txt"; echo "== T9 con riferimento campione"; cat "$OUT/t9_campione/esito.txt";
  echo "== serie"; cat "$OUT/serie/riepilogo.txt"; } >> "$OUT/riepilogo.txt" 2>/dev/null || true

echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT (riepilogo.txt, riproduzione.txt, t9_campione/, posizioni.json, serie/)."
echo "   Versiona:  git add docs/bot/esperimenti/attacco_$STAMP && git commit -m 'Attacco: riproduzione T9, riferimento campione, serie' && git push"
