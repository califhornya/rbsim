"""Coaching the net: it plays, a person decides.

A `CoachSession` runs one game at a time on a background thread. The coached
seat is a `CoachAgent`: at each of its decisions with more than one option it
searches as usual, then waits for the coach to accept one of the net's top
moves or pick any legal one. A move the coach picked asks the coach for the
choices inside it too (a target, a mode, ...). Every coached decision becomes a
training example whose policy target is the coach's move; when the game ends
they are saved with its result (coach_<time>.npz in the session's directory),
for `selfplay.train(coach_dir=...)` to mix into its batches. The coach can also
file a report on what they see (reports.jsonl): rule bugs, odd plays.

The web page in scripts/coach.py drives a session through `state()`,
`answer()`, `new_game()`, `report()` and `abandon()`. It draws the board as a
table of card images: every action, suggestion and choice it gets carries an
Italian description and the place on the table it refers to (a "ref": hand:2,
unit:me:base:0, unit:opp:1:2, legend:me, champion:me, gear:me:base:0, bf:1,
base:opp, facedown:0:0, trash:me, banished:me), and the session keeps a log of
the game in Italian (the engine's own English log stays, for reports).
"""

from __future__ import annotations

import json
import queue
import random
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Optional

import numpy as np

from riftbound.ai.encoding import ACTION_DIM, action_to_index, encode_observation, legal_mask
from riftbound.ai.net_mcts import _PASS, NetGuidedMCTSAgent, _ForcedChoice, _split_key
from riftbound.core.decisions import DecisionPoint, Observation
from riftbound.core.legality import legal_actions
from riftbound.core.loop import NO_MORE
from riftbound.registry.cards_registry import CARD_REGISTRY

CARDS_JSON = Path(__file__).resolve().parents[1] / "data" / "cards" / "all_cards.json"


class _ThreadLog:
    """sys.stdout that sends the game thread's prints (the engine's verbose
    log) to its session and everything else to the real stdout."""

    def __init__(self, real):
        self.real = real
        self.sinks: dict = {}          # thread ident -> deque of lines

    def write(self, text: str) -> int:
        sink = self.sinks.get(threading.get_ident())
        if sink is None:
            return self.real.write(text)
        for line in text.splitlines():
            if line.strip():
                sink.append(line.rstrip())
        return len(text)

    def flush(self) -> None:
        self.real.flush()


def _thread_log() -> _ThreadLog:
    if not isinstance(sys.stdout, _ThreadLog):
        sys.stdout = _ThreadLog(sys.stdout)
    return sys.stdout


# -- describing the game for the page, in Italian -------------------------------

_TYPES = {"UNIT": "unità", "SPELL": "magia", "GEAR": "equipaggiamento", "RUNE": "runa",
          "LEGEND": "leggenda", "CHAMPION": "campione", "BATTLEFIELD": "campo di battaglia"}

_QUESTIONS = {
    "target": "Scegli il bersaglio", "mode": "Quale effetto usare?",
    "equip": "Su quale unità attaccare l'equipaggiamento?",
    "combat_damage_order": "Quale unità nemica colpire per prima in combattimento?",
    "cost_unit": "Quale unità usare per pagare il costo?", "discard": "Quale carta scartare?",
    "destination": "Dove spostare l'unità?", "deploy": "Dove schierare l'equipaggiamento?",
    "domain": "Di quale dominio prendere il Power?", "keep": "Quale carta tenere?",
    "predict_recycle": "Mandare in fondo al mazzo questa carta?", "card": "Quale carta?",
    "predict_order": "Quale carta rimettere in cima (la prima scelta si pesca per prima)?",
    "trigger_order": "Quale abilità innescata risolvere per prima (le altre dopo, nell'ordine scelto)?",
    "show_off": "Cosa mostrare (SHOW OFF)?", "disarm": "Quale nemico indebolire (DISARM)?",
    "spend_buff": "Quale buff spendere?", "cost_banish": "Quale carta del cimitero bandire?",
    "cost_extras": "Quanto spendere per ridurre il costo?",
    "first_unit_here": "Quale unità rimandare in base?",
    "player": "Quale giocatore scegliere?",
    "token_location": "Dove giocare il token?",
    "battlefield": "Quale campo di battaglia scegliere?", "tag": "Quale tag scegliere?",
}
# The same choices in a few words, after a suggested move ("→ bersaglio: Zed").
_SHORT = {"target": "bersaglio", "mode": "effetto", "equip": "su", "combat_damage_order":
          "in combattimento colpisce prima", "cost_unit": "paga con", "discard": "scarta",
          "destination": "verso", "deploy": "schiera su", "domain": "Power",
          "keep": "tiene", "card": "carta", "predict_order": "in cima", "trigger_order": "prima",
          "show_off": "mostra", "disarm": "indebolisce",
          "spend_buff": "spende il buff di", "cost_banish": "bandisce",
          "first_unit_here": "rimanda in base", "player": "giocatore", "token_location": "token in",
          "battlefield": "campo", "tag": "tag"}
_OPTIONAL = {"accelerate": "Pagare ACCELERATE? (l'unità entra pronta)",
             "additional_cost": "Pagare il costo aggiuntivo?", "SHOW OFF": "Usare SHOW OFF?",
             "enter_ready": "Far entrare l'unità pronta?"}


def question(kind: str) -> str:
    head, _, rest = kind.partition(":")
    if head == "optional":
        return _OPTIONAL.get(rest, "Usare questo effetto?")
    return _QUESTIONS.get(head, kind)


def _rel(side: str, viewer: str) -> str:
    return "me" if side == viewer else "opp"


def _bf_name(gs, i: int) -> str:
    return _view_bf_names([{"named": b.card.name if b.card is not None else None}
                           for b in gs.battlefields])[i]


def _unit_ref(gs, viewer: str, unit) -> Optional[str]:
    for side in ("A", "B"):
        rel = _rel(side, viewer)
        for i, bf in enumerate(gs.battlefields):
            for j, u in enumerate(bf._units_for(side)):
                if u is unit:
                    return f"unit:{rel}:{i}:{j}"
        for j, u in enumerate(gs.get_player(side).base_units):
            if u is unit:
                return f"unit:{rel}:base:{j}"
        if (gs.legend_unit_A if side == "A" else gs.legend_unit_B) is unit:
            return f"legend:{rel}"
        for k, (lu, _neeko) in enumerate(gs.added_legends[side]):
            if lu is unit:
                return f"legend:{rel}:{k + 1}"
    return None


