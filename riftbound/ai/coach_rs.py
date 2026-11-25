"""The coach page on the Rust engine (25/11, phase 4).

`CoachSession.new_game` plays on Rust, with the rules profile `regole` (default
6427b90+D72-D77), a game between two lists the Rust engine covers
(`arena_rs.COPERTI`) against the champion ("campione") or "simple_trade"; the net's
advice and "La rete" stay on Python (6427b90, the frozen engine). The page is the
same: it reads the same JSON (`CoachSession.state()`).

How a game runs here (`RustGame`, on the game thread of the session):
- the human seat is `Game.set_human_agent(seat, ask, payments=True)`: every
  decision and choice of the coach calls `ask(event_json)` (riftbound_rs, docs/RUST.md
  "Posto umano e traccia in diretta"); the event carries the state as a raw dump,
  which `vista_rs.carica` rebuilds as a read-only Python GameState: the texts, the
  refs and the board are the Python page's own functions (`action_info`, `option_text`,
  `_board_extras`, `_card_texts`...) over it. `ask` turns the event into the pending
  question the Python path shows (`CoachSession.ask_decision`, `ask_choice`,
  `ask_mulligan`, "Come paghi?" with `payment_text`), auto-answers where the Python
  page does not ask (a single option; the agent's own `decide_*` defaults; choices
  while no move of the coach is resolving), and turns the page's answer into the
  Rust one (an index; `{"index": i, "via": w}`, `{"solo_gold": j, "via": w}`, a choice's
  index, the mulligan's indices);
- `trace_on(watch)` tells every event live: the opponent's moves keep the board, the
  events and the log updated (the Python `watched` wrappers' job);
- the champion is `set_search_agent(seat, N, seed, budget=None, probs=make_probs(net))`
  with a FIXED number of iterations N (not a time): the game is deterministic from its
  seed and the coach's answers, which the rewind needs;
- rewind: every answer given to the Rust game is recorded (`RsLoop.record`); "Annulla
  l'ultima mossa" raises `_Rewind` from `ask` (it comes out of `start()` as the same
  object), the session rebuilds the same game (same seed, decks, agents) and `ask`
  answers from the record, without asking the page, up to the checkpoint; the session's
  `_resume` then checks the view is the checkpoint's and the game goes on live.

What Rust tells the seat besides the questions (`Agent::notify`, only a human seat, never in the trace):
`notify(event)` of `set_human_agent` is told the cards it looks at on top of its deck ("look"; `RustGame.notify`
-> `CoachSession._looked`, shown with the choice that follows or held on the board when none does), and its
sett_save choice event carries `dying` (the units of its side dying together, the one asked about): the page
asks once which to save (`CoachSession.ask_save`, only the savable ones) and the engine's yes/no per unit is
answered from that pick.
"""
from __future__ import annotations

import json
import random
import threading
from collections import deque
from types import SimpleNamespace
from typing import Optional

from riftbound.ai import coach as C
from riftbound.core.decisions import DecisionPoint

# The champion's fixed iterations a decision on Rust. Measured on 25/11 with
# `Game.search_stats` at budget=0.03 s (the Rust budget promoted as equal to Python's
# 0.4 s, STATO.md 24/11), the champion's search (prior forward + search) on ES and EK, six
# games (seeds 1-6, rules 6427b90+D72-D77, both seats searching): the median iterations
# of a main-turn search is 42 (252 searches; per game 33-61, mean 140, max 786). The
# checkpoint of the champion is not in the build container: the net there was a
# default-architecture PPONet with random weights (the forward costs the same). Re-measure
# on the Mac with the real checkpoint (docs/RUST.md) and change this or pass --iterazioni.
ITERAZIONI_CAMPIONE = 42
_NO_MORE = json.dumps("$NO_MORE")


def giocabile(deck_a, deck_b) -> bool:
    """Whether the Rust engine plays a game between these two lists (the extension is
    there and both are lists of the covered matchups, recognised by their content)."""
    from riftbound.rs import arena_rs, rust_bridge
    return rust_bridge.available() and arena_rs.coperte(deck_a, deck_b)


class RsLoop:
    """What `CoachSession.loop` is on Rust: the record the rewind replays, one (event kind, answer) per
    `ask` of the human seat, in order; and, for the rules the page's helpers read from a loop
    (`_has_effect`, `_unit_death_replacement`...), a GameLoop never started over the current
    state (`vloop`, set where needed)."""

    def __init__(self, record: list):
        self.record = record
        self.vloop = None

    def __getattr__(self, name):
        if name in ("record", "vloop") or self.vloop is None:
            raise AttributeError(name)
        return getattr(self.vloop, name)


