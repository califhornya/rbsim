"""Seguiti (Astra, 26/11): il valore della rete nuova aiuta a scegliere una linea migliore su posizioni nuove?

Combinazione (d): prior del campione (`ckpt_040000`) + valore della rete nuova (`rete.pt`) al 20% nelle foglie (80%
valutazione a mano `rimonta`), 138 iterazioni. Su partite autonome del campione (entrambi i posti = campione dell'arena)
si rifa' ogni decisione di turno con (d); dove (d) sceglie una mossa diversa dal campione, si giocano entrambe fino alla
fine sugli stessi mondi `ignote` (continuazione: il campione su entrambi i posti) e si confrontano a coppie.

  `partite(...)`          le partite autonome (semi BASE_SEME + 1000 i + j, posto del campione alternato).
  `decisioni(...)`        le decisioni di turno del campione di una partita, rifatte con (d).
  `gioca_decisione(...)`  la fase 2 su una decisione: le due linee sui mondi, delta appaiati, `decisione.json`.
  `riassunto(...)`        media per decisione, totale (ogni decisione pesa 1), intervallo 95% per ricampionamento.
  `seguiti(...)`          tutto; scrive `riepilogo.json` e `riepilogo.txt` (ultima riga `totale:`).
"""
from __future__ import annotations

import json
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from riftbound.rs import arena_rs, attacco as A, decisione_rs as D
from riftbound.rs.responso import sparse

REGOLE = "6427b90+D72-D83"
VALUTAZIONE = "rimonta"
ITERAZIONI = 138
PESO = 0.2
BASE_SEME = 50_000_000      # la raccolta usa 30M, l'arena di sviluppo 40M
MONDI0 = 7000               # primo indice dei mondi
N_BOOT = 40_000


# -- le partite e le decisioni ----------------------------------------------------------------------

def partite(matchup, n_partite: int, ckpt, casuali: bool, iterazioni: int = ITERAZIONI,
            regole: str = REGOLE) -> list[dict]:
    """Per ogni matchup `n_partite` partite autonome del campione (valutazione dell'arena su entrambi i posti)."""
    out = []
    for mu in matchup:
        i = arena_rs.COPERTI.index(mu)
        for j in range(n_partite):
            out.append(D.autonoma(mu, BASE_SEME + 1_000 * i + j, ckpt, casuali, iterazioni,
                                  "A" if j % 2 == 0 else "B", regole=regole,
                                  valutazione=D._valutazione_registrata(VALUTAZIONE), entrambi=True))
    return out


def _riassunto_rifai(r: dict) -> dict:
    return {"azione": r["azione"], "prefisso_ok": r["prefisso_ok"],
            "classifica": [{k: x[k] for k in ("i", "azione", "n", "q", "P", "rango")} for x in r["classifica"]]}


def decisioni(partita: dict, per_partita: int, ckpt_valore, peso: float = PESO) -> list[dict]:
    """Le decisioni `turn_action` del campione con almeno 2 voci nel menu, al piu' `per_partita` sparse sui turni,
    ciascuna rifatta con (d). Una riga: partita, nome, k, turno, menu, campione, d, prefisso_ok, classifica."""
    P = D._prepara(partita)
    cand = [o for o in D.originale(partita) if o["seat"] == P["camp"] and o["point"] == "turn_action"
            and len(o["menu"]) >= 2]
    out = []
    for o in sparse(cand, per_partita):
        r = D.rifai(partita, o["k"], posizione=False, valore_rete=(peso, str(ckpt_valore)))
        out.append({"partita": partita, "nome": A.nome_partita(partita), "k": o["k"], "turno": o["turn"],
                    "menu": o["menu"], "campione": o["action"], "d": r["azione"], "prefisso_ok": r["prefisso_ok"],
                    "classifica": _riassunto_rifai(r)["classifica"]})
    return out


def _lavoro_partita(args) -> tuple[str, list[dict]]:
    partita = args[0]
    return A.nome_partita(partita), decisioni(*args)


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
                for r in d["decisioni"]:
                    r["partita"] = _ripristina(r["partita"])
                out[d["nome"]] = d["decisioni"]
    return out


# -- fase 2 -----------------------------------------------------------------------------------------

def _info(dec: dict) -> dict:
    return {k: dec[k] for k in ("nome", "k", "turno", "menu", "campione", "d", "prefisso_ok", "classifica")} | \
        {"matchup": dec["partita"]["matchup"]}


