"""Pensare di piu' (riftbound/rs/pensa.py): il campione a 1.000 iterazioni batte il campione a 138?

  pensa.py --out DIR [--ckpt F] [--matchup EK ES ...] [--coppie 100] [--iter-pensa 1000] [--iter-base 138]
           [--processi 4] [--regole 6427b90+D72-D83]

Uscita: `arena.txt` (totale con IC 95%, per matchup, latenza dei due lati per decisione e per turno, criteri),
`arena.json`, `arena_righe.jsonl` (ripresa se rilanciato con le stesse impostazioni).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, pensa as P  # noqa: E402
from riftbound.rs.seguiti import REGOLE  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
    ap.add_argument("--coppie", type=int, default=P.COPPIE)
    ap.add_argument("--iter-pensa", type=int, default=P.ITER_PENSA)
    ap.add_argument("--iter-base", type=int, default=P.ITER_BASE)
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--regole", default=REGOLE)
    a = ap.parse_args()
    ckpt = str((ROOT / a.ckpt) if not Path(a.ckpt).is_absolute() else Path(a.ckpt))
    righe = P.arena(a.matchup, a.coppie, Path(a.out), ckpt, a.processi, a.regole, a.iter_pensa, a.iter_base)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
