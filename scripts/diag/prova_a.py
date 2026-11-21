#!/usr/bin/env python
"""Prova A (21/11, docs/PIANO_FORZA.md): una ricerca che gioca davvero tutto il
turno dell'avversario sceglie mosse migliori del bot a mano?

Radici: decisioni del turno principale da partite nuove del bot a mano contro
se stesso (come scripts/passo2.py: Evelynn A contro Kha'Zix B, bilanciate per
chi comincia, chi decide e terzo della partita). Gruppi fissati prima:
sviluppo 128 (seed 50000-50127), conferma 400 (seed 51000-51399).

Candidate: le sorelle del passo 2: la mossa del bot (100 iterazioni), la
migliore alternativa per Q, una mossa legale diversa a caso.

La ricerca A: ogni candidata in 16 mondi condivisi (determinize dal punto di
vista di chi decide); forzata la mossa (scelte interne al baseline), i due
bot a mano a 16 iterazioni (ognuno vede solo ciò che sa) finiscono il nostro
turno, giocano tutto il turno dell'avversario, fino alla nostra prossima
decisione del turno principale: lì table_value dal nostro lato (+1 / 0 / -1
se la partita è finita); con --arresto fine, fino alla fine della partita.
Si sceglie la candidata con la media più alta (a
parità, la mossa del bot).

Giudizio: dove A sceglie diversamente dal bot, le due mosse forzate su 16
mondi nuovi e comuni, giocate fino alla fine dal bot a mano a 32 iterazioni
(i piloti del pilota e del passo 2). G = media per radice (scelta di A -
mossa del bot), 0 dove coincidono.

Regola fissata prima (revisione esterna): G >= +0,02 e limite inferiore
dell'IC 95% sopra 0 -> passa; limite superiore sotto +0,02 -> la ricetta si
chiude; altrimenti incerto. Sviluppo per stimare la varianza e guardare;
conferma, a variante congelata, per decidere.

Riprende da dove si era fermato; un file STOP nella cartella lo ferma.

  uv run python scripts/diag/prova_a.py --gruppo sviluppo --arresto prossima
  uv run python scripts/diag/prova_a.py --gruppo sviluppo --arresto fine
"""
from __future__ import annotations

import argparse
import json
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
sys.path.insert(0, str(ROOT / "scripts/diag"))

import bootstrap_net as B  # noqa: E402  (KNOWN, POSITIONS, _init, _mean_ci)
import passo2 as P2  # noqa: E402  (_root)
import pilota_sorelle as P  # noqa: E402  (play_forced)

GROUPS = {"sviluppo": (50_000, 128), "conferma": (51_000, 400)}
WORLDS, ROLL_ITERS = 16, 16
JUDGE_WORLDS, JUDGE_ITERS = 16, 32
G_MIN = 0.02


class _Reached(BaseException):
    """Our next main-turn decision (not an Exception: the loop won't catch it)."""


def look_past(d: dict, action, seed: int, stop: str = "prossima") -> dict:
    """Root `d`, world `seed`: `action` forced, then both hand-written bots at
    ROLL_ITERS through the rest of our turn and the whole opponent's turn, up
    to our next main decision: table_value from our side there (stop
    "prossima"); or on to the end of the game (stop "fine")."""
    from riftbound.ai.handwritten import HandwrittenAgent, table_value
    from riftbound.core.decisions import DecisionPoint, Observation
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import determinize
    side = d["side"]
    gs = d["state"].clone()
    gs.rng = random.Random(seed)
    determinize(gs, observer=side, rng=gs.rng)
    turn0 = gs.turn

    class Me(HandwrittenAgent):
        first = True

        def decide_action(self, opponent, cards_played: int = 0):
            if self.first:
                self.first = False
                self._ensure_rng()
                self._ensure_fallback()
                self._release_forced()
                legal = [a.to_engine() for a in legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)]
                if action not in legal:
                    raise RuntimeError(f"mossa non legale in questo mondo: {action}")
                return action
            if stop == "prossima" and self.gs.turn != turn0:
                raise _Reached()
            return super().decide_action(opponent, cards_played)

    other = gs.other(side)
    for p, cls, k in ((gs.get_player(side), Me, 1), (gs.get_player(other), HandwrittenAgent, 2)):
        p.agent = cls(p, iterations=ROLL_ITERS, rng=random.Random(seed * 2 + k))
        p.agent.reaction_iterations = ROLL_ITERS
    t0 = time.process_time()
    try:
        res = GameLoop(gs).resume_to_completion()
        v = 1.0 if res.winner == side else 0.0 if res.winner == "DRAW" else -1.0
    except _Reached:
        v = table_value(Observation.from_state(gs, side))
    except RuntimeError as e:
        return {"v": None, "err": str(e)}
    return {"v": v, "cpu": round(time.process_time() - t0, 3), "turns": gs.turn - turn0}


