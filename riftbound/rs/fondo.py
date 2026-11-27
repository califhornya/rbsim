"""Fondo (misura di «Pensa»): se a ogni decisione si giocano fino in fondo le mosse candidate del campione, quella che
rende di piu' batte la mossa che il campione gioca davvero?

Sulle 480 posizioni di sviluppo di `scelta` (`seguiti.selezionate`), a ogni decisione:

  Fase 1  `candidati(o)`: dall'albero ORIGINALE del campione, la mossa giocata (primo candidato) e fino ad altre due
          (le piu' visitate, poi Q, poi l'ordine del menu). La scelta per Q deve coincidere con la mossa giocata
          (`coerente`), altrimenti la decisione e' esclusa e contata.
  Fase 2  scelta: ogni candidato si gioca fino alla fine sugli stessi 32 mondi `ignote` (indici 40000..) e si prende
          quello con il ritorno medio piu' alto («Pensa»; a pari merito il campione).
          verifica: dove la scelta differisce dal campione, campione e scelta si giocano su 100 mondi DIVERSI
          (indici 50000..): delta = ritorno della scelta - ritorno del campione. Dove coincide, delta = 0 senza giocare.
  `riassunto`  ogni matchup pesa uguale, zeri compresi; IC 95% ricampionando PARTITE intere (`scelta.riassunto`).
  `posizioni(...)`  tutto; scrive `riepilogo.txt` (ultima riga `totale:`), `riepilogo.json`, `esito.json`.

Le rigiocate di tutte le posizioni vanno in un unico pool di processi (`_Corsa`): un compito e' un mondo di una
decisione; le verifiche passano davanti alle scelte ancora da fare.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np

from riftbound.rs import arena_rs, attacco as A, decisione_rs as D, scelta as C, seguiti as S
from riftbound.rs.seguiti import BASE_SEME, ITERAZIONI, N_BOOT, REGOLE, VALUTAZIONE

N_PARTITE = 6
PER_PARTITA = 8
CANDIDATI = 3
MONDI_SCELTA = 40_000
N_SCELTA = 32                   # indici di mondo, non semi di partita
MONDI_VERIFICA = 50_000
N_VERIFICA = 100
MINIMO_CAMBI = 20               # regola di stop, fissata prima dei risultati
PROCESSI_MAC = 9
PROCESSI_SERVER = 47
COPPIE_ARENA = 100

_CHIAVI_MONDO = ("world", "line", "returns", "winner", "turns", "end_A_B", "primo_ok", "primo_giocata", "secondi")


# -- funzioni pure ------------------------------------------------------------------------------------

def mondi(n_scelta: int = N_SCELTA, n_verifica: int = N_VERIFICA) -> tuple[range, range]:
    """Gli indici di mondo della scelta e della verifica: devono essere disgiunti (mondi diversi)."""
    if n_scelta < 1 or n_verifica < 1:
        raise ValueError("Servono almeno un mondo di scelta e uno di verifica.")
    a = range(MONDI_SCELTA, MONDI_SCELTA + n_scelta)
    b = range(MONDI_VERIFICA, MONDI_VERIFICA + n_verifica)
    if a.stop > b.start:
        raise ValueError(f"Mondi di scelta {a.start}..{a.stop - 1} e di verifica {b.start}..{b.stop - 1} si sovrappongono.")
    return a, b


def candidati(o: dict, partita: dict | None = None, n: int = CANDIDATI) -> dict:
    """Da una riga di `D.originale` (`o["riga"]["children"]` = [azione, n, q, w, sub] nell'ordine della radice, NON
    del menu; `o["riga"]["menu"]` = le azioni nell'ordine del menu, `o["menu"]` le etichette): il campione (la mossa
    giocata) per primo, poi al piu' `n - 1` altri figli validi (n > 0, etichetta nota, etichetta diversa dal campione e
    non ripetuta) per visite decrescenti, poi Q decrescente, poi indice nel menu. `coerente`: la scelta per Q (il primo
    figlio con la Q massima fra quelli con n > 0) esiste ed e' la mossa giocata."""
    riga = o["riga"]
    etichetta = {json.dumps(a): o["menu"][i] for i, a in enumerate(riga["menu"]) if i < len(o["menu"])}
    indice = {json.dumps(a): i for i, a in enumerate(riga["menu"])}
    validi = []                                   # (etichetta, n, q, indice nel menu), nell'ordine dei figli
    mq = None
    for c in riga["children"]:
        nn, q = c[1], c[2]
        if not nn > 0:
            continue
        chiave = json.dumps(c[0])
        if mq is None or q > mq[1]:
            mq = (etichetta.get(chiave), q)
        if chiave in etichetta:
            validi.append((etichetta[chiave], nn, q, indice[chiave]))
    coerente = mq is not None and mq[0] is not None and mq[0] == o["action"]
    camp = o["action"]
    mio = next(((nn, q) for e, nn, q, _i in validi if e == camp), (None, None))
    altri, visti = [], {camp}
    for e, nn, q, i in sorted((v for v in validi if v[0] != camp), key=lambda v: (-v[1], -v[2], v[3])):
        if e not in visti:
            visti.add(e)
            altri.append((e, nn, q))
    altri = altri[:max(0, n - 1)]
    out = {"k": o["k"], "turno": o["turn"], "menu": o["menu"], "campione": camp,
           "candidati": [camp] + [x[0] for x in altri], "n": [mio[0]] + [x[1] for x in altri],
           "q": [mio[1]] + [x[2] for x in altri], "coerente": bool(coerente)}
    if partita is not None:
        out = {"partita": partita, "nome": A.nome_partita(partita), "matchup": partita["matchup"]} | out
    return out


