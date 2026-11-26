"""Attacco: confronto fra il riferimento del campione e linee di attacco proposte, in una posizione qualunque.

Porting generale del prototipo di Astra sul T9 (docs/bot/esperimenti/t9_attacco/sorgenti: ev.py, proposte.py,
selezione.py, bersagli.py, misure.py), scritto per una sola posizione (partita 013325, k=10, Sett = posto B, campo BF0).
Qui la posizione e' una decisione `turn_action` k del campione di qualunque partita (`pagina` o `autonoma` di
`decisione_rs`); il posto del campione e' `P["camp"]`. Il protocollo dei semi e' quello di Astra.

Pezzi:
  `posizione(partita, k)`   la posizione (P, albero, menu, seme base = P["seed"]*100_003 + k*1_009, come Astra a k=10).
  `mondo(pos, modo, seme)`  un mondo: `fisse` (mazzi rimescolati) o `ignote` (le carte che il campione non vede,
                            mano dell'avversario e mazzi, ridistribuite con `determinize` dal suo punto di vista).
  `continua(...)`           una continuazione dal mondo fino alla fine della partita, per una linea: `campione`
                            (riferimento nuovo: nessun controllo forzato), una sequenza di etichette di turno
                            (il `Turn` non-attacco di ev.py) o una proposta di attacco (`Attack` + `Branch`).
  `genera(pos)`             le proposte (griglia di Astra per ogni campo dell'avversario con unita'), con eventi e
                            tavolo di fine turno nel mondo di riferimento; deduplica degli eventi uguali.
  `confronta(...)`          proposte, selezione sui mondi di scelta, verifica sui mondi tenuti da parte, vista del
                            campione a k, esito della posizione (esito.json, esito.txt).
  `posizioni(partita)`      le posizioni candidate di una partita (primo `turn_action` utile di ogni turno).
  `serie(...)`              `confronta` per ogni posizione di un elenco e un riepilogo.
  `rivedi(...)`             verifiche in piu' (sonde della valutazione, migliore per vittorie, ricerca con finestre e
                            quota) su una serie gia' fatta.
  `riproduci_t9(...)`       rifa la prova di Astra e la confronta riga per riga con i suoi dati.

Valutazione del campione (`Game.valuta`, lettura pura): a fine turno e a fine turno dell'avversario, per la
valutazione storica e per quella della partita (`P["valutazione"]`), nel campo `valori` di ogni riga.
"""
from __future__ import annotations

import copy
import json
import multiprocessing
import random
import re
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from itertools import product
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

from riftbound.rs import decisione_esp as E, decisione_rs as D

NOME_RIF = "riferimento"
SCELTA = (2000, 16)      # mondi di scelta: (inizio, quanti), come Astra
VERIFICA = (4000, 100)   # mondi tenuti da parte: (inizio, quanti), come Astra
T9_REPLAY = "docs/bot/partite/coach/20261126_013325_competitive_evelynn_vs_competitive_sett.json"
T9_RIFERIMENTO = "Play Vi Peacekeeper ; Move Sett Kingpin base→BF1 ; Pass"


# -- la posizione ---------------------------------------------------------------------------------

def posizione(partita: dict, k: int) -> dict:
    """La posizione della decisione k del campione (deve essere `turn_action`): P, albero, menu, turno, seme base."""
    P, e = E.posizione(partita, k)
    if e["point"] != "turn_action":
        raise ValueError(f"k={k} non è una decisione di turno ({e['point']})")
    return {"partita": partita, "P": P, "k": k, "tree": E.albero(e["state_raw"]), "menu": e["menu"],
            "turno": e["turn"], "base": P["seed"] * 100_003 + k * 1_009}


def _altro(seat: str) -> str:
    return "B" if seat == "A" else "A"


# -- i mondi --------------------------------------------------------------------------------------

def _note_in_cima(deck: dict) -> int:
    """Quante carte in cima al mazzo (canonico; cima = fine della lista) il proprietario conosce: `Deck.known_on_top`."""
    cards, n = deck["cards"], 0
    for card in deck["known_top"]:
        if card not in cards:
            continue
        if n < len(cards) and cards[len(cards) - 1 - n] == card:
            n += 1
        else:
            break
    return n


def mondo(pos: dict, modo: str, seme: int) -> dict:
    """L'albero di un mondo. `fisse`: i mazzi (carte e rune non ancora viste) rimescolati; `ignote`: le carte che il
    campione non vede (mano dell'avversario, mazzi, carte coperte dell'avversario) ridistribuite con `determinize`."""
    from riftbound.core.state import determinize
    from riftbound.rs import vista_rs
    from riftbound.rs.canon import Canon
    P, root = pos["P"], pos["tree"]
    camp = P["camp"]
    rng = random.Random(seme)
    if modo == "fisse":
        state = copy.deepcopy(root)
        for side in ("A", "B"):
            pl = state["root"][side]["$v"]
            deck = pl["deck"]["$v"]
            k = _note_in_cima(deck)
            if k:
                # le carte in cima note al proprietario (PREDICT) restano dove sono; si rimescola il resto
                sotto = deck["cards"][:len(deck["cards"]) - k]
                rng.shuffle(sotto)
                deck["cards"][:len(sotto)] = sotto
            else:
                rng.shuffle(deck["cards"])
            rd = pl["rune_deck"]["$v"]
            n = rd["unseen"] if rd["unseen"] is not None else len(rd["runes"])
            first = rd["runes"][:n]
            rng.shuffle(first)
            rd["runes"][:n] = first
        return state
    if modo != "ignote":
        raise ValueError(f"modo sconosciuto: {modo}")
    original_raw = json.loads(E.gioco(P, root, 0).raw_dump())
    c = Canon()
    state = c.canonical(original_raw)
    gs, objects = vista_rs.carica(original_raw)
    to_ref = {id(obj): "#" + c.ids[rid] for rid, obj in objects.items() if rid in c.ids}
    runes = {}
    original_cards = {}
    for side, pl in (("A", gs.A), ("B", gs.B)):
        player = state["root"][side]["$v"]
        runes[side] = {id(r): x for r, x in zip(pl.rune_deck.runes, player["rune_deck"]["$v"]["runes"])}
        slots = [fd.card for bf in gs.battlefields for fd in bf.facedowns if fd.owner == side]
        original_cards[side] = sorted(to_ref[id(o)] for o in pl.hand + pl.deck.cards + slots)
    before = [(fd.owner, fd.turn_hidden) for b in gs.battlefields for fd in b.facedowns]

    def mano_camp():
        return [to_ref[id(x)] for x in getattr(gs, camp).hand]
    fixed = mano_camp()
    determinize(gs, camp, rng)
    assert before == [(fd.owner, fd.turn_hidden) for b in gs.battlefields for fd in b.facedowns]
    assert fixed == mano_camp()
    for side, pl in (("A", gs.A), ("B", gs.B)):
        player = state["root"][side]["$v"]
        player["hand"] = [to_ref[id(x)] for x in pl.hand]
        player["deck"]["$v"]["cards"] = [to_ref[id(x)] for x in pl.deck.cards]
        player["rune_deck"]["$v"]["runes"] = [runes[side][id(r)] for r in pl.rune_deck.runes]
        # come le lascia `determinize`: la cima nota del campione resta, quella dell'avversario (mazzo rimescolato)
        # si azzera; le carte di mano note restano nel loro posto
        player["deck"]["$v"]["known_top"] = [to_ref[id(x)] for x in pl.deck.known_top]
        player["hand_public"] = [to_ref[id(x)] for x in pl.hand_public]
        slots = [fd.card for bf in gs.battlefields for fd in bf.facedowns if fd.owner == side]
        assert original_cards[side] == sorted(to_ref[id(o)] for o in pl.hand + pl.deck.cards + slots)
    opp = _altro(camp)
    for i, bf in enumerate(gs.battlefields):
        for fd, dest in zip(bf.facedowns, state["objs"]["bf" + str(i)]["facedowns"]):
            if fd.owner == opp:
                assert fd.card.has_keyword("HIDDEN")
                dest["$v"]["card"] = to_ref[id(fd.card)]
    return state


