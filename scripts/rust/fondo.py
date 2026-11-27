"""Fondo, misura di «Pensa» (riftbound/rs/fondo.py): a ogni decisione si giocano fino in fondo fino a 3 mosse candidate
dall'albero del campione sugli stessi mondi e si sceglie la migliore; dove cambia mossa, la verifica su mondi diversi.

  fondo.py --out DIR [--ckpt F | --casuali] [--matchup EK ES ...] [--partite 6] [--per-partita 8]
        [--mondi-scelta 32] [--mondi-verifica 100] [--iterazioni 138] [--processi 4] [--regole 6427b90+D72-D83]
        [--n-boot 4000] [--processi-mac 9] [--coppie-arena 100]

Uscita: `riepilogo.txt` (ultima riga `totale:`), `riepilogo.json`, `esito.json` (regola di stop). Rilanciato nella stessa
cartella riprende dal lavoro gia' fatto.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, fondo as F  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
    ap.add_argument("--casuali", action="store_true", help="prior a pesi casuali (prove senza checkpoint)")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
    ap.add_argument("--partite", type=int, default=F.N_PARTITE)
    ap.add_argument("--per-partita", type=int, default=F.PER_PARTITA)
    ap.add_argument("--mondi-scelta", type=int, default=F.N_SCELTA)
    ap.add_argument("--mondi-verifica", type=int, default=F.N_VERIFICA)
    ap.add_argument("--iterazioni", type=int, default=F.ITERAZIONI)
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--regole", default=F.REGOLE)
    ap.add_argument("--n-boot", type=int, default=F.N_BOOT)
    ap.add_argument("--processi-mac", type=int, default=F.PROCESSI_MAC)
    ap.add_argument("--coppie-arena", type=int, default=F.COPPIE_ARENA)
    a = ap.parse_args()
    ckpt = str((ROOT / a.ckpt) if not Path(a.ckpt).is_absolute() else Path(a.ckpt))
    righe = F.posizioni(a.matchup, a.partite, a.per_partita, a.mondi_scelta, a.mondi_verifica, Path(a.out),
                        None if a.casuali else ckpt, a.casuali, a.processi, a.regole, a.iterazioni, a.n_boot,
                        a.processi_mac, a.coppie_arena)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
