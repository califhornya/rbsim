"""Rifare una decisione del campione con più iterazioni (docs/RUST.md "Rifare una decisione del campione").

  decisione.py rifai --pagina runs/coach/partite/XXX.json --turno 5 --iterazioni 42 200 1000 [--attese "Vi Peacekeeper"]
  decisione.py rifai --autonoma ES:3:a --k 17 --iterazioni 42 200 1000 [--ckpt PATH | --pesi-casuali] [--out F.json]
  decisione.py concordanza --matchup ES EK --semi 20 --iterazioni 200 [--campioni-per-tipo 20] [--out F.json]

`rifai`: rigioca la partita (regole, seed, mazzi, prior e iterazioni del campione come all'origine) e alla ricerca
scelta rifà la decisione con ogni valore di --iterazioni (quello uguale all'originale, 42 di norma, riproduce la mossa:
la prima riga dice se è così). Con --turno T le decisioni bersaglio sono quelle del campione nel turno T al punto
--tipo (turno | reazione | showdown | tutti; default turno). Per ogni valore: la mossa scelta, le prime 6 per visite
(n, q, P) e, per ogni --attese (sottostringa dell'etichetta), se è nel menu: visite, q, rango.
`concordanza`: autonome campione contro campione (iterazioni della pagina + sonda); su un campione di decisioni per tipo di
punto le rifà a M iterazioni e conta le uguali. Il win_probe resta acceso nel rifacimento (override in Rust). Il checkpoint di default è runs/sett/ekris_s12/ckpt_040000.pt; --pesi-casuali prova
con una rete a pesi casuali (dove il checkpoint non c'è).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import decisione_rs as D  # noqa: E402

TIPO_PUNTO = {"turno": "turn_action", "reazione": "reaction", "showdown": "showdown_action"}


def partita_da_args(a) -> dict:
    extra = {"ckpt": a.ckpt, "casuali": a.pesi_casuali}
    if a.pagina:
        return {"tipo": "pagina", "file": a.pagina, **extra}
    mu, seed, starter = a.autonoma.split(":")
    return {"tipo": "autonoma", "matchup": mu, "seed": int(seed), "starter": starter, "iterazioni": a.iter_orig,
            "probe": True, "campione": a.campione, **extra}


def _f(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def _riga_top(c: list) -> str:
    return " | ".join(f"{x['azione'][:34]} n={x['n']} q={_f(x['q'], 2)} P={_f(x['P'], 3)}" for x in c[:6])


def cmd_rifai(a) -> int:
    P = partita_da_args(a)
    elenco = D.elenca(P)
    if a.k is not None:
        bersagli = [a.k]
    else:
        tipi = TIPO_PUNTO if a.tipo == "tutti" else {a.tipo: TIPO_PUNTO[a.tipo]}
        bersagli = [r["k"] for r in elenco if r["turn"] == a.turno and r["n_menu"] > 1 and r["point"] in tipi.values()]
        if not bersagli:
            print(f"nessuna decisione del campione al turno {a.turno} (tipo {a.tipo}); turni con ricerche: "
                  f"{sorted({r['turn'] for r in elenco})}")
            return 1
    orig_n = (D._prepara(P)["iterazioni"])
    tutti = []
    for k in bersagli:
        base = D.rifai(P, k, None, posizione=True)
        e = elenco[k]
        print(f"[k={k} turno {e['turn']} {e['point']}] originale: {e['action']}; riproduce la mossa originale: "
              f"{'sì' if base['riproduce'] else 'no'}" + ("" if base["prefisso_ok"] else " (il prefisso non coincide)")
              + (" [dopo decisioni della sonda: indice coerente, la sonda gira anche nel rifacimento]" if base["dopo_sonda"] else ""))
        for r in D.testo_posizione(base["posizione"]):
            print("  " + r[:200])
        out = {"k": k, "originale": e["action"], "posizione": base["posizione"], "varianti": {}}
        for n in a.iterazioni:
            r = base if n == orig_n else D.rifai(P, k, n, posizione=False)
            out["varianti"][n] = {kk: vv for kk, vv in r.items() if kk != "posizione"}
            print(f"  N={n}: scelta {r['azione']} ({'uguale' if r['uguale'] else 'DIVERSA'} dall'originale)")
            print(f"    top: {_riga_top(r['classifica'])}")
            for sub in a.attese:
                trov = [x for x in r["classifica"] if sub.casefold() in x["azione"].casefold()]
                if not trov:
                    print(f"    attesa '{sub}': non è nel menu (non legale)")
                for x in trov:
                    print(f"    attesa '{sub}': {x['azione']} visite={x['n']} q={_f(x['q'], 2)} rango={x['rango']}/{len(r['classifica'])}")
        tutti.append(out)
    if a.out:
        Path(a.out).write_text(json.dumps({"partita": {k: v for k, v in P.items() if k != "answers"},
                                           "decisioni": tutti}, ensure_ascii=False, indent=1, default=str))
    return 0


def cmd_concordanza(a) -> int:
    t0 = time.time()
    tot = {}
    for mu in a.matchup:
        r = D.concordanza(mu, D.semi(a.semi), a.iterazioni[0], a.campioni_per_tipo, a.ckpt, a.pesi_casuali,
                          a.iter_orig, a.campione)
        tot[mu] = r
        for tipo, x in r.items():
            pct = "-" if x["pct"] is None else f"{x['pct']:.0f}%"
            print(f"{mu} {tipo}: decisioni {x['decisioni']}, uguali {x['uguali']}, {pct}"
                  f" (disponibili {x['disponibili']}, escluse per prefisso non riprodotto {x['escluse']})")
    print(f"M={a.iterazioni[0]} contro originale {a.iter_orig}; {time.time() - t0:.0f} s")
    if a.out:
        Path(a.out).write_text(json.dumps(tot, ensure_ascii=False, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("rifai", "concordanza"):
        s = sub.add_parser(nome)
        s.add_argument("--ckpt", default=None, help=f"default {D.CKPT_DEFAULT}")
        s.add_argument("--pesi-casuali", action="store_true")
        s.add_argument("--iterazioni", type=int, nargs="+", required=True)
        s.add_argument("--iter-orig", type=int, default=D.ITERAZIONI_CAMPIONE, help="iterazioni del campione originale (autonome)")
        s.add_argument("--campione", default="A", choices=["A", "B"])
        s.add_argument("--out")
    r = sub.choices["rifai"]
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--pagina")
    g.add_argument("--autonoma", help="MU:SEME:starter, es. ES:3:a")
    t = r.add_mutually_exclusive_group(required=True)
    t.add_argument("--turno", type=int)
    t.add_argument("--k", type=int)
    r.add_argument("--tipo", default="turno", choices=["turno", "reazione", "showdown", "tutti"])
    r.add_argument("--attese", nargs="*", default=[])
    c = sub.choices["concordanza"]
    c.add_argument("--matchup", nargs="+", required=True)
    c.add_argument("--semi", required=True, help="N (1..N) o A-B")
    c.add_argument("--campioni-per-tipo", type=int, default=20)
    a = ap.parse_args(argv)
    return cmd_rifai(a) if a.cmd == "rifai" else cmd_concordanza(a)


if __name__ == "__main__":
    sys.exit(main())
