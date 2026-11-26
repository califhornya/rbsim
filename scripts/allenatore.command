#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: apre nel browser la pagina per
# giocare a mano (scripts/coach.py), http://127.0.0.1:8765. Avversario di
# default: il campione, il bot a mano guidato dai prior di
# runs/sett/ekris_s12/ckpt_040000.pt (allenato su Evelynn, Kha'Zix, Rengar, Ivern
# e Sett). Se qui non c'è, lo prende dall'altro checkout (../rbsim/runs/...);
# senza nessuno dei due restano gli altri avversari.
# Motore: Rust con le regole 6427b90+D72-D82 (D72-D82 corretti) fra i cinque mazzi;
# l'estensione si compila qui a ogni avvio (serve Rust: https://rustup.rs; la prima
# volta qualche minuto). Senza Rust, o fuori dai cinque mazzi, gioca su Python.
# Opzioni, per esempio:
#   scripts/allenatore.command --iterazioni 80          # campione più forte (su Rust)
#   scripts/allenatore.command --motore python          # il motore Python (regole 6427b90)
#   scripts/allenatore.command --net runs/precons-2/net.pt   # i consigli della vecchia rete (su Python)
# Per fermarla: chiudi questa finestra (o Ctrl+C).
cd "$(dirname "$0")/.." || exit 1
CKPT=runs/sett/ekris_s12/ckpt_040000.pt
extra=()
case " $* " in
  *" --campione"*) ;;
  *) if [ ! -f "$CKPT" ] && [ -f "../rbsim/$CKPT" ]; then extra=(--campione "../rbsim/$CKPT"); fi ;;
esac
uv sync --extra rl >/dev/null || exit 1
source .venv/bin/activate
if command -v rustc >/dev/null; then
  echo "== compilo il motore Rust"
  uv pip install maturin >/dev/null
  (cd rust/rbsim-py && maturin develop --release 2>&1 | tail -1)
else
  echo "manca Rust (https://rustup.rs): la pagina gioca su Python, regole 6427b90"
fi
python scripts/coach.py "${extra[@]}" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
