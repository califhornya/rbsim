#!/usr/bin/env python
"""Arena di un candidato contro il bot a mano (20/11): stesso disegno
dell'arena dello spareggio (arena_spareggio.py).

Candidati:
  tempo      il bot a mano con 0,8 s di CPU per mossa (l'avversario 0,4 s):
             gioca meglio se pensa il doppio?
  orizzonte  riftbound/ai/horizon.py, 0,4 s in tutto per mossa: guarda oltre
             la fine del proprio turno quando le due mosse migliori sono vicine.

Disegno: --pairs seed nuovi (da --seed0); per seed due partite Evelynn (A)
contro Kha'Zix (B) con la stessa apertura, i piloti scambiati; chi comincia
bilanciato (seed pari: Evelynn). Regola fissata prima: punteggio >= 0,52 e
limite inferiore dell'IC 95% sulle medie di coppia > 0,50 -> promosso.
Risultato in --out (e a schermo).

  uv run python scripts/diag/arena_bot.py --candidato orizzonte --pairs 800
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap_net as B  # noqa: E402

THRESHOLD, LOWER = 0.52, 0.50
REF_BUDGET = 0.4
CANDIDATES = {
    "tempo": "il bot a mano con 0,8 s di CPU per mossa",
    "orizzonte": "il bot che guarda oltre la fine del turno (riftbound/ai/horizon.py), 0,4 s per mossa",
    "prior_ppo": "il bot a mano con i prior della rete PPO (riftbound/ai/ppo/prior_bot.py), 0,4 s per mossa",
}
PPO_CKPT = ROOT / "runs/ppo1/corrente.pt"
_PPO: dict = {}


def _make(name, p, rng, ckpt=None):
    from riftbound.ai.handwritten import HandwrittenAgent
    if name == "tempo":
        return HandwrittenAgent(p, rng=rng, budget=2 * REF_BUDGET)
    if name == "orizzonte":
        from riftbound.ai.horizon import HorizonAgent
        return HorizonAgent(p, rng=rng, budget=REF_BUDGET)
    if name == "prior_ppo":
        import torch
        from riftbound.ai.ppo.model import load
        from riftbound.ai.ppo.prior_bot import PPOPriorAgent
        torch.set_num_threads(1)
        path = ckpt or os.environ.get("PPO_CKPT", str(PPO_CKPT))
        if path not in _PPO:                     # one net per checkpoint file
            _PPO[path] = load(path)
        return PPOPriorAgent(p, _PPO[path], rng=rng, budget=REF_BUDGET)
    return HandwrittenAgent(p, rng=rng, budget=REF_BUDGET)


def _game(task):
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    seed, starter, cand_seat, name, ckpt, opp, opp_ckpt = task
    gs = build_game(game_seed=seed, deck_a_path=B.EVE, deck_b_path=B.KHA, ai_a=None, ai_b=None,
                    max_turns=B.MAX_TURNS, first_player=starter)
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        rng = random.Random(seed * 2 + (seat == "B"))
        p.agent = _make(name, p, rng, ckpt) if seat == cand_seat else _make(opp, p, rng, opp_ckpt)
    res = GameLoop(gs).start()
    cand, bot = gs.get_player(cand_seat).agent, gs.get_player(gs.other(cand_seat)).agent
    s = 1.0 if res.winner == cand_seat else 0.5 if res.winner == "DRAW" else 0.0
    return (seed, starter, cand_seat, s, cand.main_iters, bot.main_iters,
            (cand.empty_turns, cand.turns), (bot.empty_turns, bot.turns), dict(getattr(cand, "stats", {})))


def _first_move(task):
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import determinize
    import pickle
    name, who, w = task
    d = pickle.load(open(B.POSITIONS / f"{name}.pkl", "rb"))
    side = d["side"]
    gs = d["state"].clone()
    gs.rng = random.Random(10_000 + w)
    determinize(gs, observer=side, rng=gs.rng)
    p = gs.get_player(side)
    p.agent = _make(who, p, random.Random(20_000 + w))
    GameLoop(gs)
    return name, who, p.agent.decide_action(gs.get_player(gs.other(side)), d["cards_played"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidato", choices=tuple(CANDIDATES), required=True)
    ap.add_argument("--ckpt", default=None, help="prior_ppo: il checkpoint PPO del candidato")
    ap.add_argument("--avversario", choices=("bot", "prior_ppo"), default="bot")
    ap.add_argument("--ckpt-avversario", default=None, help="prior_ppo: il checkpoint dell'avversario")
    ap.add_argument("--pairs", type=int, default=800)
    ap.add_argument("--seed0", type=int, default=None)
    ap.add_argument("--worlds", type=int, default=24)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    name = args.candidato
    seed0 = args.seed0 if args.seed0 is not None else {"tempo": 13_000, "orizzonte": 14_000,
                                                       "prior_ppo": 15_000}[name]
    tag = name if args.avversario == "bot" else f"{name}_{Path(args.ckpt or '').stem}_contro_{Path(args.ckpt_avversario or '').stem}"
    out = args.out or ROOT / f"runs/arena_{tag}/ARENA.txt"
    out.parent.mkdir(parents=True, exist_ok=True)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(out, "a") as f:
            f.write(text + "\n")

    say(f"\n== Arena: {name} ({time.strftime('%d/%m %H:%M')})")
    import hashlib

    def sha(path):
        return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16] if path and Path(path).exists() else "-"
    opp_words = "il bot a mano" if args.avversario == "bot" else \
        f"il bot a mano con i prior PPO di {args.ckpt_avversario} (sha256 {sha(args.ckpt_avversario)})"
    cand_ck = args.ckpt or os.environ.get("PPO_CKPT", str(PPO_CKPT)) if name == "prior_ppo" else None
    say(f"candidato: {CANDIDATES[name]}" + (f", {cand_ck} (sha256 {sha(cand_ck)})" if cand_ck else "")
        + f"; avversario: {opp_words}, {REF_BUDGET} s per mossa")
    say(f"regola fissata prima: punteggio >= {THRESHOLD:.2f} e limite inferiore dell'IC 95% per coppia "
        f"> {LOWER:.2f} -> promosso")

    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    import pickle
    if name == "orizzonte":
        say(f"0. (solo informativo) prima mossa nelle posizioni note ({args.worlds} mondi, a tempo):")
        tasks = [(n, who, w) for n in B.KNOWN for who in (name, "bot") for w in range(args.worlds)]
        with Pool(args.workers, initializer=B._init) as pool:
            moves = pool.map(_first_move, tasks)
        for n, (right_key, words) in B.KNOWN.items():
            pos = pickle.load(open(B.POSITIONS / f"{n}.pkl", "rb"))
            labels = {a.to_engine(): a.label for a in
                      legal_actions(GameLoop(pos["state"].clone()), DecisionPoint.TURN_ACTION, pos["side"])}
            line = f"   {n}: giusta {words}"
            for who, words_who in ((name, "candidato"), ("bot", "bot a mano")):
                got = [m for nn, ww, m in moves if nn == n and ww == who]
                top = Counter(labels.get(m, str(m)) for m in got).most_common(2)
                line += f"\n      {words_who}: giusta in {sum(m == pos[right_key] for m in got)}/{len(got)} " \
                        f"({'; '.join(f'{k}x {m}' for m, k in top)})"
            say(line)

    seeds = range(seed0, seed0 + args.pairs)
    say(f"1. {args.pairs} coppie, seed {seeds[0]}-{seeds[-1]} (pari: comincia Evelynn, dispari: Kha'Zix)")
    tasks = [(s, "a" if s % 2 == 0 else "b", seat, name, args.ckpt, args.avversario, args.ckpt_avversario)
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
        parts = []
        for starter, who in (("a", "comincia Evelynn"), ("b", "comincia Kha'Zix")):
            mm, hh = B._mean_ci([r[3] for r in rows if r[2] == seat and r[1] == starter])
            parts.append(f"{who} {mm:.3f} +- {hh:.3f}")
        say(f"   candidato con {deck}: " + "; ".join(parts))
    for idx, who in ((4, "candidato"), (5, "bot")):
        its = [x for r in rows for x in r[idx]]
        e, t = sum(r[idx + 2][0] for r in rows), sum(r[idx + 2][1] for r in rows)
        say(f"   {who}: {sum(its) / max(1, len(its)):.0f} iterazioni per decisione del turno, "
            f"turni passati subito {e}/{t} ({e / max(1, t):.1%})")
    st: Counter = Counter()
    for r in rows:
        st.update(r[8])
    if st:
        say("   orizzonte: " + ", ".join(f"{k} {v}" for k, v in st.items()))
    say(f"   {(time.time() - t0) / 60:.0f} min")
    ok = m >= THRESHOLD and m - h > LOWER
    verdict = "PROMOSSO" if ok else "NON PROMOSSO"
    say(f"   Esito: {verdict} (punteggio {m:.3f}, soglia {THRESHOLD:.2f}; "
        f"limite inferiore {m - h:.3f}, deve superare {LOWER:.2f})")


if __name__ == "__main__":
    main()
