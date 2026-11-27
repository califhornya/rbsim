"""Muovo prima contro schiero in base (riftbound/rs/muovi.py).

  muovi.py --out DIR [--ckpt F | --casuali] [--mondi 100] [--processi 4] [--replay F ...] [--autonome MU:SEME ...]
        [--iterazioni 138] [--autonome-nuove N] [--quota | --no-quota] [--matchup EK ES ...]

Senza `--replay` e `--autonome`: i replay salvati della pagina (docs/bot/partite/coach/*.json) tranne quelli con il seme
della partita della scoperta (20261126_155859, 20261126_013325). Su ogni posizione (un'unita' puo' andare su un campo
libero e un'altra unita' puo' essere schierata) si giocano riferimento, "muovo prima" e "schiero in base" sugli stessi
mondi; uscita `riepilogo.txt` (ultima riga `totale:`), `riepilogo.json`, una cartella per posizione.
`--autonome EK:3 ES:4` + `--casuali`: partite autonome a pesi casuali (prove senza checkpoint e replay).
`--autonome-nuove N`: N partite NUOVE del campione per matchup (i dieci di arena_rs.COPERTI, o `--matchup`), semi da
80.000.000, regole D72-D83; vale il modo quota. `--quota`: quattro linee (campione = la sua mossa originale forzata, "muovo
prima", "schiero in base", "con quota" = la ricerca rifatta con 8 visite iniziali ai figli "base→bf" della radice),
Q - campione su tutte le posizioni e regola di stop (`esito.json`, riga `regola di stop:`). Con i replay della pagina il
modo quota c'e' solo con `--quota`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import arena_rs, decisione_rs as D, muovi as M  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="runs/sett/ekris_s12/ckpt_040000.pt")
    ap.add_argument("--casuali", action="store_true", help="prior a pesi casuali (prove senza checkpoint)")
    ap.add_argument("--mondi", type=int, default=M.N_MONDI)
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--iterazioni", type=int, default=M.ITERAZIONI, help="della continuazione (e delle partite autonome)")
    ap.add_argument("--replay", nargs="+", help="replay della pagina al posto dell'insieme di default")
    ap.add_argument("--autonome", nargs="+", metavar="MU:SEME", help="partite autonome (posto A) al posto dei replay")
    ap.add_argument("--autonome-nuove", type=int, metavar="N", help="N partite nuove del campione per matchup")
    ap.add_argument("--quota", action=argparse.BooleanOptionalAction, default=None,
                    help="modo quota (di default acceso con --autonome-nuove)")
    ap.add_argument("--matchup", nargs="+", default=list(arena_rs.COPERTI), choices=list(arena_rs.COPERTI),
                    help="solo con --autonome-nuove")
    a = ap.parse_args()
    quota = a.quota if a.quota is not None else bool(a.autonome_nuove)
    if a.autonome_nuove is not None and a.autonome_nuove < 1:
        ap.error("--autonome-nuove vuole almeno 1 partita per matchup")
    ckpt = str((ROOT / a.ckpt) if not Path(a.ckpt).is_absolute() else Path(a.ckpt))
    base_seme = None
    if a.autonome_nuove:
        if a.autonome or a.replay:
            ap.error("--autonome-nuove non va con --autonome / --replay")
        base_seme = M.BASE_SEME_NUOVE
        partite = M.partite_autonome(a.matchup, a.autonome_nuove, None if a.casuali else ckpt, a.casuali, a.iterazioni,
                                     base_seme)
    elif a.autonome:
        partite = []
        for x in a.autonome:
            mu, seme = x.split(":")
            partite.append(D.autonoma(mu, int(seme), None if a.casuali else ckpt, a.casuali, a.iterazioni, "A",
                                      valutazione=D._valutazione_registrata(M.VALUTAZIONE), entrambi=True))
    else:
        # PR 76 (Codex): un replay della pagina si rigioca solo con la rete che ha giocato quella partita (le risposte
        # registrate di Matteo seguono le sue mosse); con pesi casuali non si riproduce, e il riepilogo direbbe
        # «pesi casuali» per un esperimento diverso.
        if a.casuali:
            ap.error("--casuali vale solo con --autonome e --autonome-nuove: i replay della pagina vogliono il checkpoint del campione")
        files = [Path(f) for f in a.replay] if a.replay else M.replay_default()
        partite = M.partite_replay(files, ckpt)
    righe = M.muovi(partite, a.mondi, Path(a.out), None if a.casuali else ckpt, a.casuali, a.processi, a.iterazioni,
                    quota=(M.QUOTA_ETICHETTE, M.QUOTA_VISITE) if quota else None, base_seme=base_seme)
    print("\n".join(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
