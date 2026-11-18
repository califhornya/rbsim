"""Scenari per i giudizi dell'utente (docs/bot/GIUDIZI.md).

Uno scenario è una posizione costruita giocando mosse vere nel motore dal primo
turno, non scritta a mano: i mazzi sono messi in un ordine scelto (le mani e le
rune di partenza che lo scenario descrive), poi ognuno dei due giocatori fa le
mosse del suo copione, turno per turno. Così la posizione è legale per
costruzione (non si controlla un campo senza averlo conquistato) e
`tests/test_scenari.py` verifica che sia quella che il testo descrive.

Al turno dello scenario il posto dell'utente smette di seguire il copione e
chiede a lui, sulla pagina (`scripts/scenari.py`), mossa per mossa, fino alla
fine di quel turno; l'avversario passa. Il coach (`riftbound/ai/coach.py`) non
cambia: qui se ne riusano i pezzi (la vista del tavolo, le domande).

Definizioni in `docs/bot/scenari.json`. Ogni scenario:
  id, title, question          testo mostrato all'utente
  decks {"A","B"}              nomi dei file in riftbound/data/decks
  battlefields {"A","B"}       il campo di ciascuno (BF0 è quello di A)
  first                        chi comincia ("A" / "B")
  human                        il posto dell'utente
  seed                         l'ordine del resto dei mazzi
  swaps {"A","B"}              (facoltativo) cambi di sideboard, [esce, entra]
  hands {"A","B"}              le carte in ordine di pesca: le 4 iniziali, poi
                               una per pescata (in cima al mazzo)
  runes {"A","B"}              i domini delle rune in ordine di canalizzazione
  script                       [{"turn", "seat", "main"/"showdown"/"reaction":
                               [etichette di mosse legali]}]: finita la lista,
                               quel giocatore passa
  turn                         il turno dello scenario (gs.turn)
  human_from                   "any" (default): l'utente decide dalla prima
                               decisione dopo il copione; "main": dalla prima
                               del suo Main Phase (le altre intanto passano)
  legend_used                  (facoltativo) true: quando l'utente prende il
                               posto, le abilità "una volta per turno" della
                               sua legend risultano già usate in quel turno
                               (la stessa posizione, senza il trigger)
  expect                       com'è la posizione alla prima decisione
                               dell'utente (controllato dai test)
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions

ROOT = Path(__file__).resolve().parents[2]
SCENARI_PATH = ROOT / "docs" / "bot" / "scenari.json"
DECK_DIR = ROOT / "riftbound" / "data" / "decks"
RISPOSTE_PATH = ROOT / "docs" / "bot" / "risposte_scenari.jsonl"

_PASS = ("PASS", None, None)
_POINTS = {DecisionPoint.TURN_ACTION: "main", DecisionPoint.SHOWDOWN_ACTION: "showdown",
           DecisionPoint.REACTION: "reaction"}


class ScenarioOver(Exception):
    """The scenario's turn is over: the game stops here."""


class ScenarioError(Exception):
    """A scenario can't be built as written (a move not legal, a card not in the deck)."""