def _card_ref(gs, viewer: str, card) -> Optional[str]:
    for side in ("A", "B"):
        rel, p = _rel(side, viewer), gs.get_player(side)
        if side == viewer:
            for i, c in enumerate(p.hand):
                if c is card:
                    return f"hand:{i}"
        for i, g in enumerate(p.base_gear):
            if g is card:
                return f"gear:{rel}:base:{i}"
        for i, bf in enumerate(gs.battlefields):
            for j, dg in enumerate(bf.gear_for(side)):
                if dg.card is card:
                    return f"gear:{rel}:{i}:{j}"
            for j, fd in enumerate(bf.facedowns):
                if fd.card is card:
                    return f"facedown:{i}:{j}"
        for u in [*p.base_units, *(u for bf in gs.battlefields for u in bf._units_for(side))]:
            if u.card is card or any(g is card for g in u.gear):
                return _unit_ref(gs, viewer, u)
        if any(c is card for c in p.trash):
            return f"trash:{rel}"
        if any(c is card for c in p.banished):
            return f"banished:{rel}"
        if (gs.champion_A if side == "A" else gs.champion_B) is card:
            return f"champion:{rel}"
    return None


def option_ref(gs, viewer: str, option) -> Optional[str]:
    """Where a choice's option is on the table (None: not on it)."""
    from riftbound.core.combat import UnitInPlay
    if isinstance(option, tuple) and option and isinstance(option[-1], UnitInPlay):
        option = option[-1]
    if isinstance(option, UnitInPlay):
        return _unit_ref(gs, viewer, option)
    i = next((i for i, bf in enumerate(gs.battlefields) if bf is option), None)
    if i is not None:
        return f"bf:{i}"
    if hasattr(option, "cost_energy"):
        return _card_ref(gs, viewer, option)
    return None


def option_text(gs, viewer: str, option) -> str:
    """A choice's option, as `viewer` reads it."""
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.state import ChainItem, PendingTrigger
    if isinstance(option, PendingTrigger):     # a triggered ability to order
        return f"abilità di {option.card.name}"
    if isinstance(option, tuple) and option and isinstance(option[-1], UnitInPlay):
        option = option[-1]
    if isinstance(option, ChainItem):          # on the chain (a counter's target)
        whose = "tua" if option.player == viewer else "avversaria"
        what = "abilità" if option.ability is not None else "magia"
        return f"{option.card.name} ({what} {whose} sulla catena)"
    if isinstance(option, UnitInPlay):
        ref = (_unit_ref(gs, viewer, option) or "unit:opp:base").split(":")
        whose = "tua" if ref[1] == "me" else "avversaria"
        at = "leggenda" if ref[0] == "legend" else "in base" if ref[2] == "base" else \
            f"su {_bf_name(gs, int(ref[2]))}"
        return f"{option.card.name} ({whose}, Might {option.might}, {at})"
    i = next((i for i, bf in enumerate(gs.battlefields) if bf is option), None)
    if i is not None:
        return _bf_name(gs, i)
    if option is None:                     # a place choice: None is the base
        return "Base"
    if option is NO_MORE:                  # "up to N": stop picking
        return "Nessun altro"
    if isinstance(option, bool):
        return "Sì" if option else "No"
    if option is gs.A or option is gs.B:
        return "Tu" if option.name == viewer else "L'avversario"
    if hasattr(option, "cost_energy"):
        kind = _TYPES.get(getattr(getattr(option, "category", None), "name", ""), "carta")
        return f"{option.name} ({kind}, costo {option.cost_energy or 0})"
    if isinstance(option, tuple):
        return str(getattr(option[0], "name", option[0]))
    if isinstance(option, int):
        return f"Effetto {option + 1}"
    return str(getattr(option, "name", option)).title()


def _chosen_text(gs, viewer: str, got) -> str:
    """A choice's answer in words: one option, or several ("up to two")."""
    if isinstance(got, list):
        return ", ".join(option_text(gs, viewer, o) for o in got) or "nessuno"
    return option_text(gs, viewer, got)


def chain_name(item) -> str:
    """A chain item's name: its card's, an ability's with its source's."""
    return f"abilità di {item.card.name}" if item.ability is not None else item.card.name


def declared_text(gs, viewer: str, item) -> str:
    """What a spell on the chain chose as it was played (its targets, mode,
    where it moves), as `viewer` reads it: "bersaglio: Zed (tua, ...)"."""
    parts = []
    for slot in sorted(item.declared or {}):
        kind, _, got = item.declared[slot]
        parts.append(f"{_SHORT.get(kind.partition(':')[0], 'scelta')}: {_chosen_text(gs, viewer, got)}")
    return ", ".join(parts)


def mulligan_text(hand: list, back: list) -> str:
    """A mulligan in words: the cards (names) sent back from `hand`."""
    if not back:
        return "Tieni tutta la mano"
    return "Rimanda " + " e ".join(hand[i] for i in back)


_PASS_TEXT = {DecisionPoint.TURN_ACTION: "Passa: hai finito le tue azioni",
              DecisionPoint.SHOWDOWN_ACTION: "Passa", DecisionPoint.REACTION: "Non reagire"}