class RustGame:
    """One game of a `CoachSession` on the Rust engine (see the module docstring)."""

    def __init__(self, session):
        self.s = session
        self.seed = session._build["seed"]
        # Who starts: the opening's choice (new_game with `apertura`), else a coin flip of the seed
        # (Python draws it off the game's generator).
        self.starter = session._build.get("starter") or random.Random(self.seed).choice(["A", "B"])
        self.record: list = []
        self.n_replay = 0          # answers of the record given back without asking the page
        self.k = 0
        self.objs: dict = {}
        self.chooser_on = False    # the coach's choices are asked (CoachAgent's _CoachChooser)
        self._batch: Optional[dict] = None      # the picks of the choice being logged (_logged_choice)

    # -- the game thread -------------------------------------------------------------

    def play(self, entries: Optional[list]):
        """The game on this thread: from its start, or (`entries`: a rewind) rebuilt and
        replayed from the record up to the coach's decision asked again."""
        s = self.s
        if entries is not None:
            s.gs = None
            s._replaying = True
            C._thread_log().sinks[threading.get_ident()] = deque(maxlen=50)   # the replay's lines: not shown
        self.record = list(entries or [])
        self.k, self.n_replay = 0, len(self.record)
        self.chooser_on, self._batch = False, None
        self._save_group: Optional[frozenset] = None     # the dying group the page was asked about
        self._save_pick: Optional[int] = None            # ... and the unit it saves (its id; None: no one)
        s.loop = RsLoop(self.record)
        g = self._game()
        winner, turns = g.start()
        # The final state (PR 47, Codex): a game can end with no decision after the last event
        # (a point scored at the start of a turn); the page must show where it really ended.
        self._flush()
        self._load({"state_raw": json.loads(g.raw_dump())})
        return SimpleNamespace(winner=winner, turns=turns)

    def _game(self):
        from riftbound.rs import arena_rs, rust_bridge
        s, b = self.s, self.s._build
        g = rust_bridge.build(self.seed, b["deck_a"], b["deck_b"], self.starter.lower(), arena_rs.MAX_TURNS,
                              regole=s.regole, bf_a=b.get("bf_a"), bf_b=b.get("bf_b"))
        opp = "B" if s.side == "A" else "A"
        if b["opponent"] == "campione":
            g.set_search_agent(opp, s.iterazioni or ITERAZIONI_CAMPIONE, self.seed * 2 + (opp == "B"), None,
                               arena_rs.make_probs(b["ppo"]), False)
            g.set_search_win_probe(opp, True)
        else:
            g.set_agent(opp, "simple_trade", self.seed)
        g.set_human_agent(s.side, self.ask, True, self.notify)
        g.set_side_chooser()
        g.trace_on(self.watch)
        return g

    def _load(self, e: dict) -> None:
        """The state of an event as the session's `gs` (the page's views read it)."""
        from riftbound.rs import vista_rs
        if e.get("state_raw") is not None:
            self.s.gs, self.objs = vista_rs.carica(e["state_raw"])

    # -- the coach's seat: what Rust asks --------------------------------------------

    def ask(self, ev: str):
        s = self.s
        e = json.loads(ev)
        k = e["k"]
        self._flush()
        if self.k < self.n_replay:                       # a rewind's replay: the record answers
            kind, answer = self.record[self.k]
            if kind != k:
                raise C._ReplayError(f"atteso {kind}, chiesto {k} ({self.k})")
            self.k += 1
            return answer
        if s._replaying:                                 # the replay is over: the page as it was
            self._load(e)
            s._resume()
        answer = getattr(self, "_" + k)(e)
        self.record.append((k, answer))
        return answer

    # The agent's own preferences: only defaults for the choices that follow (as _Seat does).
    def _decide_optional(self, e: dict) -> bool:
        return True

    def _decide_mode(self, e: dict):
        return None

    def _decide_predict_recycle(self, e: dict) -> bool:
        return False

    def _decide_mulligan(self, e: dict) -> list:
        s = self.s
        self._load(e)
        hand = [c.name for c in s.gs.get_player(e["seat"]).hand]
        if not hand:
            return []
        s.opening = True                   # no turn has started: nothing to log yet
        s.thinking(DecisionPoint.MULLIGAN)
        try:
            return s.ask_mulligan(hand, [])
        finally:
            s.opening = False
            s.view = None                  # the first turn's line comes next

    def _decision(self, e: dict):
        from riftbound.rs import vista_rs
        s, side = self.s, e["seat"]
        point, menu = DecisionPoint(e["point"]), e["menu"]
        n = len(menu)
        s.show_looked()                    # a look no choice followed: held on the board until seen
        if point == DecisionPoint.TURN_ACTION:
            self.chooser_on = False        # CoachAgent._release_coach
        if n <= 1:
            if n and point == DecisionPoint.REACTION:
                self._load(e)
                s.notice_chain()
            return 0 if n else None
        self._load(e)
        s.thinking(point)
        gs = s.gs
        vloop = vista_rs.vista_loop(gs)
        tuples = [tuple(a) for a in e["actions"]]      # the menu's moves, from Rust
        infos = [C.action_info(vloop, side, side, point, t) for t in tuples]
        # Cards only the Golds' Power pays for: offered too, after the engine's moves.
        solo = e.get("gold_only") or []
        solo_infos: list = []
        if solo:
            try:
                got = dict(C.gold_only_plays(vloop, side, point, tuples))
            except Exception:  # noqa: BLE001 — the text falls back to the table as it is
                got = {}
            for g in solo:
                t = tuple(g["action"])
                solo_infos.append(got.get(t) or C.action_info(vloop, side, side, point, t))
        infos += [{**i, "text": i["text"] + " (col Gold)"} for i in solo_infos]
        answer = s.ask_decision(point, side, infos, [], C.decision_context(gs, side, point))
        i = int(answer["action"])
        auto = bool(answer.get("auto"))
        if i < n:
            action, text, ways = tuples[i], infos[i]["text"], (e.get("pay") or [None] * n)[i]
            make = lambda via: i if via is None else {"index": i, "via": via}  # noqa: E731
        else:
            j = i - n
            action, ways = tuple(solo[j]["action"]), solo[j]["ways"]
            text = infos[i]["text"].removesuffix(" (col Gold)")
            make = lambda via: {"solo_gold": j, "via": via or 0}  # noqa: E731
        via, way = None, None
        if ways and not auto:
            card = C._paid_card(vloop, side, action)
            name = getattr(card, "name", None) or text
            via = 0
            shown = list(enumerate(ways))                  # (index in the event's ways, way)
            if C.accelerate_asked(ways):                   # "Pagare ACCELERATE?" first (CoachAgent._coached)
                yes = s.ask_choice("optional:accelerate", side,
                                   [{"text": "Sì", "ref": None}, {"text": "No", "ref": None}], 0, name) == 0
                shown = C.accelerate_ways(ways, yes)
            if len(shown) > 1:                             # "Come paghi?"
                pick = s.ask_choice("payment", side,
                                    [{"text": C.payment_text(w["golds"], [(d, k) for d, k in w["recycled"]]),
                                      "ref": None} for _i, w in shown], 0, name)
                via = shown[pick][0]
            else:
                via = shown[0][0]
            way = ways[via]
            for _ in range(way["golds"]):
                s.event("me", f"Usa Gold: Power {str(way['gold_domain']).title()} per pagare {name}", move=True)
        if action[0] != "PASS":
            s.event("me", text + (" (partita lasciata)" if auto else ""), move=True)
        self.chooser_on = True             # the choices inside the move are the coach's
        return make(via)

    def _choice(self, e: dict) -> int:
        from riftbound.rs import vista_rs
        s, side, kind = self.s, e["seat"], e["kind"]
        default, raw = e["default"], e["options_raw"]
        if not self.chooser_on or len(raw) <= 1:
            return default
        self._load(e)
        gs = s.gs
        options = [vista_rs.valore(o, self.objs) for o in raw]
        source = vista_rs.valore(e["source_raw"], self.objs) if e.get("source_raw") is not None else None
        if kind == "optional:sett_save" and e.get("dying"):
            got = self._sett_save(e, source)
            if got is not None:
                return got
        described = [{"text": C.option_text(gs, side, o), "ref": C.option_ref(gs, side, o)} for o in options]
        # Options the page can't tell apart are one (CoachAgent's _CoachChooser).
        keys = [(d["text"], d["ref"]) for d in described]
        firsts = [i for i, k in enumerate(keys) if k not in keys[:i]]
        if len(firsts) <= 1:
            return default
        shown = firsts.index(keys.index(keys[default])) if 0 <= default < len(keys) else 0
        pick = s.ask_choice(kind, side, [described[i] for i in firsts], shown, getattr(source, "name", None))
        return firsts[pick] if 0 <= pick < len(firsts) else default

    def _sett_save(self, e: dict, source) -> Optional[int]:
        """Sett The Boss's save, asked once for the units dying together (CoachSession.ask_save: only
        the savable ones), then yes for the unit picked and no for the others as the engine asks them
        one by one. None: not a death the page saw (the generic question)."""
        from riftbound.rs import vista_rs
        s = self.s
        dying = e["dying"]
        if not dying.get("group") or not dying.get("now"):
            return None
        s.loop.vloop = vista_rs.vista_loop(s.gs)
        group = {u["id"]: vista_rs.valore(u["unit"], self.objs) for u in dying["group"]["units"]}
        now = vista_rs.valore(dying["now"]["unit"], self.objs)
        ids = frozenset(group)
        if self._save_group != ids:
            self._save_group, self._save_pick = ids, C._UNASKED
        bf = dying["group"]["bf"]
        kept = (s._dying, s._save_pick, s._dying_bf, s._replacing)
        s._dying, s._dying_bf, s._replacing = list(group.values()), None if bf is None else s.gs.battlefields[bf], now
        s._save_pick = C._UNASKED if self._save_pick is C._UNASKED else \
            (None if self._save_pick is None else group.get(self._save_pick))
        try:
            got = s.ask_save(getattr(source, "name", None))
            pick = s._save_pick
        finally:
            s._dying, s._save_pick, s._dying_bf, s._replacing = kept
        if got is None:
            return None
        self._save_pick = next((i for i, u in group.items() if u is pick), None)
        return got

    # -- what happens: the live trace ------------------------------------------------

    def notify(self, ev: str) -> None:
        """The cards the coach looks at on top of their deck (Trifarian Captain's dig, Predict...):
        held for the choice that follows, or alone when there is none (CoachSession._looked)."""
        from riftbound.rs import vista_rs
        if self.s._replaying:
            return
        e = json.loads(ev)
        if e["k"] == "look":
            self.s._looked([vista_rs.valore(c, {}).name for c in e["args"]["cards"]])

    def watch(self, ev: str) -> None:
        """Every event, answer included (trace_on): the opponent's moves keep the page's
        board, events and log current, as the Python `watched` wrappers do."""
        s = self.s
        if s._replaying:
            return
        e = json.loads(ev)
        k, mine = e["k"], e.get("seat") == s.side
        if k in ("decision", "choice"):
            self._tech(e)
        if k != "choice":
            self._flush()
        if k == "decision" and not mine:
            from riftbound.rs import vista_rs
            self._load(e)
            s._opponent_turn()
            action = e.get("action")
            if action and action[0] != "PASS":
                info = C.action_info(vista_rs.vista_loop(s.gs), e["seat"], s.side, DecisionPoint(e["point"]),
                                     tuple(action))
                s.event("opp", info["text"], move=True)
        elif k == "decide_mulligan" and not mine:
            self._load(e)
            hand = [c.name for c in s.gs.get_player(e["seat"]).hand]
            s.opp_mulligan = {"hand": hand, "returned": [hand[i] for i in e["out"]]}
        elif k == "choice":
            self._logged_choice(e, mine)

    # -- the technical log (English; Rust has no text log, this is made from the trace) ----------

    def _tech(self, e: dict) -> None:
        """One line of `s.log` for a decision or a choice of either seat. A line that can't be
        formatted becomes a fallback with the raw kind: it never breaks the game."""
        s = self.s
        try:
            line = self._tech_line(e)
        except Exception as exc:  # noqa: BLE001
            line = f"? {e.get('seat')} {e.get('k')} {e.get('kind') or e.get('point')} (unformatted: {exc!r})"
        try:
            s.log.append(line)
        except Exception:  # noqa: BLE001
            pass

    def _tech_line(self, e: dict) -> str:
        from riftbound.rs import vista_rs
        s, seat = self.s, e.get("seat")
        if e["k"] == "decision":
            turn = (e.get("win") or {}).get("turn", "?")
            menu, i = e.get("menu") or [], e.get("index")
            what = menu[i] if isinstance(i, int) and 0 <= i < len(menu) else " ".join(map(str, e.get("action") or ["?"]))
            return f"T{turn} {seat} decision {str(e.get('point')).upper()}: {what}"
        self._load(e)
        gs, raw, kind = s.gs, e.get("options_raw") or [], e["kind"]
        turn = gs.turn if gs is not None else "?"
        objs = dict(self.objs)
        options = [vista_rs.valore(o, objs) for o in raw]
        source = vista_rs.valore(e["source_raw"], objs) if e.get("source_raw") is not None else None
        src = f" [{source.name}]" if getattr(source, "name", None) else ""
        i = e.get("chosen")
        got = options[i] if isinstance(i, int) and 0 <= i < len(options) else None
        if options and all(isinstance(o, bool) for o in options):
            return f"T{turn} {seat} choice {kind}{src}: {got}"
        texts = [self._en(gs, o) for o in options]
        shown = ", ".join(texts[:12]) + (f", ... (+{len(texts) - 12})" if len(texts) > 12 else "")
        pick = "none" if got is None else texts[i]
        return f"T{turn} {seat} choice {kind}{src}: {pick} of [{shown}]"

    @staticmethod
    def _en(gs, o) -> str:
        """An option in English, by names: a unit with its owner, Might and place."""
        from riftbound.core.combat import UnitInPlay
        if o is C.NO_MORE:
            return "no more"
        from riftbound.core.state import PendingTrigger
        if isinstance(o, PendingTrigger):
            return f"trigger of {o.card.name} ({o.trigger})"
        if isinstance(o, tuple) and o and isinstance(o[-1], UnitInPlay):
            o = o[-1]
        if isinstance(o, UnitInPlay):
            ref = (C._unit_ref(gs, "A", o) or "unit:opp:base").split(":")
            owner = "A" if ref[1] == "me" else "B"
            at = "legend" if ref[0] == "legend" else "base" if ref[2] == "base" else C._bf_name(gs, int(ref[2]))
            return f"{o.card.name} ({owner}, Might {o.might}, {at})"
        i = next((i for i, bf in enumerate(gs.battlefields) if bf is o), None)
        if i is not None:
            return C._bf_name(gs, i)
        if o is None:
            return "Base"
        if o is gs.A or o is gs.B:
            return o.name
        if isinstance(o, tuple):
            return str(getattr(o[0], "name", o[0]))
        return str(getattr(o, "name", o))

    def _logged_choice(self, e: dict, mine: bool) -> None:
        """A public choice, in the log as the Python page does (CoachSession._log_choice: once per
        choice, a "choose up to N" with its picks together): the opponent's; the coach's only when
        the page had nothing to ask. Consecutive picks of one choice (same seat, kind and source,
        each one's options the last one's without its pick) are gathered and logged by `_flush`."""
        from riftbound.rs import vista_rs
        s, raw, kind = self.s, e["options_raw"], e["kind"]
        head = kind.partition(":")[0]
        source = None
        if head == "keep" and raw and e.get("source_raw") is not None:     # public if the dig reveals
            self._load(e)
            source = vista_rs.valore(e["source_raw"], self.objs)
        if not raw or not C.is_public_choice(s._PUBLIC_CHOICES, kind, source) or (mine and len(raw) > 1) or (not mine and head == "discard"):
            self._flush()
            return
        self._load(e)
        options = [vista_rs.valore(o, self.objs) for o in raw]
        keys = [json.dumps(o["root"]["o"], sort_keys=True) for o in raw]
        src = None if e.get("source_raw") is None else json.dumps(e["source_raw"]["root"]["o"], sort_keys=True)
        got, b = options[e["chosen"]], self._batch
        if b is None or b["seat"] != e["seat"] or b["kind"] != kind or b["src"] != src \
                or set(keys) - {_NO_MORE} != b["left"]:
            self._flush()
            b = self._batch = {"seat": e["seat"], "kind": kind, "src": src, "n": len(options),
                               "picks": [], "many": False, "left": None}
        b["gs"], b["objs"], b["source_raw"] = s.gs, self.objs, e.get("source_raw")   # the last event's state
        if got is C.NO_MORE:                  # "up to N": the picks are over
            b["many"] = True
            self._flush()
            return
        b["picks"].append(raw[e["chosen"]])
        b["many"] = b["many"] or len(b["picks"]) > 1
        b["left"] = set(keys) - {_NO_MORE, keys[e["chosen"]]}

    def _flush(self) -> None:
        """Log the choice gathered by `_logged_choice`."""
        b, self._batch = self._batch, None
        if b is None:
            return
        s, saved = self.s, self.s.gs
        if not b["picks"] and not b["many"]:
            return
        from riftbound.rs import vista_rs
        picks = [vista_rs.valore(r, b["objs"]) for r in b["picks"]]     # the last state's objects
        source = vista_rs.valore(b["source_raw"], b["objs"]) if b["source_raw"] is not None else None
        s.gs = b["gs"]
        try:
            s._log_choice(b["kind"], b["seat"], b["n"], picks if b["many"] else picks[0], source)
        finally:
            s.gs = saved
