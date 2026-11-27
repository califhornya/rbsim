"""Muovo prima contro schiero in base (Astra, 27/11): su una posizione dove un'unita' puo' andare su un campo libero e,
da li', un'altra unita' puo' essere schierata, conviene muovere prima o schierare in base adesso?

Caso di partenza: partita della pagina 20261126_155859, turno 5, il campione gioca "Play Fiora Victorious" (in base) e poi
"Move Sett Kingpin base→BF1"; la linea di Matteo, "Move Sett Kingpin base→BF1" e poi "Play Fiora Victorious to BF1",
vinceva +19 pp sugli stessi 100 mondi (la ricerca: 136 visite a Fiora in base, 1 a muovere Sett).

  `replay_default()`      i replay salvati della pagina, esclusi quelli con il seme della partita della scoperta.
  `scegli(o, vista)`      la regola di selezione su una riga di `D.originale` (deterministica, senza esiti).
  `selezionate(partita)`  le posizioni di una partita: al piu' la prima che qualifica per ogni turno del campione.
  `partite_autonome(...)` partite NUOVE del campione (10 matchup, semi da `BASE_SEME_NUOVE`), come `seguiti.partite`.
  `gioca_posizione(...)`  le tre linee (riferimento, "muovo prima", "schiero in base") sugli stessi mondi `ignote`,
                          `decisione.json`. Con `quota` (modo quota) quattro linee: "campione" (la sua mossa ORIGINALE,
                          forzata), M, B e "con quota" (la ricerca rifatta con la quota alla radice: `QUOTA_*`).
  `riassunto(...)`        media M-B per posizione (ognuna pesa 1), intervallo 95% ricampionando le PARTITE.
  `riassunto_quota(...)`  sottoinsiemi per mossa originale del campione, Q - campione su TUTTE le posizioni (zeri
                          compresi), regola di stop.
  `muovi(...)`            tutto; scrive `riepilogo.json` e `riepilogo.txt` (ultima riga `totale:`) e, col modo quota,
                          `esito.json`.
  `arena_quota(...)`      se la regola passa: candidato (campione con quota alla radice) contro il campione.

Il prefisso si rigioca con le impostazioni registrate nel replay (come `A.posizione`); la continuazione dopo la prima
mossa forzata e' il campione di oggi: `ITERAZIONI` iterazioni e valutazione `VALUTAZIONE` su entrambi i posti.
"""
from __future__ import annotations

import json
import math
import multiprocessing
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from riftbound.rs import arena_rs, attacco as A, decisione_rs as D, seguiti as S

ITERAZIONI = 138
VALUTAZIONE = "rimonta"
MONDI0 = 30_000
N_MONDI = 100
N_BOOT = 40_000
NOME_M = "muovo prima"
NOME_B = "schiero in base"
NOME_CAMPIONE = "campione"              # la sua mossa originale, forzata (modo quota)
NOME_Q = "con quota"
QUOTA_ETICHETTE = ["base→bf"]           # figli della radice "da base a un campo" (minuscolo, sottostringa)
QUOTA_VISITE = 8                        # visite iniziali riservate a ciascuno
MIN_POSIZIONI = 20                      # regola di stop: posizioni valide minime (27/11, prima dei risultati)
MIN_CAMBIANO = 5                        # regola di stop: posizioni minime in cui la quota cambia mossa
BASE_SEME_NUOVE = 80_000_000            # partite autonome nuove (la raccolta 30M, arena di sviluppo 40M, seguiti 50M)
BASE_SEME_ARENA = 90_000_000            # arena: aperture nuove
SEME_SCOPERTA = "20261126_155859"       # la partita della scoperta (la 20261126_013325 ha lo stesso seme)
CARTELLA_REPLAY = D.ROOT / "docs/bot/partite/coach"

_MUOVI = re.compile(r"^Move .* base→BF(\d+)$")
_GIOCA = re.compile(r"^Play (.+)$")
_IN_CAMPO = re.compile(r" to BF\d+$")


# -- i replay ---------------------------------------------------------------------------------------

def _seme_replay(f: Path) -> int | None:
    return json.loads(Path(f).read_text(encoding="utf-8"))["replay"]["seed"]


def replay_default(cartella: Path = CARTELLA_REPLAY) -> list[Path]:
    """I replay salvati della pagina (`*.json`, non i `reports_*.jsonl`) senza quelli con il seme della partita della
    scoperta, in ordine di nome."""
    cartella = Path(cartella)
    scoperta = next(iter(sorted(cartella.glob(f"{SEME_SCOPERTA}_*.json"))), None)
    escluso = _seme_replay(scoperta) if scoperta else None
    return [f for f in sorted(cartella.glob("*.json")) if escluso is None or _seme_replay(f) != escluso]


def partite_replay(files, ckpt) -> list[dict]:
    return [{"tipo": "pagina", "file": str(Path(f).resolve()), "ckpt": str(ckpt)} for f in files]


