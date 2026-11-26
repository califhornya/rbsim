"""Rifare una decisione del campione con più iterazioni (docs/RUST.md "Rifare una decisione del campione").

  decisione.py rifai --pagina runs/coach/partite/XXX.json --turno 5 --iterazioni 42 200 1000 [--attese "Vi Peacekeeper"]
  decisione.py rifai --autonoma ES:3:a --k 17 --iterazioni 42 200 1000 [--ckpt PATH | --pesi-casuali] [--out F.json]
  decisione.py concordanza --matchup ES EK --semi 20 --iterazioni 200 [--campioni-per-tipo 20] [--out F.json]
  decisione.py incrocio --pagina F.json --campione B --k 10 --iterazioni 1000 5000 --mosse "Move X base→BF0" "Play Y"
        --conta "Punch First" [--quota-n 100] [--out F.txt]
  decisione.py guidata  --pagina F.json --campione B --k 10 --sequenza "Move X base→BF0" "Punch First" "Pass"
        [--avversario passa|campione] [--out F.txt]
  decisione.py continua --pagina F.json --campione B --k 10 --mosse "Move X base→BF0" "Play Y" [--n 100] [--processi 4]
        (ogni --mosse puo' essere una linea intera: "Play gear Z @BF0 ; Kinkou ; Move X base→BF0 ; Pass ; Punch First")
        etichette speciali: "?Punch First" = condizionale (solo se l'avversario risponde nella finestra, a catena
        risolta; se no e' saltata); "danni:Vex" = solo per la scelta dell'ordine dei danni; "scelta:Kinkou" = solo per
        le scelte; una linea di continua che finisce con " ; @finestre" passa al campione CON le finestre.

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
    orig = {}
    vo = getattr(a, "valutazione_orig", None)
    if vo and vo.split(":")[0] != "storica":
        nome, *par = vo.split(":")
        orig["valutazione"] = (nome, float(par[0]) if par else 3.0, float(par[1]) if len(par) > 1 else 0.2)
    if getattr(a, "finestre_orig", False):
        orig["finestre"] = True
    return {"tipo": "autonoma", "matchup": mu, "seed": int(seed), "starter": starter, "iterazioni": a.iter_orig,
            "probe": True, "campione": a.campione, **orig, **extra}


def _f(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def _riga_top(c: list) -> str:
    return " | ".join(f"{x['azione'][:34]} n={x['n']} q={_f(x['q'], 2)} P={_f(x['P'], 3)}" for x in c[:6])


def _stampa_diagnosi(d: dict, attese: list) -> None:
    """Per figlio della radice (per visite): visite, q e le giocate dei piloti nelle sue simulazioni (posto, punto,
    etichetta: conteggio); con --attese solo quelle la cui etichetta contiene una delle sottostringhe."""
    print("    figli della radice (visite, q; giocate dei piloti nelle finestre):")
    for i, c in sorted(enumerate(d["children"]), key=lambda x: (-x[1]["n"], x[0])):
        if not c["n"]:
            continue
        tal = [t for t in c["tally"] if not attese or any(s.casefold() in t[2].casefold() for s in attese)]
        tal.sort(key=lambda t: -t[3])
        resto = "; ".join(f"{t[0]} {t[1]} {t[2]}: {t[3]}" for t in tal[:8]) or "-"
        print(f"      {c['label'][:40]:40} n={c['n']:4} q={_f(c['q'], 2)}  {resto}")


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
    # None = omessa (la decisione rifatta tiene la valutazione originale); anche "storica" esplicita e' un override.
    val = (a.valutazione, a.k_acc, a.alpha) if a.valutazione is not None else None
    etich = f" [{a.valutazione} k={a.k_acc} alpha={a.alpha}]" if val else ""
    etich += " [finestre]" if a.finestre else ""
    etich += f" [quota {' | '.join(a.quota)} n={a.quota_n}]" if a.quota else ""
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
            if val is not None or a.finestre or a.quota:
                r = D.rifai(P, k, n, posizione=False, valutazione=val, finestre=True if a.finestre else None,
                            quota=(a.quota, a.quota_n) if a.quota else None)
            else:
                r = base if n == orig_n else D.rifai(P, k, n, posizione=False)
            out["varianti"][n] = {kk: vv for kk, vv in r.items() if kk != "posizione"}
            print(f"  N={n}{etich}: scelta {r['azione']} ({'uguale' if r['uguale'] else 'DIVERSA'} dall'originale)")
            print(f"    top: {_riga_top(r['classifica'])}")
            if r.get("diagnosi"):
                _stampa_diagnosi(r["diagnosi"], a.attese)
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


def _k_da_args(a, P) -> int:
    if a.k is not None:
        return a.k
    elenco = D.elenca(P)
    ks = [r["k"] for r in elenco if r["turn"] == a.turno and r["point"] == "turn_action" and r["n_menu"] > 1]
    if not ks:
        raise SystemExit(f"nessuna decisione di turno del campione al turno {a.turno}; turni con ricerche: "
                         f"{sorted({r['turn'] for r in elenco})}")
    return ks[0]


class _Rapporto:
    """Stampa e tiene le righe (per --out)."""

    def __init__(self):
        self.righe: list[str] = []

    def __call__(self, t: str = "") -> None:
        self.righe.append(t)
        print(t, flush=True)

    def scrivi(self, path) -> None:
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("\n".join(self.righe).rstrip("\n") + "\n", encoding="utf-8")


def cmd_incrocio(a) -> int:
    from riftbound.rs import decisione_esp as E
    P = partita_da_args(a)
    k = _k_da_args(a, P)
    out = _Rapporto()
    t0 = time.time()
    res = E.incrocio(P, k, a.iterazioni, a.mosse, a.conta, a.quota_n,
                     avanzamento=lambda n, c: print(f"  N={n} {E._nome_cond(c)} fatto ({time.time() - t0:.0f} s)", file=sys.stderr, flush=True))
    for r in E.testo_incrocio(res, a.mosse, a.conta, k, a.quota_n):
        out(r)
    out(f"{time.time() - t0:.0f} s")
    out.scrivi(a.out)
    return 0


def cmd_guidata(a) -> int:
    from riftbound.rs import decisione_esp as E
    P = partita_da_args(a)
    out = _Rapporto()
    E.guidata(P, _k_da_args(a, P), a.sequenza, a.avversario, out)
    out.scrivi(a.out)
    return 0


def cmd_continua(a) -> int:
    from riftbound.rs import decisione_esp as E
    P = partita_da_args(a)
    out = _Rapporto()
    res = E.continua(P, _k_da_args(a, P), a.mosse, a.n, a.processi, out)
    for r in E.testo_continua(res):
        out(r)
    out.scrivi(a.out)
    if a.out:   # gli esiti per mondo (differenze appaiate, istogrammi delle deviazioni) accanto al testo
        Path(a.out).with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
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
    r.add_argument("--valutazione", default=None, choices=["storica", "accumulo", "minaccia", "corsa", "rimonta"],
                   help="valutazione delle foglie nella decisione rifatta (il prefisso resta quello di --valutazione-orig)")
    r.add_argument("--valutazione-orig", default=None, metavar="NOME[:k:alpha]",
                   help="valutazione con cui e' stata giocata la partita autonoma originale (default storica): il prefisso si riproduce con lei")
    r.add_argument("--finestre-orig", action="store_true",
                   help="la partita autonoma originale e' stata giocata con le finestre (il prefisso si riproduce solo cosi')")
    r.add_argument("--k-acc", dest="k_acc", type=float, default=3.0)
    r.add_argument("--alpha", type=float, default=0.2)
    r.add_argument("--tipo", default="turno", choices=["turno", "reazione", "showdown", "tutti"])
    r.add_argument("--attese", nargs="*", default=[])
    r.add_argument("--finestre", action="store_true",
                   help="le simulazioni della ricerca rifatta giocano le finestre di reazione/showdown per i due posti (pilota)")
    r.add_argument("--quota", nargs="+", default=None, metavar="ETICHETTA",
                   help="nella radice della ricerca di turno, finché un figlio la cui etichetta contiene una di queste "
                        "sottostringhe ha meno di --quota-n visite si simula quello con meno visite")
    r.add_argument("--quota-n", type=int, default=10)
    c = sub.choices["concordanza"]
    c.add_argument("--matchup", nargs="+", required=True)
    c.add_argument("--semi", required=True, help="N (1..N) o A-B")
    c.add_argument("--campioni-per-tipo", type=int, default=20)
    for nome in ("incrocio", "guidata", "continua"):
        x = sub.add_parser(nome)
        x.add_argument("--ckpt", default=None, help=f"default {D.CKPT_DEFAULT}")
        x.add_argument("--pesi-casuali", action="store_true")
        x.add_argument("--iter-orig", type=int, default=D.ITERAZIONI_CAMPIONE, help="iterazioni del campione originale (autonome)")
        x.add_argument("--campione", default="A", choices=["A", "B"])
        x.add_argument("--out")
        g = x.add_mutually_exclusive_group(required=True)
        g.add_argument("--pagina")
        g.add_argument("--autonoma", help="MU:SEME:starter, es. ES:3:a")
        t = x.add_mutually_exclusive_group(required=True)
        t.add_argument("--turno", type=int, help="la prima decisione di turno del campione in quel turno")
        t.add_argument("--k", type=int)
        x.add_argument("--valutazione-orig", default=None, metavar="NOME[:k:alpha]")
        x.add_argument("--finestre-orig", action="store_true",
                       help="la partita autonoma originale e' stata giocata con le finestre")
    x = sub.choices["incrocio"]
    x.add_argument("--iterazioni", type=int, nargs="+", required=True)
    x.add_argument("--mosse", nargs="+", required=True, metavar="ETICHETTA")
    x.add_argument("--conta", nargs="*", default=[], metavar="ETICHETTA")
    x.add_argument("--quota-n", type=int, default=100)
    x = sub.choices["guidata"]
    x.add_argument("--sequenza", nargs="+", required=True, metavar="ETICHETTA")
    x.add_argument("--avversario", default="passa", choices=["passa", "campione"])
    x = sub.choices["continua"]
    x.add_argument("--mosse", nargs="+", required=True, metavar="LINEA",
                   help='una etichetta (la prima mossa, poi il campione) o etichette separate da " ; " (la linea, forzata come in guidata; '
                        'in coda " ; @finestre" = poi il campione con le finestre)')
    x.add_argument("--n", type=int, default=100)
    x.add_argument("--processi", type=int, default=1, help="processi in parallelo (una continuazione ciascuno)")
    a = ap.parse_args(argv)
    return {"rifai": cmd_rifai, "concordanza": cmd_concordanza, "incrocio": cmd_incrocio, "guidata": cmd_guidata,
            "continua": cmd_continua}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