# -- il controllo dei turni -------------------------------------------------------------------------

class PosizioneNonAdatta(ValueError):
    """La posizione ha informazione nascosta nota (carta in cima al mazzo vista, mano pubblica): `ignote` e `fisse`
    non la sanno ricostruire."""


class Release(Exception):
    """Il controllo restituisce la posizione al campione (protocollo di consegna del progetto)."""


class Sequenza:
    """Il posto del campione segue una sequenza fissa di etichette di turno (il ramo non-attacco di `Turn` di ev.py);
    altrove passa (la prima voce "Pass", se no la prima). Esaurita la sequenza rilascia (prefisso completo);
    un'etichetta assente dal menu rilascia con prefisso incompleto."""

    def __init__(self, etichette: list[str]):
        self.seq = list(etichette)
        self.stage = 0
        self.resumed = None
        self.complete = False
        self.reason = None

    def release(self, e, done, why=None):
        self.resumed = e["state_raw"]
        self.complete = done
        self.reason = why
        raise Release()

    def ask(self, event):
        e = json.loads(event)
        if e["k"] == "decision":
            m = e["menu"]
            idx = next((i for i, z in enumerate(m) if z.startswith("Pass")), 0)
            if e["point"] == "turn_action":
                if self.stage == len(self.seq):
                    self.release(e, True)
                label = self.seq[self.stage]
                if label not in m:
                    self.release(e, False, label)
                self.stage += 1
                return m.index(label)
            return idx
        if e["k"] == "choice":
            return e["default"]
        if e["k"] == "decide_optional":
            return True
        if e["k"] == "decide_mode":
            return None
        if e["k"] == "decide_mulligan":
            return []
        if e["k"] == "decide_predict_recycle":
            return False
        raise ValueError(e["k"])


# -- le proposte ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Proposal:
    gear_target: str
    waves: int
    spell_wave: int
    ambush_index: int


def griglia():
    """La griglia di Astra: gear none/weak/strong x ondate 1/2 x ondata della magia x indice ambush 0/1 (18)."""
    for gear, waves, ambush in product(("none", "weak", "strong"), (1, 2), (0, 1)):
        for wave in range(1, waves + 1):
            yield Proposal(gear, waves, wave, ambush)


def indexed(menu, predicate):
    # Le copie legalmente identiche delle carte sono intercambiabili: una sola per etichetta (la prima).
    distinct = {}
    for i, entry in enumerate(menu):
        if predicate(entry):
            distinct.setdefault(entry, i)
    return list(distinct.items())


class Attack:
    """La politica di attacco di Astra (proposte.py): gear, una o due ondate, magia, riserva Ambush; `field` e' l'indice
    del campo bersaglio. Alla seconda ondata registra i nemici sul campo bersaglio (`nemici_seconda`, bersagli.py)."""

    def __init__(self, proposal, seat, field):
        self.p = proposal
        self.seat = seat
        self.field = field
        self.prepared = False
        self.wave = 0
        self.declaring = False
        self.used_spell = False
        self.used_ambush = False
        self.events = []
        self.nemici_seconda = None

    def act(self, event):
        e = json.loads(event)
        kind = e["k"]
        if kind == "decision":
            menu = e["menu"]
            i = self.decision(e, menu)
            if menu[i] != "Pass":
                self.events.append([self.wave, e["point"], menu[i]])
            return i
        if kind == "choice":
            i = self.choice(e)
            self.events.append([self.wave, e["kind"], E.etichette_scelta(e)[i]])
            return i
        return {"decide_optional": True, "decide_mulligan": [],
                "decide_predict_recycle": False, "decide_mode": None}[kind]

    def decision(self, e, menu):
        skip = next(i for i, label in enumerate(menu) if label.startswith("Pass"))
        field = f"BF{self.field}"
        if e["point"] == "turn_action":
            if not self.prepared:
                self.prepared = True
                gear = indexed(menu, lambda s: s.startswith("Play gear ") and s.endswith("@" + field))
                if self.p.gear_target != "none" and gear:
                    return gear[0][1]
            moves = indexed(menu, lambda s: s.startswith("Move ") and s.endswith(" base→" + field))
            if self.declaring:
                if self.p.waves == 1 and moves:
                    return moves[0][1]
                self.declaring = False
                return skip
            if self.wave < self.p.waves and moves:
                view = D.riassunto(e["state_raw"], self.seat)
                force = dict(view["base"]["campione"]["unita"])
                self.wave += 1
                self.declaring = True
                if self.wave == 2:
                    self.nemici_seconda = [u for u, _m in view["campi"][self.field]["avversario"]["unita"]]
                return min(moves, key=lambda item: force[item[0][5:].rsplit(" base→", 1)[0]])[1]
            return skip
        if e["point"] == "showdown_action" and self.wave > 0:
            if self.wave == self.p.waves and not self.used_ambush:
                ambush = indexed(menu, lambda s: s.startswith("AMBUSH ") and s.endswith("@" + field))
                if ambush:
                    self.used_ambush = True
                    return ambush[min(self.p.ambush_index, len(ambush) - 1)][1]
            if self.wave == self.p.spell_wave and not self.used_spell:
                spells = indexed(menu, lambda s: s.startswith("Showdown ") and s.endswith("@" + field))
                if spells:
                    self.used_spell = True
                    return spells[0][1]
        return skip

    def choice(self, e):
        k = e["kind"]
        labels = E.etichette_scelta(e)

        def subjects(seat):
            out = []
            for i, s in enumerate(labels):
                m = re.search(r"\(([AB]), Might (\d+), (.+)\)$", s)
                if m and m.group(1) == seat:
                    out.append((int(m.group(2)), i, m.group(3)))
            return out
        ours = subjects(self.seat)
        other = subjects(_altro(self.seat))
        if k == "target:buff_unit" and ours:
            return (min if self.p.gear_target == "weak" else max)(ours)[1]
        if k == "target:grant_temporary_might":
            here = [x for x in ours if x[2] != "base"]
            if here:
                return max(here)[1]
        if k == "target:stun_unit" and other:
            return max(other)[1]
        if k == "combat_damage_order" and other:
            # Un'uccisione alla portata se c'e'; a pari costo, il posto legale piu' tardo.
            return min(other, key=lambda x: (x[0], -x[1]))[1]
        if k.startswith("optional:"):
            return next((i for i, s in enumerate(labels) if s.endswith(": sì")), e["default"])
        return e["default"]


