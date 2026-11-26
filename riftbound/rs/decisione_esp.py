"""Esperimenti su una posizione del campione (scripts/rust/decisione.py: incrocio, guidata, continua).

`incrocio`: alla ricerca k, 4 condizioni (finestre spente/accese x quota spenta/accesa) con gli stessi semi
    (stessi mondi nascosti per simulazione) e le stesse iterazioni; per mossa confrontata visite, q, rango, giocate
    dei piloti nelle finestre per posto.
`guidata`: dalla posizione k il posto del campione e' forzato attraverso una sequenza di etichette (azioni di turno,
    finestre, scelte); fino alla fine di quel turno.
`continua`: dalla posizione k, per ogni prima mossa, n continuazioni fino alla fine della partita (mondi diversi:
    i mazzi, di cui nessuno dei due conosce l'ordine, sono rimescolati; tutto il resto dello stato resta com'e').

La posizione di partenza e' lo stato (state_raw) dell'evento di decisione k della partita originale, caricato in un
Game nuovo (`Game.from_canonical`, come le posizioni dei test): la ricerca del campione riparte senza i "piani" che
aveva in memoria dai turni precedenti (Layer::Plan), e il generatore del motore riparte da un seme nuovo.
"""
from __future__ import annotations

import copy
import json
import math
import random
import time

from riftbound.rs import decisione_rs as D

MAX_GIRI = 200          # tetto di turni nelle continuazioni (la partita finisce prima: max_turns dello stato)


class Stop(Exception):
    """Fine voluta della partita (sequenza non legale)."""


# -- posizione di partenza ------------------------------------------------------------------------

def posizione(partita: dict, k: int):
    """(P preparata, evento di k con `state_raw`, `menu`, `point`, `turn`): la posizione della decisione k del campione."""
    orig = D.originale(partita)
    if not 0 <= k < len(orig):
        raise ValueError(f"k={k} fuori dalle {len(orig)} ricerche del campione")
    P = D._prepara(partita)
    _righe, _ev, e = D._gioca(P, k, None, ordine=D._ORIGINALI[D._chiave(P)]["pos"][k])
    if e is None or e.get("state_raw") is None:
        raise RuntimeError(f"la posizione {k} non c'è nella partita rifatta")
    return P, e


def albero(state_raw: dict) -> dict:
    from riftbound.rs.canon import Canon
    return Canon().canonical(state_raw)


def rimescola(tree: dict, seme: int) -> dict:
    """Una copia dell'albero col mazzo e il mazzo delle rune dei due posti rimescolati (con `seme`)."""
    t = copy.deepcopy(tree)
    rng = random.Random(seme)
    for s in ("A", "B"):
        pl = t["root"][s]["$v"]
        rng.shuffle(pl["deck"]["$v"]["cards"])
        rng.shuffle(pl["rune_deck"]["$v"]["runes"])
    return t


def gioco(P: dict, tree: dict, seme: int):
    import riftbound_rs
    from riftbound.rs import rust_bridge
    return riftbound_rs.Game.from_canonical(rust_bridge.registry(P["regole"]), json.dumps(tree), seme)


def _agente_campione(g, P: dict, seat: str, seme: int, primo: str | None = None) -> None:
    """Il posto `seat` gioca come il campione della partita (iterazioni, rete, sonda, valutazione); `primo`: la sua
    prima mossa di turno e' la prima legale la cui etichetta contiene `primo`."""
    g.set_search_agent(seat, P["iterazioni"], seme, None, D.rete(P["ckpt"], P["casuali"]), False)
    g.set_search_win_probe(seat, bool(P["probe"]))
    if P.get("valutazione") and P["valutazione"][0] != "storica":
        v = P["valutazione"]
        g.set_search_valutazione(seat, v[0], float(v[1]), float(v[2]))
    if primo:
        g.set_search_first_move(seat, primo)


def _punti(raw: dict) -> tuple[int, int]:
    r = raw["root"]
    return int(r["points_A"]), int(r["points_B"])


# -- incrocio -------------------------------------------------------------------------------------

CONDIZIONI = [(False, False), (True, False), (False, True), (True, True)]


def _f(x) -> str:
    return "-" if x is None else f"{x:.2f}"


def _nome_cond(c) -> str:
    return f"finestre {'on ' if c[0] else 'off'} quota {'on ' if c[1] else 'off'}"


