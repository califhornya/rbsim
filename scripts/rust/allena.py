"""Allenamento pilota della rete sui dati della raccolta (riftbound/rs/allena.py).

  allena.py --raccolta runs/raccolta/pilota --nome pilota1 [--init runs/sett/ekris_s12/ckpt_040000.pt | --casuali]
            [--epoche 10] [--lr 1e-4] [--minibatch 512] [--peso-valore 1.0] [--dispositivo cuda|mps|cpu]
            [--out runs/allena]

Uscita: <out>/<nome>/ con rete.pt, misure.json, misure.txt (ultima riga `totale:`), provenienza.json.
Dispositivo: cuda se c'e', poi mps, poi cpu. `--casuali`: parte da pesi casuali (per provare senza checkpoint);
`--prova`: con sviluppo e verifica vuoti (mini raccolta) usa l'allenamento al loro posto.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import allena as A  # noqa: E402


def _abs(p: str) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raccolta", required=True, help="la cartella della raccolta (con indice.jsonl)")
    ap.add_argument("--nome", default="pilota")
    ap.add_argument("--out", default="runs/allena")
    ap.add_argument("--init", default=A.CKPT_DEFAULT, help="il checkpoint di partenza (stessa architettura)")
    ap.add_argument("--casuali", action="store_true", help="parti da pesi casuali (per provare senza checkpoint)")
    ap.add_argument("--epoche", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--minibatch", type=int, default=512)
    ap.add_argument("--peso-valore", type=float, default=1.0)
    ap.add_argument("--seme", type=int, default=0)
    ap.add_argument("--dispositivo", default=None, help="cuda, mps o cpu (default: il primo disponibile)")
    ap.add_argument("--prova", action="store_true")
    a = ap.parse_args()
    init = None
    if not a.casuali:
        init = _abs(a.init)
        if not init.is_file():
            sys.exit(f"manca il checkpoint {init} (--init, oppure --casuali per provare)")
    A.allena(_abs(a.raccolta), _abs(a.out) / a.nome, init, a.casuali, a.epoche, a.lr, a.minibatch, a.peso_valore,
             a.seme, a.dispositivo, a.prova, lambda t: print(t, flush=True))


if __name__ == "__main__":
    main()