def scegli(medie: list) -> int:
    """Indice della media piu' alta (a pari merito il piu' basso: 0 = campione); None = nessun valore."""
    best, idx = None, 0
    for i, m in enumerate(medie):
        if m is None:
            continue
        if best is None or m > best:
            best, idx = m, i
    return idx


def valuta_scelta(dati: list, nomi: list[str]) -> dict:
    """`dati`: per mondo la lista delle righe (una per linea). Un mondo vale solo se TUTTE le linee hanno `primo_ok`
    (confronto appaiato); gli altri sono esclusi e contati."""
    ritorni: list[list[float]] = [[] for _ in nomi]
    esclusi = 0
    for rows in dati:
        r = {x["line"]: x for x in rows}
        if all(r[nome]["primo_ok"] for nome in nomi):
            for j, nome in enumerate(nomi):
                ritorni[j].append(r[nome]["returns"])
        else:
            esclusi += 1
    medie = [sum(x) / len(x) if x else None for x in ritorni]
    return {"ritorni": ritorni, "medie": medie, "n_mondi": len(ritorni[0]) if ritorni else 0,
            "mondi_esclusi": esclusi, "scelta": scegli(medie)}


def delta_verifica(dati: list) -> dict:
    """Delta = ritorno di `scelta` - ritorno di `campione` nei mondi dove entrambe rispettano la prima mossa."""
    deltas, esclusi = [], 0
    for rows in dati:
        r = {x["line"]: x for x in rows}
        if r["campione"]["primo_ok"] and r["scelta"]["primo_ok"]:
            deltas.append(r["scelta"]["returns"] - r["campione"]["returns"])
        else:
            esclusi += 1
    return {"deltas": deltas, "media": float(np.mean(deltas)) if deltas else None, "n_mondi": len(deltas),
            "mondi_esclusi": esclusi}


