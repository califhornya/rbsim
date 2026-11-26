"""Serie «stesso seme»: la partita di Matteo (Evelynn contro Sett, campione) rifatta dal Mac da sola, dal turno 1, con lo
stesso seme di partita, finche' Sett non vince (riftbound/rs/stesso_seme.py).

  stesso_seme.py --partita FILE.json [--x 500] [--processi W] [--ckpt PATH | --casuali] --out DIR

`--ckpt` (default: `info.campione` della partita, se esiste, se no runs/sett/ekris_s12/ckpt_040000.pt) o `--casuali`
(rete a pesi casuali, per provare dove il checkpoint non c'e'). Scrive in DIR: tentativi.jsonl, vittoria.json,
sconfitta.json, matteo.json e riepilogo.txt (ultima riga `totale:`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import stesso_seme as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partita", required=True, help="partita salvata dalla pagina (file json)")
    ap.add_argument("--x", type=int, default=500, help="tentativi al massimo (default 500)")
    ap.add_argument("--processi", type=int, default=1)
    ap.add_argument("--ckpt", help="checkpoint del campione")
    ap.add_argument("--casuali", action="store_true", help="rete a pesi casuali")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    B = S.base(a.partita, a.ckpt, a.casuali)
    print(f"== stesso seme: {B['nome']} seme {B['seed']}, al piu' {a.x} tentativi, {a.processi} processi", flush=True)
    righe = S.serie(B, a.x, a.processi, Path(a.out), lambda s: print(s, flush=True))
    print("\n".join(righe[-3:]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
