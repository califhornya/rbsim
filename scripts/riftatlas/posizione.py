"""Dal tavolo RiftAtlas a una posizione del motore, e la mossa del bot a mano.

Uso: python scripts/riftatlas/posizione.py <file.json> [seq] [--budget S]
                                           [--mazzo-avversario lista.txt|deck.json] [--seed N]

Prende lo stato ricostruito da `stati.py` a una seq (default: l'ultima) in cui
chi registra è nel suo Main Phase, ne fa un `GameState` (`riftbound/core/`) e
chiede al bot a mano (`riftbound/ai/handwritten.py`) la prima azione del turno,
con le alternative che ha esplorato.

Cosa il tavolo non dice, e come si riempie (ogni scelta finisce negli avvisi):
- le carte coperte di chi registra (mazzo): la sua lista (`decklistRaw` nel
  file) meno le carte viste altrove; l'ordine dal seed;
- quelle dell'avversario (mano, mazzo, coperte): la sua lista se si passa
  `--mazzo-avversario` (.txt come lo esporta RiftMana, o .json di
  `riftbound/data/decks`), se no le carte del
  suo mazzo viste in partita, ripetute fino al numero giusto. La ricerca
  rimescola comunque mano e mazzo avversari (`determinize`): conta di che
  carte è fatto il mucchio, non l'ordine;
- il danno sulle unità (RiftAtlas non lo tiene; al Main Phase è 0) e i
  segnalini a mano dei giocatori (`whiteCounter`): il motore calcola la Might da
  sé, le differenze col segnalino si segnalano;
- i lati del motore: posto 0 = A (BF0, il campo di A), posto 1 = B;
- la catena e una conquista in corso su RiftAtlas: ignorate (avviso).
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import stati  # noqa: E402
from riftbound.ai.handwritten import HandwrittenAgent  # noqa: E402
from riftbound.core.battlefield import Battlefield, FacedownCard  # noqa: E402
from riftbound.core.cards import GearCard  # noqa: E402
from riftbound.core.combat import UnitInPlay  # noqa: E402
from riftbound.core.decisions import DecisionPoint  # noqa: E402
from riftbound.core.enums import Domain  # noqa: E402
from riftbound.core.legality import legal_actions  # noqa: E402
from riftbound.core.loop import GameLoop  # noqa: E402
from riftbound.core.player import Player, Rune, RuneDeck  # noqa: E402
from riftbound.core.state import GameState  # noqa: E402
from riftbound.registry.cards_registry import CARD_REGISTRY, load_deck_json  # noqa: E402

_REG = {re.sub(r"[^a-z0-9]", "", k.lower()): k for k in CARD_REGISTRY}
_DOMINI = {"fury": Domain.FURY, "calm": Domain.CALM, "mind": Domain.MIND,
           "body": Domain.BODY, "chaos": Domain.CHAOS, "order": Domain.ORDER}


def nome_motore(c: dict) -> str | None:
    """Il nome della carta nel registro del motore (i nomi RiftAtlas hanno la
    virgola: "Ivern, Nurturer" → "Ivern Nurturer")."""
    dati = stati.dati_carta(c)
    for n in ((dati or {}).get("name"), c.get("name")):
        if n and stati._norm(n) in _REG:
            return _REG[stati._norm(n)]
    return None


def dominio_runa(c: dict) -> Domain | None:
    parola = (c.get("name") or "").split(" ")[0].lower()
    return _DOMINI.get(parola)


@dataclass
class Posizione:
    gs: GameState
    side: str            # il lato di chi registra
    seq: int
    avvisi: list = field(default_factory=list)
    nomi: dict = field(default_factory=dict)   # lato -> nome del giocatore


class _Costruttore:
    def __init__(self, partita: stati.Partita, seq: int | None, mazzo_avversario, seed: int):
        self.partita = partita
        self.rng = random.Random(seed)
        self.avvisi: list[str] = []
        self.mazzo_avversario = mazzo_avversario
        # Il tavolo alla seq, il turno in cui ogni coperta è arrivata sul
        # campo, e le carte dell'avversario viste in tutta la partita.
        self.turno_coperta: dict[str, int] = {}
        self.viste: dict[str, dict[str, str]] = {}   # pid -> id carta -> nome motore
        fine = partita.ultima_seq if seq is None else seq
        tavolo = None
        for s, t in stati.stati(partita):
            self._osserva(t)
            if s == fine:
                tavolo = t
                break
        if tavolo is None:
            raise ValueError(f"seq {seq} fuori dalla partita")
        self.t = tavolo
        self.unita: dict = {}   # id(UnitInPlay) -> (carta RiftAtlas, zona)
        self.lato = {p["id"]: ("A" if p["seat"] == 0 else "B") for p in tavolo.players}

    def _osserva(self, t: stati.Tavolo) -> None:
        turno = t.room.get("turnNumber") or 0
        for p in t.players:
            for zona in stati.ZONE_CAMPI:
                for c in p["board"].get(zona) or []:
                    if stati.nascosta(c):
                        self.turno_coperta.setdefault(c["id"], turno)
            for zona, carte in p["board"].items():
                if not isinstance(carte, list):
                    continue
                for c in carte:
                    if c.get("source") == "mainDeck" and not c.get("isPlaceholder"):
                        n = nome_motore(c)
                        if n:
                            pid = c.get("ownerPlayerId") or p["id"]
                            self.viste.setdefault(pid, {})[c["id"]] = n
        for e in t.chain:
            c = e.get("card") or {}
            pid = c.get("ownerPlayerId")
            if pid and c.get("source") == "mainDeck" and nome_motore(c):
                self.viste.setdefault(pid, {})[c.get("id")] = nome_motore(c)

    # ------------------------------------------------------------ carte

    def carta(self, c: dict):
        n = nome_motore(c)
        if n is None:
            self.avvisi.append(f"carta sconosciuta al motore: {c.get('name')!r} ({c.get('cardCode')})")
            return None
        card = CARD_REGISTRY[n].instantiate()
        if c.get("source") == "token":
            card.is_token = True
        if isinstance(card, GearCard):
            card.tapped = bool(c.get("exhausted"))
        return card

    def _lista(self, p: dict) -> tuple[list[str], Counter]:
        """(carte del mazzo principale, rune per dominio) della lista di p."""
        if p["id"] != self.partita.me and self.mazzo_avversario:
            path = Path(self.mazzo_avversario)
            if path.suffix.lower() == ".txt":
                return self._lista_txt(path)
            specs, rune, *_ = load_deck_json(path)
            return [s.name for s in specs], Counter({d: n for d, n in rune})
        sez = (p.get("deck") or {}).get("sections")
        if not sez:
            return [], Counter()
        carte = []
        for voce in sez.get("mainDeck") or []:
            n = nome_motore(voce)
            if n is None:
                self.avvisi.append(f"lista di {p['name']}: {voce.get('name')!r} sconosciuta al motore")
                continue
            carte += [n] * int(voce.get("count", 1))
        rune = Counter()
        for voce in sez.get("runes") or []:
            d = dominio_runa(voce)
            if d is not None:
                rune[d] += int(voce.get("count", 1))
        return carte, rune

    def _lista_txt(self, path: Path) -> tuple[list[str], Counter]:
        """Una lista come la esporta RiftMana ("MainDeck:", "Runes:", righe
        "N Nome"). Letta qui e non con `load_deck_json`, che rifiuta copie del
        campione scelto nel mazzo principale (§103.3.b.1 le permette)."""
        carte, rune, sezione = [], Counter(), None
        for riga in path.read_text(encoding="utf-8").splitlines():
            riga = riga.strip()
            if riga.endswith(":"):
                sezione = riga[:-1].strip().lower()
                continue
            m = re.match(r"(\d+)\s+(.+)", riga)
            if not m:
                continue
            n, nome = int(m.group(1)), m.group(2).strip()
            if sezione == "maindeck":
                k = nome_motore({"name": nome})
                if k is None:
                    self.avvisi.append(f"{path.name}: {nome!r} sconosciuta al motore")
                else:
                    carte += [k] * n
            elif sezione in ("runes", "rune pool"):
                d = dominio_runa({"name": nome})
                if d is not None:
                    rune[d] += n
        return carte, rune

    def coperte(self, p: dict, n: int, note: list[str]):
        """n carte per le zone coperte di p: la sua lista meno le carte note
        (`note`, nomi motore), se c'è; se no le carte del suo mazzo viste."""
        if n == 0:
            return []
        lista, _ = self._lista(p)
        if lista:
            resto = Counter(lista) - Counter(note)
            pool = sorted(resto.elements())
            if len(pool) != n:
                self.avvisi.append(f"{p['name']}: {n} carte coperte, la lista ne lascia "
                                   f"{len(pool)}: {'tolte' if len(pool) > n else 'aggiunte'} a caso")
        else:
            viste = sorted(Counter(self.viste.get(p["id"], {}).values()).elements())
            if not viste:
                raise ValueError(f"{p['name']}: nessuna carta del suo mazzo vista finora: "
                                 "serve --mazzo-avversario")
            pool = [viste[i % len(viste)] for i in range(n)]
            self.avvisi.append(
                f"{p['name']}: lista non disponibile, {n} carte coperte (mano, mazzo, coperte) "
                f"fatte con le {len(set(viste))} carte viste del suo mazzo: "
                + ", ".join(sorted(set(viste))))
        self.rng.shuffle(pool)
        while len(pool) < n:
            pool.append(pool[len(pool) % max(1, len(pool))] if pool else lista[0])
        return [CARD_REGISTRY[x].instantiate() for x in pool[:n]]

    # ------------------------------------------------------------ stato

    def costruisci(self) -> Posizione:
        t, r = self.t, self.t.room
        if r.get("phase") != "in_game":
            raise ValueError(f"seq {t.seq}: la partita non è in corso (fase {r.get('phase')})")
        if t.chain:
            self.avvisi.append(f"catena non vuota ({len(t.chain)} oggetti): ignorata")
        if r.get("pendingBattlefieldConquerAssist"):
            self.avvisi.append("conquista in corso su RiftAtlas: ignorata")
        me = self.partita.me
        side = self.lato[me]
        attivo = r.get("activeTurnPlayerId")
        if attivo != me or r.get("activeTurnStep") != "main":
            self.avvisi.append(f"non è il Main Phase di chi registra (attivo {attivo}, "
                               f"passo {r.get('activeTurnStep')}): il bot sceglie come se lo fosse")
        gs = GameState(rng=random.Random(self.rng.randrange(1 << 30)), A=Player(name="A"),
                       B=Player(name="B"), turn=int(r.get("turnNumber") or 1),
                       active=self.lato.get(attivo, side))
        gs.turns_taken = {self.lato[pid]: n for pid, n in (r.get("playerTurnCounts") or {}).items()}
        campi = stati.campi(t)
        ctrl = stati.controllo(t)
        gs.battlefields = []
        giocatori = sorted(t.players, key=lambda p: p["seat"])
        for (zona, _nome), p in zip(campi, giocatori):
            bf = Battlefield(card=self.carta({"name": p.get("selectedBattlefield"),
                                              "cardCode": p.get("selectedBattlefieldCardCode")}))
            if (r.get("battlefieldBrushByZone") or {}).get(zona):
                bf.replaced, bf.card = bf.card, CARD_REGISTRY["Brush"].instantiate()
            gs.battlefields.append(bf)
        segnati = r.get("battlefieldScoredThisTurnByPlayer") or {}
        for p in giocatori:
            self._giocatore(gs, p, campi)
            s = self.lato[p["id"]]
            mio = segnati.get(p["id"]) or {}
            if mio.get("turnNumber") == r.get("turnNumber"):
                for (zona, _), bf in zip(campi, gs.battlefields):
                    if mio.get(zona):
                        setattr(bf, f"scored_this_turn_{s}", True)
        for (zona, nome), bf in zip(campi, gs.battlefields):
            soli = {s for s in "AB" if bf._units_for(s)}
            chi = self.lato.get(ctrl.get(zona)) if ctrl.get(zona) else None
            if len(soli) == 1:
                if chi is not None and chi not in soli:
                    self.avvisi.append(f"{nome}: conquistato per ultimo da {chi}, ora ci sono solo unità di {soli}")
                chi = next(iter(soli))
            elif len(soli) == 2:
                self.avvisi.append(f"{nome}: unità di entrambi al Main Phase")
            bf.held_by = bf.last_controller = chi
            for fd in bf.facedowns:
                if fd.owner != chi:
                    self.avvisi.append(f"{nome}: coperta di {fd.owner} su un campo che non controlla")
        loop = GameLoop(gs)
        loop._recompute_passives()
        self._confronta_might(gs, campi)
        nomi = {self.lato[p["id"]]: p["name"] for p in giocatori}
        return Posizione(gs=gs, side=side, seq=t.seq, avvisi=self.avvisi, nomi=nomi)

    def _giocatore(self, gs: GameState, p: dict, campi) -> None:
        s = self.lato[p["id"]]
        b = p["board"]
        P = gs.get_player(s)
        mio = p["id"] == self.partita.me
        setattr(gs, f"points_{s}", int(b.get("score") or 0))
        setattr(gs, f"xp_{s}", int(b.get("legendXp") or 0))
        # Nomi motore delle carte del mazzo principale fuori dal mazzo (la
        # catena compresa: è ignorata, ma quelle carte non sono nel mazzo).
        note: list[str] = [nome_motore(e["card"]) for e in self.t.chain
                           if (e.get("card") or {}).get("ownerPlayerId") == p["id"]
                           and e["card"].get("source") == "mainDeck" and nome_motore(e["card"])]

        leg = b.get("legend") or []
        if leg:
            card = self.carta(leg[0])
            setattr(gs, f"legend_{s}", card)
            setattr(gs, f"legend_unit_{s}", UnitInPlay(card=card, ready=not leg[0].get("exhausted")))
        champ = b.get("champion") or []
        if champ:
            setattr(gs, f"champion_{s}", self.carta(champ[0]))

        def unita(c: dict, zona: str) -> UnitInPlay | None:
            card = self.carta(c)
            if card is None:
                return None
            u = UnitInPlay(card=card, ready=not c.get("exhausted"),
                           might_counters=int(c.get("temporaryMightBuff") or 0),
                           is_token=c.get("source") == "token")
            if c.get("source") == "champion":
                setattr(gs, f"champion_{s}", card)
                setattr(gs, f"champion_{s}_deployed", True)
            elif c.get("source") == "mainDeck":
                note.append(nome_motore(c))
            self.unita[id(u)] = (c, zona)
            return u

        def gear(c: dict, unita_per_id: dict, zona: str):
            card = self.carta(c)
            if card is None:
                return None
            if c.get("source") == "mainDeck":
                note.append(nome_motore(c))
            dove = unita_per_id.get(c.get("attachedToCardId"))
            if dove is not None:
                dove.gear.append(card)
                return None
            if c.get("attachedToCardId"):
                self.avvisi.append(f"{c.get('name')}: attaccata a una carta che non è in {zona}")
            return card

        def zona_con_unita(carte: list, zona: str):
            unita_per_id, units, gears, coperte = {}, [], [], []
            for c in carte:
                if stati.nascosta(c):
                    coperte.append(c)
                elif c.get("type") == "unit" or (c.get("type") is None and c.get("source") == "champion"):
                    u = unita(c, zona)
                    if u is not None:
                        unita_per_id[c["id"]] = u
                        units.append(u)
            for c in carte:
                if not stati.nascosta(c) and c.get("type", "").lower() == "gear":
                    g = gear(c, unita_per_id, zona)
                    if g is not None:
                        gears.append(g)
            altro = [c for c in carte if not stati.nascosta(c)
                     and c.get("type") not in ("unit", "gear", "Gear")]
            for c in altro:
                self.avvisi.append(f"{c.get('name')} ({c.get('type')}) in {zona}: ignorata")
            return units, gears, coperte

        units, gears, cop = zona_con_unita(b.get("base") or [], "base")
        P.base_units = units
        P.base_gear = gears
        if cop:
            self.avvisi.append(f"{p['name']}: {len(cop)} carte coperte in base: ignorate")

        coperte_campo = []   # (indice campo, carta RiftAtlas)
        for i, (zona, nome) in enumerate(campi):
            units, gears, cop = zona_con_unita(b.get(zona) or [], zona)
            bf = gs.battlefields[i]
            bf._units_for(s).extend(units)
            for g in gears:
                self.avvisi.append(f"{g.name} non attaccata a {nome}: ignorata")
            coperte_campo += [(i, c) for c in cop]

        for zona in ("trash", "banished"):
            out = []
            for c in b.get(zona) or []:
                if c.get("isPlaceholder"):
                    self.avvisi.append(f"{p['name']}: carta coperta in {zona}: ignorata")
                    continue
                card = self.carta(c)
                if card is not None:
                    out.append(card)
                    if c.get("source") == "mainDeck":
                        note.append(nome_motore(c))
            setattr(P, "trash" if zona == "trash" else "banished", out)

        mano = b.get("hand") or []
        mano_note = [c for c in mano if not c.get("isPlaceholder")]
        for c in mano_note:
            if c.get("source") == "mainDeck":
                note.append(nome_motore(c))
        for c in coperte_campo:
            if not c[1].get("isPlaceholder"):
                note.append(nome_motore(c[1]))
        n_mano_coperte = len(mano) - len(mano_note)
        n_campo_coperte = sum(1 for _, c in coperte_campo if c.get("isPlaceholder"))
        n_mazzo = len(b.get("deck") or [])
        riempite = self.coperte(p, n_mano_coperte + n_campo_coperte + n_mazzo, note)

        P.hand = []
        for c in mano:
            if c.get("isPlaceholder"):
                P.hand.append(riempite.pop())
            else:
                card = self.carta(c)
                if card is not None:
                    P.hand.append(card)
                    if c.get("revealedToOpponent") or b.get("handRevealToOpponent"):
                        P.hand_public.append(card)
        for i, c in coperte_campo:
            card = riempite.pop() if c.get("isPlaceholder") else self.carta(c)
            gs.battlefields[i].facedowns.append(
                FacedownCard(card=card, owner=s, turn_hidden=self.turno_coperta.get(c["id"], gs.turn)))
        P.deck.cards = riempite

        rune = b.get("runeArea") or []
        P.rune_pool = {}
        P.power_pool = {}
        pronte = 0
        for c in rune:
            d = dominio_runa(c)
            if d is None:
                self.avvisi.append(f"runa sconosciuta: {c.get('name')!r}")
                continue
            # Il motore spende da una riserva: le rune pronte sono la loro
            # Energia (rune_energy), ogni runa in gioco il suo Potere (riciclo).
            P.rune_pool.setdefault(d, []).append(Rune(domain=d, ready=False))
            P.power_pool[d] = P.power_pool.get(d, 0) + 1
            pronte += not c.get("exhausted")
        P.rune_energy = pronte
        P.pool_energy = int(b.get("floatingEnergy") or 0)
        if b.get("floatingPower"):
            self.avvisi.append(f"{p['name']}: {b['floatingPower']} Potere in sospeso, dominio "
                               "ignoto: ignorato")
        _, rune_lista = self._lista(p)
        resto = rune_lista - Counter(dominio_runa(c) for c in rune)
        n_rune = len(b.get("runeDeck") or [])
        domini = sorted(resto.elements(), key=lambda d: d.name)
        if len(domini) != n_rune:
            visti = sorted({dominio_runa(c) for c in rune} - {None}, key=lambda d: d.name) or [Domain.FURY]
            if rune_lista:
                self.avvisi.append(f"{p['name']}: mazzo delle rune {n_rune}, la lista ne lascia {len(domini)}")
            domini = [visti[i % len(visti)] for i in range(n_rune)]
        self.rng.shuffle(domini)
        P.rune_deck = RuneDeck(runes=[Rune(domain=d) for d in domini])

    def _confronta_might(self, gs: GameState, campi) -> None:
        for s in "AB":
            units = list(gs.get_player(s).base_units)
            for bf in gs.battlefields:
                units += bf._units_for(s)
            for u in units:
                c, zona = self.unita.get(id(u), ({}, "?"))
                segno = c.get("whiteCounter")
                if segno is not None and int(segno) != u.might:
                    self.avvisi.append(f"{u.card.name} ({zona}): Might {u.might} nel motore, "
                                       f"segnalino RiftAtlas {segno}")
                if c.get("customLabels"):
                    self.avvisi.append(f"{u.card.name} ({zona}): etichette RiftAtlas "
                                       f"{'/'.join(c['customLabels'])} (non lette)")


