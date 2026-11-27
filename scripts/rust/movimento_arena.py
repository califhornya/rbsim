"""Arena del movimento dalla base (riftbound/rs/muovi.py, `arena_quota`): candidato = campione con la quota alla radice
di ogni ricerca di turno (8 visite iniziali a ciascun figlio "base→bf"), avversario = campione.

  movimento_arena.py --out DIR [--ckpt F] [--matchup EK ES ...] [--coppie 100] [--iterazioni 138] [--processi 4]
        [--regole 6427b90+D72-D83]

Coppie a posti scambiati, semi da 90.000.000 (aperture nuove). Uscita `arena.txt`, `arena.json`; rilanciato nella stessa
cartella riprende dalle partite gia' fatte (manifest `arena_righe.jsonl.provenienza.json`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, muovi as M, seguiti as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
    ap.add_argument("--coppie", type=int, default=100)
    ap.add_argument("--iterazioni", type=int, default=M.ITERAZIONI)
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--regole", default=S.REGOLE)
    a = ap.parse_args()
    ckpt = str((ROOT / a.ckpt) if not Path(a.ckpt).is_absolute() else Path(a.ckpt))
    righe = M.arena_quota(a.matchup, a.coppie, Path(a.out), ckpt, a.processi, a.regole, a.iterazioni)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