class Branch(Attack):
    """Restituisce la posizione al campione alla prima azione libera dopo l'attacco (selezione.py)."""

    def __init__(self, proposal, seat, field):
        super().__init__(proposal, seat, field)
        self.resumed = None
        self.complete = False
        self.reason = None

    def ask(self, event):
        e = json.loads(event)
        if e["k"] == "decision" and e["point"] == "turn_action" and self.prepared and not self.declaring:
            target = f" base→BF{self.field}"
            can_move = any(s.startswith("Move ") and s.endswith(target) for s in e["menu"])
            if self.wave >= self.p.waves or not can_move:
                self.resumed = e["state_raw"]
                self.complete = self.wave >= self.p.waves
                self.reason = None if self.complete else "mossa non disponibile"
                raise Release()
        return self.act(event)


# -- una continuazione ----------------------------------------------------------------------------

def setup(g, P: dict, seed: int) -> None:
    """Entrambi i posti campione (seme per posto come in `un_mondo`) e il chooser dei lati."""
    for side in ("A", "B"):
        E._agente_campione(g, P, side, seed * 2 + (side == "B") + 1_000_003)
    g.set_side_chooser()


def tavolo(g, camp: str) -> dict:
    """Il tavolo visto dal campione (come `table` di ev.py): punti (campione, avversario), turno, chi controlla ogni
    campo, unita' dell'avversario e del campione sul campo 0, unita' della base del campione."""
    p = D.riassunto(json.loads(g.raw_dump()), camp)
    return {"points": p["punti"], "t": p["turno"], "fields": [f["controlla"] for f in p["campi"]],
            "theirs": [v[0] for v in p["campi"][0]["avversario"]["unita"]],
            "ours": [v[0] for v in p["campi"][0]["campione"]["unita"]],
            "base_camp": [v[0] for v in p["base"]["campione"]["unita"]],
            # in piu' di Astra (il confronto con i suoi dati legge solo le sue chiavi): le unita' di ogni campo
            "unita": [{"campo": f["campo"], "avversario": [v[0] for v in f["avversario"]["unita"]],
                       "campione": [v[0] for v in f["campione"]["unita"]]} for f in p["campi"]]}


def valori(g, P: dict) -> dict:
    """La valutazione del bot dal posto del campione, dello stato corrente: storica e quella della partita."""
    camp = P["camp"]
    out = {"storica": g.valuta(camp, "storica")}
    v = P.get("valutazione")
    if v and v[0] != "storica":
        out[v[0]] = g.valuta(camp, v[0], float(v[1]), float(v[2]))
    return out


def _facce(st: dict) -> list:
    """I nomi delle carte coperte sui campi del mondo (uguali per tutte le linee dello stesso mondo)."""
    out = []
    objs = st["objs"]
    for key in sorted(k for k in objs if re.fullmatch(r"bf\d+", k)):
        for fd in objs[key]["facedowns"]:
            out.append(objs[fd["$v"]["card"][1:]]["name"])
    return out


def linea_campione() -> dict:
    return {"nome": NOME_RIF, "tipo": "campione"}


def linea_sequenza(etichette: list[str], nome: str = NOME_RIF) -> dict:
    return {"nome": nome, "tipo": "sequenza", "etichette": list(etichette)}


def linea_proposta(nome: str, proposta: Proposal, campo: int) -> dict:
    return {"nome": nome, "tipo": "proposta", "proposta": asdict(proposta), "campo": campo}


def _controllo(linea: dict, camp: str):
    if linea["tipo"] == "campione":
        return None
    if linea["tipo"] == "sequenza":
        return Sequenza(linea["etichette"])
    return Branch(Proposal(**linea["proposta"]), camp, linea["campo"])


def continua(pos: dict, st: dict, linea: dict, i: int, modo: str) -> dict:
    """Una continuazione dal mondo `st` (indice `i`, seme pos.base + i) fino alla fine della partita (finish di ev.py).
    `campione`: i due posti campione da subito. Sequenza o proposta: il posto del campione e' controllato fino alla
    consegna (azione di turno libera), poi il turno riparte da quello stato con i due posti campione."""
    P = pos["P"]
    camp = P["camp"]
    opp = _altro(camp)
    seed = pos["base"] + i
    t0 = time.time()
    ctrl = _controllo(linea, camp)
    g = E.gioco(P, st, seed)
    if ctrl is None:
        setup(g, P, seed)
        w = g.run_actions_end()
    else:
        E._agente_campione(g, P, opp, seed * 2 + (opp == "B") + 1_000_003)
        g.set_human_agent(camp, ctrl.ask, False, None)
        g.set_side_chooser()
        try:
            w = g.run_actions_end()
        except Release:
            # A un'azione di turno pulita: e' il protocollo di consegna del progetto.
            g = E.gioco(P, E.albero(ctrl.resumed), seed + 555)
            setup(g, P, seed)
            w = g.run_actions_end()
    fine = tavolo(g, camp)
    assert w is not None or fine["t"] == pos["turno"] + 1, (fine["t"], pos["turno"])
    v_fine = valori(g, P) if w is None else None
    if w is None:
        setup(g, P, seed + 7411)
        w = g.run_begin()
    inizio10 = E._punti(json.loads(g.raw_dump()))
    if w is None:
        w = g.run_actions_end()
    end10 = E._punti(json.loads(g.raw_dump()))
    v_avv = valori(g, P) if w is None else None
    r = E._finisci(g, P, w, i, time.time(), end10)
    assert r["vince"] in ("A", "B", "DRAW")
    row = {"world": i, "set": modo, "line": linea["nome"], "face": _facce(st),
           "prefix_ok": True if ctrl is None else ctrl.complete, "fallback": None if ctrl is None else ctrl.reason,
           "t9": fine, "start10_A_B": inizio10, "end10_A_B": end10, "winner": r["vince"],
           "end_A_B": r["punti_fine"], "turns": r["turni"], "returns": E.punteggio(r, camp),
           "valori": {"fine_turno": v_fine, "fine_turno_avv": v_avv}, "secondi": time.time() - t0}
    if isinstance(ctrl, Branch) and ctrl.p.waves == 2:
        row["nemici_seconda_ondata"] = ctrl.nemici_seconda
    return row


# -- generazione delle proposte -------------------------------------------------------------------