def partite_autonome(matchup, n_partite: int, ckpt, casuali: bool, iterazioni: int = ITERAZIONI,
                     base_seme: int = BASE_SEME_NUOVE, regole: str = S.REGOLE) -> list[dict]:
    """Per ogni matchup `n_partite` partite autonome nuove del campione (come `seguiti.partite`): seme
    `base_seme` + 1000 * indice del matchup in `arena_rs.COPERTI` + j, il campione al posto A per j pari e B per j
    dispari, valutazione `rimonta` su entrambi i posti (`entrambi=True`), regole D72-D83."""
    out = []
    for mu in matchup:
        i = arena_rs.COPERTI.index(mu)
        for j in range(n_partite):
            out.append(D.autonoma(mu, base_seme + 1_000 * i + j, ckpt, casuali, iterazioni, "A" if j % 2 == 0 else "B",
                                  regole=regole, valutazione=D._valutazione_registrata(VALUTAZIONE), entrambi=True))
    return out


def _id_partita(p: dict) -> str:
    if p["tipo"] == "pagina":
        return Path(p["file"]).name
    return f"{A.nome_partita(p)}/{p.get('iterazioni')}"


def registrate(partita: dict) -> dict:
    """Regole, valutazione, iterazioni e seme registrati della partita (il prefisso si rigioca con questi)."""
    P = D._prepara(partita)
    return {"nome": A.nome_partita(partita), "seme": P["seed"], "regole": P["regole"],
            "valutazione": P["valutazione"][0] if P["valutazione"] else "storica", "iterazioni": P["iterazioni"]}


# -- selezione --------------------------------------------------------------------------------------

def e_unita(nome: str) -> bool:
    """Una carta che si schiera come unita': UNIT o CHAMPION (il campione si gioca come unita') del registro delle carte
    del motore (`riftbound.registry.cards_registry.CARD_REGISTRY`, da `all_cards.json`)."""
    from riftbound.core.enums import CardType
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get(nome)
    return spec is not None and spec.category in (CardType.UNIT, CardType.CHAMPION)


def _prior(o: dict) -> dict[str, float]:
    """Il prior P della riga di ricerca originale per etichetta del menu (via json.dumps come `scelta.scelte`)."""
    riga = o["riga"]
    etichetta = {json.dumps(a): o["menu"][i] for i, a in enumerate(riga["menu"]) if i < len(o["menu"])}
    out: dict[str, float] = {}
    for a, p in riga.get("P") or []:
        lab = etichetta.get(json.dumps(a))
        if lab is not None and lab not in out:
            out[lab] = p
    return out


def _preferita(cand: list[str], o: dict, prior: dict[str, float]) -> str:
    """La mossa giocata dal campione se e' fra i candidati, altrimenti quella col prior piu' alto (a pari prior l'ordine
    del menu)."""
    if o["action"] in cand:
        return o["action"]
    best = cand[0]
    for lab in cand[1:]:
        if prior.get(lab, 0.0) > prior.get(best, 0.0):
            best = lab
    return best


def scegli(o: dict, vista: dict, unita=e_unita) -> dict | None:
    """La regola di selezione su una decisione `turn_action` del campione (riga di `D.originale`, `vista` = `D.riassunto`
    dello stato): campi liberi = senza unita' dell'avversario e non controllati dal campione; M = "Move ... base→BF<i>"
    con i libero; B = "Play <Carta>" (in base) con la carta unita'. Qualifica se M e B non sono vuoti. None altrimenti."""
    if len(o["menu"]) < 2:
        return None
    liberi = {f["campo"] for f in vista["campi"] if not f["avversario"]["unita"] and f["controlla"] != "campione"}
    m = [x for x in o["menu"] if (g := _MUOVI.match(x)) and int(g.group(1)) in liberi]
    b = [x for x in o["menu"] if (g := _GIOCA.match(x)) and not _IN_CAMPO.search(x) and unita(g.group(1))]
    if not m or not b:
        return None
    prior = _prior(o)
    lab_m, lab_b = _preferita(m, o, prior), _preferita(b, o, prior)
    return {"k": o["k"], "turno": o["turn"], "lab_M": lab_m, "lab_B": lab_b,
            "P_M": prior.get(lab_m), "P_B": prior.get(lab_b), "campione": o["action"],
            "scelta_campione": "M" if o["action"] == lab_m else "B" if o["action"] == lab_b else None,
            "n_M": len(m), "n_B": len(b), "liberi": sorted(liberi),
            "campi": [{"campo": f["campo"], "controlla": f["controlla"],
                       "unita_avv": len(f["avversario"]["unita"]), "unita_camp": len(f["campione"]["unita"])}
                      for f in vista["campi"]]}


def selezionate(partita: dict) -> list[dict]:
    """Le posizioni di una partita: per ogni decisione `turn_action` del campione (menu con >= 2 voci) la regola
    `scegli`, al piu' la PRIMA che qualifica per ogni turno del campione."""
    camp = D._prepara(partita)["camp"]
    orig = D.originale(partita, stato=lambda s: s["point"] == "turn_action")
    fatti: set = set()
    out = []
    for o in orig:
        if o["seat"] != camp or o["point"] != "turn_action" or o["turn"] in fatti or len(o["menu"]) < 2:
            continue
        st = o["e"].get("state_raw")
        if st is None:
            continue
        s = scegli(o, D.riassunto(st, camp))
        if s:
            fatti.add(o["turn"])
            out.append({"partita": partita, "nome": A.nome_partita(partita)} | s)
    return out


