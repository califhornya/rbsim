"""Primo responso (riftbound/rs/responso.py): quando la ricerca suggerisce una mossa diversa, si vince di piu'?

  responso.py --out DIR [--ckpt F | --casuali] [--matchup EK ES ...] [--semi 300 301] [--per-partita 4]
        [--mondi 32] [--iterazioni 138 512] [--processi 4] [--regole 6427b90+D72-D83] [--valutazione rimonta]

Partite autonome del campione (10 matchup coperti, semi 300 e 301), al piu' `--per-partita` decisioni di turno a testa,
rifatte a due budget; dove prior, visite e Q indicano mosse diverse, ogni mossa e' giocata fino alla fine sugli stessi
mondi `ignote`. Uscita: una cartella per decisione, `riepilogo.txt` (ultima riga `totale:`) e `riepilogo.json`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, responso as R  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--casuali", action="store_true", help="rete a pesi casuali (prove senza checkpoint)")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
    ap.add_argument("--semi", nargs="+", type=int, default=list(R.SEMI))
    ap.add_argument("--per-partita", type=int, default=4)
    ap.add_argument("--mondi", type=int, default=32)
    ap.add_argument("--iterazioni", nargs=2, type=int, default=list(R.ITERAZIONI), metavar=("BASSE", "ALTE"))
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--regole", default=R.REGOLE)
    ap.add_argument("--valutazione", default=R.VALUTAZIONE)
    a = ap.parse_args()
    righe = R.responso(a.matchup, a.semi, a.per_partita, tuple(a.iterazioni), a.mondi, Path(a.out), a.ckpt, a.casuali,
                       a.processi, a.regole, a.valutazione)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
