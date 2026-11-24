"""Arena mista a passo comune (metodo di Astra, 24/11): il bot coi prior PPO su
Rust a un budget ridotto contro lo stesso bot su Python a 0,4 s, stesso
checkpoint, semi appaiati, posti scambiati.

Una partita mista non si può giocare su un solo motore. Si giocano due copie
della stessa partita, una per motore, dallo stesso seme e con gli stessi
generatori degli agenti, una accanto all'altra (due thread):
- quando cerca il bot "Python", la copia Python fa la sua ricerca a tempo
  (--budget-python) e passa il numero esatto di iterazioni alla copia Rust,
  che ripete la ricerca con quel numero;
- quando cerca il bot "Rust", lo fa la copia Rust col suo tempo
  (--budget-rust) e passa il numero alla copia Python;
- chi cerca a tempo parte solo quando l'altra copia è ferma ad aspettare
  (il tempo CPU del processo conta solo la sua ricerca); scambi e controlli
  fuori dal cronometro;
- vale per turno principale, reazioni e showdown; mulligan e decisioni
  forzate restano come sono. A lavoro fisso i due motori sono identici
  (arena_parita.py): le due copie restano la stessa partita.
Ogni ricerca ha un'identità (posto, progressivo, finestra, turno), controllata
a ogni scambio; a fine partita si confrontano la traccia (stato canonico,
menu, azioni, scelte, estrazioni) e ogni ricerca (menu, prior, visite, Q,
mossa, scelte interne). Una partita divergente sospende l'esito.

Regole fissate prima (default): 800 coppie, semi 70000-70799 (fuori da quelli
di calibrazione e di parità, 40000-40039 e 900001-900010), budget Rust 0,030 s
CPU, Python 0,400 s; punteggio del bot Rust (vittoria 1, pareggio 0,5,
sconfitta 0), media delle coppie con IC 95%: promosso se il limite inferiore,
prima dell'arrotondamento, supera 0,47. Si può fermare e rilanciare.

  python scripts/rust/arena_mista.py --ckpt runs/sett/ekris_s12/ckpt_040000.pt --out runs/budget/ARENA_MISTA.txt [--workers N]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import random
import sys
import threading
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))

WAIT_S = 1800
_NET: dict = {}


class Abort(BaseException):
    """The other copy stopped (an error or a divergence there)."""


class Divergence(BaseException):
    """The two copies are no longer at the same search."""


class Link:
    """The two copies' inboxes ("py", "rs"); `leader[seat]`: the engine whose
    budget that seat's bot searches with."""

    def __init__(self, leader: dict):
        self.box = {"py": queue.Queue(), "rs": queue.Queue()}
        self.leader = leader
        self.counts: list = []        # (seat, point, n, engine) of every led search
        self.diverged = None          # the first identity mismatch met by either copy

    def _get(self, engine: str):
        try:
            msg = self.box[engine].get(timeout=WAIT_S)
        except queue.Empty:
            raise Abort("timeout") from None
        if msg[0] == "abort":
            raise Abort(msg[1])
        return msg

    def abort(self, why: str) -> None:
        for q in self.box.values():
            q.put(("abort", why))

    def _diverge(self, why: str):
        if self.diverged is None:
            self.diverged = why
        raise Divergence(why)

    def hooks(self, engine: str):
        other = "rs" if engine == "py" else "py"

        def before(info: dict) -> int:
            if self.leader[info["seat"]] == engine:
                msg = self._get(engine)
                if msg != ("ready", info):
                    self._diverge(f"{engine} leads {info}, the other copy is at {msg}")
                return -1
            self.box[other].put(("ready", info))
            msg = self._get(engine)
            if msg[0] != "count" or msg[1] != info:
                self._diverge(f"{engine} repeats {info}, the other copy sent {msg}")
            return msg[2]

        def after(info: dict, n: int) -> None:
            self.counts.append((info["seat"], info["point"], n, engine))
            self.box[other].put(("count", info, n))
        return before, after


