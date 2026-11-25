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

The net is optional (24/11): without it the coached seat is the person alone,
with no search, no suggestions and no training examples (games.jsonl still
keeps each result), and the opponent can be the champion (`PPOPriorAgent` with
a PPO checkpoint's priors, `budget` CPU seconds a decision; opponents()).

The engine (25/11, phase 4): a game between two lists Rust covers (arena_rs.COPERTI),
against the champion or the simple bot, plays on the Rust engine with the rules profile
`regole` (default 6427b90+D72-D80; riftbound/ai/coach_rs.py, the champion there with a fixed
number of iterations a decision); the net's advice and "La rete" stay on Python (6427b90).
`state()["regole"]` and games.jsonl say what was played.
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
from riftbound.ai.net_mcts import (
    _PASS,
    NetGuidedMCTSAgent,
    _choice_keys,
    _ForcedChoice,
    _split_key,
    _unlink,
)
from riftbound.core.decisions import DecisionPoint, Observation
from riftbound.core.legality import legal_actions
from riftbound.core.loop import NO_MORE, GameLoop
from riftbound.core.player import Domain
from riftbound.provenienza import REGOLE_D72_D80, REGOLE_PYTHON
from riftbound.registry.cards_registry import CARD_REGISTRY

CARDS_JSON = Path(__file__).resolve().parents[1] / "data" / "cards" / "all_cards.json"

# The champion (STATO.md, 24/11): the hand-written search guided by the priors
# of this PPO checkpoint, 0.4 s a decision. It searches copies of the game with
# the hidden cards resampled: it doesn't see the coach's hand.
CAMPIONE = Path(__file__).resolve().parents[2] / "runs" / "sett" / "ekris_s12" / "ckpt_040000.pt"
CAMPIONE_DECKS = ("Evelynn", "Kha'Zix", "Rengar", "Ivern", "Sett")   # what it trained on
# The opponents a game can have, in the menu's order (opponents()).
_OPPONENTS = {"campione": "Il campione",
              "net": "La rete",
              "simple_trade": "Bot semplice"}

_PPO_NETS: dict = {}            # one PPO net per checkpoint file (and its mtime)


def _ppo_net(path: Path):
    import torch

    from riftbound.ai.ppo.model import load
    torch.set_num_threads(1)    # as the champion was measured (its budget is CPU time)
    path = Path(path).resolve()
    key = (str(path), path.stat().st_mtime_ns)
    if key not in _PPO_NETS:
        _PPO_NETS[key] = load(path).eval()
    return _PPO_NETS[key]


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


class _Full(deque):
    """A display deque (the last `maxlen` lines) that also keeps every line in `full`, for the saved
    game (CoachSession._save_game). A rewind cuts `full` back to the checkpoint's length."""

    def __init__(self, maxlen: Optional[int] = None):
        super().__init__(maxlen=maxlen)
        self.full: list = []

    def append(self, item) -> None:
        self.full.append(item)
        super().append(item)


def _thread_log() -> _ThreadLog:
    if not isinstance(sys.stdout, _ThreadLog):
        sys.stdout = _ThreadLog(sys.stdout)
    return sys.stdout


# -- describing the game for the page, in Italian -------------------------------

_TYPES = {"UNIT": "unità", "SPELL": "magia", "GEAR": "equipaggiamento", "RUNE": "runa",
          "LEGEND": "leggenda", "CHAMPION": "campione", "BATTLEFIELD": "campo di battaglia"}

_QUESTIONS = {
    "target": "Scegli il bersaglio", "mode": "Quale effetto usare?", "payment": "Come paghi?",
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
    "facedown_trash": "Non c'è più posto: quale carta coperta mettere nel cimitero?",
}
# The same choices in a few words, after a suggested move ("→ bersaglio: Zed").
_SHORT = {"target": "bersaglio", "mode": "effetto", "equip": "su", "combat_damage_order":
          "in combattimento colpisce prima", "cost_unit": "paga con", "discard": "scarta",
          "destination": "verso", "deploy": "schiera su", "domain": "Power",
          "keep": "tiene", "card": "carta", "predict_order": "in cima", "trigger_order": "prima",
          "show_off": "mostra", "disarm": "indebolisce",
          "spend_buff": "spende il buff di", "cost_banish": "bandisce",
          "first_unit_here": "rimanda in base", "player": "giocatore", "token_location": "token in",
          "battlefield": "campo", "tag": "tag", "facedown_trash": "nel cimitero"}
_OPTIONAL = {"accelerate": "Pagare ACCELERATE? (l'unità entra pronta)",
             "additional_cost": "Pagare il costo aggiuntivo?", "SHOW OFF": "Usare SHOW OFF?",
             "enter_ready": "Far entrare l'unità pronta?",
             "keep": "Prendere una delle carte guardate?"}


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


def reveals_keep(kind: str, source) -> bool:
    """A `keep:dig` / `keep:reveal_and_choose` choice whose kept card is revealed (Trifarian
    Captain; the engine's `spec.get("reveal", not spec.get("must"))`): its answer is public."""
    head, _, eff = kind.partition(":")
    if head != "keep" or eff not in ("dig", "reveal_and_choose"):
        return False
    spec = CARD_REGISTRY.get(getattr(source, "name", None))
    for e in (spec.effects if spec is not None else ()):
        if e.effect == eff:
            p = e.params
            return bool(p.get("reveal", not p.get("must")))
    return False


def is_public_choice(public: set, kind: str, source) -> bool:
    """Is the answer to this choice told in the log (`public`: the kinds that always are)?"""
    return kind.partition(":")[0] in public or reveals_keep(kind, source)


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


def _cast_outcome(loop, side: str, action):
    """What casting `action` (a SPELL) does, as the players see it: the choices
    asked on the way (default answers) and the table after, for both seats.
    Played on a copy of the game; None if the copy fails."""
    from riftbound.core.loop import GameLoop
    clone = loop.gs.clone()
    copy = GameLoop(clone)
    asked: list = []

    def chooser(_loop, kind, s, options, default, source):
        asked.append((s, kind, [option_text(_loop.gs, s, o) for o in options]))
        return None
    copy.chooser = chooser
    try:
        copy._apply_action(clone.get_player(side), action)
        seen = [(Observation.from_state(clone, s).to_dict(), _board_extras(clone, s)) for s in ("A", "B")]
    except Exception:  # noqa: BLE001 — a comparison never stops the game
        return None
    return json.dumps([asked, seen], sort_keys=True, default=str)


def spell_lane_free(loop, side: str, point: DecisionPoint, idx) -> bool:
    """Whether hand card `idx`, a spell, does the same whichever battlefield the
    engine aims it at (§355: a spell has no place; the engine's battlefield only
    narrows "a unit here"). Punch First's "a unit" is any unit, the base's too:
    the page then offers one cast, and the target is the next question."""
    lanes = [a.to_engine() for a in legal_actions(loop, point, side)
             if a.kind == "SPELL" and a.to_engine()[1] == idx]
    if len(lanes) < 2:
        return False
    first = _cast_outcome(loop, side, lanes[0])
    return first is not None and all(_cast_outcome(loop, side, a) == first for a in lanes[1:])


# Paying (Matteo, 25/11). A Gold's ability Adds a Power of any domain: the
# engine has it used before the card is played. A [rune] cost (any domain:
# hiding a card, a two-domain card's Power, DEFLECT) the engine pays from the
# first domain that covers it, where the rules let the player pick the rune.
# The page asks how to pay when a move can be paid in more than one way and
# plays it so: the Golds first (CoachAgent._gold_step), the [rune] from the
# chosen domain (CoachLoop). The engine itself is unchanged.
_PAY_KINDS = ("UNIT", "SPELL", "GEAR", "CHAMPION", "HIDE", "ABILITY")


class CoachLoop(GameLoop):
    """The engine's game as the page plays it: `recycle_first` = (side,
    domain) pays that side's next [rune] cost from that domain when it can
    (then it is spent); without it, as the engine does. `record`: every
    decision and choice of both players, in order, to replay the game up to
    one of them (CoachSession.rewind)."""
    recycle_first = None

    def __init__(self, gs, *args, **kwargs):
        super().__init__(gs, *args, **kwargs)
        self.record: list = []

    def _consult(self, loop, kind: str, side: str, options: list, default: int, source):
        i = super()._consult(loop, kind, side, options, default, source)
        self.record.append(("choice", side, kind, len(options), default if i is None else int(i)))
        return i

    def _note_decision(self, side: str, point: str, action) -> None:
        super()._note_decision(side, point, action)
        self.record.append(("decision", side, point, action, self.recycle_first))

    def _open_segment(self, side: str, action, cards_played: int) -> None:
        super()._open_segment(side, action, cards_played)
        self.record.append(("decision", side, DecisionPoint.TURN_ACTION.value, action, self.recycle_first))

    def _preferred(self, actor):
        pref = self.recycle_first
        if pref is None or self.gs.get_player(pref[0]) is not actor:
            return None
        self.recycle_first = None
        return pref[1]

    def _pay_generic_power(self, actor, n: int) -> bool:
        d = self._preferred(actor) if n > 0 else None
        if d is not None and actor.can_pay_cost(0, n, d):
            ok = actor.pay_cost(0, n, d)
            self._drain_rune_recycles()
            return ok
        return super()._pay_generic_power(actor, n)

    def _pay_card_cost(self, actor, card, energy: int, power, domain=None) -> bool:
        d = self._preferred(actor) if power and (domain or card.cost_power_domain) is None else None
        if d is None:
            return super()._pay_card_cost(actor, card, energy, power, domain)
        base = actor.pay_power_of

        def first(n, domains):               # a two-domain card's Power: `d` first
            domains = list(domains)
            k = min(n, actor._power_left(d)) if d in domains else 0
            if k and not actor.pay_cost(0, k, d):
                return False
            return base(n - k, domains) if n > k else True
        actor.pay_power_of = first
        try:
            return super()._pay_card_cost(actor, card, energy, power, domain)
        finally:
            del actor.pay_power_of


class _Rewind(BaseException):
    """The coach takes back their last move (CoachSession.rewind). Not an
    Exception: the engine's own `except Exception` must let it through."""


class _ReplayError(BaseException):
    """A rewind's replay left the recorded game."""


_LIVE = object()


class _Record:
    """A page game's record (CoachLoop.record) replayed by a rewind: the
    chooser at the bottom of the loop's chain, and the seats' agents (_Seat),
    answer from it in order; at its end the live game goes on. A game that
    isn't replayed has an empty one: it only lets the other choosers answer."""

    def __init__(self, entries: list):
        self.entries, self.k = list(entries), 0
        self.loop = None
        self.previous = None                # always the bottom of the chain

    @property
    def replaying(self) -> bool:
        return self.k < len(self.entries)

    def _next(self, *head):
        e = self.entries[self.k]
        if tuple(e[:len(head)]) != head:
            raise _ReplayError(f"atteso {head}, registrato {tuple(e[:len(head)])} ({self.k})")
        self.k += 1
        return e

    def __call__(self, loop, kind, side, options, default, source):
        return self._next("choice", side, kind, len(options))[4] if self.replaying else None

    def decision(self, side: str, point: str):
        if not self.replaying:
            return _LIVE
        e = self._next("decision", side, point)
        self.loop.recycle_first = e[4]
        return e[3]

    def mulligan(self, side: str):
        return self._next("mulligan", side)[2] if self.replaying else _LIVE


class _Seat:
    """A seat's agent in a page game: answers from the record while a rewind
    replays it (_Record), else is the live agent (its other methods too).
    The mulligans are recorded here: the engine asks the agent, not a chooser.
    `on_live`: called the first time the live agent is asked (the coach's
    seat: the replay is over)."""

    def __init__(self, live, record: _Record, on_live=None):
        self.live, self.record, self.on_live = live, record, on_live
        self.player = live.player

    def __getattr__(self, name):
        if name == "live":                  # not built yet (a copy)
            raise AttributeError(name)
        return getattr(self.live, name)

    def _live(self):
        if self.on_live is not None:
            self.on_live()
        return self.live

    def _decide(self, point: DecisionPoint, method: str, *args, **kwargs):
        got = self.record.decision(self.player.name, point.value)
        return getattr(self._live(), method)(*args, **kwargs) if got is _LIVE else got

    def decide_action(self, opponent, cards_played: int = 0):
        return self._decide(DecisionPoint.TURN_ACTION, "decide_action", opponent, cards_played=cards_played)

    def decide_showdown_action(self, opponent, bf_idx: int):
        return self._decide(DecisionPoint.SHOWDOWN_ACTION, "decide_showdown_action", opponent, bf_idx)

    def decide_reaction(self, opponent, chain):
        return self._decide(DecisionPoint.REACTION, "decide_reaction", opponent, chain)

    def decide_mulligan(self) -> list:
        got = self.record.mulligan(self.player.name)
        if got is _LIVE:
            got = list(self._live().decide_mulligan() or [])
        self.loop.record.append(("mulligan", self.player.name, list(got)))
        return got

    # The agent's preferences, only defaults for the choices that follow (the
    # chooser answers them): none while replaying.
    def decide_optional(self, card, name) -> bool:
        f = None if self.record.replaying else getattr(self.live, "decide_optional", None)
        return True if f is None else f(card, name)

    def decide_mode(self, card, n_modes: int):
        f = None if self.record.replaying else getattr(self.live, "decide_mode", None)
        return None if f is None else f(card, n_modes)

    def decide_predict_recycle(self, card) -> bool:
        f = None if self.record.replaying else getattr(self.live, "decide_predict_recycle", None)
        return False if f is None else f(card)


def _golds(loop, side: str, point: DecisionPoint) -> list:
    """The ABILITY lanes of `side`'s gear that Add a Power of any domain
    (Gold) and are legal moves now: not an exhausted one, nor one while units
    are being moved (only more moves are)."""
    entries = loop.activatable_abilities(side)
    return [t[2] for t in (a.to_engine() for a in legal_actions(loop, point, side))
            if t[0] == "ABILITY" and isinstance(t[2], int) and t[2] < len(entries)
            and entries[t[2]].get("type") == "gear_ability"
            and getattr(entries[t[2]].get("eff"), "effect", None) == "gain_power_any_domain"]


def _paid_card(loop, side: str, action):
    """The card whose cost `action` pays (from hand, or the champion)."""
    kind, idx = action[0], action[1]
    p = loop.gs.get_player(side)
    if kind == "CHAMPION" or (kind == "HIDE" and idx == "champion"):
        return loop.gs.champion_A if side == "A" else loop.gs.champion_B
    if kind == "ABILITY":
        return None
    return p.hand[idx] if isinstance(idx, int) and 0 <= idx < len(p.hand) else None


def _pay_domains(loop, side: str, card) -> list:
    """The domains that may pay `card`'s Power: its own, then the player's."""
    own = getattr(card, "cost_power_domain", None) if card is not None else None
    doms = [own] if own is not None else []
    if card is not None and own is None and len(loop._power_domains(card)) < len(Domain):
        doms += loop._power_domains(card)               # two domains: either
    doms += list(loop.gs.get_player(side).power_pool)
    return list(dict.fromkeys(doms))


def _pay_outcome(loop, side: str, point: DecisionPoint, action, golds: int, gold_domain, prefer,
                 accelerate: Optional[bool] = True):
    """(the runes `action` recycles, ((domain name, n), ...), whether the move
    asked ACCELERATE), once `golds` Golds Added `gold_domain` Power, its
    [rune] paid from `prefer` first, ACCELERATE answered `accelerate`; on a
    copy of the game. None if it can't be played so."""
    clone = loop.gs.clone()
    copy = CoachLoop(clone)
    p = clone.get_player(side)
    asked = []

    def chooser(_loop, kind, s, options, default, source):
        if kind == "optional:accelerate" and s == side:
            asked.append(True)
            return options.index(accelerate) if accelerate is not None else None
        return options.index(gold_domain) if kind.startswith("domain") and s == side \
            and gold_domain in options else None
    copy.chooser = chooser
    try:
        for _ in range(golds):
            lanes = _golds(copy, side, point)
            if not lanes:
                return None
            copy._apply_action(p, ("ABILITY", "ACTIVATED", lanes[0]))
        if action not in [a.to_engine() for a in legal_actions(copy, point, side)]:
            return None
        before = {d: len(rs) for d, rs in p.rune_pool.items()}
        copy.recycle_first = (side, prefer) if prefer is not None else None
        copy._apply_action(p, action)
        return tuple((d.name, n - len(p.rune_pool.get(d, []))) for d, n in before.items()
                     if n > len(p.rune_pool.get(d, []))), bool(asked)
    except Exception:  # noqa: BLE001 — a comparison never stops the game
        return None


def payment_text(golds: int, recycled) -> str:
    """A way to pay, in words: "Col Gold, ricicli 1 runa Body"."""
    how = "" if not golds else "col Gold, " if golds == 1 else f"con {golds} Gold, "
    what = ", ".join(f"{n} {'runa' if n == 1 else 'rune'} {d.title()}" for d, n in recycled)
    text = how + (f"ricicli {what}" if what else "nessuna runa riciclata")
    return text[0].upper() + text[1:]


def payment_options(loop, side: str, point: DecisionPoint, action) -> list:
    """The ways to pay `action` that recycle different runes: [{"golds",
    "gold_domain", "prefer", "accelerate", "recycled", "text"}], fewest Golds
    first (the engine's own way first); a Gold only where it saves a rune
    (among the ways with the same ACCELERATE answer). `accelerate`: None, or
    where the move asks "Pagare ACCELERATE?" (and it can be paid) True / False,
    the answer the way is for (yes first). One way: no choice to make; none:
    it can't be paid, Golds or not."""
    if action[0] not in _PAY_KINDS:
        return []
    golds = _golds(loop, side, point)
    if action[0] == "ABILITY" and action[2] in golds:
        return []
    p = loop.gs.get_player(side)
    doms = _pay_domains(loop, side, _paid_card(loop, side, action))
    out: list = []
    for k in range(len(golds) + 1):
        ways = [(None, None)] + [(None, d) for d in p.power_pool if p._power_left(d)] if not k \
            else [(g, g) for g in doms]
        for gold_domain, prefer in ways:
            got = _pay_outcome(loop, side, point, action, k, gold_domain, prefer, True)
            if got is None:
                continue
            outcomes = [(None, got[0])]
            if got[1]:                          # the move asks ACCELERATE: both answers
                other = _pay_outcome(loop, side, point, action, k, gold_domain, prefer, False)
                outcomes = [(True, got[0])] + ([(False, other[0])] if other is not None else [])
            for acc, recycled in outcomes:
                key = bool(acc)                 # a move that did not ask ACCELERATE counts as "No"
                fewest = min((sum(n for _d, n in o["recycled"]) for o in out
                              if o["golds"] == k - 1 and bool(o["accelerate"]) == key), default=None)
                if any(o["golds"] == k and bool(o["accelerate"]) == key and o["recycled"] == recycled for o in out):
                    continue
                if k and fewest is not None and sum(n for _d, n in recycled) >= fewest:
                    continue
                out.append({"golds": k, "gold_domain": gold_domain, "prefer": prefer, "accelerate": acc,
                            "recycled": recycled, "text": payment_text(k, recycled)})
    if any(o["accelerate"] is not None for o in out):   # the move asks it on some way: the others are "No"
        for o in out:
            if o["accelerate"] is None:
                o["accelerate"] = False
    return out


def gold_only_plays(loop, side: str, point: DecisionPoint, legal: list) -> list:
    """The cards `side` can play only with its Golds' Power: [(action, info)],
    the info as action_info gives it, read once the Golds are used."""
    lanes = _golds(loop, side, point)
    if not lanes:
        return []
    p = loop.gs.get_player(side)
    champ = loop.gs.champion_A if side == "A" else loop.gs.champion_B
    domains: list = []
    for card in list(p.hand) + ([champ] if champ is not None else []):
        domains += [d for d in _pay_domains(loop, side, card) if d not in domains]
    out: dict = {}
    for domain in domains:
        clone = loop.gs.clone()
        copy = CoachLoop(clone)
        copy.chooser = lambda _l, kind, s, options, default, source, d=domain: \
            options.index(d) if kind.startswith("domain") and s == side and d in options else None
        try:
            for _ in lanes:
                copy._apply_action(clone.get_player(side), ("ABILITY", "ACTIVATED", _golds(copy, side, point)[0]))
            for a in legal_actions(copy, point, side):
                t = a.to_engine()
                if t[0] in _PAY_KINDS and t[0] != "ABILITY" and t not in legal and t not in out:
                    out[t] = action_info(copy, side, side, point, t)
        except Exception:  # noqa: BLE001
            continue
    return [(t, info) for t, info in out.items() if payment_options(loop, side, point, t)]


class _GoldDomain:
    """The domain a Gold Adds, chosen with the card it pays for: answers the
    player's next "which domain" choice, then leaves the chain of choosers."""

    def __init__(self, me: str, domain, loop, previous):
        self.me, self.domain, self.loop, self.previous = me, domain, loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if side == self.me and kind.startswith("domain") and self.domain in options:
            self.release()
            return options.index(self.domain)
        return self.previous(loop, kind, side, options, default, source) if self.previous else None

    def release(self) -> None:
        _unlink(self.loop, self)


class _AccelerateAnswer:
    """The answer to the next "Pagare ACCELERATE?" of the player's move, given
    with its way to pay (asked before "Come paghi?", not again by the engine);
    then leaves the chain of choosers."""

    def __init__(self, me: str, answer: bool, loop, previous):
        self.me, self.answer, self.loop, self.previous = me, answer, loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if side == self.me and kind == "optional:accelerate" and self.answer in options:
            self.release()
            return options.index(self.answer)
        return self.previous(loop, kind, side, options, default, source) if self.previous else None

    def release(self) -> None:
        _unlink(self.loop, self)


def accelerate_asked(ways: list) -> bool:
    """Do the ways to pay a move hold both answers to "Pagare ACCELERATE?"."""
    return {True, False} <= {w.get("accelerate") for w in ways}


def accelerate_ways(ways: list, answer: bool) -> list:
    """The ways for `answer` ("Sì" = True), (index in `ways`, way) pairs; Sì: only
    the ways that pay ACCELERATE; No: those that do not (False) or never ask (None)."""
    return [(i, w) for i, w in enumerate(ways)
            if (w.get("accelerate") is True if answer else w.get("accelerate") in (None, False))]


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
    elif kind == "SPELL" and spell_lane_free(loop, side, point, idx):
        text = f"Lancia {name}"          # one cast; its target is the next question
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
        if point == DecisionPoint.TURN_ACTION and dst is not None and dst != n_bf:
            text, to = f"Gioca il campione {name} su {_bf_name(gs, dst)}", f"bf:{dst}"
        elif point == DecisionPoint.TURN_ACTION:
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
        keys = _choice_keys(_loop, kind, s, options, source) if not seen and s == side else []
        if force in keys:
            opt = options[keys.index(force)]
            head = kind.partition(":")[0]
            # "you may" of a card that isn't the move's (Shadow Clone attacking
            # when the showdown starts): name the card.
            name = getattr(source, "name", None)
            text = f"{name + ': ' if name else ''}{question(kind)} {option_text(_loop.gs, side, opt)}" \
                if head == "optional" else f"{_SHORT.get(head, 'scelta')}: {option_text(_loop.gs, side, opt)}"
            seen.update(text=", ".join(targets + [text]), ref=option_ref(_loop.gs, side, opt))
            return keys.index(force)
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
        # The engine keeps no exhausted rune, only the Energy not spent yet
        # (`rune_energy`, Player.channel): as many runes are ready, the first
        # ones in the pool's order; the others are drawn exhausted.
        p = gs.get_player(side)
        ready = max(0, p.rune_energy)
        pool = [d for d, rs in p.rune_pool.items() for _r in rs]
        return [{"domain": d.name, "ready": k < ready} for k, d in enumerate(pool)]

    def gear_exhausted(side):
        # In the Observation's order: base gear, then each battlefield's.
        return {"base": [bool(getattr(g, "tapped", False)) for g in gs.get_player(side).base_gear],
                **{str(i): [bool(getattr(dg.card, "tapped", False)) for dg in bf.gear_for(side)]
                   for i, bf in enumerate(gs.battlefields)}}
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
        "gear_exhausted": {"me": gear_exhausted(viewer), "opp": gear_exhausted(gs.other(viewer))},
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


def _card_texts(obs: Optional[dict], extras: Optional[dict] = None, more=()) -> dict:
    """Printed text, type, cost, Might and image code of the cards on view
    (and `more`: the ones a question shows, such as those looked at)."""
    if not obs:
        return {}
    names: set = set(obs.get("my_hand") or []) | set(more)
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

_UNASKED = object()


class _CoachChooser:
    """While a move the coach picked resolves: its player's choices (any kind
    with more than one option) are asked to the coach."""

    def __init__(self, me: str, session: "CoachSession", loop, previous):
        self.me, self.session, self.loop, self.previous = me, session, loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if side == self.me and kind == "optional:sett_save":
            pick = self.session.ask_save(getattr(source, "name", None))
            if pick is not None:
                return pick
        if side == self.me and len(options) > 1:
            gs = loop.gs
            described = [{"text": option_text(gs, side, o), "ref": option_ref(gs, side, o)}
                         for o in options]
            # Options the page can't tell apart are one (Matteo, 25/11: two Pyke
            # Returned, five enemy deaths, ten "abilità di Pyke Returned" to order).
            keys = [(d["text"], d["ref"]) for d in described]
            firsts = [i for i, k in enumerate(keys) if k not in keys[:i]]
            if len(firsts) > 1:
                shown = firsts.index(keys.index(keys[default])) if 0 <= default < len(keys) else 0
                pick = self.session.ask_choice(kind, side, [described[i] for i in firsts], shown,
                                               getattr(source, "name", None))
                return firsts[pick] if 0 <= pick < len(firsts) else default
        return self.previous(loop, kind, side, options, default, source) if self.previous else None

    def release(self) -> None:
        _unlink(self.loop, self)


def decision_context(gs, side: str, point: DecisionPoint, bf_idx: Optional[int] = None) -> str:
    """What a decision of `side` is about, in a sentence (the page's context line)."""
    if point == DecisionPoint.SHOWDOWN_ACTION:
        where = _bf_name(gs, bf_idx if bf_idx is not None else gs.showdown_bf_idx or 0)
        return f"Showdown su {where}: puoi giocare magie veloci (ACTION, REACTION) o passare."
    if point == DecisionPoint.REACTION and gs.chain:
        top = gs.chain[-1]
        who = "L'avversario ha lanciato" if top.player != side else "Hai lanciato"
        if top.ability is not None:
            who = "L'avversario ha usato" if top.player != side else "Hai usato"
            if top.ability["kind"] in ("triggered", "reflexive"):
                who = "Si è innescata per l'avversario" if top.player != side \
                    else "Si è innescata per te"
        chose = declared_text(gs, side, top)
        return f"{who} {chain_name(top)}" + (f" ({chose})" if chose else "") + \
            ": puoi rispondere con una reazione o lasciar correre."
    if gs.pending_move is not None and gs.pending_move[1] == side:
        where = _bf_name(gs, gs.pending_move[0])
        return (f"Stai spostando unità su {where}: puoi mandarne altre insieme. "
                "Quando hai finito parte lo showdown, poi il turno continua.")
    return "È il tuo turno: puoi giocare carte, spostare unità, usare abilità o passare."


class CoachAgent(NetGuidedMCTSAgent):
    """The net searches; the coach decides (see the module docstring). With no
    net (`net=None`) there is no search: the coach plays alone, with no
    suggestions, and nothing is kept for training."""

    def __init__(self, player, net, session: "CoachSession", **kw):
        super().__init__(player, net, **kw)
        self.session = session
        self._gold_plan: Optional[dict] = None    # a card paid with Golds: the Golds first

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
        values = self.mulligan_values() if self.net is not None else []
        for combo, v in sorted(values, key=lambda cv: -cv[1]):
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
        return decision_context(self.gs, self.player.name, point, bf_idx)

    def _coached(self, point: DecisionPoint, cards_played: int = 0, bf_idx: Optional[int] = None):
        self.session.show_looked()
        self._ensure_rng()
        if point == DecisionPoint.TURN_ACTION:
            self._release_forced()
            self._release_coach()
        side = self.player.name
        self.loop.recycle_first = None          # a [rune] domain chosen for a move: that move only
        c = self.loop.chooser                   # an ACCELERATE answer is for that move only
        while c is not None:
            prev = getattr(c, "previous", None)
            if isinstance(c, _AccelerateAnswer) and c.me == side:
                c.release()
            c = prev
        legal = legal_actions(self.loop, point, side)
        if self._gold_plan is not None:        # a card paid with Golds: its next step
            step = self._gold_step(side, point, [a.to_engine() for a in legal])
            if step is not None:
                return step
        if len(legal) <= 1:
            self.session._snapshot()            # the page never asks: the log still catches up
            if point == DecisionPoint.REACTION:
                self.session.notice_chain()
            return legal[0].to_engine() if legal else _PASS
        self.session.thinking(point)
        tuples = [a.to_engine() for a in legal]
        infos = [action_info(self.loop, side, side, point, t) for t in tuples]
        # Cards only the Golds' Power pays for: offered too, after the engine's moves.
        gold_only = gold_only_plays(self.loop, side, point, tuples)
        infos += [{**info, "text": info["text"] + " (col Gold)"} for _t, info in gold_only]
        suggestions = []
        ranked, total = [], 1
        if self.net is not None:           # without a net: no search, no advice
            root = self.search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
            total = sum(c.N for c in root.children.values()) or 1
            ranked = self.variants(root)
            if ranked and self.prefer_pass(root, ranked[0][0]) == _PASS and ranked[0][0] != _PASS:
                # The net would pass: its top move isn't clearly better (prefer_pass).
                ranked = [kv for kv in ranked if kv[0] == _PASS] + [kv for kv in ranked if kv[0] != _PASS]
        for key, n_visits, w_total in ranked:
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
                same["share"] += n_visits / total
                continue
            q = w_total / n_visits if n_visits else 0.0
            suggestions.append({"key": key, "action": i, "share": n_visits / total, "win": (q + 1) / 2,
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
            i = int(answer["action"])
            action = tuples[i] if i < len(tuples) else gold_only[i - len(tuples)][0]
            self.loop.chooser = _CoachChooser(side, self.session, self.loop, self.loop.chooser)
            best = _split_key(suggestions[0]["key"])[0] if suggestions else None
            corrected = action != best
        auto = bool(answer.get("auto"))      # the net finishing the game on its own
        ways = payment_options(self.loop, side, point, action) if not auto and force is None else []
        if ways:
            card = _paid_card(self.loop, side, action)
            text = next((info["text"] for t, info in zip(tuples, infos) if t == action), None) \
                or next(info["text"] for t, info in gold_only if t == action).removesuffix(" (col Gold)")
            name = getattr(card, "name", None) or text
            if accelerate_asked(ways):          # "Pagare ACCELERATE?" first, the ways are for its answer
                yes = self.session.ask_choice("optional:accelerate", side,
                                              [{"text": "Sì", "ref": None}, {"text": "No", "ref": None}], 0, name) == 0
                ways = [w for _i, w in accelerate_ways(ways, yes)]
            pick = 0
            if len(ways) > 1:
                pick = self.session.ask_choice("payment", side, [{"text": w["text"], "ref": None} for w in ways],
                                               0, name)
            way = ways[pick]
            if not way["golds"]:
                self.loop.recycle_first = (side, way["prefer"]) if way["prefer"] is not None else None
                if way.get("accelerate") is not None:
                    self.loop.chooser = _AccelerateAnswer(side, way["accelerate"], self.loop, self.loop.chooser)
            else:
                self._gold_plan = {"left": way["golds"], "domain": way["gold_domain"], "prefer": way["prefer"],
                                   "accelerate": way.get("accelerate"), "action": action, "point": point,
                                   "card": getattr(card, "name", None) or text, "text": text}
                step = self._gold_step(side, point, tuples)
                if step is None:                 # not possible after all: asked again
                    return self._coached(point, cards_played, bf_idx)
                if self.net is not None:
                    self.session.record(self.gs, side, legal, step, corrected)
                return step
        if action != _PASS or force is not None:
            # A suggestion taken says the choice it makes too ("Fatto: parte lo
            # showdown → Shadow Clone: Usare questo effetto? Sì").
            i = tuples.index(action)
            text = suggestions[int(answer["suggestion"])]["text"] if force is not None \
                else infos[i]["text"]
            if auto:
                note = " (la rete, da sola)" if self.net is not None else " (partita lasciata)"
            else:
                note = "" if not suggestions else " (diversa dalla rete)" if corrected else " (come la rete)"
            self.session.event("me", text + note, move=True)
        if not auto and self.net is not None:   # no net, no training examples
            self.session.record(self.gs, side, legal, action, corrected)
        return action

    def _gold_step(self, side: str, point: DecisionPoint, tuples: list):
        """The next step of a card paid with Golds: a Gold (Adding the domain
        the card needs), then the card. An Add ability keeps the player's
        priority, so the steps follow one another. None: the plan is over or
        no longer possible (the decision is asked as usual)."""
        plan = self._gold_plan
        if plan["point"] != point:
            self._gold_plan = None
            return None
        lanes = _golds(self.loop, side, point)
        gold = ("ABILITY", "ACTIVATED", lanes[0]) if lanes else None
        if plan["left"] > 0 and gold in tuples:
            plan["left"] -= 1
            self.loop.chooser = _GoldDomain(side, plan["domain"], self.loop, self.loop.chooser)
            domain = plan["domain"].name.title()
            self.session.event("me", f"Usa Gold: Power {domain} per pagare {plan['card']}", move=True)
            return gold
        self._gold_plan = None
        if plan["action"] not in tuples:
            return None
        if plan["prefer"] is not None:
            self.loop.recycle_first = (side, plan["prefer"])
        self.loop.chooser = _CoachChooser(side, self.session, self.loop, self.loop.chooser)
        if plan.get("accelerate") is not None:
            self.loop.chooser = _AccelerateAnswer(side, plan["accelerate"], self.loop, self.loop.chooser)
        self.session.event("me", plan["text"], move=True)
        return plan["action"]


class CoachSession:
    """One coached game at a time, on its own thread, for the web page."""

    def __init__(self, net_path: Optional[Path] = None, out_dir: Path = Path("runs") / "coach",
                 iterations: int = 100, opponent_pause: float = 0.8,
                 campione_path: Optional[Path] = None, budget: float = 0.4,
                 motore: str = "python", regole: str = REGOLE_D72_D80, iterazioni: Optional[int] = None,
                 valutazione: str = "storica"):
        # The old AlphaZero net: the advice to the coach and the "net"
        # opponent. Without it the coach plays alone (no advice, nothing kept
        # for training).
        self.net_path = None if net_path is None else Path(net_path)
        # The champion's PPO checkpoint and its CPU seconds a decision.
        self.campione_path = None if campione_path is None else Path(campione_path)
        self.budget = budget
        # The engine the page plays on (25/11, phase 4): "rust" (scripts/coach.py's default) plays with
        # the rules profile `regole` whatever game Rust covers (riftbound/ai/coach_rs.py), else Python;
        # "python" (this class's default: the frozen engine) always Python.
        # `iterazioni`: the champion's fixed iterations a decision on Rust.
        self.motore, self.regole = motore, regole
        self.iterazioni = iterazioni
        # The evaluation of the champion's search leaves on Rust ("storica", "rimonta", ...); ignored on Python.
        self.valutazione = valutazione
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.iterations = iterations
        # Seconds the board holds still before each opponent decision that
        # follows a change, so the coach can watch what the opponent does.
        self.opponent_pause = opponent_pause
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.status = "idle"            # idle | opening | thinking | waiting | over
        self.activity = ""
        self._answers: "queue.Queue" = queue.Queue()
        self.pending: Optional[dict] = None
        self.examples: list = []
        self.log: deque = _Full(maxlen=400)       # .full: every line, for the saved game
        self.events: deque = _Full(maxlen=300)
        self.notes: list = []                     # the reports made in this game
        self.partita_path: Optional[Path] = None  # where _save_game wrote the game
        self._partita_name: Optional[str] = None
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
        self._opponent = None               # the other seat's agent
        self.looked: Optional[list] = None  # the coach's last look at their deck's top, not yet shown
        self._seen: Optional[list] = None   # ... and the last one shown with a choice
        self._dying: list = []              # the coach's units dying together (_route_deaths)
        self._replacing = None              # the one whose death may be replaced now
        self._save_pick = _UNASKED          # the one the coach saves (ask_save)
        self._dying_bf = None               # where they die (None: in base)
        # Rewind (Matteo, 25/11, as RiftAtlas's): the coach's answered decisions,
        # each with the page as it was asked; the game is rebuilt from its seed
        # and replayed from its record up to the last one, asked again.
        self.checkpoints: list = []
        self.rewinds = 0
        self._replaying = False             # a rewind replays the game: the page holds still
        self._resume_cp: Optional[dict] = None
        self._build: Optional[dict] = None  # what new_game built the game from
        self.rs = None                      # the Rust game (coach_rs.RustGame), None on Python
        self.apertura: Optional[dict] = None    # the opening the page shows (status "opening")
        self._ap: dict = {}                 # ... and what it keeps hidden until both fields are shown

    # -- what a game can have ------------------------------------------------------

    @property
    def advice(self) -> bool:
        """Whether the net advises the coach (and their decisions train it)."""
        return self.net_path is not None and self.net_path.is_file()

    def opponents(self) -> list:
        """The opponents a game can have, for the page's menu: the champion
        first when its checkpoint is there, the net only when there is one."""
        out = []
        if self.campione_path is not None and self.campione_path.is_file():
            out.append({"id": "campione", "name": _OPPONENTS["campione"], "decks": list(CAMPIONE_DECKS)})
        if self.advice:
            out.append({"id": "net", "name": _OPPONENTS["net"]})
        out.append({"id": "simple_trade", "name": _OPPONENTS["simple_trade"]})
        return out

    # -- the game thread ---------------------------------------------------------

    def new_game(self, deck_mine: Path, deck_opp: Path, seat: str = "A",
                 opponent: Optional[str] = None, seed: Optional[int] = None, apertura: bool = False) -> None:
        """Start a game: the coach's seat plays `deck_mine`, with the net's
        search as advisor when there is a net; the other seat is one of
        opponents() (the first by default): the champion ("campione"), the net
        ("net") or the simple_trade heuristic ("simple_trade"). ValueError for
        one that isn't available. With `apertura` (the page: 25/11, as RiftAtlas) the game waits
        in the opening (status "opening": battlefield, d20, who starts: scegli_campo, inizia)
        and starts with those choices; without, the seed's coin flip and random battlefields."""
        available = [o["id"] for o in self.opponents()]
        opponent = opponent or available[0]
        if opponent not in available:
            if opponent == "campione":
                raise ValueError(f"Il campione non è disponibile: manca il checkpoint {self.campione_path}")
            if opponent == "net":
                raise ValueError("La rete non è disponibile: avvia la pagina con --net")
            raise ValueError(f"Avversario sconosciuto: {opponent}")
        # The nets first: a checkpoint that doesn't load leaves the game on.
        net = ppo = None
        if self.advice:
            import torch

            from riftbound.ai.net import load_checkpoint
            net = load_checkpoint(self.net_path, device=torch.device("cpu"))
        if opponent == "campione":
            ppo = _ppo_net(self.campione_path)
        if self._thread is not None and self._thread.is_alive():
            self.abandon()
            self._thread.join(timeout=60)
        self._reset()
        seed = random.randrange(1 << 30) if seed is None else seed
        deck_a, deck_b = (deck_mine, deck_opp) if seat == "A" else (deck_opp, deck_mine)
        self.side = seat
        self._build = {"seed": seed, "deck_a": Path(deck_a), "deck_b": Path(deck_b),
                       "deck_mine": Path(deck_mine), "deck_opp": Path(deck_opp),
                       "opponent": opponent, "net": net, "ppo": ppo,
                       # the opening's choices (None: the seed's, as before): a rewind keeps them
                       "bf_a": None, "bf_b": None, "starter": None}
        self.info = {"seed": seed, "seat": seat, "deck_mine": Path(deck_mine).stem,
                     "deck_opp": Path(deck_opp).stem, "opponent": opponent,
                     "net": str(self.net_path) if net is not None else None,
                     "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self._partita_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{Path(deck_a).stem}_vs_{Path(deck_b).stem}.json"
        if opponent == "campione":
            self.info.update(campione=str(self.campione_path), budget=self.budget)
        if apertura:
            self._apri()
        else:
            self._avvia()

    # -- the opening (RiftAtlas, 25/11): battlefield, d20, who starts -------------------

    def _opp_name(self) -> str:
        return _OPPONENTS.get(self._build["opponent"], "L'avversario")

    def _apri(self) -> None:
        from riftbound.core.game_factory import deck_battlefield_names
        b = self._build
        mine, theirs = deck_battlefield_names(b["deck_mine"]), deck_battlefield_names(b["deck_opp"])
        self._ap = {"mine": mine, "theirs": theirs, "bf_mine": None, "bf_opp": None, "roll": None, "inizia": None}
        self.apertura = {"step": "campo", "mine": mine, "opp_n": len(theirs), "opp": None, "bf_mine": None,
                         "bf_opp": None, "tiri": None, "chi_decide": None, "inizia": None,
                         "opponent": self._opp_name()}
        self.status, self.activity = "opening", "Scegli il tuo campo di battaglia"

    def scegli_campo(self, choice: Optional[str]) -> None:
        """The coach's battlefield (a name of their deck, or None/"random": at random); the champion
        chooses too (apertura.scegli_campo), both are shown, then the d20 (a generator of the seed)."""
        from riftbound.ai import apertura as ap
        with self._lock:
            a = self.apertura
            if self.status != "opening" or not a or a["step"] != "campo":
                raise RuntimeError("Il campo di battaglia non si sceglie ora.")
            seed, b, own = self._build["seed"], self._build, self._ap
            if choice in (None, "", "random", "casuale"):
                choice = random.Random(seed * 3 + 2).choice(own["mine"])
            elif choice not in own["mine"]:
                raise ValueError(f"Campo sconosciuto: {choice}")
            theirs = ap.scegli_campo(b["deck_opp"].stem, b["deck_mine"].stem, own["theirs"],
                                     random.Random(seed * 3 + 1))
            rng = random.Random(seed * 3 + 3)
            rolls = []
            while True:                                  # a tie is rolled again
                rolls.append((rng.randint(1, 20), rng.randint(1, 20)))
                if rolls[-1][0] != rolls[-1][1]:
                    break
            mio, suo = rolls[-1]
            if mio > suo:
                inizia = None                            # the coach decides
            else:
                inizia = "io" if not ap.scegli_inizio(b["deck_opp"].stem, b["deck_mine"].stem,
                                                      theirs, choice) else "avv"
            a.update(step="tiro", opp=theirs, bf_mine=choice, bf_opp=theirs, tiri=[list(r) for r in rolls],
                     chi_decide="io" if mio > suo else "avv", inizia=inizia)
            self.activity = "Tiro del d20"
        who = self._opp_name()
        self.event("sys", f"Campi di battaglia: tu {choice}, {who.lower()} {theirs}")
        self.event("sys", "d20: " + "; ".join(f"tu {m}, {who.lower()} {o}" for m, o in rolls)
                   + (" (pari: si ritira)" if len(rolls) > 1 else ""))
        if inizia is not None:
            self._dichiara_inizio(inizia, scelto_da=who)

    def _dichiara_inizio(self, inizia: str, scelto_da: Optional[str] = None) -> None:
        self.event("sys", (f"{scelto_da} sceglie di " + ("cominciare" if inizia == "avv" else "lasciarti cominciare"))
                   if scelto_da else ("Hai scelto di cominciare tu" if inizia == "io" else "Hai scelto che cominci l'avversario"))

    def inizia(self, io: Optional[bool] = None) -> None:
        """Who starts, then the game: `io` the coach's decision when they won the d20 (None: the
        champion's, already taken). The game is built with the two battlefields and the first player."""
        with self._lock:
            a = self.apertura
            if self.status != "opening" or not a or a["step"] != "tiro":
                raise RuntimeError("Chi comincia non si decide ora.")
            if a["inizia"] is None:
                if io is None:
                    raise ValueError("Scegli chi comincia.")
                a["inizia"] = "io" if io else "avv"
                decided = True
            else:
                decided = False
        if decided:
            self._dichiara_inizio(a["inizia"])
        b, seat = self._build, self.side
        mine_starts = a["inizia"] == "io"
        b["starter"] = seat if mine_starts else ("B" if seat == "A" else "A")
        bf_seat, bf_other = a["bf_mine"], a["bf_opp"]
        b["bf_a"], b["bf_b"] = (bf_seat, bf_other) if seat == "A" else (bf_other, bf_seat)
        self.info.update(campo_mio=bf_seat, campo_avv=bf_other, inizia="io" if mine_starts else "avv")
        self.apertura = None
        self._avvia()

    def _avvia(self) -> None:
        """The game the opening (or new_game) asked for: the engine, the agents, the game thread."""
        b, seat = self._build, self.side
        deck_mine, deck_opp, opponent = b["deck_mine"], b["deck_opp"], b["opponent"]
        motore = self._engine_for(deck_mine, deck_opp, opponent)
        if motore == "rust":
            from riftbound.ai.coach_rs import RustGame
            self.rs = RustGame(self)
            gs, starter = None, self.rs.starter
        else:
            gs = self._new_state()
            starter = gs.active
        self.gs = gs
        self.info.update(motore=motore, regole=self.regole if motore == "rust" else REGOLE_PYTHON)
        if motore == "rust" and b["opponent"] == "campione":
            self.info["valutazione"] = self.valutazione
        # Who starts: the mulligan depends on it.
        self.info["you_start"] = starter == seat
        self.event("sys", self._starter_text())
        self.status = "thinking"
        self.activity = "La partita sta iniziando…"
        self._thread = threading.Thread(target=self._run, name="rbsim-coach", daemon=True)
        self._thread.start()

    def _engine_for(self, deck_mine: Path, deck_opp: Path, opponent: str) -> str:
        """"rust" when the page's engine is Rust and this game is one it plays: no net's advice
        or opponent (they stay on Python), the two lists among the covered ones."""
        if self.motore != "rust" or self.advice or opponent == "net":
            return "python"
        from riftbound.ai import coach_rs
        return "rust" if coach_rs.giocabile(deck_mine, deck_opp) else "python"

    def _new_state(self):
        """The game new_game asked for, as it starts (its seed: the same deck
        order, the same coin flip), with its agents: a rewind rebuilds it."""
        from riftbound.core.game_factory import build_game, make_agent
        b, seat = self._build, self.side
        seed, net, opponent = b["seed"], b["net"], b["opponent"]
        gs = build_game(game_seed=seed, deck_a_path=b["deck_a"], deck_b_path=b["deck_b"],
                        ai_a=None, ai_b=None, first_player=(b["starter"] or "random").lower(),
                        bf_a=b["bf_a"], bf_b=b["bf_b"])
        me, them = gs.get_player(seat), gs.get_player(gs.other(seat))
        me.agent = CoachAgent(me, net, self, iterations=self.iterations, rng=random.Random(seed))
        if opponent == "campione":
            from riftbound.ai.ppo.prior_bot import PPOPriorAgent
            them.agent = PPOPriorAgent(them, b["ppo"], rng=random.Random(seed + 1), budget=self.budget)
        elif opponent == "net":
            them.agent = NetGuidedMCTSAgent(them, net, iterations=self.iterations,
                                            rng=random.Random(seed + 1))
        else:
            them.agent = make_agent(opponent, them)
        self._opponent = them.agent
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
        return gs

    def _starter_text(self) -> str:
        if "you_start" not in self.info:
            return ""
        return "Inizi tu" if self.info["you_start"] else \
            "Inizia l'avversario: al tuo primo turno canalizzi una runa in più"

    def _watch(self, loop) -> None:
        """What the page needs from the real game loop, without changing its
        rules: the opponent's discards, the coach's looks at the top of their
        deck, the units dying together (Sett The Boss saves one), the choices."""
        opp = self.gs.get_player(self.gs.other(self.side))
        me = self.gs.get_player(self.side)

        def discard(player, card, _inner=loop._discard):
            # A discard is public (the card goes to the trash face up).
            if player is opp and card in player.hand:
                self.opp_discards.append(card.name)
            return _inner(player, card)
        loop._discard = discard

        def look(player, cards, _inner=loop._offer_reveal_from_top):
            # The coach looks at the top of their own deck (Trifarian
            # Captain's dig, Predict...): they see the cards, with the
            # choice that follows, or alone when there is none.
            if player is me and cards:
                self._looked([c.name for c in cards])
            return _inner(player, cards)
        loop._offer_reveal_from_top = look

        def route_deaths(ordered, *a, _inner=loop._route_deaths, **k):
            # Units dying together: the engine offers each a replacement in
            # turn ("you may ... instead"); the coach picks one (ask_save).
            kept = (self._dying, self._save_pick, self._dying_bf)
            self._dying, self._save_pick = [u for u, s in ordered if s == self.side], _UNASKED
            self._dying_bf = a[0] if a else k.get("bf")
            if (a[1:2] or [k.get("in_base", False)])[0]:
                self._dying_bf = None
            try:
                return _inner(ordered, *a, **k)
            finally:
                self._dying, self._save_pick, self._dying_bf = kept
        loop._route_deaths = route_deaths

        def replace_death(dead_unit, *a, _inner=loop._try_replace_death, **k):
            kept, self._replacing = self._replacing, dead_unit
            try:
                return _inner(dead_unit, *a, **k)
            finally:
                self._replacing = kept
        loop._try_replace_death = replace_death
        loop.on_choice = self._log_choice

    def _may_be_saved(self, u) -> bool:
        """Whether the engine will offer Sett The Boss's save for `u` (one of
        the coach's units dying together): buffed, and no earlier way out
        of its death in _route_deaths / _try_replace_death (a banish of
        Smite, Mordekaiser's sacrifice, Soraka here, its own or a base gear's
        death replacement, a ward this turn)."""
        from riftbound.registry.cards_registry import CARD_REGISTRY as REG
        loop, gs = self.loop, self.gs
        owner = gs.get_player(self.side)
        if u.might_counters <= 0 or u.banish_if_dies_turn == gs.turn or u.ward_turn == gs.turn:
            return False
        if loop._has_effect(u.card, "sacrifice_instead_of_dying") and \
                gs.once_per_turn_used.get((u.card, "sacrifice_instead_of_dying")) != gs.turn:
            return False
        bf = self._dying_bf
        if bf is not None and any(o is not u and loop._has_effect(o.card, "protect_weaker_here")
                                  and u.might < o.might for o in bf._units_for(self.side)):
            return False
        if loop._unit_death_replacement(u) is not None:
            return False
        return not any(e.trigger == "death_replacement" and e.effect in loop._DEATH_REPLACEMENT_EFFECTS
                       for g in owner.base_gear for e in (REG[g.name].effects if g.name in REG else ()))

    def ask_save(self, source: Optional[str]) -> Optional[int]:
        """Sett The Boss ("If a buffed unit you control would die, you may pay
        [rune], exhaust me, and spend its buff to heal it ... instead"), asked
        once for the units dying together: which one to save. The engine's
        yes/no for each unit in turn follows the pick. None: not a death the
        page saw (the generic question)."""
        unit = self._replacing
        if unit is None or not self._dying:
            return None
        if self._save_pick is _UNASKED:
            cands = [u for u in self._dying if self._may_be_saved(u)]
            if not any(u is unit for u in cands):
                cands.insert(0, unit)
            names = [u.card.name for u in cands]
            texts = [f"{n} (Might {u.might})" + (f" n°{names[:i].count(n) + 1}" if names.count(n) > 1 else "")
                     for i, (n, u) in enumerate(zip(names, cands))]
            dying = ", ".join(u.card.name for u in self._dying)
            options = [{"text": f"Salva {t}", "ref": None} for t in texts] + \
                      [{"text": "Non salvare nessuna", "ref": None}]
            answer = self._wait({
                "type": "choice", "kind": "sett_save", "question": "Quale unità salvare?",
                "source": source, "default": 0, "options": options,
                "context": f"Muoiono: {dying}. Ne puoi salvare una: paghi 1 Power, la leggenda si "
                           "esaurisce, l'unità spende il suo buff, si cura, si esaurisce e torna in base."})
            pick = int(answer.get("option", 0)) if answer else 0
            pick = pick if 0 <= pick < len(options) else len(cands)
            self._save_pick = cands[pick] if pick < len(cands) else None
            self.event("me", f"{source + ': ' if source else ''}" + (
                f"salvi {texts[pick]}" if pick < len(cands) else "non salvi nessuna unità"), move=True)
        return 0 if self._save_pick is unit else 1

    def _run(self) -> None:
        log = _thread_log()
        log.sinks[threading.get_ident()] = self.log
        try:
            entries = None
            while True:
                try:
                    result = self._play(entries)
                    break
                except _Rewind:
                    cp = self.checkpoints.pop()
                    entries = self.loop.record[:cp["record"]]
                    self._resume_cp = cp
                    self.rewinds += 1
            self.result = {"winner": result.winner, "turns": result.turns,
                           "you_won": result.winner == self.side}
            if not self._abandoned:
                self._save(result.winner)
            else:
                self._save_game(abandoned=True)
        except _ReplayError as exc:
            self.result = {"error": f"Annulla: la partita rigiocata è diversa ({exc})"}
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

    def _play(self, entries: Optional[list]):
        """The game on this thread: from its start, or (`entries`: a rewind)
        rebuilt and replayed from its record up to the coach's decision asked
        again, the page holding still meanwhile (_resume)."""
        if self.rs is not None:
            return self.rs.play(entries)
        log = _thread_log()
        if entries is not None:
            self.gs = self._new_state()
            self._replaying = True
            log.sinks[threading.get_ident()] = deque(maxlen=50)    # the replay's lines: not shown
        record = _Record(entries or [])
        for p in (self.gs.A, self.gs.B):
            p.agent = _Seat(p.agent, record, self._resume if p.name == self.side else None)
        self.loop = CoachLoop(self.gs, verbose=True)
        for p in (self.gs.A, self.gs.B):
            p.agent.live.gs, p.agent.live.loop = self.gs, self.loop
        record.loop = self.loop
        self.loop.chooser = record          # at the bottom of the chain, from the start
        self.loop.journal = []              # the champion's segments, from the start
        self._watch(self.loop)
        return self.loop.start()

    def _resume(self) -> None:
        """A rewind's replay reached the coach's decision: the page as it was
        when that decision was asked; the game goes on live."""
        if not self._replaying:
            return
        cp, self._replaying = self._resume_cp, False
        _thread_log().sinks[threading.get_ident()] = self.log
        del self.log.full[cp["n_log"]:]
        del self.events.full[cp["n_events"]:]
        self.log.clear()
        self.log.extend(cp["log"])
        self.events.clear()
        self.events.extend(cp["events"])
        del self.examples[cp["examples"]:]
        for k in ("looked", "_seen", "opp_discards", "stop_on_opp_chain", "opp_mulligan", "opening"):
            setattr(self, k, cp[k])
        same = Observation.from_state(self.gs, self.side).to_dict() == cp["view"] and \
            _board_extras(self.gs, self.side) == cp["extras"]
        self.view, self.extras = cp["view"], cp["extras"]
        if not same:
            raise _ReplayError("il tavolo non coincide")
        self.event("sys", "Mossa annullata: torni alla tua decisione di prima")

    def _checkpoint(self) -> dict:
        """The page as the coach is asked a decision: where a rewind takes them back."""
        self._snapshot()
        return {"record": len(getattr(self.loop, "record", ())), "events": list(self.events),
                "log": list(self.log), "n_log": len(self.log.full), "n_events": len(self.events.full),
                "view": self.view, "extras": self.extras,
                "examples": len(self.examples), "looked": self.looked, "_seen": self._seen,
                "opp_discards": list(self.opp_discards), "stop_on_opp_chain": self.stop_on_opp_chain,
                "opp_mulligan": self.opp_mulligan, "opening": self.opening}

    def _keep(self, cp: dict, answer: dict) -> None:
        """An answered decision: a rewind may take the coach back to it."""
        if answer and not answer.get("auto") and hasattr(self.loop, "record"):
            self.checkpoints.append(cp)

    def _snapshot(self) -> bool:
        """The coach's view of the board, taken on the game thread (the page
        never reads the live game); what changed since the last one goes to the
        log. Returns whether anything changed."""
        if self.gs is None or self.side is None or self._replaying:
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
    _LEFT = "Partita lasciata: passi tu, l'avversario la chiude da solo…"   # no net to finish it

    def _finishing(self) -> str:
        return self._FINISHING if self.advice else self._LEFT

    def _looked(self, names: list) -> None:
        if self._replaying:
            return
        self.show_looked()                 # an earlier look nobody showed yet
        self.looked, self._seen = names, None
        n = len(names)
        self.event("me", ("Guardi la prima carta del mazzo: " if n == 1 else
                          f"Guardi le prime {n} carte del mazzo: ") + ", ".join(names))

    def _take_looked(self) -> Optional[list]:
        names, self.looked = self.looked, None
        return names

    def show_looked(self) -> None:
        """The cards the coach looked at with no choice after them (a dig
        with none they may take): held on the board until seen."""
        names = self._take_looked()
        if not names or len(names) < 2:
            return
        self._wait({"type": "notice", "own": True, "cards": names, "card": names[0],
                    "context": f"Hai guardato le prime {len(names)} carte del mazzo: nessuna "
                               "si poteva prendere."})

    def _opponent_turn(self) -> None:
        if self._replaying:
            return
        self.show_looked()
        changed = self._snapshot()
        self.status = "thinking"
        self.activity = self._finishing() if self.autoplay else "L'avversario sta giocando…"
        if changed and self.opponent_pause and not self.autoplay:
            time.sleep(self.opponent_pause)

    def event(self, who: str, text: str, move: bool = False) -> None:
        """A line of the Italian log: who is "me", "opp", "sys" or "turn"; a
        move is something a player chose to do (the rest is what happened)."""
        if self._replaying:
            return
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
        if side == self.side and n_options:
            self.looked = None             # the choice after the look was made
        if not is_public_choice(self._PUBLIC_CHOICES, kind, source) or not n_options or self.gs is None:
            return
        mine = side == self.side
        if mine and n_options > 1:
            return                         # asked on the page, logged there
        if not mine and head == "discard":
            return                         # opp_discards logs it
        name = getattr(source, "name", None)
        label = "rivela e pesca" if head == "keep" else _SHORT.get(head, "scelta")
        text = f"{name + ': ' if name else ''}{label} → " \
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
        self.activity = self._finishing() if self.autoplay else \
            "La rete sta pensando alla tua mossa…" if self.advice else "Tocca a te…"

    def _wait(self, request: dict) -> dict:
        """Ask the coach and wait; {} once the net finishes the game alone.
        A rewind (self.rewind) leaves the game here (_Rewind)."""
        if self._replaying:
            raise _ReplayError(f"una domanda durante il replay ({request.get('type')})")
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
        if answer.get("rewind"):
            self.activity = "Torno alla tua mossa di prima…"
            raise _Rewind()
        return answer

    def ask_decision(self, point: DecisionPoint, side: str, actions: list, suggestions: list,
                     context: str = "") -> dict:
        cp = self._checkpoint()
        answer = self._wait({"type": "decision", "point": point.value, "context": context,
                             "actions": actions,
                             "suggestions": [{k: v for k, v in s.items() if k != "key"}
                                             for s in suggestions]})
        self._keep(cp, answer)
        if not answer:                     # the net finishes alone: its move
            if suggestions:
                return {"suggestion": 0, "auto": True}
            # No net to finish the game (no advice): the coach's seat passes.
            passes = [i for i, a in enumerate(actions) if a.get("kind") == "PASS"]
            return {"action": passes[0] if passes else 0, "auto": True}
        return answer

    def ask_mulligan(self, hand: list, suggestions: list) -> list:
        """The coach's mulligan: the hand indices to send back (up to two)."""
        cp = self._checkpoint()
        answer = self._wait({"type": "mulligan", "hand": [{"text": n, "ref": f"hand:{i}"}
                                                          for i, n in enumerate(hand)],
                             "suggestions": suggestions, "max": 2,
                             "context": "La tua mano iniziale: puoi rimandare in fondo al mazzo "
                                        "fino a 2 carte e pescarne altrettante."
                                        + (f" {self._starter_text()}." if self._starter_text() else "")})
        self._keep(cp, answer)
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
        request = {"type": "choice", "kind": kind, "question": question(kind),
                   "options": options, "default": default, "source": source}
        seen = self._take_looked()
        if seen:
            self._seen = seen
        elif kind.startswith("keep"):
            seen = self._seen               # "Quale carta tenere?" after "Prendere ...?"
        if seen:
            request["seen"] = seen          # the cards looked at, the choice is about them
        answer = self._wait(request)
        if not answer:
            return default
        pick = int(answer.get("option", default))
        if 0 <= pick < len(options):
            self.event("me", f"{source + ': ' if source else ''}{question(kind)} → {options[pick]['text']}",
                       move=True)
        return pick

    # -- the page's side ---------------------------------------------------------

    def answer(self, payload: dict) -> None:
        """Answer the pending question. It stops being pending at once: a
        second answer sent before the game thread took the first one (a double
        click) is refused, not kept for the next question."""
        with self._lock:
            if self.pending is None:
                raise RuntimeError("nothing is waiting for an answer")
            self.pending = None
            self.status, self.activity = "thinking", "Sto giocando la mossa…"
            self._answers.put(payload)

    def finish(self, save: bool = True) -> None:
        """Stop coaching: the net plays the rest of the game on its own, without
        questions or pauses. With `save` the coach's decisions so far are saved
        with the result when it ends (the net's own moves aren't); without,
        nothing is. With no net the coach's seat passes to the end."""
        with self._lock:
            if self.status not in ("thinking", "waiting"):
                return
            self.autoplay = True
            self._abandoned = self._abandoned or not save
            self.info["finished_by_net"] = True
            if self._abandoned and getattr(self._opponent, "budget", None):
                # Nothing of the rest counts: the champion closes it quickly
                # (at 0.4 s a decision that was about ten seconds).
                self._opponent.budget = 0.01
            self.activity = self._finishing()
            if self.pending is not None:
                self._answers.put({})
        if self._abandoned:
            self._save_game(abandoned=True)

    def rewind(self) -> None:
        """Take back the coach's last decision, as RiftAtlas's Rewind: the game
        goes back to the page as it was asked, everything since undone (the
        opponent's moves too, decided again). Only while a question waits."""
        with self._lock:
            if self.status != "waiting" or self.pending is None or self.autoplay or not self.checkpoints:
                raise RuntimeError("Non c'è una tua mossa da annullare.")
            self.pending = None
            self.status, self.activity = "thinking", "Torno alla tua mossa di prima…"
            self._answers.put({"rewind": True})

    def abandon(self) -> None:
        """Let the net finish the game on its own (with no net, the coach's
        seat passes to the end); nothing is saved."""
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

    def _shown_cards(self) -> list:
        """The cards the pending question shows besides the board (looked at
        on top of the deck): the page draws them with their image and text."""
        p = self.pending or {}
        return list(p.get("seen") or []) + list(p.get("cards") or [])

    def state(self) -> dict:
        obs, extras = self.view, self.extras
        return {"status": self.status, "activity": self.activity, "info": self.info,
                "autoplay": self.autoplay, "saving": not self._abandoned,
                "pending": self.pending, "observation": obs, "board": extras,
                "events": self._copy(self.events), "log": self._copy(self.log)[-60:],
                "result": self.result, "decisions": len(self.examples),
                "corrections": sum(1 for e in self.examples if e["corrected"]),
                "cards": _card_texts(obs, extras, self._shown_cards()) or self._opening_cards(),
                "apertura": self.apertura,
                "opponents": self.opponents(), "advice": self.advice,
                "regole": self.info.get("regole", self.regole if self.motore == "rust" else REGOLE_PYTHON),
                "motore": self.info.get("motore", self.motore),
                "can_rewind": self.status == "waiting" and not self.autoplay and bool(self.checkpoints),
                "rewinds": self.rewinds, "partita": str(self.partita_path) if self.partita_path else None}

    def _opening_cards(self) -> dict:
        """The cards the opening shows: the coach's battlefields and, once shown, the champion's."""
        a = self.apertura
        if not a:
            return {}
        names = list(a["mine"]) + ([a["opp"]] if a["opp"] else [])
        return _card_texts({"battlefields": [{"named": n} for n in names]})

    def report(self, note: str) -> Path:
        path = self.out_dir / "reports.jsonl"
        self.notes.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note,
                                 **self.state(), "log": self._copy(self.log),
                                 "opp_mulligan": self.opp_mulligan, "partita": self._game_file()},
                                default=str) + "\n")
        self._save_game()
        return path

    def _iterazioni_effettive(self) -> Optional[int]:
        """The champion's iterations this game really used (Rust), so the file replays even after the default moves."""
        if self.iterazioni or self.motore != "rust":
            return self.iterazioni
        from riftbound.ai.coach_rs import ITERAZIONI_CAMPIONE
        return ITERAZIONI_CAMPIONE

    def _game_file(self) -> Optional[str]:
        """Where this game's file is (or will be): runs/coach/partite/<start>_<deckA>_vs_<deckB>.json."""
        return None if self._partita_name is None else str(self.out_dir / "partite" / self._partita_name)

    def _save_game(self, abandoned: bool = False) -> Optional[Path]:
        """The whole game in its own file, to be sent for review: overwritten at each call (game end,
        abandon, report), the same file for the same game. The full Italian events and technical log,
        what the page knew of the opening, and what replays the game exactly (seed, opening,
        the recorded answers). Never breaks the game: None when it can't be written."""
        if self._partita_name is None or self._build is None:
            return None
        try:
            b, r = self._build, self.result or {}
            rec = list(getattr(self.loop, "record", None) or [])
            data = {"info": self.info, "apertura": self.apertura, "opp_mulligan": self.opp_mulligan,
                    "status": self.status, "abandoned": abandoned or self._abandoned,
                    "result": self.result, "winner": r.get("winner"), "turns": r.get("turns"),
                    "rewinds": self.rewinds, "reports": list(self.notes),
                    "events": list(self.events.full), "log": list(self.log.full),
                    "replay": {"seed": b["seed"], "seat": self.side, "opponent": b["opponent"],
                               "deck_a": str(b["deck_a"]), "deck_b": str(b["deck_b"]),
                               "bf_a": b.get("bf_a"), "bf_b": b.get("bf_b"), "starter": b.get("starter"),
                               "iterazioni": self._iterazioni_effettive(), "regole": self.info.get("regole"),
                               "valutazione": self.info.get("valutazione"),
                               "motore": self.info.get("motore"), "answers": rec}}
            path = self.out_dir / "partite" / self._partita_name
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            self.partita_path = path
            return path
        except Exception:  # noqa: BLE001 — a failed copy never stops the game
            return None

    # -- training examples -----------------------------------------------------------

    def record(self, gs, side: str, legal: list, action, corrected: bool) -> None:
        policy = np.zeros(ACTION_DIM, dtype=np.float32)
        n_bf = len(gs.battlefields)
        idx = action_to_index(action, n_bf)
        if idx is None:
            return
        policy[idx] = 1.0
        self.examples.append({"state": encode_observation(Observation.from_state(gs, side)),
                              "policy": policy, "mask": legal_mask(legal, n_bf), "player": side,
                              "corrected": corrected})

    def _save(self, winner: str) -> Optional[Path]:
        """The coach's decisions (coach_<time>.npz, when there are any) and a
        line with the game's result in games.jsonl (always)."""
        path = None
        if self.examples:
            z = [0.0 if winner == "DRAW" else 1.0 if winner == e["player"] else -1.0 for e in self.examples]
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = self.out_dir / f"coach_{stamp}.npz"
            np.savez_compressed(path, state=np.stack([e["state"] for e in self.examples]),
                                policy=np.stack([e["policy"] for e in self.examples]),
                                mask=np.stack([e["mask"] for e in self.examples]),
                                z=np.asarray(z, dtype=np.float32),
                                corrected=np.asarray([e["corrected"] for e in self.examples]))
        turns = self.result.get("turns") if self.result else None
        with open(self.out_dir / "games.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**self.info, "file": path.name if path else None, "winner": winner,
                                 "you_won": winner == self.side, "turns": turns,
                                 "decisions": len(self.examples), "rewinds": self.rewinds,
                                 "corrections": sum(1 for e in self.examples if e["corrected"])}) + "\n")
        self._save_game()
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
