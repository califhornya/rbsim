#!/bin/bash
# Doppio clic nel Finder (Mac), o dal Terminale: apre nel browser la pagina per
# giocare a mano (scripts/coach.py), http://127.0.0.1:8765. Avversario di
# default: il campione, il bot a mano guidato dai prior di
# runs/sett/ekris_s12/ckpt_040000.pt, 0,4 s per mossa (allenato su Evelynn,
# Kha'Zix, Rengar, Ivern e Sett). Se qui non c'è, lo prende dall'altro checkout
# (../rbsim/runs/...); senza nessuno dei due restano gli altri avversari.
# Opzioni, per esempio:
#   scripts/allenatore.command --campione altro/ckpt.pt --budget 0.8
#   scripts/allenatore.command --net runs/precons-2/net.pt   # i consigli della vecchia rete
# Per fermarla: chiudi questa finestra (o Ctrl+C).
cd "$(dirname "$0")/.." || exit 1
CKPT=runs/sett/ekris_s12/ckpt_040000.pt
extra=()
case " $* " in
  *" --campione"*) ;;
  *) if [ ! -f "$CKPT" ] && [ -f "../rbsim/$CKPT" ]; then extra=(--campione "../rbsim/$CKPT"); fi ;;
esac
uv run --extra rl python scripts/coach.py "${extra[@]}" "$@"
read -r -p "Fatto. Premi Invio per chiudere."
