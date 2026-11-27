"""Scelta finale (Astra, 27/11): la mossa piu' visitata e' migliore di quella con la Q piu' alta, dallo stesso albero?

Oggi il campione (prior `ckpt_040000`, `rimonta`, 138 iterazioni, win_probe) gioca, dopo la ricerca, il figlio con la Q
piu' alta fra i visitati. Qui si prova il figlio piu' visitato (a pari visite: Q piu' alta, poi l'ordine) sulle stesse
480 posizioni di sviluppo di `seguiti` (stesse partite, stesse decisioni: `seguiti.selezionate`).

  Fase 1  `scelte(o)`: dalla riga di ricerca ORIGINALE del campione, la mossa per Q e quella per visite; la scelta per
          Q deve coincidere con la mossa giocata (`coerente`), altrimenti la decisione e' esclusa e contata.
  Fase 2  solo dove le due mosse differiscono: si giocano entrambe fino alla fine sugli stessi 32 mondi `ignote`
          (indipendenti dalla ricerca; il campione su entrambi i posti dopo la prima mossa); delta = visite - Q.
  `riassunto(...)`  ogni matchup pesa uguale, zeri compresi; intervallo 95% ricampionando PARTITE intere.
  `posizioni(...)`  tutto; scrive `riepilogo.txt` (ultima riga `totale:`), `riepilogo.json`, `esito.json`.
  `arena(...)`      se la regola di stop passa: candidato (scelta per visite) contro campione, coppie a posti scambiati.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from riftbound.rs import arena_rs, attacco as A, decisione_rs as D, generazione, seguiti as S
from riftbound.rs.seguiti import BASE_SEME, ITERAZIONI, MONDI0, N_BOOT, REGOLE, VALUTAZIONE

BASE_SEME_ARENA = 60_000_000    # la raccolta usa 30M, l'arena di sviluppo 40M, i seguiti 50M
COPPIE = 100
PER_PARTITA = 8
N_PARTITE = 6
MONDI = 32


# -- fase 1 -----------------------------------------------------------------------------------------

def scelte(o: dict, partita: dict | None = None) -> dict:
    """Da una riga di `D.originale` (`o["riga"]` = la riga di search_log: `children` = [azione, n, q, w, sub] nell'ordine
    della radice; `menu` = le azioni, nello stesso ordine delle etichette `o["menu"]`): fra i figli con n > 0, in ordine,
    la scelta per Q (il primo con la Q massima) e quella per visite (il primo che massimizza n, poi q; confronti
    stretti). `coerente`: la scelta per Q e' la mossa che il campione ha davvero giocato (`o["action"]`)."""
    riga = o["riga"]
    etichetta = {json.dumps(a): o["menu"][i] for i, a in enumerate(riga["menu"]) if i < len(o["menu"])}
    mq = mv = None
    for c in riga["children"]:
        n, q = c[1], c[2]
        if not n > 0:
            continue
        if mq is None or q > mq[2]:
            mq = (c, n, q)
        if mv is None or n > mv[1] or (n == mv[1] and q > mv[2]):
            mv = (c, n, q)
    lab_q = etichetta.get(json.dumps(mq[0][0])) if mq else None
    lab_v = etichetta.get(json.dumps(mv[0][0])) if mv else None
    ok = lab_q is not None and lab_v is not None and lab_q == o["action"]
    out = {"k": o["k"], "turno": o["turn"], "menu": o["menu"], "q": lab_q, "visite": lab_v,
           "n_q": mq[1] if mq else None, "q_q": mq[2] if mq else None,
           "n_v": mv[1] if mv else None, "q_v": mv[2] if mv else None,
           "coerente": bool(ok), "disaccordo": bool(ok and lab_q != lab_v)}
    if partita is not None:
        out = {"partita": partita, "nome": A.nome_partita(partita), "matchup": partita["matchup"]} | out
    return out


def decisioni(partita: dict, per_partita: int) -> list[dict]:
    """Le decisioni di `seguiti.selezionate`, ciascuna con la scelta per Q e quella per visite dall'albero originale."""
    return [scelte(o, partita) for o in S.selezionate(partita, per_partita)]


def _lavoro_partita(args) -> tuple[str, list[dict]]:
    partita = args[0]
    return A.nome_partita(partita), decisioni(*args)


