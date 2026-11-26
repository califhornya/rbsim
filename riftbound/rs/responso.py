"""Primo responso (Astra, 26/11): quando la ricerca suggerisce una mossa diversa, si vince di piu'?

Su decisioni di turno nuove (partite autonome del campione, 10 matchup, semi 300 e 301), a due budget di iterazioni
(138 e 512), si confrontano la mossa preferita dal prior (P massimo), la piu' visitata (n massimo) e quella di q
massimo fra le visitate (la giocata dal campione, `conclude`). Dove gli insiemi (pari merito inclusi) sono disgiunti
si gioca ogni mossa fino alla fine sugli stessi mondi `ignote` (linea `primo` di `attacco`) e si confrontano a coppie.

  `decisioni(partita, per_partita, iters)`   le decisioni scelte di una partita, con `rifai` ai due budget.
  `mosse(dec)`                               per budget: insiemi P/n/q, rappresentanti, disaccordi.
  `linee_decisione(dec)`                     le mosse distinte da giocare (al piu' MAX_LINEE).
  `responso(...)`                            tutto: decisioni, mondi, riepilogo (`riepilogo.txt`, ultima riga `totale:`).
"""
from __future__ import annotations

import json
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

from riftbound.rs import attacco as A, decisione_rs as D

SEMI = (300, 301)           # posto A per il pari, B per il dispari
REGOLE = "6427b90+D72-D83"
VALUTAZIONE = "rimonta"
ITERAZIONI = (138, 512)
MONDI0 = 7000               # primo indice dei mondi
MAX_LINEE = 4
TIPI = (("visite_prior", "visite", "prior", "prior≠visite"),
        ("q_visite", "q", "visite", "visite≠Q"),
        ("q_prior", "q", "prior", "prior≠Q"))


# -- le decisioni -----------------------------------------------------------------------------------

