#!/usr/bin/env python
"""Arena sui tre matchup (22/11, docs/PIANO_FORZA.md): il bot a mano con i
prior di una rete allenata anche su Rengar (--ckpt) contro il campione, il
bot a mano con i prior 30.016 (--ckpt-avversario); 0,4 s per mossa a
entrambi, la stessa ricerca (scripts/diag/arena_bot.py, candidato prior_ppo).

Per matchup --coppie-* seed nuovi, due partite per seed con la stessa
apertura e i piloti scambiati; chi comincia bilanciato (seed pari: il primo
mazzo del matchup):
  EK  Evelynn-Kha'Zix  seed da 30.000
  ER  Evelynn-Rengar   seed da 31.000
  KR  Kha'Zix-Rengar   seed da 32.000
Regole fissate prima, IC 95% sulle medie di coppia:
  Rengar: ER e KR insieme, punteggio >= 0,52 e limite inferiore > 0,50;
  Evelynn-Kha'Zix tiene: limite inferiore > 0,47 (tolleranza di 3 punti);
  entrambe -> PROMOSSO, il candidato diventa il campione.

  uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt runs/rengar/ekr_s8/corrente.pt
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/diag"))

import arena_bot as A  # noqa: E402
import bootstrap_net as B  # noqa: E402

SEED0 = {"EK": 30_000, "ER": 31_000, "KR": 32_000}


def _sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16] if Path(path).exists() else "-"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="i prior PPO del candidato")
    ap.add_argument("--ckpt-avversario", default=str(ROOT / "runs/ppo1/ckpt_030016.pt"),
                    help="i prior PPO del campione")
    ap.add_argument("--coppie-ek", type=int, default=600)
    ap.add_argument("--coppie-rengar", type=int, default=400, help="per ciascuno di ER e KR")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=ROOT / "runs/rengar/ARENA.txt")
    args = ap.parse_args()
    from riftbound.ai.ppo.collect import DECK_NAME
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    pairs = {"EK": args.coppie_ek, "ER": args.coppie_rengar, "KR": args.coppie_rengar}
    say(f"\n== Arena sui tre matchup ({time.strftime('%d/%m %H:%M')})")
    say(f"candidato: il bot a mano con i prior PPO di {args.ckpt} (sha256 {_sha(args.ckpt)}); avversario: il "
        f"bot a mano con i prior PPO di {args.ckpt_avversario} (sha256 {_sha(args.ckpt_avversario)}); "
        f"{A.REF_BUDGET} s per mossa")
    say("regole fissate prima: Rengar (ER e KR insieme) >= 0,52 e limite inferiore > 0,50; Evelynn-Kha'Zix "
        "limite inferiore > 0,47; entrambe -> promosso")
    say("   " + "; ".join(f"{mu} {n} coppie, seed {SEED0[mu]}-{SEED0[mu] + n - 1}" for mu, n in pairs.items()))
    tasks = [(s, "a" if s % 2 == 0 else "b", seat, "prior_ppo", args.ckpt, "prior_ppo", args.ckpt_avversario, mu)
             for mu, n in pairs.items() for s in range(SEED0[mu], SEED0[mu] + n) for seat in ("A", "B")]
    t0, rows = time.time(), []
    with Pool(args.workers, initializer=B._init) as pool:
        for r in pool.imap_unordered(A._game, tasks):
            rows.append(r)
            if len(rows) % 100 == 0:
                print(f"   ... {len(rows)}/{len(tasks)} partite, {(time.time() - t0) / 60:.0f} min", flush=True)

    def mu_of(seed: int) -> str:
        return next(mu for mu, s0 in SEED0.items() if s0 <= seed < s0 + 1000)

    by: dict = {}
    for r in rows:
        by.setdefault(r[0], []).append(r[3])
    res = {}
    for group in (("EK",), ("ER",), ("KR",), ("ER", "KR")):
        ps = [sum(v) / 2 for seed, v in by.items() if mu_of(seed) in group]
        m, h = B._mean_ci(ps)
        res[group] = (m, h)
        if len(group) == 1:
            mu = group[0]
            a, b = DECK_NAME[mu[0]], DECK_NAME[mu[1]]
            cells = []
            for seat, deck in (("A", a), ("B", b)):
                for starter, who in (("a", a), ("b", b)):
                    xs = [r[3] for r in rows if mu_of(r[0]) == mu and r[2] == seat and r[1] == starter]
                    cells.append(f"con {deck}, comincia {who} {sum(xs) / max(1, len(xs)):.2f}")
            say(f"   {a}-{b}: {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f}); " + "; ".join(cells))
        else:
            say(f"   Rengar (ER e KR insieme): {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f})")
    m, h = res[("ER", "KR")]
    rengar = m >= 0.52 and m - h > 0.50
    me, he = res[("EK",)]
    ek = me - he > 0.47
    say(f"   Rengar: {'SÌ' if rengar else 'no'}; Evelynn-Kha'Zix tiene: {'SÌ' if ek else 'no'} "
        f"(limite inferiore {me - he:.3f}, soglia 0,47)")
    say(f"   {(time.time() - t0) / 60:.0f} min")
    say(f"   Esito: {'PROMOSSO' if rengar and ek else 'non promosso'}")


if __name__ == "__main__":
    main()
