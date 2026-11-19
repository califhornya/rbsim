#!/usr/bin/env python
"""Arena dello spareggio (19/11): il bot a mano con tie_break="mean" contro il
bot a mano di adesso (tie_break="first"), stessa ricerca e stesso valore.

Regola fissata prima del lancio: punteggio osservato >= 0,52 E limite inferiore
dell'IC 95% sulle medie di coppia > 0,50 -> lo spareggio diventa il default del
bot; altrimenti resta com'è.

Disegno: --pairs seed nuovi (da --seed0); per ogni seed due partite Evelynn (A)
contro Kha'Zix (B) con la stessa apertura, i piloti scambiati; il primo
giocatore bilanciato (seed pari: comincia Evelynn, dispari: Kha'Zix); --budget s
di CPU per mossa ciascuno. Con --avanza, per entrambi il PASS forzato che chiude
un movimento si gioca subito. Prima, solo da leggere, la prima mossa nelle
quattro posizioni note (100 iterazioni). Risultato in --out (e a schermo).

  uv run python scripts/diag/arena_spareggio.py --pairs 800 --budget 0.4
"""
from __future__ import annotations

import argparse
import os
import pickle
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap_net as B  # noqa: E402  (decks, positions, _init, _mean_ci)

THRESHOLD, LOWER = 0.52, 0.50


def _first_move(task):
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import determinize
    name, tie, w, adv = task
    d = pickle.load(open(B.POSITIONS / f"{name}.pkl", "rb"))
    side = d["side"]
    gs = d["state"].clone()
    gs.rng = random.Random(10_000 + w)
    determinize(gs, observer=side, rng=gs.rng)
    p = gs.get_player(side)
    p.agent = HandwrittenAgent(p, rng=random.Random(20_000 + w), tie_break=tie, advance_forced_move=adv)
    GameLoop(gs)
    return name, tie, p.agent.decide_action(gs.get_player(gs.other(side)), d["cards_played"])


