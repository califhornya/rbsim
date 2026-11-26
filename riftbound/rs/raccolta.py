"""Raccolta pilota per riallenare la rete con la ricerca (Astra, 26/11): partite del campione contro se stesso su
Rust, con esplorazione, e un registro per ogni decisione cercata (politica = visite, valore = esito).

Una partita (`gioca`): due posti campione (`arena_rs.make_probs`, 138 iterazioni, win_probe, valutazione `rimonta` con le
costanti della pagina), esplorazione e registro accesi; la partita va avanti un turno alla volta (`setup` + `play_turn`,
le stesse chiamate di `start()`) e a ogni fine turno `osserva` registra lo stato per entrambi i posti.

File di una partita: pickle (protocollo 5) compresso gzip, un dict:
  seme, matchup, posti {"A": lettera mazzo, "B": ...}, comincia ("a"|"b"), vincitore ("A"|"B"|"DRAW"), turni, insieme,
  esito {"A": +1|0|-1, "B": ...}, record [dict di `search_registro` + "esito"], stati [{"seat","turn","x","q","ctx","esito"}],
  indice (la riga di indice.jsonl). `carica(percorso)` lo rilegge.

Piano: matchup i, partita j -> seme 30_000_000 + i*10_000 + j; j pari: il primo mazzo in A; chi comincia alterna ogni
due partite (a, a, b, b: bilanciato per posto e per mazzo); `insieme`: j % 10 == 8 sviluppo, == 9 verifica, il resto
allenamento. Campi casuali dal seme (build senza bf).
"""
from __future__ import annotations

import gzip
import json
import multiprocessing
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SEME = 30_000_000
MAX_TURNS = 40
ITERAZIONI = 138
ESPLORAZIONE = (0.3, 0.25, 4)       # alfa, eps, mosse (Astra)
REGOLE_DEFAULT = "6427b90+D72-D82"
CKPT_DEFAULT = "runs/sett/ekris_s12/ckpt_040000.pt"


def insieme(j: int) -> str:
    return {8: "sviluppo", 9: "verifica"}.get(j % 10, "allenamento")


