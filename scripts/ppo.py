#!/usr/bin/env python
"""L'allenamento PPO (21-22/11, docs/PIANO_FORZA.md; disegno e correzioni
della revisione esterna).

Una rete (riftbound/ai/ppo/) che gioca senza ricerca decide ogni scelta vera
e impara giocando contro se stessa, Evelynn (A) contro Kha'Zix (B); con
--mazzi ekr (22/11) a ciclo fisso metà Evelynn-Kha'Zix, un quarto Evelynn-
Rengar e un quarto Kha'Zix-Rengar, chi comincia alternato entro il matchup;
con --mazzi ekri (23/11) anche Ivern, con ekris anche Sett (vedi MAZZI).

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
    cali ampi, IC ~ +-0,10);
  - per gli altri matchup di --pannello-mazzi (ER, KR): --st-partite contro
    simple_trade e --coppie-ancora coppie contro l'ultima ancora, per mazzo
    pilotato dalla rete.
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
# The training mix, one cycle: the first deck of a matchup sits in A (letters
# as in collect.DECK_OF). "ekr": 50% Evelynn-Kha'Zix, 25% Evelynn-Rengar, 25%
# Kha'Zix-Rengar (revisione esterna, 21-22/11).
# "ekri" (23/11): the old three 2:1:1 on half the games, Evelynn-Ivern,
# Kha'Zix-Ivern, Rengar-Ivern a sixth each (cycle of 24: 6 EK, 3 ER, 3 KR,
# 4 EI, 4 KI, 4 RI); Ivern in B.
MAZZI = {"ek": ("EK",), "ekr": ("EK", "EK", "ER", "KR"),
         "ekri": ("EK", "EI", "ER", "KI", "EK", "RI", "KR", "EI", "EK", "KI", "ER", "RI",
                  "EK", "EI", "KR", "KI", "EK", "RI", "ER", "EI", "EK", "KI", "KR", "RI")}
# "ekris" (23/11): half the games the "ekri" cycle, half Evelynn-, Kha'Zix-,
# Rengar-, Ivern-Sett an eighth each (Sett in B); cycle of 48, alternating.
MAZZI["ekris"] = tuple(mu for pair in zip(MAZZI["ekri"], ("ES", "KS", "RS", "IS") * 6) for mu in pair)
# Measuring openings per matchup, disjoint (offsets from EVAL_SEED0):
# simple_trade, pairs against the anchor.
PANEL_SEEDS = {"EK": (0, 500_000), "ER": (100_000, 600_000), "KR": (200_000, 700_000),
               "EI": (300_000, 310_000), "KI": (320_000, 330_000), "RI": (340_000, 350_000),
               "ES": (360_000, 370_000), "KS": (380_000, 390_000), "RS": (400_000, 410_000),
               "IS": (420_000, 430_000)}
_NETS: dict = {}


def _init():
    import torch
    torch.set_num_threads(1)


def _net(blob: bytes, key: tuple[str, str]):
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


def _load_anchors(paths) -> dict[str, bytes]:
    from riftbound.ai.ppo.model import load

    files = list(dict.fromkeys(Path(path).resolve() for path in paths))
    stem_counts = Counter(path.stem for path in files)
    anchors = {}
    for path in files:
        label = path.stem if stem_counts[path.stem] == 1 else str(path)
        anchors[label] = _blob(load(path))
    return anchors


def batch_games(start: int, n: int, seme: int, archive: list, rng: random.Random,
                assegnazione: str = "bilanciata", archivio: str = "recenti", mazzi: str = "ek") -> list:
    """The games of one update: (seed, starter, opponent, learner seat, matchup).
    opponent "self" (both seats learn, learner seat None) or a checkpoint key.
    The matchup follows the cycle of MAZZI[mazzi] by the game's number; who
    starts alternates within each matchup, and against the archive the four
    cells (seat x starter) are balanced within each matchup."""
    out = []
    cycle = MAZZI[mazzi]
    # One offset per matchup, across batches too ("ek": the same draws as before).
    ks = {mu: rng.randrange(4) if assegnazione == "bilanciata" else 0 for mu in dict.fromkeys(cycle)}
    for g in range(n):
        seed = TRAIN_SEED0 + seme * 10_000_000 + start + g
        i = start + g
        mu = cycle[i % len(cycle)]
        nth = (i // len(cycle)) * cycle.count(mu) + cycle[:i % len(cycle)].count(mu)
        if archive and rng.random() < 0.2:
            recent, older = archive[-5:], archive[:-5]
            pool = older if archivio == "misto" and older and rng.random() < 0.5 else recent
            key = rng.choice(pool)
            if assegnazione == "vecchia":
                # The pilot's: seat by the game's index, starter by the seed's
                # parity; with batches of 64 they always matched.
                out.append((seed, "a" if seed % 2 == 0 else "b", key, "A" if g % 2 == 0 else "B", mu))
            else:
                k = ks[mu]
                out.append((seed, "a" if k % 2 == 0 else "b", key, "A" if k % 4 < 2 else "B", mu))
                ks[mu] += 1
        else:
            out.append((seed, "a" if nth % 2 == 0 else "b", "self", None, mu))
    return out


def _motore(kw: dict) -> str:
    """The engine a game of collect.play with these arguments goes to: Rust
    for the matchups the Rust engine covers (riftbound/rs/arena_rs.COPERTI:
    Evelynn, Kha'Zix, Rengar and Ivern among them; the lists recognised by
    their content, not their path: riftbound/provenienza.py) when --motore
    rust, Python otherwise (and for the games against the hand-written bot)."""
    from riftbound.ai.ppo.collect import EVE, KHA
    from riftbound.rs.arena_rs import coperte
    covered = coperte(kw.get("deck_a", EVE), kw.get("deck_b", KHA))
    rust = os.environ.get("RBSIM_MOTORE", "python") == "rust" and covered and kw.get("opponent") != "bot"
    return "rust" if rust else "python"


def _play(seed, nets, learners, **kw):
    """collect.play on the engine RBSIM_MOTORE names (--motore): "rust" plays
    the games of the covered matchups (_motore) on the Rust engine
    (riftbound/rs/collect_rs.py, the same examples bit for bit); the other
    matchups and the games against the hand-written bot stay on the Python
    engine (not ported yet)."""
    if _motore(kw) == "rust":
        from riftbound.rs.collect_rs import play
    else:
        from riftbound.ai.ppo.collect import play
    return play(seed, nets, learners, **kw)


def _collect(task):
    """A chunk of training games: (games, weights, snapshots {key: blob}, lam)."""
    from riftbound.ai.ppo.collect import DECK_OF, gae
    games, cur, snaps, lam = task
    me = _net(cur[1], ("learner", cur[0]))
    recs, out = [], []
    for seed, starter, opp, seat, mu in games:
        if opp == "self":
            nets, learners = {"A": me, "B": me}, {"A": True, "B": True}
        else:
            archived = _net(snaps[opp], ("archive", opp))
            nets = {seat: me, ("B" if seat == "A" else "A"): archived}
            learners = {seat: True}
        g = _play(seed, nets, learners, sample=True, starter=starter, deck_a=DECK_OF[mu[0]], deck_b=DECK_OF[mu[1]])
        for s, rs in g["records"].items():
            if rs:
                gae(rs, g["z"][s], gamma=1.0, lam=lam)
                recs += rs
        cell = None if opp == "self" else ("" if mu == "EK" else f"{mu} ") + f"{seat}{starter}"
        out.append({"winner": g["winner"], "turns": g["turns"], "counts": dict(g["counts"]), "cell": cell,
                    "matchup": mu})
    return recs, out


def _eval(task):
    """Measuring games, the highest score: (games [(seed, cand seat, starter,
    opponent kind, key, matchup)], cand, anchors {key: blob})."""
    from riftbound.ai.ppo.collect import DECK_OF
    games, cand, anchors = task
    me = _net(cand[1], ("panel", cand[0]))
    out = []
    for seed, seat, starter, kind, key, mu in games:
        other = "B" if seat == "A" else "A"
        if kind == "ancora":
            frozen = _net(anchors[key], ("anchor", key))
            nets, opp = {seat: me, other: frozen}, None
        else:
            nets, opp = {seat: me, other: None}, kind
        g = _play(seed, nets, {}, sample=False, starter=starter, opponent=opp,
                 deck_a=DECK_OF[mu[0]], deck_b=DECK_OF[mu[1]])
        out.append((kind, key, seed, seat, starter, 1.0 if g["winner"] == seat else 0.5 if g["winner"] == "DRAW" else 0.0,
                    mu))
    return out


def _chunks(xs: list, n: int) -> list:
    k = max(1, math.ceil(len(xs) / n))
    return [xs[i:i + k] for i in range(0, len(xs), k)]


def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


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
    ap.add_argument("--pannello-ogni", type=int, default=None,
                    help="ogni quante partite il pannello (default --tappa; checkpoint e archivio restano a ogni "
                         "--tappa; alla fine sempre)")
    ap.add_argument("--seme", type=int, default=0)
    ap.add_argument("--init", default=None, help="pesi di partenza (un checkpoint PPO); default casuali dal seme")
    ap.add_argument("--assegnazione", choices=("bilanciata", "vecchia"), default="bilanciata")
    ap.add_argument("--archivio", choices=("recenti", "misto"), default="recenti")
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr-finale", type=float, default=None,
                    help="lr a fine allenamento (--partite): scende in linea retta da --lr; default costante")
    ap.add_argument("--lam", type=float, default=0.98)
    ap.add_argument("--mazzi", choices=tuple(MAZZI), default="ek",
                    help="ek: solo Evelynn-Kha'Zix; ekr: 50%% Evelynn-Kha'Zix, 25%% Evelynn-Rengar, 25%% Kha'Zix-Rengar; "
                         "ekri: i tre di ekr 2:1:1 sulla metà, Evelynn-, Kha'Zix-, Rengar-Ivern un sesto ciascuno; "
                         "ekris: ekri sulla metà, Evelynn-, Kha'Zix-, Rengar-, Ivern-Sett un ottavo ciascuno")
    ap.add_argument("--pannello-mazzi", nargs="*", choices=tuple(PANEL_SEEDS), default=None,
                    help="i matchup del pannello (default: quelli di --mazzi); EK sempre")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--motore", choices=("python", "rust"), default="python",
                    help="motore dei matchup coperti da Rust (EK, ER, KR; rust: estensione riftbound_rs)")
    args = ap.parse_args()
    # The workers read the engine from the environment (_play).
    os.environ["RBSIM_MOTORE"] = args.motore
    if args.motore == "rust":
        import riftbound_rs  # noqa: F401  (the extension must be there: no silent fallback)
        from riftbound.rs.arena_rs import COPERTI
        print(f"motore: Rust per i matchup {', '.join(COPERTI)} (nei due posti); altri mazzi e bot su Python")

    import torch
    from riftbound.ai.ppo.collect import DECK_NAME
    from riftbound.ai.ppo.model import PPONet, load, save
    from riftbound.ai.ppo.train import update
    panel_matchups = list(dict.fromkeys(["EK"] + (args.pannello_mazzi if args.pannello_mazzi is not None
                                                  else list(MAZZI[args.mazzi]))))
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
    anchor_blobs = _load_anchors(anchors)

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
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.provenienza import REGOLE_PYTHON, provenienza, registra
    mus = list(dict.fromkeys(list(MAZZI[args.mazzi]) + panel_matchups))
    motori = {mu: _motore({"deck_a": DECK_OF[mu[0]], "deck_b": DECK_OF[mu[1]]}) for mu in mus} | {"bot": "python"}
    registra(run, provenienza(
        motore=motori, liste={k: DECK_OF[k] for k in sorted({c for mu in mus for c in mu})},
        checkpoint={"init": args.init, "corrente": run / "corrente.pt" if (run / "corrente.pt").exists() else None}
        | {f"ancora {a}": a for a in anchors}, partite=st["partite"], opzioni=vars(args) | {"run_dir": str(run)}))
    say(f"provenienza.jsonl: regole {REGOLE_PYTHON}, motore "
        + ", ".join(f"{mu} {m}" for mu, m in motori.items()))
    pool = Pool(args.workers, initializer=_init)

    extra = [mu for mu in panel_matchups if mu != "EK"]
    last_anchor = list(anchor_blobs)[-1] if anchor_blobs else None

    def panel(tag: str, with_bot: bool) -> dict:
        cand = (f"misura{st['partite']}", _blob(net))
        games = [(EVAL_SEED0 + k, "A" if k % 4 < 2 else "B", "a" if k % 2 == 0 else "b", "simple_trade", "", "EK")
                 for k in range(args.st_partite)]
        for key in anchor_blobs:
            games += [(EVAL_SEED0 + 500_000 + k, seat, "a" if k % 2 == 0 else "b", "ancora", key, "EK")
                      for k in range(args.coppie_ancora) for seat in ("A", "B")]
        if with_bot:
            games += [(EVAL_SEED0 + 900_000 + k, seat, "a" if k % 2 == 0 else "b", "bot", "", "EK")
                      for k in range(32) for seat in ("A", "B")]
        # The other matchups: simple_trade, and pairs against the last anchor.
        for mu in extra:
            s0, a0 = PANEL_SEEDS[mu]
            games += [(EVAL_SEED0 + s0 + k, "A" if k % 4 < 2 else "B", "a" if k % 2 == 0 else "b", "simple_trade",
                       "", mu) for k in range(args.st_partite)]
            if last_anchor:
                games += [(EVAL_SEED0 + a0 + k, seat, "a" if k % 2 == 0 else "b", "ancora", last_anchor, mu)
                          for k in range(args.coppie_ancora) for seat in ("A", "B")]
        allrows = [r for out in pool.map(_eval, [(c, cand, anchor_blobs) for c in _chunks(games, args.workers * 3)])
                   for r in out]
        rows = [r[:6] for r in allrows if r[6] == "EK"]
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
        for mu in extra:
            mrows = [r for r in allrows if r[6] == mu]
            names = {"A": DECK_NAME[mu[0]], "B": DECK_NAME[mu[1]]}
            first = {"a": names["A"], "b": names["B"]}
            stx = [r[5] for r in mrows if r[0] == "simple_trade"]
            out = {"simple_trade": sum(stx) / max(1, len(stx))}
            text = f"      {names['A']}-{names['B']}: simple_trade {out['simple_trade']:.3f} ("
            text += "; ".join(f"con {names[seat]} " + ", ".join(
                f"comincia {first[stt]} {_mean([r[5] for r in mrows if r[0] == 'simple_trade' and r[3] == seat and r[4] == stt]):.2f}"
                for stt in ("a", "b")) for seat in ("A", "B")) + ")"
            if last_anchor:
                per_seed: dict = {}
                for r in mrows:
                    if r[0] == "ancora":
                        per_seed.setdefault(r[2], []).append(r[5])
                m, h = _ci([sum(v) / len(v) for v in per_seed.values()])
                out[last_anchor], out["ic"] = m, h
                text += f"; contro {last_anchor} {m:.3f} +- {h:.3f} (" + ", ".join(
                    f"con {names[seat]} {_mean([r[5] for r in mrows if r[0] == 'ancora' and r[3] == seat]):.2f}"
                    for seat in ("A", "B")) + ")"
            res[mu] = out
            say(text)
        return res

    if not st["fatto_pannello_iniziale"]:
        say(f"\n== PPO ({time.strftime('%d/%m %H:%M')}) {run.name}: mazzi {args.mazzi}, seme {args.seme}, assegnazione "
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
                            args.assegnazione, args.archivio, args.mazzi)
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
            st.setdefault("matchup", {})
            st["matchup"][o["matchup"]] = st["matchup"].get(o["matchup"], 0) + 1
        with open(run / "aggiornamenti.jsonl", "a") as f:     # every update (revisione, 23/11)
            f.write(json.dumps({"partite": st["partite"], "esempi": len(recs)} | stats, default=float) + "\n")
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
                f"matchup {dict(sorted(st['matchup'].items()))}; "
                f"contro l'archivio, celle posto x chi comincia: {dict(sorted(st['celle'].items()))}")
            ogni = args.pannello_ogni or args.tappa
            if st["partite"] // ogni > prev // ogni or st["partite"] >= args.partite or bot:
                row = panel(f"{st['partite']} partite", with_bot=bot)
            else:
                row = {"partite": st["partite"], "tappa": f"{st['partite']} partite (senza pannello)"}
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
