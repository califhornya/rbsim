"""Muovo prima contro schiero in base (Astra, 27/11): su una posizione dove un'unita' puo' andare su un campo libero e,
da li', un'altra unita' puo' essere schierata, conviene muovere prima o schierare in base adesso?

Caso di partenza: partita della pagina 20261126_155859, turno 5, il campione gioca "Play Fiora Victorious" (in base) e poi
"Move Sett Kingpin base→BF1"; la linea di Matteo, "Move Sett Kingpin base→BF1" e poi "Play Fiora Victorious to BF1",
vinceva +19 pp sugli stessi 100 mondi (la ricerca: 136 visite a Fiora in base, 1 a muovere Sett).

  `replay_default()`      i replay salvati della pagina, esclusi quelli con il seme della partita della scoperta.
  `scegli(o, vista)`      la regola di selezione su una riga di `D.originale` (deterministica, senza esiti).
  `selezionate(partita)`  le posizioni di una partita: al piu' la prima che qualifica per ogni turno del campione.
  `gioca_posizione(...)`  le tre linee (riferimento, "muovo prima", "schiero in base") sugli stessi mondi `ignote`,
                          `decisione.json`.
  `riassunto(...)`        media M-B per posizione (ognuna pesa 1), intervallo 95% ricampionando le PARTITE.
  `muovi(...)`            tutto; scrive `riepilogo.json` e `riepilogo.txt` (ultima riga `totale:`).

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

from riftbound.rs import attacco as A, decisione_rs as D

ITERAZIONI = 138
VALUTAZIONE = "rimonta"
MONDI0 = 30_000
N_MONDI = 100
N_BOOT = 40_000
NOME_M = "muovo prima"
NOME_B = "schiero in base"
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


def gioca_posizione(pos: dict, n_mondi: int, cart: Path, processi: int = 1, mondi0: int = MONDI0,
                    iterazioni: int = ITERAZIONI, valutazione: str = VALUTAZIONE) -> dict:
    """Le tre linee sugli stessi mondi `ignote` (campione su entrambi i posti a `iterazioni` con `valutazione` dopo la
    prima mossa forzata); scrive `mondi.jsonl` e `decisione.json` in `cart`."""
    cart = Path(cart)
    cart.mkdir(parents=True, exist_ok=True)
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


def _pp(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f} pp"


def _ic_txt(s: dict) -> str:
    if s["media"] is None:
        return "-"
    return _pp(s["media"]) + ("" if s["ic95"] is None else f" [{100 * s['ic95'][0]:+.1f}, {100 * s['ic95'][1]:+.1f}]")


def _testo(rs: dict, righe: list[dict], imp: dict, regs: list[dict], secondi: float) -> list[str]:
    t = [f"Muovo prima contro schiero in base: prior del campione {imp['ckpt']}; continuazione {imp['iterazioni']} "
         f"iterazioni, valutazione {imp['valutazione']} (entrambi i posti campione dopo la prima mossa forzata)",
         f"{imp['mondi']} mondi per posizione (da {imp['mondi0']}), {imp['n_boot']} ricampionamenti di partite"]
    for r in regs:
        t.append(f"replay {r['nome']}: seme {r['seme']}, regole {r['regole']}, valutazione registrata "
                 f"{r['valutazione']}, iterazioni registrate {r['iterazioni']} (solo il prefisso)")
    t.append(f"posizioni {rs['posizioni']} ({rs['valide']} con mondi validi)")
    for r in righe:
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
    ic = "-" if rs["ic95"] is None else f"IC 95% da {100 * rs['ic95'][0]:+.1f} a {100 * rs['ic95'][1]:+.1f}"
    t.append(f"totale: {rs['posizioni']} posizioni, M-B {_pp(rs['media'])} ({ic}), a favore {rs['a_favore']}, contro "
             f"{rs['contro']}, pari {rs['pari']}, {secondi / 60:.1f} min")
    return t


# -- la corsa ---------------------------------------------------------------------------------------

def _controlla_impostazioni(out_dir: Path, partite: list[dict], ckpt, casuali: bool, n_mondi: int, mondi0: int,
                            iterazioni: int, valutazione: str) -> None:
    """Scrive `impostazioni.json` alla prima corsa; un rilancio nella stessa cartella riprende solo con le stesse
    impostazioni (checkpoint sha256, mondi, primo mondo, replay, continuazione)."""
    from riftbound.provenienza import checkpoint_sha256
    pc = Path(str(ckpt or D.CKPT_DEFAULT))
    pc = pc if pc.is_absolute() else D.ROOT / pc
    imp = {"ckpt_sha256": None if casuali else checkpoint_sha256(str(pc)), "casuali": bool(casuali),
           "mondi": n_mondi, "mondi0": mondi0, "iterazioni": iterazioni, "valutazione": valutazione,
           "partite": [_id_partita(p) for p in partite]}
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
          print_=print) -> list[str]:
    """Tutto: selezione (in cache in `selezione.jsonl`), le tre linee su ogni posizione (`NNN_partita_kK/`), riepilogo."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    _controlla_impostazioni(out_dir, partite, ckpt, casuali, n_mondi, mondi0, iterazioni, valutazione)
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
        if res is None or "deltas" not in res:
            print_(f"== posizione {n + 1}/{len(tutte)}: {pos['nome']} turno {pos['turno']} k={pos['k']}, "
                   f"{n_mondi} mondi")
            res = gioca_posizione(pos, n_mondi, cart, processi, mondi0, iterazioni, valutazione)
        righe.append(res | {"delta_MB": res["deltas"]["M-B"]})
    rs = riassunto(righe, n_boot)
    imp = {"ckpt": str(ckpt) if ckpt and not casuali else "(pesi casuali)", "iterazioni": iterazioni,
           "valutazione": valutazione, "mondi": n_mondi, "mondi0": mondi0, "n_boot": n_boot}
    regs = [registrate(p) for p in partite]
    testo = _testo(rs, righe, imp, regs, time.time() - t0)
    (out_dir / "riepilogo.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(
        json.dumps({"impostazioni": imp, "replay": regs, "riassunto": rs,
                    "posizioni": [{k: v for k, v in r.items() if k not in ("deltas", "delta_MB")} for r in righe]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return testo