# -- fase 2 -----------------------------------------------------------------------------------------

def gioca_decisione(dec: dict, n_mondi: int, cart: Path, processi: int = 1, mondi0: int = MONDI0) -> dict:
    """Gioca la mossa per Q e quella per visite fino alla fine sugli stessi mondi `ignote`; delta appaiati (ritorno di
    visite - ritorno di Q, dal lato di chi sceglie; 1 vittoria, 0,5 patta) nei mondi dove entrambe le righe rispettano
    la prima mossa. Scrive `mondi.jsonl` e `decisione.json` in `cart`."""
    cart = Path(cart)
    cart.mkdir(parents=True, exist_ok=True)
    pos = A.posizione(dec["partita"], dec["k"])
    linee = [A.linea_primo("q", dec["q"]), A.linea_primo("visite", dec["visite"])]
    dati = A.esegui(pos, "ignote", range(mondi0, mondi0 + n_mondi), linee, cart / "mondi.jsonl", processi,
                    lambda *_: None)
    delta, escluse = [], 0
    for rows in dati:
        r = {x["line"]: x for x in rows}
        if r["q"]["primo_ok"] and r["visite"]["primo_ok"]:
            delta.append(r["visite"]["returns"] - r["q"]["returns"])
        else:
            escluse += 1
    res = {k: dec[k] for k in ("nome", "k", "turno", "menu", "q", "visite", "n_q", "q_q", "n_v", "q_v")} | \
        {"matchup": dec["partita"]["matchup"], "deltas": delta,
         "media": float(np.mean(delta)) if delta else None, "n_mondi": len(delta), "mondi_esclusi": escluse}
    (cart / "decisione.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


# -- statistiche ------------------------------------------------------------------------------------

def _valore(r: dict):
    """Valore di una decisione: None se esclusa (incoerente, o disaccordo senza mondi validi), 0 se accordo."""
    if not r.get("coerente", True):
        return None
    if not r.get("disaccordo"):
        return 0.0
    return r.get("media")


def riassunto(rows: list[dict], n_boot: int = N_BOOT, seme: int = 0) -> dict:
    """`rows`: una riga per decisione (matchup, nome = la partita, coerente, disaccordo, media, n_mondi,
    mondi_esclusi). Valore della decisione = media dei delta (0 se le due mosse coincidono); escluse e contate le
    incoerenti e i disaccordi senza mondi validi. Matchup = media delle sue decisioni; TOTALE = media dei matchup (pesi
    uguali, zeri compresi). IC 95%: bootstrap che ricampiona PARTITE intere dentro ogni matchup (stesso numero di
    partite), matchup = media di tutte le decisioni delle partite estratte. Stesso schema per la media sui soli
    disaccordi (un unico gruppo fra i matchup). `passa`: limite inferiore del totale > 0."""
    mus = sorted({r["matchup"] for r in rows})
    inc = sum(not r.get("coerente", True) for r in rows)
    senza = sum(bool(r.get("coerente", True)) and bool(r.get("disaccordo")) and r.get("media") is None for r in rows)
    ok = [(r, v) for r in rows if (v := _valore(r)) is not None]
    dis = [(r, v) for r, v in ok if r.get("disaccordo")]
    # per matchup: una riga per partita = (somma, conteggio) su tutte le decisioni e sui soli disaccordi
    cluster = {}
    for mu in mus:
        g: dict[str, list[float]] = {}
        for r, v in ok:
            if r["matchup"] == mu:
                x = g.setdefault(r["nome"], [0.0, 0, 0.0, 0])
                x[0] += v
                x[1] += 1
                if r.get("disaccordo"):
                    x[2] += v
                    x[3] += 1
        cluster[mu] = np.array(list(g.values()), float).reshape(-1, 4)
    rng = np.random.default_rng(seme)
    boot_mu, boot_dn, boot_dd = {}, np.zeros(n_boot), np.zeros(n_boot)
    for mu in mus:
        c = cluster[mu]
        if not len(c):
            boot_mu[mu] = np.zeros(n_boot)
            continue
        idx = rng.integers(0, len(c), (n_boot, len(c)))
        num, den = c[idx, 0].sum(axis=1), c[idx, 1].sum(axis=1)
        boot_mu[mu] = np.where(den > 0, num / np.maximum(den, 1), 0.0)
        boot_dn += c[idx, 2].sum(axis=1)
        boot_dd += c[idx, 3].sum(axis=1)

    def ic(b):
        return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]

    pm = {}
    for mu in mus:
        rr = [r for r in rows if r["matchup"] == mu]
        vv = [v for r, v in ok if r["matchup"] == mu]
        coer = [r for r in rr if r.get("coerente", True)]
        nd = sum(bool(r.get("disaccordo")) for r in coer)
        pm[mu] = {"esaminate": len(rr), "incoerenti": len(rr) - len(coer), "n_decisioni": len(vv), "disaccordi": nd,
                  "tasso_disaccordo": nd / max(1, len(coer)), "media": float(np.mean(vv)) if vv else 0.0,
                  "ic95": ic(boot_mu[mu])}
    tot_boot = np.mean([boot_mu[mu] for mu in mus], axis=0) if mus else np.zeros(n_boot)
    tot = float(np.mean([pm[mu]["media"] for mu in mus])) if mus else 0.0
    ic_tot = ic(tot_boot)
    mdis = [v for _r, v in dis]
    coer_tot = [r for r in rows if r.get("coerente", True)]
    nd_tot = sum(bool(r.get("disaccordo")) for r in coer_tot)
    out = {"esaminate": len(rows), "incoerenti": inc, "senza_mondi": senza, "n_decisioni": len(ok),
           "disaccordi": nd_tot, "tasso_disaccordo": nd_tot / max(1, len(coer_tot)),
           "mondi_validi": sum(r.get("n_mondi", 0) for r in rows),
           "mondi_esclusi": sum(r.get("mondi_esclusi", 0) for r in rows),
           "totale": [tot, *ic_tot], "per_matchup": pm,
           "media_disaccordi": float(np.mean(mdis)) if mdis else None, "n_disaccordi_validi": len(mdis),
           "ic95_disaccordi": ic(np.where(boot_dd > 0, boot_dn / np.maximum(boot_dd, 1), 0.0)) if mdis else None,
           "a_favore": sum(v > 0 for v in mdis), "contro": sum(v < 0 for v in mdis), "pari": sum(v == 0 for v in mdis)}
    out["passa"] = bool(ic_tot[0] > 0)
    return out


