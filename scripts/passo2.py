#!/usr/bin/env python
"""Passo 2 (20/11, docs/bot/RETE.md): un valore che impara a confrontare le
mosse, dalle mosse sorelle giocate fino alla fine (il pilota: le differenze
si ripetono su mondi nuovi, 32 iterazioni bastano).

1. radici: da partite diverse del bot a mano contro se stesso (32 iterazioni,
   Evelynn A contro Kha'Zix B), una decisione del turno principale per
   partita, scelta tra quelle raggiunte: bilanciate per chi comincia, per chi
   decide e per terzo della partita (inizio, metà, fine delle sue decisioni).
   Gruppi per seed, fissati prima: allenamento 1.000 (seed 40000-40999),
   scelta dell'epoca 200 (41000-41199), prova 400 (41200-41599). In ogni
   radice fino a tre sorelle come nel pilota (scripts/diag/pilota_sorelle.py).
2. etichette (allenamento e scelta dell'epoca): ogni sorella in 8 mondi, i
   due bot a 32 iterazioni fino alla fine.
3. allena: riftbound/ai/residual.py, table_value + una correzione che parte da
   zero; impara il risultato di ogni sorella e la differenza tra sorelle.
   Tiene l'epoca con l'errore più basso sulle differenze delle 200.
4. soglia, sulle 400 di prova mai usate: il bot a mano e il bot col nuovo
   valore scelgono la mossa (0,4 s di CPU ciascuno, come in arena); dove
   scelgono diversamente, le due mosse in 16 mondi nuovi col bot a 100
   iterazioni. G = media per radice (scelta nuova - scelta del bot), 0 dove
   coincidono. Regola fissata prima (revisione esterna): G >= +0,02 e limite
   inferiore dell'IC 95% sopra 0 -> si fa l'arena; altrimenti questa ricetta
   si ferma.

Riprende da dove si era fermato; un file STOP nella cartella lo ferma.

  uv run --extra rl python scripts/passo2.py tutto --run-dir runs/passo2
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/diag"))

import bootstrap_net as B  # noqa: E402  (EVE, KHA, MAX_TURNS, _init, _mean_ci)
import pilota_sorelle as P  # noqa: E402  (_siblings, play_forced)

SPLITS = {"allenamento": (40_000, 1000), "epoca": (41_000, 200), "prova": (41_200, 400)}
CHEAP, REF = 32, 100
LABEL_WORLDS, GATE_WORLDS = 8, 16
BUDGET = 0.4
G_MIN = 0.02


def _seed(split: str, i: int) -> int:
    return SPLITS[split][0] + i


def _path(run: Path, split: str, i: int) -> Path:
    return run / "radici" / split / f"r{i:04d}.pkl"


# ------------------------------------------------------------- 1. roots

def _root(task):
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.game_factory import build_game
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    split, i = task
    seed = _seed(split, i)
    rng = random.Random(seed)
    starter = "a" if i % 2 == 0 else "b"
    side = "A" if (i // 2) % 2 == 0 else "B"
    phase = (i // 4) % 3
    gs = build_game(game_seed=seed, deck_a_path=B.EVE, deck_b_path=B.KHA, ai_a=None, ai_b=None,
                    max_turns=B.MAX_TURNS, first_player=starter)
    snaps: list = []

    class Rec(HandwrittenAgent):
        def decide_action(self, opponent, cards_played: int = 0):
            if len(legal_actions(self.loop, DecisionPoint.TURN_ACTION, self.player.name)) >= 2:
                snaps.append((pickle.dumps(self.gs.clone()), cards_played, self.gs.turn))
            return super().decide_action(opponent, cards_played)

    for seat in ("A", "B"):
        p = gs.get_player(seat)
        cls = Rec if seat == side else HandwrittenAgent
        p.agent = cls(p, iterations=CHEAP, rng=random.Random(seed * 2 + (seat == "B")))
    GameLoop(gs).start()
    if not snaps:
        return None
    n = len(snaps)
    third = snaps[phase * n // 3:(phase + 1) * n // 3] or snaps
    order = list(range(len(third)))
    rng.shuffle(order)
    for x in order[:6]:
        blob, cp, turn = third[x]
        state = pickle.loads(blob)
        sib = P._siblings(state, side, cp, rng)
        if sib is not None:
            acts, labels, kinds, q = sib
            return {"state": state, "side": side, "cards_played": cp, "turn": turn, "split": split,
                    "index": i, "seed": seed, "starter": starter, "phase": phase, "decisions": n,
                    "siblings": acts, "labels": labels, "kinds": kinds, "q": q,
                    "deck": "Evelynn" if side == "A" else "Kha'Zix"}
    return None


# ------------------------------------------------------------- 2. labels

def _label(task):
    path, split, i, j, k = task
    d = pickle.load(open(path, "rb"))
    out = P.play_forced(d, d["siblings"][j], 1_000_000 + d["seed"] * 64 + k, CHEAP)
    out.update({"split": split, "i": i, "j": j, "k": k})
    return out


# ------------------------------------------------------------- 3. training

def _child(d: dict, j: int):
    """The position after sibling j at the real root (baseline inner choices),
    as the decider sees it: (encoded observation, table_value)."""
    from riftbound.ai.encoding import encode_observation
    from riftbound.ai.handwritten import table_value
    from riftbound.core.decisions import Observation
    from riftbound.core.loop import GameLoop
    s = d["state"].clone()
    s.rng = random.Random(0)
    loop = GameLoop(s)
    loop._apply_action(s.get_player(d["side"]), d["siblings"][j], cards_played_this_turn=d["cards_played"])
    loop._recompute_passives()
    obs = Observation.from_state(s, d["side"])
    return encode_observation(obs), table_value(obs)


def _examples(run: Path, split: str, labels: list):
    """Arrays for the roots of `split` with all their siblings labelled:
    X, tv, v (2 * mean score - 1), the root of each row, the sibling pairs."""
    import numpy as np
    by: dict = {}
    for r in labels:
        if r["split"] == split and r["score"] is not None:
            by.setdefault((r["i"], r["j"]), []).append(r["score"])
    X, tv, v, root, pairs = [], [], [], [], []
    for f in sorted((run / "radici" / split).glob("r*.pkl")):
        d = pickle.load(open(f, "rb"))
        i, js = d["index"], range(len(d["siblings"]))
        if any(len(by.get((i, j), [])) < LABEL_WORLDS for j in js):
            continue
        start = len(v)
        for j in js:
            x, t = _child(d, j)
            X.append(x)
            tv.append(t)
            v.append(2 * sum(by[(i, j)]) / len(by[(i, j)]) - 1)
            root.append(i)
        pairs += [(start + a, start + b) for a in js for b in js if a < b]
    return (np.asarray(X, dtype=np.float32), np.asarray(tv, dtype=np.float32),
            np.asarray(v, dtype=np.float32), np.asarray(root), np.asarray(pairs, dtype=np.int64))


def train(run: Path, labels: list, say, epochs: int = 200, pair_weight: float = 2.0) -> None:
    import numpy as np
    import torch
    from riftbound.ai.net import save_checkpoint
    from riftbound.ai.residual import combine, make_net
    torch.manual_seed(0)
    tr, va = _examples(run, "allenamento", labels), _examples(run, "epoca", labels)
    say(f"3. Allenamento: {len(set(tr[3]))} radici ({len(tr[2])} posizioni) per allenare, "
        f"{len(set(va[3]))} ({len(va[2])}) per scegliere l'epoca")
    net = make_net()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)

    def tensors(data):
        X, tv, v, root, pairs = data
        return (torch.as_tensor(X), torch.as_tensor(tv), torch.as_tensor(v), root, torch.as_tensor(pairs))

    T, V = tensors(tr), tensors(va)

    def losses(data, train_mode=False):
        X, tv, v, _, pairs = data
        net.train(train_mode)
        _, r = net(X)
        pred = combine(tv, r.squeeze(1))
        a = ((pred - v) ** 2).mean()
        p = (((pred[pairs[:, 0]] - pred[pairs[:, 1]]) - (v[pairs[:, 0]] - v[pairs[:, 1]])) ** 2).mean()
        return a, p, pred

    def choice_gain(data, pred):
        """Mean over roots of (label of the sibling the value would pick - label of
        table_value's pick), in win points: an in-sample look at G."""
        X, tv, v, root, _ = data
        gain, n = 0.0, 0
        for i in set(root.tolist()):
            idx = np.where(root == i)[0]
            gain += float(v[idx[int(np.argmax(pred[idx]))]] - v[idx[int(np.argmax(tv[idx]))]]) / 2
            n += 1
        return gain / max(1, n)

    with torch.no_grad():
        a0, p0, _ = losses(V)
    say(f"   solo table_value, epoca: errore sul risultato {a0:.4f}, sulle differenze {p0:.4f}")
    roots = sorted(set(tr[3].tolist()))
    rows_of = {i: np.where(tr[3] == i)[0] for i in roots}
    best = (float("inf"), -1, None)
    for ep in range(1, epochs + 1):
        random.Random(ep).shuffle(roots)
        for b in range(0, len(roots), 64):
            idx = np.concatenate([rows_of[i] for i in roots[b:b + 64]])
            remap = {int(g): n for n, g in enumerate(idx)}
            pairs = [(remap[int(x)], remap[int(y)]) for x, y in tr[4] if int(x) in remap]
            batch = (T[0][idx], T[1][idx], T[2][idx], None, torch.as_tensor(pairs, dtype=torch.long))
            a, p, _ = losses(batch, train_mode=True)
            loss = a + pair_weight * p
            opt.zero_grad()
            loss.backward()
            opt.step()
        with torch.no_grad():
            a, p, pred = losses(V)
        if p.item() < best[0]:
            best = (p.item(), ep, {k: t.clone() for k, t in net.state_dict().items()})
            best_line = (f"   epoca {ep}: errore sul risultato {a.item():.4f}, sulle differenze {p.item():.4f}; "
                         f"guadagno di scelta (etichette a 8 mondi) {choice_gain(va, pred.numpy()):+.3f}")
    net.load_state_dict(best[2])
    save_checkpoint(net, run / "valore.pt")
    say(f"   tenuta l'epoca {best[1]} di {epochs}:")
    say(best_line)


# ------------------------------------------------------------- 4. the gate

_NETS: dict = {}


def _net(path: str):
    if path not in _NETS:
        import torch
        from riftbound.ai.net import load_checkpoint
        _NETS[path] = load_checkpoint(path, device=torch.device("cpu")).eval()
    return _NETS[path]


def _choose(task):
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.ai.residual import ResidualAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    path, i, ckpt = task
    d = pickle.load(open(path, "rb"))
    out = {"i": i}
    for who in ("bot", "nuovo"):
        s = d["state"].clone()
        p = s.get_player(d["side"])
        rng = random.Random(d["seed"] * 7 + (who == "nuovo"))
        p.agent = ResidualAgent(p, _net(ckpt), rng=rng, budget=BUDGET) if who == "nuovo" \
            else HandwrittenAgent(p, rng=rng, budget=BUDGET)
        GameLoop(s)
        legal = legal_actions(p.agent.loop, DecisionPoint.TURN_ACTION, d["side"])
        root = p.agent.search(DecisionPoint.TURN_ACTION, legal, cards_played=d["cards_played"])
        out[who] = list(p.agent._play(root, d["side"]))
    return out


def _gate_play(task):
    path, i, who, action, k = task
    d = pickle.load(open(path, "rb"))
    out = P.play_forced(d, tuple(action), 2_000_000 + d["seed"] * 64 + k, REF)
    out.update({"i": i, "who": who, "k": k})
    return out


# ------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("radici", "etichette", "allena", "soglia", "tutto"))
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs/passo2")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--scale", type=float, default=1.0, help="solo per provarlo: frazione delle radici")
    ap.add_argument("--epochs", type=int, default=200)
    args = ap.parse_args()
    run = args.run_dir
    run.mkdir(parents=True, exist_ok=True)
    stop = run / "STOP"
    sizes = {s: max(1, round(n * args.scale)) for s, (_, n) in SPLITS.items()}
    steps = ("radici", "etichette", "allena", "soglia") if args.step == "tutto" else (args.step,)

    def say(text: str) -> None:
        print(text, flush=True)
        with open(run / "PASSO2.txt", "a") as f:
            f.write(text + "\n")

    def pooled(fn, tasks, out_path, name):
        rows = [json.loads(x) for x in open(out_path)] if out_path.exists() else []
        if not tasks:
            return rows
        print(f"{name}: {len(tasks)} da fare", flush=True)
        t1 = time.time()
        with Pool(args.workers, initializer=B._init) as pool, open(out_path, "a") as out:
            for n, r in enumerate(pool.imap_unordered(fn, tasks, chunksize=1), 1):
                out.write(json.dumps(r) + "\n")
                out.flush()
                rows.append(r)
                if n % 200 == 0:
                    print(f"   ... {n}/{len(tasks)}, {(time.time() - t1) / 60:.0f} min", flush=True)
                if stop.exists():
                    pool.terminate()
                    sys.exit("Fermato (STOP): rilanciato, riprende.")
        return rows

    def roots_of(split):
        return {i: _path(run, split, i) for i in range(sizes[split]) if _path(run, split, i).exists()}

    t0 = time.time()
    say(f"\n== Passo 2 ({time.strftime('%d/%m %H:%M')}): {', '.join(steps)}")

    if "radici" in steps:
        todo = [(s, i) for s in SPLITS for i in range(sizes[s])
                if not _path(run, s, i).exists() and not _path(run, s, i).with_suffix(".none").exists()]
        if todo:
            print(f"Radici da preparare: {len(todo)}", flush=True)
            with Pool(args.workers, initializer=B._init) as pool:
                for (s, i), d in zip(todo, pool.imap(_root, todo)):
                    _path(run, s, i).parent.mkdir(parents=True, exist_ok=True)
                    if d is None:
                        _path(run, s, i).with_suffix(".none").touch()
                    else:
                        pickle.dump(d, open(_path(run, s, i), "wb"))
                    if stop.exists():
                        pool.terminate()
                        sys.exit("Fermato (STOP).")
        for s in SPLITS:
            ds = [pickle.load(open(p, "rb")) for p in roots_of(s).values()]
            say(f"1. {s}: {len(ds)} radici su {sizes[s]}; turni {min((d['turn'] for d in ds), default=0)}-"
                f"{max((d['turn'] for d in ds), default=0)}, mediana "
                f"{sorted(d['turn'] for d in ds)[len(ds) // 2] if ds else 0}; tre sorelle in "
                f"{sum(len(d['siblings']) == 3 for d in ds)}")

    lab_path = run / "etichette.jsonl"
    labels = [json.loads(x) for x in open(lab_path)] if lab_path.exists() else []
    if "etichette" in steps:
        done = {(r["split"], r["i"], r["j"], r["k"]) for r in labels}
        tasks = []
        for s in ("allenamento", "epoca"):
            for i, p in roots_of(s).items():
                d = pickle.load(open(p, "rb"))
                tasks += [(str(p), s, i, j, k) for j in range(len(d["siblings"])) for k in range(LABEL_WORLDS)
                          if (s, i, j, k) not in done]
        labels = pooled(_label, tasks, lab_path, "Etichette")
        c = [r["cpu"] for r in labels if r.get("cpu")]
        say(f"2. etichette: {len(labels)} partite fino alla fine, {sum(c) / max(1, len(c)):.1f} s di CPU in "
            f"media; fallite {sum(r['score'] is None for r in labels)}")

    if "allena" in steps:
        train(run, labels, say, epochs=args.epochs)

    if "soglia" in steps:
        ckpt = str(run / "valore.pt")
        test = roots_of("prova")
        ch_path = run / "scelte.jsonl"
        have = {json.loads(x)["i"] for x in open(ch_path)} if ch_path.exists() else set()
        choices = pooled(_choose, [(str(p), i, ckpt) for i, p in test.items() if i not in have],
                         ch_path, "Scelte")
        diff = {c["i"]: c for c in choices if c["bot"] != c["nuovo"]}
        g_path = run / "soglia.jsonl"
        done = {(r["i"], r["who"], r["k"]) for r in ([json.loads(x) for x in open(g_path)]
                                                     if g_path.exists() else [])}
        tasks = [(str(test[i]), i, who, c[who], k) for i, c in diff.items() for who in ("bot", "nuovo")
                 for k in range(GATE_WORLDS) if (i, who, k) not in done]
        rows = pooled(_gate_play, tasks, g_path, "Soglia")
        per: dict = {}
        for r in rows:
            if r["score"] is not None:
                per.setdefault(r["i"], {}).setdefault(r["who"], []).append(r["score"])
        gains = [0.0] * (len(choices) - len(diff))
        for i in diff:
            s = per.get(i, {})
            if len(s.get("bot", [])) and len(s.get("nuovo", [])):
                gains.append(sum(s["nuovo"]) / len(s["nuovo"]) - sum(s["bot"]) / len(s["bot"]))
        m, h = B._mean_ci(gains) if len(gains) > 1 else (0.0, float("inf"))
        say(f"4. Soglia sulle {len(choices)} radici di prova: scelte diverse in {len(diff)}; "
            f"G = {m:+.3f} ± {h:.3f} punti vittoria per radice (IC 95%: {m - h:+.3f} - {m + h:+.3f})")
        better = sum(1 for g in gains if g > 0)
        worse = sum(1 for g in gains if g < 0)
        say(f"   dove scelgono diversamente: meglio il nuovo valore in {better}, il bot in {worse}")
        ok = m >= G_MIN and m - h > 0
        verdict = "PASSA: si fa l'arena" if ok else "NON PASSA: questa ricetta si ferma"
        say(f"   Regola: {verdict} (G {m:+.3f}, serve >= +{G_MIN:.2f}; "
            f"limite inferiore {m - h:+.3f}, serve > 0)")
    say(f"   ({(time.time() - t0) / 60:.0f} min)")


if __name__ == "__main__":
    main()