def action_info(loop, side: str, viewer: str, point: DecisionPoint, action) -> dict:
    """An engine action tuple for the page: its Italian text and where it goes
    from and to on the table (refs, as `viewer` sees it). A card `side` hides
    stays unnamed for the other player."""
    gs = loop.gs
    kind, idx, lane = action[0], action[1], action[2]
    dst = action[3] if len(action) > 3 else None
    p, rel, n_bf = gs.get_player(side), _rel(side, viewer), len(gs.battlefields)
    card = p.hand[idx] if kind in ("UNIT", "SPELL", "GEAR", "HIDE") and isinstance(idx, int) \
        and 0 <= idx < len(p.hand) else None
    name = card.name if card is not None else "?"
    src = f"hand:{idx}" if card is not None and side == viewer else None
    if kind == "HIDE" and idx == "champion":            # from the Champion Zone
        champ = gs.champion_A if side == "A" else gs.champion_B
        name, src = (champ.name if champ is not None else "?"), f"champion:{rel}"
    to = None
    moving = gs.pending_move if gs.pending_move is not None and gs.pending_move[1] == side else None
    if kind == "PASS" and moving is not None and point == DecisionPoint.TURN_ACTION:
        text = f"Fatto: parte lo showdown su {_bf_name(gs, moving[0])}"
    elif kind == "PASS":
        text = _PASS_TEXT.get(point, "Passa")
    elif kind == "UNIT":
        if dst is None or dst == n_bf:
            text, to = f"Gioca {name} in base", f"base:{rel}"
        else:
            how = "" if point == DecisionPoint.TURN_ACTION else " con AMBUSH"
            text, to = f"Gioca {name}{how} su {_bf_name(gs, dst)}", f"bf:{dst}"
    elif kind == "SPELL":
        text, to = f"Lancia {name} (campo: {_bf_name(gs, lane)})", f"bf:{lane}"
    elif kind == "GEAR":
        if card is not None and card.has_keyword("DEPLOY"):
            text, to = f"Gioca l'equipaggiamento {name} su {_bf_name(gs, lane)}", f"bf:{lane}"
        else:
            text, to = f"Gioca l'equipaggiamento {name}", f"base:{rel}"
    elif kind == "CHAMPION":
        champ = gs.champion_A if side == "A" else gs.champion_B
        name, src = getattr(champ, "name", "?"), f"champion:{rel}"
        if point == DecisionPoint.TURN_ACTION:
            text, to = f"Gioca il campione {name}", f"base:{rel}"
        else:
            text, to = f"Gioca il campione {name} con AMBUSH su {_bf_name(gs, lane)}", f"bf:{lane}"
    elif kind == "MOVE":
        units = p.base_units if lane == n_bf else gs.battlefields[lane]._units_for(side)
        j = idx if isinstance(idx, int) and idx < len(units) else \
            next((k for k, u in enumerate(units) if u.ready), 0)
        unit = units[j].card.name if j < len(units) else "?"
        src = f"unit:{rel}:{'base' if lane == n_bf else lane}:{j}"
        frm = "dalla base" if lane == n_bf else f"da {_bf_name(gs, lane)}"
        verb = "Manda anche" if moving is not None and moving[0] == dst else "Sposta"
        text = f"{verb} {unit} {frm} " + ("alla base" if dst == n_bf else f"a {_bf_name(gs, dst)}")
        to = f"base:{rel}" if dst == n_bf else f"bf:{dst}"
    elif kind == "HIDE":
        text = f"Nascondi {name} coperta su {_bf_name(gs, lane)}" if side == viewer else \
            f"Mette una carta coperta su {_bf_name(gs, lane)}"
        to = f"bf:{lane}"
    elif kind == "HIDDEN_PLAY":
        fds = gs.battlefields[lane].facedowns
        fd = fds[idx or 0] if (idx or 0) < len(fds) else None
        text = f"Gioca la carta coperta {getattr(getattr(fd, 'card', None), 'name', '?')}" \
               f" su {_bf_name(gs, lane)}"
        src = f"facedown:{lane}:{idx or 0}"
    elif kind == "ABILITY":
        entries = loop.activatable_abilities(side)
        e = entries[lane] if isinstance(lane, int) and 0 <= lane < len(entries) else {}
        if e.get("type") == "ability":
            same = [x for x in entries if x.get("type") == "ability" and x["unit"] is e["unit"]]
            nth = f" (abilità {same.index(e) + 1})" if len(same) > 1 else ""
            text, src = f"Usa l'abilità di {e['unit'].card.name}{nth}", _unit_ref(gs, viewer, e["unit"])
        elif e.get("type") == "equip":
            text = f"Attacca l'equipaggiamento {e['gear'].name} a un'unità"
            src = _card_ref(gs, viewer, e["gear"])
        elif e.get("type") == "flow":
            text, src = f"Gioca {e['card'].name} dal cimitero (FLOW)", f"trash:{rel}"
        elif e.get("type") == "banished_play":
            text, src = f"Gioca {e['card'].name} dalle carte bandite", f"banished:{rel}"
        elif e.get("type") == "trash_play":
            text, src = f"Gioca {e['card'].name} dal cimitero", f"trash:{rel}"
        elif e.get("type") == "gear_ability":
            text, src = f"Usa {e['gear'].name}", _card_ref(gs, viewer, e["gear"])
        elif e.get("type") == "bf_ability":
            text, src = f"Usa l'abilità del campo {e['bf'].card.name}", f"bf:{e['bf_idx']}"
        else:
            text = "Usa un'abilità"
    else:
        text = str(action)
    return {"kind": kind, "text": text, "src": src, "dst": to}


def _choice_preview(gs, side: str, action, force, cards_played: int) -> dict:
    """The option a suggestion forces at its first choice, found by playing the
    action on a copy of the game: {"text", "ref"} (empty if never reached).
    Targets picked before it (the only one there is: Twilight Step's unit with
    3 Might or less) are named too."""
    from riftbound.core.loop import GameLoop
    clone = gs.clone()
    loop = GameLoop(clone)
    seen: dict = {}
    targets: list = []

    def chooser(_loop, kind, s, options, default, source):
        if not seen and s == side and (kind, len(options)) == tuple(force[:2]):
            opt = options[force[2]]
            head = kind.partition(":")[0]
            # "you may" of a card that isn't the move's (Shadow Clone attacking
            # when the showdown starts): name the card.
            name = getattr(source, "name", None)
            text = f"{name + ': ' if name else ''}{question(kind)} {option_text(_loop.gs, side, opt)}" \
                if head == "optional" else f"{_SHORT.get(head, 'scelta')}: {option_text(_loop.gs, side, opt)}"
            seen.update(text=", ".join(targets + [text]), ref=option_ref(_loop.gs, side, opt))
            return force[2]
        if not seen and s == side and kind.startswith("target"):
            targets.append(f"{_SHORT['target']}: {option_text(_loop.gs, side, options[default])}")
        return None

    loop.chooser = chooser
    try:
        loop._apply_action(clone.get_player(side), action, cards_played_this_turn=cards_played)
    except Exception:  # noqa: BLE001 — a preview never stops the game
        pass
    return seen


