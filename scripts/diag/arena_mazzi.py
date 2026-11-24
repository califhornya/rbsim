#!/usr/bin/env python
"""Arena su più matchup (22-23/11, docs/PIANO_FORZA.md): il bot a mano con i
prior di una rete (--ckpt) contro il bot a mano con i prior del campione
(--ckpt-avversario); 0,4 s per mossa a entrambi, la stessa ricerca
(scripts/diag/arena_bot.py, candidato prior_ppo).

Per matchup --coppie seed nuovi (mu=n; default 800 per i --vecchi, 300 per
gli altri), da --seed0 + 1.000 x l'indice del matchup in ORDER; due partite
per seed con la stessa apertura e i piloti scambiati; chi comincia
bilanciato (seed pari: il primo mazzo del matchup).
Regole fissate prima, IC 95% sulle medie di coppia:
  ciascuno dei --vecchi tiene se il limite inferiore è > 0,47;
  ciascun blocco di --blocchi (matchup separati da virgole, a pesi uguali)
    fa >= 0,52 con limite inferiore > 0,50;
  tutte -> PROMOSSO, il candidato diventa il campione.
Ogni partita finita va in --righe (jsonl): rilanciato, riprende.

Rengar (22/11): --vecchi EK --blocchi ER,KR --coppie EK=600 ER=400 KR=400
--seed0 30000 (allora ER e KR insieme sulle coppie, non a pesi uguali).

  uv run --extra rl python scripts/diag/arena_mazzi.py --ckpt a.pt --ckpt-avversario b.pt \\
      --vecchi EK ER KR --blocchi EI,KI,RI ES,KS,RS,IS --out runs/sett/ARENA.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/diag"))

import arena_bot as A  # noqa: E402
import bootstrap_net as B  # noqa: E402

ORDER = ("EK", "ER", "KR", "EI", "KI", "RI", "ES", "KS", "RS", "IS")


def _sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16] if Path(path).exists() else "-"


def _block(parts: list) -> tuple:
    """Equal-weight mean of independent estimates (m, h): h adds in quadrature."""
    return sum(m for m, _ in parts) / len(parts), sum(h * h for _, h in parts) ** 0.5 / len(parts)


def _game(job):
    """A game on the engine its matchup plays on (--motore)."""
    engine, task = job
    if engine == "rust":
        from riftbound.rs.arena_rs import game
        return game(task)
    return A._game(task)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="i prior PPO del candidato")
    ap.add_argument("--ckpt-avversario", required=True, help="i prior PPO del campione")
    ap.add_argument("--vecchi", nargs="*", choices=ORDER, default=["EK", "ER", "KR"])
    ap.add_argument("--blocchi", nargs="*", default=["EI,KI,RI", "ES,KS,RS,IS"])
    ap.add_argument("--coppie", nargs="*", default=[], help="mu=n, per esempio EK=800 EI=300")
    ap.add_argument("--seed0", type=int, default=40_000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--righe", type=Path, default=None, help="default: --out con estensione .jsonl")
    ap.add_argument("--esito-positivo", default="PROMOSSO", help="la parola dell'esito quando le regole passano")
    ap.add_argument("--esito-negativo", default=None, help="e quando non passano (default: non + la positiva)")
    ap.add_argument("--tenuta", nargs="*", default=[],
                    help="blocchi (matchup separati da virgole) che, a pesi uguali, devono avere limite inferiore > 0,47")
    ap.add_argument("--budget-candidato", type=float, default=None, help="secondi di CPU per mossa (default 0,4)")
    ap.add_argument("--budget-avversario", type=float, default=None, help="secondi di CPU per mossa (default 0,4)")
    ap.add_argument("--motore", choices=("python", "rust"), default="python",
                    help="rust: i matchup coperti dal motore Rust (arena_rs.COPERTI: i cinque mazzi fra loro, riconosciuti dal contenuto delle "
                         "liste) giocano su Rust (riftbound/rs/arena_rs.py), gli altri su Python")
    args = ap.parse_args()
    from riftbound.ai.ppo.collect import DECK_NAME
    blocks = [b.split(",") for b in args.blocchi]
    holds = [b.split(",") for b in args.tenuta]
    mus = list(dict.fromkeys(args.vecchi + [mu for b in blocks + holds for mu in b]))
    if any(mu not in ORDER for mu in mus):
        sys.exit(f"matchup sconosciuto; quelli noti: {' '.join(ORDER)}")
    pairs = {mu: 800 if mu in args.vecchi else 300 for mu in mus}
    pairs.update({k: int(v) for k, v in (c.split("=") for c in args.coppie)})
    s0 = {mu: args.seed0 + 1_000 * ORDER.index(mu) for mu in mus}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    righe = args.righe or args.out.with_suffix(".jsonl")

    def say(text: str) -> None:
        print(text, flush=True)
        with open(args.out, "a") as f:
            f.write(text + "\n")

    def name(mu: str) -> str:
        return f"{DECK_NAME[mu[0]]}-{DECK_NAME[mu[1]]}"

    say(f"\n== Arena su {len(mus)} matchup ({time.strftime('%d/%m %H:%M')})")
    say(f"candidato: il bot a mano con i prior PPO di {args.ckpt} (sha256 {_sha(args.ckpt)}); avversario: il "
        f"bot a mano con i prior PPO di {args.ckpt_avversario} (sha256 {_sha(args.ckpt_avversario)}); "
        f"{args.budget_candidato or A.REF_BUDGET} s per mossa al candidato, "
        f"{args.budget_avversario or A.REF_BUDGET} s all'avversario; {args.workers} processi")
    say(f"regole fissate prima: ciascuno di {' '.join(args.vecchi) or '-'} limite inferiore > 0,47; ciascun blocco "
        f"({'; '.join(' '.join(b) for b in blocks) or '-'}), a pesi uguali, >= 0,52 e limite inferiore > 0,50; "
        + (f"ciascun blocco di tenuta ({'; '.join(' '.join(b) for b in holds)}), a pesi uguali, limite inferiore "
           f"> 0,47; " if holds else "") +
        f"tutte -> {args.esito_positivo.lower()}")
    say("   " + "; ".join(f"{mu} {pairs[mu]} coppie, seed {s0[mu]}-{s0[mu] + pairs[mu] - 1}" for mu in mus))
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.provenienza import REGOLE_PYTHON, file_sha, provenienza, registra
    if args.motore == "rust":
        import riftbound_rs  # noqa: F401  (the extension must be there: no silent fallback)
        from riftbound.rs.arena_rs import coperto
        motore = {mu: "rust" if coperto(mu) else "python" for mu in mus}
    else:
        motore = {mu: "python" for mu in mus}
    sha_c, sha_a = file_sha(args.ckpt), file_sha(args.ckpt_avversario)
    registra(args.out.parent, provenienza(
        motore=motore, liste={k: DECK_OF[k] for k in sorted({c for mu in mus for c in mu})},
        checkpoint={"candidato": args.ckpt, "avversario": args.ckpt_avversario},
        arena=str(args.out), budget={"candidato": args.budget_candidato or A.REF_BUDGET,
                                     "avversario": args.budget_avversario or A.REF_BUDGET}))
    say(f"   provenienza in {args.out.parent / 'provenienza.jsonl'}; motore: "
        + ", ".join(f"{mu} {m}" for mu, m in motore.items()))

    tasks = [(s, "a" if s % 2 == 0 else "b", seat, "prior_ppo", args.ckpt, "prior_ppo", args.ckpt_avversario, mu,
              args.budget_candidato, args.budget_avversario)
             for mu in mus for s in range(s0[mu], s0[mu] + pairs[mu]) for seat in ("A", "B")]
    rows: list = []
    if righe.exists():
        for line in open(righe):
            r = json.loads(line)
            # Only comparable results: same checkpoints (path and, when recorded, hash),
            # budgets, engine and rules (rows before 24/11 have neither: Python, 6427b90).
            if r["ckpt"] == args.ckpt and r["avversario"] == args.ckpt_avversario and \
                    r.get("budget_c") == args.budget_candidato and r.get("budget_a") == args.budget_avversario and \
                    r.get("motore", "python") == motore.get(r["mu"], "python") and \
                    r.get("regole", REGOLE_PYTHON) == REGOLE_PYTHON and \
                    r.get("sha_c", sha_c) == sha_c and r.get("sha_a", sha_a) == sha_a:
                rows.append((r["seed"], r["starter"], r["seat"], r["score"], r["mu"]))
    done = {(r[0], r[2], r[4]) for r in rows}
    todo = [t for t in tasks if (t[0], t[2], t[7]) not in done]
    if rows:
        say(f"   ripresa: {len(rows)} partite già giocate, {len(todo)} da giocare")
    t0 = time.time()
    iters: dict = {"candidato": [], "avversario": []}      # this launch's games only
    with Pool(args.workers, initializer=B._init) as pool, open(righe, "a") as f:
        for task, r in zip(todo, pool.imap(_game, [(motore[t[7]], t) for t in todo])):
            mu = task[7]
            rows.append((r[0], r[1], r[2], r[3], mu))
            iters["candidato"] += r[4]
            iters["avversario"] += r[5]
            row = {"ckpt": args.ckpt, "avversario": args.ckpt_avversario, "seed": r[0],
                   "starter": r[1], "seat": r[2], "score": r[3], "mu": mu, "motore": motore[mu],
                   "regole": REGOLE_PYTHON, "sha_c": sha_c, "sha_a": sha_a}
            if args.budget_candidato is not None or args.budget_avversario is not None:
                row |= {"budget_c": args.budget_candidato, "budget_a": args.budget_avversario}
            f.write(json.dumps(row) + "\n")
            f.flush()
            if len(rows) % 100 == 0:
                print(f"   ... {len(rows)}/{len(tasks)} partite, {(time.time() - t0) / 60:.0f} min", flush=True)
    rows = [r for r in rows if r[4] in mus and s0[r[4]] <= r[0] < s0[r[4]] + pairs[r[4]]]

    est = {}
    for mu in mus:
        by: dict = {}
        for seed, _, _, s, m_ in rows:
            if m_ == mu:
                by.setdefault(seed, []).append(s)
        m, h = B._mean_ci([sum(v) / len(v) for v in by.values()])
        est[mu] = (m, h)
        a, b = DECK_NAME[mu[0]], DECK_NAME[mu[1]]
        cells = []
        for seat, deck in (("A", a), ("B", b)):
            for starter, who in (("a", a), ("b", b)):
                xs = [r[3] for r in rows if r[4] == mu and r[2] == seat and r[1] == starter]
                cells.append(f"con {deck}, comincia {who} {sum(xs) / max(1, len(xs)):.2f}")
        say(f"   {name(mu)}: {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f}); " + "; ".join(cells))
    ok = True
    verdicts = []
    for mu in args.vecchi:
        m, h = est[mu]
        good = m - h > 0.47
        ok &= good
        verdicts.append(f"{name(mu)} tiene: {'SÌ' if good else 'no'} (limite inferiore {m - h:.3f}, soglia 0,47)")
    for b in blocks:
        m, h = _block([est[mu] for mu in b])
        good = m >= 0.52 and m - h > 0.50
        ok &= good
        say(f"   blocco {' '.join(b)} a pesi uguali: {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f})")
        verdicts.append(f"blocco {' '.join(b)}: {'SÌ' if good else 'no'} (punteggio {m:.3f}, limite inferiore "
                        f"{m - h:.3f})")
    for b in holds:
        m, h = _block([est[mu] for mu in b])
        good = m - h > 0.47
        ok &= good
        say(f"   tenuta {' '.join(b)} a pesi uguali: {m:.3f} +- {h:.3f} ({m - h:.3f}-{m + h:.3f})")
        verdicts.append(f"tenuta {' '.join(b)}: {'SÌ' if good else 'no'} (limite inferiore {m - h:.3f}, soglia 0,47)")
    for v in verdicts:
        say(f"   {v}")
    for who, xs in iters.items():
        if xs:
            say(f"   {who}: {sum(xs) / len(xs):.0f} iterazioni per decisione del turno (partite di questo lancio)")
    say(f"   {(time.time() - t0) / 60:.0f} min da questo lancio")
    say(f"   Esito: {args.esito_positivo if ok else (args.esito_negativo or 'non ' + args.esito_positivo.lower())}")


if __name__ == "__main__":
    main()
