"""Sonda A a un'ondata: prototipo offline fuori dal bot (NON agganciato ad arena e pagina).

Costanti congelate sulle 24 posizioni della serie del 26/11 (vedi `SOGLIA`, `MONDI`); `VERIFICA` = mondi nuovi, mai
usati nello sviluppo (2000.. e 4000.. lo sono).

Pezzi:
  `proposte_a(pos)`   le proposte A dal menu visibile (un'ondata, senza informazione nascosta).
  `sonda(pos)`        la decisione: il campione contro le proposte A, a fine turno, sui mondi `ignote` appaiati.
  `valuta(...)`       una posizione: sonda e verifica a partita intera (migliore alternativa contro campione), classe.
  `congela(...)`      la sonda sulle posizioni della serie (controllo di identita' con le righe salvate).
  `fuori(...)`        `valuta` su posizioni fuori campione e riepilogo per gruppo e matchup.
  `diagnosi_t9(...)`  il caso diagnostico del T9 di Astra (linee guidate, foglia dopo l'avversario).
"""
from __future__ import annotations

import json
import multiprocessing
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median

from riftbound.rs import attacco as A, decisione_esp as E, decisione_rs as D

SOGLIA = 0.15            # congelata sulle 24, 26/11
MONDI = A.SCELTA         # (2000, 16): i mondi della sonda
MODO = "ignote"
VERIFICA = (6000, 100)   # mondi nuovi (2000.. e 4000.. sono di sviluppo)
RADICE = Path(__file__).resolve().parents[2]
ESCLUDI = "docs/bot/esperimenti/attacco_20261126/posizioni.json"
ATTESI = ("06_ES3B_k1", "08_ES4A_k10", "09_ES5B_k5", "11_ES6A_k1", "22_EK7B_k10", "19_EK4A_k27")


# -- le proposte ----------------------------------------------------------------------------------

def _verso(menu: list) -> set:
    """I campi raggiungibili dal menu con una mossa dalla base."""
    return {int(m.group(1)) for m in map(A._MOSSA.match, menu) if m}


def _vista(pos: dict) -> dict:
    """La vista del campione a k (stato del gioco a k, come `genera`)."""
    game = E.gioco(pos["P"], pos["tree"], pos["base"])
    return D.riassunto(json.loads(game.raw_dump()), pos["P"]["camp"])


def _ambush_in_mano(pos: dict) -> int:
    """Quanti nomi distinti di carte AMBUSH ha in mano il campione (vista Python, come `mondo`)."""
    from riftbound.rs import vista_rs
    raw = json.loads(E.gioco(pos["P"], pos["tree"], pos["base"]).raw_dump())
    gs, _ = vista_rs.carica(raw)
    return len({c.name for c in getattr(gs, pos["P"]["camp"]).hand if c.has_keyword("AMBUSH")})


def proposte_a(pos: dict) -> list[dict]:
    """Le proposte A: per ogni campo con mossa dalla base e controllato dall'avversario con almeno un'unita'
    (regola di `posizioni`), `none` a un'ondata; con almeno 2 nomi distinti di carte AMBUSH in mano anche con l'indice
    di AMBUSH 1. Record `{nome, field, proposal, ambush_mano}`."""
    verso = _verso(pos["menu"])
    campi = [f["campo"] for f in _vista(pos)["campi"]
             if f["controlla"] == "avversario" and f["avversario"]["unita"] and f["campo"] in verso]
    if not campi:
        return []
    ambush = _ambush_in_mano(pos)
    out = []
    for f in campi:
        for a in ((0, 1) if ambush >= 2 else (0,)):
            out.append({"nome": f"BF{f}a{a}", "field": f, "proposal": asdict(A.Proposal("none", 1, 1, a)),
                        "ambush_mano": ambush})
    return out


def campi_liberi(pos: dict) -> list[int]:
    """Campi raggiungibili dal menu, senza nemici, non controllati dal campione (regola `punto_libero`)."""
    verso = _verso(pos["menu"])
    return [f["campo"] for f in _vista(pos)["campi"]
            if f["campo"] in verso and not f["avversario"]["unita"] and f["controlla"] != "campione"]


# -- la sonda -------------------------------------------------------------------------------------

def _lavoro_sonda(args):
    pos, modo, i, linee = args
    st = A.mondo(pos, modo, pos["base"] + i)
    return [A.fino_fine_turno(pos, st, linea, i, modo) for linea in linee]