def gioca_decisione(dec: dict, n_mondi: int, cart: Path, processi: int = 1, mondi0: int = MONDI0) -> dict:
    """Gioca la mossa del campione e quella di (d) fino alla fine sugli stessi mondi `ignote`; delta appaiati
    (ritorno di d - ritorno del campione, 1 vittoria, 0,5 patta) nei mondi dove entrambe le righe rispettano la prima
    mossa. Scrive `mondi.jsonl` e `decisione.json` in `cart`."""
    cart = Path(cart)
    cart.mkdir(parents=True, exist_ok=True)
    pos = A.posizione(dec["partita"], dec["k"])
    linee = [A.linea_primo("campione", dec["campione"]), A.linea_primo("d", dec["d"])]
    dati = A.esegui(pos, "ignote", range(mondi0, mondi0 + n_mondi), linee, cart / "mondi.jsonl", processi,
                    lambda *_: None)
    delta, escluse = [], 0
    for rows in dati:
        r = {x["line"]: x for x in rows}
        if r["campione"]["primo_ok"] and r["d"]["primo_ok"]:
            delta.append(r["d"]["returns"] - r["campione"]["returns"])
        else:
            escluse += 1
    res = _info(dec) | {"deltas": delta, "media": float(np.mean(delta)) if delta else None, "n_mondi": len(delta),
                        "mondi_esclusi": escluse}
    (cart / "decisione.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def _nome_cartella(n: int, dec: dict) -> str:
    return f"{n:03d}_{dec['nome']}_k{dec['k']}"


# -- statistiche ------------------------------------------------------------------------------------

def riassunto(dec_rows: list[dict], n_boot: int = N_BOOT, seme: int = 0) -> dict:
    """`dec_rows`: una riga per decisione esaminata con matchup, prefisso_ok, disaccordo, media (None se nessun mondo
    valido), n_mondi. Il totale e' la media delle medie delle decisioni con almeno un mondo valido (ognuna pesa 1);
    intervallo 95% ricampionando le decisioni."""
    medie = np.array([r["media"] for r in dec_rows if r.get("disaccordo") and r.get("media") is not None], float)
    out: dict = {"esaminate": len(dec_rows), "escluse": sum(not r["prefisso_ok"] for r in dec_rows),
                 "disaccordi": sum(bool(r.get("disaccordo")) for r in dec_rows), "n_decisioni": int(len(medie)),
                 "mondi_validi": sum(r.get("n_mondi", 0) for r in dec_rows),
                 "mondi_esclusi": sum(r.get("mondi_esclusi", 0) for r in dec_rows)}
    out["tasso_disaccordo"] = out["disaccordi"] / max(1, out["esaminate"] - out["escluse"])
    if len(medie):
        rng = np.random.default_rng(seme)
        boot = medie[rng.integers(0, len(medie), (n_boot, len(medie)))].mean(axis=1)
        out |= {"media": float(medie.mean()), "ic95": [float(np.percentile(boot, 2.5)),
                                                       float(np.percentile(boot, 97.5))],
                "a_favore": int((medie > 0).sum()), "contro": int((medie < 0).sum()), "pari": int((medie == 0).sum())}
    else:
        out |= {"media": None, "ic95": None, "a_favore": 0, "contro": 0, "pari": 0}
    pm = {}
    for mu in sorted({r["matchup"] for r in dec_rows}):
        rr = [r for r in dec_rows if r["matchup"] == mu]
        ex = sum(not r["prefisso_ok"] for r in rr)
        dis = [r for r in rr if r.get("disaccordo")]
        mm = [r["media"] for r in dis if r.get("media") is not None]
        pm[mu] = {"esaminate": len(rr), "escluse": ex, "disaccordi": len(dis),
                  "tasso_disaccordo": len(dis) / max(1, len(rr) - ex), "media": float(np.mean(mm)) if mm else None}
    out["per_matchup"] = pm
    return out


def _pp(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f} pp"


def _testo(rs: dict, imp: dict, secondi: float) -> list[str]:
    righe = [f"Seguiti: prior del campione {imp['ckpt']}, valore della rete nuova {imp['ckpt_valore']} al "
             f"{100 * imp['peso']:.0f}% (resto: valutazione {VALUTAZIONE}), {imp['iterazioni']} iterazioni, regole "
             f"{imp['regole']}",
             f"partite {imp['partite']}, al piu' {imp['per_partita']} decisioni per partita, {imp['mondi']} mondi per "
             f"decisione, {imp['n_boot']} ricampionamenti",
             f"decisioni esaminate {rs['esaminate']} (prefisso non riprodotto: {rs['escluse']}); con mossa diversa dal "
             f"campione {rs['disaccordi']} ({100 * rs['tasso_disaccordo']:.1f}% delle valide)"]
    if rs["media"] is None:
        righe.append("nessuna decisione con mondi validi: niente differenza da stimare")
    else:
        a, b = rs["ic95"]
        righe.append(f"differenza media (d - campione) sulle decisioni con disaccordo: {_pp(rs['media'])} "
                     f"(IC 95% da {100 * a:+.1f} a {100 * b:+.1f}); a favore {rs['a_favore']}, contro {rs['contro']}, "
                     f"pari {rs['pari']}")
    righe.append(f"mondi giocati validi {rs['mondi_validi']}; esclusi {rs['mondi_esclusi']} (la prima mossa forzata non e' "
                 f"quella chiesta)")
    righe.append("per matchup (esaminate, escluse, disaccordi, tasso, differenza media nei disaccordi):")
    for mu, m in rs["per_matchup"].items():
        righe.append(f"  {mu}: {m['esaminate']}, {m['escluse']}, {m['disaccordi']}, "
                     f"{100 * m['tasso_disaccordo']:.1f}%, {_pp(m['media'])}")
    righe.append(f"totale: {rs['esaminate']} decisioni, {rs['disaccordi']} disaccordi, {_pp(rs['media'])}, "
                 f"{secondi / 60:.1f} min")
    return righe


# -- la corsa ---------------------------------------------------------------------------------------

def _controlla_impostazioni(out_dir: Path, ckpt, ckpt_valore, peso, casuali, regole, iterazioni) -> None:
    """Scrive `impostazioni.json` alla prima corsa; un rilancio nella stessa cartella riprende solo con le stesse
    impostazioni e gli stessi checkpoint (sha256): la cache delle decisioni e i mondi non si mescolano."""
    from riftbound.provenienza import checkpoint_sha256
    pc = Path(str(ckpt or D.CKPT_DEFAULT))
    pc = pc if pc.is_absolute() else D.ROOT / pc
    imp = {"ckpt_sha256": None if casuali else checkpoint_sha256(str(pc)),
           "valore_sha256": checkpoint_sha256(str(ckpt_valore)), "peso": peso, "casuali": bool(casuali),
           "regole": regole, "iterazioni": iterazioni, "valutazione": VALUTAZIONE, "base_seme": BASE_SEME,
           "mondi0": MONDI0}
    f = out_dir / "impostazioni.json"
    if f.exists():
        if json.loads(f.read_text(encoding="utf-8")) != imp:
            raise ValueError(f"Impostazioni diverse da {f}: usare una nuova cartella.")
    else:
        f.write_text(json.dumps(imp, indent=1), encoding="utf-8")


def seguiti(matchup, n_partite: int, per_partita: int, n_mondi: int, out_dir, ckpt, ckpt_valore, peso: float = PESO,
            casuali: bool = False, processi: int = 1, regole: str = REGOLE, iterazioni: int = ITERAZIONI,
            n_boot: int = N_BOOT, print_=print) -> list[str]:
    """Tutto: decisioni rifatte con (d) (in cache in `decisioni.jsonl`), mondi dove (d) cambia mossa, riepilogo."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    _controlla_impostazioni(out_dir, ckpt, ckpt_valore, peso, casuali, regole, iterazioni)
    parti = partite(matchup, n_partite, ckpt, casuali, iterazioni, regole)
    cache_path = out_dir / "decisioni.jsonl"
    cache = _leggi_cache(cache_path)
    da_fare = [p for p in parti if A.nome_partita(p) not in cache]
    print_(f"== decisioni: {len(parti)} partite ({len(parti) - len(da_fare)} gia' fatte), al piu' {per_partita} "
           f"ciascuna, (d) al {100 * peso:.0f}%")
    lavori = [(p, per_partita, ckpt_valore, peso) for p in da_fare]

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
        riga = {"matchup": dec["partita"]["matchup"], "nome": dec["nome"], "k": dec["k"],
                "prefisso_ok": dec["prefisso_ok"], "disaccordo": dec["prefisso_ok"] and dec["d"] != dec["campione"],
                "media": None, "n_mondi": 0}
        if riga["disaccordo"]:
            cart = out_dir / _nome_cartella(n, dec)
            f = cart / "decisione.json"
            res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
            if res is None or "deltas" not in res:
                print_(f"== decisione {n + 1}/{len(decs)}: {dec['nome']} k={dec['k']} turno {dec['turno']}, "
                       f"{n_mondi} mondi")
                res = gioca_decisione(dec, n_mondi, cart, processi)
            riga |= {"media": res["media"], "n_mondi": res["n_mondi"], "mondi_esclusi": res["mondi_esclusi"]}
        righe_dec.append(riga)
    rs = riassunto(righe_dec, n_boot)
    imp = {"ckpt": str(ckpt) if ckpt else "(pesi casuali)", "ckpt_valore": str(ckpt_valore), "peso": peso,
           "iterazioni": iterazioni, "regole": regole, "partite": len(parti), "per_partita": per_partita,
           "mondi": n_mondi, "n_boot": n_boot}
    righe = _testo(rs, imp, time.time() - t0)
    (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(json.dumps({"impostazioni": imp, "riassunto": rs, "decisioni": righe_dec},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    return righe
