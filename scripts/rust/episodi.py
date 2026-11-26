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

 §9 "prima togli il pezzo che blocca, poi gioca": Vex Apathetic (lista di Evelynn: "When an opponent plays a unit
    while I'm at a battlefield, STUN it"). Per il posto in --posti (il campione: per ES/EK contro Evelynn usare
    --posti B), da TUTTE le decisioni del campione (anche sonda, reazioni, showdown) con lo stato prima della mossa:
    occasione = decisione che gioca un'unita' ("Play X [to BFn]", "Deploy champion X", "AMBUSH X @BFn") mentre una
    Vex Apathetic avversaria e' su un campo. Esito, dagli stati delle decisioni successive del campione nello STESSO
    turno (numero di turno della traccia): "uccisa dopo" = poi la Vex non e' piu' fra le unita' avversarie (campi +
    base): candidato "ordine sbagliato"; "sopravvive" = e' ancora li' all'ultima decisione del turno; "n.d." =
    nessuna decisione successiva nel turno. "Ordine giusto" = turno del campione che inizia con la Vex su un campo,
    la Vex sparisce nel turno e il campione gioca almeno un'unita' DOPO, senza occasioni prima. Limiti: la morte si
    vede solo allo stato della decisione seguente (non distingue morte da rimbalzo in mano); "turni con Vex" = turni
    in cui il campione e' attivo e vede la Vex su un campo.
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


VEX = "Vex Apathetic"
GIOCA_UNITA = re.compile(r"^(?:Play|Deploy champion|AMBUSH) (.+?)(?: to BF\d| @BF\d)?$")


def nomi_unita() -> set:
    reg = json.loads((ROOT / "rust/data/registry.json").read_text())["cards"]
    return {c["name"] for c in reg if c["category"] in ("UNIT", "CHAMPION")}


def gioca_unita(label: str, unita: set) -> bool:
    m = GIOCA_UNITA.match(label)
    return bool(m) and m.group(1) in unita


def classifica_vex(seq: list) -> dict:
    """§9 sulla sequenza delle decisioni del campione (nell'ordine). Ogni elemento: turn, proprio (il campione e'
    attivo), vex_bf (Vex Apathetic avversarie su un campo), vex_tot (su un campo o in base), gioca (la mossa scelta
    gioca un'unita'), label, point, k (None se decisa dalla sonda). Logica pura, senza motore.
    -> {"turni_vex": n, "occasioni": [..], "ordine_giusto": [..]}; ogni occasione: turn, k, label, proprio,
    esito ("uccisa" | "sopravvive" | "nd"), tolta (etichetta dell'azione dopo cui la Vex sparisce, o None)."""
    turni: dict = {}
    for e in seq:
        turni.setdefault(e["turn"], []).append(e)
    out = {"turni_vex": 0, "occasioni": [], "ordine_giusto": []}
    for t, ev in turni.items():
        if any(e["proprio"] and e["vex_bf"] > 0 for e in ev):
            out["turni_vex"] += 1
        occ_prima = False
        for i, e in enumerate(ev):
            if not (e["gioca"] and e["vex_bf"] > 0):
                continue
            occ_prima = True
            dopo = ev[i + 1:]
            j = next((j for j, x in enumerate(dopo) if x["vex_tot"] < e["vex_tot"]), None)
            tolta = None
            if j is None:
                esito = "sopravvive" if dopo else "nd"
            else:
                esito = "uccisa"
                prima = ev[i + 1:i + 1 + j]  # le decisioni fra la giocata e lo stato in cui la Vex non c'e' piu'
                ta = [x for x in prima if x["point"] == "turn_action" and x["label"] != "Pass"]
                np_ = [x for x in prima if x["label"] != "Pass"]
                tolta = (ta[-1] if ta else np_[-1] if np_ else prima[-1])["label"] if prima else None
            out["occasioni"].append({"turn": t, "k": e["k"], "label": e["label"], "proprio": e["proprio"],
                                     "esito": esito, "tolta": tolta})
        if ev[0]["proprio"] and ev[0]["vex_bf"] > 0 and not occ_prima:
            j = next((j for j, x in enumerate(ev) if x["vex_tot"] < ev[0]["vex_tot"]), None)
            if j is not None:
                g = next((x for x in ev[j:] if x["gioca"]), None)
                if g:
                    out["ordine_giusto"].append({"turn": t, "k": g["k"], "label": g["label"]})
    return out


