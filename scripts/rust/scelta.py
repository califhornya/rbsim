"""Scelta finale (riftbound/rs/scelta.py): la mossa piu' visitata e' migliore di quella con la Q piu' alta?

  scelta.py posizioni --out DIR [--ckpt F | --casuali] [--matchup EK ES ...] [--partite 6] [--per-partita 8]
        [--mondi 32] [--iterazioni 138] [--processi 4] [--regole 6427b90+D72-D83]
  scelta.py arena --out DIR [--ckpt F] [--matchup ...] [--coppie 100] [--iterazioni 138] [--processi 4]

`posizioni`: sulle stesse posizioni di sviluppo dei seguiti, dove le due scelte differiscono si giocano entrambe sugli
stessi mondi; uscita `riepilogo.txt` (ultima riga `totale:`), `riepilogo.json`, `esito.json` (regola di stop).
`arena`: candidato con scelta per visite contro il campione, coppie a posti scambiati; uscita `arena.txt`, `arena.json`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, scelta as C  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("posizioni", "arena"):
        p = sub.add_parser(nome)
        p.add_argument("--out", required=True)
        p.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
        p.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
        p.add_argument("--iterazioni", type=int, default=C.ITERAZIONI)
        p.add_argument("--processi", type=int, default=1)
        p.add_argument("--regole", default=C.REGOLE)
        if nome == "posizioni":
            p.add_argument("--casuali", action="store_true", help="prior a pesi casuali (prove senza checkpoint)")
            p.add_argument("--partite", type=int, default=C.N_PARTITE)
            p.add_argument("--per-partita", type=int, default=C.PER_PARTITA)
            p.add_argument("--mondi", type=int, default=C.MONDI)
        else:
            p.add_argument("--coppie", type=int, default=C.COPPIE)
    a = ap.parse_args()
    ckpt = str((ROOT / a.ckpt) if not Path(a.ckpt).is_absolute() else Path(a.ckpt))
    if a.cmd == "posizioni":
        righe = C.posizioni(a.matchup, a.partite, a.per_partita, a.mondi, Path(a.out), None if a.casuali else ckpt,
                            a.casuali, a.processi, a.regole, a.iterazioni)
    else:
        righe = C.arena(a.matchup, a.coppie, Path(a.out), ckpt, a.processi, a.regole, a.iterazioni)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