def genera(pos: dict, deduplica: bool = True) -> list[dict]:
    """Le proposte nel mondo di riferimento (la posizione com'e', seme base; come `proposte.run`): per ogni campo
    controllato dall'avversario con unita' (in ordine di indice) e per ogni voce della griglia, gli eventi della
    politica e il tavolo a fine turno. Con `deduplica` una proposta con gli stessi eventi di una precedente ha
    `uguale_a` = il nome della prima e non entra nelle linee."""
    P, tree, base = pos["P"], pos["tree"], pos["base"]
    seat = P["camp"]
    other = _altro(seat)
    game = E.gioco(P, tree, base)
    view = D.riassunto(json.loads(game.raw_dump()), seat)
    campi = [f["campo"] for f in view["campi"] if f["controlla"] == "avversario" and f["avversario"]["unita"]]
    out = []
    visti: dict = {}
    for n, (campo, proposal) in enumerate(product(campi, list(griglia()))):
        game = E.gioco(P, tree, base)
        E._agente_campione(game, P, other, 2 * base + (other == "B") + 1_000_003)
        policy = Attack(proposal, seat, campo)
        game.set_human_agent(seat, policy.act, False, None)
        game.set_side_chooser()
        game.run_actions_end()
        nome = f"p{n:02d}"
        chiave = json.dumps(policy.events)
        uguale = visti.get(chiave) if deduplica else None
        visti.setdefault(chiave, nome)
        out.append({"nome": nome, "indice": n, "field": campo, "proposal": asdict(proposal),
                    "events": policy.events, "waves": policy.wave, "ambush": policy.used_ambush,
                    "spell": policy.used_spell, "state": tavolo(game, seat), "uguale_a": uguale})
    return out


def linee_da(proposte: list[dict], riferimento) -> list[dict]:
    """Le linee da giocare: il riferimento (`campione` o lista di etichette) e le proposte non duplicate."""
    rif = linea_campione() if riferimento in (None, "campione") else linea_sequenza(riferimento)
    return [rif] + [linea_proposta(p["nome"], Proposal(**p["proposal"]), p["field"])
                    for p in proposte if p["uguale_a"] is None]


# -- selezione e verifica -------------------------------------------------------------------------

def _lavoro(args):
    pos, modo, i, linee = args
    st = mondo(pos, modo, pos["base"] + i)
    return [continua(pos, st, linea, i, modo) for linea in linee]


def esegui(pos: dict, modo: str, indici, linee: list[dict], path: Path | None, processi: int = 1, out=print) -> list:
    """Per ogni mondo di `indici` tutte le `linee` (stesso mondo, stesso seme); una riga jsonl per mondo, in ordine."""
    lavori = [(pos, modo, i, linee) for i in indici]
    risultati = []
    f = path.open("w", encoding="utf-8") if path else None
    pool = None
    try:
        if processi > 1:
            pool = ProcessPoolExecutor(processi, mp_context=multiprocessing.get_context("spawn"))
            it = pool.map(_lavoro, lavori)
        else:
            it = map(_lavoro, lavori)
        t0 = time.time()
        for j, rows in enumerate(it, 1):
            risultati.append(rows)
            if f:
                f.write(json.dumps(rows, ensure_ascii=False) + "\n")
                f.flush()
            if j == 1 or j % 10 == 0 or j == len(lavori):
                out(f"  {path.name if path else modo}: {j}/{len(lavori)} mondi, {time.time() - t0:.0f} s")
    finally:
        if f:
            f.close()
        if pool:
            pool.shutdown()
    return risultati


def _riga(rows: list, nome: str) -> dict:
    return next(r for r in rows if r["line"] == nome)


def confronto(data: list, rif: str = NOME_RIF) -> dict:
    """Per ogni linea, sui mondi appaiati: punti, vittorie, patte e la differenza rispetto alla linea `rif`
    (media +- 1,96 errori standard appaiati, come `misure.compare`); `valori`: differenza media della valutazione
    del campione a fine turno e dopo il turno dell'avversario (linea - riferimento)."""
    out = {}
    for nome in [r["line"] for r in data[0]]:
        arm = [_riga(rows, nome) for rows in data]
        ref = [_riga(rows, rif) for rows in data]
        delta = [a["returns"] - b["returns"] for a, b in zip(arm, ref)]
        n = len(delta)
        avg = mean(delta)
        margine = 1.96 * stdev(delta) / sqrt(n) if n > 1 else float("nan")
        val = {}
        for punto, coda in (("fine_turno", ""), ("fine_turno_avv", " dopo l'avversario")):
            chiavi = next((a["valori"][punto] for a in arm if a["valori"][punto]), {})
            for chiave in chiavi:
                d = [a["valori"][punto][chiave] - b["valori"][punto][chiave]
                     for a, b in zip(arm, ref) if a["valori"][punto] and b["valori"][punto]]
                if d:
                    val[chiave + coda] = {"n": len(d), "media": mean(d)}
        out[nome] = {"n": n, "punti_partita": sum(a["returns"] for a in arm),
                     "vittorie": sum(a["returns"] == 1.0 for a in arm), "patte": sum(a["returns"] == 0.5 for a in arm),
                     "delta": avg, "intervallo_95": [avg - margine, avg + margine],
                     "vince_solo_linea": sum(v > 0 for v in delta), "vince_solo_riferimento": sum(v < 0 for v in delta),
                     "prefisso_completo": sum(a["prefix_ok"] for a in arm), "valori": val}
    return out