def _lockstep_class():
    from riftbound.ai.net_mcts import _Node
    from riftbound.ai.ppo.prior_bot import _Q, PPOPriorAgent
    from riftbound.core.decisions import DecisionPoint

    class LockstepPrior(PPOPriorAgent):
        """PPOPriorAgent whose searches follow the step: its own CPU budget
        (as _Budget.search) when it leads, the other copy's count otherwise."""

        def __init__(self, player, net, rng, budget, before, after):
            super().__init__(player, net, rng=rng, budget=budget)
            self._before, self._after, self._k = before, after, 0

        def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
            self._question = _Q.get(point, "main")
            self._ensure_rng()
            side = self.player.name
            root = _Node()
            self._full = True
            info = {"seat": side, "k": self._k, "point": point.value, "turn": self.gs.turn}
            self._k += 1
            turn = point == DecisionPoint.TURN_ACTION

            def step():
                if turn:
                    self._iterate(root, side, cards_played, legal)
                else:
                    self._iterate_now(root, side, point, legal, bf_idx)
            n = self._before(info)
            if n >= 0:
                for _ in range(n):
                    step()
                return root
            t0, n = time.process_time(), 0
            while n < 1 or time.process_time() - t0 < self.budget:
                step()
                n += 1
            if turn:
                self.main_iters.append(n)
            self._after(info, n)
            return root
    return LockstepPrior


def _net(ckpt: str):
    if ckpt not in _NET:
        import torch
        from riftbound.ai.ppo.model import PPONet, load
        torch.set_num_threads(1)
        if ckpt.startswith("seme:"):
            torch.manual_seed(int(ckpt[5:]))
            _NET[ckpt] = PPONet().eval()
        else:
            _NET[ckpt] = load(ckpt).eval()
    return _NET[ckpt]