def _riga_mossa(r: dict, sub: str, conta: list) -> dict:
    """Visite, q (media pesata), rango migliore, e giocate dei piloti per posto delle voci del menu che contengono `sub`."""
    voci = [x for x in r["classifica"] if sub.casefold() in x["azione"].casefold()]
    n = sum(x["n"] for x in voci)
    q = sum(x["n"] * x["q"] for x in voci if x["q"] is not None) / n if n else None
    out = {"voci": [x["azione"] for x in voci], "n": n, "q": q, "rango": min((x["rango"] for x in voci), default=None),
           "tot": len(r["classifica"]), "conta": None}
    d = r.get("diagnosi")
    if d and d["finestre"]:
        etichette = {x["azione"] for x in voci}
        tab = {c: {"A": 0, "B": 0} for c in conta}
        for ch in d["children"]:
            if ch["label"] not in etichette:
                continue
            for seat, _punto, et, cnt in ch["tally"]:
                for c in conta:
                    if c.casefold() in et.casefold():
                        tab[c][seat] += cnt
        out["conta"] = tab
    return out


def incrocio(partita: dict, k: int, iterazioni: list, mosse: list, conta: list, quota_n: int = 100,
             avanzamento=None) -> list:
    """-> per ogni valore di `iterazioni`: {n, semi_uguali, prefisso_ok, righe: [{cond, scelta, mosse: [..]}]}."""
    out = []
    for n in iterazioni:
        rr = {}
        for c in CONDIZIONI:
            rr[c] = D.rifai(partita, k, n, posizione=False, finestre=c[0],
                            quota=(list(mosse), quota_n) if c[1] else None, semi=True)
            if avanzamento:
                avanzamento(n, c)
        seeds = [rr[c]["diagnosi"]["seeds"] for c in CONDIZIONI]
        out.append({"n": n, "semi_uguali": all(s == seeds[0] for s in seeds) and len(seeds[0]) > 0,
                    "n_semi": len(seeds[0]), "prefisso_ok": all(r["prefisso_ok"] for r in rr.values()),
                    "righe": [{"cond": c, "scelta": rr[c]["azione"],
                               "mosse": [_riga_mossa(rr[c], m, conta) for m in mosse]} for c in CONDIZIONI]})
    return out


def testo_incrocio(res: list, mosse: list, conta: list, k: int, quota_n: int) -> list[str]:
    righe = []
    for blocco in res:
        righe.append(f"N={blocco['n']} (k={k}, quota {quota_n}); stessi semi nelle 4 condizioni: "
                     f"{'sì' if blocco['semi_uguali'] else 'NO'} ({blocco['n_semi']} simulazioni); prefisso riprodotto: "
                     f"{'sì' if blocco['prefisso_ok'] else 'NO'}")
        for m in mosse:
            voci = next(r["mosse"][mosse.index(m)]["voci"] for r in blocco["righe"])
            righe.append(f"  mossa '{m}': " + (" | ".join(voci) if voci else "NON NEL MENU"))
        celle = []
        for r in blocco["righe"]:
            cs = []
            for m in r["mosse"]:
                if m["n"] == 0 and not m["voci"]:
                    cs.append("assente dal menu")
                    continue
                t = f"n={m['n']} q={_f(m['q'])} r{m['rango']}/{m['tot']}"
                if m["conta"] is not None:
                    t += " " + " ".join(f"{c[:12]} A{v['A']}/B{v['B']}" for c, v in m["conta"].items())
                cs.append(t)
            celle.append([_nome_cond(r["cond"]), r["scelta"][:30]] + cs)
        testa = ["condizione", "scelta"] + list(mosse)
        larg = [max(len(testa[i]), *(len(c[i]) for c in celle)) for i in range(len(testa))]
        righe.append("  " + " | ".join(t.ljust(w) for t, w in zip(testa, larg)))
        for c in celle:
            righe.append("  " + " | ".join(t.ljust(w) for t, w in zip(c, larg)))
        righe.append("")
    return righe


# -- guidata --------------------------------------------------------------------------------------

def _nome_carta(raw_val) -> str:
    try:
        objs, v = raw_val["objs"], raw_val["root"]["o"]
        o = objs[v["$ref"]] if isinstance(v, dict) and "$ref" in v else v
        return str(o.get("name", ""))
    except Exception:
        return ""


def etichette_scelta(e: dict) -> list[str]:
    """Le opzioni di una scelta in testo: "<tipo>: <opzione>" (unita' con proprietario, Might e posto)."""
    from riftbound.ai.coach_rs import RustGame
    from riftbound.rs import vista_rs
    gs, objs = vista_rs.carica(e["state_raw"])
    out = []
    for o in e["options_raw"]:
        v = vista_rs.valore(o, objs)
        try:
            t = ("sì" if v else "no") if isinstance(v, bool) else RustGame._en(gs, v)
        except Exception:
            t = str(v)
        out.append(f"{e['kind']}: {t}")
    return out


