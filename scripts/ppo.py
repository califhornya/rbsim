#!/usr/bin/env python
"""L'allenamento PPO (21-22/11, docs/PIANO_FORZA.md; disegno e correzioni
della revisione esterna).

Una rete (riftbound/ai/ppo/) che gioca senza ricerca decide ogni scelta vera
e impara giocando contro se stessa, Evelynn (A) contro Kha'Zix (B).

Ogni aggiornamento: --per-aggiornamento partite con i pesi congelati, chi
comincia alternato. All'inizio tutte contro se stessa (entrambi i posti
imparano); poi l'80% così e il 20% contro un checkpoint dell'archivio (impara
solo il suo posto):
  --archivio recenti   il 20% dagli ultimi 5 checkpoint (il pilota);
  --archivio misto     10% dagli ultimi 5, 10% da quelli più vecchi.
  --assegnazione bilanciata  contro l'archivio, posto di chi impara e chi
                             comincia bilanciati nelle quattro combinazioni;
  --assegnazione vecchia     come il pilota del 21/11: chi impara cominciava
                             sempre (difetto trovato dalla revisione, tenuto
                             solo per confrontare le ricette).
GAE per posto (gamma 1, lambda 0,98); PPO (clip 0,2, 4 epoche). --seme fissa
pesi iniziali, partite, scelte degli avversari e ordine dei minibatch.

Ogni --tappa partite un checkpoint e il pannello, a mossa col punteggio più
alto, su aperture di misura mai usate per allenare:
  - --coppie-ancora coppie (stesso seed, piloti scambiati) contro ciascuna
    ancora congelata (--ancore: di default i checkpoint 5.056, 15.040,
    30.016 del pilota in runs/ppo1); media a pesi uguali, IC 95% sui seed;
  - --st-partite partite contro simple_trade, per continuità;
  - ogni --allarme-bot partite, 32 coppie contro il bot a mano (allarme per
    cali ampi, IC ~ +-0,10).
Tutto anche in tappe.jsonl (KL, clip, entropia per famiglia di menu, misure).

Riprende dall'ultimo checkpoint; un file STOP nella cartella lo ferma.

  uv run --extra rl python scripts/ppo.py --run-dir runs/ppo2 --partite 20000 --seme 1
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
PILOT_ANCHORS = ("ckpt_005056.pt", "ckpt_015040.pt", "ckpt_030016.pt")
_NETS: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _net(blob: bytes, key: str):
    from riftbound.ai.ppo.model import PPONet
    import torch
    if key not in _NETS:
        if len(_NETS) > 8:
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


def batch_games(start: int, n: int, seme: int, archive: list, rng: random.Random,
                assegnazione: str = "bilanciata", archivio: str = "recenti") -> list:
    """The games of one update: (seed, starter, opponent, learner seat).
    opponent "self" (both seats learn, learner seat None) or a checkpoint key."""
    out = []
    k = rng.randrange(4) if assegnazione == "bilanciata" else 0   # across batches too
    for g in range(n):
        seed = TRAIN_SEED0 + seme * 10_000_000 + start + g
        if archive and rng.random() < 0.2:
            recent, older = archive[-5:], archive[:-5]
            pool = older if archivio == "misto" and older and rng.random() < 0.5 else recent
            key = rng.choice(pool)
            if assegnazione == "vecchia":
                # The pilot's: seat by the game's index, starter by the seed's
                # parity; with batches of 64 they always matched.
                out.append((seed, "a" if seed % 2 == 0 else "b", key, "A" if g % 2 == 0 else "B"))
            else:
                out.append((seed, "a" if k % 2 == 0 else "b", key, "A" if k % 4 < 2 else "B"))
            k += 1
        else:
            out.append((seed, "a" if g % 2 == 0 else "b", "self", None))
    return out


def _collect(task):
    """A chunk of training games: (games, weights, snapshots {key: blob}, lam)."""
    from riftbound.ai.ppo.collect import gae, play
    games, cur, snaps, lam = task
    me = _net(cur[1], cur[0])
    recs, out = [], []
    for seed, starter, opp, seat in games:
        if opp == "self":
            nets, learners = {"A": me, "B": me}, {"A": True, "B": True}
        else:
            nets = {seat: me, ("B" if seat == "A" else "A"): _net(snaps[opp], opp)}
            learners = {seat: True}
        g = play(seed, nets, learners, sample=True, starter=starter)
        for s, rs in g["records"].items():
            if rs:
                gae(rs, g["z"][s], gamma=1.0, lam=lam)
                recs += rs
        cell = None if opp == "self" else f"{seat}{starter}"
        out.append({"winner": g["winner"], "turns": g["turns"], "counts": dict(g["counts"]), "cell": cell})
    return recs, out


def _eval(task):
    """Measuring games, the highest score: (games [(seed, cand seat, starter,
    opponent kind, key)], cand, anchors {key: blob})."""
    from riftbound.ai.ppo.collect import play
    games, cand, anchors = task
    me = _net(cand[1], cand[0])
    out = []
    for seed, seat, starter, kind, key in games:
        other = "B" if seat == "A" else "A"
        if kind == "ancora":
            nets, opp = {seat: me, other: _net(anchors[key], key)}, None
        else:
            nets, opp = {seat: me, other: None}, kind
        g = play(seed, nets, {}, sample=False, starter=starter, opponent=opp)
        out.append((kind, key, seed, seat, starter, 1.0 if g["winner"] == seat else 0.5 if g["winner"] == "DRAW" else 0.0))
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
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs/ppo2")
    ap.add_argument("--partite", type=int, default=20000, help="partite di allenamento in tutto")
    ap.add_argument("--per-aggiornamento", type=int, default=64)
    ap.add_argument("--tappa", type=int, default=1000, help="ogni quante partite il pannello")
    ap.add_argument("--ancore", nargs="*", default=None)
    ap.add_argument("--coppie-ancora", type=int, default=64)
    ap.add_argument("--st-partite", type=int, default=200)
    ap.add_argument("--allarme-bot", type=int, default=5000, help="ogni quante partite 32 coppie col bot (0: mai)")
    ap.add_argument("--seme", type=int, default=0)
    ap.add_argument("--init", default=None, help="pesi di partenza (un checkpoint PPO); default casuali dal seme")
    ap.add_argument("--assegnazione", choices=("bilanciata", "vecchia"), default="bilanciata")
    ap.add_argument("--archivio", choices=("recenti", "misto"), default="recenti")
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr-finale", type=float, default=None,
                    help="lr a fine allenamento (--partite): scende in linea retta da --lr; default costante")
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

    def log(row: dict) -> None:
        with open(run / "tappe.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")

    anchors = args.ancore if args.ancore is not None else \
        [str(ROOT / "runs/ppo1" / a) for a in PILOT_ANCHORS if (ROOT / "runs/ppo1" / a).exists()]
    anchor_blobs = {Path(a).stem: _blob(load(a)) for a in anchors}

    state_path = run / "stato.json"
    st = json.loads(state_path.read_text()) if state_path.exists() else \
        {"partite": 0, "aggiornamenti": 0, "archivio": [], "fatto_pannello_iniziale": False,
         "celle": {}, "opzioni": vars(args) | {"run_dir": str(run)}}
    if not (run / "iniziale.pt").exists():
        torch.manual_seed(args.seme)
        save(load(args.init) if args.init else PPONet(), run / "iniziale.pt")
    net = load(run / "corrente.pt") if (run / "corrente.pt").exists() else load(run / "iniziale.pt")
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    if (run / "ottimizzatore.pt").exists():
        opt.load_state_dict(torch.load(run / "ottimizzatore.pt"))
    rng = random.Random(args.seme * 1_000_003 + st["partite"])
    pool = Pool(args.workers, initializer=_init)

    def panel(tag: str, with_bot: bool) -> dict:
        cand = (f"misura{st['partite']}", _blob(net))
        games = [(EVAL_SEED0 + k, "A" if k % 4 < 2 else "B", "a" if k % 2 == 0 else "b", "simple_trade", "")
                 for k in range(args.st_partite)]
        for key in anchor_blobs:
            games += [(EVAL_SEED0 + 500_000 + k, seat, "a" if k % 2 == 0 else "b", "ancora", key)
                      for k in range(args.coppie_ancora) for seat in ("A", "B")]
        if with_bot:
            games += [(EVAL_SEED0 + 900_000 + k, seat, "a" if k % 2 == 0 else "b", "bot", "")
                      for k in range(32) for seat in ("A", "B")]
        rows = [r for out in pool.map(_eval, [(c, cand, anchor_blobs) for c in _chunks(games, args.workers * 3)])
                for r in out]
        res = {"partite": st["partite"], "tappa": tag}
        stx = [r[5] for r in rows if r[0] == "simple_trade"]
        res["simple_trade"] = sum(stx) / len(stx) if stx else None
        line = f"   [{tag}] simple_trade {res['simple_trade']:.3f}" if stx else f"   [{tag}]"
        if anchor_blobs:
            per_seed: dict = {}
            for kind, key, seed, seat, starter, s in rows:
                if kind == "ancora":
                    per_seed.setdefault(seed, []).append(s)
                    res.setdefault("ancore", {}).setdefault(key, []).append(s)
            res["ancore"] = {k: sum(v) / len(v) for k, v in res["ancore"].items()}
            m, h = _ci([sum(v) / len(v) for v in per_seed.values()])
            res["media ancore"], res["ic"] = m, h
            cells = []
            for seat, deck in (("A", "Evelynn"), ("B", "Kha'Zix")):
                for starter, who in (("a", "comincia Evelynn"), ("b", "comincia Kha'Zix")):
                    xs = [s for kind, _, _, se, stt, s in rows if kind == "ancora" and se == seat and stt == starter]
                    cells.append(f"{deck}, {who} {sum(xs) / max(1, len(xs)):.2f}")
            line += f"; ancore {m:.3f} +- {h:.3f} (" + ", ".join(f"{k} {v:.3f}" for k, v in res["ancore"].items()) \
                + "); " + "; ".join(cells)
        if with_bot:
            per: dict = {}
            for kind, _, seed, _, _, s in rows:
                if kind == "bot":
                    per.setdefault(seed, []).append(s)
            m, h = _ci([sum(v) / 2 for v in per.values()])
            res["bot"], res["ic bot"] = m, h
            line += f"; bot a mano {m:.3f} +- {h:.3f}"
        say(line)
        return res

    if not st["fatto_pannello_iniziale"]:
        say(f"\n== PPO ({time.strftime('%d/%m %H:%M')}) {run.name}: seme {args.seme}, assegnazione "
            f"{args.assegnazione}, archivio {args.archivio}, lr {args.lr}"
            + (f" -> {args.lr_finale}" if args.lr_finale is not None else "") + f", {args.workers} processi, "
            f"{args.per_aggiornamento} partite per aggiornamento; ancore: {', '.join(anchor_blobs) or 'nessuna'}")
        log(panel("rete iniziale", with_bot=False))
        st["fatto_pannello_iniziale"] = True
        state_path.write_text(json.dumps(st))

    t0 = time.time()
    while st["partite"] < args.partite:
        cur = (f"w{st['aggiornamenti']}", _blob(net))
        games = batch_games(st["partite"], args.per_aggiornamento, args.seme, st["archivio"], rng,
                            args.assegnazione, args.archivio)
        snaps = {g[2]: (run / f"{g[2]}.pt").read_bytes() for g in games if g[2] != "self"}
        snap_blobs = {k: _blob(load(io.BytesIO(v))) for k, v in snaps.items()}
        t1 = time.time()
        res = pool.map(_collect, [(c, cur, snap_blobs, args.lam) for c in _chunks(games, args.workers)])
        recs = [r for rs, _ in res for r in rs]
        info = [o for _, out in res for o in out]
        t_col = time.time() - t1
        torch.manual_seed(args.seme * 100_003 + st["aggiornamenti"])
        if args.lr_finale is not None:
            frac = min(1.0, st["partite"] / max(1, args.partite))
            for group in opt.param_groups:
                group["lr"] = args.lr + (args.lr_finale - args.lr) * frac
        t1 = time.time()
        stats = update(net, opt, recs)
        t_upd = time.time() - t1
        prev = st["partite"]
        st["partite"] += len(games)
        st["aggiornamenti"] += 1
        for o in info:
            if o["cell"]:
                st["celle"][o["cell"]] = st["celle"].get(o["cell"], 0) + 1
        print(f"   partite {st['partite']}: {len(recs)} esempi; kl {stats['kl']:+.4f}, clip "
              f"{stats['clipfrac']:.2f}, entropia {stats['entropia']:.3f}, errore valore "
              f"{stats['errore valore']:.3f}; raccolta {t_col:.0f} s, aggiornamento {t_upd:.0f} s", flush=True)
        save(net, run / "corrente.pt")
        torch.save(opt.state_dict(), run / "ottimizzatore.pt")
        if st["partite"] // args.tappa > prev // args.tappa:
            key = f"ckpt_{st['partite']:06d}"
            save(net, run / f"{key}.pt")
            st["archivio"].append(key)
            bot = args.allarme_bot > 0 and st["partite"] // args.allarme_bot > prev // args.allarme_bot
            counts: Counter = Counter()
            for o in info:
                counts.update(o["counts"])
            say(f"Tappa {st['partite']} partite ({(time.time() - t0) / 60:.0f} min da questo lancio); "
                f"contro l'archivio, celle posto x chi comincia: {dict(sorted(st['celle'].items()))}")
            row = panel(f"{st['partite']} partite", with_bot=bot)
            row.update({k: v for k, v in stats.items()})
            log(row)
        state_path.write_text(json.dumps(st))
        if stop.exists():
            pool.terminate()
            sys.exit("Fermato (STOP): rilanciato, riprende.")
    pool.close()
    say(f"Fine: {st['partite']} partite, {(time.time() - t0) / 60:.0f} min da questo lancio")


if __name__ == "__main__":
    main()