def _look(task):
    path, i, j, k, stop = task
    d = pickle.load(open(path, "rb"))
    out = look_past(d, d["siblings"][j], 3_000_000 + d["seed"] * 64 + k, stop)
    out.update({"i": i, "j": j, "k": k})
    return out


def _judge(task):
    path, i, who, j, k = task
    d = pickle.load(open(path, "rb"))
    out = P.play_forced(d, d["siblings"][j], 4_000_000 + d["seed"] * 64 + k, JUDGE_ITERS)
    out.update({"i": i, "who": who, "k": k})
    return out


def _known(task):
    name, which, k, stop = task
    d = pickle.load(open(B.POSITIONS / f"{name}.pkl", "rb"))
    out = look_past(d, d[which], 5_000_000 + k, stop)
    out.update({"name": name, "which": which, "k": k})
    return out


def choice(vals: dict) -> int:
    """The sibling A plays: the highest mean over the worlds (ties: the bot's move, j = 0)."""
    means = {j: sum(v) / len(v) for j, v in vals.items() if v}
    return max(sorted(means), key=lambda j: (means[j], -j)) if means else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gruppo", choices=tuple(GROUPS), default="sviluppo")
    ap.add_argument("--arresto", choices=("prossima", "fine"), default="prossima",
                    help="dove si valuta: alla nostra prossima decisione (table_value) o a fine partita")
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs/prova_a")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--radici", type=int, default=None, help="solo per provarlo: meno radici")
    args = ap.parse_args()
    group = args.gruppo
    seed0, n = GROUPS[group]
    n = args.radici or n
    run = args.run_dir / args.arresto / group
    rdir = args.run_dir / "radici" / group
    rdir.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    stop = run / "STOP"

    def say(text: str) -> None:
        print(text, flush=True)
        with open(run / "PROVA_A.txt", "a") as f:
            f.write(text + "\n")

    def pooled(fn, tasks, out_path, name):
        rows = [json.loads(x) for x in open(out_path)] if out_path.exists() else []
        if not tasks:
            return rows
        print(f"{name}: {len(tasks)} da fare", flush=True)
        t1 = time.time()
        with Pool(args.workers, initializer=B._init) as pool, open(out_path, "a") as out:
            for m, r in enumerate(pool.imap_unordered(fn, tasks, chunksize=1), 1):
                out.write(json.dumps(r) + "\n")
                out.flush()
                rows.append(r)
                if m % 200 == 0:
                    print(f"   ... {m}/{len(tasks)}, {(time.time() - t1) / 60:.0f} min", flush=True)
                if stop.exists():
                    pool.terminate()
                    sys.exit("Fermato (STOP): rilanciato, riprende.")
        return rows

    t0 = time.time()
    say(f"\n== Prova A, {group} ({time.strftime('%d/%m %H:%M')}): turno avversario intero, "
        f"{WORLDS} mondi, bot a {ROLL_ITERS} iterazioni per le continuazioni, valutazione "
        f"{'alla nostra prossima decisione (table_value)' if args.arresto == 'prossima' else 'a fine partita'}")

    # 1. roots
    todo = [i for i in range(n) if not (rdir / f"r{i:04d}.pkl").exists() and not (rdir / f"r{i:04d}.none").exists()]
    if todo:
        print(f"Radici da preparare: {len(todo)}", flush=True)
        with Pool(args.workers, initializer=B._init) as pool:
            for i, d in zip(todo, pool.imap(P2._root, [(group, i, seed0 + i) for i in todo])):
                if d is None:
                    (rdir / f"r{i:04d}.none").touch()
                else:
                    pickle.dump(d, open(rdir / f"r{i:04d}.pkl", "wb"))
                if stop.exists():
                    pool.terminate()
                    sys.exit("Fermato (STOP).")
    roots = {i: rdir / f"r{i:04d}.pkl" for i in range(n) if (rdir / f"r{i:04d}.pkl").exists()}
    sib = {i: len(pickle.load(open(p, "rb"))["siblings"]) for i, p in roots.items()}
    say(f"1. radici: {len(roots)} su {n}; candidate per radice: "
        + ", ".join(f"{c}: {sum(v == c for v in sib.values())}" for c in (2, 3)))

    # 0. the known positions, only to read (outside the estimate)
    kn = pooled(_known, [(name, w, k, args.arresto) for name in B.KNOWN for w in ("ref", "reply")
                         for k in range(WORLDS)],
                run / "note.jsonl", "Posizioni note") if group == "sviluppo" else []
    for name, (right, words) in B.KNOWN.items():
        means = {}
        for w in ("ref", "reply"):
            vs = [r["v"] for r in kn if r["name"] == name and r["which"] == w and r["v"] is not None]
            if vs:
                means[w] = sum(vs) / len(vs)
        if len(means) == 2:
            pick = max(("ref", "reply"), key=lambda w: means[w])
            say(f"   {name}: giusta {words}; A sceglie {'GIUSTO' if pick == right else 'SBAGLIATO'} "
                f"(ref {means['ref']:+.3f}, reply {means['reply']:+.3f})")

    # 2. the search A
    def done_keys(path, key):
        return {key(json.loads(x)) for x in open(path)} if path.exists() else set()

    have = done_keys(run / "ricerca.jsonl", lambda r: (r["i"], r["j"], r["k"]))
    looks = pooled(_look, [(str(p), i, j, k, args.arresto) for i, p in roots.items() for j in range(sib[i])
                           for k in range(WORLDS) if (i, j, k) not in have],
                   run / "ricerca.jsonl", "Ricerca A")
    vals: dict = {}
    for r in looks:
        if r["v"] is not None:
            vals.setdefault(r["i"], {}).setdefault(r["j"], []).append(r["v"])
    chosen = {i: choice(vals.get(i, {})) for i in roots}
    diff = {i: c for i, c in chosen.items() if c != 0}
    c = [r["cpu"] for r in looks if r.get("cpu") is not None]
    say(f"2. ricerca A: {len(looks)} continuazioni, {sum(c) / max(1, len(c)):.2f} s di CPU in media "
        f"({sum(c) * WORLDS / max(1, len(c)) * 3:.0f} s per radice con 3 candidate); sceglie diversamente "
        f"dal bot in {len(diff)} radici su {len(roots)} (l'alternativa in "
        f"{sum(v == 1 for v in diff.values())}, la mossa a caso in {sum(v == 2 for v in diff.values())})")

    # 3. the judgment
    have = done_keys(run / "giudizio.jsonl", lambda r: (r["i"], r["who"], r["k"]))
    judged = pooled(_judge, [(str(roots[i]), i, who, j, k) for i, ja in diff.items()
                             for who, j in (("A", ja), ("bot", 0)) for k in range(JUDGE_WORLDS)
                             if (i, who, k) not in have],
                    run / "giudizio.jsonl", "Giudizio")
    per: dict = {}
    for r in judged:
        if r["score"] is not None:
            per.setdefault(r["i"], {}).setdefault(r["who"], []).append(r["score"])
    gains = [0.0] * (len(roots) - len(diff))
    for i in diff:
        s = per.get(i, {})
        if s.get("A") and s.get("bot"):
            gains.append(sum(s["A"]) / len(s["A"]) - sum(s["bot"]) / len(s["bot"]))
    m, h = B._mean_ci(gains) if len(gains) > 1 else (0.0, float("inf"))
    better = sum(1 for g in gains if g > 0)
    worse = sum(1 for g in gains if g < 0)
    say(f"3. giudizio ({JUDGE_WORLDS} mondi nuovi, bot a {JUDGE_ITERS} fino alla fine): "
        f"G = {m:+.3f} ± {h:.3f} per radice (IC 95%: {m - h:+.3f} - {m + h:+.3f}); "
        f"meglio A in {better}, il bot in {worse}")
    if m >= G_MIN and m - h > 0:
        verdict = "PASSA"
    elif m + h < G_MIN:
        verdict = "NON PASSA: la ricetta si chiude"
    else:
        verdict = "INCERTO"
    say(f"   Regola: {verdict} (G {m:+.3f}, serve >= +{G_MIN:.2f} con limite inferiore > 0; "
        f"si chiude se il limite superiore {m + h:+.3f} è sotto +{G_MIN:.2f})")
    say(f"   ({(time.time() - t0) / 60:.0f} min)")


if __name__ == "__main__":
    main()
