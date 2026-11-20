#!/usr/bin/env python
"""Pilota del passo 2 (20/11, protocollo della revisione esterna): le etichette
di confronto tra mosse sorelle sono stabili, e 32 iterazioni bastano a farle?

Radici: 128 decisioni del turno principale da 128 partite diverse (seed
30000-30127) del bot a mano contro se stesso (100 iterazioni), Evelynn (A)
contro Kha'Zix (B). Bilanciate per chi comincia (seed pari: Evelynn), per chi
decide (A o B) e per fase (turni 1-4, 5-8, 9+). In ogni radice fino a tre
sorelle: la mossa del bot (100 iterazioni), la migliore alternativa per Q, una
mossa legale diversa a caso; due mosse che lasciano lo stesso identico stato
(confronto byte per byte dopo la mossa) contano una volta sola.

Continuazioni: in un mondo (determinize dal punto di vista di chi decide, seed
fisso) si forza solo la prima mossa (le scelte interne al baseline), poi i
due bot a mano giocano fino alla fine con seed fissi, gli stessi per ogni
sorella. Esito 1 / 0,5 / 0 dal lato di chi decideva.
  A. tutte le radici, 8 mondi (W1), 32 iterazioni;
  B. tutte le radici, 8 mondi nuovi (W2), 32 iterazioni: le differenze tra
     sorelle si ripetono?
  C. 48 radici (indice % 8 < 3, tutti gli strati), W1, 100 iterazioni;
  D. dove la migliore sorella per A e per C non coincide: le due su 16 mondi
     nuovi (W3) a 100 iterazioni; la perdita di scegliere con 32.

Regole fissate prima (in RISULTATO): le differenze si ripetono se la
correlazione tra le differenze delle sorelle in W1 e in W2 ha il limite
inferiore dell'IC 95% (bootstrap per radice) sopra 0; 32 iterazioni bastano
se il limite superiore dell'IC 95% della perdita media per radice è sotto
0,02 punti di vittoria.

Riprende da dove si era fermato (runs/pilota/risultati.jsonl); un file STOP
nella cartella lo ferma.

  uv run python scripts/diag/pilota_sorelle.py --run-dir runs/pilota
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap_net as B  # noqa: E402  (EVE, KHA, MAX_TURNS, _init)

SEED0 = 30_000
CHEAP, REF = 32, 100
WORLDS = {"W1": (31_000, 8), "W2": (32_000, 8), "W3": (33_000, 16)}
STRATA = ((1, 4), (5, 8), (9, 40))
KINDS = ("bot", "alternativa", "altra")


def _subset(i: int) -> bool:
    return i % 8 < 3


class _Stop(BaseException):
    """Ends a source game at its root (not an Exception: the loop won't catch it)."""


def _fingerprint(gs, side, action, cards_played) -> str:
    from riftbound.core.loop import GameLoop
    s = gs.clone()
    s.rng = random.Random(0)
    try:
        loop = GameLoop(s)
        loop._apply_action(s.get_player(side), action, cards_played_this_turn=cards_played)
        loop._recompute_passives()
        s.A.agent = s.B.agent = None
        return hashlib.sha1(pickle.dumps(s, protocol=pickle.HIGHEST_PROTOCOL)).hexdigest()
    except Exception as e:  # noqa: BLE001 — then it counts as different
        return f"errore {type(e).__name__} {action}"


def _siblings(gs, side, cards_played, rng):
    """(actions, labels, kinds, Q) at a root, or None with fewer than 2 distinct."""
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    s = gs.clone()
    p = s.get_player(side)
    p.agent = HandwrittenAgent(p, iterations=REF, rng=random.Random(rng.randrange(1 << 30)))
    GameLoop(s)
    legal = legal_actions(p.agent.loop, DecisionPoint.TURN_ACTION, side)
    if len(legal) < 2:
        return None
    labels = {a.to_engine(): a.label for a in legal}
    root = p.agent.search(DecisionPoint.TURN_ACTION, legal, cards_played=cards_played)
    bot = p.agent._play(root, side)
    q = {k: c.Q for k, c in root.children.items() if c.N > 0}
    chosen, fps = [bot], {_fingerprint(gs, side, bot, cards_played)}

    def take(cands):
        for a in cands:
            if a in chosen:
                continue
            fp = _fingerprint(gs, side, a, cards_played)
            if fp not in fps:
                chosen.append(a)
                fps.add(fp)
                return True
        return False
    take(sorted(q, key=lambda k: -q[k]))
    rest = [a.to_engine() for a in legal]
    rng.shuffle(rest)
    take(rest)
    if len(chosen) < 2:
        return None
    return chosen, [labels.get(a, str(a)) for a in chosen], list(KINDS[:len(chosen)]), \
        [q.get(a) for a in chosen]


def _root(i: int):
    """Plays source game i to its root; the root's record, or None."""
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.game_factory import build_game
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    seed = SEED0 + i
    rng = random.Random(seed)
    starter = "a" if i % 2 == 0 else "b"
    side = "A" if (i // 2) % 2 == 0 else "B"
    lo, hi = STRATA[(i // 4) % 3]
    target = rng.randint(lo, hi)
    gs = build_game(game_seed=seed, deck_a_path=B.EVE, deck_b_path=B.KHA, ai_a=None, ai_b=None,
                    max_turns=B.MAX_TURNS, first_player=starter)

    class Scout(HandwrittenAgent):
        def decide_action(self, opponent, cards_played: int = 0):
            if self.gs.turn >= target and \
                    len(legal_actions(self.loop, DecisionPoint.TURN_ACTION, self.player.name)) >= 2:
                sib = _siblings(self.gs, self.player.name, cards_played, rng)
                if sib is not None:
                    raise _Stop({"state": self.gs.clone(), "side": self.player.name,
                                 "cards_played": cards_played, "turn": self.gs.turn, "sib": sib})
            return super().decide_action(opponent, cards_played)

    for seat in ("A", "B"):
        p = gs.get_player(seat)
        cls = Scout if seat == side else HandwrittenAgent
        p.agent = cls(p, iterations=REF, rng=random.Random(seed * 2 + (seat == "B")))
    try:
        GameLoop(gs).start()
        return None                       # ended before the target turn
    except _Stop as stop:
        d = stop.args[0]
    acts, labels, kinds, q = d.pop("sib")
    d.update(index=i, seed=seed, starter=starter, stratum=f"{lo}-{hi}", siblings=acts,
             labels=labels, kinds=kinds, q=q, deck="Evelynn" if side == "A" else "Kha'Zix")
    return d


def _continue(task):
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import determinize
    root_path, i, j, wset, k, iters = task
    d = pickle.load(open(root_path, "rb"))
    side, forced = d["side"], d["siblings"][j]
    base, _ = WORLDS[wset]
    w = base + i * 64 + k
    gs = d["state"].clone()
    gs.rng = random.Random(w)
    determinize(gs, observer=side, rng=gs.rng)

    class Forced(HandwrittenAgent):
        first = True

        def decide_action(self, opponent, cards_played: int = 0):
            if self.first:
                self.first = False
                self._ensure_rng()
                self._ensure_fallback()
                self._release_forced()
                legal = [a.to_engine() for a in legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)]
                if forced not in legal:
                    raise RuntimeError(f"mossa non legale in questo mondo: {forced}")
                return forced
            return super().decide_action(opponent, cards_played)

    other = gs.other(side)
    gs.get_player(side).agent = Forced(gs.get_player(side), iterations=iters, rng=random.Random(w * 2 + 1))
    gs.get_player(other).agent = HandwrittenAgent(gs.get_player(other), iterations=iters,
                                                  rng=random.Random(w * 2 + 2))
    t0 = time.process_time()
    try:
        res = GameLoop(gs).resume_to_completion()
        s = 1.0 if res.winner == side else 0.5 if res.winner == "DRAW" else 0.0
    except RuntimeError as e:
        return {"i": i, "j": j, "set": wset, "k": k, "it": iters, "score": None, "err": str(e)}
    return {"i": i, "j": j, "set": wset, "k": k, "it": iters, "score": s,
            "cpu": round(time.process_time() - t0, 2)}


# ----------------------------------------------------------------- the report

def _means(rows, i, wset, it):
    by: dict = {}
    for r in rows:
        if r["i"] == i and r["set"] == wset and r["it"] == it and r["score"] is not None:
            by.setdefault(r["j"], []).append(r["score"])
    return {j: sum(v) / len(v) for j, v in by.items()}


def _pairs(m):
    js = sorted(m)
    return {(a, b): m[a] - m[b] for x, a in enumerate(js) for b in js[x + 1:]}


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx and sy else float("nan")


def _best(m):
    return max(sorted(m), key=lambda j: m[j])      # ties: the first (the bot's move)


def report(run_dir: Path, roots: dict, rows: list, say) -> None:
    say(f"Radici: {len(roots)}; sorelle per radice: "
        + ", ".join(f"{n}: {sum(len(d['siblings']) == n for d in roots.values())}" for n in (2, 3)))
    for key, vals in (("deck", ("Evelynn", "Kha'Zix")), ("starter", ("a", "b")),
                      ("stratum", tuple(f"{lo}-{hi}" for lo, hi in STRATA))):
        say(f"   per {key}: " + ", ".join(f"{v} {sum(d[key] == v for d in roots.values())}" for v in vals))

    # 1. replication: W1 against W2, 32 iterations
    pr = []
    for i in roots:
        p1, p2 = _pairs(_means(rows, i, "W1", CHEAP)), _pairs(_means(rows, i, "W2", CHEAP))
        pr += [(i, p1[k], p2[k]) for k in p1 if k in p2]
    r = _corr([a for _, a, _ in pr], [b for _, _, b in pr])
    idx = sorted({i for i, _, _ in pr})
    brng, boots = random.Random(1), []
    for _ in range(2000):
        pick = [brng.choice(idx) for _ in idx]
        xs, ys = [], []
        for i in pick:
            for ii, a, b in pr:
                if ii == i:
                    xs.append(a)
                    ys.append(b)
        c = _corr(xs, ys)
        if not math.isnan(c):
            boots.append(c)
    boots.sort()
    lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]
    clear = [(a, b) for _, a, b in pr if abs(a) >= 0.375]
    same = sum((a > 0 and b > 0) or (a < 0 and b < 0) for a, b in clear)
    say(f"1. Si ripetono? Differenze tra sorelle, 8 mondi W1 contro 8 nuovi W2, {CHEAP} iterazioni: "
        f"{len(pr)} coppie, correlazione {r:.2f} (IC 95% {lo:.2f}-{hi:.2f})")
    say(f"   con |differenza| >= 3/8 in W1: stesso verso in W2 in {same}/{len(clear)}")
    # By pair: the move at random is often easy to tell from the others; the
    # pair that matters for choosing is the bot's move against its alternative.
    for a, b in ((0, 1), (0, 2), (1, 2)):
        sel = []
        for i in roots:
            p1, p2 = _pairs(_means(rows, i, "W1", CHEAP)), _pairs(_means(rows, i, "W2", CHEAP))
            if (a, b) in p1 and (a, b) in p2:
                sel.append((p1[(a, b)], p2[(a, b)]))
        if len(sel) >= 3:
            cl = [(x, y) for x, y in sel if abs(x) >= 0.375]
            sm = sum((x > 0 and y > 0) or (x < 0 and y < 0) for x, y in cl)
            say(f"   {KINDS[a]} contro {KINDS[b]}: {len(sel)} coppie, correlazione "
                f"{_corr([x for x, _ in sel], [y for _, y in sel]):.2f}; con |differenza| >= 3/8: "
                f"stesso verso in {sm}/{len(cl)}; differenza media {sum(x + y for x, y in sel) / (2 * len(sel)):+.3f}")
    if r > 0:
        for target in (0.5, 0.7):
            n = 8 * (target / (1 - target)) * ((1 - r) / r)
            say(f"   mondi per radice per un'affidabilità di {target}: circa {math.ceil(n)}")
    say(f"   Regola: {'SI RIPETONO' if lo > 0 else 'NON SI RIPETONO'} (limite inferiore {lo:.2f}, deve superare 0)")

    # 2. 32 against 100 on the same worlds, then the loss on new worlds
    sub = [i for i in roots if _subset(i)]
    agree, d32, d100, losses = 0, [], [], []
    for i in sub:
        m32, m100 = _means(rows, i, "W1", CHEAP), _means(rows, i, "W1", REF)
        if not m32 or not m100:
            continue
        p32, p100 = _pairs(m32), _pairs(m100)
        d32 += [p32[k] for k in p32 if k in p100]
        d100 += [p100[k] for k in p32 if k in p100]
        b32, b100 = _best(m32), _best(m100)
        if b32 == b100:
            agree += 1
            losses.append(0.0)
        else:
            m3 = _means(rows, i, "W3", REF)
            if b32 in m3 and b100 in m3:
                losses.append(m3[b100] - m3[b32])
    say(f"2. {CHEAP} contro {REF} iterazioni, {len(sub)} radici, stessi mondi W1: stessa sorella migliore in "
        f"{agree}/{len(losses)}; correlazione delle differenze {_corr(d32, d100):.2f}")
    if losses:
        ml, hl = B._mean_ci(losses) if len(losses) > 1 else (losses[0], 0.0)
        say(f"   perdita di scegliere con {CHEAP} (valutata su 16 mondi nuovi W3 a {REF}): "
            f"{ml:+.3f} ± {hl:.3f} per radice (IC 95%: {ml - hl:+.3f} - {ml + hl:+.3f})")
        say(f"   Regola: {CHEAP} iterazioni {'BASTANO' if ml + hl < 0.02 else 'NON BASTANO'} "
            f"(limite superiore {ml + hl:+.3f}, deve stare sotto +0,02)")

    # 3. what it cost
    for it in (CHEAP, REF):
        c = [r["cpu"] for r in rows if r["it"] == it and r.get("cpu") is not None]
        if c:
            say(f"3. {it} iterazioni: {len(c)} continuazioni, {sum(c) / len(c):.1f} s di CPU in media")
    c = [r["cpu"] for r in rows if r["it"] == CHEAP and r.get("cpu") is not None]
    if c:
        hours = 1000 * 3 * 8 * (sum(c) / len(c)) / 3600
        say(f"   1.000 radici x 3 sorelle x 8 mondi a {CHEAP} iterazioni: circa {hours:.0f} ore di CPU "
            f"({hours / 8:.1f} ore su 8 core)")
    errs = [r for r in rows if r["score"] is None]
    if errs:
        say(f"   continuazioni fallite: {len(errs)} (prima: {errs[0].get('err')})")


# ----------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs/pilota")
    ap.add_argument("--roots", type=int, default=128)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--scale-worlds", type=int, default=0,
                    help="solo per provarlo: usa al massimo questi mondi per insieme")
    args = ap.parse_args()
    run, rdir = args.run_dir, args.run_dir / "radici"
    rdir.mkdir(parents=True, exist_ok=True)
    stop = run / "STOP"

    def say(text: str) -> None:
        print(text, flush=True)
        with open(run / "RISULTATO.txt", "a") as f:
            f.write(text + "\n")

    t0 = time.time()
    todo = [i for i in range(args.roots) if not (rdir / f"r{i:03d}.pkl").exists()
            and not (rdir / f"r{i:03d}.none").exists()]
    if todo:
        print(f"Radici da preparare: {len(todo)}", flush=True)
        with Pool(args.workers, initializer=B._init) as pool:
            for i, d in zip(todo, pool.imap(_root, todo)):
                if d is None:
                    (rdir / f"r{i:03d}.none").touch()
                else:
                    pickle.dump(d, open(rdir / f"r{i:03d}.pkl", "wb"))
                if stop.exists():
                    pool.terminate()
                    sys.exit("Fermato (STOP).")
    roots = {}
    for i in range(args.roots):
        f = rdir / f"r{i:03d}.pkl"
        if f.exists():
            roots[i] = pickle.load(open(f, "rb"))

    res_path = run / "risultati.jsonl"
    rows = [json.loads(x) for x in open(res_path)] if res_path.exists() else []
    done = {(r["i"], r["j"], r["set"], r["k"], r["it"]) for r in rows}

    def nworlds(wset):
        n = WORLDS[wset][1]
        return min(n, args.scale_worlds) if args.scale_worlds else n

    def run_tasks(tasks, name):
        tasks = [t for t in tasks if t[1:] not in done]
        if not tasks:
            return
        print(f"{name}: {len(tasks)} continuazioni", flush=True)
        t1 = time.time()
        with Pool(args.workers, initializer=B._init) as pool, open(res_path, "a") as out:
            for n, r in enumerate(pool.imap_unordered(_continue, tasks, chunksize=1), 1):
                out.write(json.dumps(r) + "\n")
                out.flush()
                rows.append(r)
                done.add((r["i"], r["j"], r["set"], r["k"], r["it"]))
                if n % 100 == 0:
                    print(f"   ... {n}/{len(tasks)}, {(time.time() - t1) / 60:.0f} min", flush=True)
                if stop.exists():
                    pool.terminate()
                    sys.exit("Fermato (STOP): rilanciato, riprende.")

    def tasks_for(idx, wset, it, sibs=None):
        return [(str(rdir / f"r{i:03d}.pkl"), i, j, wset, k, it) for i in idx
                for j in (sibs[i] if sibs else range(len(roots[i]["siblings"])))
                for k in range(nworlds(wset))]

    sub = [i for i in roots if _subset(i)]
    run_tasks(tasks_for(roots, "W1", CHEAP) + tasks_for(sub, "W1", REF), "A e C")
    run_tasks(tasks_for(roots, "W2", CHEAP), "B")
    pick = {}
    for i in sub:
        m32, m100 = _means(rows, i, "W1", CHEAP), _means(rows, i, "W1", REF)
        if m32 and m100 and _best(m32) != _best(m100):
            pick[i] = sorted({_best(m32), _best(m100)})
    run_tasks(tasks_for(list(pick), "W3", REF, pick), "D")

    say(f"\n== Pilota delle sorelle ({time.strftime('%d/%m %H:%M')}), {(time.time() - t0) / 60:.0f} min")
    report(run, roots, rows, say)


if __name__ == "__main__":
    main()
