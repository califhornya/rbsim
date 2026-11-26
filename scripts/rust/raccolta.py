"""Raccolta pilota del campione contro se stesso (riftbound/rs/raccolta.py), per riallenare la rete con la ricerca.

  raccolta.py --nome pilota [--partite-per-matchup 200] [--matchup EK ER ...] [--processi 4] [--iterazioni 138]
              [--ckpt F | --casuali] [--regole 6427b90+D72-D82] [--esplorazione 0.3 0.25 4] [--out runs/raccolta]

Uscita: <out>/<nome>/ con partite/<matchup>/<seme>.pkl.gz, indice.jsonl, provenienza.json, misura.txt (scritta dopo le
prime 200 partite e alla fine). Rilanciato, salta le partite gia' fatte.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import raccolta as R  # noqa: E402
from riftbound.rs.arena_rs import COPERTI  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", default="pilota")
    ap.add_argument("--out", default="runs/raccolta")
    ap.add_argument("--partite-per-matchup", type=int, default=200)
    ap.add_argument("--matchup", nargs="+", default=list(COPERTI), choices=COPERTI)
    ap.add_argument("--processi", type=int, default=4)
    ap.add_argument("--iterazioni", type=int, default=R.ITERAZIONI)
    ap.add_argument("--ckpt", default=R.CKPT_DEFAULT)
    ap.add_argument("--casuali", action="store_true", help="rete a pesi casuali (per provare senza checkpoint)")
    ap.add_argument("--regole", default=R.REGOLE_DEFAULT)
    ap.add_argument("--esplorazione", nargs=3, type=float, default=list(R.ESPLORAZIONE),
                    metavar=("ALFA", "EPS", "MOSSE"))
    ap.add_argument("--misura-dopo", type=int, default=200)
    a = ap.parse_args()
    ckpt = None
    if not a.casuali:
        ckpt = Path(a.ckpt)
        ckpt = ckpt if ckpt.is_absolute() else ROOT / ckpt
        if not ckpt.is_file():
            sys.exit(f"manca il checkpoint {ckpt} (--ckpt, oppure --casuali per provare)")
    alfa, eps, mosse = a.esplorazione
    R.esegui(ROOT / a.out / a.nome if not Path(a.out).is_absolute() else Path(a.out) / a.nome, a.matchup,
             a.partite_per_matchup, a.processi, ckpt, a.regole, a.iterazioni, (alfa, eps, int(mosse)), a.misura_dopo,
             lambda t: print(t, flush=True))


if __name__ == "__main__":
    main()