def sparse(v: list, m: int) -> list:
    return [v[(j * len(v)) // m] for j in range(m)] if m < len(v) else list(v)


def partita_autonoma(mu: str, seme: int, ckpt, casuali: bool, iterazioni: int, regole: str = REGOLE,
                     valutazione: str = VALUTAZIONE) -> dict:
    return D.autonoma(mu, seme, ckpt, casuali, iterazioni, "A" if seme % 2 == 0 else "B", regole=regole,
                      valutazione=D._valutazione_registrata(valutazione))


def _riassunto_rifai(r: dict) -> dict:
    """Quanto serve di una `rifai`: la classifica (azione, n, q, P, indice nel menu) e la mossa giocata."""
    return {"iterazioni": r["iterazioni"], "iterazioni_fatte": r.get("iterazioni_fatte"), "azione": r["azione"],
            "prefisso_ok": r["prefisso_ok"],
            "classifica": [{k: x[k] for k in ("i", "azione", "n", "q", "P", "rango")} for x in r["classifica"]]}


def decisioni(partita: dict, per_partita: int, iters: tuple[int, int]) -> list[dict]:
    """Le decisioni `turn_action` del campione con almeno 2 voci nel menu, al piu' `per_partita` sparse sull'elenco
    (cioe' sui turni), ciascuna rifatta ai due budget. Una riga: partita, k, turno, menu, `rifai` per budget."""
    P = D._prepara(partita)
    orig = D.originale(partita)
    cand = [o for o in orig if o["seat"] == P["camp"] and o["point"] == "turn_action" and len(o["menu"]) >= 2]
    out = []
    for o in sparse(cand, per_partita):
        rifa = {str(it): _riassunto_rifai(D.rifai(partita, o["k"], it, posizione=False, semi=True)) for it in iters}
        out.append({"partita": partita, "nome": A.nome_partita(partita), "k": o["k"], "turno": o["turn"],
                    "menu": o["menu"], "rifai": rifa})
    return out


def _lavoro_partita(args) -> list[dict]:
    return decisioni(*args)


# -- disaccordi -------------------------------------------------------------------------------------

def _insiemi(classifica: list[dict]) -> dict:
    """Gli insiemi (indici nel menu, pari merito inclusi) con P massimo, n massimo, q massimo fra le visitate."""
    def massimi(chiave, ammessi):
        v = [(x[chiave], x["i"]) for x in classifica if ammessi(x) and x[chiave] is not None]
        m = max((a for a, _ in v), default=None)
        return sorted(i for a, i in v if a == m)
    return {"prior": massimi("P", lambda x: True), "visite": massimi("n", lambda x: True),
            "q": massimi("q", lambda x: x["n"] > 0)}


def mosse(dec: dict) -> dict:
    """Per budget: gli insiemi, il rappresentante di ciascuno (a pari merito la prima voce del menu; per Q la mossa
    giocata se e' nell'insieme), la mossa giocata e quali tipi di disaccordo ci sono (insiemi disgiunti)."""
    out = {}
    for it, r in dec["rifai"].items():
        ins = _insiemi(r["classifica"])
        etich = {x["i"]: x["azione"] for x in r["classifica"]}
        giocata = next((x["i"] for x in r["classifica"] if x["azione"] == r["azione"]), None)
        rapp = {k: (v[0] if v else None) for k, v in ins.items()}
        if giocata is not None and giocata in ins["q"]:
            rapp["q"] = giocata
        dis = {nome: bool(ins[a] and ins[b] and not set(ins[a]) & set(ins[b])) for nome, a, b, _ in TIPI}
        out[it] = {"insiemi": ins, "rapp": {k: (etich[v] if v is not None else None) for k, v in rapp.items()},
                   "giocata": r["azione"], "disaccordo": dis, "disaccordo_qualsiasi": any(dis.values())}
    return out


def linee_decisione(m: dict, iters: tuple[int, int]) -> list[str]:
    """Le mosse distinte fra {prior, visite, Q} ai due budget, al piu' MAX_LINEE: prima la mossa del campione ai due
    budget, poi prior e visite a quello basso, poi a quello alto."""
    lo, hi = str(iters[0]), str(iters[1])
    ordine = [("q", lo), ("q", hi), ("prior", lo), ("visite", lo), ("prior", hi), ("visite", hi)]
    out: list[str] = []
    for tipo, it in ordine:
        e = m[it]["rapp"][tipo]
        if e is not None and e not in out:
            out.append(e)
    return out[:MAX_LINEE]


def _confronti(m: dict, iters: tuple[int, int]) -> dict:
    """I confronti da fare in una decisione: nome -> (mossa X, mossa Y, differenza X - Y), solo dove le due mosse
    sono diverse (disaccordo del tipo a quel budget; per il budget: scelta alta contro bassa)."""
    out = {}
    for it in map(str, iters):
        for nome, a, b, _ in TIPI:
            if m[it]["disaccordo"][nome]:
                out[f"{nome}@{it}"] = (m[it]["rapp"][a], m[it]["rapp"][b])
    g0, g1 = m[str(iters[0])]["giocata"], m[str(iters[1])]["giocata"]
    if g0 != g1:
        out[f"scelta{iters[1]}_{iters[0]}"] = (g1, g0)
    return out


# -- statistiche ------------------------------------------------------------------------------------

def stat(delta: list[float]) -> dict:
    n = len(delta)
    if not n:
        return {"n": 0, "media": None, "intervallo_95": None}
    avg = mean(delta)
    mar = 1.96 * stdev(delta) / sqrt(n) if n > 1 else float("nan")
    return {"n": n, "media": avg, "intervallo_95": [avg - mar, avg + mar]}


def _delta_mondi(dati: list, x: str, y: str) -> list[float]:
    """Le differenze appaiate (ritorno della linea x - ritorno della linea y) in ogni mondo di una decisione."""
    d = []
    for rows in dati:
        r = {row["line"]: row for row in rows}
        if x in r and y in r:
            d.append(r[x]["returns"] - r[y]["returns"])
    return d


def _fmt(s: dict) -> str:
    if not s["n"]:
        return "-"
    a, b = s["intervallo_95"]
    return f"{100 * s['media']:+.1f} [{100 * a:+.1f}, {100 * b:+.1f}] pp (n={s['n']})"


# -- la corsa ---------------------------------------------------------------------------------------

def _nome_cartella(n: int, dec: dict) -> str:
    return f"{n:03d}_{dec['nome']}_k{dec['k']}"


def responso(matchup, semi, per_partita: int, iters: tuple[int, int], n_mondi: int, out_dir: Path, ckpt=None,
             casuali: bool = False, processi: int = 1, regole: str = REGOLE, valutazione: str = VALUTAZIONE,
             print_=print) -> list[str]:
    """Tutto il responso; scrive in `out_dir` una cartella per decisione (`decisione.json`, `mondi.jsonl` se c'e'
    disaccordo), `riepilogo.json` e `riepilogo.txt` (ultima riga `totale:`)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    partite = [partita_autonoma(mu, s, ckpt, casuali, iters[0], regole, valutazione) for mu in matchup for s in semi]
    lavori = [(p, per_partita, iters) for p in partite]
    decs: list[dict] = []
    print_(f"== decisioni: {len(partite)} partite, al piu' {per_partita} ciascuna, rifai a {iters[0]} e {iters[1]}")
    if processi > 1:
        with ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn")) as pool:
            for j, ds in enumerate(pool.map(_lavoro_partita, lavori), 1):
                decs += ds
                print_(f"  partita {j}/{len(partite)}: {len(ds)} decisioni, {time.time() - t0:.0f} s")
    else:
        for j, lav in enumerate(lavori, 1):
            decs += _lavoro_partita(lav)
            print_(f"  partita {j}/{len(partite)}: {len(decs)} decisioni, {time.time() - t0:.0f} s")
    indici = range(MONDI0, MONDI0 + n_mondi)
    righe, riep = [], []
    t_decisioni = time.time() - t0
    for n, dec in enumerate(decs):
        m = mosse(dec)
        cart = out_dir / _nome_cartella(n, dec)
        cart.mkdir(exist_ok=True)
        conf = _confronti(m, iters)
        dec_json = {k: dec[k] for k in ("partita", "nome", "k", "turno", "menu", "rifai")}
        dec_json.update(mosse=m, confronti={k: list(v) for k, v in conf.items()})
        dati = []
        if any(m[str(it)]["disaccordo_qualsiasi"] for it in iters):
            etich = linee_decisione(m, iters)
            linee = [A.linea_primo(e, e) for e in etich]
            print_(f"== decisione {n}: {dec['nome']} k={dec['k']} turno {dec['turno']}; linee {len(linee)}, "
                   f"{len(indici)} mondi")
            pos = A.posizione(dec["partita"], dec["k"])
            dati = A.esegui(pos, "ignote", indici, linee, cart / "mondi.jsonl", processi, lambda *_: None)
            dec_json["linee"] = etich
            dec_json["primo_non_rispettato"] = sum(not r["primo_ok"] for rows in dati for r in rows)
        else:
            print_(f"== decisione {n}: {dec['nome']} k={dec['k']} turno {dec['turno']}; nessun disaccordo")
        res = {}
        for nome, (x, y) in conf.items():
            res[nome] = stat(_delta_mondi(dati, x, y)) | {"x": x, "y": y}
        dec_json["risultati"] = res
        (cart / "decisione.json").write_text(json.dumps(dec_json, ensure_ascii=False, indent=1), encoding="utf-8")
        riep.append({"cartella": cart.name, "matchup": dec["partita"]["matchup"], "mosse": m, "risultati": res,
                     "delta": {nome: _delta_mondi(dati, x, y) for nome, (x, y) in conf.items()},
                     "non_rispettato": dec_json.get("primo_non_rispettato", 0)})
    righe = _riepilogo(riep, iters, len(partite), n_mondi, time.time() - t0, t_decisioni)
    (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(json.dumps(riep, ensure_ascii=False), encoding="utf-8")
    return righe


def _riepilogo(riep: list[dict], iters: tuple[int, int], n_partite: int, n_mondi: int, secondi: float,
               secondi_decisioni: float) -> list[str]:
    righe = [f"decisioni {len(riep)} (da {n_partite} partite), mondi per decisione {n_mondi}, iterazioni {iters[0]} e "
             f"{iters[1]}"]
    righe.append("disaccordo (decisioni con insiemi disgiunti, pari merito inclusi):")
    for it in map(str, iters):
        qual = sum(r["mosse"][it]["disaccordo_qualsiasi"] for r in riep)
        parti = "; ".join(f"{testo} {sum(r['mosse'][it]['disaccordo'][nome] for r in riep)}"
                          for nome, _a, _b, testo in TIPI)
        righe.append(f"  a {it}: {qual}/{len(riep)} con disaccordo; {parti}")
    nomi = [f"{nome}@{it}" for it in map(str, iters) for nome, *_ in TIPI] + [f"scelta{iters[1]}_{iters[0]}"]
    descr = {"visite_prior": "visite - prior", "q_visite": "Q - visite", "q_prior": "Q - prior"}
    righe.append("differenza media di ritorno (1 vittoria, 0,5 patta), intervallo 95% sui mondi appaiati:")
    for nome in nomi:
        base = nome.split("@")[0]
        testo = descr.get(base, f"scelta a {iters[1]} - scelta a {iters[0]}")
        if "@" in nome:
            testo += f" a {nome.split('@')[1]}"
        tutti = [d for r in riep for d in r["delta"].get(nome, [])]
        ndec = sum(1 for r in riep if nome in r["risultati"])
        righe.append(f"  {testo}: {_fmt(stat(tutti))}; decisioni {ndec}")
        for mu in sorted({r["matchup"] for r in riep}):
            parz = [d for r in riep if r["matchup"] == mu for d in r["delta"].get(nome, [])]
            if parz:
                righe.append(f"      {mu}: {_fmt(stat(parz))}")
    non = sum(r["non_rispettato"] for r in riep)
    righe.append(f"prima mossa forzata diversa dalla chiesta: {non} righe")
    righe.append(f"tempo: {secondi / 60:.1f} min ({secondi_decisioni / 60:.1f} per le decisioni)")
    disc = sum(r["mosse"][it]["disaccordo_qualsiasi"] for r in riep for it in [str(iters[0])]) if riep else 0
    righe.append(f"totale: {len(riep)} decisioni; con disaccordo a {iters[0]} {disc}; a {iters[1]} "
                 f"{sum(r['mosse'][str(iters[1])]['disaccordo_qualsiasi'] for r in riep)}; {secondi / 60:.1f} min")
    return righe
