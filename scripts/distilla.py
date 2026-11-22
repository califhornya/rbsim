#!/usr/bin/env python
"""Pilota di distillazione (22/11, docs/PIANO_FORZA.md; disegno della revisione
esterna, terzo giro): la rete impara dalle scelte del bot promosso (il
maestro: la ricerca del bot a mano con i prior PPO 30.016, 0,4 s per mossa).

1. radici: partite della rete di partenza contro se stessa (campionando,
   seed 8.000.000+ per l'allenamento, 8.100.000+ per lo sviluppo), due
   decisioni del turno principale per partita, a caso tra quelle raggiunte.
   Su una copia di ogni posizione il maestro sceglie la mossa; poi la gioca
   sulla copia col suo piano (bersagli, modi), e si registrano anche le
   scelte interne che esegue. Tutto sul menu dinamico PPO, con la vista di
   chi decide. Per ogni radice anche visite e Q delle mosse del maestro.
2. allena: due studenti dagli stessi pesi di partenza, entropia incrociata
   sulla scelta del maestro: "mossa" (solo la mossa) e "interne" (mossa più
   scelte interne). Epoca scelta sull'accordo col maestro nelle radici di
   sviluppo. In runs/distilla/studente_mossa.pt e studente_interne.pt.

Le misure (studenti contro la partenza; stesso budget PPO a studenti e a un
controllo partito dagli stessi pesi; incroci) le fa scripts/distilla.command.

  uv run --extra rl python scripts/distilla.py radici
  uv run --extra rl python scripts/distilla.py allena
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

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SPLITS = {"allenamento": 8_000_000, "sviluppo": 8_100_000}
BUDGET = 0.4
_NETS: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _load(path):
    from riftbound.ai.ppo.model import load
    if path not in _NETS:
        _NETS[path] = load(path).eval()
    return _NETS[path]


def _example(gs, side, q: str, descs, chosen: int, source=None, ctx=None) -> dict:
    from riftbound.ai.encoding import card_id, encode_observation
    from riftbound.ai.ppo import features as F
    from riftbound.core.decisions import Observation
    return {"x": encode_observation(Observation.from_state(gs, side)).astype(np.float16),
            "q": F.question_of(q), "src": card_id(getattr(source, "name", None)) if source is not None else 0,
            "ctx": ctx if ctx is not None else F.context(len(descs)),
            "otype": np.array([d.type for d in descs], dtype=np.int64),
            "ocards": np.array([d.cards for d in descs], dtype=np.int64),
            "ofeats": np.stack([d.feats for d in descs]).astype(np.float16),
            "a": int(chosen), "logp": 0.0}


def _roots(task):
    """One game of the start net against itself; two of its main decisions
    labelled by the teacher."""
    from riftbound.ai.ppo import features as F
    from riftbound.ai.ppo.agent import PPOAgent, PPOChooser
    from riftbound.ai.ppo.prior_bot import PPOPriorAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.game_factory import build_game
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop, NO_MORE
    split, i, start, teacher = task
    seed = SPLITS[split] + i
    rng = random.Random(seed)
    net = _load(start)
    gs = build_game(game_seed=seed, deck_a_path=ROOT / "riftbound/data/decks/competitive_evelynn.json",
                    deck_b_path=ROOT / "riftbound/data/decks/competitive_khazix.json", ai_a=None, ai_b=None,
                    max_turns=40, first_player="a" if i % 2 == 0 else "b")
    snaps: list = []

    class Rec(PPOAgent):
        def decide_action(self, opponent, cards_played: int = 0):
            if len(legal_actions(self.loop, DecisionPoint.TURN_ACTION, self.player.name)) >= 2:
                snaps.append((pickle.dumps(self.gs.clone()), self.player.name, cards_played, self.gs.turn))
            return super().decide_action(opponent, cards_played)

    for seat in ("A", "B"):
        gs.get_player(seat).agent = Rec(gs.get_player(seat), net, sample=True, seed=seed * 2 + (seat == "B"))
    loop = GameLoop(gs)
    loop.chooser = PPOChooser(gs)
    loop.start()
    out = []
    picks = rng.sample(range(len(snaps)), min(2, len(snaps)))
    tnet = _load(teacher)
    for k in picks:
        blob, side, cp, turn = snaps[k]
        s = pickle.loads(blob)
        p = s.get_player(side)
        p.agent = PPOPriorAgent(p, tnet, rng=random.Random(seed * 7 + k), budget=BUDGET)
        tl = GameLoop(s)
        legal = legal_actions(tl, DecisionPoint.TURN_ACTION, side)
        descs = [F.describe_action(tl, side, a) for a in legal]
        # The student's own greedy choice, to count the teacher's changes.
        stu = PPOAgent(p, net, sample=False)
        stu.loop = tl
        x_choice = stu._ask("main", descs) if len(descs) > 1 else 0
        main = _example(s, side, "main", descs, 0)
        root = p.agent.search(DecisionPoint.TURN_ACTION, legal, cards_played=cp)
        move = p.agent._play(root, side)
        keys = [a.to_engine() for a in legal]
        chosen = keys.index(move) if move in keys else 0
        main["a"] = chosen
        stats = {"N": [root.children[t].N if t in root.children else 0 for t in keys],
                 "Q": [root.children[t].Q if t in root.children else None for t in keys]}
        # The teacher plays its move on the copy with its plan; its choices of
        # this side are recorded (menu, the option executed).
        inner: list = []
        plan = tl.chooser

        def logger(loop_, kind, side_, options, default, source, _plan=plan):
            got = _plan(loop_, kind, side_, options, default, source) if _plan is not None else None
            if side_ == side and len(options) > 1:
                d = [F.describe_choice(loop_, side, o) for o in options]
                ctx = F.context(len(options), up_to=any(o is NO_MORE for o in options),
                                declaring=loop_ is not tl)
                inner.append(_example(s, side, kind, d, default if got is None else got, source, ctx))
            return got
        tl.chooser = logger
        try:
            tl._apply_action(p, move, cards_played_this_turn=cp)
        except Exception:  # noqa: BLE001 — the move's label still stands
            pass
        out.append({"split": split, "seed": seed, "side": side, "turn": turn, "main": main, "inner": inner,
                    "student": int(x_choice), "stats": stats})
    return out


def roots(args) -> None:
    run = args.run_dir
    run.mkdir(parents=True, exist_ok=True)
    for split, n in (("allenamento", args.partite), ("sviluppo", args.partite_sviluppo)):
        path = run / f"radici_{split}.pkl"
        if path.exists():
            continue
        t0 = time.time()
        with Pool(args.workers, initializer=_init) as pool:
            rows = [r for out in pool.imap_unordered(_roots, [(split, i, args.partenza, args.maestro)
                                                               for i in range(n)], chunksize=4) for r in out]
        pickle.dump(rows, open(path, "wb"))
        changed = sum(r["student"] != r["main"]["a"] for r in rows)
        print(f"{split}: {len(rows)} radici da {n} partite, scelte interne del maestro "
              f"{sum(len(r['inner']) for r in rows)}; il maestro cambia la mossa dello studente in "
              f"{changed} ({changed / max(1, len(rows)):.0%}); {(time.time() - t0) / 60:.0f} min", flush=True)


def train(args) -> None:
    import torch
    from riftbound.ai.ppo.model import load, save
    from riftbound.ai.ppo.train import evaluate, tensors
    torch.manual_seed(0)
    run = args.run_dir
    tr = pickle.load(open(run / "radici_allenamento.pkl", "rb"))
    dv = pickle.load(open(run / "radici_sviluppo.pkl", "rb"))

    def acc(net, exs):
        if not exs:
            return float("nan")
        with torch.no_grad():
            t = tensors(exs)
            logits, _ = net(t["x"], t["q"], t["src"], t["ctx"], t["otype"], t["ocards"], t["ofeats"], t["omask"])
            return float((logits.argmax(1) == t["a"]).float().mean())

    dv_main = [r["main"] for r in dv]
    dv_inner = [e for r in dv for e in r["inner"]]
    base = load(args.partenza)
    lines = [f"Distillazione ({time.strftime('%d/%m %H:%M')}): {len(tr)} radici di allenamento, {len(dv)} di "
             f"sviluppo; partenza: accordo col maestro sullo sviluppo {acc(base, dv_main):.3f} (mosse), "
             f"{acc(base, dv_inner):.3f} (scelte interne)"]
    for variant in ("mossa", "interne"):
        exs = [r["main"] for r in tr] + ([e for r in tr for e in r["inner"]] if variant == "interne" else [])
        net = load(args.partenza)
        opt = torch.optim.Adam(net.parameters(), lr=args.lr)
        t = tensors(exs)
        best = (acc(net, dv_main), 0, {k: v.clone() for k, v in net.state_dict().items()})
        for ep in range(1, args.epoche + 1):
            net.train()
            perm = torch.randperm(len(exs))
            for b in range(0, len(exs), 256):
                idx = perm[b:b + 256]
                logp, _, _ = evaluate(net, t, idx)
                loss = -logp.mean()
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
            net.eval()
            a = acc(net, dv_main)
            if a > best[0]:
                best = (a, ep, {k: v.clone() for k, v in net.state_dict().items()})
        net.load_state_dict(best[2])
        save(net, run / f"studente_{variant}.pt")
        lines.append(f"   studente {variant}: {len(exs)} esempi, epoca {best[1]}; accordo sullo sviluppo "
                     f"{best[0]:.3f} (mosse), {acc(net, dv_inner):.3f} (scelte interne)")
    text = "\n".join(lines)
    print(text)
    with open(run / "DISTILLA.txt", "a") as f:
        f.write(text + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("radici", "allena"))
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs/distilla")
    ap.add_argument("--partenza", default=str(ROOT / "runs/ppo1/ckpt_030016.pt"))
    ap.add_argument("--maestro", default=str(ROOT / "runs/ppo1/ckpt_030016.pt"),
                    help="i prior PPO del maestro (la sua ricerca è quella del bot a mano)")
    ap.add_argument("--partite", type=int, default=1000, help="partite per le radici di allenamento (2 ciascuna)")
    ap.add_argument("--partite-sviluppo", type=int, default=200)
    ap.add_argument("--epoche", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()
    if args.step == "radici":
        roots(args)
    else:
        train(args)


if __name__ == "__main__":
    main()
