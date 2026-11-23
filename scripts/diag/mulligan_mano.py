#!/usr/bin/env python
"""Mulligan di una mano fissata (23/11, domanda di Astra sulla partita 35.010):
la stessa mano iniziale di Sett, i mulligan a confronto, il resto uguale.

Mano: Rampage, First Mate, Showstopper, Irresistible Faefolk (Sett in B,
Evelynn in A). Bracci (le carte rimandate, §117: al massimo due):
  RS   Rampage e Showstopper (la scelta della rete, 95%)
  S    solo Showstopper (tenere Rampage)
  R    solo Rampage
  -    tenere tutto
Per ogni seed: build_game come le arene (mazzi mescolati dal seed), poi le
quattro carte della mano tolte dal mazzo di Sett e messe in cima, il resto
nell'ordine casuale del seed. Lo stesso seed per i quattro bracci (stesse
pescate, stesso mazzo di Evelynn: confronto appaiato); le pescate al posto
delle carte rimandate vengono dalla cima e le rimandate vanno in fondo
(Player.mulligan, §117.2-117.3). Nessuno dei due piloti conosce l'ordine del
mazzo (la ricerca determinizza le carte nascoste).
Chi comincia: seed pari Sett, dispari Evelynn. Piloti: il bot a mano, 0,4 s
per mossa, su entrambi i lati; con --ckpt il bot a mano con i prior di quella
rete (il campione delle arene; serve torch). Il mulligan di Evelynn: il suo
bot. Una riga per partita in --out (jsonl): rilanciato, riprende.

  python scripts/diag/mulligan_mano.py --seeds 300 --out runs/mulligan/sett.jsonl
  python scripts/diag/mulligan_mano.py --riassunto --out runs/mulligan/sett.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HAND = ("Rampage", "First Mate", "Showstopper", "Irresistible Faefolk")
ARMS = {"RS": ("Rampage", "Showstopper"), "S": ("Showstopper",), "R": ("Rampage",), "-": ()}
SEED0 = 700_000          # disgiunti da training (121M...), arene (13k-50k) e verifiche
_NET = {}


def _agent(p, rng, ckpt):
    from riftbound.ai.handwritten import HandwrittenAgent
    if ckpt is None:
        return HandwrittenAgent(p, rng=rng, budget=0.4)
    import torch
    from riftbound.ai.ppo.model import load
    from riftbound.ai.ppo.prior_bot import PPOPriorAgent
    torch.set_num_threads(1)
    if ckpt not in _NET:
        _NET[ckpt] = load(ckpt)
    return PPOPriorAgent(p, _NET[ckpt], rng=rng, budget=0.4)


def _game(task):
    from riftbound.ai.ppo.collect import DECK_OF, MAX_TURNS
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    seed, arm, ckpt = task
    sett_first = seed % 2 == 0
    gs = build_game(game_seed=seed, deck_a_path=DECK_OF["E"], deck_b_path=DECK_OF["S"], ai_a=None, ai_b=None,
                    max_turns=MAX_TURNS, first_player="b" if sett_first else "a")
    deck = gs.B.deck.cards
    top = []
    for name in HAND:
        i = next(i for i, c in enumerate(deck) if c.name == name)
        top.append(deck.pop(i))
    deck.extend(reversed(top))                 # draw() pops the end: HAND in order
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        p.agent = _agent(p, random.Random(seed * 2 + (seat == "B")), ckpt)
    sett = gs.B

    def forced():
        names = [c.name for c in sett.hand]
        assert sorted(names) == sorted(HAND), names
        return [names.index(n) for n in ARMS[arm]]
    sett.agent.decide_mulligan = forced
    t = time.time()
    res = GameLoop(gs).start()
    s = 1.0 if res.winner == "B" else 0.5 if res.winner == "DRAW" else 0.0
    return {"seed": seed, "arm": arm, "sett_first": sett_first, "sett": s, "winner": res.winner,
            "turns": gs.turn, "score": [gs.points_A, gs.points_B],
            "sec": round(time.time() - t, 1), "ckpt": ckpt}


def _ci(xs):
    n = len(xs)
    if n < 2:
        return (sum(xs) / max(n, 1), float("nan"))
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * (var / n) ** 0.5


def summary(path: Path) -> str:
    rows = [json.loads(l) for l in open(path)]
    by = {}
    for r in rows:
        by.setdefault(r["seed"], {})[r["arm"]] = r
    full = {s: d for s, d in by.items() if len(d) == len(ARMS)}
    out = [f"{path}: {len(rows)} partite, {len(full)} seed con tutti i bracci"]
    for label, keep in (("tutti", lambda s: True), ("Sett comincia", lambda s: s % 2 == 0),
                        ("Evelynn comincia", lambda s: s % 2 == 1)):
        seeds = [s for s in full if keep(s)]
        if not seeds:
            continue
        out.append(f"\n{label}: {len(seeds)} seed")
        for arm in ARMS:
            m, h = _ci([full[s][arm]["sett"] for s in seeds])
            d, hd = _ci([full[s][arm]["sett"] - full[s]["RS"]["sett"] for s in seeds])
            out.append(f"  rimanda {arm:3s}: Sett {m:.3f} ± {h:.3f}" +
                       ("" if arm == "RS" else f"   differenza da RS {d:+.3f} ± {hd:.3f}"))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=SEED0)
    ap.add_argument("--ckpt", default=None, help="i prior PPO dei due bot (il campione); senza: bot a mano")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--riassunto", action="store_true")
    args = ap.parse_args()
    if args.riassunto:
        print(summary(args.out))
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        done = {(r["seed"], r["arm"]) for r in map(json.loads, open(args.out))}
    tasks = [(args.seed0 + k, arm, args.ckpt) for k in range(args.seeds) for arm in ARMS
             if (args.seed0 + k, arm) not in done]
    print(f"{len(tasks)} partite da giocare ({len(done)} gia' fatte), {args.workers} processi", flush=True)
    with Pool(args.workers) as pool, open(args.out, "a") as f:
        for i, r in enumerate(pool.imap_unordered(_game, tasks), 1):
            f.write(json.dumps(r) + "\n")
            f.flush()
            if i % 40 == 0:
                print(f"  {i}/{len(tasks)} {time.strftime('%H:%M')}", flush=True)
    print(summary(args.out))


if __name__ == "__main__":
    main()