def _board_extras(gs, viewer: str) -> dict:
    """What the page draws beyond the Observation: a move being declared (its
    showdown starts when the player is done), each rune and whether it is
    ready, the chain in order, the viewer's own facedown cards."""
    def runes(side):
        return [{"domain": d.name, "ready": bool(r.ready)}
                for d, rs in gs.get_player(side).rune_pool.items() for r in rs]
    moving = gs.pending_move

    def fight(i, bf):
        # The Might each side fights with here: the attacker's units with
        # ASSAULT, the defender's with SHIELD; stunned units and units that deal
        # no combat damage don't count (combat._total_might).
        if gs.showdown_active and gs.showdown_bf_idx == i and gs.showdown_attacker:
            attacker = gs.showdown_attacker
        elif moving is not None and moving[0] == i:
            attacker = moving[1]
        else:
            attacker = gs.active
        out = {}
        for side in ("A", "B"):
            kw = "ASSAULT" if side == attacker else "SHIELD"
            out[_rel(side, viewer)] = sum(u.might + u.keyword_value(kw) for u in bf._units_for(side)
                                          if not u.stunned and not u.no_combat_damage)
        return out
    return {
        "moving": None if moving is None else {"bf": moving[0], "who": _rel(moving[1], viewer)},
        "fight": {str(i): fight(i, bf) for i, bf in enumerate(gs.battlefields)
                  if bf.units_A and bf.units_B},
        "runes": {"me": runes(viewer), "opp": runes(gs.other(viewer))},
        "chain": [{"name": i.card.name, "ability": i.ability is not None,
                   "owner": _rel(i.player, viewer), "bf": i.bf_idx,
                   "chose": declared_text(gs, viewer, i)} for i in gs.chain],
        "facedown_mine": {f"{i}:{j}": fd.card.name for i, bf in enumerate(gs.battlefields)
                          for j, fd in enumerate(bf.facedowns) if fd.owner == viewer},
    }


def _view_bf_names(battlefields: list) -> list:
    """The battlefields' names (of an Observation dict); two of the same (both
    precons bring Threshold of the Gray) say where they are on the table."""
    named = [bf["named"] for bf in battlefields]
    out = []
    for i, name in enumerate(named):
        if not name:
            out.append(f"campo {i + 1}")
        elif named.count(name) < 2:
            out.append(name)
        elif len(named) == 2:
            out.append(f"{name} ({'sinistra' if i == 0 else 'destra'})")
        else:
            out.append(f"{name} ({i + 1}°)")
    return out


def _board_events(prev: Optional[dict], cur: dict, opp_discards: Optional[list] = None) -> list:
    """What changed between two of the coach's views, as (who, text) lines:
    a new turn, points, control of a battlefield, a showdown, units gone.
    `opp_discards`: names of the cards the opponent discarded in between."""
    me = cur["viewer"]
    them = "B" if me == "A" else "A"
    names = _view_bf_names(cur["battlefields"])
    if prev is None or (prev["turn"], prev["active"]) != (cur["turn"], cur["active"]):
        whose = "a te" if cur["active"] == me else "all'avversario"
        out = [("turn", f"Turno {cur['turn']}: tocca {whose}")]
    else:
        out = []
    if prev is None:
        return out
    for who, key in (("me", "my_points"), ("opp", "opp_points")):
        d = cur[key] - prev[key]
        if d > 0:
            pts = "1 punto" if d == 1 else f"{d} punti"
            out.append((who, (f"Guadagni {pts}" if who == "me" else f"L'avversario guadagna {pts}")
                        + f" (ora {cur[key]}/{cur['victory_score']})"))
    for i, (pb, cb) in enumerate(zip(prev["battlefields"], cur["battlefields"])):
        if pb["controller"] != cb["controller"]:
            if cb["controller"] == me:
                out.append(("me", f"Ora controlli {names[i]}"))
            elif cb["controller"] is None and cb["A"] and cb["B"]:
                out.append(("sys", f"{names[i]} è conteso: ci sono unità di entrambi"))
            elif cb["controller"] is None:
                out.append(("sys", f"{names[i]} non è più controllato da nessuno"))
            else:
                out.append(("opp", f"L'avversario ora controlla {names[i]}"))
    if cur["showdown_bf"] is not None and cur["showdown_bf"] != prev["showdown_bf"]:
        out.append(("sys", f"Showdown su {names[cur['showdown_bf']]}"))
    for who, side, base, trash in (("me", me, "my_base_units", "my_trash"),
                                   ("opp", them, "opp_base_units", "opp_trash")):
        def units(v):
            return [*v[base], *(u for bf in v["battlefields"] for u in bf[side])]
        gone = Counter(u["name"] for u in units(prev)) - Counter(u["name"] for u in units(cur))
        to_trash = Counter(cur[trash]) - Counter(prev[trash])
        tokens = {u["name"] for u in units(prev) if u["is_token"]}
        for name, n in gone.items():
            dead = n if name in tokens else min(n, to_trash[name])
            to_trash[name] -= dead
            whose = "La tua unità" if who == "me" else "L'unità avversaria"
            for _ in range(dead):
                out.append((who, f"{whose} {name} è morta"))
            for _ in range(n - dead):
                out.append((who, f"{whose} {name} ha lasciato il tavolo"))
        # Banished (Shadow Clone's cost: a unit from your trash; a FLOW spell).
        banished = "my_banished" if who == "me" else "opp_banished"
        for name in sorted((Counter(cur[banished]) - Counter(prev[banished])).elements()):
            out.append((who, f"Bandita {'una tua carta' if who == 'me' else 'una carta avversaria'}: {name}"))
        # Cards drawn, and cards gone to the trash otherwise: discards, spells,
        # the top of the deck (BURN, e.g. Shadow Temple's "When you hold here").
        deck = "my_deck_count" if who == "me" else "opp_deck_count"
        left_deck = max(0, prev[deck] - cur[deck])
        if who == "me":
            left_hand = Counter(prev["my_hand"]) - Counter(cur["my_hand"])
            new = sorted((Counter(cur["my_hand"]) - Counter(prev["my_hand"])).elements())
            drawn = min(left_deck, len(new))
            burned = left_deck - drawn
            for name in sorted((+to_trash).elements()):
                if left_hand[name]:
                    # A spell leaving the hand was cast (its move is logged) or discarded.
                    left_hand[name] -= 1
                    out.append(("me", f"{name} va nel tuo cimitero" if _is_spell(name)
                                else f"Scarti {name}"))
                elif burned > 0:
                    burned -= 1
                    out.append(("me", f"Dal mazzo al cimitero: {name}"))
                else:
                    out.append(("me", f"{name} va nel tuo cimitero"))
            if drawn:
                out.append(("me", f"Peschi {', '.join(new[:drawn])}"))
        else:
            # The opponent's hand is hidden: its discards come from the engine
            # (`opp_discards`; Traveling Merchant's "discard 1 then draw 1"
            # looked like a burn), the rest that left the deck is a draw if the
            # hand grew, else a burn.
            discarded = Counter(opp_discards or ())
            gained = max(0, cur["opp_hand_count"] - prev["opp_hand_count"] + sum(discarded.values()))
            drawn = min(left_deck, gained) if gained else 0
            burned = left_deck - drawn
            for name in sorted((+to_trash).elements()):
                if discarded[name] > 0:
                    discarded[name] -= 1
                    out.append(("opp", f"L'avversario scarta {name}"))
                elif burned > 0:
                    burned -= 1
                    out.append(("opp", f"Dal mazzo avversario al cimitero: {name}"))
                else:
                    out.append(("opp", f"{name} va nel cimitero avversario"))
            if drawn:
                out.append(("opp", f"L'avversario pesca {drawn} cart{'a' if drawn == 1 else 'e'}"))
    return out