def _game(task):
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    seed, starter, cand_seat, budget, adv = task
    gs = build_game(game_seed=seed, deck_a_path=B.EVE, deck_b_path=B.KHA, ai_a=None, ai_b=None,
                    max_turns=B.MAX_TURNS, first_player=starter)
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        p.agent = HandwrittenAgent(p, rng=random.Random(seed * 2 + (seat == "B")), budget=budget,
                                   advance_forced_move=adv,
                                   tie_break="mean" if seat == cand_seat else "first")
    res = GameLoop(gs).start()
    cand, bot = gs.get_player(cand_seat).agent, gs.get_player(gs.other(cand_seat)).agent
    s = 1.0 if res.winner == cand_seat else 0.5 if res.winner == "DRAW" else 0.0
    return (seed, starter, cand_seat, s, cand.main_iters, bot.main_iters,
            (cand.empty_turns, cand.turns), (bot.empty_turns, bot.turns))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=800)
    ap.add_argument("--seed0", type=int, default=12_000)
    ap.add_argument("--budget", type=float, default=0.4)
    ap.add_argument("--worlds", type=int, default=24)
    ap.add_argument("--avanza", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=ROOT / "runs/spareggio/ARENA.txt")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    say(f"\n== Arena dello spareggio ({time.strftime('%d/%m %H:%M')})")
    say("candidato: il bot a mano con lo spareggio (tra le mosse con lo stesso Q: W/N più alto, poi più "
        "visite); avversario: il bot a mano di adesso; per entrambi backup best, table_value"
        + (", --avanza" if args.avanza else ", senza --avanza"))
    say(f"regola fissata prima: punteggio >= {THRESHOLD:.2f} e limite inferiore dell'IC 95% per coppia "
        f"> {LOWER:.2f} -> lo spareggio diventa il default; altrimenti il bot resta com'è")

    say(f"0. (solo informativo) prima mossa nelle posizioni note ({args.worlds} mondi, 100 iterazioni):")
    tasks = [(n, tie, w, args.avanza) for n in B.KNOWN for tie in ("mean", "first") for w in range(args.worlds)]
    with Pool(args.workers, initializer=B._init) as pool:
        moves = pool.map(_first_move, tasks)
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    for name, (right_key, words) in B.KNOWN.items():
        pos = pickle.load(open(B.POSITIONS / f"{name}.pkl", "rb"))
        labels = {a.to_engine(): a.label for a in
                  legal_actions(GameLoop(pos["state"].clone()), DecisionPoint.TURN_ACTION, pos["side"])}
        line = f"   {name}: giusta {words}"
        for tie, who in (("mean", "candidato"), ("first", "bot di adesso")):
            got = [m for n, t, m in moves if n == name and t == tie]
            top = Counter(labels.get(m, str(m)) for m in got).most_common(2)
            line += f"\n      {who}: giusta in {sum(m == pos[right_key] for m in got)}/{len(got)} " \
                    f"({'; '.join(f'{k}x {m}' for m, k in top)})"
        say(line)

    seeds = range(args.seed0, args.seed0 + args.pairs)
    say(f"1. {args.pairs} coppie, seed {seeds[0]}-{seeds[-1]} (pari: comincia Evelynn, dispari: Kha'Zix), "
        f"{args.budget} s di CPU per mossa ciascuno")
    tasks = [(s, "a" if s % 2 == 0 else "b", seat, args.budget, args.avanza)
             for s in seeds for seat in ("A", "B")]
    t0, rows = time.time(), []
    with Pool(args.workers, initializer=B._init) as pool:
        for r in pool.imap_unordered(_game, tasks):
            rows.append(r)
            if len(rows) % 100 == 0:
                print(f"   ... {len(rows)}/{len(tasks)} partite, {(time.time() - t0) / 60:.0f} min", flush=True)
    pairs: dict = {}
    for r in rows:
        pairs.setdefault(r[0], []).append(r[3])
    m, h = B._mean_ci([sum(v) / 2 for v in pairs.values()])
    w = sum(r[3] == 1.0 for r in rows)
    dr = sum(r[3] == 0.5 for r in rows)
    say(f"   punteggio {m:.3f} +- {h:.3f} (95%, sulle {len(pairs)} medie di coppia: {m - h:.3f}-{m + h:.3f}); "
        f"vinte {w}, perse {len(rows) - w - dr}, pari {dr}")
    for seat, deck in (("A", "Evelynn"), ("B", "Kha'Zix")):
        line = f"   candidato con {deck}: "
        parts = []
        for starter, who in (("a", "comincia Evelynn"), ("b", "comincia Kha'Zix")):
            xs = [r[3] for r in rows if r[2] == seat and r[1] == starter]
            mm, hh = B._mean_ci(xs)
            parts.append(f"{who} {mm:.3f} +- {hh:.3f}")
        say(line + "; ".join(parts))
    for idx, who in ((4, "candidato"), (5, "bot di adesso")):
        its = [x for r in rows for x in r[idx]]
        e = sum(r[idx + 2][0] for r in rows)
        t = sum(r[idx + 2][1] for r in rows)
        say(f"   {who}: {sum(its) / max(1, len(its)):.0f} iterazioni per decisione del turno, "
            f"turni passati subito {e}/{t} ({e / max(1, t):.1%})")
    say(f"   {(time.time() - t0) / 60:.0f} min")
    ok = m >= THRESHOLD and m - h > LOWER
    verdict = "PROMOSSO: lo spareggio diventa il default del bot" if ok else "NON PROMOSSO: il bot resta com'è"
    say(f"   Esito: {verdict} (punteggio {m:.3f}, soglia {THRESHOLD:.2f}; "
        f"limite inferiore {m - h:.3f}, deve superare {LOWER:.2f})")


if __name__ == "__main__":
    main()
