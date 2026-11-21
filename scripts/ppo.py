#!/usr/bin/env python
"""Il pilota PPO (21/11, docs/PIANO_FORZA.md; disegno della revisione esterna).

Una rete (riftbound/ai/ppo/) che gioca senza ricerca decide ogni scelta vera
e impara giocando contro se stessa, Evelynn (A) contro Kha'Zix (B), seed di
allenamento da 1.000.000, chi comincia alternato.

Ogni aggiornamento: --per-aggiornamento partite con i pesi congelati; all'inizio
tutte contro se stessa (entrambi i posti imparano), poi l'80% così e il 20%
contro una versione salvata (impara solo il suo posto); GAE per posto
(gamma 1, lambda 0,98); PPO (clip 0,2, 4 epoche).

Ogni --tappa partite: un checkpoint, e due misure a scelta deterministica
(la mossa col punteggio più alto), su aperture mai usate per allenare:
  - contro simple_trade (metà per mazzo e posto);
  - contro la rete iniziale congelata, a coppie (stesso seed, piloti
    scambiati): punteggio, IC 95% per coppia, celle mazzo x chi comincia.
Regola fissata prima (revisione): alle tappe 5.000 / 15.000 / 30.000, impara
se batte la rete iniziale con >= 0,52 e limite inferiore > 0,50 e fa meglio
di lei contro simple_trade; curva piatta tra le tappe -> la ricetta si chiude.

Riprende dall'ultimo checkpoint; un file STOP nella cartella lo ferma.

  uv run --extra rl python scripts/ppo.py --run-dir runs/ppo1 --partite 5000
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TRAIN_SEED0, EVAL_SEED0 = 1_000_000, 2_000_000
_NETS: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _net(blob: bytes, key: str):
    from riftbound.ai.ppo.model import PPONet
    import torch
    if key not in _NETS:
        if len(_NETS) > 4:
            _NETS.clear()
        ck = torch.load(io.BytesIO(blob), map_location="cpu")
        net = PPONet(hidden=ck["hidden"], card_dim=ck["card_dim"], opt_dim=ck["opt_dim"])
        net.load_state_dict(ck["state_dict"])
        _NETS[key] = net.eval()
    return _NETS[key]


def _blob(net) -> bytes:
    import torch
    buf = io.BytesIO()
    torch.save({"state_dict": net.state_dict(), "hidden": net.hidden, "card_dim": net.card_dim,
                "opt_dim": net.opt_dim}, buf)
    return buf.getvalue()


def _collect(task):
    """A chunk of training games: (games [(seed, mode, learner seat)], weights,
    snapshots {key: blob}, lam)."""
    from riftbound.ai.ppo.collect import gae, play
    games, cur, snaps, lam = task
    me = _net(cur[1], cur[0])
    recs, out = [], []
    for seed, mode, seat in games:
        if mode == "self":
            nets, learners = {"A": me, "B": me}, {"A": True, "B": True}
        else:
            other = _net(snaps[mode], mode)
            nets = {seat: me, ("B" if seat == "A" else "A"): other}
            learners = {seat: True}
        g = play(seed, nets, learners, sample=True)
        for s, rs in g["records"].items():
            if rs:
                gae(rs, g["z"][s], gamma=1.0, lam=lam)
                recs += rs
        out.append({"winner": g["winner"], "turns": g["turns"], "counts": dict(g["counts"])})
    return recs, out


def _eval(task):
    """A chunk of measuring games, the highest score: (games [(seed, cand seat,
    opponent: "simple_trade" or "iniziale")], cand, init)."""
    from riftbound.ai.ppo.collect import play
    games, cand, init = task
    me = _net(cand[1], cand[0])
    out = []
    for seed, seat, opp in games:
        other = "B" if seat == "A" else "A"
        if opp == "simple_trade":
            nets = {seat: me, other: None}
        else:
            nets = {seat: me, other: _net(init[1], init[0])}
        g = play(seed, nets, {}, sample=False, opponent="simple_trade")
        out.append((seed, seat, 1.0 if g["winner"] == seat else 0.5 if g["winner"] == "DRAW" else 0.0))
    return out


def _chunks(xs: list, n: int) -> list:
    k = max(1, math.ceil(len(xs) / n))
    return [xs[i:i + k] for i in range(0, len(xs), k)]


def _ci(xs: list) -> tuple:
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))
    return m, 1.96 * sd / math.sqrt(len(xs))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs/ppo1")
    ap.add_argument("--partite", type=int, default=5000, help="partite di allenamento in tutto")
    ap.add_argument("--per-aggiornamento", type=int, default=64)
    ap.add_argument("--tappa", type=int, default=1000, help="ogni quante partite misurare")
    ap.add_argument("--misura-partite", type=int, default=200, help="partite contro simple_trade; coppie contro l'iniziale")
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lam", type=float, default=0.98)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()

    import torch
    from riftbound.ai.ppo.model import PPONet, load, save
    from riftbound.ai.ppo.train import update
    torch.set_num_threads(max(1, args.workers))
    run = args.run_dir
    run.mkdir(parents=True, exist_ok=True)
    stop = run / "STOP"

    def say(text: str) -> None:
        print(text, flush=True)
        with open(run / "PPO.txt", "a") as f:
            f.write(text + "\n")

    state_path = run / "stato.json"
    st = json.loads(state_path.read_text()) if state_path.exists() else {"partite": 0, "aggiornamenti": 0,
                                                                         "archivio": [], "misure": []}
    if not (run / "iniziale.pt").exists():
        torch.manual_seed(0)
        save(PPONet(), run / "iniziale.pt")
    init = load(run / "iniziale.pt")
    net = load(run / "corrente.pt") if (run / "corrente.pt").exists() else load(run / "iniziale.pt")
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    if (run / "ottimizzatore.pt").exists():
        opt.load_state_dict(torch.load(run / "ottimizzatore.pt"))
    init_blob = ("iniziale", _blob(init))
    rng = random.Random(st["partite"] + 17)

    def measure(tag: str) -> dict:
        cand = (f"misura{st['partite']}", _blob(net))
        n = args.misura_partite
        st_games = [(EVAL_SEED0 + k, "A" if k % 4 < 2 else "B", "simple_trade") for k in range(n)]
        pairs = [(EVAL_SEED0 + 500_000 + k, seat, "iniziale") for k in range(n) for seat in ("A", "B")]
        rows = [r for out in pool.map(_eval, [(c, cand, init_blob) for c in _chunks(st_games + pairs,
                                                                                args.workers * 2)])
                for r in out]
        st_rows = [r for r in rows if r[0] < EVAL_SEED0 + 500_000]
        pr = [r for r in rows if r[0] >= EVAL_SEED0 + 500_000]
        by: dict = {}
        for seed, seat, s in pr:
            by.setdefault(seed, []).append(s)
        m, h = _ci([sum(v) / 2 for v in by.values()])
        s_st = sum(r[2] for r in st_rows) / len(st_rows)
        cells = []
        for seat, deck in (("A", "Evelynn"), ("B", "Kha'Zix")):
            for parity, who in ((0, "comincia Evelynn"), (1, "comincia Kha'Zix")):
                xs = [s for seed, se, s in pr if se == seat and seed % 2 == parity]
                cells.append(f"{deck}, {who} {sum(xs) / max(1, len(xs)):.2f}")
        say(f"   [{tag}] contro simple_trade {s_st:.3f} ({len(st_rows)} partite); contro la rete iniziale "
            f"{m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f}, {len(by)} coppie); " + "; ".join(cells))
        return {"partite": st["partite"], "simple_trade": s_st, "iniziale": m, "ic": h}

    pool = Pool(args.workers, initializer=_init)
    if not st["misure"]:
        say(f"\n== Pilota PPO ({time.strftime('%d/%m %H:%M')}), {args.workers} processi, "
            f"{args.per_aggiornamento} partite per aggiornamento")
        st["misure"].append(measure("rete iniziale"))
        state_path.write_text(json.dumps(st))
    base_st = st["misure"][0]["simple_trade"]

    t0 = time.time()
    while st["partite"] < args.partite:
        cur = (f"w{st['aggiornamenti']}", _blob(net))
        snaps = {k: (run / f"{k}.pt").read_bytes() for k in st["archivio"]}
        snap_blobs = {}
        for k, raw in snaps.items():
            ck = torch.load(io.BytesIO(raw), map_location="cpu")
            m2 = PPONet(hidden=ck["hidden"], card_dim=ck["card_dim"], opt_dim=ck["opt_dim"])
            m2.load_state_dict(ck["state_dict"])
            snap_blobs[k] = _blob(m2)
        games = []
        for g in range(args.per_aggiornamento):
            seed = TRAIN_SEED0 + st["partite"] + g
            if st["archivio"] and rng.random() < 0.2:
                games.append((seed, rng.choice(st["archivio"]), "A" if g % 2 == 0 else "B"))
            else:
                games.append((seed, "self", None))
        t1 = time.time()
        res = pool.map(_collect, [(c, cur, snap_blobs, args.lam) for c in _chunks(games, args.workers)])
        recs = [r for rs, _ in res for r in rs]
        info = [o for _, out in res for o in out]
        t_col = time.time() - t1
        t1 = time.time()
        stats = update(net, opt, recs)
        t_upd = time.time() - t1
        st["partite"] += len(games)
        st["aggiornamenti"] += 1
        counts: Counter = Counter()
        for o in info:
            counts.update(o["counts"])
        won_a = sum(o["winner"] == "A" for o in info) / len(info)
        print(f"   partite {st['partite']}: {len(recs)} esempi, Evelynn vince {won_a:.2f}, turni "
              f"{sum(o['turns'] for o in info) / len(info):.1f}; kl {stats['kl']:+.4f}, clip "
              f"{stats['clipfrac']:.2f}, entropia {stats['entropia']:.3f}, errore valore "
              f"{stats['errore valore']:.3f}; raccolta {t_col:.0f} s, aggiornamento {t_upd:.0f} s", flush=True)
        save(net, run / "corrente.pt")
        torch.save(opt.state_dict(), run / "ottimizzatore.pt")
        if st["partite"] % args.tappa < args.per_aggiornamento:
            key = f"ckpt_{st['partite']:06d}"
            save(net, run / f"{key}.pt")
            st["archivio"] = (st["archivio"] + [key])[-5:]
            say(f"Tappa {st['partite']} partite ({(time.time() - t0) / 60:.0f} min da questo lancio; "
                f"opzioni sconosciute {counts['opzioni sconosciute']})")
            st["misure"].append(measure(f"{st['partite']} partite"))
            last = st["misure"][-1]
            crossed = [m for m in (5000, 15000, 30000) if st["partite"] - len(games) < m <= st["partite"]]
            if crossed:
                ok = last["iniziale"] >= 0.52 and last["iniziale"] - last["ic"] > 0.50 and \
                    last["simple_trade"] > base_st
                say(f"   Regola alla tappa {crossed[0]}: {'IMPARA' if ok else 'NON ANCORA'} (contro l'iniziale "
                    f"{last['iniziale']:.3f}, limite inferiore {last['iniziale'] - last['ic']:.3f}; contro "
                    f"simple_trade {last['simple_trade']:.3f}, all'inizio {base_st:.3f})")
        state_path.write_text(json.dumps(st))
        if stop.exists():
            pool.terminate()
            sys.exit("Fermato (STOP): rilanciato, riprende.")
    pool.close()
    say(f"Fine: {st['partite']} partite, {(time.time() - t0) / 60:.0f} min da questo lancio")


if __name__ == "__main__":
    main()