def _is_spell(name: str) -> bool:
    spec = CARD_REGISTRY.get(name)
    return spec is not None and "Spell" in ((spec.raw or {}).get("category") or "")


_CARD_IDS: dict = {}


def _card_id(name: str) -> Optional[str]:
    """The card's code (OGN-017), the name of its image."""
    if not _CARD_IDS:
        for c in json.loads(CARDS_JSON.read_text(encoding="utf-8")):
            _CARD_IDS.setdefault(c["name"], c["card_id"])
    return _CARD_IDS.get(name)


def _card_texts(obs: Optional[dict], extras: Optional[dict] = None) -> dict:
    """Printed text, type, cost, Might and image code of the cards on view."""
    if not obs:
        return {}
    names: set = set(obs.get("my_hand") or [])
    names |= set(obs.get("my_trash") or []) | set(obs.get("opp_trash") or [])
    names |= set(obs.get("my_banished") or []) | set(obs.get("opp_banished") or [])
    names |= set(obs.get("my_base_gear") or []) | set(obs.get("opp_base_gear") or [])
    names |= set(obs.get("my_chain") or []) | set(obs.get("opp_chain") or [])
    for key in ("my_legend", "opp_legend", "my_champion", "opp_champion"):
        if obs.get(key):
            names.add(obs[key])
    for key in ("my_added_legends", "opp_added_legends"):
        names |= {name for name, _ready in obs.get(key) or []}
    units = list(obs.get("my_base_units") or []) + list(obs.get("opp_base_units") or [])
    for bf in obs.get("battlefields") or []:
        units += list(bf.get("A") or []) + list(bf.get("B") or [])
        if bf.get("named"):
            names.add(bf["named"])
        names |= set(bf.get("gear_A") or []) | set(bf.get("gear_B") or [])
    for u in units:
        names.add(u["name"])
        names |= set(u.get("gear") or [])
    if extras:
        names |= set(extras.get("facedown_mine", {}).values())
        names |= {f"{r['domain'].title()} Rune" for rs in extras.get("runes", {}).values() for r in rs}
    out = {}
    for n in names:
        spec = CARD_REGISTRY.get(n)
        raw = (spec.raw or {}) if spec is not None else {}
        out[n] = {"text": raw.get("effect") or "", "type": raw.get("category") or "",
                  "cost": raw.get("cost_energy"), "might": raw.get("might"),
                  "img": raw.get("card_id") or _card_id(n)}
    return out


# -- the coached seat ------------------------------------------------------------

class _CoachChooser:
    """While a move the coach picked resolves: its player's choices (any kind
    with more than one option) are asked to the coach."""

    def __init__(self, me: str, session: "CoachSession", loop, previous):
        self.me, self.session, self.loop, self.previous = me, session, loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if side == self.me and len(options) > 1:
            gs = loop.gs
            described = [{"text": option_text(gs, side, o), "ref": option_ref(gs, side, o)}
                         for o in options]
            return self.session.ask_choice(kind, side, described, default, getattr(source, "name", None))
        return self.previous(loop, kind, side, options, default, source) if self.previous else None

    def release(self) -> None:
        if self.loop.chooser is self:
            self.loop.chooser = self.previous