def _linee(proposte: list[dict]) -> list[dict]:
    return [A.linea_campione()] + [A.linea_proposta(p["nome"], A.Proposal(**p["proposal"]), p["field"]) for p in proposte]


def _righe_mondi(pos: dict, indici, linee: list[dict], processi: int, print_) -> list:
    """Per ogni mondo tutte le linee a fine turno (in parallelo per mondo, come `esegui`)."""
    lavori = [(pos, MODO, i, linee) for i in indici]
    pool = None
    try:
        if processi > 1:
            pool = ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn"))
            it = pool.map(_lavoro_sonda, lavori)
        else:
            it = map(_lavoro_sonda, lavori)
        out = []
        for j, rows in enumerate(it, 1):
            out.append(rows)
            if j == 1 or j % 10 == 0 or j == len(lavori):
                print_(f"  sonda: {j}/{len(lavori)} mondi")
        return out
    finally:
        if pool:
            pool.shutdown()


def sonda(pos: dict, processi: int = 1, mondi=MONDI, soglia: float = SOGLIA, print_=print) -> dict:
    """La sonda A: margine di ogni proposta = media sui mondi di `valore(proposta) - valore(campione)` a fine turno;
    "attacco" se il margine della migliore (a pari, la prima) supera `soglia`, se no "ordinaria". La migliore si
    registra sempre. `apertura_unica`: la migliore ha la stessa apertura in tutti i mondi."""
    t0 = time.time()
    proposte = proposte_a(pos)
    out = {"decisione": "ordinaria", "migliore": None, "margini": {}, "soglia": soglia, "proposte": proposte, "righe": [],
           "apertura_unica": None, "secondi_cpu": 0.0, "secondi_muro": 0.0, "linee": 1 + len(proposte), "mondi": mondi[1]}
    if not proposte:
        out["motivo"] = "nessuna proposta"
        out["secondi_muro"] = time.time() - t0
        return out
    linee = _linee(proposte)
    righe = _righe_mondi(pos, range(mondi[0], mondi[0] + mondi[1]), linee, processi, print_)
    for p in proposte:
        out["margini"][p["nome"]] = mean(A._riga(rows, p["nome"])["valore"] - A._riga(rows, A.NOME_RIF)["valore"]
                                         for rows in righe)
    out["migliore"] = max(out["margini"], key=out["margini"].get)       # a pari, la prima
    if out["margini"][out["migliore"]] > soglia:
        out["decisione"] = "attacco"
    aperture = {A._riga(rows, out["migliore"])["piano"]["apertura"] for rows in righe}
    out["apertura_unica"] = len(aperture) == 1
    out["apertura"] = sorted(a or "" for a in aperture)[0] if len(aperture) == 1 else sorted(a or "" for a in aperture)
    out["righe"] = righe
    out["secondi_cpu"] = sum(r["secondi"] for rows in righe for r in rows)
    out["secondi_muro"] = time.time() - t0
    return out


# -- una posizione --------------------------------------------------------------------------------

def _classe(decisione: str, lo: float, hi: float) -> str:
    if decisione == "attacco":
        return "vero positivo" if lo > 0 else "falso positivo" if hi < 0 else "neutro"
    return "falso negativo" if lo > 0 else "vero negativo" if hi < 0 else "neutro"


def _piano_verifica(rows: list) -> dict:
    """Il piano della riga della migliore nei mondi di verifica: attacchi completati, interruzioni per motivo, risposte
    piu' frequenti dell'avversario (prime 5: [punto, etichetta, mondi])."""
    piani = [r["piano"] for r in rows]
    risposte = Counter((p, e) for pi in piani for p, e in pi["risposte"])
    return {"mondi": len(piani), "completati": sum(bool(pi["completato"]) for pi in piani),
            "interruzioni": dict(Counter(pi["interruzione"] for pi in piani if pi["interruzione"])),
            "risposte": [[p, e, n] for (p, e), n in risposte.most_common(5)]}


