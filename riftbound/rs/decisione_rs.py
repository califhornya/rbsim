"""Rifare una decisione del campione (la ricerca coi prior della rete) su Rust, con più iterazioni.

`rifai(partita, k, iterazioni)` rigioca da capo la partita con le impostazioni originali del campione
(regole, seed, mazzi, prior, iterazioni, win_probe) e alla ricerca `k` del campione fa `iterazioni`
iterazioni invece di quelle originali (None = come l'originale), poi ferma la partita. `elenca(partita)`
dà tutte le decisioni cercate del campione nella partita originale per scegliere `k`.

`partita`:
  {"tipo": "pagina", "file": "runs/coach/partite/XXX.json"}   posto umano risposto con le `answers` del
      blocco `replay` (come il rewind di coach_rs.py); il campione è l'altro posto.
  {"tipo": "autonoma", "matchup": "ES", "seed": 3, "starter": "a", "regole": ..., "ckpt": path,
      "iterazioni": 42, "probe": True, "campione": "A"}      campione contro campione (stesso ckpt,
      entrambi i posti, come arena_rs.game ma a lavoro fisso); `campione` è il posto studiato.
  Chiavi facoltative: "casuali": True (rete a pesi casuali: `PPONet()` con `torch.manual_seed(0)`, come la
  misura di N=42 in coach_rs.py, per provare dove il checkpoint non c'è), "ckpt", "max_turni".

Ganci e win_probe (verificato in search.rs, `decide_action`): con i ganci (`before`/`after`, il lockstep)
il win_probe NON gira (`self.win_probe && self.lockstep.is_none()`). Il rifacimento ha i ganci sul posto del
campione, dunque salta la sonda: dove la partita originale ha deciso con la sonda (il turno in cui il campione
trova una vittoria in questo turno, senza ricerca né riga di log) il rifacimento cerca invece, consuma
numeri casuali e diverge da lì in poi. Prima di quel turno la partita si riproduce uguale. Nessun
aggiramento in Rust: `rifai` confronta il prefisso (azioni delle ricerche 0..k) con l'originale e dice
`riproduce` sì/no; le decisioni dell'ultimo turno del campione (di una partita che lui vince) sono quelle a rischio.

Dopo la ricerca k il rifacimento si ferma dall'osservatore della traccia (`trace_on`) sull'evento di decisione
di k, non dal gancio `after` (che con un numero fisso di iterazioni non viene chiamato, e comunque scatta
prima che la riga di log di k esista): lo stato dell'evento è la posizione di k.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from riftbound.provenienza import REGOLE_D72_D77

ROOT = Path(__file__).resolve().parents[2]
CKPT_DEFAULT = "runs/sett/ekris_s12/ckpt_040000.pt"
ITERAZIONI_CAMPIONE = 42
TIPI = {"turn_action": "turno", "reaction": "reazione", "showdown_action": "showdown"}
_RETI: dict = {}
_ORIGINALI: dict = {}


class _Stop(Exception):
    """Fine voluta della partita rifatta."""


class _Finite(Exception):
    """Le risposte registrate del posto umano sono finite (partita salvata a metà: abbandonata)."""


# -- la rete ------------------------------------------------------------------------------------

def rete(ckpt: str | None = None, casuali: bool = False):
    """La funzione dei prior (arena_rs.make_probs) del checkpoint, o di una rete a pesi casuali."""
    from riftbound.rs import arena_rs
    key = "casuali" if casuali else str(ckpt or CKPT_DEFAULT)
    if key not in _RETI:
        import torch
        torch.set_num_threads(1)
        if casuali:
            from riftbound.ai.ppo.model import PPONet
            torch.manual_seed(0)
            net = PPONet().eval()
        else:
            from riftbound.ai.ppo.model import load
            p = Path(key)
            net = load(p if p.is_absolute() else ROOT / p).eval()
        _RETI[key] = arena_rs.make_probs(net)
    return _RETI[key]


# -- la partita ---------------------------------------------------------------------------------

def _prepara(partita: dict) -> dict:
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import arena_rs
    P: dict = {"tipo": partita["tipo"], "casuali": bool(partita.get("casuali")),
               "max_turni": partita.get("max_turni", arena_rs.MAX_TURNS)}
    if partita["tipo"] == "pagina":
        d = json.loads(Path(partita["file"]).read_text(encoding="utf-8"))
        rp = d["replay"]
        if rp.get("opponent") != "campione":
            raise ValueError("la partita non è contro il campione")
        seed = rp["seed"]
        umano = rp["seat"]
        P.update(seed=seed, umano=umano, camp="B" if umano == "A" else "A",
                 deck_a=Path(rp["deck_a"]), deck_b=Path(rp["deck_b"]), bf_a=rp.get("bf_a"), bf_b=rp.get("bf_b"),
                 starter=(rp.get("starter") or random.Random(seed).choice(["A", "B"])).lower(),
                 iterazioni=rp.get("iterazioni") or ITERAZIONI_CAMPIONE, probe=True,
                 regole=rp.get("regole") or REGOLE_D72_D77, answers=rp["answers"],
                 ckpt=partita.get("ckpt") or d.get("info", {}).get("campione") or CKPT_DEFAULT)
    elif partita["tipo"] == "autonoma":
        mu = partita["matchup"]
        P.update(seed=partita["seed"], camp=partita.get("campione", "A"), umano=None,
                 deck_a=Path(DECK_OF[mu[0]]), deck_b=Path(DECK_OF[mu[1]]), bf_a=None, bf_b=None,
                 starter=str(partita.get("starter", "a")).lower(), iterazioni=partita.get("iterazioni", ITERAZIONI_CAMPIONE),
                 probe=partita.get("probe", True), regole=partita.get("regole") or REGOLE_D72_D77, answers=None,
                 ckpt=partita.get("ckpt") or CKPT_DEFAULT)
    else:
        raise ValueError(f"tipo di partita sconosciuto: {partita['tipo']}")
    return P


def _chiave(P: dict) -> str:
    return json.dumps({k: str(v) for k, v in P.items() if k != "answers"}, sort_keys=True) + \
        (str(len(P["answers"])) if P["answers"] is not None else "")


def _gioca(P: dict, k: int | None, iterazioni: int | None, stato=None, ganci: bool = True):
    """Una partita. `k`: la ricerca del campione da rifare (None: la partita originale, senza ganci);
    si ferma sull'evento di decisione di k. -> (righe di log "search", eventi del campione, evento di k).
    `stato(e)`: tiene lo stato (state_raw) degli eventi del campione per cui è vero."""
    from riftbound.rs import arena_rs, rust_bridge
    camp, umano = P["camp"], P["umano"]
    g = rust_bridge.build(P["seed"], P["deck_a"], P["deck_b"], P["starter"], P["max_turni"],
                          regole=P["regole"], bf_a=P["bf_a"], bf_b=P["bf_b"])
    probs = rete(P["ckpt"], P["casuali"])
    st = {"armato": False, "k": None, "evento": None, "finestra": None, "nonpass": False}
    eventi: list = []
    n_ask = [0]

    def before(info):
        i = json.loads(info)
        if k is not None and i["k"] == k:
            st["armato"] = True
            return -1 if iterazioni is None else int(iterazioni)
        return -1

    def watch(ev):
        if '"k":"decision"' not in ev[:60]:
            return
        e = json.loads(ev)
        if e.get("k") != "decision":
            return
        w = e.get("win") or {}
        sd = w.get("showdown")
        # finestra di showdown: l'azione e' la prima non-pass della finestra
        if sd is None:
            st["finestra"], st["nonpass"] = None, False
        elif st["finestra"] != (w.get("turn"), sd):
            st["finestra"], st["nonpass"] = (w.get("turn"), sd), False
        primo = not st["nonpass"]
        if e["action"] and e["action"][0] != "PASS":
            st["nonpass"] = True
        if e["seat"] != camp:
            return
        slim = {"seat": e["seat"], "point": e["point"], "turn": w.get("turn"), "showdown": sd, "menu": e["menu"],
                "action": e["action"], "index": e["index"], "primo": primo}
        if (st["armato"] and k is not None) or (stato is not None and stato(slim)):
            slim["state_raw"] = e["state_raw"]
        eventi.append(slim)
        if st["armato"] and k is not None:
            st["evento"] = slim
            raise _Stop()

    def ask(ev):
        e = json.loads(ev)
        i = n_ask[0]
        if i >= len(P["answers"]):
            raise _Finite()
        kind, answer = P["answers"][i]
        if kind != e["k"]:
            raise ValueError(f"atteso {kind}, chiesto {e['k']} ({i}): la partita non si riproduce")
        n_ask[0] += 1
        return answer

    use = ganci and k is not None
    for s in ("A", "B"):
        if s == umano:
            continue
        mine = s == camp
        g.set_search_agent(s, P["iterazioni"], P["seed"] * 2 + (s == "B"), None, probs, mine,
                           before if (use and mine) else None, (lambda i, n: None) if (use and mine) else None)
        g.set_search_win_probe(s, bool(P["probe"]))
    if umano is not None:
        g.set_human_agent(umano, ask, True, lambda ev: None)
    g.set_side_chooser()
    g.trace_on(watch)
    try:
        g.start()
    except (_Stop, _Finite):
        pass
    righe = [r for r in json.loads(g.search_log(camp)) if r["k"] == "search"]
    return righe, eventi, st["evento"]


def _abbina(righe: list, eventi: list) -> tuple:
    """Per ogni riga di ricerca l'evento di decisione del campione (le decisioni della sonda non hanno riga:
    i turni di azione con scelta senza riga sono `sonde`, come indice della ricerca che le segue)."""
    out, sonde, j = [], [], 0
    for r in righe:
        while j < len(eventi):
            e = eventi[j]
            j += 1
            if e["point"] == r["point"] and e["turn"] == r["turn"] and e["action"] == r["action"] \
                    and len(e["menu"]) == len(r["menu"]):
                out.append(e)
                break
            if e["point"] == "turn_action" and len(e["menu"]) > 1:
                sonde.append(len(out))
        else:
            raise RuntimeError(f"nessun evento per la ricerca {len(out)}: la traccia non coincide col log")
    sonde += [len(righe) for e in eventi[j:] if e["point"] == "turn_action" and len(e["menu"]) > 1]
    return out, sonde


def originale(partita: dict, stato=None) -> list[dict]:
    """La partita originale del campione: una riga per ricerca (k, seat, turn, point, action = etichetta,
    menu = etichette, riga = la riga di search_log, e = l'evento con "primo" ed eventuale state_raw)."""
    P = _prepara(partita)
    key = _chiave(P)
    got = _ORIGINALI.get(key)
    if got is None or (stato is not None and not got.get("_stato")):
        righe, eventi, _ = _gioca(P, None, None, stato)
        ev, sonde = _abbina(righe, eventi)
        got = _ORIGINALI[key] = {"righe": righe, "eventi": ev, "sonde": sonde, "_stato": stato is not None}
    return [{"k": i, "seat": r["seat"], "turn": r["turn"], "point": r["point"],
             "action": e["menu"][e["index"]], "menu": e["menu"], "riga": r, "e": e}
            for i, (r, e) in enumerate(zip(got["righe"], got["eventi"]))]


def sonde(partita: dict) -> list[int]:
    """Gli indici di ricerca davanti a cui il campione ha deciso con la sonda (senza ricerca né riga di log):
    da lì il rifacimento coi ganci (senza sonda) può divergere."""
    originale(partita)
    return list(_ORIGINALI[_chiave(_prepara(partita))]["sonde"])


def elenca(partita: dict) -> list[dict]:
    """Tutte le decisioni cercate del campione nella partita originale: (k, turn, point, action)."""
    return [{"k": o["k"], "turn": o["turn"], "point": o["point"], "action": o["action"], "seat": o["seat"],
             "n_menu": len(o["menu"]), "iterazioni": o["riga"].get("iters")} for o in originale(partita)]


# -- la posizione -------------------------------------------------------------------------------

def riassunto(state_raw: dict, seat: str) -> dict:
    """La posizione vista dal campione `seat`: punti, turno, campi (chi controlla, unità e Might per lato),
    base, mano, energia."""
    from riftbound.core.decisions import Observation
    from riftbound.rs import vista_rs
    gs, _ = vista_rs.carica(state_raw)
    o = Observation.from_state(gs, seat)
    opp = "B" if seat == "A" else "A"

    def lato(units):
        us = [(u.name, u.might) for u in units]
        return {"unita": us, "might": sum(m for _n, m in us)}

    campi = []
    for i, b in enumerate(o.battlefields):
        mine, theirs = (b.A, b.B) if seat == "A" else (b.B, b.A)
        c = "campione" if b.controller == seat else "avversario" if b.controller == opp else None
        campi.append({"campo": i, "nome": b.named, "controlla": c, "campione": lato(mine), "avversario": lato(theirs)})
    return {"seat": seat, "turno": o.turn, "attivo": o.active, "punti": [o.my_points, o.opp_points],
            "energia": [o.my_energy, o.opp_energy], "campi": campi, "base": {"campione": lato(o.my_base_units),
            "avversario": lato(o.opp_base_units)}, "mano": list(o.my_hand), "mano_avv": o.opp_hand_count,
            "showdown": o.showdown_bf}


def testo_posizione(p: dict) -> list[str]:
    def us(l):
        return ", ".join(f"{n} {m}" for n, m in l["unita"]) or "-"
    righe = [f"turno {p['turno']} (attivo {p['attivo']}); punti campione {p['punti'][0]} - avversario {p['punti'][1]}; "
             f"energia {p['energia'][0]}/{p['energia'][1]}"]
    for c in p["campi"]:
        righe.append(f"campo {c['campo']} {c['nome'] or ''} controlla {c['controlla'] or 'nessuno'}: campione "
                     f"{c['campione']['might']} [{us(c['campione'])}] | avversario {c['avversario']['might']} "
                     f"[{us(c['avversario'])}]")
    righe.append(f"base: campione [{us(p['base']['campione'])}] | avversario [{us(p['base']['avversario'])}]")
    righe.append(f"mano del campione: {', '.join(p['mano']) or '-'} (avversario: {p['mano_avv']} carte)")
    return righe


# -- rifare ---------------------------------------------------------------------------------------

def _classifica(riga: dict, menu: list) -> list[dict]:
    """Le azioni del menu con visite, q, P e rango (per visite, a pari visite l'ordine del menu)."""
    ch = {json.dumps(c[0]): c for c in riga["children"]}
    pr = {json.dumps(a): p for a, p in riga["P"]}
    out = []
    for i, a in enumerate(riga["menu"]):
        key = json.dumps(a)
        c = ch.get(key)
        out.append({"i": i, "azione": menu[i] if i < len(menu) else str(a), "n": c[1] if c else 0,
                    "q": c[2] if c and c[1] else None, "P": pr.get(key)})
    ordine = sorted(out, key=lambda x: (-x["n"], x["i"]))
    for r, x in enumerate(ordine, 1):
        x["rango"] = r
    return ordine


def rifai(partita: dict, k: int, iterazioni: int | None = None, posizione: bool = True) -> dict:
    """La ricerca k del campione rifatta con `iterazioni` (None: come l'originale), sulla stessa partita.
    -> {k, turn, point, iterazioni, azione, azione_originale, uguale, riproduce (il prefisso 0..k-1
    coincide con l'originale; con iterazioni None anche l'azione di k), classifica (per visite),
    riga (la riga di search_log), posizione}. Dopo la ricerca k la partita si ferma."""
    orig = originale(partita)
    if not 0 <= k < len(orig):
        raise ValueError(f"k={k} fuori dalle {len(orig)} ricerche del campione")
    P = _prepara(partita)
    righe, _ev, e = _gioca(P, k, iterazioni)
    if e is None or len(righe) <= k:
        raise RuntimeError(f"la ricerca {k} non c'è nella partita rifatta ({len(righe)} ricerche)")
    r = righe[k]
    prefisso = all(righe[i]["action"] == orig[i]["riga"]["action"] and righe[i]["turn"] == orig[i]["turn"]
                   for i in range(k)) and r["turn"] == orig[k]["turn"] and r["point"] == orig[k]["point"]
    azione = e["menu"][e["index"]]
    uguale = r["action"] == orig[k]["riga"]["action"]
    out = {"k": k, "turn": r["turn"], "point": r["point"], "iterazioni": iterazioni,
           "iterazioni_fatte": r.get("iters"), "azione": azione, "azione_originale": orig[k]["action"],
           "uguale": uguale, "prefisso_ok": prefisso, "dopo_sonda": any(k >= x for x in sonde(partita)), "riproduce": prefisso and (uguale if iterazioni is None else None),
           "classifica": _classifica(r, e["menu"]), "riga": r}
    if posizione:
        out["posizione"] = riassunto(e["state_raw"], P["camp"])
    return out


# -- concordanza ----------------------------------------------------------------------------------

def semi(testo: str) -> list[int]:
    """"N" -> 1..N; "A-B" -> A..B."""
    if "-" in testo:
        a, b = testo.split("-")
        return list(range(int(a), int(b) + 1))
    return list(range(1, int(testo) + 1))


def autonoma(matchup: str, seed: int, ckpt: str | None = None, casuali: bool = False, iterazioni: int = ITERAZIONI_CAMPIONE,
             campione: str = "A", **extra) -> dict:
    """La partita autonoma del campione contro sé stesso (lo starter alterna col seme, come l'arena)."""
    return {"tipo": "autonoma", "matchup": matchup, "seed": seed, "starter": "a" if seed % 2 == 0 else "b",
            "iterazioni": iterazioni, "probe": True, "ckpt": ckpt, "casuali": casuali, "campione": campione, **extra}


def concordanza(matchup: str, seme_lista: list[int], iterazioni: int, per_tipo: int = 20, ckpt: str | None = None,
                casuali: bool = False, iter_orig: int = ITERAZIONI_CAMPIONE, campione: str = "A", rng_seed: int = 0,
                avanzamento=None, **extra) -> dict:
    """Su un campione di decisioni del campione per tipo di punto (turno / reazione / showdown, solo con più di
    una mossa nel menu) rifà la decisione a `iterazioni` e conta in quante la mossa è uguale all'originale
    (a `iter_orig`, con la sonda). Le decisioni il cui prefisso non si riproduce sono escluse e contate.
    -> {tipo: {decisioni, uguali, escluse, pct}}, con `dettagli` (seed, k, originale, rifatta)."""
    cand: dict = {t: [] for t in TIPI.values()}
    partite = {}
    for seed in seme_lista:
        P = autonoma(matchup, seed, ckpt, casuali, iter_orig, campione, **extra)
        partite[seed] = P
        for o in originale(P):
            if len(o["menu"]) > 1:
                cand[TIPI[o["point"]]].append((seed, o["k"]))
    rng = random.Random(rng_seed)
    out: dict = {}
    for tipo, lista in cand.items():
        scelte = sorted(rng.sample(lista, min(per_tipo, len(lista))))
        n = uguali = escluse = 0
        det = []
        for seed, k in scelte:
            r = rifai(partite[seed], k, iterazioni, posizione=False)
            if avanzamento:
                avanzamento(tipo, seed, k)
            det.append({"seed": seed, "k": k, "turn": r["turn"], "originale": r["azione_originale"],
                        "rifatta": r["azione"], "prefisso_ok": r["prefisso_ok"]})
            if not r["prefisso_ok"]:
                escluse += 1
                continue
            n += 1
            uguali += r["uguale"]
        out[tipo] = {"disponibili": len(lista), "decisioni": n, "uguali": uguali, "escluse": escluse,
                     "pct": (100.0 * uguali / n) if n else None, "dettagli": det}
    return out