class CoachAgent(NetGuidedMCTSAgent):
    """The net searches; the coach decides (see the module docstring)."""

    def __init__(self, player, net, session: "CoachSession", **kw):
        super().__init__(player, net, **kw)
        self.session = session

    def decide_action(self, opponent, cards_played: int = 0):
        return self._coached(DecisionPoint.TURN_ACTION, cards_played=cards_played)

    def decide_showdown_action(self, opponent, bf_idx: int):
        return self._coached(DecisionPoint.SHOWDOWN_ACTION, bf_idx=bf_idx)

    def decide_reaction(self, opponent, chain):
        return self._coached(DecisionPoint.REACTION)

    def decide_mulligan(self) -> list:
        """The coach picks the cards (up to two) to send back; the net's three
        best mulligans, by its value of the opening, are the advice."""
        hand = [c.name for c in self.player.hand]
        if not hand:
            return []
        self.session.opening = True        # no turn has started: nothing to log yet
        self.session.thinking(DecisionPoint.MULLIGAN)
        suggestions, seen = [], set()
        for combo, v in sorted(self.mulligan_values(), key=lambda cv: -cv[1]):
            names = tuple(sorted(hand[i] for i in combo))   # two copies: one idea
            if names not in seen and len(suggestions) < 3:
                seen.add(names)
                suggestions.append({"return": combo, "win": (v + 1) / 2,
                                    "text": mulligan_text(hand, combo)})
        try:
            return self.session.ask_mulligan(hand, suggestions)
        finally:
            self.session.opening = False
            self.session.view = None       # the first turn's line comes next

    def _release_coach(self) -> None:
        chooser = getattr(self.loop, "chooser", None)
        if isinstance(chooser, _CoachChooser) and chooser.me == self.player.name:
            chooser.release()

    def _context(self, point: DecisionPoint, bf_idx: Optional[int]) -> str:
        """What the decision is about, in a sentence."""
        gs = self.gs
        if point == DecisionPoint.SHOWDOWN_ACTION:
            where = _bf_name(gs, bf_idx if bf_idx is not None else gs.showdown_bf_idx or 0)
            return f"Showdown su {where}: puoi giocare magie veloci (ACTION, REACTION) o passare."
        if point == DecisionPoint.REACTION and gs.chain:
            top = gs.chain[-1]
            who = "L'avversario ha lanciato" if top.player != self.player.name else "Hai lanciato"
            if top.ability is not None:
                who = "L'avversario ha usato" if top.player != self.player.name else "Hai usato"
                if top.ability["kind"] in ("triggered", "reflexive"):
                    who = "Si è innescata per l'avversario" if top.player != self.player.name \
                        else "Si è innescata per te"
            chose = declared_text(gs, self.player.name, top)
            return f"{who} {chain_name(top)}" + (f" ({chose})" if chose else "") +                 ": puoi rispondere con una reazione o lasciar correre."
        if gs.pending_move is not None and gs.pending_move[1] == self.player.name:
            where = _bf_name(gs, gs.pending_move[0])
            return (f"Stai spostando unità su {where}: puoi mandarne altre insieme. "
                    "Quando hai finito parte lo showdown, poi il turno continua.")
        return "È il tuo turno: puoi giocare carte, spostare unità, usare abilità o passare."

    def _coached(self, point: DecisionPoint, cards_played: int = 0, bf_idx: Optional[int] = None):
        self._ensure_rng()
        if point == DecisionPoint.TURN_ACTION:
            self._release_forced()
            self._release_coach()
        side = self.player.name
        legal = legal_actions(self.loop, point, side)
        if len(legal) <= 1:
            if point == DecisionPoint.REACTION:
                self.session.notice_chain()
            return legal[0].to_engine() if legal else _PASS
        self.session.thinking(point)
        root = self.search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
        tuples = [a.to_engine() for a in legal]
        infos = [action_info(self.loop, side, side, point, t) for t in tuples]
        total = sum(c.N for c in root.children.values()) or 1
        ranked = sorted(root.children.items(), key=lambda kv: -kv[1].N)
        if ranked and self.prefer_pass(root, ranked[0][0]) == _PASS and ranked[0][0] != _PASS:
            # The net would pass: its top move isn't clearly better (prefer_pass).
            ranked = [(_PASS, root.children[_PASS])] + [kv for kv in ranked if kv[0] != _PASS]
        suggestions = []
        for key, child in ranked:
            if len(suggestions) == 3:
                break
            action, force = _split_key(key)
            if action not in tuples:
                continue
            i = tuples.index(action)
            choice = _choice_preview(self.gs, side, action, force, cards_played) if force else {}
            text = infos[i]["text"] + (f" → {choice['text']}" if choice else "")
            same = next((s for s in suggestions if s["text"] == text), None)
            if same is not None:              # two copies of a card in hand: one idea
                same["share"] += child.N / total
                continue
            q = child.W / child.N if child.N else 0.0
            suggestions.append({"key": key, "action": i, "share": child.N / total, "win": (q + 1) / 2,
                                "text": text, "choice": choice.get("text"), "choice_ref": choice.get("ref")})
        answer = self.session.ask_decision(point, side, infos, suggestions, self._context(point, bf_idx))
        force = None
        if "suggestion" in answer:
            action, force = _split_key(suggestions[int(answer["suggestion"])]["key"])
            # The net's searched choice is forced; the other choices inside the
            # move (which card to discard for a battlefield...) are the coach's.
            self.loop.chooser = _CoachChooser(side, self.session, self.loop, self.loop.chooser)
            if force is not None:
                self.loop.chooser = _ForcedChoice(side, force, self.loop, self.loop.chooser)
            corrected = int(answer["suggestion"]) != 0
        else:
            action = tuples[int(answer["action"])]
            self.loop.chooser = _CoachChooser(side, self.session, self.loop, self.loop.chooser)
            best = _split_key(suggestions[0]["key"])[0] if suggestions else None
            corrected = action != best
        auto = bool(answer.get("auto"))      # the net finishing the game on its own
        if action != _PASS or force is not None:
            # A suggestion taken says the choice it makes too ("Fatto: parte lo
            # showdown → Shadow Clone: Usare questo effetto? Sì").
            i = tuples.index(action)
            text = suggestions[int(answer["suggestion"])]["text"] if force is not None \
                else infos[i]["text"]
            note = " (la rete, da sola)" if auto else "" if not suggestions else \
                " (diversa dalla rete)" if corrected else " (come la rete)"
            self.session.event("me", text + note, move=True)
        if not auto:
            self.session.record(self.gs, side, legal, action, corrected)
        return action