def valuta(partita: dict, k: int, out_dir: Path | None, processi: int = 1, verifica=VERIFICA, print_=print,
           mondi=MONDI, soglia: float = SOGLIA) -> dict:
    """Una posizione: `sonda`, poi (se c'e' una proposta) la verifica a partita intera sui mondi `verifica`: campione
    e migliore alternativa. Classe, differenza della sonda, saturazione, punto libero, piano. Scrive in `out_dir`:
    sonda.json, sonda.jsonl, verifica.jsonl, esito.json, esito.txt."""
    pos = A.posizione(partita, k)
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    A.mondo(pos, MODO, pos["base"] + mondi[0])           # PosizioneNonAdatta subito
    s = sonda(pos, processi, mondi, soglia, print_)
    liberi = campi_liberi(pos)
    e: dict = {"partita": partita, "k": k, "turno": pos["turno"], "punto_libero": bool(liberi), "decisione": s["decisione"],
               "migliore": s["migliore"], "margine": s["margini"].get(s["migliore"]) if s["migliore"] else None,
               "soglia": soglia, "apertura": s.get("apertura"), "apertura_unica": s["apertura_unica"],
               "motivo": s.get("motivo"), "mondi": list(mondi), "verifica": list(verifica),
               "secondi_cpu": s["secondi_cpu"], "classe": "senza proposta", "differenza": None, "differenza_sonda": 0.0,
               "diff_mondi": [], "saturata": None, "punto_libero_preso": None, "piano_verifica": None}
    if out_dir:
        (out_dir / "sonda.json").write_text(json.dumps({c: v for c, v in s.items() if c != "righe"}, ensure_ascii=False,
                                                       indent=1), encoding="utf-8")
        with (out_dir / "sonda.jsonl").open("w", encoding="utf-8") as f:
            for rows in s["righe"]:
                f.write(json.dumps(rows, ensure_ascii=False) + "\n")
    if s["migliore"]:
        prop = next(p for p in s["proposte"] if p["nome"] == s["migliore"])
        linee_v = [A.linea_campione(), A.linea_proposta(prop["nome"], A.Proposal(**prop["proposal"]), prop["field"])]
        dati = A.esegui(pos, MODO, range(verifica[0], verifica[0] + verifica[1]), linee_v,
                        out_dir / "verifica.jsonl" if out_dir else None, processi, print_, piano=True)
        c = A.confronto(dati)
        d, rif = c[s["migliore"]], c[A.NOME_RIF]
        lo, hi = d["intervallo_95"]
        e["classe"] = _classe(s["decisione"], lo, hi)
        e["differenza"] = {"media": d["delta"], "intervallo_95": [lo, hi], "n": d["n"]}
        e["differenza_sonda"] = d["delta"] if s["decisione"] == "attacco" else 0.0
        e["diff_mondi"] = ([a["returns"] - b["returns"] for a, b in
                            ((A._riga(rows, s["migliore"]), A._riga(rows, A.NOME_RIF)) for rows in dati)]
                           if s["decisione"] == "attacco" else [0.0] * d["n"])
        e["vittorie"] = {"campione": rif["vittorie"], "migliore": d["vittorie"], "n": d["n"]}
        e["saturata"] = rif["vittorie"] in (0, d["n"])
        presi = {}
        for f in liberi:
            presi[str(f)] = {nome: sum(A._riga(rows, nome)["t9"]["fields"][f] == "campione" for rows in dati)
                             for nome in (A.NOME_RIF, s["migliore"])}
        e["punto_libero_preso"] = presi
        if e["classe"] == "vero negativo":
            conviene = any(v[A.NOME_RIF] * 2 > d["n"] for v in presi.values())
            e["motivo_negativo"] = "conviene il punto libero" if conviene else "il campione gioca meglio"
        e["piano_verifica"] = _piano_verifica([A._riga(rows, s["migliore"]) for rows in dati])
    if out_dir:
        (out_dir / "esito.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        (out_dir / "esito.txt").write_text("\n".join(testo_esito(e)) + "\n", encoding="utf-8")
    return e


def testo_esito(e: dict) -> list[str]:
    r = [f"posizione k={e['k']} (turno {e['turno']}, punto libero {'si' if e['punto_libero'] else 'no'}): "
         f"sonda {e['decisione']}" + (f" ({e['motivo']})" if e.get("motivo") else "")]
    if e["migliore"]:
        r.append(f"migliore {e['migliore']}, margine {e['margine']:+.3f} (soglia {e['soglia']}), apertura "
                 f"{e['apertura']}{'' if e['apertura_unica'] else ' [NON unica]'}; sonda {e['secondi_cpu']:.0f} s cpu")
    if e.get("differenza"):
        d = e["differenza"]
        r.append(f"verifica {e['verifica'][1]} mondi: {e['classe']}; differenza migliore - campione "
                 f"{100 * d['media']:+.1f} pp [{100 * d['intervallo_95'][0]:+.1f}, {100 * d['intervallo_95'][1]:+.1f}]"
                 f"; vittorie campione/migliore {e['vittorie']['campione']}/{e['vittorie']['migliore']}"
                 + ("; saturata" if e["saturata"] else ""))
        if e.get("motivo_negativo"):
            r.append(f"vero negativo: {e['motivo_negativo']}")
        if e["punto_libero_preso"]:
            r.append("punto libero preso (campione/migliore): " + ", ".join(
                f"BF{f} {v[A.NOME_RIF]}/{v[e['migliore']]}" for f, v in e["punto_libero_preso"].items()))
        pv = e["piano_verifica"]
        r.append(f"piano: attacco completato {pv['completati']}/{pv['mondi']}; interruzioni {pv['interruzioni'] or 'nessuna'}; "
                 f"risposte {[f'{p}: {x} ({n})' for p, x, n in pv['risposte']] or 'nessuna'}")
    return r


# -- congela: la sonda sulle 24 della serie ---------------------------------------------------------

def _uguali(a, b, tol: float = 1e-9) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_uguali(a[x], b[x], tol) for x in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_uguali(x, y, tol) for x, y in zip(a, b))
    return a == b