def riga(dec: dict, sc: dict | None, ve: dict | None) -> dict:
    """La riga per `scelta.riassunto`. Senza disaccordo `C._valore` da' 0,0 esatto (coincide = 0 senza giocare)."""
    coerente = bool(dec["coerente"])
    dis = bool(coerente and sc is not None and sc["scelta"] != 0)
    ve = ve if dis else None
    return {"nome": dec["nome"], "matchup": dec["matchup"], "k": dec["k"], "turno": dec["turno"],
            "coerente": coerente, "disaccordo": dis, "media": ve["media"] if ve else None,
            "n_mondi": ve["n_mondi"] if ve else 0, "mondi_esclusi": ve["mondi_esclusi"] if ve else 0,
            "deltas": ve["deltas"] if ve else [],
            "scelta": dec["candidati"][sc["scelta"]] if sc is not None else None}


def regola_stop(rs: dict, minimo: int = MINIMO_CAMBI) -> bool:
    """Limite inferiore del totale > 0 e almeno `minimo` posizioni cambiano mossa (con mondi validi)."""
    return bool(rs["totale"][1] > 0 and rs["n_disaccordi_validi"] >= minimo)


def _quantili(x, nomi: dict) -> dict:
    if not len(x):
        return {k: None for k in nomi}
    return {k: float(f(np.asarray(x, float))) for k, f in nomi.items()}


def tempi(cpu: list, per_turno: list, per_partita: list, processi_mac: int, coppie: int, n_matchup: int,
          processi_server: int, seme: int = 0) -> dict:
    """Stime di tempo. `cpu`: secondi di cpu della fase di scelta per decisione (solo dove si e' giocata); `per_turno`:
    per ogni turno con almeno una decisione idonea, quante; `per_partita`: decisioni idonee per partita."""
    p95 = lambda x: np.percentile(x, 95)  # noqa: E731
    out = {"cpu": _quantili(cpu, {"mediana": np.median, "p95": p95, "massimo": np.max}) | {"n": len(cpu)},
           "per_turno": _quantili(per_turno, {"media": np.mean, "p95": p95})}
    mac = {"mediana": None, "p95": None}
    if len(cpu) and len(per_turno):
        rng = np.random.default_rng(seme)
        c = np.asarray(cpu, float)
        ks = rng.choice(np.asarray(per_turno, int), 20_000)
        somme = c[rng.integers(0, len(c), int(ks.sum()))]
        inizi = np.concatenate([[0], np.cumsum(ks)[:-1]])
        tot = np.add.reduceat(somme, inizi) / processi_mac
        mac = {"mediana": float(np.median(tot)), "p95": float(np.percentile(tot, 95))}
    out["mac_turno"] = mac
    arena = {"coppie": coppie, "decisioni_per_partita": float(np.mean(per_partita)) if len(per_partita) else None,
             "ore_cpu": None, "ore_server": None}
    if len(cpu) and len(per_partita):
        arena["ore_cpu"] = float(2 * coppie * n_matchup * np.mean(per_partita) * np.mean(cpu) / 3600)
        arena["ore_server"] = arena["ore_cpu"] / processi_server
    out["arena"] = arena
    return out


# -- fase 1: le decisioni ---------------------------------------------------------------------------

def decisioni(partita: dict, per_partita: int) -> tuple[list[dict], list[int], int]:
    """Le decisioni di `seguiti.selezionate` con i candidati; inoltre, per le decisioni idonee del campione (come
    `selezionate`: `turn_action` con almeno 2 voci), quante per turno e quante in tutto."""
    decs = [candidati(o, partita) for o in S.selezionate(partita, per_partita)]
    P = D._prepara(partita)
    turni: dict = {}
    for o in D.originale(partita):
        if o["seat"] == P["camp"] and o["point"] == "turn_action" and len(o["menu"]) >= 2:
            turni[o["turn"]] = turni.get(o["turn"], 0) + 1
    return decs, list(turni.values()), sum(turni.values())


def _lavoro_partita(args) -> tuple[str, list[dict], list[int], int]:
    partita = args[0]
    decs, per_turno, n_idonee = decisioni(*args)
    return A.nome_partita(partita), decs, per_turno, n_idonee


