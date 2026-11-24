#!/bin/bash
# Prova di forza del budget Rust (metodo di Astra, 24/11): il campione su Rust a 0,030 s CPU per
# ricerca contro lo stesso campione su Python a 0,400 s, Evelynn-Kha'Zix, partite a passo comune
# (scripts/rust/arena_mista.py). Regole fissate prima: 800 coppie, semi 70000-70799, posti
# scambiati, promosso se il limite inferiore dell'IC 95% supera 0,47; una partita divergente
# sospende l'esito. Doppio clic dal Finder o:
#   bash scripts/rust/arena_mista.command [checkpoint.pt]
#   (default runs/sett/ekris_s12/ckpt_040000.pt; anche da un altro checkout:
#    bash scripts/rust/arena_mista.command ../rbsim/runs/sett/ekris_s12/ckpt_040000.pt)
# WORKERS=6 bash scripts/rust/arena_mista.command: meno processi, Mac più fresco, più lento.
# Si può fermare (ctrl-C) e rilanciare: riprende dalle partite già giocate.
# Risultati: runs/budget/ARENA_MISTA.txt (+ .jsonl, provenienza.jsonl). Circa 2-3 ore.
set -euo pipefail
CKPT="${1:-}"
if [ -n "$CKPT" ] && [ -f "$CKPT" ]; then CKPT="$(cd "$(dirname "$CKPT")" && pwd)/$(basename "$CKPT")"; fi
cd "$(dirname "$0")/../.."
CKPT="${CKPT:-runs/sett/ekris_s12/ckpt_040000.pt}"
[ -f "$CKPT" ] || { echo "Manca il checkpoint $CKPT"; exit 1; }
command -v rustc >/dev/null || { echo "manca Rust: installalo con  curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
workers=${WORKERS:-$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null)}
case "$workers" in ''|*[!0-9]*) workers=4 ;; esac

uv sync --extra rl >/dev/null
source .venv/bin/activate
uv pip install maturin >/dev/null
git log --oneline -1
(cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1)
python -m pytest -q tests/rust 2>&1 | tail -1
caffeinate -i python scripts/rust/arena_mista.py --ckpt "$CKPT" --coppie 800 --seed0 70000 \
  --budget-rust 0.030 --budget-python 0.400 --workers "$workers" --out runs/budget/ARENA_MISTA.txt \
  --spiegata 70113:A
read -r -p "Fatto. Premi Invio per chiudere."