# -- una posizione ----------------------------------------------------------------------------------

def _ic(delta: list[float]) -> dict:
    n = len(delta)
    if not n:
        return {"n": 0, "media": None, "ic95": None}
    m = float(np.mean(delta))
    if n < 2:
        return {"n": n, "media": m, "ic95": None}
    marg = 1.96 * float(np.std(delta, ddof=1)) / math.sqrt(n)
    return {"n": n, "media": m, "ic95": [m - marg, m + marg]}


def analizza(dati: list) -> dict:
    """Da `A.esegui` (per mondo le righe delle tre linee): vittorie e patte per linea nei mondi validi (una linea
    forzata con `primo_ok` falso e' esclusa dai confronti che la riguardano), delta appaiati M-B, M-rif, B-rif
    (ritorni dal posto del campione) e i flip M contro B."""
    righe = [{x["line"]: x for x in rows} for rows in dati]

    def ok(r, nome):
        return r[nome].get("primo_ok", True)

    def ret(r, nome):
        return r[nome]["returns"]

    linee = {}
    for nome in (A.NOME_RIF, NOME_M, NOME_B):
        v = [ret(r, nome) for r in righe if ok(r, nome)]
        linee[nome] = {"n": len(v), "vittorie": sum(x == 1.0 for x in v), "patte": sum(x == 0.5 for x in v),
                       "sconfitte": sum(x == 0.0 for x in v), "esclusi": len(righe) - len(v)}

    def delta(a, b):
        return [ret(r, a) - ret(r, b) for r in righe if ok(r, a) and ok(r, b)]

    mb = [(ret(r, NOME_M), ret(r, NOME_B)) for r in righe if ok(r, NOME_M) and ok(r, NOME_B)]
    d = {"M-B": delta(NOME_M, NOME_B), "M-rif": delta(NOME_M, A.NOME_RIF), "B-rif": delta(NOME_B, A.NOME_RIF)}
    return {"linee": linee, "deltas": d, "stat": {k: _ic(v) for k, v in d.items()},
            "flip": {"B_perde_M_vince": sum(b == 0.0 and m == 1.0 for m, b in mb),
                     "B_vince_M_perde": sum(b == 1.0 and m == 0.0 for m, b in mb)},
            "n_mondi": len(righe)}


def linee_quota(campione: str, lab_m: str, lab_b: str, lab_q: str) -> tuple[list[dict], dict]:
    """Le linee del modo quota (prima mossa forzata) con le etichette uguali giocate una volta sola: -> (linee, mappa)
    con `mappa[nome]` = il nome della linea che rappresenta `nome`."""
    prima: dict[str, str] = {}
    mappa: dict[str, str] = {}
    linee = []
    for nome, lab in ((NOME_CAMPIONE, campione), (NOME_M, lab_m), (NOME_B, lab_b), (NOME_Q, lab_q)):
        if lab not in prima:
            prima[lab] = nome
            linee.append(A.linea_primo(nome, lab))
        mappa[nome] = prima[lab]
    return linee, mappa


def analizza_quota(dati: list, mappa: dict) -> dict:
    """Come `analizza` per le quattro linee del modo quota (`mappa` da `linee_quota`): delta appaiati M-B, M-campione,
    B-campione, Q-campione (zeri esatti se la mossa con la quota e' quella del campione: e' la stessa linea)."""
    righe = [{x["line"]: x for x in rows} for rows in dati]

    def ok(r, nome):
        return r[mappa[nome]].get("primo_ok", True)

    def ret(r, nome):
        return r[mappa[nome]]["returns"]

    nomi = (NOME_CAMPIONE, NOME_M, NOME_B, NOME_Q)
    linee = {}
    for nome in nomi:
        v = [ret(r, nome) for r in righe if ok(r, nome)]
        linee[nome] = {"n": len(v), "vittorie": sum(x == 1.0 for x in v), "patte": sum(x == 0.5 for x in v),
                       "sconfitte": sum(x == 0.0 for x in v), "esclusi": len(righe) - len(v)}

    def delta(a, b):
        return [ret(r, a) - ret(r, b) for r in righe if ok(r, a) and ok(r, b)]

    mb = [(ret(r, NOME_M), ret(r, NOME_B)) for r in righe if ok(r, NOME_M) and ok(r, NOME_B)]
    d = {"M-B": delta(NOME_M, NOME_B), "M-campione": delta(NOME_M, NOME_CAMPIONE),
         "B-campione": delta(NOME_B, NOME_CAMPIONE), "Q-campione": delta(NOME_Q, NOME_CAMPIONE)}
    stat = {k: _ic(v) for k, v in d.items()}
    if mappa[NOME_Q] == mappa[NOME_CAMPIONE]:       # stessa mossa: differenza 0 per costruzione, anche senza mondi
        stat["Q-campione"] = {"n": len(d["Q-campione"]), "media": 0.0, "ic95": None}
    return {"linee": linee, "deltas": d, "stat": stat, "rif": NOME_CAMPIONE,
            "flip": {"B_perde_M_vince": sum(b == 0.0 and m == 1.0 for m, b in mb),
                     "B_vince_M_perde": sum(b == 1.0 and m == 0.0 for m, b in mb)},
            "n_mondi": len(righe)}


