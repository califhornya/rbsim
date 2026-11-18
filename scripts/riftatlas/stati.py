"""Stato del tavolo RiftAtlas a ogni modifica, da un file del registratore.

Uso: python scripts/riftatlas/stati.py <file.json> [seq]
     (senza seq: l'ultima; seq 0 = l'istantanea iniziale)

Il file (`registratore.js`, chiavi `me`, `room`, `net`) contiene i messaggi
WebSocket della partita. Si parte da `authoritative_snapshot` (`msg.snapshot`)
e si applicano in ordine di `seq` le `authoritative_patch_commit`
(`msg.patch.operations`). RiftAtlas è un tavolo manuale, non un motore: lo
stato è quello che i giocatori hanno messo sul tavolo (Might, controllo e
punteggio non sono calcolati da regole). Le carte nascoste arrivano come
segnaposto (`__hidden_zone__`, `isPlaceholder`) e restano tali.

Zone di una plancia: deck, hand, base, trash, banished, battlefieldA/B/C,
battlefieldToken, champion, legend, runeDeck, runeArea. In duello
battlefieldA è il campo scelto dal posto 0, battlefieldB quello del posto 1
(verificato sui log di 82FAW: "moved ... to Bandle Scouts' Academy").
"""
from __future__ import annotations

import copy
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARDS = ROOT / "riftbound" / "data" / "cards" / "all_cards.json"

ZONE_CAMPI = ("battlefieldA", "battlefieldB", "battlefieldC")


# ---------------------------------------------------------------- carte

_INDICE: dict | None = None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _indice() -> dict:
    global _INDICE
    if _INDICE is None:
        per_codice, per_nome = {}, {}
        for c in json.loads(CARDS.read_text(encoding="utf-8")):
            per_codice.setdefault(c["card_id"], c)
            for v in c.get("variants") or []:
                per_codice.setdefault(v["variant_id"], c)
            per_nome.setdefault(_norm(c["name"]), c)
        _INDICE = {"codice": per_codice, "nome": per_nome}
    return _INDICE


def dati_carta(carta: dict) -> dict | None:
    """La carta del motore (all_cards.json) per una carta RiftAtlas:
    per codice, poi per nome (i codici RiftAtlas hanno varianti come
    UNL-051A o RAD-157P che i dati non sempre elencano)."""
    idx = _indice()
    codice = carta.get("cardCode")
    if codice and codice in idx["codice"]:
        return idx["codice"][codice]
    nome = carta.get("name")
    if nome:
        return idx["nome"].get(_norm(nome))
    return None


# ---------------------------------------------------------------- stato

@dataclass
class Tavolo:
    seq: int
    room: dict  # campi della stanza (phase, turnNumber, activeTurnPlayerId...)
    players: list  # dict con id, seat, name, board, selectedBattlefield...
    chain: list = field(default_factory=list)
    log: list = field(default_factory=list)  # più recente per primo

    def player(self, pid: str) -> dict:
        for p in self.players:
            if p["id"] == pid:
                return p
        raise KeyError(pid)

    def zona(self, pid: str, zone: str) -> list:
        return self.player(pid)["board"].setdefault(zone, [])


def _trova(zona: list, card_id: str) -> int:
    for i, c in enumerate(zona):
        if c["id"] == card_id:
            return i
    raise KeyError(card_id)