def _pp(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f} pp"


def _testo(rs: dict, imp: dict, secondi: float) -> list[str]:
    t, lo, hi = rs["totale"]
    righe = [f"Scelta finale: mossa piu' visitata contro mossa con Q piu' alta, dallo stesso albero del campione "
             f"{imp['ckpt']}, {imp['iterazioni']} iterazioni, valutazione {VALUTAZIONE}, regole {imp['regole']}",
             f"partite {imp['partite']}, al piu' {imp['per_partita']} decisioni per partita, {imp['mondi']} mondi per "
             f"decisione, {imp['n_boot']} ricampionamenti di partite intere",
             f"decisioni esaminate {rs['esaminate']} (incoerenti: {rs['incoerenti']}, disaccordi senza mondi validi: "
             f"{rs['senza_mondi']}); con mossa diversa {rs['disaccordi']} ({100 * rs['tasso_disaccordo']:.1f}% delle "
             f"coerenti)",
             f"visite - Q, totale (ogni matchup pesa uguale, accordi = 0): {_pp(t)} (IC 95% da {100 * lo:+.1f} a "
             f"{100 * hi:+.1f})"]
    if rs["media_disaccordi"] is None:
        righe.append("nessun disaccordo con mondi validi: niente differenza da stimare")
    else:
        a, b = rs["ic95_disaccordi"]
        righe.append(f"visite - Q sui soli disaccordi: {_pp(rs['media_disaccordi'])} (IC 95% da {100 * a:+.1f} a "
                     f"{100 * b:+.1f}); a favore {rs['a_favore']}, contro {rs['contro']}, pari {rs['pari']}")
    righe.append(f"mondi giocati validi {rs['mondi_validi']}; esclusi {rs['mondi_esclusi']} (la prima mossa forzata non "
                 f"e' quella chiesta)")
    righe.append("per matchup (esaminate, incoerenti, disaccordi, tasso, visite - Q con IC 95%):")
    for mu, m in rs["per_matchup"].items():
        righe.append(f"  {mu}: {m['esaminate']}, {m['incoerenti']}, {m['disaccordi']}, "
                     f"{100 * m['tasso_disaccordo']:.1f}%, {_pp(m['media'])} "
                     f"({100 * m['ic95'][0]:+.1f} a {100 * m['ic95'][1]:+.1f})")
    righe.append("regola di stop: PASSA (limite inferiore > 0): arena" if rs["passa"] else
                 "regola di stop: NON PASSA: resta la scelta per Q")
    righe.append(f"totale: {rs['esaminate']} decisioni, {rs['disaccordi']} disaccordi, {_pp(t)}, {secondi / 60:.1f} min")
    return righe