def gioca_posizione(pos: dict, n_mondi: int, cart: Path, processi: int = 1, mondi0: int = MONDI0,
                    iterazioni: int = ITERAZIONI, valutazione: str = VALUTAZIONE, quota=None) -> dict:
    """Le tre linee sugli stessi mondi `ignote` (campione su entrambi i posti a `iterazioni` con `valutazione` dopo la
    prima mossa forzata); scrive `mondi.jsonl` e `decisione.json` in `cart`. Con `quota` = (etichette, n) il modo
    quota: prima la ricerca rifatta con la quota alla radice (con le iterazioni della partita; `D.rifai`) da cui la
    mossa `lab_Q`; poi le linee "campione" (la mossa originale forzata), M, B e "con quota" sugli stessi mondi. Se il
    prefisso non si riproduce (`prefisso_ok` falso) la posizione e' esclusa e non si gioca."""
    cart = Path(cart)
    cart.mkdir(parents=True, exist_ok=True)
    if quota is not None:
        return _gioca_posizione_quota(pos, n_mondi, cart, processi, mondi0, iterazioni, valutazione, quota)
    p = A.posizione(pos["partita"], pos["k"])
    # il prefisso e' gia' rigiocato con le impostazioni registrate; da qui il campione di oggi (P serve solo agli agenti
    # e alla valutazione della continuazione: `gioco`, `_agente_campione`, `valori`)
    p["P"] = {**p["P"], "iterazioni": iterazioni, "valutazione": D._valutazione_registrata(valutazione)}
    linee = [A.linea_campione(), A.linea_primo(NOME_M, pos["lab_M"]), A.linea_primo(NOME_B, pos["lab_B"])]
    dati = A.esegui(p, "ignote", range(mondi0, mondi0 + n_mondi), linee, cart / "mondi.jsonl", processi,
                    lambda *_: None)
    res = {k: v for k, v in pos.items() if k != "partita"} | analizza(dati)
    (cart / "decisione.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def _gioca_posizione_quota(pos: dict, n_mondi: int, cart: Path, processi: int, mondi0: int, iterazioni: int,
                           valutazione: str, quota) -> dict:
    r = D.rifai(pos["partita"], pos["k"], posizione=False, quota=(list(quota[0]), int(quota[1])))
    lab_q, orig = r["azione"], pos["campione"]
    base = {k: v for k, v in pos.items() if k != "partita"} | {
        "matchup": pos["partita"].get("matchup", "-"), "lab_Q": lab_q, "prefisso_ok": bool(r["prefisso_ok"]),
        "classifica_quota": [{k: x[k] for k in ("azione", "n", "q")} for x in r["classifica"][:6]]}
    linee, mappa = linee_quota(orig, pos["lab_M"], pos["lab_B"], lab_q)
    if not r["prefisso_ok"]:                        # escluse: nessun mondo giocato
        res = base | analizza_quota([], mappa) | {"q_uguale": None, "q_media": None}
    else:
        p = A.posizione(pos["partita"], pos["k"])
        p["P"] = {**p["P"], "iterazioni": iterazioni, "valutazione": D._valutazione_registrata(valutazione)}
        dati = A.esegui(p, "ignote", range(mondi0, mondi0 + n_mondi), linee, cart / "mondi.jsonl", processi,
                        lambda *_: None)
        an = analizza_quota(dati, mappa)
        q_uguale = ("campione" if lab_q == orig else "M" if lab_q == pos["lab_M"] else
                    "B" if lab_q == pos["lab_B"] else "altro")
        res = base | an | {"q_uguale": q_uguale, "q_media": an["stat"]["Q-campione"]["media"]}
    res["quota"] = [list(quota[0]), int(quota[1])]
    (cart / "decisione.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


# -- statistiche ------------------------------------------------------------------------------------

def riassunto(righe: list[dict], n_boot: int = N_BOOT, seme: int = 0) -> dict:
    """`righe`: una per posizione con `nome` (la partita) e `stat["M-B"]` (n, media, ic95) e `flip`. Totale = media delle
    medie M-B delle posizioni con almeno un mondo valido (ognuna pesa 1); intervallo 95% ricampionando le PARTITE
    (cluster bootstrap, la statistica e' sempre la media sulle posizioni delle partite estratte)."""
    val = [r for r in righe if r["stat"]["M-B"]["media"] is not None]
    out: dict = {"posizioni": len(righe), "valide": len(val),
                 "flip_B_perde_M_vince": sum(r["flip"]["B_perde_M_vince"] for r in righe),
                 "flip_B_vince_M_perde": sum(r["flip"]["B_vince_M_perde"] for r in righe)}
    ic = [r["stat"]["M-B"]["ic95"] for r in val]
    out["pos_ic_positivo"] = sum(x is not None and x[0] > 0 for x in ic)
    out["pos_ic_negativo"] = sum(x is not None and x[1] < 0 for x in ic)
    giochi: dict[str, list[dict]] = {}
    for r in val:
        giochi.setdefault(r["nome"], []).append(r)
    per = {}
    for nome, rr in giochi.items():
        pooled = [x for r in rr for x in r.get("delta_MB", [])]
        per[nome] = {"posizioni": len(rr), "media": float(np.mean([r["stat"]["M-B"]["media"] for r in rr])),
                     "mondi": len(pooled), "ic95": _ic(pooled)["ic95"]}
    out["per_partita"] = per
    out["partite_ic_positivo"] = sum(g["ic95"] is not None and g["ic95"][0] > 0 for g in per.values())
    out["partite_ic_negativo"] = sum(g["ic95"] is not None and g["ic95"][1] < 0 for g in per.values())
    if val:
        medie = np.array([r["stat"]["M-B"]["media"] for r in val], float)
        out["media"] = float(medie.mean())
        out["a_favore"], out["contro"], out["pari"] = int((medie > 0).sum()), int((medie < 0).sum()), \
            int((medie == 0).sum())
        nomi = list(giochi)
        somme = np.array([sum(r["stat"]["M-B"]["media"] for r in giochi[n]) for n in nomi], float)
        conta = np.array([len(giochi[n]) for n in nomi], float)
        rng = np.random.default_rng(seme)
        idx = rng.integers(0, len(nomi), (n_boot, len(nomi)))
        boot = somme[idx].sum(axis=1) / conta[idx].sum(axis=1)
        out["ic95"] = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    else:
        out |= {"media": None, "ic95": None, "a_favore": 0, "contro": 0, "pari": 0}
    return out


def riassunto_quota(righe: list[dict], n_boot: int = N_BOOT, seme: int = 0) -> dict:
    """Modo quota. `righe`: una per posizione (`nome` = la partita, `matchup`, `campione`, `lab_Q`, `q_uguale`,
    `q_media`, `prefisso_ok`, `scelta_campione`, `stat["M-B"]`, `flip`, `delta_MB`). Escluse e contate: quelle col
    prefisso non riprodotto, e (a parte) quelle dove la quota cambia mossa ma nessun mondo e' valido.
    - sottoinsiemi per la mossa originale del campione ("campione = B" schierata in base, "campione = M", "altro"):
      n e media M-B con IC 95% (come `riassunto`, ricampionando le partite);
    - Q - campione su TUTTE le posizioni valide, zeri compresi (ognuna pesa 1): IC 95% con il bootstrap a cluster,
      ricampionando le PARTITE dentro ogni matchup (stesso numero di partite), statistica = media su tutte le
      posizioni delle partite estratte;
    - quante posizioni cambiano mossa con la quota e verso cosa (M, B, altro);
    - regola di stop: `passa` = limite inferiore di Q - campione > 0, con almeno MIN_POSIZIONI posizioni valide e almeno
      MIN_CAMBIANO posizioni in cui la quota cambia mossa (con poche partite per matchup l'intervallo a cluster si
      schiaccia: fissato prima dei risultati, 27/11)."""
    valide = [r for r in righe if r.get("prefisso_ok", True)]
    ok = [r for r in valide if r.get("q_media") is not None]
    out: dict = {"posizioni": len(righe), "esclusi_prefisso": len(righe) - len(valide),
                 "senza_mondi": len(valide) - len(ok)}
    sub = {}
    for chiave, nome in (("B", "campione = B"), ("M", "campione = M"), (None, "altro")):
        sel = [r for r in valide if r.get("scelta_campione") == chiave]
        rs = riassunto(sel, n_boot, seme)
        sub[nome] = {"posizioni": len(sel), "n": rs["valide"], "media": rs["media"], "ic95": rs["ic95"]}
    out["sottoinsiemi"] = sub
    cambiano = [r for r in valide if r["lab_Q"] != r["campione"]]
    out["cambiano"] = len(cambiano)
    out["cambiano_verso"] = {k: sum(r.get("q_uguale") == k for r in cambiano) for k in ("M", "B", "altro")}
    gruppi: dict[str, dict[str, list[float]]] = {}
    for r in ok:
        x = gruppi.setdefault(r.get("matchup", "-"), {}).setdefault(r["nome"], [0.0, 0])
        x[0] += r["q_media"]
        x[1] += 1
    out["n_valide"] = len(ok)
    out["per_matchup"] = {mu: {"posizioni": int(sum(c[1] for c in g.values())),
                               "media": float(sum(c[0] for c in g.values()) / sum(c[1] for c in g.values()))}
                          for mu, g in sorted(gruppi.items())}
    if ok:
        m = float(np.mean([r["q_media"] for r in ok]))
        rng = np.random.default_rng(seme)
        num, den = np.zeros(n_boot), np.zeros(n_boot)
        for mu in sorted(gruppi):
            c = np.array(list(gruppi[mu].values()), float)
            idx = rng.integers(0, len(c), (n_boot, len(c)))
            num += c[idx, 0].sum(axis=1)
            den += c[idx, 1].sum(axis=1)
        boot = num / den
        lo, hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
        out["q_meno_campione"] = [m, lo, hi]
        out["passa"] = bool(lo > 0 and len(ok) >= MIN_POSIZIONI and len(cambiano) >= MIN_CAMBIANO)
    else:
        out["q_meno_campione"] = [None, None, None]
        out["passa"] = False
    return out


def _pp(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f} pp"


def _ic_txt(s: dict) -> str:
    if s["media"] is None:
        return "-"
    return _pp(s["media"]) + ("" if s["ic95"] is None else f" [{100 * s['ic95'][0]:+.1f}, {100 * s['ic95'][1]:+.1f}]")


def _riga_quota(r: dict) -> str:
    if not r.get("prefisso_ok", True):
        return f"{r['nome']} t{r['turno']} k{r['k']}: ESCLUSA (il prefisso non si riproduce con la ricerca rifatta)"
    w = r["linee"]
    q = r["stat"]["Q-campione"]
    return (f"{r['nome']} t{r['turno']} k{r['k']}: campione={r['campione']} | M={r['lab_M']} | B={r['lab_B']} | "
            f"Q={r['lab_Q']} ({r['q_uguale']}) | vittorie campione {w[NOME_CAMPIONE]['vittorie']}/"
            f"{w[NOME_CAMPIONE]['n']}, M {w[NOME_M]['vittorie']}/{w[NOME_M]['n']}, B {w[NOME_B]['vittorie']}/"
            f"{w[NOME_B]['n']}, Q {w[NOME_Q]['vittorie']}/{w[NOME_Q]['n']} | M-B {_ic_txt(r['stat']['M-B'])} | "
            f"Q-campione {_ic_txt(q)}")


def _testo_quota(rq: dict) -> list[str]:
    t = [f"con la quota: {rq['cambiano']} posizioni cambiano mossa (verso M {rq['cambiano_verso']['M']}, B "
         f"{rq['cambiano_verso']['B']}, altro {rq['cambiano_verso']['altro']}); escluse per il prefisso "
         f"{rq['esclusi_prefisso']}, senza mondi validi {rq['senza_mondi']}",
         "M-B per mossa originale del campione (posizioni, con mondi validi, media e IC 95% ricampionando le partite):"]
    for nome, x in rq["sottoinsiemi"].items():
        ic = _pp(x["media"]) + ("" if x["ic95"] is None else f" [{100 * x['ic95'][0]:+.1f}, {100 * x['ic95'][1]:+.1f}]")
        t.append(f"  {nome}: {x['posizioni']}, {x['n']}, {ic if x['media'] is not None else '-'}")
    m, lo, hi = rq["q_meno_campione"]
    t.append("Q - campione su tutte le posizioni (zeri compresi, IC 95% ricampionando le partite per matchup): " +
             ("-" if m is None else f"{_pp(m)} [{100 * lo:+.1f}, {100 * hi:+.1f}] su {rq['n_valide']} posizioni"))
    for mu, x in rq["per_matchup"].items():
        t.append(f"  {mu}: {x['posizioni']} posizioni, {_pp(x['media'])}")
    t.append(f"regola di stop: PASSA (limite inferiore di Q - campione > 0, almeno {MIN_POSIZIONI} posizioni valide e "
             f"{MIN_CAMBIANO} che cambiano mossa): arena" if rq["passa"] else
             f"regola di stop: NON PASSA (serve limite inferiore di Q - campione > 0, almeno {MIN_POSIZIONI} posizioni "
             f"valide e {MIN_CAMBIANO} che cambiano mossa): resta il campione")
    return t


def _testo(rs: dict, righe: list[dict], imp: dict, regs: list[dict], secondi: float, rq: dict | None = None) -> list[str]:
    t = [f"Muovo prima contro schiero in base: prior del campione {imp['ckpt']}; continuazione {imp['iterazioni']} "
         f"iterazioni, valutazione {imp['valutazione']} (entrambi i posti campione dopo la prima mossa forzata)",
         f"{imp['mondi']} mondi per posizione (da {imp['mondi0']}), {imp['n_boot']} ricampionamenti di partite"]
    if rq is not None:
        t.append(f"modo quota: etichette {imp['quota'][0]}, {imp['quota'][1]} visite iniziali per figlio alla radice; "
                 f"linee campione (mossa originale forzata), M, B, con quota")
    for r in regs:
        t.append(f"replay {r['nome']}: seme {r['seme']}, regole {r['regole']}, valutazione registrata "
                 f"{r['valutazione']}, iterazioni registrate {r['iterazioni']} (solo il prefisso)")
    t.append(f"posizioni {rs['posizioni']} ({rs['valide']} con mondi validi)")
    for r in righe:
        if rq is not None:
            t.append(_riga_quota(r))
            continue
        w = r["linee"]
        t.append(f"{r['nome']} t{r['turno']} k{r['k']}: M={r['lab_M']} | B={r['lab_B']} | campione={r['campione']} | "
                 f"vittorie M {w[NOME_M]['vittorie']}/{w[NOME_M]['n']}, B {w[NOME_B]['vittorie']}/{w[NOME_B]['n']}, "
                 f"rif {w[A.NOME_RIF]['vittorie']}/{w[A.NOME_RIF]['n']} | M-B {_ic_txt(r['stat']['M-B'])} | flip "
                 f"B perde-M vince {r['flip']['B_perde_M_vince']}, B vince-M perde {r['flip']['B_vince_M_perde']}")
    t.append("per partita (posizioni, media M-B, IC 95% sui mondi appaiati):")
    for n, g in rs["per_partita"].items():
        ic = "-" if g["ic95"] is None else f"[{100 * g['ic95'][0]:+.1f}, {100 * g['ic95'][1]:+.1f}]"
        t.append(f"  {n}: {g['posizioni']}, {_pp(g['media'])} {ic}")
    t.append(f"posizioni con IC sopra 0: {rs['pos_ic_positivo']}, sotto 0: {rs['pos_ic_negativo']}; partite con IC "
             f"sopra 0: {rs['partite_ic_positivo']}, sotto 0: {rs['partite_ic_negativo']}")
    t.append(f"flip totali: B perde e M vince {rs['flip_B_perde_M_vince']}, B vince e M perde "
             f"{rs['flip_B_vince_M_perde']}")
    if rq is not None:
        t += _testo_quota(rq)
    ic = "-" if rs["ic95"] is None else f"IC 95% da {100 * rs['ic95'][0]:+.1f} a {100 * rs['ic95'][1]:+.1f}"
    t.append(f"totale: {rs['posizioni']} posizioni, M-B {_pp(rs['media'])} ({ic}), a favore {rs['a_favore']}, contro "
             f"{rs['contro']}, pari {rs['pari']}, {secondi / 60:.1f} min")
    return t


# -- la corsa ---------------------------------------------------------------------------------------

def _controlla_impostazioni(out_dir: Path, partite: list[dict], ckpt, casuali: bool, n_mondi: int, mondi0: int,
                            iterazioni: int, valutazione: str, quota=None, base_seme=None) -> None:
    """Scrive `impostazioni.json` alla prima corsa; un rilancio nella stessa cartella riprende solo con le stesse
    impostazioni (checkpoint sha256, mondi, primo mondo, replay, continuazione)."""
    from riftbound.provenienza import checkpoint_sha256
    pc = Path(str(ckpt or D.CKPT_DEFAULT))
    pc = pc if pc.is_absolute() else D.ROOT / pc
    imp = {"ckpt_sha256": None if casuali else checkpoint_sha256(str(pc)), "casuali": bool(casuali),
           "mondi": n_mondi, "mondi0": mondi0, "iterazioni": iterazioni, "valutazione": valutazione,
           "partite": [_id_partita(p) for p in partite]}
    if quota is not None:
        imp["quota"] = [list(quota[0]), int(quota[1])]
    if base_seme is not None:
        imp["base_seme"] = int(base_seme)
    f = out_dir / "impostazioni.json"
    if f.exists():
        if json.loads(f.read_text(encoding="utf-8")) != imp:
            raise ValueError(f"Impostazioni diverse da {f}: usare una nuova cartella.")
    else:
        f.write_text(json.dumps(imp, indent=1), encoding="utf-8")


def _ripristina(partita: dict) -> dict:
    """Dopo il giro in json la valutazione e' una lista: la ricerca la vuole come tupla."""
    if isinstance(partita.get("valutazione"), list):
        partita = {**partita, "valutazione": tuple(partita["valutazione"])}
    return partita


def _leggi_cache(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if path.exists():
        for riga in path.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                d = json.loads(riga)
                for r in d["posizioni"]:
                    r["partita"] = _ripristina(r["partita"])
                out[d["id"]] = d["posizioni"]
    return out


def _lavoro_selezione(partita: dict) -> tuple[str, list[dict]]:
    return _id_partita(partita), selezionate(partita)


def muovi(partite: list[dict], n_mondi: int, out_dir, ckpt, casuali: bool = False, processi: int = 1,
          iterazioni: int = ITERAZIONI, valutazione: str = VALUTAZIONE, mondi0: int = MONDI0, n_boot: int = N_BOOT,
          print_=print, quota=None, base_seme=None) -> list[str]:
    """Tutto: selezione (in cache in `selezione.jsonl`), le tre linee su ogni posizione (`NNN_partita_kK/`), riepilogo.
    Col modo `quota` = (etichette, n) le quattro linee, il riassunto del modo quota e `esito.json` ({"passa",
    "q_meno_campione": [media, lo, hi], ...}); `base_seme` (delle partite autonome) va in `impostazioni.json`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    _controlla_impostazioni(out_dir, partite, ckpt, casuali, n_mondi, mondi0, iterazioni, valutazione, quota, base_seme)
    cache_path = out_dir / "selezione.jsonl"
    cache = _leggi_cache(cache_path)
    da_fare = [p for p in partite if _id_partita(p) not in cache]
    print_(f"== selezione: {len(partite)} partite ({len(partite) - len(da_fare)} gia' fatte)")

    def salva(i, ps):
        cache[i] = ps
        with cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": i, "posizioni": ps}, ensure_ascii=False) + "\n")

    if processi > 1 and len(da_fare) > 1:
        with ProcessPoolExecutor(min(processi, len(da_fare)), mp_context=multiprocessing.get_context("spawn")) as pool:
            for j, (i, ps) in enumerate(pool.map(_lavoro_selezione, da_fare), 1):
                salva(i, ps)
                print_(f"== partita {j}/{len(da_fare)}: {len(ps)} posizioni, {time.time() - t0:.0f} s")
    else:
        for j, p in enumerate(da_fare, 1):
            i, ps = _lavoro_selezione(p)
            salva(i, ps)
            print_(f"== partita {j}/{len(da_fare)}: {len(ps)} posizioni, {time.time() - t0:.0f} s")
    tutte = [{**ps, "partita": _ripristina(ps["partita"])} for p in partite for ps in cache[_id_partita(p)]]
    righe = []
    for n, pos in enumerate(tutte):
        cart = out_dir / f"{n:03d}_{pos['nome']}_k{pos['k']}"
        f = cart / "decisione.json"
        res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        if res is None or "deltas" not in res or (quota is not None and "quota" not in res):
            print_(f"== posizione {n + 1}/{len(tutte)}: {pos['nome']} turno {pos['turno']} k={pos['k']}, "
                   f"{n_mondi} mondi")
            res = gioca_posizione(pos, n_mondi, cart, processi, mondi0, iterazioni, valutazione, quota)
        righe.append(res | {"delta_MB": res["deltas"]["M-B"]})
    rs = riassunto(righe, n_boot)
    imp = {"ckpt": str(ckpt) if ckpt and not casuali else "(pesi casuali)", "iterazioni": iterazioni,
           "valutazione": valutazione, "mondi": n_mondi, "mondi0": mondi0, "n_boot": n_boot}
    rq = None
    if quota is not None:
        imp["quota"] = [list(quota[0]), int(quota[1])]
        rq = riassunto_quota(righe, n_boot)
    regs = [registrate(p) for p in partite]
    testo = _testo(rs, righe, imp, regs, time.time() - t0, rq)
    (out_dir / "riepilogo.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(
        json.dumps({"impostazioni": imp, "replay": regs, "riassunto": rs,
                    "posizioni": [{k: v for k, v in r.items() if k not in ("deltas", "delta_MB")} for r in righe]}
                   | ({} if rq is None else {"quota": rq}), ensure_ascii=False, indent=1), encoding="utf-8")
    if rq is not None:
        (out_dir / "esito.json").write_text(json.dumps(
            {"passa": rq["passa"], "q_meno_campione": rq["q_meno_campione"], "cambiano": rq["cambiano"],
             "posizioni": rq["posizioni"], "esclusi_prefisso": rq["esclusi_prefisso"],
             "sottoinsiemi": rq["sottoinsiemi"]}, ensure_ascii=False), encoding="utf-8")
    return testo


# -- l'arena (solo se la regola di stop passa) -------------------------------------------------------

def arena_quota(matchup, coppie: int, out_dir, ckpt, processi: int = 1, regole: str = S.REGOLE,
                iterazioni: int = ITERAZIONI, n_boot: int = 4000, base_seme: int = BASE_SEME_ARENA,
                print_=print) -> list[str]:
    """Candidato (campione con la quota alla radice di ogni ricerca di turno: `QUOTA_*`) contro il campione, coppie a
    posti scambiati con lo stesso seme (`scelta.arena_campione`: ripresa e manifest). `promuovibile`: limite inferiore
    dell'IC 95% del totale > 0,5. Scrive `arena.json` e `arena.txt`."""
    from riftbound.rs import generazione, scelta
    out_dir = Path(out_dir)
    ckpt = str(ckpt)
    quota = [list(QUOTA_ETICHETTE), QUOTA_VISITE]
    opz = generazione._opz(0.0, iterazioni, False) | {"quota_cand": quota}
    a = scelta.arena_campione(matchup, coppie, out_dir, ckpt, opz, base_seme,
                              {"iterazioni": iterazioni, "quota": quota}, "arena", processi, regole, n_boot, print_)
    tot, lo, hi = a["totale"]
    per = a["per"]
    prom = bool(lo > 0.5)
    res = {"totale": [tot, lo, hi], "matchup": {mu: list(x) for mu, x in per.items()}, "coppie_per_matchup": coppie,
           "promuovibile": prom, "configurazione": a["config"], "minuti": a["minuti"]}
    testo = [f"Arena: candidato (campione con quota {QUOTA_VISITE} visite a {QUOTA_ETICHETTE} alla radice) contro il "
             f"campione {ckpt}, {coppie} coppie per matchup ({', '.join(matchup)}), {iterazioni} iterazioni, regole "
             f"{regole}, semi da {base_seme}",
             f"totale {tot:.3f} (IC 95% {lo:.3f}-{hi:.3f}), pesi uguali fra i matchup",
             "   " + "; ".join(f"{mu} {x[0]:.3f} ({x[1]:.2f}-{x[2]:.2f})" for mu, x in per.items()),
             "criterio: limite inferiore > 50%: candidato promuovibile: " + ("SI" if prom else "NO"),
             f"durata dell'arena: {res['minuti']} min"]
    (out_dir / "arena.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "arena.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    return testo