def sequenza_vex(partita: dict, unita: set) -> list:
    """Le decisioni del campione con la Vex (stato prima della mossa) per `classifica_vex`."""
    seat = partita["campione"]
    D.originale(partita, lambda e: True)
    tutti, pos = D.tutti(partita)
    k_di = {p: k for k, p in enumerate(pos)}
    seq = []
    for i, e in enumerate(tutti):
        lab = e["menu"][e["index"]]
        p = D.riassunto(e["state_raw"], seat)
        bf = sum(1 for c in p["campi"] for n, _m in c["avversario"]["unita"] if n == VEX)
        base = sum(1 for n, _m in p["base"]["avversario"]["unita"] if n == VEX)
        seq.append({"turn": e["turn"], "proprio": p["attivo"] == seat, "vex_bf": bf, "vex_tot": bf + base,
                    "gioca": gioca_unita(lab, unita), "label": lab, "point": e["point"], "k": k_di.get(i)})
    return seq


def esamina(partita: dict, might: set) -> tuple:
    """-> (decisioni esaminate, [episodi], decisioni Play/Move per stato della corsa)."""
    seat = partita["campione"]

    def tieni(e):
        lab = e["menu"][e["index"]]
        return e["point"] == "turn_action" or \
               (e["point"] == "showdown_action" and e["primo"] and SHOW.match(lab) and SHOW.match(lab).group(1) in might)

    righe = D.originale(partita, lambda e: True)  # lo stato di tutte le decisioni (serve a §9); §8/§7 filtrano con tieni
    ep = []
    stati = {-1: 0, 0: 0, 1: 0}  # decisioni turn_action (Play/Move) per stato della corsa
    for o in righe:
        e = o["e"]
        if "state_raw" not in e or not tieni(e):
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


def stampa_vex(a, vex: dict, comando) -> None:
    occ = [o for _P, o in vex["occ"]]
    kill = [(P, o) for P, o in vex["occ"] if o["esito"] == "uccisa"]
    surv = [o for o in occ if o["esito"] == "sopravvive"]
    nd = [o for o in occ if o["esito"] == "nd"]
    print(f"\n§9 Vex Apathetic, matchup {a.matchup}, {vex['partite']} partite (posti {' '.join(a.posti)}):")
    print(f"  turni del campione con la Vex su un campo: {vex['turni']}")
    print(f"  occasioni (unita' giocata con la Vex su un campo): {len(occ)}, di cui in turno avversario "
          f"(AMBUSH/reazione) {sum(1 for o in occ if not o['proprio'])}")
    print(f"    uccisa dopo (ordine sbagliato?): {len(kill)}   sopravvive: {len(surv)}   n.d.: {len(nd)}")
    print(f"  ordine giusto (Vex tolta prima, poi unita' giocata): {len(vex['giusto'])} turni")
    for titolo, lista in (("uccisa dopo", kill), ("sopravvive", [(P, o) for P, o in vex["occ"] if o["esito"] == "sopravvive"]),
                          ("ordine giusto", vex["giusto"])):
        print(f"  esempi {titolo}:")
        for P, o in lista[:a.esempi]:
            if o["k"] is None:
                print(f"    seme {P['seed']} turno {o['turn']} {o['label']}: decisa dalla sonda (nessuna riga, niente k)")
                continue
            tolta = o.get("tolta")
            print(f"    seme {P['seed']} turno {o['turn']} {o['label']}" + (f"; Vex tolta con: {tolta}" if tolta else "")
                  + f"\n      {comando(P, o['k'], '138 1000 5000', tolta, 'scripts/rust/decisione.py')}")


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
    unita = nomi_unita()
    vex = {"partite": 0, "turni": 0, "occ": [], "giusto": []}
    for seed in D.semi(a.semi):
        for seat in a.posti:
            P = D.autonoma(a.matchup, seed, a.ckpt, a.pesi_casuali, a.iterazioni, seat, **extra)
            n, ep, stati = esamina(P, might)
            v9 = classifica_vex(sequenza_vex(P, unita))
            D._ORIGINALI.clear()  # gli stati di tutte le decisioni pesano: la partita non serve piu'
            vex["partite"] += 1
            vex["turni"] += v9["turni_vex"]
            vex["occ"] += [(P, o) for o in v9["occasioni"]]
            vex["giusto"] += [(P, o) for o in v9["ordine_giusto"]]
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

    def comando(P, k, iters="42 200 1000", attese=None, prefisso="decisione.py"):
        cmd = f"{prefisso} rifai --autonoma {a.matchup}:{P['seed']}:{P['starter']} --k {k} --iterazioni {iters}"
        if attese:
            cmd += f' --attese "{attese}"'
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
        return cmd

    stampa_vex(a, vex, comando)
    for tipo, lista in esempi.items():
        print(f"\nesempi {tipo}:")
        for P, x in lista[:a.esempi]:
            cmd = comando(P, x["k"])
            extra = f"Might gia' {x['might_gia']}" + (f" vs {x['might_avv']}" if "might_avv" in x else "")
            print(f"  turno {x['turn']} {x['azione']}; {extra}; punti {x['punti'][0]}-{x['punti'][1]}\n    {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