def riga_tavolo(p: dict) -> str:
    """Una riga: turno, punti, energia/potenza, unita' (Might) per campo e base."""
    def us(l):
        return ",".join(f"{n} {m}" for n, m in l["unita"]) or "-"
    pot = [",".join(f"{d[:3].lower()}{n}" for d, n in x.items() if n) or "-" for x in p["potenza"]]
    campi = " ".join(f"BF{c['campo']}[{(c['controlla'] or 'nessuno')[:4]}: {us(c['campione'])} / {us(c['avversario'])}]"
                     for c in p["campi"])
    return (f"T{p['turno']} punti {p['punti'][0]}-{p['punti'][1]} en {p['energia'][0]}/{p['energia'][1]} "
            f"pot {pot[0]}/{pot[1]} {campi} base[{us(p['base']['campione'])} / {us(p['base']['avversario'])}]")


class Guida:
    """Il callback `ask` del posto forzato (Game.set_human_agent). Regole: vedi `cerca`."""

    def __init__(self, sequenza: list, seat: str, out):
        self.seq = list(sequenza)
        self.seat = seat
        self.out = out                    # funzione di stampa
        self.i = 0                        # prossima etichetta
        self.attesa = None                # (n, descrizione) del passo fatto, in attesa dello stato dopo di lui
        self.default = 0                  # scelte lasciate al motore
        self.finito = False
        self.non_legale = None

    def _tavolo(self, raw) -> str:
        return riga_tavolo(D.riassunto(raw, self.seat))

    def _chiudi_attesa(self, raw) -> None:
        if self.attesa is not None and raw is not None:
            self.out(f"  {self.attesa[0]}. {self.attesa[1]}\n       => {self._tavolo(raw)}")
            self.attesa = None

    @staticmethod
    def cerca(label: str, opzioni: list[str]):
        """Indice dell'opzione: uguale (senza maiuscole) o, se no, la prima che contiene l'etichetta; None."""
        l = label.casefold()
        for i, o in enumerate(opzioni):
            if o.casefold() == l:
                return i
        for i, o in enumerate(opzioni):
            if l in o.casefold():
                return i
        return None

    def passo(self, desc: str) -> None:
        self.i += 1
        self.attesa = (self.i, desc)

    def ask(self, ev: str):
        e = json.loads(ev)
        k = e["k"]
        raw = e.get("state_raw")
        self._chiudi_attesa(raw)
        lab = self.seq[self.i] if self.i < len(self.seq) else None
        if k == "decision":
            menu, punto = e["menu"], e["point"]
            pas = next((j for j, m in enumerate(menu) if m.casefold().startswith("pass")), 0)
            if lab is None:
                if not self.finito:
                    self.finito = True
                    self.out(f"  (sequenza finita al punto '{punto}': da qui si passa)")
                return pas
            j = self.cerca(lab, menu)
            if j is not None:
                self.passo(f"[{punto}] {menu[j]}")
                return j
            if punto == "turn_action":
                self.non_legale = (lab, punto, menu)
                self.out(f"  {self.i + 1}. NON LEGALE: '{lab}' non è nel menu di '{punto}' (turno "
                         f"{(e.get('win') or {}).get('turn')}). Menu: {menu}")
                if raw is not None:
                    self.out(f"       posizione: {self._tavolo(raw)}")
                raise Stop()
            return pas                                    # finestra non voluta dalla sequenza: passo
        if k == "choice":
            opz = etichette_scelta(e) if len(e["options_raw"]) > 1 else []
            if lab is not None and opz:
                j = self.cerca(lab, opz)
                if j is not None:
                    self.passo(f"[scelta] {opz[j]}")
                    return j
            self.default += 1
            return e["default"]
        if k == "decide_optional":
            nome = _nome_carta(e["args"][0]) if e.get("args") else ""
            tipo = e["args"][1] if len(e.get("args", [])) > 1 and isinstance(e["args"][1], str) else "optional"
            for val in (True, False):
                t = f"{tipo}: {'sì yes' if val else 'no'} ({nome})"
                if lab is not None and lab.casefold() in t.casefold():
                    self.passo(f"[opzionale] {t}")
                    return val
            return True
        if k == "decide_mode":
            n = e["args"][1] if len(e.get("args", [])) > 1 else 0
            nome = _nome_carta(e["args"][0]) if e.get("args") else ""
            if lab is not None and isinstance(n, int):
                for j in range(n):
                    t = f"mode {nome} #{j}"
                    if lab.casefold() in t.casefold():
                        self.passo(f"[modo] {t}")
                        return j
            return None
        if k == "decide_predict_recycle":
            return False
        if k == "decide_mulligan":
            return []
        raise ValueError(f"domanda sconosciuta: {k}")