def game(task) -> dict:
    """One game in step. task: (seed, starter, rust_seat, ckpt, budget_rust,
    budget_python, check)."""
    seed, starter, rs_seat, ckpt, b_rs, b_py, check = task
    import arena_parita as AP
    from riftbound.ai.ppo.collect import EVE, KHA, MAX_TURNS
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.arena_rs import make_probs
    net = _net(ckpt)
    py_seat = "B" if rs_seat == "A" else "A"
    link = Link({rs_seat: "rs", py_seat: "py"})
    budget = {rs_seat: b_rs, py_seat: b_py}
    out: dict = {}

    def run_py():
        try:
            from riftbound.ai.ppo.agent import PPOChooser
            from riftbound.core.game_factory import build_game
            from riftbound.core.loop import GameLoop
            from riftbound.rs.trace_py import traced_game
            cls = _lockstep_class()
            log: list = []
            AP.hook_python(log)
            before, after = link.hooks("py")
            fac = {s: (lambda p, s=s: cls(p, net, random.Random(seed * 2 + (s == "B")), budget[s], before, after))
                   for s in "AB"}
            t0 = time.perf_counter()
            if check:
                res, tr = traced_game(seed, EVE, KHA, fac, starter=starter, chooser="ppo", with_obs=False,
                                      keep_states=True)
            else:
                gs = build_game(game_seed=seed, deck_a_path=EVE, deck_b_path=KHA, ai_a=None, ai_b=None,
                                max_turns=MAX_TURNS, first_player=starter)
                for s in "AB":
                    gs.get_player(s).agent = fac[s](gs.get_player(s))
                loop = GameLoop(gs)
                loop.chooser = PPOChooser(gs)
                res, tr = loop.start(), None
            out["py"] = (res.winner, res.turns, tr, log, time.perf_counter() - t0)
        except BaseException as e:  # noqa: BLE001 — told to the other copy, reported in the row
            out["py_err"] = repr(e)
            link.abort(f"python: {e!r}")

    def run_rs():
        try:
            before, after = link.hooks("rs")
            g = rb.build(seed, EVE, KHA, starter, MAX_TURNS)
            probs = make_probs(net)
            for s in "AB":
                g.set_search_agent(s, 100, seed * 2 + (s == "B"), budget[s], probs, check,
                                   lambda info: before(json.loads(info)),
                                   lambda info, n: after(json.loads(info), n))
            g.set_side_chooser()
            start = json.loads(g.raw_dump()) if check else None
            if check:
                g.trace_on()
            t0 = time.perf_counter()
            winner, turns = g.start()
            wall = time.perf_counter() - t0
            if check:
                out["rs"] = (winner, turns, start, json.loads(g.events()), json.loads(g.raw_dump()),
                             {"A": json.loads(g.search_log("A")), "B": json.loads(g.search_log("B"))}, wall)
            else:
                out["rs"] = (winner, turns, None, None, None, None, wall)
        except BaseException as e:  # noqa: BLE001
            out["rs_err"] = repr(e)
            link.abort(f"rust: {e!r}")

    threads = [threading.Thread(target=run_py), threading.Thread(target=run_rs)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    row = {"seed": seed, "starter": starter, "rust_seat": rs_seat, "wall_s": round(time.perf_counter() - t0, 2)}
    if link.diverged is not None:
        # The copies left each other at a search: a divergence (the other
        # copy's stop is its consequence), not a failed game to replay.
        row["divergenza"] = [{"passo": link.diverged}]
        return row
    if "py_err" in out or "rs_err" in out:
        row["errore"] = {k: out[k] for k in ("py_err", "rs_err") if k in out}
        return row
    pw, pt, tr, py_log, _ = out["py"]
    rw, rt, start, events, end, rs_logs, _ = out["rs"]
    row |= {"winner": pw, "turns": pt, "score": 1.0 if pw == rs_seat else 0.5 if pw == "DRAW" else 0.0}
    diff = []
    if (pw, pt) != (rw, rt):
        diff.append({"risultato": [[pw, pt], [rw, rt]]})
    if check:
        from diff_trace import FIELDS, canonical_rust_events, first_difference
        rs, rs_trees = canonical_rust_events(start, events, end)
        py = [e for e in tr.events if e["k"] in FIELDS or e["k"].startswith("decide_")]
        d = first_difference(py, rs, tr.states, rs_trees)
        if d is not None:
            diff.append({"traccia": {"event": d[0], "field": d[1], "python": d[2], "rust": d[3]}})
        s = AP.first_search_difference(py_log, rs_logs)
        if s is not None:
            diff.append({"ricerca": s})
        row["eventi"] = len(py)
    if diff:
        row["divergenza"] = json.loads(json.dumps(diff, default=str))[:2]
    counts: dict = {}
    for seat, point, n, engine in link.counts:
        counts.setdefault(f"{engine} {point}", []).append(n)
    row["iterazioni"] = counts
    return row


def _init() -> None:
    try:
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass


def _ci(xs: list) -> tuple:
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))
    return m, 1.96 * sd / math.sqrt(len(xs))