def _leggi_cache(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for r in path.read_text(encoding="utf-8").splitlines():
            if r.strip():
                d = json.loads(r)
                partita = S._ripristina(d["partita"])
                out[d["nome"]] = {"partita": partita, "decisioni": [{"partita": partita} | x for x in d["decisioni"]],
                                  "per_turno": d["per_turno"], "n_idonee": d["n_idonee"]}
    return out


# -- fase 2: le rigiocate -----------------------------------------------------------------------------

def _lavoro_mondo(args):
    t = time.process_time()
    rows = A._lavoro(args)
    return rows, time.process_time() - t


def _scrivi(path: Path, testo: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(testo, encoding="utf-8")
    os.replace(tmp, path)


def _scrivi_json(path: Path, obj) -> None:
    _scrivi(path, json.dumps(obj, ensure_ascii=False, indent=1))


class _Subito:
    """Esecutore in linea (un processo): esegue al momento, senza pool."""

    def submit(self, fn, *args):
        f: Future = Future()
        try:
            f.set_result(fn(*args))
        except BaseException as e:  # noqa: BLE001 - lo rilancia `result()`
            f.set_exception(e)
        return f

    def shutdown(self, **_k):
        pass


class _Corsa:
    """Scheduler: una coda di compiti (decisione, fase), ciascuno su un elenco di mondi; in volo al piu'
    `max(4, 2 * processi)` mondi. Le verifiche passano davanti. Con `cascata` una scelta che cambia mossa mette in coda
    la sua verifica."""

    def __init__(self, ms: range, mv: range, processi: int = 1, print_=print, cascata: bool = True):
        self.ms, self.mv, self.processi, self.print_, self.cascata = ms, mv, processi, print_, cascata
        self.coda: deque = deque()
        self.pos: dict = {}
        self.attivi: dict = {}
        self.esiti: dict = {}
        self.totale = self.finiti = 0
        self.t0 = time.time()

    def compito(self, n: int, dec: dict, fase: str, cart: Path, s: int | None = None) -> dict:
        if fase == "scelta":
            indici = self.ms
            linee = [A.linea_primo(f"c{j}", et) for j, et in enumerate(dec["candidati"])]
        else:
            indici = self.mv
            linee = [A.linea_primo("campione", dec["candidati"][0]), A.linea_primo("scelta", dec["candidati"][s])]
        return {"n": n, "dec": dec, "fase": fase, "cart": Path(cart), "s": s, "indici": indici, "linee": linee,
                "ris": {}, "prossimo": 0}

    def aggiungi(self, job: dict, davanti: bool = False) -> None:
        (self.coda.appendleft if davanti else self.coda.append)(job)
        self.attivi[job["n"]] = self.attivi.get(job["n"], 0) + 1
        self.totale += 1

    def _pos(self, job: dict) -> dict:
        if job["n"] not in self.pos:
            self.pos[job["n"]] = A.posizione(job["dec"]["partita"], job["dec"]["k"])
        return self.pos[job["n"]]

    def _finito(self, job: dict) -> None:
        dec, cart, rows = job["dec"], job["cart"], job["ris"]
        ordine = list(job["indici"])
        dati = [rows[i][0] for i in ordine]
        cpu = [rows[i][1] for i in ordine]
        cart.mkdir(parents=True, exist_ok=True)
        jl = "".join(json.dumps([{k: r.get(k) for k in _CHIAVI_MONDO} for r in d], ensure_ascii=False) + "\n"
                     for d in dati)
        base = {"mondi": [job["indici"].start, len(ordine)]}
        if job["fase"] == "scelta":
            nomi = [f"c{j}" for j in range(len(dec["candidati"]))]
            v = valuta_scelta(dati, nomi)
            v.pop("ritorni")
            res = {"candidati": dec["candidati"], "n": dec["n"], "q": dec["q"]} | base | v | \
                {"mossa": dec["candidati"][v["scelta"]], "cpu": float(sum(cpu)), "cpu_mondi": cpu}
            _scrivi(cart / "scelta_mondi.jsonl", jl)
            _scrivi_json(cart / "scelta.json", res)
            if self.cascata and v["scelta"] != 0:
                self.aggiungi(self.compito(job["n"], dec, "verifica", cart, v["scelta"]), davanti=True)
        else:
            res = base | delta_verifica(dati)
            _scrivi(cart / "verifica_mondi.jsonl", jl)
            _scrivi_json(cart / "verifica.json", res)
        self.esiti[(job["n"], job["fase"])] = res
        self.attivi[job["n"]] -= 1
        if not self.attivi[job["n"]]:
            self.pos.pop(job["n"], None)
        self.finiti += 1
        if self.finiti % 10 == 0:
            self.print_(f"== compiti {self.finiti}/{self.totale}, {(time.time() - self.t0) / 60:.1f} min")

    def esegui(self) -> None:
        pool = _Subito() if self.processi <= 1 else \
            ProcessPoolExecutor(self.processi, mp_context=multiprocessing.get_context("spawn"))
        cap = max(4, 2 * self.processi)
        volo: dict = {}
        try:
            while self.coda or volo:
                while self.coda and len(volo) < cap:
                    job = self.coda[0]
                    i = job["indici"][job["prossimo"]]
                    volo[pool.submit(_lavoro_mondo, (self._pos(job), "ignote", i, job["linee"]))] = (job, i)
                    job["prossimo"] += 1
                    if job["prossimo"] == len(job["indici"]):
                        self.coda.popleft()
                fatti, _ = wait(list(volo), return_when=FIRST_COMPLETED)
                for f in fatti:
                    job, i = volo.pop(f)
                    job["ris"][i] = f.result()
                    if len(job["ris"]) == len(job["indici"]):
                        self._finito(job)
        finally:
            pool.shutdown(cancel_futures=True)
        if self.finiti % 10:
            self.print_(f"== compiti {self.finiti}/{self.totale}, {(time.time() - self.t0) / 60:.1f} min")


def gioca_fase(dec: dict, fase: str, cart: Path, n_mondi: int, scelta: int | None = None, processi: int = 1) -> dict:
    """Un solo compito (stesso scheduler). `scelta`: indice del candidato scelto, per la verifica. Scrive i file in
    `cart` e restituisce `scelta.json` o `verifica.json`."""
    if fase not in ("scelta", "verifica"):
        raise ValueError(f"Fase sconosciuta: {fase}")
    if fase == "verifica" and not scelta:
        raise ValueError("La verifica vuole l'indice di un candidato diverso dal campione.")
    ms, mv = mondi(n_mondi if fase == "scelta" else 1, n_mondi if fase == "verifica" else 1)
    corsa = _Corsa(ms, mv, processi, lambda *_: None, cascata=False)
    corsa.aggiungi(corsa.compito(0, dec, fase, Path(cart), scelta))
    corsa.esegui()
    return corsa.esiti[(0, fase)]


# -- il riepilogo -------------------------------------------------------------------------------------

def _pp(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f} pp"


def _s(x) -> str:
    return "-" if x is None else f"{x:.1f}"


def _testo(rs: dict, imp: dict, tm: dict, extra: dict, secondi: float) -> list[str]:
    t, lo, hi = rs["totale"]
    r = [f"Fondo («Pensa»): fino a {imp['candidati']} mosse dall'albero del campione {imp['ckpt']}, "
         f"{imp['iterazioni']} iterazioni, valutazione {VALUTAZIONE}, regole {imp['regole']}",
         f"partite {imp['partite']}, al piu' {imp['per_partita']} decisioni per partita; mondi di scelta "
         f"{imp['mondi_scelta'][0]}..{imp['mondi_scelta'][0] + imp['mondi_scelta'][1] - 1}, di verifica "
         f"{imp['mondi_verifica'][0]}..{imp['mondi_verifica'][0] + imp['mondi_verifica'][1] - 1}, "
         f"{imp['n_boot']} ricampionamenti di partite intere",
         f"decisioni esaminate {rs['esaminate']} (incoerenti: {rs['incoerenti']}, con un solo candidato: "
         f"{extra['un_candidato']}, scelte senza mondi validi: {extra['scelte_senza_mondi']}, verifiche senza mondi "
         f"validi: {rs['senza_mondi']}); cambiano mossa {rs['disaccordi']} ({100 * rs['tasso_disaccordo']:.1f}% delle "
         f"coerenti)",
         f"Pensa - campione, totale (ogni matchup pesa uguale, coincide = 0): {_pp(t)} (IC 95% da {100 * lo:+.1f} a "
         f"{100 * hi:+.1f})"]
    if rs["media_disaccordi"] is None:
        r.append("nessuna posizione cambia mossa con mondi validi: niente differenza da stimare")
    else:
        a, b = rs["ic95_disaccordi"]
        r.append(f"Pensa - campione sulle sole posizioni cambiate: {_pp(rs['media_disaccordi'])} (IC 95% da "
                 f"{100 * a:+.1f} a {100 * b:+.1f}); a favore {rs['a_favore']}, contro {rs['contro']}, pari {rs['pari']}")
    r.append(f"mondi di scelta validi {extra['mondi_scelta']}, esclusi {extra['mondi_scelta_esclusi']}; mondi di "
             f"verifica validi {rs['mondi_validi']}, esclusi {rs['mondi_esclusi']} (la prima mossa forzata non e' "
             f"quella chiesta)")
    r.append("per matchup (esaminate, incoerenti, cambiano mossa, tasso, Pensa - campione con IC 95%):")
    for mu, m in rs["per_matchup"].items():
        r.append(f"  {mu}: {m['esaminate']}, {m['incoerenti']}, {m['disaccordi']}, {100 * m['tasso_disaccordo']:.1f}%, "
                 f"{_pp(m['media'])} ({100 * m['ic95'][0]:+.1f} a {100 * m['ic95'][1]:+.1f})")
    c, pt, mac, ar = tm["cpu"], tm["per_turno"], tm["mac_turno"], tm["arena"]
    r.append(f"tempo di cpu per decisione (fase di scelta, {c['n']} decisioni giocate): mediana {_s(c['mediana'])} s, "
             f"95° percentile {_s(c['p95'])} s, massimo {_s(c['massimo'])} s")
    r.append(f"stima per turno sul Mac ({imp['processi_mac']} processi, un core del Mac = uno di questa macchina, stima "
             f"prudente): mediana {_s(mac['mediana'])} s, 95° percentile {_s(mac['p95'])} s; decisioni di turno per "
             f"turno: media {_s(pt['media'])}, 95° percentile {_s(pt['p95'])}")
    r.append(f"stima dell'arena ({ar['coppie']} coppie per matchup, {imp['n_matchup']} matchup, "
             f"{_s(ar['decisioni_per_partita'])} decisioni per partita): {_s(ar['ore_cpu'])} ore di cpu, "
             f"{_s(ar['ore_server'])} ore con {imp['processi_server']} processi")
    if rs["passa"]:
        r.append(f"regola di stop: PASSA (limite inferiore > 0 e almeno {MINIMO_CAMBI} posizioni cambiano mossa): "
                 f"prossimo passo «Pensa» nella pagina e arena")
    else:
        motivi = []
        if not lo > 0:
            motivi.append("limite inferiore <= 0")
        if rs["n_disaccordi_validi"] < MINIMO_CAMBI:
            motivi.append(f"solo {rs['n_disaccordi_validi']} posizioni cambiano mossa su {MINIMO_CAMBI} richieste")
        r.append(f"regola di stop: NON PASSA ({'; '.join(motivi)}): il campione resta com'e'")
    r.append(f"totale: {rs['esaminate']} decisioni, {rs['disaccordi']} cambiano mossa, {_pp(t)}, {secondi / 60:.1f} min")
    return r


# -- la corsa -----------------------------------------------------------------------------------------

def _controlla_impostazioni(out_dir: Path, ckpt, casuali, regole, iterazioni, matchup, n_partite, per_partita,
                            n_scelta, n_verifica) -> None:
    """Scrive `impostazioni.json` alla prima corsa; un rilancio nella stessa cartella riprende solo con le stesse
    impostazioni e lo stesso checkpoint (sha256): la cache delle decisioni e i mondi non si mescolano."""
    from riftbound.provenienza import checkpoint_sha256
    pc = Path(str(ckpt or D.CKPT_DEFAULT))
    pc = pc if pc.is_absolute() else D.ROOT / pc
    imp = {"ckpt_sha256": None if casuali else checkpoint_sha256(str(pc)), "casuali": bool(casuali),
           "regole": regole, "iterazioni": iterazioni, "valutazione": VALUTAZIONE, "base_seme": BASE_SEME,
           "matchup": list(matchup), "partite": n_partite, "per_partita": per_partita, "candidati": CANDIDATI,
           "mondi_scelta": [MONDI_SCELTA, n_scelta], "mondi_verifica": [MONDI_VERIFICA, n_verifica]}
    imp = json.loads(json.dumps(imp))
    f = out_dir / "impostazioni.json"
    if f.exists():
        if json.loads(f.read_text(encoding="utf-8")) != imp:
            raise ValueError(f"Impostazioni diverse da {f}: usare una nuova cartella.")
    else:
        f.write_text(json.dumps(imp, indent=1), encoding="utf-8")


def _leggi(f: Path):
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def posizioni(matchup, n_partite: int, per_partita: int, n_scelta: int, n_verifica: int, out_dir, ckpt,
              casuali: bool = False, processi: int = 1, regole: str = REGOLE, iterazioni: int = ITERAZIONI,
              n_boot: int = N_BOOT, processi_mac: int = PROCESSI_MAC, coppie_arena: int = COPPIE_ARENA,
              processi_server: int = PROCESSI_SERVER, print_=print) -> list[str]:
    """Tutto: le decisioni con i candidati (in cache in `decisioni.jsonl`), le scelte e le verifiche, riepilogo,
    `esito.json` {"passa", "totale", "cambi", "minimo_cambi"}."""
    out_dir = Path(out_dir)
    ms, mv = mondi(n_scelta, n_verifica)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    _controlla_impostazioni(out_dir, ckpt, casuali, regole, iterazioni, matchup, n_partite, per_partita,
                            n_scelta, n_verifica)
    parti = S.partite(matchup, n_partite, ckpt, casuali, iterazioni, regole)
    cache_path = out_dir / "decisioni.jsonl"
    cache = _leggi_cache(cache_path)
    da_fare = [p for p in parti if A.nome_partita(p) not in cache]
    print_(f"== decisioni: {len(parti)} partite ({len(parti) - len(da_fare)} gia' fatte), al piu' {per_partita} ciascuna")
    lavori = [(p, per_partita) for p in da_fare]
    vive = {A.nome_partita(p): p for p in da_fare}

    def salva(nome, decs, per_turno, n_idonee):
        partita = vive[nome]
        cache[nome] = {"partita": partita, "decisioni": [x | {"partita": partita} for x in decs],
                       "per_turno": per_turno, "n_idonee": n_idonee}
        with cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"nome": nome, "partita": partita,
                                "decisioni": [{k: v for k, v in x.items() if k != "partita"} for x in decs],
                                "per_turno": per_turno, "n_idonee": n_idonee}, ensure_ascii=False) + "\n")

    if processi > 1 and lavori:
        with ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn")) as pool:
            for j, res in enumerate(pool.map(_lavoro_partita, lavori), 1):
                salva(*res)
                print_(f"== partita {j}/{len(lavori)}: {len(res[1])} decisioni, {time.time() - t0:.0f} s")
    else:
        for j, lav in enumerate(lavori, 1):
            res = _lavoro_partita(lav)
            salva(*res)
            print_(f"== partita {j}/{len(lavori)}: {len(res[1])} decisioni, {time.time() - t0:.0f} s")

    decs, per_turno, per_part = [], [], []
    for p in parti:
        c = cache[A.nome_partita(p)]
        decs += c["decisioni"]
        per_turno += c["per_turno"]
        per_part.append(c["n_idonee"])

    # -- le rigiocate: cio' che manca, in un unico pool
    corsa = _Corsa(ms, mv, processi, print_)
    carts, verifiche, scelte_da_fare = {}, [], []
    for n, dec in enumerate(decs):
        if not dec["coerente"]:
            continue
        cart = carts[n] = out_dir / f"{n:03d}_{dec['nome']}_k{dec['k']}"
        sc = _leggi(cart / "scelta.json")
        if sc is None and len(dec["candidati"]) == 1:
            cart.mkdir(parents=True, exist_ok=True)
            sc = {"candidati": dec["candidati"], "n": dec["n"], "q": dec["q"], "mondi": [ms.start, 0],
                  "medie": [None], "n_mondi": 0, "mondi_esclusi": 0, "scelta": 0, "mossa": dec["candidati"][0],
                  "cpu": None, "cpu_mondi": [], "un_candidato": True}
            _scrivi_json(cart / "scelta.json", sc)
        if sc is None:
            scelte_da_fare.append(corsa.compito(n, dec, "scelta", cart))
        elif sc["scelta"] != 0 and not (cart / "verifica.json").exists():
            verifiche.append(corsa.compito(n, dec, "verifica", cart, sc["scelta"]))
    for job in verifiche + scelte_da_fare:
        corsa.aggiungi(job)
    print_(f"== rigiocate: {len(scelte_da_fare)} scelte e {len(verifiche)} verifiche da fare, {len(ms)} mondi di "
           f"scelta e {len(mv)} di verifica, {processi} processi")
    corsa.esegui()

    righe_dec, cpu, extra = [], [], {"un_candidato": 0, "scelte_senza_mondi": 0, "mondi_scelta": 0,
                                    "mondi_scelta_esclusi": 0}
    for n, dec in enumerate(decs):
        sc = ve = None
        if n in carts:
            sc = _leggi(carts[n] / "scelta.json")
            ve = _leggi(carts[n] / "verifica.json")
            if sc.get("un_candidato"):
                extra["un_candidato"] += 1
            else:
                extra["mondi_scelta"] += sc["n_mondi"]
                extra["mondi_scelta_esclusi"] += sc["mondi_esclusi"]
                extra["scelte_senza_mondi"] += sc["n_mondi"] == 0
                if sc["cpu"] is not None:
                    cpu.append(sc["cpu"])
        righe_dec.append(riga(dec, sc, ve))
    rs = C.riassunto(righe_dec, n_boot)
    rs["passa"] = regola_stop(rs)
    tm = tempi(cpu, per_turno, per_part, processi_mac, coppie_arena, len(matchup), processi_server)
    imp = {"ckpt": str(ckpt) if ckpt else "(pesi casuali)", "iterazioni": iterazioni, "regole": regole,
           "partite": len(parti), "per_partita": per_partita, "candidati": CANDIDATI,
           "mondi_scelta": [ms.start, len(ms)], "mondi_verifica": [mv.start, len(mv)], "n_boot": n_boot,
           "processi_mac": processi_mac, "coppie_arena": coppie_arena, "processi_server": processi_server,
           "n_matchup": len(matchup), "matchup": list(matchup)}
    testo = _testo(rs, imp, tm, extra, time.time() - t0)
    (out_dir / "riepilogo.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(json.dumps({"impostazioni": imp, "riassunto": rs, "tempi": tm,
                                                        "decisioni": righe_dec}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (out_dir / "esito.json").write_text(json.dumps({"passa": rs["passa"], "totale": rs["totale"],
                                                    "cambi": rs["n_disaccordi_validi"],
                                                    "minimo_cambi": MINIMO_CAMBI}), encoding="utf-8")
    return testo