def confronta(partita: dict, k: int, out_dir: Path | None = None, riferimento="campione", modo: str = "ignote",
              scelta=SCELTA, verifica=VERIFICA, deduplica: bool = True, processi: int = 1, print_=print) -> dict:
    """Tutto per una posizione: proposte, selezione, verifica, vista del campione ed esito (vedi il docstring del modulo).
    `riferimento`: "campione" o una lista di etichette di turno. Scrive in `out_dir` (se dato): proposte.json,
    scelta.jsonl, verifica.jsonl, vista.json, esito.json, esito.txt."""
    pos = posizione(partita, k)
    P = pos["P"]
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    mondo(pos, modo, pos["base"] + scelta[0])          # PosizioneNonAdatta subito, prima delle proposte
    proposte = genera(pos, deduplica)
    if out_dir:
        (out_dir / "proposte.json").write_text(json.dumps(proposte, ensure_ascii=False), encoding="utf-8")
    linee = linee_da(proposte, riferimento)
    print_(f"{len(proposte)} proposte ({len(linee) - 1} dopo la deduplica); {len(linee)} linee")
    dati_s = esegui(pos, modo, range(scelta[0], scelta[0] + scelta[1]), linee,
                    out_dir / "scelta.jsonl" if out_dir else None, processi, print_)
    nomi = [li["nome"] for li in linee]
    totali = {n: sum(_riga(rows, n)["returns"] for rows in dati_s) for n in nomi}
    migliore = max(nomi, key=totali.get)        # a pari punti la prima nell'ordine (il riferimento per primo)
    print_(f"selezione: migliore {migliore} ({totali[migliore]:g} contro {totali[NOME_RIF]:g} del riferimento)")
    linee_v = [linee[0]] + ([next(li for li in linee if li["nome"] == migliore)] if migliore != NOME_RIF else [])
    dati_v = esegui(pos, modo, range(verifica[0], verifica[0] + verifica[1]), linee_v,
                    out_dir / "verifica.jsonl" if out_dir else None, processi, print_)
    ver = confronto(dati_v)
    # la vista del campione a k: visite e q di ogni proposta nella ricerca originale
    vista = D.rifai(partita, k, None, posizione=False, semi=True)
    classifica = vista["classifica"]
    iters = P["iterazioni"]
    for p in proposte:
        etichetta = next((ev[2] for ev in p["events"] if ev[1] == "turn_action"), None)
        voce = next((c for c in sorted(classifica, key=lambda c: c["i"]) if c["azione"] == etichetta), None) \
            if etichetta else None
        p["prima_etichetta"] = etichetta
        p["visite"] = voce["n"] if voce else 0
        p["q"] = voce["q"] if voce and voce["n"] else 0
    esito = _esito(proposte, migliore, ver, iters)
    esito.update({"partita": partita, "k": k, "turno": pos["turno"], "riferimento": riferimento, "modo": modo,
                  "scelta": list(scelta), "verifica": list(verifica), "deduplica": deduplica,
                  "selezione": totali, "secondi": time.time() - t0})
    if out_dir:
        (out_dir / "proposte.json").write_text(json.dumps(proposte, ensure_ascii=False), encoding="utf-8")
        (out_dir / "vista.json").write_text(json.dumps({"k": k, "iterazioni": iters, "prefisso_ok": vista["prefisso_ok"],
                                                       "azione": vista["azione"], "azione_originale": vista.get("azione_originale"),
                                                       "classifica": classifica}, ensure_ascii=False), encoding="utf-8")
        (out_dir / "esito.json").write_text(json.dumps(esito, ensure_ascii=False, indent=1), encoding="utf-8")
        (out_dir / "esito.txt").write_text("\n".join(testo_esito(esito)) + "\n", encoding="utf-8")
    return esito


def _esito(proposte: list, migliore: str, ver: dict, iters: int) -> dict:
    e: dict = {"migliore": migliore, "verifica_dati": ver}
    if migliore == NOME_RIF:
        e.update({"esito": "riferimento scelto", "sottoclasse": None, "differenza": None, "valori": None})
        return e
    d = ver[migliore]
    lo, hi = d["intervallo_95"]
    scelta = next(p for p in proposte if p["nome"] == migliore)
    e["proposta"] = {k: scelta[k] for k in ("nome", "field", "proposal", "events", "prima_etichetta", "visite", "q")}
    e["sottoclasse"] = None
    if lo > 0:
        e["esito"] = "attacco migliore"
        e["sottoclasse"] = "mai costruita" if scelta["visite"] < max(3, 0.02 * iters) else "costruita ma valutata male"
    elif hi < 0:
        e["esito"] = "riferimento migliore"
    else:
        e["esito"] = "indeciso"
    e["differenza"] = {"media": d["delta"], "intervallo_95": d["intervallo_95"]}
    segno = (d["delta"] > 0) - (d["delta"] < 0)
    e["valori"] = {n: {**v, "concorda_con_vittorie": ((v["media"] > 0) - (v["media"] < 0)) == segno}
                   for n, v in d["valori"].items()}
    return e


def testo_esito(e: dict) -> list[str]:
    righe = [f"posizione k={e['k']} (turno {e['turno']}): {e['esito']}"
             + (f" ({e['sottoclasse']})" if e.get("sottoclasse") else "")]
    sel = e["selezione"]
    righe.append(f"selezione ({e['scelta'][1]} mondi {e['modo']}): migliore {e['migliore']} con {sel[e['migliore']]:g} punti, "
                 f"riferimento {sel[NOME_RIF]:g}")
    if e.get("proposta"):
        p = e["proposta"]
        righe.append(f"proposta {p['nome']} campo {p['field']} {p['proposal']}: prima mossa {p['prima_etichetta']}, "
                     f"visite {p['visite']}, q {round(p['q'], 3)}")
    if e.get("differenza"):
        d = e["differenza"]
        righe.append(f"differenza (proposta - riferimento) su {e['verifica'][1]} mondi: {100 * d['media']:+.1f} pp "
                     f"[{100 * d['intervallo_95'][0]:+.1f}, {100 * d['intervallo_95'][1]:+.1f}]")
        for n, v in (e.get("valori") or {}).items():
            righe.append(f"valori ({n}): media {v['media']:+.3f}; segno {'concorde' if v['concorda_con_vittorie'] else 'discorde'} "
                         f"con la differenza di vittorie")
    return righe


# -- posizioni candidate --------------------------------------------------------------------------

_MOSSA = re.compile(r"^Move .* base→BF(\d+)$")


def posizioni(partita: dict) -> list[dict]:
    """Per ogni turno del campione la PRIMA decisione `turn_action` in cui un campo e' controllato dall'avversario con
    almeno un'unita' e il menu ha uno spostamento dalla base verso quel campo. `punto_libero`: il menu ha anche uno
    spostamento verso un campo senza nemici non controllato dal campione."""
    def stato(s):
        return s["point"] == "turn_action" and any(_MOSSA.match(x) for x in s["menu"])
    orig = D.originale(partita, stato)
    camp = D._prepara(partita)["camp"]
    fatti = set()
    out = []
    for o in orig:
        if o["point"] != "turn_action" or o["turn"] in fatti or o["e"].get("state_raw") is None:
            continue
        verso = {int(m.group(1)) for m in map(_MOSSA.match, o["menu"]) if m}
        vista = D.riassunto(o["e"]["state_raw"], camp)
        campi = [f["campo"] for f in vista["campi"]
                 if f["controlla"] == "avversario" and f["avversario"]["unita"] and f["campo"] in verso]
        if not campi:
            continue
        libero = any(f["campo"] in verso and not f["avversario"]["unita"] and f["controlla"] != "campione"
                     for f in vista["campi"])
        fatti.add(o["turn"])
        out.append({"partita": partita, "k": o["k"], "turno": o["turn"], "punti": vista["punti"], "campi": campi,
                    "punto_libero": libero})
    return out


# -- serie ----------------------------------------------------------------------------------------

def nome_partita(partita: dict) -> str:
    if partita["tipo"] == "pagina":
        return Path(partita["file"]).stem[:24]
    return f"{partita['matchup']}{partita['seed']}{partita.get('campione', 'A')}"


