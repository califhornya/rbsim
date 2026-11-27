"""Pilota «studente» (riftbound/rs/studente.py, docs/bot/STUDENTE.md): un modello veloce impara da «Pensa» quale delle <=3
mosse candidate del campione scegliere, su entrambi i posti; raccolta, addestramento e cancello, congelamento, verifica.

  studente.py --out DIR [--dati DIR] [--ckpt F] [--matchup EK ES ...] [--processi 4] [--per-posto 4]
        [--semi-raccolta 60] [--semi-verifica 40] [--semi-maestro 3] [--mondi-raccolta 8] [--mondi-verifica 64]
        [--mondi-maestro 32] [--tetto-raccolta-min 55] [--tetto-verifica-min 50] [--iterazioni 138]
        [--regole 6427b90+D72-D83] [--n-boot 40000] [--forza-cancello]

`--out`: risultati leggeri (riepilogo.txt con ultima riga `totale:`, riepilogo.json, esito.json, studente.pt,
congelato.json). `--dati`: dati pesanti (input della rete), default `runs/studente/<nome di --out>`.
`--forza-cancello`: SOLO per le prove, la verifica gira anche se lo studente non impara.
Le regole statistiche (semi, divisione, cancello, congelamento, soglia, tetti) sono della specifica e non si cambiano qui.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, studente as T  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dati", default=None)
    ap.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI))
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--per-posto", type=int, default=T.PER_POSTO)
    ap.add_argument("--semi-raccolta", type=int, default=T.SEMI_RACCOLTA)
    ap.add_argument("--semi-verifica", type=int, default=T.SEMI_VERIFICA)
    ap.add_argument("--semi-maestro", type=int, default=T.SEMI_MAESTRO)
    ap.add_argument("--mondi-raccolta", type=int, default=T.N_RACCOLTA)
    ap.add_argument("--mondi-verifica", type=int, default=T.N_VERIFICA)
    ap.add_argument("--mondi-maestro", type=int, default=T.N_MAESTRO)
    ap.add_argument("--tetto-raccolta-min", type=float, default=T.TETTO_RACCOLTA_MIN)
    ap.add_argument("--tetto-verifica-min", type=float, default=T.TETTO_VERIFICA_MIN)
    ap.add_argument("--iterazioni", type=int, default=T.ITERAZIONI)
    ap.add_argument("--regole", default=T.REGOLE)
    ap.add_argument("--n-boot", type=int, default=T.N_BOOT)
    ap.add_argument("--epoche", type=int, default=300)
    ap.add_argument("--forza-cancello", action="store_true", help="solo per le prove")
    a = ap.parse_args()
    ckpt = ROOT / a.ckpt if not Path(a.ckpt).is_absolute() else Path(a.ckpt)
    out = Path(a.out)
    dati = Path(a.dati) if a.dati else ROOT / "runs" / "studente" / out.name
    righe = T.esegui(a.matchup, out, dati, str(ckpt), a.processi, a.per_posto, a.semi_raccolta, a.semi_verifica,
                     a.semi_maestro, a.mondi_raccolta, a.mondi_verifica, a.mondi_maestro, a.tetto_raccolta_min,
                     a.tetto_verifica_min, a.iterazioni, a.regole, a.n_boot, a.forza_cancello, a.epoche)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
