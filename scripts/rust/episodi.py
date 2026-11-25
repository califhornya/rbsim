"""Cerca nelle autonome campione contro campione (D72-D77, iterazioni della pagina, sonda) le decisioni del campione che
somigliano a due difetti segnalati, dai log di ricerca (decisione_rs.originale: righe di `search_log` + eventi
di traccia con lo stato prima della mossa).

  python scripts/rust/episodi.py --matchup ES --semi 1-50 [--pesi-casuali] [--ckpt PATH] [--esempi 5] [--posti A B]

Criteri esatti (il campione = il posto indicato in --posti, default A; una "decisione esaminata" è una riga di
search_log di quel posto, cioè una ricerca; le decisioni prese dalla sonda non hanno riga e non si contano):

 §8 accumulo: decisione al punto turn_action con etichetta "Play X to BFn" (unità giocata sul campo n) o
    "Move X ...→BFn" (unità spostata sul campo n, da base o da un altro campo), tale che, nella posizione prima
    della mossa, (a) il campione controlla già il campo n, (b) lì non ci sono unità avversarie, (c) l'avversario
    controlla un altro campo. Si riportano il Might del campione già sul campo n (il margine: l'avversario ha 0) e i punti.
    Non contano: gear, AMBUSH in reazione, mosse verso la base.
 §7 spreco: decisione al punto showdown_action, prima azione non-pass della finestra di showdown (nessuna
    azione non-pass di nessuno dall'inizio dello showdown), con etichetta "Showdown X ..." dove X è una carta che
    aumenta la Might, tale che il Might del campione sul campo dello showdown supera già quello avversario.
    Carte che aumentano la Might: SPELL dei cinque mazzi il cui testo, tolte le parentesi (i promemoria), contiene
    "+N [might]" (registry.json; l'elenco è stampato). Includono Call to Glory, Punch First, Hold 'Em, Grim Resolve...
Uscita: conteggi e esempi come comando per `scripts/rust/decisione.py rifai --autonoma MU:SEME:starter --k K`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import decisione_rs as D  # noqa: E402

PLAY = re.compile(r"^Play (?!gear )(.+?) to BF(\d)$")
MOVE = re.compile(r"^Move (.+) (base|BF\d)→BF(\d)$")
SHOW = re.compile(r"^Showdown (.+?)(?: @BF\d)?$")


def carte_might() -> set:
    from riftbound.ai.ppo.collect import DECK_OF
    reg = json.loads((ROOT / "rust/data/registry.json").read_text())["cards"]
    nomi = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("name", "card") and isinstance(v, str):
                    nomi.add(v)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    for p in DECK_OF.values():
        walk(json.loads(Path(p).read_text()))
    out = set()
    for c in reg:
        if c["name"] in nomi and c["category"] == "SPELL":
            testo = re.sub(r"\([^)]*\)", "", c["raw"].get("effect") or "")
            if re.search(r"\+\d+\s*\[?might", testo, re.I):
                out.add(c["name"])
    return out


def corsa(pos: dict) -> tuple:
    """Come `race_info` di search.rs sulla posizione di `D.riassunto`: -> (race, op_next_wins). La prossima Beginning
    Phase e' di chi non e' attivo; si alternano le tenute (solo i campi controllati segnano) fino a V."""
    me = pos["seat"]
    h_me = sum(1 for c in pos["campi"] if c["controlla"] == "campione")
    h_op = sum(1 for c in pos["campi"] if c["controlla"] == "avversario")
    v = pos["v"]
    pm, po = pos["punti"]
    turno = "B" if pos["attivo"] == "A" else "A"
    onw = turno != me and po + h_op >= v and h_op > 0
    if h_me == 0 and h_op == 0:
        return 0, onw
    for _ in range(30):
        if turno == me:
            pm += h_me
            if pm >= v:
                return 1, onw
        else:
            po += h_op
            if po >= v:
                return -1, onw
        turno = "B" if turno == "A" else "A"
    return 0, onw


def esamina(partita: dict, might: set) -> tuple:
    """-> (decisioni esaminate, [episodi], decisioni Play/Move per stato della corsa)."""
    seat = partita["campione"]

    def tieni(e):
        lab = e["menu"][e["index"]]
        return e["point"] == "turn_action" or \
               (e["point"] == "showdown_action" and e["primo"] and SHOW.match(lab) and SHOW.match(lab).group(1) in might)

    righe = D.originale(partita, tieni)
    ep = []
    stati = {-1: 0, 0: 0, 1: 0}  # decisioni turn_action (Play/Move) per stato della corsa
    for o in righe:
        e = o["e"]
        if "state_raw" not in e:
            continue
        lab = o["action"]
        if e["point"] == "turn_action":
            m = PLAY.match(lab) or MOVE.match(lab)
            if not m:
                continue
            rc = corsa(D.riassunto(e["state_raw"], seat))[0]
            stati[rc] += 1
            d = int(m.group(2) if lab.startswith("Play") else m.group(3))
            pos = D.riassunto(e["state_raw"], seat)
            c = pos["campi"][d]
            if c["controlla"] == "campione" and not c["avversario"]["unita"] and \
                    any(x["controlla"] == "avversario" for i, x in enumerate(pos["campi"]) if i != d):
                ep.append({"tipo": "§8 accumulo", "race": rc, "k": o["k"], "turn": o["turn"], "azione": lab,
                           "might_gia": c["campione"]["might"], "punti": pos["punti"]})
        else:
            pos = D.riassunto(e["state_raw"], seat)
            c = pos["campi"][e["showdown"]]
            if c["campione"]["might"] > c["avversario"]["might"]:
                ep.append({"tipo": "§7 spreco", "k": o["k"], "turn": o["turn"], "azione": lab,
                           "might_gia": c["campione"]["might"], "might_avv": c["avversario"]["might"], "punti": pos["punti"]})
    return len(righe), ep, stati


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matchup", required=True)
    ap.add_argument("--semi", required=True, help="N (1..N) o A-B")
    ap.add_argument("--pesi-casuali", action="store_true")
    ap.add_argument("--ckpt")
    ap.add_argument("--esempi", type=int, default=5)
    ap.add_argument("--posti", nargs="+", default=["A"], choices=["A", "B"])
    ap.add_argument("--iterazioni", type=int, default=D.ITERAZIONI_CAMPIONE)
    ap.add_argument("--valutazione", default="storica", choices=["storica", "accumulo", "minaccia", "corsa", "rimonta"],
                    help="valutazione delle foglie del campione (default storica)")
    ap.add_argument("--k-acc", type=float, default=3.0)
    ap.add_argument("--alpha", type=float, default=0.2)
    a = ap.parse_args(argv)
    extra = {"valutazione": (a.valutazione, a.k_acc, a.alpha)} if a.valutazione != "storica" else {}
    val_orig = extra.get("valutazione")
    print(f"valutazione: {a.valutazione}" + (f" k={a.k_acc} alpha={a.alpha}" if extra else ""))
    might = carte_might()
    print("carte che aumentano la Might:", ", ".join(sorted(might)))
    t0 = time.time()
    esaminate, partite, conta, esempi = 0, 0, {}, {}
    den_race, ep_race = {-1: 0, 0: 0, 1: 0}, {-1: 0, 0: 0, 1: 0}
    per_partita: dict = {}
    for seed in D.semi(a.semi):
        for seat in a.posti:
            P = D.autonoma(a.matchup, seed, a.ckpt, a.pesi_casuali, a.iterazioni, seat, **extra)
            n, ep, stati = esamina(P, might)
            for r_, c_ in stati.items():
                den_race[r_] += c_
            esaminate += n
            partite += 1
            for x in ep:
                conta[x["tipo"]] = conta.get(x["tipo"], 0) + 1
                if "race" in x:
                    ep_race[x["race"]] += 1
                per_partita.setdefault(x["tipo"], set()).add((seed, seat))
                esempi.setdefault(x["tipo"], []).append((P, x))
            print(f"  seme {seed} posto {seat}: {n} ricerche, {len(ep)} episodi ({time.time() - t0:.0f} s)", flush=True)
    print(f"\nmatchup {a.matchup}: {partite} partite, {esaminate} decisioni esaminate (ricerche del campione)")
    for tipo in ("§8 accumulo", "§7 spreco"):
        print(f"{tipo}: {conta.get(tipo, 0)} episodi in {len(per_partita.get(tipo, ()))} partite su {partite}")
    print("§8 per stato della corsa al momento della decisione (episodi / decisioni Play-Move del campione):")
    for r_ in (-1, 0, 1):
        print(f"  race {r_:+d}: {ep_race[r_]}/{den_race[r_]}" + (f" = {100 * ep_race[r_] / den_race[r_]:.1f}%" if den_race[r_] else ""))
    for tipo, lista in esempi.items():
        print(f"\nesempi {tipo}:")
        for P, x in lista[:a.esempi]:
            cmd = f"decisione.py rifai --autonoma {a.matchup}:{P['seed']}:{P['starter']} --k {x['k']} --iterazioni 42 200 1000"
            if P["campione"] != "A":
                cmd += f" --campione {P['campione']}"
            if a.pesi_casuali:
                cmd += " --pesi-casuali"
            elif a.ckpt:
                cmd += f" --ckpt {a.ckpt}"
            if a.iterazioni != D.ITERAZIONI_CAMPIONE:
                cmd += f" --iter-orig {a.iterazioni}"
            if val_orig:  # la partita originale ha giocato con questa valutazione: il prefisso si riproduce solo con lei
                cmd += f" --valutazione-orig {val_orig[0]}:{val_orig[1]}:{val_orig[2]}"
            extra = f"Might gia' {x['might_gia']}" + (f" vs {x['might_avv']}" if "might_avv" in x else "")
            print(f"  turno {x['turn']} {x['azione']}; {extra}; punti {x['punti'][0]}-{x['punti'][1]}\n    {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