def scegli_posizioni(elenco: list[dict], n: int) -> list[dict]:
    """Al piu' `n` posizioni: meta' con `punto_libero` se ce ne sono (le altre completano), sparse sull'elenco."""
    def sparse(v, m):
        return [v[(j * len(v)) // m] for j in range(m)] if m < len(v) else list(v)
    liberi = [p for p in elenco if p.get("punto_libero")]
    altri = [p for p in elenco if not p.get("punto_libero")]
    a = sparse(liberi, min(len(liberi), n // 2))
    b = sparse(altri, min(len(altri), n - len(a)))
    a = sparse(liberi, min(len(liberi), n - len(b)))
    ids = {id(p) for p in a + b}
    return [p for p in elenco if id(p) in ids]


def serie(elenco: list[dict], out_dir: Path, massimo: int | None = None, riferimento="campione", modo: str = "ignote",
          scelta=SCELTA, verifica=VERIFICA, deduplica: bool = True, processi: int = 1, print_=print) -> list[str]:
    """`confronta` per ogni posizione (cartella `NN_...`) e `riepilogo.txt`: una riga per posizione."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    righe = []
    esiti: dict = {}
    for n, p in enumerate(scegli_posizioni(elenco, massimo) if massimo else elenco):
        nome = nome_partita(p["partita"])
        print_(f"== posizione {n}: {nome} k={p['k']} turno {p['turno']}")
        try:
            e = confronta(p["partita"], p["k"], out_dir / f"{n:02d}_{nome}_k{p['k']}", riferimento, modo, scelta, verifica,
                          deduplica, processi, print_)
        except PosizioneNonAdatta as x:
            righe.append(f"{nome} | k={p['k']} | turno {p['turno']} | punto_libero={'sì' if p.get('punto_libero') else 'no'} | "
                         f"saltata: {x}")
            (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
            continue
        if e.get("differenza"):
            d = e["differenza"]
            dif = f"{100 * d['media']:+.1f} [{100 * d['intervallo_95'][0]:+.1f}, {100 * d['intervallo_95'][1]:+.1f}] pp"
        else:
            dif = "-"
        val = "; ".join(f"{k} {v['media']:+.3f} ({'concorde' if v['concorda_con_vittorie'] else 'discorde'})"
                        for k, v in (e.get("valori") or {}).items()) or "-"
        esito = e["esito"] + (f" ({e['sottoclasse']})" if e.get("sottoclasse") else "")
        righe.append(f"{nome} | k={p['k']} | turno {p['turno']} | punto_libero={'sì' if p.get('punto_libero') else 'no'} | "
                     f"{esito} | differenza {dif} | valori {val}")
        esiti[esito] = esiti.get(esito, 0) + 1
        (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    saltate = sum("| saltata:" in r for r in righe)
    righe.append("totale: " + "; ".join(f"{k} {v}" for k, v in sorted(esiti.items(), key=lambda x: -x[1]))
                 + (f"; saltate {saltate}" if saltate else ""))
    (out_dir / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    return righe


# -- rivedi: verifiche in piu' su una serie gia' fatta ---------------------------------------------

def _chiave_valori(dati: list) -> str | None:
    """La valutazione da leggere nelle righe di scelta: quella della partita se c'e' (es. `rimonta`), se no `storica`."""
    for rows in dati:
        for r in rows:
            for punto in ("fine_turno", "fine_turno_avv"):
                v = r["valori"][punto]
                if v:
                    return next((c for c in v if c != "storica"), "storica")
    return None


def _media_valori(dati: list, nome: str, punto: str, chiave: str) -> float | None:
    """Media della valutazione `chiave` di una linea ai mondi di scelta (i mondi senza valutazione, partita gia' finita, non contano)."""
    v = [_riga(rows, nome)["valori"][punto][chiave] for rows in dati if _riga(rows, nome)["valori"][punto]]
    return mean(v) if v else None


def linee_in_piu(dati_s: list, nomi: list[str], migliore: str, gia: set) -> tuple[dict, dict]:
    """Le linee da verificare in piu' (vedi `rivedi`): {nome: {"motivi": [...], "margini": {punto: margine}}} e le
    informazioni sulla posizione ({"chiave", "decisa", "punti_riferimento", "mondi"}). `gia`: nomi gia' verificati."""
    chiave = _chiave_valori(dati_s)
    totali = {n: sum(_riga(rows, n)["returns"] for rows in dati_s) for n in nomi}
    info = {"chiave": chiave, "mondi": len(dati_s), "punti_riferimento": totali[NOME_RIF],
            "decisa": totali[NOME_RIF] in (0, len(dati_s))}
    out: dict = {}

    def aggiungi(nome, motivo):
        if nome in gia:
            return
        margini = {}
        if chiave:
            for punto in ("fine_turno", "fine_turno_avv"):
                a, b = _media_valori(dati_s, nome, punto, chiave), _media_valori(dati_s, NOME_RIF, punto, chiave)
                margini[punto] = None if a is None or b is None else a - b
        voce = out.setdefault(nome, {"motivi": [], "margini": margini})
        voce["motivi"].append(motivo)

    if chiave:
        for punto, motivo in (("fine_turno", "sonda fine turno"), ("fine_turno_avv", "sonda dopo l'avversario")):
            medie = {n: _media_valori(dati_s, n, punto, chiave) for n in nomi}
            medie = {n: m for n, m in medie.items() if m is not None}
            if NOME_RIF not in medie:
                continue
            best = max(medie, key=lambda n: (medie[n], -nomi.index(n)))   # a pari media la prima nell'ordine
            if best != NOME_RIF and medie[best] > medie[NOME_RIF]:
                aggiungi(best, motivo)
    if migliore == NOME_RIF and len(nomi) > 1:
        best = max(nomi[1:], key=lambda n: (totali[n], -nomi.index(n)))
        aggiungi(best, "migliore per vittorie")
    return out, info


def _rilegge(path: Path) -> list:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _controllo_riferimento(pos: dict, modo: str, indici, linea_rif: dict, salvate: list, processi: int) -> list[str]:
    """Rifa il riferimento sui primi mondi di verifica e lo confronta con le righe salvate (returns, end_A_B, t9)."""
    nuove = esegui(pos, modo, list(indici)[:2], [linea_rif], None, processi, lambda *_: None)
    dif = []
    for rows, vecchie in zip(nuove, salvate):
        a = json.loads(json.dumps(rows[0]))
        b = _riga(vecchie, NOME_RIF)
        for campo in ("returns", "end_A_B", "t9"):
            if a[campo] != b[campo]:
                dif.append(f"mondo {a['world']}: {campo} {a[campo]} (nuovo) contro {b[campo]} (salvato)")
    return dif


def _vista_ricerca(partita: dict, k: int, iters: int, mosse: dict, conta: list, quota_n: int, mirata_n: int,
                   prima_etichetta: str | None, print_=print) -> list[dict]:
    """Le 5 condizioni della ricerca k (finestre si/no, quota nessuna/`([""], quota_n)`/mirata sulla prima mossa
    dell'attacco). `mosse`: {"attacco": etichetta, "campione": etichetta}. Per ciascuna: l'azione scelta e, per le due
    mosse, visite, q, rango e (con le finestre) le giocate dei piloti delle azioni di showdown `conta`."""
    condizioni = [(False, None), (True, None), (False, "tutte"), (True, "tutte")]
    if prima_etichetta:
        condizioni.append((True, "mirata"))
    out = []
    for fin, quota in condizioni:
        q = None if quota is None else ([""], quota_n) if quota == "tutte" else ([prima_etichetta], mirata_n)
        r = D.rifai(partita, k, iters, posizione=False, semi=True, finestre=fin, quota=q)
        out.append({"finestre": fin, "quota": quota, "scelta": r["azione"], "prefisso_ok": r["prefisso_ok"],
                    "mosse": {n: E._riga_mossa(r, m, conta) for n, m in mosse.items() if m}})
        print_(f"    ricerca finestre {'si' if fin else 'no'} quota {quota or 'no'}: {r['azione']}")
    return out


def _f(x, d=2) -> str:
    return "-" if x is None else f"{x:.{d}f}"


def _testo_vista(vista: list[dict], posto: str) -> list[str]:
    righe = []
    for v in vista:
        quota = {None: "senza", "tutte": "quota", "mirata": "quota mirata"}[v["quota"]]
        t = f"    finestre {'si' if v['finestre'] else 'no'}, {quota}: scelta '{v['scelta']}'"
        for nome, m in v["mosse"].items():
            t += f" | {nome}: n={m['n']} q={_f(m['q'])}" + (f" r{m['rango']}/{m['tot']}" if m["rango"] else " assente")
            if m.get("conta"):
                t += " showdown " + ",".join(f"{c[:14]}={x[posto]}" for c, x in m["conta"].items())
        righe.append(t)
    return righe


def _posizione_rivedi(cart: Path, out: Path, processi: int, quota_n: int, mirata_n: int, ckpt, casuali, print_) -> tuple:
    """-> (righe di testo, scheda json, lista delle linee in piu' verificate con le loro statistiche)."""
    esito = json.loads((cart / "esito.json").read_text(encoding="utf-8"))
    partita, k, modo = dict(esito["partita"]), esito["k"], esito["modo"]
    if ckpt:
        partita["ckpt"] = ckpt
    if casuali:
        partita["casuali"] = True
    proposte = json.loads((cart / "proposte.json").read_text(encoding="utf-8"))
    dati_s = _rilegge(cart / "scelta.jsonl")
    dati_v = _rilegge(cart / "verifica.jsonl")
    pos = posizione(partita, k)
    linee = linee_da(proposte, esito["riferimento"])
    nomi = [li["nome"] for li in linee]
    gia = {r["line"] for r in dati_v[0]}
    extra, info = linee_in_piu(dati_s, nomi, esito["migliore"], gia)
    indici = [r[0]["world"] for r in dati_v]
    scheda: dict = {"k": k, "turno": esito["turno"], "esito_serie": esito["esito"], "selezione_migliore": esito["migliore"],
                    **info, "linee": {}, "errore": None, "vista": None}
    righe: list[str] = []
    stats: list[dict] = []
    if extra:
        dif = _controllo_riferimento(pos, modo, indici, linee[0], dati_v, processi)
        if dif:
            scheda["errore"] = "il riferimento rifatto non coincide con quello salvato: " + "; ".join(dif)
            return [f"ERRORE: {scheda['errore']}"], scheda, stats
        nuove = [li for li in linee if li["nome"] in extra]
        dati_n = esegui(pos, modo, indici, nuove, out / "verifica_extra.jsonl", processi, print_)
        conf = confronto([[_riga(v, NOME_RIF)] + n for v, n in zip(dati_v, dati_n)])
        rif = conf[NOME_RIF]
        for nome, voce in extra.items():
            c = conf[nome]
            lo, hi = c["intervallo_95"]
            s = {"nome": nome, **voce, "vittorie_riferimento": rif["vittorie"], "vittorie_linea": c["vittorie"],
                 "n": c["n"], "delta": c["delta"], "intervallo_95": [lo, hi], "migliore": lo > 0, "peggiore": hi < 0}
            stats.append(s)
            scheda["linee"][nome] = s
            m = voce["margini"]
            mm = "; ".join(f"{lab} {m[p]:+.3f}" for p, lab in (("fine_turno", "fine turno"), ("fine_turno_avv", "dopo l'avversario"))
                           if m.get(p) is not None) or "senza valutazione"
            righe.append(f"  {nome} ({', '.join(voce['motivi'])}): margine {info['chiave']} {mm}; vittorie riferimento/linea "
                         f"{rif['vittorie']}/{c['vittorie']} su {c['n']}; differenza {100 * c['delta']:+.1f} "
                         f"[{100 * lo:+.1f}, {100 * hi:+.1f}] pp" + ("; decisa" if info["decisa"] else ""))
    # vista con finestre e quota, dove c'e' un attacco verificato migliore
    migliori = [s for s in stats if s["migliore"]]
    scelta_serie = esito["proposta"]["nome"] if esito["esito"] == "attacco migliore" else None
    nome_att = scelta_serie or (max(migliori, key=lambda s: s["delta"])["nome"] if migliori else None)
    if nome_att:
        p = next(x for x in proposte if x["nome"] == nome_att)
        etichetta = p.get("prima_etichetta") or next((ev[2] for ev in p["events"] if ev[1] == "turn_action"), None)
        vista0 = json.loads((cart / "vista.json").read_text(encoding="utf-8"))
        # la mossa giocata dal campione (la ricerca sceglie il figlio visitato col q piu' alto, non il piu' visitato:
        # Codex, PR 67); le viste delle serie del 26/11 non la registrano, si chiede al rifacimento
        orig = vista0.get("azione_originale") or D.rifai(partita, k, None, posizione=False)["azione_originale"]
        conta = list(dict.fromkeys(ev[2] for ev in p["events"] if ev[1] == "showdown_action"))
        vista = _vista_ricerca(partita, k, pos["P"]["iterazioni"], {"attacco": etichetta, "campione": orig}, conta,
                               quota_n, mirata_n, etichetta, print_)
        scheda["vista"] = {"proposta": nome_att, "prima_etichetta": etichetta, "mossa_campione": orig,
                           "showdown": conta, "condizioni": vista}
        righe.append(f"  vista della ricerca (attacco {nome_att}: '{etichetta}'; campione: '{orig}'; "
                     f"showdown da giocare: {', '.join(conta) or 'nessuno'}):")
        righe += _testo_vista(vista, pos["P"]["camp"])
    if not righe:
        righe = ["  niente da verificare"]
    return righe, scheda, stats


def rivedi(serie_dir: Path, out_dir: Path, processi: int = 1, quota_n: int = 4, mirata_n: int = 10, print_=print,
           ckpt: str | None = None, casuali: bool = False) -> list[str]:
    """Verifiche in piu' su una serie gia' fatta (cartelle `NN_..._kK/` di `serie`): per ogni posizione le linee con la
    media piu' alta della valutazione a fine turno e dopo l'avversario nei mondi di scelta (sonde) e, se la selezione ha
    scelto il riferimento, la proposta con piu' punti; verificate sugli stessi mondi di verifica, appaiate alle righe
    del riferimento salvate (controllo prima su 2 mondi). Per le posizioni con un attacco verificato migliore, la
    ricerca del campione rifatta con finestre e quota. Scrive in `out_dir`: una cartella per posizione
    (`rivedi.json`, `verifica_extra.jsonl`) e `rivedi.txt` (una riga `totale:` in fondo)."""
    serie_dir, out_dir = Path(serie_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    righe: list[str] = []
    tutte: list[dict] = []
    sonda_fine = {"veri positivi": 0, "falsi positivi": 0, "indecisi": 0}
    errori = 0
    for cart in sorted(p for p in serie_dir.iterdir() if (p / "esito.json").is_file()):
        out = out_dir / cart.name
        out.mkdir(parents=True, exist_ok=True)
        print_(f"== {cart.name}")
        righe.append(f"{cart.name}:")
        try:
            testo, scheda, stats = _posizione_rivedi(cart, out, processi, quota_n, mirata_n, ckpt, casuali, print_)
        except PosizioneNonAdatta as x:
            testo, scheda, stats = [f"ERRORE: saltata: {x}"], {"errore": f"saltata: {x}"}, []
        except Exception as x:   # una posizione che fallisce non ferma le altre
            testo, scheda, stats = [f"ERRORE: {type(x).__name__}: {x}"], {"errore": f"{type(x).__name__}: {x}"}, []
        errori += bool(scheda.get("errore"))
        (out / "rivedi.json").write_text(json.dumps(scheda, ensure_ascii=False, indent=1), encoding="utf-8")
        righe += testo
        tutte += stats
        for s in stats:
            if "sonda fine turno" in s["motivi"]:
                sonda_fine["veri positivi" if s["migliore"] else "falsi positivi" if s["peggiore"] else "indecisi"] += 1
        (out_dir / "rivedi.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    righe.append(f"totale: {len(tutte)} linee in più verificate; limite inferiore > 0: {sum(s['migliore'] for s in tutte)}; "
                 f"limite superiore < 0: {sum(s['peggiore'] for s in tutte)}; sonda fine turno: "
                 + ", ".join(f"{k} {v}" for k, v in sonda_fine.items()) + (f"; errori {errori}" if errori else ""))
    (out_dir / "rivedi.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    return righe


# -- riproduzione del T9 di Astra -----------------------------------------------------------------

def _norm_t9(t: dict) -> dict:
    t = dict(t)
    if "base_B" in t:
        t["base_camp"] = t.pop("base_B")
    return t


def _riga_uguale(mia: dict, astra: dict) -> list[str]:
    diff = []
    for chiave in ("winner", "returns", "end_A_B", "turns", "prefix_ok"):
        if mia.get(chiave) != astra.get(chiave):
            diff.append(f"{chiave}: mio {mia.get(chiave)!r} astra {astra.get(chiave)!r}")
    a, b = _norm_t9(mia["t9"]), _norm_t9(astra["t9"])
    for chiave in b:
        if a.get(chiave) != b[chiave]:
            diff.append(f"t9.{chiave}: mio {a.get(chiave)!r} astra {b[chiave]!r}")
    return diff


def diff_proposte(pm: list, pa: list) -> list[str]:
    """Le differenze fra le proposte mie (`pm`) e quelle di Astra (`pa`, proposte.json), nell'ordine."""
    dif = []
    if len(pa) != len(pm):
        dif.append(f"proposte: {len(pm)} contro {len(pa)} di Astra")
    for j, (a, m) in enumerate(zip(pa, pm)):
        for chiave in ("field", "proposal", "events", "waves", "ambush", "spell"):
            if a[chiave] != m[chiave]:
                dif.append(f"proposta p{j:02d}.{chiave}: mia {m[chiave]!r} astra {a[chiave]!r}")
        # solo le chiavi di Astra (come `_riga_uguale`): le aggiunte del tavolo (`unita`) non contano
        sa, sm = _norm_t9(a["state"]), _norm_t9(m["state"])
        sm = {chiave: sm.get(chiave) for chiave in sa}
        if sa != sm:
            dif.append(f"proposta p{j:02d}.state: mio {sm} astra {sa}")
    return dif


def confronta_con_astra(mio: Path, dati: Path, rapida: bool = False) -> list[str]:
    """Le differenze (lista vuota = IDENTICO) fra i file prodotti in `mio` e quelli di Astra in `dati` (proposte.json,
    scelta.jsonl, verifica.jsonl); i campi nuovi si ignorano; `valley` = il riferimento. Con `rapida` solo i primi
    2 mondi di scelta."""
    dif = diff_proposte(json.loads((mio / "proposte.json").read_text()), json.loads((dati / "proposte.json").read_text()))
    for fn in ("scelta.jsonl", "verifica.jsonl"):
        if not (mio / fn).exists():
            continue
        ra = [json.loads(x) for x in (dati / fn).read_text().splitlines()]
        rm = [json.loads(x) for x in (mio / fn).read_text().splitlines()]
        if not rapida and len(ra) != len(rm):
            dif.append(f"{fn}: {len(rm)} mondi contro {len(ra)} di Astra")
        for wa, wm in zip(ra, rm):
            da = {(NOME_RIF if r["line"] == "valley" else r["line"]): r for r in wa}
            for r in wm:
                nome = NOME_RIF if r["line"] == "valley" else r["line"]
                if nome not in da:
                    dif.append(f"{fn} mondo {r['world']}: linea {r['line']} assente in Astra")
                    continue
                for d in _riga_uguale(r, da[nome]):
                    dif.append(f"{fn} mondo {r['world']} {r['line']}: {d}")
    return dif


def riproduci_t9(dati: Path, out_dir: Path, rapida: bool = False, ckpt: str | None = None, casuali: bool = False,
                 processi: int = 1, print_=print, replay: str = T9_REPLAY) -> list[str]:
    """La prova di Astra (partita 013325, k=10, riferimento `Play Vi ; Move Sett base→BF1 ; Pass`, senza deduplica,
    scelta `ignote` 2000..2015, verifica 4000..4099) e il confronto con i suoi dati. `rapida`: solo proposte e i primi 2
    mondi di scelta. -> la lista delle differenze (vuota = IDENTICO)."""
    partita = {"tipo": "pagina", "file": replay, "ckpt": ckpt, "casuali": casuali}
    rif = [x.strip() for x in T9_RIFERIMENTO.split(" ; ")]
    out_dir = Path(out_dir)
    if rapida:
        pos = posizione(partita, 10)
        out_dir.mkdir(parents=True, exist_ok=True)
        proposte = genera(pos, deduplica=False)
        (out_dir / "proposte.json").write_text(json.dumps(proposte, ensure_ascii=False), encoding="utf-8")
        esegui(pos, "ignote", range(SCELTA[0], SCELTA[0] + 2), linee_da(proposte, rif), out_dir / "scelta.jsonl",
               processi, print_)
    else:
        confronta(partita, 10, out_dir, rif, "ignote", SCELTA, VERIFICA, False, processi, print_)
    return confronta_con_astra(out_dir, Path(dati), rapida)