def _stato_identita(dif: list, fatti: int, attesi: int) -> str:
    """OK solo se tutti i confronti attesi sono stati fatti e nessuno differisce (Codex, PR 69: zero confronti non e'
    un'identita' verificata)."""
    if attesi == 0:
        return "identita NON DISPONIBILE (nessuna riga da confrontare)"
    if dif:
        return f"identita DIFFERENZE {len(dif)}" + ("" if fatti == attesi else f" (confronti {fatti} su {attesi})")
    return "identita OK" if fatti == attesi else f"identita INCOMPLETA (confronti {fatti} su {attesi})"


def _identita(s: dict, serie_p: list, scelta: list, riferimento_campione: bool) -> tuple[list[str], int, int]:
    """Confronta `valori.fine_turno` e `t9` delle righe della sonda con quelle salvate in scelta.jsonl (`continua`), per il
    riferimento e per le proposte A con una linea propria nella serie. -> (differenze, confronti fatti, confronti
    attesi): un mondo o una linea assenti dalle righe salvate contano come confronti mancati."""
    corrisp = {}
    if riferimento_campione:
        corrisp[A.NOME_RIF] = A.NOME_RIF
    for p in s["proposte"]:
        q = next((x for x in serie_p if x["field"] == p["field"] and x["proposal"] == p["proposal"]
                  and x["uguale_a"] is None), None)
        if q:
            corrisp[p["nome"]] = q["nome"]
    salvate = {rows[0]["world"]: rows for rows in scelta}
    dif = []
    fatti = attesi = 0
    for rows in s["righe"]:
        for r in rows:
            if r["line"] not in corrisp:
                continue
            attesi += 1
            vecchia = salvate.get(r["world"])
            v = None if vecchia is None else next((x for x in vecchia if x["line"] == corrisp[r["line"]]), None)
            if v is None:
                continue
            fatti += 1
            if not _uguali(r["valori"], v["valori"]["fine_turno"]):
                dif.append(f"mondo {r['world']} {r['line']}: valori {r['valori']} contro {v['valori']['fine_turno']}")
            if not _uguali(json.loads(json.dumps(r["t9"])), v["t9"]):
                dif.append(f"mondo {r['world']} {r['line']}: t9 diverso")
    return dif, fatti, attesi


