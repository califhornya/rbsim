"""Seguiti (riftbound/rs/seguiti.py): il valore della rete nuova aiuta a scegliere una linea migliore?

  seguiti.py --out DIR --valore RETE.pt [--ckpt F | --casuali] [--matchup EK ES ...] [--partite 6] [--per-partita 8]
        [--mondi 32] [--peso 0.2] [--iterazioni 138] [--processi 4] [--regole 6427b90+D72-D83]

Partite autonome del campione; ogni decisione di turno e' rifatta con (d) = prior del campione + valore della rete nuova
al `--peso`; dove (d) sceglie una mossa diversa, le due mosse sono giocate fino alla fine sugli stessi mondi.
Uscita: `riepilogo.txt` (ultima riga `totale:`), `riepilogo.json`, una cartella per decisione.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, seguiti as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
    ap.add_argument("--valore", required=True, help="checkpoint della rete di cui si usa il valore")
    ap.add_argument("--casuali", action="store_true", help="prior a pesi casuali (prove senza checkpoint)")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
    ap.add_argument("--partite", type=int, default=6)
    ap.add_argument("--per-partita", type=int, default=8)
    ap.add_argument("--mondi", type=int, default=32)
    ap.add_argument("--peso", type=float, default=S.PESO)
    ap.add_argument("--iterazioni", type=int, default=S.ITERAZIONI)
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--regole", default=S.REGOLE)
    a = ap.parse_args()
    ckpt = None if a.casuali else str((ROOT / a.ckpt) if not Path(a.ckpt).is_absolute() else Path(a.ckpt))
    valore = Path(a.valore)
    righe = S.seguiti(a.matchup, a.partite, a.per_partita, a.mondi, Path(a.out), ckpt, str(valore.resolve()), a.peso,
                      a.casuali, a.processi, a.regole, a.iterazioni)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