# -- la corsa -----------------------------------------------------------------------------------------

def _controlla_impostazioni(out_dir: Path, ckpt, casuali, regole, iterazioni, n_partite, per_partita, n_mondi) -> None:
    """Scrive `impostazioni.json` alla prima corsa; un rilancio nella stessa cartella riprende solo con le stesse
    impostazioni e lo stesso checkpoint (sha256): la cache delle decisioni e i mondi non si mescolano."""
    from riftbound.provenienza import checkpoint_sha256
    pc = Path(str(ckpt or D.CKPT_DEFAULT))
    pc = pc if pc.is_absolute() else D.ROOT / pc
    imp = {"ckpt_sha256": None if casuali else checkpoint_sha256(str(pc)), "casuali": bool(casuali),
           "regole": regole, "iterazioni": iterazioni, "valutazione": VALUTAZIONE, "base_seme": BASE_SEME,
           "mondi0": MONDI0, "partite": n_partite, "per_partita": per_partita, "mondi": n_mondi}
    f = out_dir / "impostazioni.json"
    if f.exists():
        if json.loads(f.read_text(encoding="utf-8")) != imp:
            raise ValueError(f"Impostazioni diverse da {f}: usare una nuova cartella.")
    else:
        f.write_text(json.dumps(imp, indent=1), encoding="utf-8")


