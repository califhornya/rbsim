"""Varianti piu' economiche di «pensa» sui dati salvati di un esperimento fondo. Uso: fondo_ridotto.py <cartella fondo/>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from riftbound.rs import fondo as F, scelta as C  # noqa: E402

MONDI, KS, FRAZ_SALTO = (8, 12, 16, 24, 32), (2, 3), (0.25, 0.5, 0.75)
ITER, ARENA_H, MAC_S = 138, 56.5, 65.7
SOGLIA_TOT, MAX_NV = 0.019, 0.10


def carica(fondo: Path) -> list[dict]:
    decs = [d for riga in open(fondo / "decisioni.jsonl") for d in json.loads(riga)["decisioni"]]
    cart = {}
    for c in sorted(p for p in fondo.iterdir() if p.is_dir()):
        _, resto = c.name.split("_", 1)
        nome, k = resto.rsplit("_k", 1)
        cart[(nome, int(k))] = c
    out = []
    for d in decs:
        c = cart.get((d["nome"], d["k"]))
        if c is None and d["coerente"]:
            raise KeyError((d["nome"], d["k"]))
        e = {"dec": d, "sc": None, "dati": [], "ve": None}
        if c is None:  # decisione incoerente senza cartella: niente scelta, niente verifica
            out.append(e)
            continue
        if (c / "scelta_mondi.jsonl").exists():
            e["sc"] = json.loads((c / "scelta.json").read_text())
            e["dati"] = [json.loads(r) for r in open(c / "scelta_mondi.jsonl") if r.strip()]
        if (c / "verifica.json").exists():
            v = json.loads((c / "verifica.json").read_text())
            e["ve"] = {"media": v.get("media"), "n_mondi": len(v["deltas"]), "mondi_esclusi": v.get("mondi_esclusi", 0),
                       "deltas": v["deltas"]}
        out.append(e)
    return out


def stima_non_verificata(dati: list, nomi: list[str], s: int, m: int):
    """Media(ritorno[s]-ritorno[0]) sui mondi di indice >= m (con m=32 tutti: distorta); mondo valido se tutte le linee ok."""
    biased = m >= len(dati)
    idx = range(len(dati)) if biased else range(m, len(dati))
    dl = []
    for i in idx:
        r = {x["line"]: x for x in dati[i]}
        if all(r[n]["primo_ok"] for n in nomi):
            dl.append(r[nomi[s]]["returns"] - r[nomi[0]]["returns"])
    return (float(np.mean(dl)) if dl else None), len(dl), biased


def valuta(e: dict, m: int, k: int, salto: tuple | None, soglie: dict, mista: bool = False):
    """-> (riga, costo, info) con info = dict(cambia, nonver, distorta). Per m < 32 la scelta ridotta diversa dal
    campione si valuta SEMPRE sui mondi rimasti (m..31), indipendenti dalla scelta piena; con `mista=True` la stima
    di prima (verifica se la scelta coincide con la piena, altrimenti i mondi rimasti), non verificate «distorte»."""
    d, sc = e["dec"], e["sc"]
    nc = min(k, len(d["candidati"]))
    base = {"cambia": False, "nonver": False, "distorta": False, "senza_mondi": False}
    if sc is None or len(d["candidati"]) < 2:
        return F.riga(d, None, None), 0.0, base
    if salto:
        tipo = salto[0]
        x = d["n"][0] / ITER if tipo == "quota" else d["q"][0] - max(d["q"][1:nc])
        if x >= soglie[salto]:
            return F.riga(d, None, None), 0.0, base | {"saltata": True}
    nomi = [f"c{j}" for j in range(nc)]
    costo = sum(x["secondi"] for rows in e["dati"][:m] for x in rows if x["line"] in nomi)
    v = F.valuta_scelta(e["dati"][:m], nomi)
    s = v["scelta"]
    if s == 0 or not d["coerente"]:
        return F.riga(d, {"scelta": 0}, None), costo, base
    info = base | {"cambia": True}
    if m < len(e["dati"]) and not mista:
        media, n, _ = stima_non_verificata(e["dati"], nomi, s, m)
        ve = {"media": media, "n_mondi": n, "mondi_esclusi": 0, "deltas": []}
        info |= {"senza_mondi": media is None}
    elif s == sc["scelta"] and e["ve"] is not None:
        ve = e["ve"]
    else:
        media, n, biased = stima_non_verificata(e["dati"], nomi, s, m)
        ve = {"media": media, "n_mondi": n, "mondi_esclusi": 0, "deltas": []}
        info |= {"nonver": True, "distorta": biased or mista, "senza_mondi": media is None}
    return F.riga(d, {"scelta": s}, ve), costo, info


def variante(es, m, k, salto, soglie, mista=False):
    rows, costo, ch, nv, dist, sm = [], 0.0, 0, 0, 0, 0
    for e in es:
        r, c, i = valuta(e, m, k, salto, soglie, mista)
        rows.append(r)
        costo += c
        ch += i["cambia"]
        nv += i["nonver"]
        dist += i["distorta"]
        sm += i["senza_mondi"]
    return rows, costo, ch, nv, dist, sm


def main(fondo: Path) -> None:
    es = carica(fondo)
    molti = [e for e in es if e["sc"] is not None and len(e["dec"]["candidati"]) >= 2]
    n_multi = len(molti)
    quote = np.array([e["dec"]["n"][0] / ITER for e in molti])
    scarti = {k: np.array([e["dec"]["q"][0] - max(e["dec"]["q"][1:min(k, len(e["dec"]["candidati"]))]) for e in molti])
              for k in KS}
    saltimenti: list[tuple | None] = [None]
    soglie_q = {f: float(np.quantile(quote, 1 - f)) for f in FRAZ_SALTO}
    soglie_s = {(k, f): float(np.quantile(scarti[k], 1 - f)) for k in KS for f in FRAZ_SALTO}
    anomalie = []
    anomalie.append(f"decisioni {len(es)}, con >=2 candidati e mondi {n_multi}; incoerenti {sum(not e['dec']['coerente'] for e in es)}")
    # costo variante piena
    _, c_pieno, *_ = variante(es, 32, 3, None, {})
    res = []
    for m in MONDI:
        for k in KS:
            lista = [("nessuno", None, None)]
            for f in FRAZ_SALTO:
                lista.append((f"quota {soglie_q[f]:.3f}", ("quota", f), soglie_q[f]))
                lista.append((f"scarto {soglie_s[(k, f)]:.4f}", ("scarto", f), soglie_s[(k, f)]))
            for nome, chiave, soglia in lista:
                sg = {chiave: soglia} if chiave else {}
                rows, costo, ch, nv, dist, sm = variante(es, m, k, chiave, sg)
                rs = C.riassunto(rows)
                rows_m, _c, _ch, nv_m, dist_m, _sm = variante(es, m, k, chiave, sg, mista=True)
                rs_m = C.riassunto(rows_m)
                # non verificate a 0
                nonver_ids = nonverificate_ids(es, m, k, chiave, sg)
                rows0 = [r | ({"media": 0.0, "disaccordo": r["disaccordo"]} if i in nonver_ids else {}) for i, r in enumerate(rows)]
                rs0 = C.riassunto(rows0)
                saltate = sum(1 for e in molti if valuta(e, m, k, chiave, sg)[2].get("saltata"))
                res.append({"m": m, "k": k, "salto": nome, "tipo": chiave[0] if chiave else None,
                            "frazione": chiave[1] if chiave else 0, "saltate": saltate, "frac_saltate": saltate / n_multi,
                            "totale": rs["totale"], "cambi": ch, "nonverificate": nv, "distorta": dist, "senza_mondi": sm,
                            "totale_nv0": rs0["totale"][0], "totale_mista": rs_m["totale"],
                            "nonver_mista": nv_m, "distorte_mista": dist_m, "rapporto": costo / c_pieno,
                            "ore_arena": ARENA_H * costo / c_pieno, "s_turno_mac": MAC_S * costo / c_pieno})
    # controllo
    pieno = next(r for r in res if r["m"] == 32 and r["k"] == 3 and r["tipo"] is None)
    t, lo, hi = pieno["totale"]
    ok = round(100 * t, 1) == 2.5 and round(100 * lo, 1) == 1.7 and round(100 * hi, 1) == 3.4 and pieno["cambi"] == 135
    # scelta ricalcolata = scelta.json
    diff = sum(1 for e in molti if F.valuta_scelta(e["dati"], [f"c{j}" for j in range(len(e["dec"]["candidati"]))])["scelta"] != e["sc"]["scelta"])
    anomalie.append(f"scelta ricalcolata diversa da scelta.json: {diff}")
    anomalie.append(f"verifiche mancanti dove la scelta piena e' diversa da 0: "
                    f"{sum(1 for e in es if e['sc'] and e['sc']['scelta'] != 0 and e['ve'] is None)}")
    anomalie.append(f"non verificate senza mondi validi (valore escluso): {sum(r['senza_mondi'] for r in res)} su tutte le varianti")
    # m < 32: totale indipendente sui mondi rimasti, senza criterio sulle non verificate (che vale solo per m = 32)
    buone = [r for r in res if r["totale"][0] >= SOGLIA_TOT and r["totale"][1] > 0
             and (r["m"] < 32 or r["nonverificate"] <= MAX_NV * max(1, r["cambi"]))]
    buone.sort(key=lambda r: r["rapporto"])
    out = {"controllo": {"ok": ok, "pieno": pieno}, "consigliata": buone[0] if buone else None, "migliori8": buone[:8],
           "varianti": res, "anomalie": anomalie,
           "soglie": {"quota": {str(f): v for f, v in soglie_q.items()},
                      "scarto": {f"k{k}_{f}": v for (k, f), v in soglie_s.items()}}}
    sup = fondo.parent
    (sup / "ridotto.json").write_text(json.dumps(out, indent=1))

    def pp(x): return f"{100 * x:+.1f}"
    def riga_t(r):
        return (f"m={r['m']} k={r['k']} salto={r['salto']} (saltate {100 * r['frac_saltate']:.0f}%): {pp(r['totale'][0])} pp "
                f"[{pp(r['totale'][1])}, {pp(r['totale'][2])}], cambi {r['cambi']}, non verif. {r['nonverificate']}"
                f"{' (distorte ' + str(r['distorta']) + ')' if r['distorta'] else ''}, tot. nv=0 {pp(r['totale_nv0'])}, "
                f"{'mista ' + pp(r['totale_mista'][0]) + ' [' + pp(r['totale_mista'][1]) + ', ' + pp(r['totale_mista'][2]) + '] non verif. ' + str(r['nonver_mista']) + ' (distorte ' + str(r['distorte_mista']) + '), ' if r['m'] < 32 else ''}"
                f"costo {r['rapporto']:.3f}, arena {r['ore_arena']:.1f} h, {r['s_turno_mac']:.1f} s/turno")
    L = [f"Controllo variante piena: {'OK' if ok else 'FALLITO'} -> " + riga_t(pieno),
         "Regola: la piu' economica con totale >= +1,9 pp, limite inf. > 0; per m = 32 anche non verificate <= 10% dei cambi.",
         "Per m < 32 il totale usa i mondi rimasti (m..31) per ogni scelta ridotta diversa dal campione; la stima mista e' in 'mista'.",
         "CONSIGLIATA: " + (riga_t(buone[0]) if buone else "nessuna"), "", "Prime 8 che rispettano la regola:"]
    L += [f"{i + 1}. " + riga_t(r) for i, r in enumerate(buone[:8])]
    L += ["", "Tutte le varianti:"] + [riga_t(r) for r in sorted(res, key=lambda r: r["rapporto"])]
    L += ["", "Anomalie:"] + anomalie
    (sup / "ridotto.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L[:3 + 10]))


def nonverificate_ids(es, m, k, salto, soglie) -> set:
    return {i for i, e in enumerate(es) if valuta(e, m, k, salto, soglie)[2]["nonver"]}


if __name__ == "__main__":
    main(Path(sys.argv[1]))
