"""Prima generazione, passi 3 e 4 (riftbound/rs/generazione.py); i passi 1 e 2 sono raccolta.py e allena.py.

  generazione.py partita --rete runs/allena/X/rete.pt --out docs/bot/esperimenti/generazione_DATA
  generazione.py arena   --rete runs/allena/X/rete.pt --out docs/bot/esperimenti/generazione_DATA [--coppie 100]
                         [--matchup EK ER ...] [--processi N]

`partita`: una partita della rete nuova (rimonta, 138 iterazioni, win_probe) contro il campione: partita.json e
partita.txt (registro leggibile). `arena`: l'arena di sviluppo, (b) rete nuova + rimonta e (c) 80% rimonta + 20% valore,
contro il campione, posti scambiati: arena.json, arena.txt, arena_righe.jsonl (si riprende).
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import generazione as G  # noqa: E402
from riftbound.rs import raccolta as R  # noqa: E402
from riftbound.rs.arena_rs import COPERTI  # noqa: E402


def _abs(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("passo", choices=("partita", "arena"))
    ap.add_argument("--rete", required=True)
    ap.add_argument("--campione", default=R.CKPT_DEFAULT)
    ap.add_argument("--casuali-campione", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--out", required=True)
    ap.add_argument("--regole", default=R.REGOLE_DEFAULT)
    ap.add_argument("--iterazioni", type=int, default=G.ITERAZIONI)
    ap.add_argument("--coppie", type=int, default=100)
    ap.add_argument("--matchup", nargs="+", default=list(COPERTI), choices=COPERTI)
    ap.add_argument("--processi", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--varianti", nargs="+", default=["b", "c"], choices=("b", "c"))
    ap.add_argument("--seme", type=int, default=G.BASE_SEME_SVILUPPO + 500_000, help="seme della partita (passo partita)")
    ap.add_argument("--mu", default="EK", choices=COPERTI, help="matchup della partita (passo partita)")
    ap.add_argument("--peso-valore", type=float, default=0.0, help="peso del valore della rete nella partita (default 0: come (b))")
    a = ap.parse_args()
    rete, campione, out = str(_abs(a.rete)), str(_abs(a.campione)), _abs(a.out)
    for p in (rete, campione):
        if not Path(p).is_file():
            sys.exit(f"manca il file {p}")
    out.mkdir(parents=True, exist_ok=True)
    if a.passo == "partita":
        r = G.partita_leggibile(rete, campione, a.regole, a.seme, a.mu, "A", a.iterazioni, a.peso_valore)
        (out / "partita.json").write_text(json.dumps({k: v for k, v in r.items() if k != "righe"}, indent=1))
        (out / "partita.txt").write_text(
            f"Rete nuova (posto A, segnata con *) contro il campione, {a.mu} seme {a.seme}, {a.iterazioni} iterazioni, "
            f"rimonta, win_probe, regole {a.regole}\nvince {r['vincitore']} in {r['turni']} turni "
            f"(punteggio della rete nuova {r['esito']}); {r['secondi']} s\n\n" + "\n".join(r["righe"]) + "\n")
        print(f"partita: vince {r['vincitore']} in {r['turni']} turni, {len(r['righe'])} decisioni, {r['secondi']} s")
        return
    res = G.arena(rete, campione, a.matchup, a.coppie, a.regole, out / "arena_righe.jsonl", a.processi, a.iterazioni,
                  tuple(a.varianti), lambda t: print(t, flush=True))
    (out / "arena.json").write_text(json.dumps(res, indent=1))
    txt = G.testo_arena(res)
    (out / "arena.txt").write_text("\n".join(txt) + "\n")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
