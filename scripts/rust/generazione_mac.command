#!/bin/bash
# Prima generazione sul Mac (Astra, 26/11): raccolta pilota (se non c'e' gia'), allenamento da ckpt_040000, una partita
# della rete nuova contro il campione, arena di sviluppo (b) rimonta e (c) 80% rimonta + 20% valore.
#   cd ~/projects/rbsim2026/rbsim-rust && git checkout rust && git pull && bash scripts/rust/generazione_mac.command
# Opzioni (variabili d'ambiente): COPPIE=100 (per matchup nell'arena), PARTITE=200 (per matchup nella raccolta),
#   CKPT=runs/sett/ekris_s12/ckpt_040000.pt, PROCESSI=<n> (default: core - 1), NOME=pilota.
# Rilanciato riprende: la raccolta e l'arena saltano le partite gia' fatte (l'allenamento si rifa').
# Uscita: docs/bot/esperimenti/generazione_<data_ora>/ (misure, partita, arene, durate; NON i dati grezzi della raccolta,
# che restano in runs/raccolta/). Alla fine stampa il comando git da incollare.
# Prerequisiti: uv, Rust (https://rustup.rs). Con Rust l'estensione si compila e la ricerca gira su Rust: qui serve.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -z "${CKPT:-}" ]; then
  for c in runs/sett/ekris_s12/ckpt_040000.pt ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt; do
    [ -f "$c" ] && { CKPT="$c"; break; }
  done
fi
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
PARTITE="${PARTITE:-200}"
COPPIE="${COPPIE:-100}"
NOME="${NOME:-pilota}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
PROCESSI="${PROCESSI:-$((NCPU > 1 ? NCPU - 1 : 1))}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="docs/bot/esperimenti/generazione_$STAMP"
ALLENA="runs/allena/generazione_$STAMP"
RACC="runs/raccolta/$NOME"
[ -f "$CKPT" ] || { echo "Manca il checkpoint $CKPT"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: https://rustup.rs"; exit 1; }
mkdir -p "$OUT"
LOG="$OUT/log.txt"
t() { date +%s; }
passo() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
mkdir -p runs/generazione
# esegui <file di uscita completa> <filtro egrep> <comando...>: l'uscita completa va in runs/, a schermo e nel log solo
# le righe del filtro (ultime 30); se il comando fallisce, mostra la coda e si ferma.
esegui() {
  local f="runs/generazione/${STAMP}_$1.out" filtro="$2"; shift 2
  if ! "$@" > "$f" 2>&1; then echo "ERRORE in $*"; tail -20 "$f"; exit 1; fi
  { grep -E "$filtro" "$f" || true; } | tail -30 | tee -a "$LOG"
}

passo "== ambiente"
uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1) | tee -a "$LOG" || true
python -c "import riftbound_rs" || { echo "estensione Rust non caricata"; exit 1; }
git log --oneline -1 | tee -a "$LOG"
echo "processi: $PROCESSI; checkpoint: $CKPT; $PARTITE partite per matchup; $COPPIE coppie per matchup" | tee -a "$LOG"

T0=$(t)
passo "== 1. raccolta pilota ($PARTITE per matchup, 138 iterazioni)"
FATTE=0
[ -f "$RACC/indice.jsonl" ] && FATTE=$(wc -l < "$RACC/indice.jsonl")
if [ "$FATTE" -ge $((PARTITE * 10)) ]; then
  passo "gia' fatta ($FATTE partite in $RACC): salto"
else
  esegui raccolta "gia' fatte|partite|stima|secondi" python scripts/rust/raccolta.py --nome "$NOME" \
    --partite-per-matchup "$PARTITE" --processi "$PROCESSI" --ckpt "$CKPT"
fi
T1=$(t)
mkdir -p "$OUT/raccolta"
cp "$RACC/misura.txt" "$RACC/provenienza.json" "$OUT/raccolta/" 2>/dev/null || true

passo "== 2. allenamento da $CKPT"
esegui allena "dispositivo|decisioni|^epoca|^partenza|^totale" python scripts/rust/allena.py --raccolta "$RACC" \
  --nome "generazione_$STAMP" --init "$CKPT"
T2=$(t)
mkdir -p "$OUT/allenamento"
cp "$ALLENA/misure.txt" "$ALLENA/misure.json" "$ALLENA/provenienza.json" "$OUT/allenamento/"
RETE="$ALLENA/rete.pt"

passo "== 3. una partita: rete nuova contro il campione"
esegui partita "partita" python scripts/rust/generazione.py partita --rete "$RETE" --campione "$CKPT" --out "$OUT"
T3=$(t)

passo "== 4. arena di sviluppo ($COPPIE coppie per matchup, 10 matchup, posti scambiati)"
esegui arena "^\(|^   |^Arena|^durata" python scripts/rust/generazione.py arena --rete "$RETE" --campione "$CKPT" \
  --out "$OUT" --coppie "$COPPIE" --processi "$PROCESSI"
T4=$(t)

{
  echo "durata dei passi (s): raccolta $((T1 - T0)), allenamento $((T2 - T1)), partita $((T3 - T2)), arena $((T4 - T3)), totale $((T4 - T0))"
  echo "processi $PROCESSI su $NCPU core"
} | tee "$OUT/durata.txt" | tee -a "$LOG"

echo
echo "== fatto. Risultati in $OUT (arena.txt, partita.txt, allenamento/misure.txt, durata.txt)."
echo "Per portarli su GitHub (i dati grezzi in runs/ restano fuori):"
echo "  git add $OUT && git commit -m \"Prima generazione: allenamento pilota e arena di sviluppo ($STAMP)\" && git push"
read -r -p "Premi Invio per chiudere."