def posizioni(matchup, n_partite: int, per_partita: int, n_mondi: int, out_dir, ckpt, casuali: bool = False,
              processi: int = 1, regole: str = REGOLE, iterazioni: int = ITERAZIONI, n_boot: int = N_BOOT,
              print_=print) -> list[str]:
    """Tutto: le decisioni con le due scelte (in cache in `decisioni.jsonl`), i mondi dove le scelte differiscono,
    riepilogo, `esito.json` {"passa", "totale"}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    _controlla_impostazioni(out_dir, ckpt, casuali, regole, iterazioni, n_partite, per_partita, n_mondi)
    parti = S.partite(matchup, n_partite, ckpt, casuali, iterazioni, regole)
    cache_path = out_dir / "decisioni.jsonl"
    cache = S._leggi_cache(cache_path)
    da_fare = [p for p in parti if A.nome_partita(p) not in cache]
    print_(f"== decisioni: {len(parti)} partite ({len(parti) - len(da_fare)} gia' fatte), al piu' {per_partita} ciascuna")
    lavori = [(p, per_partita) for p in da_fare]

    def salva(nome, ds):
        cache[nome] = ds
        with cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"nome": nome, "decisioni": ds}, ensure_ascii=False) + "\n")

    if processi > 1 and lavori:
        with ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn")) as pool:
            for j, (nome, ds) in enumerate(pool.map(_lavoro_partita, lavori), 1):
                salva(nome, ds)
                print_(f"== partita {j}/{len(lavori)}: {len(ds)} decisioni, {time.time() - t0:.0f} s")
    else:
        for j, lav in enumerate(lavori, 1):
            nome, ds = _lavoro_partita(lav)
            salva(nome, ds)
            print_(f"== partita {j}/{len(lavori)}: {len(ds)} decisioni, {time.time() - t0:.0f} s")
    decs = [d for p in parti for d in cache[A.nome_partita(p)]]
    righe_dec = []
    for n, dec in enumerate(decs):
        riga = {k: dec[k] for k in ("nome", "matchup", "k", "turno", "q", "visite", "coerente", "disaccordo")} | \
            {"media": None, "n_mondi": 0, "mondi_esclusi": 0}
        if dec["disaccordo"]:
            cart = out_dir / f"{n:03d}_{dec['nome']}_k{dec['k']}"
            f = cart / "decisione.json"
            res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
            if res is None or "deltas" not in res:
                print_(f"== decisione {n + 1}/{len(decs)}: {dec['nome']} k={dec['k']} turno {dec['turno']}, "
                       f"{n_mondi} mondi")
                res = gioca_decisione(dec, n_mondi, cart, processi)
            riga |= {"media": res["media"], "n_mondi": res["n_mondi"], "mondi_esclusi": res["mondi_esclusi"],
                     "deltas": res["deltas"]}
        righe_dec.append(riga)
    rs = riassunto(righe_dec, n_boot)
    imp = {"ckpt": str(ckpt) if ckpt else "(pesi casuali)", "iterazioni": iterazioni, "regole": regole,
           "partite": len(parti), "per_partita": per_partita, "mondi": n_mondi, "n_boot": n_boot}
    righe = _testo(rs, imp, time.time() - t0)
    (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(json.dumps({"impostazioni": imp, "riassunto": rs, "decisioni": righe_dec},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "esito.json").write_text(json.dumps({"passa": rs["passa"], "totale": rs["totale"]}), encoding="utf-8")
    return righe


# -- l'arena ------------------------------------------------------------------------------------------

def _gioca_arena(job: dict) -> dict:
    """Una partita dell'arena (in un processo): candidato contro il campione (stesso checkpoint), con le opzioni
    `opz` del lavoro. Con `opz["log"]` la riga porta anche `log`: per lato (cand/opp) le ricerche [turno, iterazioni,
    secondi di ricerca + secondi della sonda]."""
    import torch
    torch.set_num_threads(1)
    os.environ["RBSIM_REGOLE"] = job["regole"]
    seme, mu, posto = job["seme"], job["mu"], job["posto"]
    r = arena_rs.game((seme, "a" if seme % 2 == 0 else "b", posto, "prior_ppo", job["ckpt"], "prior_ppo", job["ckpt"],
                       mu, None, None, job["opz"]))
    riga = {"mu": mu, "seme": seme, "posto": posto, "score": r[3]}
    if job["opz"].get("log"):
        riga["log"] = {lato: [[x[1], x[2], round(x[3] + x[4], 6)] for x in r[8]["log"][lato]]
                       for lato in ("cand", "opp")}
    return riga


def _opz(iterazioni: int) -> dict:
    return generazione._opz(0.0, iterazioni, False) | {"scelta_cand": "visite"}


def arena_campione(matchup, coppie: int, out_dir, ckpt, opz: dict, base_seme: int, config_extra: dict,
                   etichetta: str = "arena", processi: int = 1, regole: str = REGOLE, n_boot: int = 4000,
                   print_=print) -> dict:
    """Il cuore delle arene: candidato (opzioni `opz`) contro il campione con lo stesso checkpoint, coppie a posti
    scambiati con lo stesso seme (`base_seme` + 1000 per matchup + k). Le partite finite vanno in
    `arena_righe.jsonl` (ripresa per (matchup, seme, posto)) con il manifest (config_extra va nella configurazione:
    impostazioni diverse sono rifiutate). -> {"fatte", "punti", "totale", "per", "config", "minuti"}."""
    from filelock import FileLock
    from riftbound.provenienza import checkpoint_sha256, scrivi_json_atomico
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    ckpt = str(ckpt)
    righe = out_dir / "arena_righe.jsonl"
    config = {"ckpt_sha256": checkpoint_sha256(ckpt), "regole": regole, **config_extra,
              "max_turni": arena_rs.MAX_TURNS, "base_seme": base_seme, "opz": opz}
    manifest = righe.with_name(righe.name + ".provenienza.json")
    with FileLock(str(righe) + ".rbsim.lock", timeout=0):
        if manifest.exists():
            if json.loads(manifest.read_text()) != json.loads(json.dumps(config)):
                raise ValueError(f"Configurazione arena incompatibile con {manifest}. Usare una nuova uscita.")
        elif righe.is_file() and righe.stat().st_size:
            raise ValueError(f"Arena senza provenienza: {righe}. Usare una nuova uscita.")
        else:
            scrivi_json_atomico(manifest, config)
        fatte = {}
        if righe.is_file():
            for x in righe.read_text().splitlines():
                if x.strip():
                    r = json.loads(x)
                    fatte[(r["mu"], r["seme"], r["posto"])] = r
        jobs = []
        for mu in matchup:
            s0 = base_seme + 1_000 * arena_rs.COPERTI.index(mu)
            for k in range(coppie):
                for posto in ("A", "B"):
                    if (mu, s0 + k, posto) not in fatte:
                        jobs.append({"mu": mu, "seme": s0 + k, "posto": posto, "ckpt": ckpt, "regole": regole,
                                     "opz": opz})
        print_(f"== {etichetta}: {len(fatte)} partite gia' fatte, {len(jobs)} da giocare, {processi} processi")
        if jobs:
            os.environ["RBSIM_REGOLE"] = regole
            with open(righe, "a") as f:
                def registra(n, r):
                    fatte[(r["mu"], r["seme"], r["posto"])] = r
                    f.write(json.dumps(r) + "\n")
                    f.flush()
                    if n % 20 == 0 or n == len(jobs):
                        print_(f"== {etichetta} {n}/{len(jobs)} partite, {(time.time() - t0) / 60:.1f} min")
                if processi > 1:
                    with ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn")) as pool:
                        for n, r in enumerate(pool.map(_gioca_arena, jobs), 1):
                            registra(n, r)
                else:
                    for n, job in enumerate(jobs, 1):
                        registra(n, _gioca_arena(job))
    punti = {}
    for mu in matchup:
        s0 = base_seme + 1_000 * arena_rs.COPERTI.index(mu)
        punti[mu] = np.array([(fatte[(mu, s0 + k, "A")]["score"] + fatte[(mu, s0 + k, "B")]["score"]) / 2
                              for k in range(coppie)])
    tot, lo, hi, per = generazione.intervallo(punti, np.random.default_rng(0), n_boot)
    return {"fatte": fatte, "punti": punti, "totale": (tot, lo, hi), "per": per, "config": config,
            "minuti": round((time.time() - t0) / 60, 1)}


def arena(matchup, coppie: int, out_dir, ckpt, processi: int = 1, regole: str = REGOLE,
          iterazioni: int = ITERAZIONI, n_boot: int = 4000, print_=print) -> list[str]:
    """Candidato (campione con scelta per visite) contro il campione, coppie a posti scambiati con lo stesso seme.
    Le partite finite vanno in `arena_righe.jsonl` (ripresa per (matchup, seme, posto)). `promuovibile`: limite
    inferiore dell'IC 95% del totale > 0,5. Scrive `arena.json` e `arena.txt`."""
    out_dir = Path(out_dir)
    ckpt = str(ckpt)
    a = arena_campione(matchup, coppie, out_dir, ckpt, _opz(iterazioni), BASE_SEME_ARENA, {"iterazioni": iterazioni},
                       "arena", processi, regole, n_boot, print_)
    tot, lo, hi = a["totale"]
    per, config = a["per"], a["config"]
    prom = bool(lo > 0.5)
    res = {"totale": [tot, lo, hi], "matchup": {mu: list(x) for mu, x in per.items()}, "coppie_per_matchup": coppie,
           "promuovibile": prom, "configurazione": config, "minuti": a["minuti"]}
    testo = [f"Arena: candidato (scelta per visite) contro il campione {ckpt}, {coppie} coppie per matchup "
             f"({', '.join(matchup)}), {iterazioni} iterazioni, regole {regole}, semi da {BASE_SEME_ARENA}",
             f"totale {tot:.3f} (IC 95% {lo:.3f}-{hi:.3f}), pesi uguali fra i matchup",
             "   " + "; ".join(f"{mu} {x[0]:.3f} ({x[1]:.2f}-{x[2]:.2f})" for mu, x in per.items()),
             ("criterio: limite inferiore > 0,5: PROMUOVIBILE" if prom else
              "criterio: limite inferiore > 0,5: NON promuovibile"),
             f"durata dell'arena: {res['minuti']} min"]
    (out_dir / "arena.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "arena.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    return testo