def _pct(xs: list, q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def _replay_it(r: dict) -> bool:
    """A divergent game to play again: the copies left each other (no result,
    or a different trace or result), so the game has no valid result."""
    return "divergenza" in r and ("score" not in r or any(set(d) - {"ricerca"} for d in r["divergenza"]))


def _impronta(r: dict) -> str:
    """The fingerprint of one recorded game: what an explanation is about."""
    import hashlib
    g = {k: r.get(k) for k in ("seed", "rust_seat", "starter", "winner", "turns", "score", "iterazioni", "divergenza")}
    return hashlib.sha256(json.dumps(g, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _spiegazione(r: dict, entries: list, key: dict) -> bool:
    """Whether a saved explanation is about this very game (same fingerprint)
    played in this configuration (checkpoint, budgets, rules, checks)."""
    imp = _impronta(r)
    return any(e.get("impronta") == imp and e.get("configurazione") == key for e in entries)


def _explained(r: dict, spiegate: set) -> bool:
    """A divergence reproduced and explained (arena_mista_riprova.py identical
    with the current code), only in the searches' numbers: the two copies
    played the same game, which counts."""
    return (r["seed"], r["rust_seat"]) in spiegate and "score" in r and \
        all(set(d) == {"ricerca"} for d in r.get("divergenza", []))


def valuta(rows: list, seeds, coppie: int, soglia: float, spiegate: frozenset = frozenset()) -> dict:
    """The verdict on the prescribed sample: SOSPESO while any game diverged
    (unless explained: `spiegate`, (seed, rust seat)) or any of the 2 x coppie
    games is missing (failed games are replayed on the next launch); else
    PROMOSSO when the lower bound of the 95% CI on the pairs' means, before
    rounding, is above `soglia`."""
    seeds = set(seeds)
    rows = [r for r in rows if r["seed"] in seeds]
    div = [r for r in rows if "divergenza" in r and not _explained(r, spiegate)]
    valid = [r for r in rows if "score" in r and ("divergenza" not in r or _explained(r, spiegate))]
    expected = {(s, seat) for s in seeds for seat in ("A", "B")}
    missing = expected - {(r["seed"], r["rust_seat"]) for r in rows}
    by: dict = {}
    for r in valid:
        by.setdefault(r["seed"], []).append(r["score"])
    pairs = [sum(v) / len(v) for v in by.values() if len(v) == 2]
    complete = not div and not missing and len(pairs) == coppie
    m, h = _ci(pairs) if pairs else (float("nan"), float("nan"))
    esito = "SOSPESO" if not complete else "PROMOSSO" if m - h > soglia else "NON PROMOSSO"
    return {"esito": esito, "media": m, "mezzo_ic": h, "coppie": pairs, "valide": valid, "divergenti": div,
            "mancanti": missing, "completo": complete}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="i prior di entrambi i bot (o seme:N per una rete casuale)")
    ap.add_argument("--coppie", type=int, default=800)
    ap.add_argument("--seed0", type=int, default=70_000)
    ap.add_argument("--budget-rust", type=float, default=0.030)
    ap.add_argument("--budget-python", type=float, default=0.400)
    ap.add_argument("--soglia", type=float, default=0.47, help="il limite inferiore dell'IC 95%% deve superarla")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--senza-controlli", action="store_true",
                    help="niente traccia né confronto delle ricerche (resta il controllo dell'identità a ogni scambio)")
    ap.add_argument("--tempo-produzione", type=int, default=4,
                    help="partite tutte su Rust, entrambi i bot a --budget-rust, per il tempo reale per partita")
    ap.add_argument("--spiegata", action="append", default=[], metavar="SEME:POSTO",
                    help="una divergenza riprodotta e spiegata (arena_mista_riprova.py), solo nei numeri delle "
                         "ricerche: la partita conta; per esempio --spiegata 70113:A (a fine arena le altre si "
                         "rigiocano da sole coi conteggi registrati: <out>.spiegate.json)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    spiegate = frozenset((int(x.split(":")[0]), x.split(":")[1]) for x in args.spiegata)
    from riftbound.provenienza import REGOLE_PYTHON, file_sha, provenienza, registra
    args.out.parent.mkdir(parents=True, exist_ok=True)
    righe = args.out.with_suffix(".jsonl")
    sha = file_sha(args.ckpt) if not args.ckpt.startswith("seme:") else args.ckpt

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    seeds = range(args.seed0, args.seed0 + args.coppie)
    say(f"\n== Arena mista a passo comune ({time.strftime('%d/%m %H:%M')}), Evelynn-Kha'Zix")
    say(f"bot coi prior di {args.ckpt} (sha256 {sha}) in entrambi i posti: Rust a {args.budget_rust} s CPU per "
        f"ricerca contro Python a {args.budget_python} s; {args.workers} processi")
    say(f"regole fissate prima: {args.coppie} coppie, semi {seeds[0]}-{seeds[-1]} (pari: comincia Evelynn), posti "
        f"scambiati; punteggio del bot Rust; promosso se il limite inferiore dell'IC 95% sulle coppie > "
        f"{args.soglia}; una partita divergente sospende l'esito")
    from riftbound.ai.ppo.collect import EVE, KHA
    registra(args.out.parent, provenienza(
        motore={"EK": "misto (passo comune)"}, liste={"E": EVE, "K": KHA},
        checkpoint={"prior": None if sha == args.ckpt else args.ckpt},
        arena=str(args.out), budget={"rust": args.budget_rust, "python": args.budget_python}))
    check = not args.senza_controlli
    key = {"ckpt_sha": sha, "budget_rust": args.budget_rust, "budget_python": args.budget_python,
           "regole": REGOLE_PYTHON, "controlli": check}
    rows: list = []
    if righe.exists():
        for line in open(righe):
            r = json.loads(line)
            # Only comparable games, and with the checks on only checked ones
            # (a trace compared, or a divergence met); failed games are replayed.
            if all(r.get(k) == v for k, v in key.items()) and "errore" not in r and not _replay_it(r) and \
                    (not check or "eventi" in r or "divergenza" in r):
                rows.append(r)
    done = {(r["seed"], r["rust_seat"]) for r in rows}
    tasks = [(s, "a" if s % 2 == 0 else "b", seat, args.ckpt, args.budget_rust, args.budget_python,
              check) for s in seeds for seat in ("A", "B") if (s, seat) not in done]
    if rows:
        say(f"   ripresa: {len(rows)} partite già giocate, {len(tasks)} da giocare")
    t0 = time.time()
    with Pool(args.workers, initializer=_init) as pool, open(righe, "a") as f:
        for r in pool.imap_unordered(game, tasks):
            r |= key
            f.write(json.dumps(r) + "\n")
            f.flush()
            if "errore" in r:
                say(f"   ERRORE seme {r['seed']} posto Rust {r['rust_seat']}: {r['errore']}")
                continue
            rows.append(r)
            if "divergenza" in r:
                say(f"   DIVERGENZA seme {r['seed']} posto Rust {r['rust_seat']}: {json.dumps(r['divergenza'])[:600]}")
            if len(rows) % 100 == 0:
                print(f"   ... {len(rows)}/{2 * args.coppie} partite, {(time.time() - t0) / 60:.0f} min", flush=True)
    # Divergences only in the searches' numbers (the same game in both copies):
    # replayed with their recorded counts and the current code; identical now
    # = explained by the fixes made since, the game counts. One that stays is
    # a new problem: it keeps the verdict suspended.
    from arena_mista_riprova import spiega
    from riftbound.provenienza import revisione
    sp_file = righe.with_suffix(".spiegate.json")
    entries = json.loads(sp_file.read_text()) if sp_file.exists() else []
    entries = entries if isinstance(entries, list) else []
    todo = [r for r in rows if "divergenza" in r and not _replay_it(r) and not _spiegazione(r, entries, key)
            and (r["seed"], r["rust_seat"]) not in spiegate]
    if todo:
        say(f"   riprova automatica di {len(todo)} divergenze nelle ricerche, col codice attuale")
        commit = revisione()["commit"]
        by_game = {(r["seed"], r["rust_seat"]): r for r in todo}
        with Pool(min(args.workers, len(todo)), initializer=_init) as pool:
            for x in pool.imap_unordered(spiega, [(r, args.ckpt) for r in todo]):
                r = by_game[(x["seed"], x["rust_seat"])]
                if x["identica"]:
                    entries.append({"seed": r["seed"], "rust_seat": r["rust_seat"], "impronta": _impronta(r),
                                    "configurazione": key, "causa": "riprova identica col codice attuale",
                                    "commit": commit})
                    say(f"   seme {x['seed']} posto Rust {x['rust_seat']}: spiegata (identica col codice attuale)")
                else:
                    say(f"   seme {x['seed']} posto Rust {x['rust_seat']}: NON spiegata, {json.dumps(x['dettaglio'])[:600]}")
        sp_file.write_text(json.dumps(entries, indent=1))
    spiegate = spiegate | {(r["seed"], r["rust_seat"]) for r in rows if "divergenza" in r and _spiegazione(r, entries, key)}
    ver = valuta(rows, seeds, args.coppie, args.soglia, spiegate)
    if spiegate:
        say("   divergenze spiegate (contano): " + ", ".join(f"seme {s} posto Rust {p}" for s, p in sorted(spiegate)))
    div, missing, pairs, complete = ver["divergenti"], ver["mancanti"], ver["coppie"], ver["completo"]
    if not pairs:
        say(f"   nessuna coppia completa; divergenti {len(div)}, mancanti o in errore {len(missing)}")
        say("   Esito: SOSPESO")
        return
    rows = ver["valide"]
    m, h = ver["media"], ver["mezzo_ic"]
    cells = []
    for seat, deck in (("A", "Evelynn"), ("B", "Kha'Zix")):
        for starter, who in (("a", "Evelynn"), ("b", "Kha'Zix")):
            xs = [r["score"] for r in rows if r["rust_seat"] == seat and r["starter"] == starter]
            cells.append(f"Rust con {deck}, comincia {who} {sum(xs) / max(1, len(xs)):.3f}")
    say(f"   {len(pairs)} coppie complete su {args.coppie}{'' if complete else ' (parziale)'}: punteggio del bot "
        f"Rust {m:.4f} +- {h:.4f} (limite inferiore "
        f"{m - h:.4f}); " + "; ".join(cells))
    allc: dict = {}
    for r in rows:
        for k, v in r.get("iterazioni", {}).items():
            allc.setdefault(k, []).extend(v)
    for k in sorted(allc):
        v = allc[k]
        say(f"   iterazioni {k}: {len(v)} ricerche, media {sum(v) / len(v):.1f}, P10 {_pct(v, .1)}, "
            f"mediana {_pct(v, .5)}, P90 {_pct(v, .9)}")
    say(f"   partite verificate a ogni passo: {sum(1 for r in rows if 'eventi' in r)}; divergenti: {len(div)}; "
        f"mancanti o in errore: {len(missing)}")
    if div:
        say(f"   Esito: {ver['esito']} ({len(div)} partite divergenti da riprodurre e spiegare)")
    elif not complete:
        say(f"   Esito: {ver['esito']} (campione incompleto: {len(missing)} partite mancanti o in errore; rilanciare)")
    else:
        say(f"   Esito: {ver['esito']} {args.budget_rust} s per Evelynn-Kha'Zix (limite inferiore {m - h:.4f}, "
            f"soglia {args.soglia})" + ("" if check else "; SENZA controlli di traccia e ricerche"))
    if args.tempo_produzione > 0 and not args.ckpt.startswith("seme:"):
        from riftbound.rs.arena_rs import game as rs_game
        walls = []
        for k in range(args.tempo_produzione):
            s = 79_000 + k
            w0 = time.perf_counter()
            rs_game((s, "a" if s % 2 == 0 else "b", "A", "prior_ppo", args.ckpt, "prior_ppo", args.ckpt, "EK",
                     args.budget_rust, args.budget_rust))
            walls.append(time.perf_counter() - w0)
        say(f"   tempo reale per partita sul percorso Rust di produzione (entrambi a {args.budget_rust} s, un "
            f"processo, {len(walls)} partite): mediana {sorted(walls)[len(walls) // 2]:.2f} s")
    say(f"   {(time.time() - t0) / 60:.0f} min da questo lancio")


if __name__ == "__main__":
    main()