def guidata(partita: dict, k: int, sequenza: list, avversario: str = "passa", out=print) -> dict:
    """Forza il posto del campione dalla posizione k lungo `sequenza`, fino alla fine del suo turno.
    -> {finale: riassunto, punti, non_legale, passi, default}."""
    P, e = posizione(partita, k)
    if e["point"] != "turn_action":
        raise ValueError(f"k={k} non è una decisione di turno ({e['point']}): serve il primo punto di un turno")
    camp = P["camp"]
    opp = "B" if camp == "A" else "A"
    out(f"posizione k={k}, turno {e['turn']}, posto {camp}: {D.riassunto(e['state_raw'], camp)['punti']} punti; "
        f"avversario: {avversario}")
    out("  " + riga_tavolo(D.riassunto(e["state_raw"], camp)))
    g = gioco(P, albero(e["state_raw"]), P["seed"])
    if avversario == "campione":
        _agente_campione(g, P, opp, P["seed"] * 2 + (opp == "B"))
    else:
        g.set_script(opp)
    guida = Guida(sequenza, camp, out)
    g.set_human_agent(camp, guida.ask, False, None)
    g.set_side_chooser()
    try:
        g.run_actions_end()
    except Stop:
        pass
    raw = json.loads(g.raw_dump())
    guida._chiudi_attesa(raw)
    fin = D.riassunto(raw, camp)
    out("fine del turno" if guida.non_legale is None else "fermo (sequenza non legale)")
    out("  " + riga_tavolo(fin))
    out(f"  punti: campione ({camp}) {fin['punti'][0]} - avversario {fin['punti'][1]}; passi forzati {guida.i}/"
        f"{len(sequenza)}; scelte lasciate al motore {guida.default}")
    if guida.i < len(sequenza) and guida.non_legale is None:
        out(f"  ATTENZIONE: etichette mai trovate (il turno è finito): {sequenza[guida.i:]}")
    return {"finale": fin, "punti": fin["punti"], "non_legale": guida.non_legale, "passi": guida.i,
            "default": guida.default}


# -- continua -------------------------------------------------------------------------------------

