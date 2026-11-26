"""Prima generazione (Astra, 26/11): una partita della rete aggiornata contro il campione, con registro leggibile, e
l'arena di sviluppo (rete nuova contro il campione, posti scambiati, lavoro fisso).

Il campione e' il bot a mano coi prior di `ckpt_040000`, alle stesse impostazioni di ricerca del candidato (138
iterazioni, win_probe, valutazione `rimonta`): cambiano solo la rete e, nella variante (c), il peso del valore.
Candidato (b): rete nuova + `rimonta`; candidato (c): rete nuova con 80% `rimonta` + 20% valore della rete nelle foglie
(`peso_valore_rete` 0,2; la valutazione a mano sola sul Pass che chiude il turno).

Punteggio di una partita 1 / 1/2 / 0 dal lato del candidato; di una coppia (stesso seme e apertura, posti scambiati) la
media delle due; di un matchup la media delle coppie; totale = media a pesi uguali fra i matchup. Intervallo al 95%:
ricampionamento (bootstrap, 4000 estrazioni, seme fisso) di coppie intere dentro ogni matchup.
Semi: BASE_SEME_SVILUPPO + 1.000 x indice del matchup + k (distinti da raccolta 30.000.000 e promozione 40.000).
"""
from __future__ import annotations

import json
import multiprocessing
import os
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE_SEME_SVILUPPO = 40_000_000
ITERAZIONI = 138
PESO_VALORE = 0.2
VARIANTI = {"b": 0.0, "c": PESO_VALORE}
ETICHETTE = {"b": "(b) rete nuova + rimonta", "c": "(c) rete nuova, 80% rimonta + 20% valore"}


def _opz(peso: float, iterazioni: int, log: bool) -> dict:
    from riftbound.ai.coach_rs import VALUTAZIONE_ALPHA, VALUTAZIONE_K
    val = ["rimonta", VALUTAZIONE_K, VALUTAZIONE_ALPHA]
    o = {"iter_cand": iterazioni, "iter_opp": iterazioni, "probe_cand": True, "probe_opp": True,
         "val_cand": val, "val_opp": val, "log": log}
    if peso > 0:
        o["vr_cand"] = peso
    return o


# -- una partita con registro leggibile ---------------------------------------------------------

def partita_leggibile(rete: str, campione: str, regole: str, seme: int, mu: str, posto: str = "A",
                      iterazioni: int = ITERAZIONI, peso: float = 0.0) -> dict:
    """Rete nuova (posto `posto`) contro il campione, stesse impostazioni. -> {"esito","vincitore","turni","righe",
    "secondi"}: `righe` = il registro leggibile (una riga per decisione: turno, posto, punto, punti, menu, scelta)."""
    from riftbound.ai.coach_rs import VALUTAZIONE_ALPHA, VALUTAZIONE_K
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import arena_rs, rust_bridge as rb
    os.environ["RBSIM_REGOLE"] = regole
    t0 = time.perf_counter()
    g = rb.build(seme, Path(DECK_OF[mu[0]]), Path(DECK_OF[mu[1]]), "a" if seme % 2 == 0 else "b", arena_rs.MAX_TURNS)
    for seat in ("A", "B"):
        nuova = seat == posto
        g.set_search_agent(seat, iterazioni, seme * 2 + (seat == "B"), None,
                           arena_rs._probs_for(rete if nuova else campione, nuova and peso > 0), False)
        g.set_search_win_probe(seat, True)
        g.set_search_valutazione(seat, "rimonta", VALUTAZIONE_K, VALUTAZIONE_ALPHA)
        if nuova and peso > 0:
            g.set_search_valore_rete(seat, peso)
    g.set_side_chooser()
    g.trace_on()
    vincitore, turni = g.start()
    righe = []
    for e in json.loads(g.events()):
        if e["k"] != "decision":
            continue
        w = e.get("win") or {}
        menu = e.get("menu") or []
        i = e.get("index")
        scelta = menu[i] if isinstance(i, int) and 0 <= i < len(menu) else "?"
        righe.append(f"T{w.get('turn')} {e['seat']}{'*' if e['seat'] == posto else ' '} {e['point']:<13} "
                     f"punti A-B {w.get('points', ['?', '?'])[0]}-{w.get('points', ['?', '?'])[1]}  "
                     f"[{len(menu)} voci] -> {scelta}")
    esito = 0.5 if vincitore == "DRAW" else 1.0 if vincitore == posto else 0.0
    return {"esito": esito, "vincitore": vincitore, "turni": turni, "righe": righe,
            "secondi": round(time.perf_counter() - t0, 2), "seme": seme, "matchup": mu, "posto_nuova": posto}