def congela(serie_dir: Path, out_dir: Path, processi: int = 1, print_=print, ckpt: str | None = None,
            casuali: bool = False, mondi=MONDI, solo: list[str] | None = None, rivedi_dir: Path | None = None) -> list[str]:
    """La sonda sulle posizioni della serie (cartelle `NN_*` con esito.json). Per ogni posizione: controllo di identita'
    con scelta.jsonl, decisione, migliore, margine, apertura, `saturata`, esito della serie e di `rivedi`. `solo`: prefissi
    dei nomi di cartella da fare (per le prove). Scrive congela.txt e congela.json in `out_dir`."""
    serie_dir, out_dir = Path(serie_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if rivedi_dir is None:
        trovate = sorted(p for p in serie_dir.glob("rivedi_*") if p.is_dir())
        rivedi_dir = trovate[-1] if trovate else None
    righe: list[str] = []
    schede: list[dict] = []
    tot = {"attacco": 0, "ordinaria": 0, "senza": 0, "errori": 0, "diff": 0, "id_ok": 0, "posizioni": 0}
    attacchi_attesi = []
    fuori_attesi = []
    for cart in sorted(p for p in serie_dir.iterdir() if (p / "esito.json").is_file()):
        if solo and not any(cart.name.startswith(x) for x in solo):
            continue
        print_(f"== {cart.name}")
        esito = json.loads((cart / "esito.json").read_text(encoding="utf-8"))
        partita, k = dict(esito["partita"]), esito["k"]
        if ckpt:
            partita["ckpt"] = ckpt
        if casuali:
            partita["casuali"] = True
        scheda: dict = {"cartella": cart.name, "k": k, "esito_serie": esito["esito"]}
        try:
            pos = A.posizione(partita, k)
            A.mondo(pos, MODO, pos["base"] + mondi[0])
            s = sonda(pos, processi, mondi, SOGLIA, print_)
        except A.PosizioneNonAdatta as x:
            righe.append(f"{cart.name} | saltata: {x}")
            scheda["errore"] = f"saltata: {x}"
            schede.append(scheda)
            continue
        except Exception as x:    # una posizione che fallisce non ferma le altre
            righe.append(f"{cart.name} | ERRORE {type(x).__name__}: {x}")
            scheda["errore"] = f"{type(x).__name__}: {x}"
            tot["errori"] += 1
            schede.append(scheda)
            continue
        serie_p = json.loads((cart / "proposte.json").read_text(encoding="utf-8"))
        scelta = A._rilegge(cart / "scelta.jsonl")
        dif, fatti, attesi = _identita(s, serie_p, scelta, esito["riferimento"] == "campione")
        stato_id = _stato_identita(dif, fatti, attesi)
        tot["id_ok"] += stato_id == "identita OK"
        rif_salvato = [A._riga(rows, A.NOME_RIF)["returns"] for rows in scelta] if esito["riferimento"] == "campione" else []
        saturata = bool(rif_salvato) and sum(r == 1.0 for r in rif_salvato) in (0, len(rif_salvato))
        rivedi_testo = "-"
        if s["migliore"]:
            prop = next(p for p in s["proposte"] if p["nome"] == s["migliore"])
            q = next((x for x in serie_p if x["field"] == prop["field"] and x["proposal"] == prop["proposal"]), None)
            nome_serie = (q["uguale_a"] or q["nome"]) if q else None
            rv = cart.parent / rivedi_dir.name / cart.name / "rivedi.json" if rivedi_dir else None
            if nome_serie and rv and rv.is_file():
                linea = json.loads(rv.read_text(encoding="utf-8")).get("linee", {}).get(nome_serie)
                if linea:
                    rivedi_testo = "migliore" if linea["migliore"] else "peggiore" if linea["peggiore"] else "indecisa"
            if rivedi_testo == "-" and nome_serie and esito.get("proposta", {}).get("nome") == nome_serie:
                rivedi_testo = "(la scelta della serie)"
        tot[s["decisione"] if s["migliore"] else "senza"] += 1
        tot["diff"] += len(dif)
        tot["posizioni"] += 1
        marg = s["margini"].get(s["migliore"]) if s["migliore"] else None
        if (cart.name in ATTESI) != (s["decisione"] == "attacco"):
            fuori_attesi.append(cart.name)
        if s["decisione"] == "attacco":
            attacchi_attesi.append(cart.name)
        scheda.update({"decisione": s["decisione"], "migliore": s["migliore"], "margine": marg, "apertura": s.get("apertura"),
                       "apertura_unica": s["apertura_unica"], "saturata": saturata, "rivedi": rivedi_testo,
                       "identita": dif[:10], "identita_confronti": [fatti, attesi], "identita_stato": stato_id,
                       "secondi_cpu": s["secondi_cpu"], "margini": s["margini"]})
        schede.append(scheda)
        righe.append(f"{cart.name} | {s['decisione']} | migliore {s['migliore']} | margine "
                     + (f"{marg:+.3f}" if marg is not None else "-") + f" | apertura {s.get('apertura')}"
                     + ("" if s["apertura_unica"] in (True, None) else " [NON unica]")
                     + f" | saturata {'si' if saturata else 'no'} | serie: {esito['esito']} | rivedi: {rivedi_testo} | "
                     + stato_id)
        for d in dif[:3]:
            righe.append(f"    {d}")
        (out_dir / "congela.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    righe.append(f"totale: attacco {tot['attacco']} (attesi {len(ATTESI)}), ordinaria {tot['ordinaria']}, senza proposta "
                 f"{tot['senza']}, identità OK in {tot['id_ok']} su {tot['posizioni']} posizioni"
                 + (f", DIFFERENZE {tot['diff']}" if tot["diff"] else "")
                 + (f", incompleta o non disponibile in {tot['posizioni'] - tot['id_ok']}"
                    if not tot["diff"] and tot["id_ok"] < tot["posizioni"] else "")
                 + (f", fuori dall'atteso: {', '.join(fuori_attesi)}" if fuori_attesi and not solo else "")
                 + (f", errori {tot['errori']}" if tot["errori"] else ""))
    (out_dir / "congela.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    (out_dir / "congela.json").write_text(json.dumps(schede, ensure_ascii=False, indent=1), encoding="utf-8")
    return righe


# -- fuori campione ---------------------------------------------------------------------------------

def _chiave_partita(p: dict):
    return ("pagina", p["file"]) if p["tipo"] == "pagina" else (p["matchup"], p["seed"], p.get("campione", "A"))


def _matchup(p: dict) -> str:
    return "pagina" if p["tipo"] == "pagina" else p["matchup"]


def _gruppo(m: str) -> str:
    return "principale" if m in ("ES", "EK") else "trasferimento"


def fuori(posizioni_json: Path, out_dir: Path, processi: int = 1, per_matchup: dict | None = None, escludi: Path | None = None,
          print_=print, ckpt: str | None = None, casuali: bool = False, verifica=VERIFICA, mondi=MONDI) -> list[str]:
    """`valuta` su posizioni fuori campione (json di `attacco.py posizioni`) e `riepilogo.txt`. `escludi`: json di
    posizioni di sviluppo (default `ESCLUDI`); una posizione di una loro partita si salta. `per_matchup` {matchup: n}: al
    piu' n posizioni per matchup (`scegli_posizioni`); un matchup non elencato non ha limite."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    elenco = json.loads(Path(posizioni_json).read_text(encoding="utf-8"))
    pe = Path(escludi) if escludi else RADICE / ESCLUDI
    esclusi = {_chiave_partita(x["partita"]) for x in json.loads(pe.read_text(encoding="utf-8"))} if pe.is_file() else set()
    scelte, righe = [], []
    for m in dict.fromkeys(_matchup(x["partita"]) for x in elenco):
        mie = [x for x in elenco if _matchup(x["partita"]) == m]
        nuove = [x for x in mie if _chiave_partita(x["partita"]) not in esclusi]
        for x in mie:
            if x not in nuove:
                righe.append(f"{x.get('nome', m)} | k={x['k']} | saltata: partita di sviluppo")
        n = (per_matchup or {}).get(m)
        scelte += A.scegli_posizioni(nuove, n) if n else nuove
    esiti: list[dict] = []
    righe_pos: list[str] = []
    for n, p in enumerate(scelte):
        partita = dict(p["partita"])
        if ckpt:
            partita["ckpt"] = ckpt
        if casuali:
            partita["casuali"] = True
        nome = A.nome_partita(partita)
        m = _matchup(partita)
        print_(f"== posizione {n}: {nome} k={p['k']} turno {p['turno']}")
        try:
            e = valuta(partita, p["k"], out_dir / f"{n:02d}_{nome}_k{p['k']}", processi, verifica, print_, mondi)
        except A.PosizioneNonAdatta as x:
            righe_pos.append(f"{nome} | {m} | k={p['k']} | saltata: {x}")
            continue
        except Exception as x:   # una posizione che fallisce non ferma le altre
            righe_pos.append(f"{nome} | {m} | k={p['k']} | ERRORE {type(x).__name__}: {x}")
            print_(f"  ERRORE {type(x).__name__}: {x}")
            continue
        e["matchup"] = m
        e["nome_partita"] = nome
        esiti.append(e)
        presi = e["punto_libero_preso"]
        preso = "-" if not presi else "/".join(f"{v[A.NOME_RIF]}" for v in presi.values())
        righe_pos.append(
            f"{nome} | {m} | k={p['k']} | turno {e['turno']} | punto libero {'si' if e['punto_libero'] else 'no'} | "
            f"{e['decisione']} | margine " + (f"{e['margine']:+.3f}" if e["margine"] is not None else "-")
            + f" | {e['classe']}" + (f" ({e['motivo_negativo']})" if e.get("motivo_negativo") else "")
            + " | differenza " + (f"{100 * e['differenza']['media']:+.1f} pp" if e["differenza"] else "-")
            + f" | saturata {'-' if e['saturata'] is None else 'si' if e['saturata'] else 'no'} | punto libero preso {preso}"
            + f" | sonda {e['secondi_cpu']:.0f} s cpu")
        (out_dir / "riepilogo.txt").write_text("\n".join(righe + righe_pos) + "\n", encoding="utf-8")
    righe = righe + righe_pos
    for titolo, chiave in (("gruppo", lambda e: _gruppo(e["matchup"])), ("matchup", lambda e: e["matchup"])):
        for g in sorted({chiave(e) for e in esiti}):
            righe.append(f"{titolo} {g}: " + _riassunto([e for e in esiti if chiave(e) == g]))
    tutte = [d for e in esiti for d in e["diff_mondi"]]
    ic = intervallo_partite(esiti)
    if ic is not None:
        righe.append(f"differenza media sonda - campione su {len(esiti)} posizioni ({len(tutte)} mondi appaiati, zeri "
                     f"compresi): {100 * ic[0]:+.2f} pp, IC 95% [{100 * ic[1]:+.2f}, {100 * ic[2]:+.2f}] ricampionando "
                     f"le partite di origine dentro ogni matchup ({ic[3]} partite)")
    t = sorted(e["secondi_cpu"] for e in esiti)
    if t:
        righe.append(f"tempo della sonda per posizione (s cpu): mediana {median(t):.0f}, 95° percentile "
                     f"{t[min(len(t) - 1, int(0.95 * len(t)))]:.0f}, massimo {t[-1]:.0f}")
    righe.append("totale: " + _riassunto(esiti))
    (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    return righe


def intervallo_partite(esiti: list[dict], n_boot: int = 40_000, seme: int = 0):
    """(media, basso, alto, partite) della differenza sonda - campione: valore di una posizione = media dei suoi mondi
    (zeri compresi dove la sonda lascia giocare il campione); media = media delle posizioni. IC 95% (Astra, 27/11):
    ricampiona con reinserimento le partite di origine dentro ogni matchup (stesso numero), tenendo insieme i loro
    turni e i loro mondi; la media di ogni replica e' sulle posizioni estratte. None senza posizioni con mondi."""
    import numpy as np
    per: dict = {}
    for e in esiti:
        if e.get("diff_mondi"):
            g = per.setdefault(e["matchup"], {}).setdefault(e.get("nome_partita") or A.nome_partita(e["partita"]), [])
            g.append(float(mean(e["diff_mondi"])))
    valori = [v for g in per.values() for vv in g.values() for v in vv]
    if not valori:
        return None
    rng = np.random.default_rng(seme)
    somma, conta = np.zeros(n_boot), np.zeros(n_boot)
    for partite in per.values():
        s = np.array([sum(v) for v in partite.values()])
        c = np.array([len(v) for v in partite.values()], float)
        idx = rng.integers(0, len(s), (n_boot, len(s)))
        somma += s[idx].sum(axis=1)
        conta += c[idx].sum(axis=1)
    boot = somma / conta
    return (float(np.mean(valori)), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)),
            sum(len(p) for p in per.values()))


