#!/usr/bin/env python
"""Calibrare il campione della pagina (regole 6427b90+D72-D77, solo Rust).

La pagina gioca il campione a lavoro fisso (ITERAZIONI_CAMPIONE, oggi 42) con la
prova di vittoria; l'arena gioca a 0,030 s di CPU per mossa. Tre misure:

  misura  --partite G   campione@42+probe contro campione@0,030 s+probe (posti
                        scambiati): iterazioni a 0,030 s e secondi a 42 per tipo
                        di punto (turno / reazione / showdown); N suggerito =
                        mediana delle iterazioni del turno a 0,030 s.
  forza   --coppie ES=400 EK=400 [--iterazioni 42]
                        campione@N+probe contro campione@0,030 s+probe: non
                        inferiore se il limite inferiore dell'IC 95% > 0,47
                        (come la promozione del 24/11, RAPPORTO_ARENA.md).
  profilo --coppie ES=200 EK=200
                        campione@0,030 s contro il bot a mano senza prior
                        @0,030 s (stessa prova di vittoria), IC 95%.

  python scripts/rust/calibra_campione.py misura --ckpt C.pt --matchup ES EK --partite 20 --out DIR
  python scripts/rust/calibra_campione.py forza --pesi-casuali --coppie EK=4 --out DIR

Con --pesi-casuali una rete a pesi casuali (seed 1) al posto del checkpoint.
Semi (nuovi, mai usati dalle altre misure): misura da 78000, forza da 80000, profilo
da 82000, piu' 1000 x l'indice del matchup in ORDER. File completi in --out.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REGOLE = "6427b90+D72-D77"
ORDER = ("EK", "ER", "KR", "EI", "KI", "RI", "ES", "KS", "RS", "IS")
BUDGET = 0.030
SEME = {"misura": 78_000, "forza": 80_000, "profilo": 82_000}
TIPI = {"turn_action": "turno", "reaction": "reazione", "showdown_action": "showdown"}
SOGLIA = 0.47


def _init():
    try:
        from riftbound.compute import be_gentle
        be_gentle()
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass


def ckpt_di(args) -> str:
    """The checkpoint to use; with --pesi-casuali a random net saved in --out."""
    args.out.mkdir(parents=True, exist_ok=True)
    if args.pesi_casuali:
        import torch
        from riftbound.ai.ppo.model import PPONet, save
        path = args.out / "net_casuale.pt"
        if not path.exists():
            torch.manual_seed(1)
            save(PPONet(), path)
        return str(path)
    if not args.ckpt or not Path(args.ckpt).is_file():
        sys.exit(f"manca il checkpoint {args.ckpt} (--ckpt, oppure --pesi-casuali)")
    return str(Path(args.ckpt).resolve())


def pct(xs: list, q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, math.ceil(q * len(xs)) - 1)]


def riassunto(xs: list) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mediana": statistics.median(xs), "p90": pct(xs, 0.9)}


def media_ic(punteggi: dict) -> tuple:
    """Mean and 95% half-width of the pair means (bootstrap_net._mean_ci)."""
    xs = [sum(v) / len(v) for v in punteggi.values()]
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))
    return m, 1.96 * sd / math.sqrt(len(xs))


def _gioca(task):
    from riftbound.rs.arena_rs import game
    return game(task)


def misura(args) -> None:
    ckpt = ckpt_di(args)
    n = args.iterazioni
    opz = {"iter_cand": n, "probe_cand": True, "probe_opp": True, "log": True}
    t0 = time.time()
    per_mu: dict = {}
    righe = []
    with Pool(args.workers, initializer=_init) as pool:
        for mu in args.matchup:
            s0 = SEME["misura"] + 1_000 * ORDER.index(mu)
            tasks = [(s, "a" if s % 2 == 0 else "b", seat, "prior_ppo", ckpt, "prior_ppo", ckpt, mu, None, BUDGET, opz)
                     for s in range(s0, s0 + max(1, (args.partite + 1) // 2)) for seat in ("A", "B")]
            iters = {t: [] for t in TIPI.values()}       # opponent, budget 0,030 s
            secs = {t: [] for t in TIPI.values()}        # candidate, N iterations
            sonda = []                                   # candidate: win probe seconds before a turn search
            for r in pool.imap(_gioca, tasks):
                lg = r[8]["log"]
                for punto, _turno, it, sec, _ in lg["opp"]:
                    iters[TIPI[punto]].append(it)
                for punto, _turno, it, sec, ps in lg["cand"]:
                    secs[TIPI[punto]].append(sec)
                    if punto == "turn_action":
                        sonda.append(ps)
                righe.append({"mu": mu, "seed": r[0], "seat": r[2], "score": r[3], "log": lg})
            per_mu[mu] = {"partite": len(tasks), "seme0": s0,
                          "iterazioni_a_0030s": {t: riassunto(v) for t, v in iters.items()},
                          f"secondi_a_{n}_iterazioni": {t: riassunto(v) for t, v in secs.items()},
                          "secondi_probe_prima_del_turno": riassunto(sonda)}
    suggerito = {}
    for t in TIPI.values():
        pool_it = [it for mu in args.matchup for it in _vals(righe, mu, t)]
        if pool_it:
            suggerito[t] = round(statistics.median(pool_it))
    out = {"regole": REGOLE, "ckpt": ckpt, "pesi_casuali": bool(args.pesi_casuali), "budget": BUDGET,
           "iterazioni_provate": n, "matchup": per_mu, "N_suggerito": suggerito,
           "N_suggerito_per_matchup": {mu: {t: round(per_mu[mu]["iterazioni_a_0030s"][t]["mediana"])
                                            for t in TIPI.values() if per_mu[mu]["iterazioni_a_0030s"][t]["n"]}
                                       for mu in args.matchup},
           "minuti": round((time.time() - t0) / 60, 2)}
    (args.out / "misura.json").write_text(json.dumps(out, indent=1))
    with open(args.out / "misura_righe.jsonl", "w") as f:
        for r in righe:
            f.write(json.dumps(r) + "\n")
    for mu in args.matchup:
        m = per_mu[mu]
        it = m["iterazioni_a_0030s"]
        sc = m[f"secondi_a_{n}_iterazioni"]
        print(f"misura {mu}: {m['partite']} partite; iterazioni a 0,030 s mediana/p90: "
              + ", ".join(f"{t} {it[t].get('mediana', '-')}/{it[t].get('p90', '-')}" for t in TIPI.values())
              + f"; s a {n} it.: " + ", ".join(f"{t} {_f(sc[t].get('mediana'))}/{_f(sc[t].get('p90'))}" for t in TIPI.values()))
    print(f"misura: N suggerito {suggerito}  (turno: {suggerito.get('turno', '-')}); {out['minuti']} min; {args.out / 'misura.json'}")


def _f(x):
    return "-" if x is None else f"{x:.4f}"


def _vals(righe: list, mu: str, tipo: str) -> list:
    inv = {v: k for k, v in TIPI.items()}
    return [it for r in righe if r["mu"] == mu for punto, _t, it, _s, _p in r["log"]["opp"] if punto == inv[tipo]]


def _arena(args, nome: str, extra: list, mus: list, coppie: dict, ckpt: str, avv_mano: bool) -> None:
    """scripts/diag/arena_mazzi.py on Rust; one line per matchup from its rows."""
    out = args.out / f"{nome}.txt"
    righe = args.out / f"{nome}.jsonl"
    cmd = [sys.executable, str(ROOT / "scripts/diag/arena_mazzi.py"), "--motore", "rust", "--regole", REGOLE,
           "--ckpt", ckpt, "--vecchi", *mus, "--blocchi", "--coppie", *[f"{m}={coppie[m]}" for m in mus],
           "--seed0", str(args.seed0 if args.seed0 is not None else SEME[nome]), "--workers", str(args.workers),
           "--out", str(out), "--righe", str(righe), "--esito-positivo", "NON INFERIORE", "--esito-negativo", "INFERIORE O NON DIMOSTRATO", *extra]
    cmd += ["--avversario-mano"] if avv_mano else ["--ckpt-avversario", ckpt]
    p = subprocess.run(cmd, capture_output=True, text=True)
    (args.out / f"{nome}.log").write_text(p.stdout + p.stderr)
    if p.returncode != 0:
        sys.exit(f"{nome}: arena_mazzi fallita (vedi {args.out / (nome + '.log')}): " + (p.stderr.strip().splitlines() or ["?"])[-1])
    by: dict = {mu: {} for mu in mus}
    for line in open(righe):
        r = json.loads(line)
        if r["mu"] in by:
            by[r["mu"]].setdefault(r["seed"], []).append(r["score"])
    esiti = {}
    for mu in mus:
        m, h = media_ic(by[mu])
        esiti[mu] = {"coppie": len(by[mu]), "media": round(m, 4), "ic95": round(h, 4), "lim_inf": round(m - h, 4)}
    s0 = args.seed0 if args.seed0 is not None else SEME[nome]
    (args.out / f"{nome}.json").write_text(json.dumps(
        {"regole": REGOLE, "ckpt": ckpt, "pesi_casuali": bool(args.pesi_casuali), "seme0": s0, "matchup": esiti}, indent=1))
    for mu in mus:
        e = esiti[mu]
        verdetto = ""
        if nome == "forza":
            verdetto = f"; non inferiore (lim. inf. > {SOGLIA}): " + ("SI" if e["lim_inf"] > SOGLIA else "NO")
        print(f"{nome} {mu}: {e['media']:.3f} +- {e['ic95']:.3f} (lim. inf. {e['lim_inf']:.3f}), {e['coppie']} coppie{verdetto}")


def _coppie(args, default: int) -> tuple:
    coppie = {}
    for c in args.coppie:
        mu, n = c.split("=")
        if mu not in ORDER:
            sys.exit(f"matchup sconosciuto {mu}; noti: {' '.join(ORDER)}")
        coppie[mu] = int(n)
    return list(coppie), coppie


def forza(args) -> None:
    ckpt = ckpt_di(args)
    mus, coppie = _coppie(args, 400)
    extra = ["--iterazioni-candidato", str(args.iterazioni), "--win-probe-candidato",
             "--budget-avversario", str(BUDGET), "--win-probe-avversario"]
    _arena(args, "forza", extra, mus, coppie, ckpt, False)


def profilo(args) -> None:
    ckpt = ckpt_di(args)
    mus, coppie = _coppie(args, 200)
    extra = ["--budget-candidato", str(BUDGET), "--win-probe-candidato",
             "--budget-avversario", str(BUDGET), "--win-probe-avversario"]
    _arena(args, "profilo", extra, mus, coppie, ckpt, True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("misura", "forza", "profilo"):
        sp = sub.add_parser(nome)
        sp.add_argument("--ckpt", default=None)
        sp.add_argument("--pesi-casuali", action="store_true")
        sp.add_argument("--out", type=Path, required=True)
        sp.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
        sp.add_argument("--iterazioni", type=int, default=42, help="le iterazioni della pagina (default 42)")
        if nome == "misura":
            sp.add_argument("--matchup", nargs="+", default=["ES", "EK"])
            sp.add_argument("--partite", type=int, default=20, help="per matchup (posti scambiati)")
        else:
            sp.add_argument("--coppie", nargs="+", required=True, help="mu=n, per esempio ES=400 EK=400")
            sp.add_argument("--seed0", type=int, default=None)
    args = ap.parse_args()
    os.environ["RBSIM_REGOLE"] = REGOLE
    import riftbound_rs  # noqa: F401  (l'estensione deve esserci: niente ripiego su Python)
    {"misura": misura, "forza": forza, "profilo": profilo}[args.cmd](args)


if __name__ == "__main__":
    main()
