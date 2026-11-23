#!/usr/bin/env python
"""Verifica di un mazzo nuovo nel training (22-23/11, docs/PIANO_FORZA.md;
disegno della revisione esterna): le reti allenate anche sui matchup nuovi
(--prova) contro quelle allenate solo sui vecchi (--controllo), stessi pesi
di partenza e stessa ricetta, accoppiate per ordine (stesso seme PPO).

Ogni rete gioca contro la stessa ancora congelata (--ancora, obbligatoria)
sulle stesse aperture nuove, due partite per seed con i piloti scambiati,
mossa col punteggio più alto, chi comincia alternato (seed pari: il primo
mazzo del matchup). --coppie seed per matchup, da --seed0 + 100.000 x
l'indice del matchup in ORDER; il testa a testa prova contro controllo da
--seed0 + 2.000.000.

Δ = punteggio della prova meno quello del controllo, entrambi contro
l'ancora, appaiato per apertura; i semi PPO a pesi uguali, e anche uno per
uno (gli IC sulle aperture descrivono i checkpoint misurati, non la
variabilità tra allenamenti).

Regole fissate prima:
  il mazzo nuovo entra se, sulla media a pesi uguali dei matchup --nuovi,
    la prova contro l'ancora fa >= 0,52 con limite inferiore > 0,50 e Δ ha
    limite inferiore > 0;
  i vecchi tengono se, su ciascuno dei matchup --vecchi, Δ ha limite
    inferiore > -0,03.
(Rengar, 22/11: vecchio EK, nuovi ER e KR insieme sulle aperture; seed da
9.000.000.)

  uv run --extra rl python scripts/diag/verifica_mazzi.py --prova a.pt b.pt --controllo c.pt d.pt \\
      --ancora e.pt --vecchi EK ER KR --nuovi EI KI RI --out runs/ivern/VERIFICA.txt
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

ORDER = ("EK", "ER", "KR", "EI", "KI", "RI", "ES", "KS", "RS", "IS")
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


def _block(parts: list) -> tuple:
    """Equal-weight mean of independent estimates (m, h): h adds in quadrature."""
    return sum(m for m, _ in parts) / len(parts), math.sqrt(sum(h * h for _, h in parts)) / len(parts)


def _label(path) -> str:
    p = Path(path)
    return f"{p.parent.name}/{p.stem}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prova", nargs="+", required=True)
    ap.add_argument("--controllo", nargs="+", required=True)
    ap.add_argument("--ancora", required=True)
    ap.add_argument("--vecchi", nargs="+", choices=ORDER, default=["EK", "ER", "KR"])
    ap.add_argument("--nuovi", nargs="+", choices=ORDER, default=["EI", "KI", "RI"])
    ap.add_argument("--coppie", type=int, default=1000, help="per matchup")
    ap.add_argument("--coppie-testa", type=int, default=400, help="per matchup e seme; 0: niente")
    ap.add_argument("--seed0", type=int, default=10_000_000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if len(args.prova) != len(args.controllo):
        sys.exit("--prova e --controllo: stesso numero di reti (accoppiate per seme)")
    from riftbound.ai.ppo.collect import DECK_NAME
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    mus = list(dict.fromkeys(args.vecchi + args.nuovi))
    s0 = {mu: args.seed0 + 100_000 * ORDER.index(mu) for mu in mus}
    h0 = {mu: args.seed0 + 2_000_000 + 100_000 * ORDER.index(mu) for mu in mus}
    nets = args.prova + args.controllo
    tasks = [("ancora", mu, s0[mu] + k, seat, c, args.ancora)
             for mu in mus for c in nets for k in range(args.coppie) for seat in ("A", "B")]
    tasks += [("testa", mu, h0[mu] + k, seat, p, c) for mu in mus for p, c in zip(args.prova, args.controllo)
              for k in range(args.coppie_testa) for seat in ("A", "B")]
    say(f"\n== Verifica dei mazzi ({time.strftime('%d/%m %H:%M')}): ancora {_label(args.ancora)}; "
        f"prova {', '.join(map(_label, args.prova))}; controllo {', '.join(map(_label, args.controllo))}; "
        f"vecchi {' '.join(args.vecchi)}, nuovi {' '.join(args.nuovi)}; {args.coppie} coppie per matchup "
        f"(seed da {args.seed0} + 100.000 x indice), testa a testa {args.coppie_testa}; {len(tasks)} partite")
    t0 = time.time()
    with Pool(args.workers, initializer=_init) as pool:
        rows = pool.map(_game, tasks, chunksize=16)

    pair: dict = {}                      # (net, mu) -> seed -> [two scores]
    cell: dict = {}                      # (net, mu, seat, seed parity) -> scores
    head: dict = {}                      # (prova net, mu) -> seed -> [two scores]
    for tag, mu, seed, seat, c, s in rows:
        if tag == "ancora":
            pair.setdefault((c, mu), {}).setdefault(seed, []).append(s)
            cell.setdefault((c, mu, seat, seed % 2), []).append(s)
        else:
            head.setdefault((c, mu), {}).setdefault(seed, []).append(s)

    def ps(c, mu) -> dict:
        return {seed: sum(v) / 2 for seed, v in pair[(c, mu)].items()}

    def group(cs, mu) -> list:
        per = [ps(c, mu) for c in cs]
        return [sum(p[seed] for p in per) / len(per) for seed in per[0]]

    def delta(cs_p, cs_c, mu) -> list:
        gp, gc = group(cs_p, mu), group(cs_c, mu)
        return [a - b for a, b in zip(gp, gc)]

    est: dict = {}
    for mu in mus:
        a, b = DECK_NAME[mu[0]], DECK_NAME[mu[1]]
        say(f"   {a}-{b}, contro l'ancora:")
        for c in nets:
            m, h = _ci(list(ps(c, mu).values()))
            cells = []
            for seat, deck in (("A", a), ("B", b)):
                for par, who in ((0, a), (1, b)):
                    xs = cell.get((c, mu, seat, par), [])
                    cells.append(f"con {deck}, comincia {who} {sum(xs) / max(1, len(xs)):.2f}")
            say(f"      {_label(c)}: {m:.3f} +- {h:.3f}; " + "; ".join(cells))
        est[mu] = {"prova": _ci(group(args.prova, mu)), "controllo": _ci(group(args.controllo, mu)),
                   "delta": _ci(delta(args.prova, args.controllo, mu)),
                   "semi": [_ci(delta([p], [c], mu)) for p, c in zip(args.prova, args.controllo)]}

    def line(title: str, e: dict) -> str:
        (mp, hp), (mc, hc), (md, hd) = e["prova"], e["controllo"], e["delta"]
        semi = ", ".join(f"{_label(p)} - {_label(c)} {m:+.3f} +- {h:.3f}"
                         for (p, c), (m, h) in zip(zip(args.prova, args.controllo), e["semi"]))
        signs = {m > 0 for m, _ in e["semi"] if m != 0}
        return (f"   {title}: prova {mp:.3f} +- {hp:.3f}, controllo {mc:.3f} +- {hc:.3f}; Δ {md:+.3f} +- {hd:.3f} "
                f"({md - hd:+.3f} - {md + hd:+.3f}); per seme: {semi}" + ("; SEMI DISCORDI" if len(signs) > 1 else ""))

    verdicts = []
    for mu in args.vecchi:
        say(line(f"vecchio {DECK_NAME[mu[0]]}-{DECK_NAME[mu[1]]}", est[mu]))
        md, hd = est[mu]["delta"]
        verdicts.append(f"{DECK_NAME[mu[0]]}-{DECK_NAME[mu[1]]} tiene: {'SÌ' if md - hd > -0.03 else 'no'} "
                        f"(limite inferiore di Δ {md - hd:+.3f}, soglia -0,03)")
    for mu in args.nuovi:
        say(line(f"nuovo {DECK_NAME[mu[0]]}-{DECK_NAME[mu[1]]}", est[mu]))
    blk = {k: _block([est[mu][k] for mu in args.nuovi]) for k in ("prova", "controllo", "delta")}
    blk["semi"] = [_block([est[mu]["semi"][i] for mu in args.nuovi]) for i in range(len(args.prova))]
    say(line(f"nuovi a pesi uguali ({' '.join(args.nuovi)})", blk))
    (mp, hp), (md, hd) = blk["prova"], blk["delta"]
    ok = mp >= 0.52 and mp - hp > 0.50 and md - hd > 0
    verdicts.insert(0, f"il mazzo nuovo entra: {'SÌ' if ok else 'no'} (prova {mp:.3f}, limite inferiore "
                       f"{mp - hp:.3f}; Δ col controllo, limite inferiore {md - hd:+.3f})")

    if args.coppie_testa:
        for mu in mus:
            for p, c in zip(args.prova, args.controllo):
                m, h = _ci([sum(v) / 2 for v in head[(p, mu)].values()])
                say(f"   testa a testa {DECK_NAME[mu[0]]}-{DECK_NAME[mu[1]]}: {_label(p)} contro {_label(c)} "
                    f"{m:.3f} +- {h:.3f}")
    for v in verdicts:
        say(f"   {v}")
    say(f"   ({(time.time() - t0) / 60:.0f} min)")


if __name__ == "__main__":
    main()