def _riassunto(es: list[dict]) -> str:
    c = Counter(e["classe"] for e in es)
    fp = [e["differenza"]["media"] for e in es if e["classe"] == "falso positivo"]
    vn = [e for e in es if e["classe"] == "vero negativo"]
    return (f"posizioni {len(es)}, veri positivi {c['vero positivo']}, falsi positivi {c['falso positivo']}"
            + (f" (costo medio {100 * mean(fp):+.1f} pp)" if fp else "")
            + f", falsi negativi {c['falso negativo']}, veri negativi {len(vn)} (conviene il punto libero "
            f"{sum(e.get('motivo_negativo') == 'conviene il punto libero' for e in vn)}), neutri {c['neutro']}, "
            f"senza proposta {c['senza proposta']}, saturate {sum(bool(e['saturata']) for e in es)}")


# -- il caso diagnostico del T9 ---------------------------------------------------------------------

def _tipici_t9(righe: list, n: int = 3) -> list:
    c = Counter(json.dumps({x: r["t9"][x] for x in ("points", "fields", "theirs", "ours", "base_camp")}, sort_keys=True)
                for r in righe)
    return [(json.loads(k), v) for k, v in c.most_common(n)]


def diagnosi_t9(out_dir: Path, processi: int = 1, ckpt: str | None = None, casuali: bool = False, print_=print,
                mondi: int = 100) -> list[str]:
    """Il caso diagnostico del T9 (partita 013325, k=10): `valley`, `campione`, `buff_sett`, `matteo` e la proposta p16 su
    `mondi` mondi (semi base + 0..), modi `ignote` e `fisse`, partite intere. Identita' di `valley`, `matteo`, `buff_sett`
    con i dati di Astra, vittorie e foglia (valutazione a fine T9 e dopo l'avversario) per linea."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    partita = {"tipo": "pagina", "file": A.T9_REPLAY, "ckpt": ckpt, "casuali": casuali}
    pos = A.posizione(partita, 10)
    p16 = A.genera(pos, deduplica=False)[16]
    linee = [A.linea_sequenza([x.strip() for x in A.T9_RIFERIMENTO.split(" ; ")], "valley"),
             {"nome": "campione", "tipo": "campione"},
             A.linea_guidata_t9("buff_sett", "buff_sett"), A.linea_guidata_t9("matteo", "matteo"),
             A.linea_proposta("p16", A.Proposal(**p16["proposal"]), p16["field"])]
    righe: list[str] = [f"proposta p16: campo {p16['field']} {p16['proposal']}"]
    difetti = 0
    dati_astra = RADICE / "docs/bot/esperimenti/t9_attacco/dati"
    for modo in ("ignote", "fisse"):
        print_(f"== {modo}")
        dati = A.esegui(pos, modo, range(mondi), linee, out_dir / f"{modo}.jsonl", processi, print_)
        astra = A._rilegge(dati_astra / f"{modo}_0_100.jsonl")
        dif = []
        fatti, attesi = 0, 3 * len(dati)          # valley, matteo, buff_sett in ogni mondo rifatto
        for wm, wa in zip(dati, astra):
            da = {r["line"]: r for r in wa}
            for r in wm:
                if r["line"] in ("valley", "matteo", "buff_sett") and r["line"] in da:
                    fatti += 1
                    dif += [f"mondo {r['world']} {r['line']}: {d}" for d in A._riga_uguale(json.loads(json.dumps(r)), da[r["line"]])]
        difetti += len(dif) + (attesi - fatti)    # un confronto mancato non e' un'identita' (Codex, PR 69)
        righe.append(f"{modo}: identità con Astra (valley, matteo, buff_sett), confronti {fatti} su {attesi}: "
                     + ("IDENTICA" if not dif and fatti == attesi > 0 else
                        f"INCOMPLETA ({attesi - fatti} mancati)" if not dif else f"DIFFERENZE {len(dif)}; prime: {dif[:3]}"))
        c = A.confronto(dati, "valley")
        for li in linee:
            n = li["nome"]
            rr = [A._riga(rows, n) for rows in dati]
            voce = c[n]
            testo = (f"  {n}: vittorie {voce['vittorie']}/{voce['n']}, differenza con valley {100 * voce['delta']:+.1f} pp "
                     f"[{100 * voce['intervallo_95'][0]:+.1f}, {100 * voce['intervallo_95'][1]:+.1f}]")
            for punto, coda in (("fine_turno", "fine T9"), ("fine_turno_avv", "dopo l'avversario")):
                for ch in next((r["valori"][punto] for r in rr if r["valori"][punto]), {}):
                    v = [r["valori"][punto][ch] for r in rr if r["valori"][punto]]
                    vinti = [r["valori"][punto][ch] for r in rr if r["valori"][punto] and r["returns"] == 1.0]
                    persi = [r["valori"][punto][ch] for r in rr if r["valori"][punto] and r["returns"] != 1.0]
                    d = voce["valori"].get(ch + ("" if punto == "fine_turno" else " dopo l'avversario"))
                    testo += (f"\n      foglia {ch} {coda}: media {mean(v):+.3f}" + (f", contro valley {d['media']:+.3f}" if d else "")
                              + (f", vinti {mean(vinti):+.3f}" if vinti else "") + (f", persi {mean(persi):+.3f}" if persi else ""))
            righe.append(testo)
        for n in ("p16", "buff_sett"):
            righe.append(f"  t9 più frequenti di {n}: " + "; ".join(
                f"{v}x {t['points']} {t['fields']} nostre {t['ours']}" for t, v in _tipici_t9([A._riga(rows, n) for rows in dati])))
    righe.append(f"totale: {mondi} mondi per modo, 5 linee; identità con Astra " + ("OK" if not difetti else f"DIFFERENZE {difetti}"))
    (out_dir / "diagnosi_t9.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    return righe