# -- l'arena di sviluppo ------------------------------------------------------------------------

def _gioca(job: dict) -> dict:
    """Una partita dell'arena (in un processo): arena_rs.game con le opzioni della variante."""
    import torch
    torch.set_num_threads(1)
    os.environ["RBSIM_REGOLE"] = job["regole"]
    from riftbound.rs import arena_rs
    seme, mu, posto, v = job["seme"], job["mu"], job["posto"], job["variante"]
    r = arena_rs.game((seme, "a" if seme % 2 == 0 else "b", posto, "prior_ppo", job["rete"], "prior_ppo",
                       job["campione"], mu, None, None, _opz(VARIANTI[v], job["iterazioni"], True)))
    log = r[8].get("log", {})
    return {"variante": v, "mu": mu, "seme": seme, "posto": posto, "score": r[3], "secondi_ricerca": {
        lato: [[riga[0], riga[2], riga[3], riga[4]] for riga in log.get(lato, [])] for lato in ("cand", "opp")},
            "rete": r[8].get("rete")}


def intervallo(punteggi: dict, rng, n_boot: int = 4000):
    """punteggi {matchup: array delle medie di coppia} -> (media a pesi uguali, basso, alto, {matchup: (m, lo, hi)})."""
    mus = list(punteggi)
    medie = {mu: float(np.mean(p)) for mu, p in punteggi.items()}
    tot = float(np.mean(list(medie.values())))
    boot = np.zeros((n_boot, len(mus)))
    for j, mu in enumerate(mus):
        p = np.asarray(punteggi[mu], dtype=float)
        boot[:, j] = p[rng.integers(0, len(p), size=(n_boot, len(p)))].mean(axis=1)
    lo_hi = np.percentile(boot.mean(axis=1), [2.5, 97.5])
    per = {mu: (medie[mu], *map(float, np.percentile(boot[:, j], [2.5, 97.5]))) for j, mu in enumerate(mus)}
    return tot, float(lo_hi[0]), float(lo_hi[1]), per


def durata(righe_ricerca: list) -> dict:
    """Secondi di CPU per decisione cercata (media, mediana, 95 percentile), per punto e in tutto."""
    out = {}
    per = defaultdict(list)
    for punto, iters, secs, probe in righe_ricerca:
        per[punto].append(secs)
        per["tutte"].append(secs)
    for k, v in per.items():
        a = np.asarray(v)
        out[k] = {"n": len(a), "media": float(a.mean()), "mediana": float(np.median(a)),
                  "p95": float(np.percentile(a, 95))}
    return out


def arena(rete: str, campione: str, matchup, coppie: int, regole: str, righe: Path, processi: int,
          iterazioni: int = ITERAZIONI, varianti=("b", "c"), scrivi=print) -> dict:
    """L'arena di sviluppo; le partite finite vanno in `righe` (jsonl) e un rilancio riprende."""
    from filelock import FileLock
    from riftbound.provenienza import checkpoint_sha256, scrivi_json_atomico
    from riftbound.rs.arena_rs import COPERTI, MAX_TURNS
    righe.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    config = {"rete_sha256": checkpoint_sha256(rete), "campione_sha256": checkpoint_sha256(campione),
              "regole": regole, "iterazioni": iterazioni, "max_turni": MAX_TURNS, "base_seme": BASE_SEME_SVILUPPO,
              "ricerca": {v: _opz(peso, iterazioni, False) for v, peso in VARIANTI.items()}}
    manifest = righe.with_name(righe.name + ".provenienza.json")
    with FileLock(str(righe) + ".rbsim.lock", timeout=0):
        if manifest.exists():
            if json.loads(manifest.read_text()) != config:
                raise ValueError(f"Configurazione arena incompatibile con {manifest}. Usare una nuova uscita.")
        elif righe.is_file() and righe.stat().st_size:
            raise ValueError(f"Arena senza provenienza: {righe}. Usare una nuova uscita.")
        else:
            scrivi_json_atomico(manifest, config)
        fatte = _partite_arena(rete, campione, matchup, coppie, regole, righe, processi, iterazioni, varianti, scrivi)
    rng = np.random.default_rng(0)
    res = {"configurazione": config, "regole": regole, "iterazioni": iterazioni,
           "coppie_per_matchup": coppie, "matchup": list(matchup),
           "base_seme": BASE_SEME_SVILUPPO, "rete": rete, "campione": campione, "varianti": {}}
    for v in varianti:
        punti, ricerche = {}, {"cand": [], "opp": []}
        chiamate = {"cand": [0, 0], "opp": [0, 0]}
        for mu in matchup:
            s0 = BASE_SEME_SVILUPPO + 1_000 * COPERTI.index(mu)
            coppie_mu = []
            for k in range(coppie):
                a, b = fatte[(v, mu, s0 + k, "A")], fatte[(v, mu, s0 + k, "B")]
                coppie_mu.append((a["score"] + b["score"]) / 2)
                for r in (a, b):
                    for lato in ("cand", "opp"):
                        ricerche[lato] += r["secondi_ricerca"][lato]
                    for lato, c in (r.get("rete") or {}).items():
                        chiamate[lato][0] += c[0]
                        chiamate[lato][1] += c[1]
            punti[mu] = np.array(coppie_mu)
        tot, lo, hi, per = intervallo(punti, rng)
        res["varianti"][v] = {"etichetta": ETICHETTE[v], "peso_valore_rete": VARIANTI[v], "totale": [tot, lo, hi],
                              "matchup": {mu: list(x) for mu, x in per.items()},
                              "durata_per_mossa_s": {"candidato": durata(ricerche["cand"]),
                                                     "campione": durata(ricerche["opp"])},
                              "chiamate_rete": {"candidato": chiamate["cand"], "campione": chiamate["opp"]}}
    res["minuti"] = round((time.time() - t0) / 60, 1)
    return res


