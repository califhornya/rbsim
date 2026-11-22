#!/usr/bin/env python
"""Verifica del ramo a tre mazzi (22/11, docs/PIANO_FORZA.md; disegno della
revisione esterna): le reti allenate anche su Rengar (--prova) contro quelle
allenate solo su Evelynn-Kha'Zix (--controllo), stessi pesi di partenza e
stessi semi PPO, accoppiate per ordine (stesso seme).

Ogni rete gioca contro un'ancora congelata (--ancora, di default la partenza
30.016) sulle stesse aperture nuove, due partite per seed con i piloti
scambiati, mossa col punteggio più alto, chi comincia alternato:
  EK  Evelynn-Kha'Zix  --coppie-ek seed da 9.000.000
  ER  Evelynn-Rengar   --coppie-rengar seed da 9.100.000
  KR  Kha'Zix-Rengar   --coppie-rengar seed da 9.200.000
Per seed: media delle reti di un gruppo; differenza appaiata prova -
controllo con IC 95% sui seed (la varianza tra semi PPO si vede solo nelle
righe per seme). Poi, per matchup, prova contro controllo testa a testa
(--coppie-testa, seed da 9.300.000).

Regole fissate prima:
  Rengar entra se, su ER e KR insieme, la prova contro l'ancora fa >= 0,52
    con limite inferiore > 0,50, e la differenza prova - controllo ha
    limite inferiore > 0;
  Evelynn-Kha'Zix tiene se la differenza appaiata su EK ha limite
    inferiore > -0,03 (tolleranza di 3 punti).

  uv run --extra rl python scripts/diag/verifica_mazzi.py --prova a.pt b.pt --controllo c.pt d.pt
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SEED0 = {"EK": 9_000_000, "ER": 9_100_000, "KR": 9_200_000}
HEAD0 = 9_300_000
_NETS: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _net(path):
    from riftbound.ai.ppo.model import load
    if path not in _NETS:
        _NETS[path] = load(path).eval()
    return _NETS[path]


def _game(task):
    from riftbound.ai.ppo.collect import DECK_OF, play
    tag, mu, seed, seat, cand, opp = task
    other = "B" if seat == "A" else "A"
    g = play(seed, {seat: _net(cand), other: _net(opp)}, {}, sample=False, starter="a" if seed % 2 == 0 else "b",
             deck_a=DECK_OF[mu[0]], deck_b=DECK_OF[mu[1]])
    return tag, mu, seed, seat, cand, 1.0 if g["winner"] == seat else 0.5 if g["winner"] == "DRAW" else 0.0


def _ci(xs: list) -> tuple:
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))
    return m, 1.96 * sd / math.sqrt(len(xs))


def _label(path) -> str:
    p = Path(path)
    return f"{p.parent.name}/{p.stem}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prova", nargs="+", required=True)
    ap.add_argument("--controllo", nargs="+", required=True)
    ap.add_argument("--ancora", default=str(ROOT / "runs/ppo1/ckpt_030016.pt"))
    ap.add_argument("--coppie-ek", type=int, default=2000)
    ap.add_argument("--coppie-rengar", type=int, default=1000)
    ap.add_argument("--coppie-testa", type=int, default=600)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=ROOT / "runs/rengar/VERIFICA.txt")
    args = ap.parse_args()
    if len(args.prova) != len(args.controllo):
        sys.exit("--prova e --controllo: stesso numero di reti (accoppiate per seme)")
    from riftbound.ai.ppo.collect import DECK_NAME
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    pairs = {"EK": args.coppie_ek, "ER": args.coppie_rengar, "KR": args.coppie_rengar}
    nets = args.prova + args.controllo
    tasks = [("ancora", mu, SEED0[mu] + k, seat, c, args.ancora)
             for mu in pairs for c in nets for k in range(pairs[mu]) for seat in ("A", "B")]
    tasks += [("testa", mu, HEAD0 + 100_000 * i + k, seat, p, c)
              for i, mu in enumerate(pairs) for p, c in zip(args.prova, args.controllo)
              for k in range(args.coppie_testa) for seat in ("A", "B")]
    say(f"\n== Verifica dei tre mazzi ({time.strftime('%d/%m %H:%M')}): ancora {_label(args.ancora)}; "
        f"prova {', '.join(map(_label, args.prova))}; controllo {', '.join(map(_label, args.controllo))}; "
        f"coppie EK {args.coppie_ek}, ER e KR {args.coppie_rengar}, testa a testa {args.coppie_testa}; "
        f"{len(tasks)} partite")
    t0 = time.time()
    with Pool(args.workers, initializer=_init) as pool:
        rows = pool.map(_game, tasks, chunksize=16)

    # pair[(net, mu)][seed] = the pair's score against the anchor.
    pair: dict = {}
    seat_of: dict = {}
    for tag, mu, seed, seat, c, s in rows:
        if tag == "ancora":
            pair.setdefault((c, mu), {}).setdefault(seed, []).append(s)
            seat_of.setdefault((c, mu, seat, seed % 2), []).append(s)

    def group(cs: list, mus: tuple) -> dict:
        """Per (mu, seed): the group's mean pair score."""
        out = {}
        for mu in mus:
            for seed in pair[(cs[0], mu)]:
                out[(mu, seed)] = sum(sum(pair[(c, mu)][seed]) / 2 for c in cs) / len(cs)
        return out

    names = lambda mu: (DECK_NAME[mu[0]], DECK_NAME[mu[1]])  # noqa: E731
    for mu in pairs:
        a, b = names(mu)
        say(f"   {a}-{b}, contro l'ancora:")
        for c in nets:
            m, h = _ci([sum(v) / 2 for v in pair[(c, mu)].values()])
            cells = []
            for seat, deck in (("A", a), ("B", b)):
                for par, who in ((0, a), (1, b)):
                    xs = seat_of.get((c, mu, seat, par), [])
                    cells.append(f"con {deck}, comincia {who} {sum(xs) / max(1, len(xs)):.2f}")
            say(f"      {_label(c)}: {m:.3f} +- {h:.3f}; " + "; ".join(cells))

    verdicts = []
    for mus, title in ((("EK",), "Evelynn-Kha'Zix"), (("ER",), "Evelynn-Rengar"), (("KR",), "Kha'Zix-Rengar"),
                       (("ER", "KR"), "Rengar (ER e KR insieme)")):
        gp, gc = group(args.prova, mus), group(args.controllo, mus)
        mp, hp = _ci(list(gp.values()))
        mc, hc = _ci(list(gc.values()))
        md, hd = _ci([gp[k] - gc[k] for k in gp])
        per = []
        for p, c in zip(args.prova, args.controllo):
            xs = [sum(pair[(p, mu)][s]) / 2 - sum(pair[(c, mu)][s]) / 2 for mu in mus for s in pair[(p, mu)]]
            per.append(f"{_label(p)} - {_label(c)} {sum(xs) / len(xs):+.3f}")
        say(f"   {title}: prova {mp:.3f} +- {hp:.3f}, controllo {mc:.3f} +- {hc:.3f}; differenza "
            f"{md:+.3f} +- {hd:.3f} ({md - hd:+.3f} - {md + hd:+.3f}); per seme: " + ", ".join(per))
        if mus == ("EK",):
            verdicts.append(f"Evelynn-Kha'Zix tiene: {'SÌ' if md - hd > -0.03 else 'no'} "
                            f"(limite inferiore della differenza {md - hd:+.3f}, soglia -0,03)")
        if mus == ("ER", "KR"):
            ok = mp >= 0.52 and mp - hp > 0.50 and md - hd > 0
            verdicts.append(f"Rengar entra: {'SÌ' if ok else 'no'} (prova {mp:.3f}, limite inferiore "
                            f"{mp - hp:.3f}; differenza col controllo, limite inferiore {md - hd:+.3f})")

    for i, mu in enumerate(pairs):
        a, b = names(mu)
        for p, c in zip(args.prova, args.controllo):
            by: dict = {}
            for tag, mu_, seed, seat, cand, s in rows:
                if tag == "testa" and mu_ == mu and cand == p and HEAD0 + 100_000 * i <= seed < HEAD0 + 100_000 * (i + 1):
                    by.setdefault(seed, []).append(s)
            m, h = _ci([sum(v) / 2 for v in by.values()])
            say(f"   testa a testa {a}-{b}: {_label(p)} contro {_label(c)} {m:.3f} +- {h:.3f}")
    for v in verdicts:
        say(f"   {v}")
    say(f"   ({(time.time() - t0) / 60:.0f} min)")


if __name__ == "__main__":
    main()
