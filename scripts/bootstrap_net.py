#!/usr/bin/env python
"""The net from the hand-written bot, then measured (docs/bot/RETE.md).

1. data: the hand-written bot (riftbound/ai/handwritten.py, 100 iterations)
   plays itself, Evelynn against Kha'Zix, the seats alternating. A share
   (--keep) of its decisions with a choice becomes an example: the position
   from the decider's view, the move it played, the game's outcome, and the
   hand-written value of the position (to compare). In --run-dir/data/, one
   file per CHUNK games; launched again it goes on where it stopped. A file
   named STOP in --run-dir stops it (the games under way are lost).
2. train: the net learns the move (cross-entropy) and the outcome (squared
   error); a tenth of the games is held out. Keeps the epoch with the best
   value error on the held-out games: --run-dir/net_boot.pt.
3. measure: on the held-out games, how well the net and the hand-written
   value predict the outcome; the first move in five positions whose right
   move is known (docs/bot/posizioni/, docs/bot/TURNO_AVVERSARIO.md); pairs
   of games against the hand-written bot at the same CPU time per move; 200
   games against simple_trade as handwritten_value.py plays them (0.80).
   Everything in --run-dir/RISULTATI.txt.

  uv run --extra rl python scripts/bootstrap_net.py all --run-dir runs/boot1
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
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EVE = ROOT / "riftbound/data/decks/competitive_evelynn.json"
KHA = ROOT / "riftbound/data/decks/competitive_khazix.json"
POSITIONS = ROOT / "docs/bot/posizioni"
MAX_TURNS = 40
CHUNK = int(os.environ.get("BOOT_CHUNK", "40"))
SEED0 = 100_000
# Positions with a known right first move (TURNO_AVVERSARIO.md): which of the
# two saved moves, and in words.
KNOWN = {
    "s3012_B_t07_05": ("reply", "Zed a difendere BF0, non contro BF1 (0,92 contro 0,47)"),
    "s3090_A_t03_01": ("ref", "Evelynn Entrancing conquista BF0 (0,97 contro 0,72)"),
    "s3076_B_t03_01": ("ref", "Evelynn Entrancing conquista BF1 (0,93 contro 0,82)"),
    "s3048_A_t03_01": ("ref", "Evelynn Entrancing conquista BF0 (0,97 contro 0,90)"),
}


def _init():
    from riftbound.compute import be_gentle
    be_gentle()
    try:
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass


def _say(run_dir: Path, text: str) -> None:
    print(text, flush=True)
    with open(run_dir / "RISULTATI.txt", "a") as f:
        f.write(text + "\n")


# --- 1. data -------------------------------------------------------------------

def _data_game(seed: int) -> dict:
    from riftbound.ai.encoding import action_to_index, encode_observation, legal_mask
    from riftbound.ai.handwritten import HandwrittenAgent, table_value
    from riftbound.core.decisions import DecisionPoint, Observation
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop

    keep = float(os.environ.get("BOOT_KEEP", "0.3"))
    rows: list = []

    class Recorder(HandwrittenAgent):
        def _conclude(self, root, side, legal, point=DecisionPoint.TURN_ACTION):
            obs = Observation.from_state(self.gs, side)
            key = super()._conclude(root, side, legal, point)
            if len(legal) > 1 and self.keep_rng.random() < keep:
                n_bf = len(self.gs.battlefields)
                idx = action_to_index(key, n_bf)
                if idx is not None:
                    rows.append(dict(state=encode_observation(obs).astype(np.float16), p=idx,
                                     mask=np.packbits(legal_mask(legal, n_bf)), player=side,
                                     turn=self.gs.turn, tv=table_value(obs)))
            return key

    da, db = (EVE, KHA) if seed % 2 == 0 else (KHA, EVE)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None,
                    max_turns=MAX_TURNS)
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        p.agent = Recorder(p, iterations=100, rng=random.Random(seed * 2 + (seat == "B")))
        p.agent.keep_rng = random.Random(seed * 7 + (seat == "B"))
    res = GameLoop(gs).start()
    for r in rows:
        r["z"] = 0 if res.winner == "DRAW" else (1 if res.winner == r["player"] else -1)
    return dict(seed=seed, winner=res.winner, turns=res.turns, eve="A" if seed % 2 == 0 else "B",
                rows=rows)


def _write_chunk(path: Path, games: list) -> None:
    rows = [r for g in games for r in g["rows"]]
    np.savez_compressed(
        path,
        state=np.stack([r["state"] for r in rows]) if rows else np.zeros((0, 1), np.float16),
        p=np.asarray([r["p"] for r in rows], np.int16),
        mask=np.stack([r["mask"] for r in rows]) if rows else np.zeros((0, 1), np.uint8),
        z=np.asarray([r["z"] for r in rows], np.int8),
        turn=np.asarray([r["turn"] for r in rows], np.int16),
        tv=np.asarray([r["tv"] for r in rows], np.float32),
        seed=np.asarray([g["seed"] for g in games for _ in g["rows"]], np.int32))
    with open(path.with_suffix(".json"), "w") as f:
        json.dump([{k: g[k] for k in ("seed", "winner", "turns", "eve")} for g in games], f)


def data(args) -> None:
    out = args.run_dir / "data"
    out.mkdir(parents=True, exist_ok=True)
    n_chunks = math.ceil(args.games / CHUNK)
    todo = [c for c in range(n_chunks) if not (out / f"chunk_{c:04d}.npz").exists()]
    if not todo:
        print(f"data: {n_chunks} chunks already there")
        return
    os.environ["BOOT_KEEP"] = str(args.keep)
    seeds = [SEED0 + c * CHUNK + i for c in todo for i in range(CHUNK)]
    print(f"data: {len(todo)} chunks of {CHUNK} games to play ({len(seeds)} games), {args.workers} workers",
          flush=True)
    done: dict = {}
    t0 = time.time()
    with Pool(args.workers, initializer=_init) as pool:
        for k, g in enumerate(pool.imap_unordered(_data_game, seeds), 1):
            c = (g["seed"] - SEED0) // CHUNK
            done.setdefault(c, []).append(g)
            if len(done[c]) == CHUNK:
                _write_chunk(out / f"chunk_{c:04d}.npz", sorted(done.pop(c), key=lambda g: g["seed"]))
                el = time.time() - t0
                print(f"  chunk {c} saved; {k}/{len(seeds)} games, {el / 60:.0f} min, "
                      f"about {el / k * (len(seeds) - k) / 60:.0f} min left", flush=True)
            if (args.run_dir / "STOP").exists():
                print("STOP: stopped; the saved chunks stay", flush=True)
                pool.terminate()
                sys.exit(0)


def _load(run_dir: Path) -> dict:
    files = sorted((run_dir / "data").glob("chunk_*.npz"))
    parts = [np.load(f) for f in files]
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("state", "p", "mask", "z", "turn", "tv", "seed")}
    d["held"] = (d["seed"] - SEED0) % 10 == 9                 # a tenth of the games
    games = [g for f in files for g in json.load(open(f.with_suffix(".json")))]
    return d, games


# --- 2. train ------------------------------------------------------------------

def _value_report(v, z, turn) -> str:
    out = f"{((v - z) ** 2).mean():.3f}"
    for lo, hi in ((1, 4), (5, 8), (9, 99)):
        m = (turn >= lo) & (turn <= hi)
        if m.any():
            out += f" | turni {lo}-{hi if hi < 99 else '+'}: {((v[m] - z[m]) ** 2).mean():.3f}"
    return out


def train(args) -> None:
    import torch
    from riftbound.ai.encoding import ACTION_DIM
    from riftbound.ai.net import RiftboundNet, masked_log_softmax, save_checkpoint
    torch.manual_seed(0)
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    d, games = _load(args.run_dir)
    tr, he = ~d["held"], d["held"]
    n_tr, n_he = int(tr.sum()), int(he.sum())
    _say(args.run_dir, f"\n== Allenamento ({time.strftime('%d/%m %H:%M')})\n"
         f"partite {len(games)}, esempi {len(d['z'])}: {n_tr} per allenare, {n_he} tenuti da parte "
         f"({len({int(s) for s in d['seed'][he]})} partite)")
    X = torch.as_tensor(d["state"])
    P = torch.as_tensor(d["p"].astype(np.int64))
    M = torch.as_tensor(np.unpackbits(d["mask"], axis=1)[:, :ACTION_DIM].astype(bool))
    Z = torch.as_tensor(d["z"].astype(np.float32))
    itr, ihe = np.flatnonzero(tr), np.flatnonzero(he)
    net = RiftboundNet()
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * math.ceil(n_tr / args.batch)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps, eta_min=args.lr / 100)

    @torch.no_grad()
    def evaluate(idx):
        net.eval()
        vs, ce, hit = [], 0.0, 0
        for i in range(0, len(idx), 2048):
            j = torch.as_tensor(idx[i:i + 2048])
            logits, v = net(X[j].float())
            logp = masked_log_softmax(logits, M[j])
            ce -= logp.gather(1, P[j][:, None]).sum().item()
            hit += int((logp.argmax(1) == P[j]).sum())
            vs.append(v.squeeze(1))
        return torch.cat(vs).numpy(), ce / len(idx), hit / len(idx)

    best, log = None, []
    for ep in range(1, args.epochs + 1):
        net.train()
        perm = np.random.default_rng(ep).permutation(itr)
        for i in range(0, len(perm), args.batch):
            j = torch.as_tensor(perm[i:i + args.batch])
            logits, v = net(X[j].float())
            logp = masked_log_softmax(logits, M[j])
            loss = -logp.gather(1, P[j][:, None]).mean() + ((v.squeeze(1) - Z[j]) ** 2).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
        v, ce, acc = evaluate(ihe)
        mse = float(((v - d["z"][he]) ** 2).mean())
        log.append(dict(epoch=ep, value_held=mse, policy_held=ce, acc_held=acc))
        print(f"  epoca {ep}: valore {mse:.3f}, politica {ce:.3f}, mossa del bot {acc:.0%}", flush=True)
        if best is None or mse < best[0]:
            best = (mse, ep)
            save_checkpoint(net, args.run_dir / "net_boot.pt")
    with open(args.run_dir / "train.jsonl", "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in log)
    _say(args.run_dir, f"tenuta l'epoca {best[1]} (errore del valore sulle partite tenute da parte {best[0]:.3f})")


# --- 3. measure ----------------------------------------------------------------

_NET: dict = {}


def _net(path: str):
    if path not in _NET:
        import torch
        from riftbound.ai.net import load_checkpoint
        _NET[path] = load_checkpoint(path, device=torch.device("cpu")).eval()
    return _NET[path]


def _first_move(task):
    from riftbound.ai.handwritten import HandwrittenAgent, NetAgent
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import determinize
    name, who, w, ckpt = task
    d = pickle.load(open(POSITIONS / f"{name}.pkl", "rb"))
    side = d["side"]
    gs = d["state"].clone()
    gs.rng = random.Random(10_000 + w)
    determinize(gs, observer=side, rng=gs.rng)
    p = gs.get_player(side)
    rng = random.Random(20_000 + w)
    p.agent = NetAgent(p, _net(ckpt), rng=rng) if who == "net" else HandwrittenAgent(p, rng=rng)
    GameLoop(gs)                       # binds the agent to the game
    return name, who, p.agent.decide_action(gs.get_player(gs.other(side)), d["cards_played"])


def _h2h_game(task):
    from riftbound.ai.handwritten import HandwrittenAgent, NetAgent
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    seed, net_seat, budget, ckpt = task
    gs = build_game(game_seed=seed, deck_a_path=EVE, deck_b_path=KHA, ai_a=None, ai_b=None,
                    max_turns=MAX_TURNS)
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        rng = random.Random(seed * 2 + (seat == "B"))
        p.agent = NetAgent(p, _net(ckpt), rng=rng, budget=budget) if seat == net_seat \
            else HandwrittenAgent(p, rng=rng, budget=budget)
    res = GameLoop(gs).start()
    net, hw = gs.get_player(net_seat).agent, gs.get_player(gs.other(net_seat)).agent
    s = 1.0 if res.winner == net_seat else 0.5 if res.winner == "DRAW" else 0.0
    return seed, net_seat, s, net.main_iters, hw.main_iters


def _st_game(task):
    # As scripts/diag/handwritten_value.py plays them (its seeds, decks, seats).
    from riftbound.ai.handwritten import NetAgent
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.loop import GameLoop
    seed, seat, ckpt = task
    decks = [EVE, KHA]
    r = random.Random(seed)
    d_net, d_opp = r.choice(decks), r.choice(decks)
    da, db = (d_net, d_opp) if seat == "A" else (d_opp, d_net)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None,
                    max_turns=MAX_TURNS)
    me, them = gs.get_player(seat), gs.get_player(gs.other(seat))
    me.agent = NetAgent(me, _net(ckpt), iterations=100, rng=random.Random(seed))
    them.agent = make_agent("simple_trade", them)
    res = GameLoop(gs).start()
    return 1.0 if res.winner == seat else 0.5 if res.winner == "DRAW" else 0.0


def measure(args) -> None:
    import torch
    from riftbound.ai.net import load_checkpoint
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    run_dir, ckpt = args.run_dir, str(args.run_dir / "net_boot.pt")
    _say(run_dir, f"\n== Misure ({time.strftime('%d/%m %H:%M')}), rete {ckpt}")

    # (1) who wins, predicted on the held-out games
    d, games = _load(run_dir)
    he = d["held"]
    net = load_checkpoint(ckpt, device=torch.device("cpu")).eval()
    with torch.no_grad():
        X = torch.as_tensor(d["state"][he])
        v = torch.cat([net(X[i:i + 2048].float())[1].squeeze(1) for i in range(0, len(X), 2048)]).numpy()
    z, tv, turn = d["z"][he].astype(np.float32), d["tv"][he], d["turn"][he]
    ztr, tvtr = d["z"][~he].astype(np.float32), d["tv"][~he]
    a = float((tvtr * ztr).sum() / max(1e-9, (tvtr * tvtr).sum()))   # the best scale for the hand-written value
    _say(run_dir, "1. Chi vince, previsto sulle partite tenute da parte (errore quadratico; 1 = non sapere niente):")
    _say(run_dir, f"   rete:                {_value_report(v, z, turn)}")
    _say(run_dir, f"   valore a mano:       {_value_report(tv, z, turn)}")
    _say(run_dir, f"   valore a mano × {a:.2f}: {_value_report(np.clip(a * tv, -1, 1), z, turn)}")
    c = Counter((g["eve"] == g["winner"]) if g["winner"] != "DRAW" else None for g in games)
    _say(run_dir, f"   (nelle {len(games)} partite del bot contro sé stesso Evelynn vince {c[True]}, "
                  f"Kha'Zix {c[False]}, pareggi {c[None]})")

    # (2) the first move in the known positions
    _say(run_dir, f"2. Prima mossa nelle posizioni note ({args.worlds} mondi, 100 iterazioni):")
    tasks = [(n, who, w, ckpt) for n in KNOWN for who in ("net", "bot") for w in range(args.worlds)]
    with Pool(args.workers, initializer=_init) as pool:
        moves = pool.map(_first_move, tasks)
    for name, (right_key, words) in KNOWN.items():
        pos = pickle.load(open(POSITIONS / f"{name}.pkl", "rb"))
        labels = {a.to_engine(): a.label for a in
                  legal_actions(GameLoop(pos["state"].clone()), DecisionPoint.TURN_ACTION, pos["side"])}
        right = pos[right_key]
        line = f"   {name}: giusta {words}"
        for who in ("net", "bot"):
            got = [m for n, w_, m in moves if n == name and w_ == who]
            top = Counter(labels.get(m, str(m)) for m in got).most_common(2)
            line += f"\n      {'rete' if who == 'net' else 'bot a mano'}: giusta in {sum(m == right for m in got)}/{len(got)}" \
                    f" ({'; '.join(f'{k}× {m}' for m, k in top)})"
        _say(run_dir, line)

    # (3) against the hand-written bot, the same time per move
    _say(run_dir, f"3. Contro il bot a mano, {args.pairs} coppie, {args.budget} s di CPU per mossa ciascuno:")
    tasks = [(3000 + i, seat, args.budget, ckpt) for i in range(args.pairs) for seat in ("A", "B")]
    t0 = time.time()
    with Pool(args.workers, initializer=_init) as pool:
        rows = pool.map(_h2h_game, tasks)
    s = [r[2] for r in rows]
    pairs = {}
    for seed, seat, sc, _, _ in rows:
        pairs.setdefault(seed, []).append(sc)
    ps = [sum(v) / 2 for v in pairs.values()]
    m = sum(ps) / len(ps)
    sd = math.sqrt(sum((x - m) ** 2 for x in ps) / max(1, len(ps) - 1))
    ni = [x for r in rows for x in r[3]]
    hi = [x for r in rows for x in r[4]]
    _say(run_dir, f"   rete {sum(s) / len(s):.3f} ± {1.96 * sd / math.sqrt(len(ps)):.3f} (95%, per coppia); "
                  f"con Evelynn {sum(r[2] for r in rows if r[1] == 'A') / args.pairs:.2f}, "
                  f"con Kha'Zix {sum(r[2] for r in rows if r[1] == 'B') / args.pairs:.2f}; "
                  f"iterazioni per decisione: rete {sum(ni) / max(1, len(ni)):.0f}, bot {sum(hi) / max(1, len(hi)):.0f}; "
                  f"{(time.time() - t0) / 60:.0f} min")

    # (4) against simple_trade, as the hand-written bot's baseline
    tasks = [(1000 + g, "A" if g % 2 == 0 else "B", ckpt) for g in range(args.st_games)]
    with Pool(args.workers, initializer=_init) as pool:
        st = pool.map(_st_game, tasks)
    _say(run_dir, f"4. Contro simple_trade ({args.st_games} partite, 100 iterazioni, come handwritten_value.py): "
                  f"rete {sum(st) / len(st):.2f} (il bot a mano fa 0,80)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("data", "train", "measure", "all"))
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--games", type=int, default=2000)
    ap.add_argument("--keep", type=float, default=0.3, help="Share of the decisions that become examples")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--worlds", type=int, default=24)
    ap.add_argument("--pairs", type=int, default=100)
    ap.add_argument("--budget", type=float, default=0.4)
    ap.add_argument("--st-games", type=int, default=200)
    args = ap.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    if args.step in ("data", "all"):
        data(args)
    if args.step in ("train", "all"):
        train(args)
    if args.step in ("measure", "all"):
        measure(args)


if __name__ == "__main__":
    main()