def applica(t: Tavolo, op: dict) -> None:
    kind = op["op"]
    if kind == "set_room_fields":
        t.room.update(copy.deepcopy(op["fields"]))
    elif kind == "unset_room_fields":
        for f in op["fields"]:
            t.room.pop(f, None)
    elif kind == "set_player_fields":
        t.player(op["playerId"]).update(copy.deepcopy(op["fields"]))
    elif kind == "set_board_fields":
        t.player(op["playerId"])["board"].update(copy.deepcopy(op["fields"]))
    elif kind == "zone_insert":
        z = t.zona(op["playerId"], op["zone"])
        for k, c in enumerate(op["cards"]):
            z.insert(op["index"] + k, copy.deepcopy(c))
    elif kind == "zone_remove":
        z = t.zona(op["playerId"], op["zone"])
        via = set(op["cardIds"])
        mancano = via - {c["id"] for c in z}
        if mancano:
            raise KeyError(f"zone_remove {op['zone']}: {sorted(mancano)}")
        z[:] = [c for c in z if c["id"] not in via]
    elif kind == "zone_reorder":
        z = t.zona(op["playerId"], op["zone"])
        per_id = {c["id"]: c for c in z}
        if set(per_id) != set(op["cardIds"]) or len(z) != len(op["cardIds"]):
            raise ValueError(f"zone_reorder {op['zone']}: carte diverse")
        z[:] = [per_id[i] for i in op["cardIds"]]
    elif kind == "zone_move":
        src = t.zona(op["from"]["playerId"], op["from"]["zone"])
        carta = src.pop(_trova(src, op["cardId"]))
        if "card" in op:  # la carta come è dopo lo spostamento
            carta = copy.deepcopy(op["card"])
        dst = t.zona(op["to"]["playerId"], op["to"]["zone"])
        dst.insert(op["to"].get("index", len(dst)), carta)
    elif kind == "patch_card_fields":
        z = t.zona(op["playerId"], op["zone"])
        z[_trova(z, op["cardId"])].update(copy.deepcopy(op["fields"]))
    elif kind == "unset_card_fields":
        z = t.zona(op["playerId"], op["zone"])
        c = z[_trova(z, op["cardId"])]
        for f in op["fields"]:
            c.pop(f, None)
    elif kind == "chain_insert":
        for k, e in enumerate(op["entries"]):
            t.chain.insert(op["index"] + k, copy.deepcopy(e))
    elif kind == "chain_remove":
        via = set(op["entryIds"])
        t.chain[:] = [e for e in t.chain if e["id"] not in via]
    elif kind == "log_insert":
        for k, e in enumerate(op["entries"]):
            t.log.insert(op["index"] + k, copy.deepcopy(e))
    elif kind == "log_remove":
        via = set(op["entryIds"])
        t.log[:] = [e for e in t.log if e["id"] not in via]
    else:
        raise ValueError(f"operazione sconosciuta: {kind}")


@dataclass
class Partita:
    me: str
    room: str
    snapshot: dict  # msg dell'authoritative_snapshot
    patches: list  # msg delle authoritative_patch_commit, in ordine di seq

    @property
    def ultima_seq(self) -> int:
        return self.patches[-1]["sequence"] if self.patches else self.snapshot["sequence"]


def _messaggi(net: list) -> list[dict]:
    """I messaggi del server, decodificati. Due formati del registratore: quello
    usato dal vivo (18/11) tiene il messaggio già letto (`type`, `msg`); la
    prima bozza solo la stringa ricevuta (`data`)."""
    out = []
    for m in net:
        msg = m.get("msg")
        if msg is None and isinstance(m.get("data"), str):
            try:
                msg = json.loads(m["data"])
            except ValueError:
                continue
        if isinstance(msg, dict):
            out.append({"dir": m.get("dir"), "type": msg.get("type"), "msg": msg})
    return out


def _chi_registra(d: dict, messaggi: list[dict]) -> str:
    """Il giocatore che registra: `me` nel file, se no il `viewer` della
    stanza o chi manda le azioni."""
    if d.get("me"):
        return d["me"]
    for m in messaggi:
        viewer = (m["msg"].get("sessionDoc") or {}).get("viewer") or {}
        if m["type"] == "room_shell_sync" and viewer.get("playerId"):
            return viewer["playerId"]
    for m in messaggi:
        if m["dir"] == "out" and m["msg"].get("actorPlayerId"):
            return m["msg"]["actorPlayerId"]
    return ""


def carica(path: str | Path) -> Partita:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    net = _messaggi(d["net"])
    snaps = [m["msg"] for m in net if m["type"] == "authoritative_snapshot"]
    if not snaps:
        raise ValueError("nessun authoritative_snapshot nel file")
    if len(snaps) > 1:  # una riconnessione: si riparte dall'ultima
        snaps.sort(key=lambda s: s["sequence"])
    snap = snaps[-1]
    patches = sorted((m["msg"] for m in net
                      if m["type"] == "authoritative_patch_commit"
                      and m["msg"]["sequence"] > snap["sequence"]),
                     key=lambda p: p["sequence"])
    atteso = snap["sequence"]
    for p in patches:
        if p["baseSequence"] != atteso:
            raise ValueError(f"buco nelle patch: seq {p['sequence']} parte da "
                             f"{p['baseSequence']}, atteso {atteso}")
        atteso = p["sequence"]
    return Partita(me=_chi_registra(d, net), room=d.get("room") or snap.get("gameInstanceId", ""),
                   snapshot=snap, patches=patches)