def _partite_arena(rete, campione, matchup, coppie, regole, righe, processi, iterazioni, varianti, scrivi):
    from riftbound.rs.arena_rs import COPERTI
    fatte = {}
    if righe.is_file():
        for x in righe.read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                fatte[(r["variante"], r["mu"], r["seme"], r["posto"])] = r
    jobs = []
    for v in varianti:
        for mu in matchup:
            s0 = BASE_SEME_SVILUPPO + 1_000 * COPERTI.index(mu)
            for k in range(coppie):
                for posto in ("A", "B"):
                    if (v, mu, s0 + k, posto) not in fatte:
                        jobs.append({"variante": v, "mu": mu, "seme": s0 + k, "posto": posto, "rete": rete,
                                     "campione": campione, "regole": regole, "iterazioni": iterazioni})
    scrivi(f"arena di sviluppo: {len(fatte)} partite gia' fatte, {len(jobs)} da giocare, {processi} processi")
    if jobs:
        os.environ["RBSIM_REGOLE"] = regole
        with ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn")) as pool, \
                open(righe, "a") as f:
            for n, r in enumerate(pool.map(_gioca, jobs), 1):
                fatte[(r["variante"], r["mu"], r["seme"], r["posto"])] = r
                f.write(json.dumps(r) + "\n")
                f.flush()
                if n % 20 == 0:
                    scrivi(f"  {n}/{len(jobs)} partite, {(time.time() - t0) / 60:.1f} min")
    return fatte


def testo_arena(res: dict) -> list[str]:
    out = [f"Arena di sviluppo: {res['coppie_per_matchup']} coppie per matchup ({', '.join(res['matchup'])}), "
           f"{res['iterazioni']} iterazioni, win_probe, rimonta, regole {res['regole']}, semi da {res['base_seme']}",
           f"rete: {res['rete']}; campione: {res['campione']}"]
    for v, r in res["varianti"].items():
        m, lo, hi = r["totale"]
        out.append(f"{r['etichetta']}: totale {m:.3f} (IC 95% {lo:.3f}-{hi:.3f}), pesi uguali fra i matchup")
        out.append("   " + "; ".join(f"{mu} {x[0]:.3f} ({x[1]:.2f}-{x[2]:.2f})" for mu, x in r["matchup"].items()))
        for chi, d in r["durata_per_mossa_s"].items():
            t = d.get("tutte")
            if t:
                tp = d.get("TurnAction") or d.get("turn_action") or {}
                out.append(f"   durata per decisione cercata, {chi}: media {t['media'] * 1000:.1f} ms, mediana "
                           f"{t['mediana'] * 1000:.1f} ms, p95 {t['p95'] * 1000:.1f} ms ({t['n']} ricerche)"
                           + (f"; di turno media {tp['media'] * 1000:.1f} ms" if tp else ""))
        c = r["chiamate_rete"]["candidato"]
        if c[0]:
            out.append(f"   chiamate della rete del candidato: {c[0]}, di cui solo per il valore {c[1]}")
    out.append(f"durata dell'arena: {res['minuti']} min")
    return out