def costruisci(partita: stati.Partita, seq: int | None = None, *, mazzo_avversario=None,
               seed: int = 0) -> Posizione:
    return _Costruttore(partita, seq, mazzo_avversario, seed).costruisci()


class _Bot(HandwrittenAgent):
    """Il bot a mano che tiene la radice dell'ultima ricerca."""
    radice = None

    def search(self, point, legal, **kw):
        self.radice = super().search(point, legal, **kw)
        return self.radice


@dataclass
class Proposta:
    azione: tuple
    etichetta: str
    alternative: list   # (etichetta, visite, valore), la scelta prima
    legali: list        # etichette


def proponi(pos: Posizione, *, budget: float = 2.0, seed: int = 0) -> Proposta:
    """La prima azione del turno secondo il bot a mano, su una copia."""
    gs = pos.gs.clone()
    me, altro = gs.get_player(pos.side), gs.get_player(gs.other(pos.side))
    bot = _Bot(me, budget=budget, rng=random.Random(seed))
    me.agent = bot
    altro.agent = HandwrittenAgent(altro, budget=budget, rng=random.Random(seed + 1))
    loop = GameLoop(gs)
    legal = legal_actions(loop, DecisionPoint.TURN_ACTION, pos.side)
    etichette = {a.to_engine(): a.label for a in legal}
    azione = bot.decide_action(altro, cards_played=gs.cards_played_this_turn.get(pos.side, 0))
    alt = []
    if bot.radice is not None:
        # Come sceglie il bot (backup "best"): il valore più alto fra le visitate.
        figli = sorted(bot.radice.children.items(), key=lambda kv: (kv[1].N == 0, -kv[1].Q))
        alt = [(etichette.get(k, str(k)), c.N, round(c.Q, 3)) for k, c in figli]
    return Proposta(azione=azione, etichetta=etichette.get(azione, str(azione)),
                    alternative=alt, legali=[a.label for a in legal])