def iniziale(partita: Partita) -> Tavolo:
    s = copy.deepcopy(partita.snapshot["snapshot"])
    players = s.pop("players")
    chain = s.pop("chainEntries", [])
    return Tavolo(seq=partita.snapshot["sequence"], room=s, players=players,
                  chain=chain, log=copy.deepcopy(partita.snapshot.get("gameplayLog") or []))


def stati(partita: Partita):
    """Il tavolo dopo ogni modifica: (seq, Tavolo), a partire dall'istantanea.
    Il Tavolo è lo stesso oggetto aggiornato: copiarlo per tenerlo."""
    t = iniziale(partita)
    yield t.seq, t
    for p in partita.patches:
        for op in p["patch"]["operations"]:
            applica(t, op)
        t.seq = p["sequence"]
        yield t.seq, t


def stato_a(partita: Partita, seq: int | None = None) -> Tavolo:
    seq = partita.ultima_seq if seq is None else seq
    for s, t in stati(partita):
        if s == seq:
            return t
    raise ValueError(f"seq {seq} fuori da {partita.snapshot['sequence']}..{partita.ultima_seq}")


# ---------------------------------------------------------------- vista

def nascosta(c: dict) -> bool:
    """Coperta per l'avversario: segnaposto, o carta propria con `hidden`."""
    return bool(c.get("isPlaceholder")) or bool(c.get("hidden"))


def might(c: dict, equip: list[dict] = ()) -> int | None:
    """Might da carta stampata + buff (`temporaryMightBuff`) + equipaggiamenti.
    I modificatori fuori da questi (effetti, segnalini) RiftAtlas non li sa."""
    dati = dati_carta(c)
    if not dati or dati.get("might") is None:
        return None
    m = dati["might"] + int(c.get("temporaryMightBuff") or 0)
    for g in equip:
        gd = dati_carta(g)
        if gd and gd.get("might"):
            m += gd["might"]
    return m


def campi(t: Tavolo) -> list[tuple[str, str]]:
    """(zona, nome del campo) in ordine di posto; Brush se sostituito."""
    brush = t.room.get("battlefieldBrushByZone") or {}
    out = []
    for p, zona in zip(sorted(t.players, key=lambda p: p["seat"]), ZONE_CAMPI):
        nome = p.get("selectedBattlefield") or "?"
        if brush.get(zona):
            nome = f"Brush (al posto di {nome})"
        out.append((zona, nome))
    return out


def controllo(t: Tavolo) -> dict[str, str | None]:
    """Chi ha conquistato per ultimo ogni campo, dal log (RiftAtlas non tiene
    il controllo come campo). None se nessuno."""
    nomi = {p["name"]: p["id"] for p in t.players}
    per_nome = {}
    for p, zona in zip(sorted(t.players, key=lambda p: p["seat"]), ZONE_CAMPI):
        per_nome[p.get("selectedBattlefield")] = zona
    out = {z: None for z, _ in campi(t)}
    for e in reversed(t.log):  # dal più vecchio
        m = re.match(r"(.+?) conquered (.+?) and scored", e.get("text", ""))
        if m and m.group(2) in per_nome and m.group(1) in nomi:
            out[per_nome[m.group(2)]] = nomi[m.group(1)]
    return out


def _unita(zona: list[dict]) -> list[tuple[dict, list[dict]]]:
    """Le carte di una zona con i loro equipaggiamenti (`attachedToCardId`)."""
    attaccati: dict[str, list] = {}
    for c in zona:
        if c.get("attachedToCardId"):
            attaccati.setdefault(c["attachedToCardId"], []).append(c)
    ids = {c["id"] for c in zona}
    return [(c, attaccati.get(c["id"], [])) for c in zona
            if not (c.get("attachedToCardId") and c["attachedToCardId"] in ids)]


def _descr_carta(c: dict, equip: list[dict], mia: bool) -> str:
    if c.get("isPlaceholder"):
        return "coperta"
    nome = c.get("name") or "?"
    if c.get("hidden"):
        return f"coperta ({nome})" if mia else "coperta"
    pezzi = [nome]
    m = might(c, equip)
    if m is not None:
        pezzi.append(f"M{m}")
    if c.get("temporaryMightBuff"):
        pezzi.append(f"buff+{c['temporaryMightBuff']}")
    if c.get("whiteCounter"):
        pezzi.append(f"segnalino {c['whiteCounter']}")
    if c.get("customLabels"):
        pezzi.append("/".join(c["customLabels"]))
    if c.get("exhausted"):
        pezzi.append("esausta")
    s = " ".join(pezzi)
    if equip:
        s += " + " + ", ".join(g.get("name") or "?" for g in equip)
    return s