class CoachSession:
    """One coached game at a time, on its own thread, for the web page."""

    def __init__(self, net_path: Path, out_dir: Path, iterations: int = 100,
                 opponent_pause: float = 0.8):
        self.net_path = Path(net_path)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.iterations = iterations
        # Seconds the board holds still before each opponent decision that
        # follows a change, so the coach can watch what the opponent does.
        self.opponent_pause = opponent_pause
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.status = "idle"            # idle | thinking | waiting | over
        self.activity = ""
        self._answers: "queue.Queue" = queue.Queue()
        self.pending: Optional[dict] = None
        self.examples: list = []
        self.log: deque = deque(maxlen=400)
        self.events: deque = deque(maxlen=300)
        self.result: Optional[dict] = None
        self.info: dict = {}
        self.view: Optional[dict] = None    # the board, snapshot on the game thread
        self.extras: Optional[dict] = None
        self.gs = None
        self.loop = None
        self.side: Optional[str] = None
        self.autoplay = False               # the net finishes the game on its own
        self._abandoned = False             # ... and nothing is saved
        self._thread: Optional[threading.Thread] = None
        self.opp_mulligan: Optional[dict] = None   # told once the game is over
        self.opening = False                # the coach's mulligan, before turn 1
        self.opp_discards: list = []        # since the last snapshot (its hand is hidden)
        self.stop_on_opp_chain = True       # hold the board on each opponent spell (notice_chain)

    # -- the game thread ---------------------------------------------------------

    def new_game(self, deck_mine: Path, deck_opp: Path, seat: str = "A",
                 opponent: str = "net", seed: Optional[int] = None) -> None:
        """Start a game: the coach's seat plays `deck_mine` with the net's search
        as advisor; the other seat is the net ("net") or the simple_trade
        heuristic ("simple_trade")."""
        import torch

        from riftbound.ai.net import load_checkpoint
        from riftbound.core.game_factory import build_game, make_agent
        if self._thread is not None and self._thread.is_alive():
            self.abandon()
            self._thread.join(timeout=60)
        self._reset()
        seed = random.randrange(1 << 30) if seed is None else seed
        net = load_checkpoint(self.net_path, device=torch.device("cpu"))
        deck_a, deck_b = (deck_mine, deck_opp) if seat == "A" else (deck_opp, deck_mine)
        gs = build_game(game_seed=seed, deck_a_path=Path(deck_a), deck_b_path=Path(deck_b),
                        ai_a=None, ai_b=None)
        me, them = gs.get_player(seat), gs.get_player(gs.other(seat))
        me.agent = CoachAgent(me, net, self, iterations=self.iterations, rng=random.Random(seed))
        if opponent == "net":
            them.agent = NetGuidedMCTSAgent(them, net, iterations=self.iterations,
                                            rng=random.Random(seed + 1))
        else:
            them.agent = make_agent(opponent, them)
        # The board the page shows, and the log, follow the opponent's moves too.
        points = {"decide_action": DecisionPoint.TURN_ACTION,
                  "decide_showdown_action": DecisionPoint.SHOWDOWN_ACTION,
                  "decide_reaction": DecisionPoint.REACTION}
        for name, point in points.items():
            inner = getattr(them.agent, name)

            def watched(*a, _inner=inner, _point=point, _side=them.name, **k):
                self._opponent_turn()
                action = _inner(*a, **k)
                if action and action[0] != "PASS" and self.loop is not None:
                    self.event("opp", action_info(self.loop, _side, self.side, _point, action)["text"],
                               move=True)
                return action
            setattr(them.agent, name, watched)

        def mulligan(_inner=them.agent.decide_mulligan, _p=them):
            hand = [c.name for c in _p.hand]
            back = _inner() or []
            self.opp_mulligan = {"hand": hand, "returned": [hand[i] for i in back]}
            return back
        them.agent.decide_mulligan = mulligan
        self.gs, self.side = gs, seat
        self.info = {"seed": seed, "seat": seat, "deck_mine": Path(deck_mine).stem,
                     "deck_opp": Path(deck_opp).stem, "opponent": opponent,
                     "net": str(self.net_path), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.status = "thinking"
        self.activity = "La partita sta iniziando…"
        self._thread = threading.Thread(target=self._run, name="rbsim-coach", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        from riftbound.core.loop import GameLoop
        log = _thread_log()
        log.sinks[threading.get_ident()] = self.log
        try:
            self.loop = GameLoop(self.gs, verbose=True)
            opp = self.gs.get_player(self.gs.other(self.side))

            def discard(player, card, _inner=self.loop._discard):
                # A discard is public (the card goes to the trash face up).
                if player is opp and card in player.hand:
                    self.opp_discards.append(card.name)
                return _inner(player, card)
            self.loop._discard = discard
            self.loop.on_choice = self._log_choice
            result = self.loop.start()
            self.result = {"winner": result.winner, "turns": result.turns,
                           "you_won": result.winner == self.side}
            if not self._abandoned:
                self._save(result.winner)
        except Exception as exc:  # noqa: BLE001
            self.result = {"error": repr(exc)}
        finally:
            self._snapshot()
            if self.opp_mulligan is not None:
                m = self.opp_mulligan
                self.event("sys", "Mulligan dell'avversario: " + (
                    f"aveva rimandato {' e '.join(m['returned'])}" if m["returned"]
                    else "aveva tenuto tutta la mano") + f" ({', '.join(m['hand'])})")
            log.sinks.pop(threading.get_ident(), None)
            self.pending = None
            self.status = "over"

    def _snapshot(self) -> bool:
        """The coach's view of the board, taken on the game thread (the page
        never reads the live game); what changed since the last one goes to the
        log. Returns whether anything changed."""
        if self.gs is None or self.side is None:
            return False
        view = Observation.from_state(self.gs, self.side).to_dict()
        extras = _board_extras(self.gs, self.side)
        if view == self.view and extras == self.extras:
            return False
        if not self.opening:
            for who, text in _board_events(self.view, view, self.opp_discards):
                self.event(who, text)
        self.opp_discards = []
        self.view, self.extras = view, extras
        return True

    _FINISHING = "La rete sta finendo la partita da sola…"

    def _opponent_turn(self) -> None:
        changed = self._snapshot()
        self.status = "thinking"
        self.activity = self._FINISHING if self.autoplay else "L'avversario sta giocando…"
        if changed and self.opponent_pause and not self.autoplay:
            time.sleep(self.opponent_pause)

    def event(self, who: str, text: str, move: bool = False) -> None:
        """A line of the Italian log: who is "me", "opp", "sys" or "turn"; a
        move is something a player chose to do (the rest is what happened)."""
        turn = self.gs.turn if self.gs is not None else 0
        self.events.append({"turn": turn, "who": who, "text": text, "move": move})

    # Choices whose answer is public: the opponent's are logged, and the coach's
    # when there was only one option (the page never asked).
    _PUBLIC_CHOICES = {"target", "mode", "destination", "cost_unit", "equip", "deploy",
                       "spend_buff", "disarm", "first_unit_here", "player", "discard"}

    def _log_choice(self, kind: str, side: str, n_options: int, got, source) -> None:
        """GameLoop.on_choice: a spell's targets are told as it goes on the
        chain, other choices as they are made."""
        head = kind.partition(":")[0]
        if head not in self._PUBLIC_CHOICES or not n_options or self.gs is None:
            return
        mine = side == self.side
        if mine and n_options > 1:
            return                         # asked on the page, logged there
        if not mine and head == "discard":
            return                         # opp_discards logs it
        name = getattr(source, "name", None)
        text = f"{name + ': ' if name else ''}{_SHORT.get(head, 'scelta')} → " \
               f"{_chosen_text(self.gs, self.side, got)}"
        self.event("me" if mine else "opp", text + (" (unica scelta)" if mine else ""))

    def notice_chain(self) -> None:
        """The opponent put a card on the chain and the coach can't respond:
        hold the board until they have seen it and what it chose (the page's
        "Continua")."""
        gs = self.gs
        if not gs.chain or gs.chain[-1].player == self.side or not self.stop_on_opp_chain:
            return
        top = gs.chain[-1]
        below = [chain_name(i) for i in gs.chain[:-1]]
        chose = declared_text(gs, self.side, top)
        verb = "ha usato" if top.ability is not None else "ha lanciato"
        if top.ability is not None and top.ability["kind"] in ("triggered", "reflexive"):
            verb = "ha innescato"
        context = f"L'avversario {verb} {chain_name(top)}" + (f" ({chose})" if chose else "") + (
            f", sopra {', '.join(reversed(below))}" if below else "") + \
            ". Non hai reazioni da giocare: adesso si risolve."
        answer = self._wait({"type": "notice", "context": context, "card": top.card.name})
        if answer.get("quiet"):
            self.stop_on_opp_chain = False
            self.event("sys", "Non mi fermo più sulle magie dell'avversario in questa partita")

    def thinking(self, point: DecisionPoint) -> None:
        self._snapshot()
        self.status = "thinking"
        self.activity = self._FINISHING if self.autoplay else "La rete sta pensando alla tua mossa…"

    def _wait(self, request: dict) -> dict:
        """Ask the coach and wait; {} once the net finishes the game alone."""
        self._snapshot()
        with self._lock:
            if self.autoplay:
                return {}
            self.pending = request
            self.status = "waiting"
        answer = self._answers.get()
        with self._lock:
            self.pending = None
            self.status, self.activity = "thinking", "Sto giocando la mossa…"
        return answer

    def ask_decision(self, point: DecisionPoint, side: str, actions: list, suggestions: list,
                     context: str = "") -> dict:
        answer = self._wait({"type": "decision", "point": point.value, "context": context,
                             "actions": actions,
                             "suggestions": [{k: v for k, v in s.items() if k != "key"}
                                             for s in suggestions]})
        if not answer:                     # the net finishes alone: its move
            return {"suggestion": 0, "auto": True} if suggestions else {"action": 0, "auto": True}
        return answer

    def ask_mulligan(self, hand: list, suggestions: list) -> list:
        """The coach's mulligan: the hand indices to send back (up to two)."""
        answer = self._wait({"type": "mulligan", "hand": [{"text": n, "ref": f"hand:{i}"}
                                                          for i, n in enumerate(hand)],
                             "suggestions": suggestions, "max": 2,
                             "context": "La tua mano iniziale: puoi rimandare in fondo al mazzo "
                                        "fino a 2 carte e pescarne altrettante."})
        if "suggestion" in answer:
            back = suggestions[int(answer["suggestion"])]["return"]
        elif "return" in answer:
            back = sorted({int(i) for i in answer["return"] if 0 <= int(i) < len(hand)})[:2]
        else:                              # the net finishes alone: its mulligan
            back = suggestions[0]["return"] if suggestions else []
        if answer:
            note = "" if not suggestions else " (come la rete)" if back == suggestions[0]["return"] \
                else " (diversa dalla rete)"
            self.event("me", f"Mulligan: {mulligan_text(hand, back)}{note}", move=True)
        return back

    def ask_choice(self, kind: str, side: str, options: list, default: int,
                   source: Optional[str]) -> int:
        answer = self._wait({"type": "choice", "kind": kind, "question": question(kind),
                             "options": options, "default": default, "source": source})
        if not answer:
            return default
        pick = int(answer.get("option", default))
        if 0 <= pick < len(options):
            self.event("me", f"{source + ': ' if source else ''}{question(kind)} → {options[pick]['text']}",
                       move=True)
        return pick

    # -- the page's side ---------------------------------------------------------

    def answer(self, payload: dict) -> None:
        if self.pending is None:
            raise RuntimeError("nothing is waiting for an answer")
        self._answers.put(payload)

    def finish(self, save: bool = True) -> None:
        """Stop coaching: the net plays the rest of the game on its own, without
        questions or pauses. With `save` the coach's decisions so far are saved
        with the result when it ends (the net's own moves aren't); without,
        nothing is."""
        with self._lock:
            if self.status not in ("thinking", "waiting"):
                return
            self.autoplay = True
            self._abandoned = self._abandoned or not save
            self.info["finished_by_net"] = True
            self.activity = self._FINISHING
            if self.pending is not None:
                self._answers.put({})

    def abandon(self) -> None:
        """Let the net finish the game on its own; nothing is saved."""
        self.finish(save=False)

    def forget_last(self) -> bool:
        """The coach's last decision was a slip: it won't be used for training."""
        if not self.examples:
            return False
        self.examples.pop()
        self.event("sys", "La tua ultima decisione non verrà usata per l'allenamento")
        return True

    @staticmethod
    def _copy(items: deque) -> list:
        for _ in range(5):                  # the game thread may be appending
            try:
                return list(items)
            except RuntimeError:
                continue
        return []

    def state(self) -> dict:
        obs, extras = self.view, self.extras
        return {"status": self.status, "activity": self.activity, "info": self.info,
                "autoplay": self.autoplay, "saving": not self._abandoned,
                "pending": self.pending, "observation": obs, "board": extras,
                "events": self._copy(self.events), "log": self._copy(self.log)[-60:],
                "result": self.result, "decisions": len(self.examples),
                "corrections": sum(1 for e in self.examples if e["corrected"]),
                "cards": _card_texts(obs, extras)}

    def report(self, note: str) -> Path:
        path = self.out_dir / "reports.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note,
                                 **self.state(), "log": self._copy(self.log),
                                 "opp_mulligan": self.opp_mulligan}, default=str) + "\n")
        return path

    # -- training examples -----------------------------------------------------------

    def record(self, gs, side: str, legal: list, action, corrected: bool) -> None:
        policy = np.zeros(ACTION_DIM, dtype=np.float32)
        idx = action_to_index(action)
        if idx is None:
            return
        policy[idx] = 1.0
        self.examples.append({"state": encode_observation(Observation.from_state(gs, side)),
                              "policy": policy, "mask": legal_mask(legal), "player": side,
                              "corrected": corrected})

    def _save(self, winner: str) -> Optional[Path]:
        if not self.examples:
            return None
        z = [0.0 if winner == "DRAW" else 1.0 if winner == e["player"] else -1.0 for e in self.examples]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.out_dir / f"coach_{stamp}.npz"
        np.savez_compressed(path, state=np.stack([e["state"] for e in self.examples]),
                            policy=np.stack([e["policy"] for e in self.examples]),
                            mask=np.stack([e["mask"] for e in self.examples]),
                            z=np.asarray(z, dtype=np.float32),
                            corrected=np.asarray([e["corrected"] for e in self.examples]))
        with open(self.out_dir / "games.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**self.info, "file": path.name, "winner": winner,
                                 "decisions": len(self.examples),
                                 "corrections": sum(1 for e in self.examples if e["corrected"])}) + "\n")
        return path


def load_coach_examples(coach_dir: Path) -> list[dict]:
    """Every coached decision saved in `coach_dir`, as training examples."""
    out: list = []
    for path in sorted(Path(coach_dir).glob("coach_*.npz")):
        with np.load(path) as data:
            for i in range(len(data["z"])):
                out.append({"state": data["state"][i], "policy": data["policy"][i],
                            "mask": data["mask"][i], "z": float(data["z"][i])})
    return out
