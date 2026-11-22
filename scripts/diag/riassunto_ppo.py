#!/usr/bin/env python
"""Riassunto di più allenamenti PPO (22/11): per ogni cartella (tappe.jsonl),
la media del pannello sulle tappe da --da partite in poi (più stabile della
sola rete finale: tra due tappe il punteggio oscilla di ~0,1), contro le
ancore e contro simple_trade, e gli allarmi col bot a mano.

  uv run python scripts/diag/riassunto_ppo.py runs/ricetta2/* --da 14000
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--da", type=int, default=14000)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    lines = [f"Media del pannello dalle {args.da} partite in poi (ancore del pilota a pesi uguali):"]
    for run in args.runs:
        f = run / "tappe.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(x) for x in open(f)]
        late = [r for r in rows if r.get("partite", 0) >= args.da and "media ancore" in r]
        if not late:
            continue
        a = [r["media ancore"] for r in late]
        m = sum(a) / len(a)
        sd = math.sqrt(sum((x - m) ** 2 for x in a) / max(1, len(a) - 1))
        st = [r["simple_trade"] for r in late if r.get("simple_trade") is not None]
        bots = [f"{r['partite']}: {r['bot']:.3f}" for r in rows if "bot" in r]
        lines.append(f"   {run.name}: ancore {m:.3f} (da {len(a)} tappe, deviazione tra tappe {sd:.3f}), "
                     f"simple_trade {sum(st) / max(1, len(st)):.3f}; bot a mano (32 coppie) {', '.join(bots) or '-'}")
    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "a") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