def _lista(zona: list[dict], mia: bool) -> str:
    voci = [_descr_carta(c, eq, mia) for c, eq in _unita(zona)]
    return "; ".join(voci) if voci else "—"


def _rune(zona: list[dict]) -> str:
    pronte = [c.get("name", "?").replace(" Rune", "") for c in zona if not c.get("exhausted")]
    esauste = [c.get("name", "?").replace(" Rune", "") for c in zona if c.get("exhausted")]
    return (f"{len(pronte)} pronte ({', '.join(pronte) or '—'}), "
            f"{len(esauste)} esauste ({', '.join(esauste) or '—'})")


def descrivi(t: Tavolo, me: str) -> str:
    giocatori = sorted(t.players, key=lambda p: p["seat"])
    nome = {p["id"]: p["name"] for p in giocatori}
    r = t.room
    righe = [f"seq {t.seq} · fase {r.get('phase', '?')} · turno {r.get('turnNumber', '-')}"
             f" · attivo {nome.get(r.get('activeTurnPlayerId'), '-')}"
             f" ({r.get('activeTurnStep', '-')})"]
    righe.append("Punteggio: " + " – ".join(f"{p['name']} {p['board'].get('score', 0)}"
                                             for p in giocatori))
    ctrl = controllo(t)
    for zona, nome_campo in campi(t):
        c = ctrl.get(zona)
        righe.append(f"Campo {nome_campo} [{zona}]"
                     f" · ultimo a conquistare: {nome[c] if c else '—'}")
        for p in giocatori:
            z = p["board"].get(zona) or []
            coperte = sum(1 for x in z if nascosta(x))
            extra = f" · coperte {coperte}" if coperte else ""
            righe.append(f"  {p['name']}: {_lista(z, p['id'] == me)}{extra}")
    for p in giocatori:
        b = p["board"]
        mia = p["id"] == me
        righe.append(f"{p['name']}{' (io)' if mia else ''}:")
        righe.append(f"  base: {_lista(b.get('base') or [], mia)}")
        righe.append(f"  rune: {_rune(b.get('runeArea') or [])}"
                     f" · mazzo rune {len(b.get('runeDeck') or [])}")
        if b.get("floatingEnergy") or b.get("floatingPower"):
            righe.append(f"  in sospeso: energia {b.get('floatingEnergy', 0)},"
                         f" potere {b.get('floatingPower', 0)}")
        mano = b.get("hand") or []
        if mia:
            righe.append(f"  mano {len(mano)}: " + ", ".join(c.get("name", "?") for c in mano))
        else:
            aperta = b.get("handRevealToOpponent")
            visibili = [c["name"] for c in mano if not c.get("isPlaceholder") and c.get("name")
                        and (aperta or c.get("revealedToOpponent"))]
            righe.append(f"  mano {len(mano)}" + (f" (viste: {', '.join(visibili)})" if visibili else ""))
        righe.append(f"  mazzo {len(b.get('deck') or [])}"
                     f" · cimitero {len(b.get('trash') or [])}"
                     f" · bandite {len(b.get('banished') or [])}")
        leg = b.get("legend") or []
        champ = b.get("champion") or []
        righe.append(f"  leggenda: {_lista(leg, mia)} · campione: {_lista(champ, mia)}")
        if b.get("trash"):
            righe.append("  cimitero: " + ", ".join(c.get("name", "?") for c in b["trash"]))
    if t.chain:
        righe.append("Catena: " + "; ".join(
            f"{nome.get(e['card'].get('ownerPlayerId'), '?')}: {e['card'].get('name', '?')}"
            for e in t.chain))
    return "\n".join(righe)


def main(argv: list[str]) -> int:
    if not argv or len(argv) > 2:
        print(__doc__.split("\n\n")[1])
        return 2
    partita = carica(argv[0])
    seq = int(argv[1]) if len(argv) > 1 else None
    print(descrivi(stato_a(partita, seq), partita.me))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