def load_scenari(path: Path = SCENARI_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["scenari"]


def get_scenario(sid: str, path: Path = SCENARI_PATH) -> dict:
    for sc in load_scenari(path):
        if sc["id"] == sid:
            return sc
    raise ScenarioError(f"scenario {sid!r} not found")


# -- building -------------------------------------------------------------------------

def _stack_deck(player, names: list, sid: str) -> None:
    """`names` on top of the Main Deck, the first to be drawn first."""
    cards = list(player.deck.cards)
    picked = []
    for name in names:
        i = next((k for k, c in enumerate(cards) if c.name == name), None)
        if i is None:
            raise ScenarioError(f"{sid}: no {name!r} left in {player.name}'s deck")
        picked.append(cards.pop(i))
    player.deck.cards = cards + list(reversed(picked))     # draw() pops the end


def _swap(player, out_name: str, in_name: str, sid: str) -> None:
    """A sideboard swap: one `out_name` of the Main Deck becomes `in_name`."""
    from riftbound.registry.cards_registry import CARD_REGISTRY
    i = next((k for k, c in enumerate(player.deck.cards) if c.name == out_name), None)
    if i is None or in_name not in CARD_REGISTRY:
        raise ScenarioError(f"{sid}: can't swap {out_name!r} for {in_name!r} in {player.name}'s deck")
    player.deck.cards[i] = CARD_REGISTRY[in_name].instantiate()


def _use_legend(gs, side: str) -> None:
    """`side`'s legend: its "once each turn" abilities used this turn."""
    legend = gs.legend_A if side == "A" else gs.legend_B
    for i, e in enumerate(getattr(legend, "effects", None) or []):
        if e.get("once_per_turn"):
            gs.once_per_turn_used[(legend, i)] = gs.turn


def _stack_runes(player, domains: list, sid: str) -> None:
    runes = list(player.rune_deck.runes)
    picked = []
    for d in domains:
        i = next((k for k, r in enumerate(runes) if r.domain == Domain[d.upper()]), None)
        if i is None:
            raise ScenarioError(f"{sid}: no {d} rune left for {player.name}")
        picked.append(runes.pop(i))
    player.rune_deck.runes = picked + runes                # draw() pops the front


def build_state(sc: dict):
    """The game at its start: decks, battlefields, first player, stacked hands
    and runes. No agents yet."""
    from riftbound.core.game_factory import build_game
    gs = build_game(game_seed=int(sc.get("seed", 1)),
                    deck_a_path=DECK_DIR / f"{sc['decks']['A']}.json",
                    deck_b_path=DECK_DIR / f"{sc['decks']['B']}.json",
                    ai_a=None, ai_b=None, first_player=sc["first"],
                    bf_a=sc["battlefields"]["A"], bf_b=sc["battlefields"]["B"])
    for side in ("A", "B"):
        p = gs.get_player(side)
        for out_name, in_name in (sc.get("swaps") or {}).get(side, []):
            _swap(p, out_name, in_name, sc["id"])
        _stack_deck(p, sc["hands"][side], sc["id"])
        _stack_runes(p, sc["runes"][side], sc["id"])
    for side in ("A", "B"):
        bf = gs.battlefields[0 if side == "A" else 1]
        if bf.card is None or bf.card.name != sc["battlefields"][side]:
            raise ScenarioError(f"{sc['id']}: {side}'s battlefield is not {sc['battlefields'][side]}")
    return gs


def _plan(sc: dict) -> dict:
    """(turn, seat, point name) -> labels, in order; (turn, seat, "choices") ->
    [kind prefix, option prefix] for the choices made inside the script's moves
    (the others take the engine's default)."""
    plan: dict = {}
    for step in sc.get("script", []):
        for point in ("main", "showdown", "reaction", "choices"):
            if point in step:
                plan.setdefault((int(step["turn"]), step["seat"], point), []).extend(step[point])
    return plan


def _option_name(o) -> str:
    if isinstance(o, tuple) and len(o) == 2:
        o = o[1]
    card = getattr(o, "card", None)
    return str(getattr(card, "name", None) or getattr(o, "name", None) or o)


class ScriptedChooser:
    """The script's choices inside its moves: the next [kind, option] of the
    deciding seat's list for this turn whose kind matches; else the default."""

    def __init__(self, plan: dict, sid: str):
        self.plan, self.sid = plan, sid

    def __call__(self, loop, kind, side, options, default, source):
        todo = self.plan.get((loop.gs.turn, side, "choices"), [])
        if todo and kind.startswith(todo[0][0]):
            want = todo.pop(0)[1]
            names = [_option_name(o) for o in options]
            hit = [i for i, n in enumerate(names) if n.startswith(want)]
            if not hit:
                raise ScenarioError(f"{self.sid}: turn {loop.gs.turn}, {side}'s {kind}: "
                                    f"no {want!r} in {names}")
            return hit[0]
        return None


def _pick(loop, point: DecisionPoint, side: str, label: str, sid: str):
    legal = legal_actions(loop, point, side)
    if label == "PASS":
        return _PASS
    exact = [g for g in legal if g.label == label]
    pref = [g for g in legal if g.label.startswith(label)]
    hit = exact or (pref if len(pref) == 1 else [])
    if not hit:
        raise ScenarioError(f"{sid}: turn {loop.gs.turn}, {side} at {point.value}: "
                            f"{label!r} is not one legal move: {[g.label for g in legal]}")
    return hit[0].to_engine()


class ScriptedSeat:
    """A seat that plays its script; on the scenario's turn the human's seat
    calls `human(agent, point, bf_idx)` instead, until that turn is over."""

    def __init__(self, player, sc: dict, plan: dict, human: Callable | None = None,
                 on_move: Callable | None = None):
        self.player, self.sc, self.plan = player, sc, plan
        self.human, self.on_move = human, on_move
        self.loop = self.gs = None
        self.started = False        # the user has the seat (until the turn ends)

    def _next(self, point: DecisionPoint, bf_idx: int | None = None):
        gs, side = self.gs, self.player.name
        turn = int(self.sc["turn"])
        if gs.turn > turn:
            raise ScenarioOver()
        todo = self.plan.get((gs.turn, side, _POINTS[point]), [])
        if todo:
            label = todo.pop(0)
            action = _pick(self.loop, point, side, label, self.sc["id"])
            if action != _PASS and self.on_move is not None:
                self.on_move(self, point, action)
            return action
        # The script's moves of this turn done, the user takes over: at once or
        # (`human_from` "main") at the next decision of the Main Phase.
        scripted = any(self.plan.get((turn, side, p)) for p in ("main", "showdown", "reaction"))
        now = self.started or self.sc.get("human_from", "any") != "main" \
            or point == DecisionPoint.TURN_ACTION
        if self.human is not None and gs.turn == turn and not scripted and now:
            if not self.started and self.sc.get("legend_used"):
                _use_legend(gs, side)
            self.started = True
            return self.human(self, point, bf_idx)
        return _PASS

    def decide_action(self, opponent, cards_played: int = 0):
        return self._next(DecisionPoint.TURN_ACTION)

    def decide_showdown_action(self, opponent, bf_idx: int):
        return self._next(DecisionPoint.SHOWDOWN_ACTION, bf_idx)

    def decide_reaction(self, opponent, chain):
        return self._next(DecisionPoint.REACTION)

    def decide_mulligan(self) -> list:
        return []


# -- what the position is ---------------------------------------------------------------

def stop_after_turn(loop, turn: int) -> None:
    """The game stops as the turn after `turn` would begin (before its
    Beginning Phase scores anything): the scenario's turn is over."""
    inner = loop._begin_turn

    def begin():
        if loop.gs.turn > turn:
            raise ScenarioOver()
        return inner()
    loop._begin_turn = begin


def position(gs, side: str) -> dict:
    """The facts a scenario's text states, from `side`'s seat: score, turn, hand,
    units where they are (name and Might), own face-down cards, runes, XP."""
    other = gs.other(side)

    def units(us):
        return sorted(f"{u.card.name} ({u.might})" + ("" if u.ready else " esausta") for u in us)

    def where(s):
        p = gs.get_player(s)
        out = {"base": units(p.base_units)}
        for i, bf in enumerate(gs.battlefields):
            out[bf.card.name] = units(bf._units_for(s))
        return out

    me, them = gs.get_player(side), gs.get_player(other)
    pts = (gs.points_A, gs.points_B) if side == "A" else (gs.points_B, gs.points_A)
    return {
        "turn": gs.turn, "active": "me" if gs.active == side else "opp",
        "score": list(pts),
        "hand": sorted(c.name for c in me.hand),
        "opp_hand": len(them.hand),
        "me": where(side), "opp": where(other),
        "my_facedown": {bf.card.name: [f.card.name for f in bf.facedowns if f.owner == side]
                        for bf in gs.battlefields if any(f.owner == side for f in bf.facedowns)},
        "opp_facedown": sum(1 for bf in gs.battlefields for f in bf.facedowns if f.owner == other),
        "controls": {bf.card.name: ("me" if bf.controller() == side else "opp" if bf.controller() == other
                                    else None) for bf in gs.battlefields},
        "runes": me.total_runes_in_play(), "opp_runes": them.total_runes_in_play(),
        "energy": me.energy, "power": {d.name: n for d, n in me.power_pool.items() if n},
        "xp": gs.get_xp(side), "opp_xp": gs.get_xp(other),
        "gear": sorted(g.name for g in me.base_gear),
    }


class _Reached(Exception):
    def __init__(self, pos: dict, point: DecisionPoint):
        super().__init__("reached")
        self.pos, self.point = pos, point


def reach(sc: dict) -> tuple[dict, DecisionPoint]:
    """Play the scenario up to the human's first decision: its position and
    the kind of decision (for the tests, no page)."""
    from riftbound.core.loop import GameLoop
    gs = build_state(sc)
    plan = _plan(sc)

    def probe(agent, point, bf_idx):
        raise _Reached(position(agent.gs, agent.player.name), point)
    for side in ("A", "B"):
        p = gs.get_player(side)
        p.agent = ScriptedSeat(p, sc, plan, human=probe if side == sc["human"] else None)
    loop = GameLoop(gs)
    loop.chooser = ScriptedChooser(plan, sc["id"])
    try:
        loop.start()
    except _Reached as r:
        return r.pos, r.point
    except ScenarioOver:
        pass
    raise ScenarioError(f"{sc['id']}: the human never got a decision on turn {sc['turn']}")


# -- the page's session -------------------------------------------------------------------

def _session_class():
    """ScenarioSession, built on the coach's CoachSession without changing it
    (imported here: the coach pulls in the net's modules)."""
    from riftbound.ai.coach import (
        CoachAgent,
        CoachSession,
        _CoachChooser,
        _thread_log,
        action_info,
        question,
    )

    class ScenarioSession(CoachSession):
        """One scenario at a time: scripted up to its turn, then the user plays
        that turn on the page; the moves and the user's reasons are saved."""

        def __init__(self, out_dir: Path, answers: Path = RISPOSTE_PATH):
            super().__init__(Path(""), out_dir, opponent_pause=0.0)
            self.answers_path = Path(answers)

        def _reset(self) -> None:
            super()._reset()
            self.scenario: dict | None = None
            self.moves: list = []
            self.after: list = []      # what happened after the first decision
            self.stop_on_opp_chain = False

        def event(self, who: str, text: str, move: bool = False) -> None:
            super().event(who, text, move)
            if getattr(self, "moves", None) and not move:
                self.after.append({"turn": self.gs.turn if self.gs is not None else 0,
                                   "who": who, "text": text})

        def new_scenario(self, sid: str) -> None:
            from riftbound.core.loop import (
                GameLoop,  # noqa: F401  (fail early if broken)
            )
            sc = get_scenario(sid)
            if self._thread is not None and self._thread.is_alive():
                self.abandon()
                self._thread.join(timeout=30)
            self._reset()
            gs = build_state(sc)
            plan = self._plan = _plan(sc)
            human = sc["human"]
            for side in ("A", "B"):
                p = gs.get_player(side)
                p.agent = ScriptedSeat(p, sc, plan, human=self._decide if side == human else None,
                                       on_move=self._scripted)
            self.gs, self.side, self.scenario = gs, human, sc
            self.info = {"scenario": sc["id"], "seat": human, "deck_mine": sc["decks"][human],
                         "deck_opp": sc["decks"][gs.other(human)], "opponent": "copione",
                         "started": time.strftime("%Y-%m-%d %H:%M:%S")}
            self.status, self.activity = "thinking", "Sto preparando lo scenario…"
            self._thread = threading.Thread(target=self._run, name="rbsim-scenario", daemon=True)
            self._thread.start()

        def _run(self) -> None:
            from riftbound.core.loop import GameLoop
            log = _thread_log()
            log.sinks[threading.get_ident()] = self.log
            try:
                self.loop = GameLoop(self.gs, verbose=True)
                self.loop.chooser = ScriptedChooser(self._plan, self.scenario["id"])
                stop_after_turn(self.loop, int(self.scenario["turn"]))
                result = self.loop.start()
                self.result = {"winner": result.winner, "turns": result.turns,
                               "you_won": result.winner == self.side}
            except ScenarioOver:
                self.result = {"scenario_over": True}
            except Exception as exc:  # noqa: BLE001
                self.result = {"error": repr(exc)}
            finally:
                self._snapshot()
                log.sinks.pop(threading.get_ident(), None)
                self.pending = None
                self.status = "over"

        def _scripted(self, agent, point, action) -> None:
            """A move of the script, in the log as the game's history."""
            side = agent.player.name
            text = action_info(agent.loop, side, self.side, point, action)["text"]
            self.event("me" if side == self.side else "opp", f"(copione) {text}", move=True)

        def _decide(self, agent, point, bf_idx):
            """The user decides, as in the coach but with no net's advice."""
            loop, side = agent.loop, agent.player.name
            chooser = getattr(loop, "chooser", None)
            if point == DecisionPoint.TURN_ACTION and isinstance(chooser, _CoachChooser):
                chooser.release()
            legal = legal_actions(loop, point, side)
            if len(legal) <= 1:
                return legal[0].to_engine() if legal else _PASS
            tuples = [g.to_engine() for g in legal]
            infos = [action_info(loop, side, side, point, t) for t in tuples]
            context = CoachAgent._context(agent, point, bf_idx)
            answer = self.ask_decision(point, side, infos, [], context)
            if not answer:                     # stopped from the page
                raise ScenarioOver()
            i = int(answer["action"])
            loop.chooser = _CoachChooser(side, self, loop, loop.chooser)
            # The options and the hand as they were: what the move was chosen
            # against, and (next move) what a draw brought.
            self.moves.append({"turn": self.gs.turn, "point": point.value, "move": infos[i]["text"],
                               "options": [x["text"] for x in infos],
                               "hand": [c.name for c in agent.player.hand]})
            if tuples[i] != _PASS:
                self.event("me", infos[i]["text"], move=True)
            return tuples[i]

        def ask_choice(self, kind, side, options, default, source) -> int:
            pick = super().ask_choice(kind, side, options, default, source)
            if 0 <= pick < len(options):
                self.moves.append({"choice": f"{source + ': ' if source else ''}{question(kind)}",
                                   "pick": options[pick]["text"], "kind": kind})
            return pick

        def _save(self, winner: str):          # nothing for training here
            return None

        def record(self, *a, **k) -> None:
            return None

        def save_answer(self, note: str, alternative: str = "", change_if: str = "") -> Path:
            """One line of risposte_scenari.jsonl. The first move is the decision
            judged (with the options it was chosen from); `note` is why,
            `alternative` the move considered and discarded, `change_if` what
            would change the choice. What happened after the first decision (a
            draw, the board) is `outcome`, kept apart: the decision is judged on
            what was known when it was made."""
            if self.scenario is None:
                raise RuntimeError("nessuno scenario aperto")
            hand = [c.name for c in self.gs.get_player(self.side).hand] if self.gs is not None else []
            self.answers_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.answers_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                     "scenario": self.scenario["id"], "moves": self.moves,
                                     "note": note, "alternative": alternative,
                                     "change_if": change_if,
                                     "outcome": {"events": self.after, "hand_at_end": hand}},
                                    ensure_ascii=False) + "\n")
            self.event("sys", "Risposta salvata")
            return self.answers_path

        def state(self) -> dict:
            s = super().state()
            s["scenario"] = None if self.scenario is None else {
                k: self.scenario[k] for k in ("id", "title", "question")}
            s["scenari"] = [{k: x[k] for k in ("id", "title", "question")} for x in load_scenari()]
            s["moves"] = list(self.moves)
            return s

    return ScenarioSession


def ScenarioSession(out_dir: Path, answers: Path = RISPOSTE_PATH):
    return _session_class()(out_dir, answers)


__all__ = ["ScenarioError", "ScenarioOver", "ScenarioSession", "ScriptedSeat", "build_state",
           "get_scenario", "load_scenari", "position", "reach"]
