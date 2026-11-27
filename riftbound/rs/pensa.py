"""Pensare di piu' rende il campione piu' forte? (Astra, 27/11)

Un'arena: il campione a 1.000 iterazioni per ricerca (candidato) contro il campione a 138 (avversario), stesso
checkpoint, regole `6427b90+D72-D83`, scelta finale per Q, valutazione `rimonta` e sonda di vittoria da tutte e due
le parti. Aperture nuove (semi da `BASE_SEME`), coppie a posti scambiati, i 10 matchup di `arena_rs.COPERTI` a pesi
uguali. Si riporta il punteggio con l'IC 95% sulle coppie e la latenza REALE dei due lati: per decisione cercata e
per turno (somma delle ricerche dello stesso lato con lo stesso numero di turno in una partita).
Uscita: `arena.json`, `arena.txt`, `arena_righe.jsonl` (+ manifest)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from riftbound.rs import arena_rs, generazione
from riftbound.rs.scelta import arena_campione
from riftbound.rs.seguiti import N_BOOT, REGOLE

BASE_SEME = 70_000_000      # la raccolta usa 30M, l'arena di sviluppo 40M, i seguiti 50M, la scelta finale 60M
ITER_PENSA = 1000
ITER_BASE = 138
COPPIE = 100
LIMITE_TURNO = 300.0        # secondi: 5 minuti sul turno difficile (Matteo); la decisione sulla pagina e' umana


def _opz(iter_pensa: int, iter_base: int) -> dict:
    return generazione._opz(0.0, iter_base, True) | {"iter_cand": iter_pensa}


def _stat(x) -> dict:
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "media": float(x.mean()), "mediana": float(np.median(x)),
            "p95": float(np.percentile(x, 95)), "p99": float(np.percentile(x, 99)), "max": float(x.max())}


def latenza(fatte: dict) -> dict:
    """Dalle righe delle partite: per lato (cand/opp) le statistiche (secondi) per decisione cercata e per turno.
    Una decisione = una riga [turno, iterazioni, secondi]; un turno = somma delle decisioni dello stesso lato con lo
    stesso numero di turno nella stessa partita."""
    out = {}
    for lato in ("cand", "opp"):
        dec, turni = [], []
        for r in fatte.values():
            per_turno: dict = {}
            for t, _it, s in r.get("log", {}).get(lato, []):
                dec.append(s)
                per_turno[t] = per_turno.get(t, 0.0) + s
            turni.extend(per_turno.values())
        out[lato] = {"decisione": _stat(dec), "turno": _stat(turni)}
    return out


def _riga_lat(nome: str, s: dict) -> str:
    if not s["n"]:
        return f"   {nome}: nessun dato"
    return (f"   {nome}: n {s['n']}, media {s['media']:.2f}, mediana {s['mediana']:.2f}, p95 {s['p95']:.2f}, "
            f"p99 {s['p99']:.2f}, max {s['max']:.2f}")


def arena(matchup, coppie: int, out_dir, ckpt, processi: int = 1, regole: str = REGOLE, iter_pensa: int = ITER_PENSA,
          iter_base: int = ITER_BASE, n_boot: int = 4000, print_=print) -> list[str]:
    """Campione a `iter_pensa` iterazioni contro il campione a `iter_base`; scrive `arena.json` e `arena.txt`."""
    out_dir = Path(out_dir)
    ckpt = str(ckpt)
    a = arena_campione(matchup, coppie, out_dir, ckpt, _opz(iter_pensa, iter_base), BASE_SEME,
                       {"iter_pensa": iter_pensa, "iter_base": iter_base}, "pensa", processi, regole, n_boot, print_)
    tot, lo, hi = a["totale"]
    per = a["per"]
    lat = latenza(a["fatte"])
    sopra = bool(lo > 0.5)
    t = lat["cand"]["turno"]
    ok_max = bool(t["n"] and t["max"] <= LIMITE_TURNO)
    res = {"totale": [tot, lo, hi], "matchup": {mu: list(x) for mu, x in per.items()}, "coppie_per_matchup": coppie,
           "limite_inferiore_sopra_50": sopra, "latenza": lat, "max_turno_entro_5_minuti": ok_max,
           "configurazione": a["config"], "minuti": a["minuti"]}
    testo = [f"Pensare di piu': campione a {iter_pensa} iterazioni contro il campione a {iter_base}, {ckpt}, "
             f"{coppie} coppie per matchup ({', '.join(matchup)}), regole {regole}, scelta per Q, valutazione "
             f"rimonta e sonda da entrambe le parti, semi da {BASE_SEME}",
             f"totale {tot:.3f} (IC 95% {lo:.3f}-{hi:.3f}) sulle coppie, pesi uguali fra i matchup",
             "   " + "; ".join(f"{mu} {x[0]:.3f} ({x[1]:.2f}-{x[2]:.2f})" for mu, x in per.items()),
             f"latenza in secondi, lato {iter_pensa} iterazioni:",
             _riga_lat("per decisione cercata", lat["cand"]["decisione"]),
             _riga_lat("per turno", lat["cand"]["turno"]),
             f"latenza in secondi, lato {iter_base} iterazioni (confronto):",
             _riga_lat("per decisione cercata", lat["opp"]["decisione"]),
             _riga_lat("per turno", lat["opp"]["turno"]),
             "nota: i tempi sono misurati con tutti i processi in parallelo, quindi sono una stima per eccesso "
             "della latenza di una partita singola sulla pagina",
             f"criterio: limite inferiore > 50%: {'SI' if sopra else 'NO'}",
             (f"lato {iter_pensa}: p95 per turno {t['p95']:.1f} s, max per turno {t['max']:.1f} s; "
              f"max per turno <= 5 min: {'SI' if ok_max else 'NO'} (la decisione sulla pagina e' umana)"
              if t["n"] else "lato 1.000: nessun dato di latenza per turno"),
             f"durata dell'arena: {res['minuti']} min"]
    (out_dir / "arena.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "arena.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    return testo
