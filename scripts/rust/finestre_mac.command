#!/bin/bash
# Finestre di reazione/showdown nelle simulazioni: un'arena, candidato = campione "rimonta" CON le finestre contro
# il campione "rimonta" SENZA (stessa rete, 138 iterazioni per lato, win probe per entrambi).
# Da lanciare con:  bash scripts/rust/finestre_mac.command [checkpoint.pt]
# Regole 6427b90+D72-D81, win probe come la pagina, niente quota; le finestre solo al posto del candidato (A o B).
# Semi nuovi (da 110000: EK 110000-110799, ES 116000-116799), 800 coppie per matchup, posti scambiati sullo stesso seme,
# chi comincia bilanciato. Blocco ES+EK a pesi uguali: passa se punteggio >= 0,52 e limite inferiore > 0,50
# (IC 95% sulle medie di coppia); l'arena stampa per matchup e per blocco, e PASSA / NON PASSA.
# Prima della corsa lunga: collaudo (una coppia a posti scambiati: le finestre seguono il candidato in A e in B).
# Uscite: docs/bot/finestre/arena_<data>/ (arena_finestre.txt, .jsonl, provenienza.jsonl, riepilogo.txt): da versionare.
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
OUT="docs/bot/finestre/arena_$STAMP"
mkdir -p "$OUT"
W=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
W=$(( W > 1 ? W - 1 : 1 ))
# 3.200 partite. Senza finestre una partita a 138 iterazioni costa circa 2,3 s di un core (misura del 25/11); con le
# finestre le ricerche del candidato costano x1,4-2 e il candidato e' meta' delle ricerche: partita x1,2-1,5
# (nel cloud, con rete a pesi casuali, x1,7 sulla partita intera).
MIN_A=$(awk -v g=3200 -v w="$W" 'BEGIN { printf "%.0f", g * 2.3 * 1.2 / w / 60 }')
MIN_B=$(awk -v g=3200 -v w="$W" 'BEGIN { printf "%.0f", g * 2.3 * 1.7 / w / 60 }')
echo "== finestre: candidato rimonta+finestre contro rimonta; checkpoint $CKPT; $W processi"
echo "   durata prevista: ambiente e compilazione 1-3 min, arena da circa $MIN_A a circa $MIN_B min (3.200 partite)"

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) > "$OUT/compilazione.txt"
{
  echo "finestre_mac $(date '+%d/%m/%Y %H:%M'); $(git log --oneline -1); regole 6427b90+D72-D81"
  echo "checkpoint $CKPT (sha256 $(shasum -a 256 "$CKPT" 2>/dev/null | cut -c1-16)); $W processi; durata prevista $MIN_A-$MIN_B min"
} | tee "$OUT/riepilogo.txt"

echo "collaudo finestre ($(date +%H:%M))"
python scripts/diag/collaudo_finestre.py --ckpt "$CKPT" --mu ES --regole 6427b90+D72-D81 2>&1 | tee "$OUT/collaudo.txt" | tail -4
grep -q "SUPERATO" "$OUT/collaudo.txt" || { echo "collaudo fallito: l'arena non parte"; exit 1; }
echo "arena finestre ($(date +%H:%M))"
python scripts/diag/arena_mazzi.py --motore rust --regole 6427b90+D72-D81 \
  --ckpt "$CKPT" --ckpt-avversario "$CKPT" \
  --vecchi --blocchi ES,EK --coppie EK=800 ES=800 --seed0 110000 --workers "$W" \
  --esito-positivo PASSA --esito-negativo "NON PASSA" \
  --iterazioni-candidato 138 --iterazioni-avversario 138 --win-probe-candidato --win-probe-avversario \
  --valutazione-c rimonta --valutazione-a rimonta --finestre-candidato \
  --out "$OUT/arena_finestre.txt" > "$OUT/arena_finestre_schermo.txt" 2>&1 || { tail -5 "$OUT/arena_finestre_schermo.txt"; }
{ echo; echo "== candidato rimonta+finestre contro rimonta senza finestre"; } >> "$OUT/riepilogo.txt"
tail -25 "$OUT/arena_finestre.txt" >> "$OUT/riepilogo.txt" 2>/dev/null || tail -25 "$OUT/arena_finestre_schermo.txt" >> "$OUT/riepilogo.txt"

echo
echo "== fatto ($(date +%H:%M)). Risultati in $OUT (punteggio per matchup e per blocco con l'IC al 95%)."
echo "   Versiona:  git add docs/bot/finestre && git commit -m 'Arena delle finestre' && git push"