def wilson(x: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """(p, basso, alto) dell'intervallo di Wilson al 95%."""
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def differenza(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float, float]:
    """p1 - p2 con l'intervallo 95% di Newcombe (dagli intervalli di Wilson)."""
    p1, l1, u1 = wilson(x1, n1)
    p2, l2, u2 = wilson(x2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def un_mondo(P: dict, tree: dict, mossa: str, i: int, base_seme: int) -> dict:
    """Una continuazione: mondo `i` (mazzi rimescolati col seme base+i), il posto del campione gioca `mossa` e poi
    come il campione; entrambi i posti campione (finestre spente). -> {vince, punti_turno, punti_fine, turni, secondi}."""
    t0 = time.time()
    seme = base_seme + i
    camp = P["camp"]
    g = gioco(P, rimescola(tree, seme), seme)
    for s in ("A", "B"):
        _agente_campione(g, P, s, seme * 2 + (s == "B") + 1_000_003, mossa if s == camp else None)
    g.set_side_chooser()
    w = g.run_actions_end()
    stato = json.loads(g.raw_dump())
    pt = _punti(stato)
    max_t = int(stato["root"]["max_turns"])
    giri = 0
    while w is None and giri < MAX_GIRI:
        if g.turn > max_t:  # come play_all_turns: oltre il tetto di turni la partita è patta
            w = "DRAW"
            break
        w = g.run_begin()
        if w is None:
            w = g.run_actions_end()
        giri += 1
    fin = _punti(json.loads(g.raw_dump()))
    return {"vince": w, "punti_turno": pt, "punti_fine": fin, "turni": g.turn, "secondi": time.time() - t0, "mondo": i}


def _lavora(args):
    P, tree, mossa, i, base = args
    return args[3], mossa, un_mondo(P, tree, mossa, i, base)


def continua(partita: dict, k: int, mosse: list, n: int = 100, processi: int = 1, out=print) -> dict:
    """Per ogni mossa (sottostringa dell'etichetta nel menu di k) n continuazioni. Gli stessi n mondi per ogni mossa."""
    P, e = posizione(partita, k)
    if e["point"] != "turn_action":
        raise ValueError(f"k={k} non è una decisione di turno ({e['point']})")
    camp = P["camp"]
    tree = albero(e["state_raw"])
    base = P["seed"] * 100_003 + k * 1_009
    scelte = {}
    for m in mosse:
        j = Guida.cerca(m, e["menu"])
        if j is None:
            raise ValueError(f"mossa '{m}' non nel menu di k={k}: {e['menu']}")
        simili = [x for x in e["menu"] if m.casefold() in x.casefold()]
        scelte[m] = e["menu"][j]
        out(f"mossa '{m}' -> '{e['menu'][j]}'" + (f" (altre {len(simili) - 1} voci la contengono: {simili[:4]})"
                                                    if len(simili) > 1 and e["menu"][j].casefold() != m.casefold() else ""))
    lavori = [(P, tree, scelte[m], i, base) for i in range(n) for m in mosse]
    ris = {m: [] for m in mosse}
    inv = {scelte[m]: m for m in mosse}
    t0 = time.time()

    def prog(done):
        if done % (10 * len(mosse)) == 0 or done == len(lavori):
            out(f"  {done // len(mosse)}/{n} mondi (x{len(mosse)} mosse), {time.time() - t0:.0f} s")
    if processi > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(processi) as pool:
            for done, (_i, mossa, r) in enumerate(pool.imap_unordered(_lavora, lavori), 1):
                ris[inv[mossa]].append(r)
                prog(done)
    else:
        for done, a in enumerate(lavori, 1):
            _i, mossa, r = _lavora(a)
            ris[inv[mossa]].append(r)
            prog(done)
    opp = "B" if camp == "A" else "A"

    def pt(r, key, seat):
        return r[key][0 if seat == "A" else 1]
    rep = {}
    for m in mosse:
        rs = ris[m]
        v = sum(1 for r in rs if r["vince"] == camp)
        rep[m] = {"mossa": scelte[m], "n": len(rs), "vittorie": v, "patte": sum(1 for r in rs if r["vince"] == "DRAW"),
                  "non_finite": sum(1 for r in rs if r["vince"] is None),
                  "punti_turno": [sum(pt(r, "punti_turno", camp) for r in rs) / len(rs),
                                  sum(pt(r, "punti_turno", opp) for r in rs) / len(rs)],
                  "punti_fine": [sum(pt(r, "punti_fine", camp) for r in rs) / len(rs),
                                 sum(pt(r, "punti_fine", opp) for r in rs) / len(rs)],
                  "turni": sum(r["turni"] for r in rs) / len(rs), "secondi": sum(r["secondi"] for r in rs) / len(rs)}
    return {"partita": camp, "k": k, "turno": e["turn"], "base_seme": base, "n": n, "mosse": rep,
            "punti_iniziali": D.riassunto(e["state_raw"], camp)["punti"], "secondi": time.time() - t0}


def testo_continua(res: dict) -> list[str]:
    camp = res["partita"]
    righe = [f"continuazioni da k={res['k']} (turno {res['turno']}), campione = posto {camp}, n={res['n']} mondi per mossa "
             f"(stessi mondi per tutte le mosse, mazzi rimescolati, seme di base {res['base_seme']}); "
             f"punti all'inizio: campione {res['punti_iniziali'][0]} - avversario {res['punti_iniziali'][1]}; "
             f"{res['secondi']:.0f} s"]
    mosse = res["mosse"]
    migliore = max(mosse, key=lambda m: mosse[m]["vittorie"] / max(1, mosse[m]["n"]))
    for m, r in mosse.items():
        p, lo, hi = wilson(r["vittorie"], r["n"])
        righe.append(f"- {r['mossa']}: vittorie {r['vittorie']}/{r['n']} = {100 * p:.0f}% [{100 * lo:.0f}-{100 * hi:.0f}]; "
                     f"punti a fine turno campione {r['punti_turno'][0]:.2f} avversario {r['punti_turno'][1]:.2f}; "
                     f"a fine partita {r['punti_fine'][0]:.2f} / {r['punti_fine'][1]:.2f}; durata media {r['turni']:.1f} turni"
                     + (f"; patte {r['patte']}" if r["patte"] else "") + (f"; non finite {r['non_finite']}" if r["non_finite"] else "")
                     + f"; {r['secondi']:.0f} s a partita")
    b = mosse[migliore]
    righe.append(f"differenza rispetto alla migliore ({b['mossa']}), punti percentuali, intervallo 95% (Newcombe):")
    for m, r in mosse.items():
        if m == migliore:
            continue
        d, lo, hi = differenza(r["vittorie"], r["n"], b["vittorie"], b["n"])
        righe.append(f"- {r['mossa']}: {100 * d:+.0f} [{100 * lo:+.0f}, {100 * hi:+.0f}]")
    return righe