def piano(matchup, per_matchup: int):
    """Le partite (matchup, i, j, seme, comincia, scambio) in ordine di giro: j esterno, matchup interno, cosi' le
    prime partite finite sono di tutti i matchup."""
    from riftbound.rs.arena_rs import COPERTI
    out = []
    for j in range(per_matchup):
        for mu in matchup:
            i = COPERTI.index(mu)
            out.append((mu, i, j, BASE_SEME + i * 10_000 + j, "a" if (j // 2) % 2 == 0 else "b", j % 2 == 1))
    return out


def _probs(ckpt):
    from riftbound.rs import arena_rs, decisione_rs
    if ckpt is None:
        return decisione_rs.rete(None, True)
    return arena_rs._probs_for(str(ckpt))


def gioca(task: dict, registro: bool = True, osserva: bool = True, esplora: bool = True) -> dict:
    """Una partita. task: mu, seme, comincia, scambio, iterazioni, ckpt (None: pesi casuali), regole, esplorazione
    (alfa, eps, mosse). -> {"vincitore","turni","record","stati","secondi"} (record/stati vuoti se spenti)."""
    from riftbound.ai.coach_rs import VALUTAZIONE_ALPHA, VALUTAZIONE_K
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import rust_bridge as rb
    mu, seed = task["mu"], task["seme"]
    deck_a, deck_b = (mu[1], mu[0]) if task["scambio"] else (mu[0], mu[1])
    t0 = time.perf_counter()
    g = rb.build(seed, Path(DECK_OF[deck_a]), Path(DECK_OF[deck_b]), task["comincia"], MAX_TURNS, task.get("regole"))
    probs = _probs(task.get("ckpt"))
    for seat in ("A", "B"):
        g.set_search_agent(seat, int(task["iterazioni"]), seed * 2 + (seat == "B"), None, probs, False)
        g.set_search_win_probe(seat, True)
        g.set_search_valutazione(seat, "rimonta", VALUTAZIONE_K, VALUTAZIONE_ALPHA)
        if esplora:
            g.set_search_esplorazione(seat, *task.get("esplorazione", ESPLORAZIONE))
        g.set_search_registro(seat, registro)
    g.set_side_chooser()
    g.setup()
    stati, res = [], None
    while res is None:
        turno = g.turn
        res = g.play_turn()
        if res is None and osserva:
            for seat in ("A", "B"):
                x, q, ctx = g.osserva(seat)
                stati.append({"seat": seat, "turn": turno, "x": x, "q": q, "ctx": ctx})
    vincitore, turni = res
    esito = {s: (0 if vincitore == "DRAW" else 1 if vincitore == s else -1) for s in ("A", "B")}
    record = []
    if registro:
        for seat in ("A", "B"):
            for r in g.search_registro(seat):
                r["esito"] = esito[seat]
                record.append(r)
    for st in stati:
        st["esito"] = esito[st["seat"]]
    return {"vincitore": vincitore, "turni": turni, "record": record, "stati": stati, "esito": esito,
            "posti": {"A": deck_a, "B": deck_b}, "secondi": time.perf_counter() - t0}


def percorso(out: Path, mu: str, seme: int) -> Path:
    return out / "partite" / mu / f"{seme}.pkl.gz"


def carica(path) -> dict:
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def _lavora(task: dict) -> dict:
    """Un processo: gioca, scrive il file (atomico) e la riga d'indice; restituisce la riga."""
    out = Path(task["out"])
    r = gioca(task)
    p = percorso(out, task["mu"], task["seme"])
    p.parent.mkdir(parents=True, exist_ok=True)
    cerc = sum(1 for x in r["record"] if x["kind"] == "cercata")
    riga = {"seme": task["seme"], "matchup": task["mu"], "posti": r["posti"], "comincia": task["comincia"],
            "vincitore": r["vincitore"], "turni": r["turni"], "insieme": task["insieme"], "decisioni_cercate": cerc,
            "decisioni_leggere": len(r["record"]) - cerc, "stati": len(r["stati"]),
            "secondi": round(r["secondi"], 3), "file": str(p.relative_to(out))}
    dati = {"seme": task["seme"], "matchup": task["mu"], "posti": r["posti"], "comincia": task["comincia"],
            "vincitore": r["vincitore"], "turni": r["turni"], "insieme": task["insieme"], "esito": r["esito"],
            "record": r["record"], "stati": r["stati"], "indice": riga}
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wb", compresslevel=4) as f:
        pickle.dump(dati, f, protocol=5)
    riga["byte"] = tmp.stat().st_size
    os.replace(tmp, p)
    with open(out / "indice.jsonl", "a") as f:        # una riga sola: l'append e' atomico per righe corte
        f.write(json.dumps(riga) + "\n")
    return riga


def indice(out: Path) -> list:
    p = out / "indice.jsonl"
    if not p.is_file():
        return []
    righe = {}
    for r in (json.loads(x) for x in p.read_text().splitlines() if x.strip()):
        if (out / r["file"]).is_file():
            righe[r["seme"]] = r
    return list(righe.values())


def misura(righe: list, secondi_muro: float, processi: int, partite_run: int) -> str:
    """Il testo della misura: partite/ora, secondi e decisioni per partita, byte, stima per 100.000 partite."""
    n = len(righe)
    if n == 0:
        return "nessuna partita"
    sec = sum(r["secondi"] for r in righe) / n
    dec = sum(r["decisioni_cercate"] for r in righe) / n
    byte = sum(r["byte"] for r in righe) / n
    ora = partite_run / secondi_muro * 3600 if secondi_muro > 0 else 0.0
    ore100k = 100_000 * sec / max(processi, 1) / 3600
    return "\n".join([
        f"partite misurate: {n} ({partite_run} in questa esecuzione), {processi} processi",
        f"partite/ora (questa esecuzione, tutti i processi): {ora:.0f}",
        f"secondi medi per partita (un processo): {sec:.2f}",
        f"decisioni cercate per partita: {dec:.1f}; turni medi: {sum(r['turni'] for r in righe) / n:.1f}",
        f"byte per partita: {byte:.0f} ({byte / 1e6:.2f} MB)",
        f"stima per 100.000 partite: {ore100k:.1f} ore con {processi} processi, {100_000 * byte / 1e9:.1f} GB",
    ])


def provenienza(args: dict, out: Path, ckpt) -> dict:
    import hashlib
    from riftbound import provenienza as P
    sha = None
    if ckpt is not None:
        h = hashlib.sha256()
        with open(ckpt, "rb") as f:
            for blocco in iter(lambda: f.read(1 << 20), b""):
                h.update(blocco)
        sha = h.hexdigest()
    from riftbound.ai.coach_rs import VALUTAZIONE_ALPHA, VALUTAZIONE_K
    return {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "regole": args["regole"],
            "checkpoint": None if ckpt is None else {"file": str(ckpt), "sha256": sha}, "pesi_casuali": ckpt is None,
            "iterazioni": args["iterazioni"], "valutazione": {"nome": "rimonta", "k": VALUTAZIONE_K,
                                                              "alpha": VALUTAZIONE_ALPHA},
            "win_probe": True, "esplorazione": {"alfa": args["esplorazione"][0], "eps": args["esplorazione"][1],
                                                "mosse": args["esplorazione"][2]},
            "matchup": args["matchup"], "partite_per_matchup": args["per_matchup"], "base_seme": BASE_SEME,
            "insiemi": "j % 10 == 8 sviluppo, == 9 verifica, il resto allenamento",
            "revisione": P.revisione(), "estensione_rust": P.estensione_rust(), "agente_ppo": P.AGENTE_PPO}


def esegui(out: Path, matchup, per_matchup: int, processi: int, ckpt, regole: str, iterazioni: int = ITERAZIONI,
           esplorazione=ESPLORAZIONE, misura_dopo: int = 200, scrivi=print) -> None:
    out.mkdir(parents=True, exist_ok=True)
    os.environ["RBSIM_REGOLE"] = regole
    args = {"regole": regole, "iterazioni": iterazioni, "esplorazione": list(esplorazione), "matchup": list(matchup),
            "per_matchup": per_matchup}
    (out / "provenienza.json").write_text(json.dumps(provenienza(args, out, ckpt), indent=1))
    fatte = {r["seme"] for r in indice(out)}
    tasks = [{"mu": mu, "seme": seme, "comincia": c, "scambio": sc, "iterazioni": iterazioni,
              "ckpt": None if ckpt is None else str(ckpt), "regole": regole, "esplorazione": list(esplorazione),
              "insieme": insieme(j), "out": str(out)}
             for mu, i, j, seme, c, sc in piano(matchup, per_matchup) if seme not in fatte]
    scrivi(f"{len(fatte)} partite gia' fatte, {len(tasks)} da fare, {processi} processi")
    t0, nuove, misurato = time.time(), [], False
    if not tasks:
        return

    def dopo(n_nuove):
        txt = misura(indice(out), time.time() - t0, processi, len(nuove))
        (out / "misura.txt").write_text(txt + "\n")
        scrivi(f"== misura dopo {n_nuove} partite\n{txt}")

    with ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn")) as pool:
        futuri = [pool.submit(_lavora, t) for t in tasks]
        for f in as_completed(futuri):
            try:
                nuove.append(f.result())
            except Exception as e:           # una partita che cade non ferma la raccolta: si rifa' al rilancio
                with open(out / "errori.txt", "a") as fe:
                    fe.write(f"{type(e).__name__}: {e}\n")
                continue
            if len(nuove) % 50 == 0:
                scrivi(f"{len(nuove)}/{len(tasks)} ({time.time() - t0:.0f} s)")
            if not misurato and len(nuove) >= min(misura_dopo, len(tasks)):
                misurato = True
                if len(nuove) < len(tasks):
                    dopo(len(nuove))
    dopo(len(nuove))