def descrivi(pos: Posizione) -> str:
    gs = pos.gs
    righe = [f"Motore, seq {pos.seq}: turno {gs.turn}, attivo {gs.active}"
             f" ({pos.nomi.get(gs.active)}), io = {pos.side} ({pos.nomi.get(pos.side)})",
             f"Punti A {gs.points_A} – B {gs.points_B}"]

    def us(units):
        return ", ".join(f"{u.card.name} {u.might}{'' if u.ready else ' esausta'}"
                         + (f" [{'+'.join(g.name for g in u.gear)}]" if u.gear else "")
                         for u in units) or "—"
    for i, bf in enumerate(gs.battlefields):
        nome = bf.card.name if bf.card else "?"
        if bf.replaced is not None:
            nome += f" (al posto di {bf.replaced.name})"
        fd = ", ".join(f"coperta di {f.owner} dal turno {f.turn_hidden}" for f in bf.facedowns)
        righe.append(f"BF{i} {nome}: controllo {bf.held_by or '—'}"
                     + (f", {fd}" if fd else ""))
        righe.append(f"  A: {us(bf.units_A)}")
        righe.append(f"  B: {us(bf.units_B)}")
    for s in "AB":
        P = gs.get_player(s)
        righe.append(f"{s}: base {us(P.base_units)}; gear {len(P.base_gear)}; mano {len(P.hand)}"
                     f"; mazzo {len(P.deck.cards)}; energia {P.energy}; potere "
                     + ", ".join(f"{d.name} {n}" for d, n in P.power_pool.items()))
    return "\n".join(righe)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("seq", nargs="?", type=int)
    ap.add_argument("--budget", type=float, default=2.0, help="secondi di CPU per la ricerca")
    ap.add_argument("--mazzo-avversario")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    partita = stati.carica(a.file)
    pos = costruisci(partita, a.seq, mazzo_avversario=a.mazzo_avversario, seed=a.seed)
    print(descrivi(pos))
    if pos.avvisi:
        print("Avvisi:")
        for x in pos.avvisi:
            print(f"  - {x}")
    prop = proponi(pos, budget=a.budget, seed=a.seed)
    print(f"Mossa del bot: {prop.etichetta}")
    for et, n, q in prop.alternative[:8]:
        print(f"  {n:5d} visite  valore {q:+.3f}  {et}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
