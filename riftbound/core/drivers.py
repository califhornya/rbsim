"""Drivers — how a game is run.

``SyncDriver`` runs a prepared game straight to completion with its inline agents.
It is byte-for-byte the historical behaviour (it just calls ``GameLoop.start``),
so it is what the CLI / batch sims / the golden fixture use.

``SessionDriver`` makes the engine *pausable* for the web layer without touching
the engine's control flow. Instead of rewriting the deeply-nested phase methods
into a generator (a generator frame can't be cloned, so it wouldn't help search
anyway — search uses GameState.clone + legal_actions), it runs the ordinary game
loop on a background thread and routes the human seat's decisions through a
:class:`RemoteAgent`. The agent, called on the game thread, snapshots a
:class:`DecisionRequest` (observation + legal actions), hands it to the main
thread over a queue, and blocks until an action is submitted back.

The DecisionRequest carries an immutable Observation snapshot taken on the game
thread, so the main/web thread never reads live ``GameState`` — there is no data
race, and the observation the web sees is exactly the state at the decision point.

    driver = SessionDriver(gs)
    driver.make_remote("A")          # A is the human; B keeps its heuristic agent
    driver.start()
    while not driver.is_over():
        st = driver.state()          # {observation, pending_decision, legal_actions}
        driver.submit(chosen_action) # a GameAction, raw tuple, or [] for mulligan
    result = driver.result
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Optional

from .decisions import DecisionPoint, DecisionRequest, GameAction, Observation
from .legality import legal_actions
from .loop import GameLoop, Result

_PASS: tuple = ("PASS", None, None)


def _to_action_tuple(resp: Any) -> tuple:
    """Coerce a submitted response into the raw action tuple the engine expects."""
    if resp is None:
        return _PASS
    if isinstance(resp, GameAction):
        return resp.to_engine()
    if isinstance(resp, dict):
        return GameAction(**resp).to_engine()
    if isinstance(resp, tuple):
        return resp
    raise TypeError(f"cannot interpret submitted action: {resp!r}")


def _result_dict(result: Optional[Result]) -> Optional[dict]:
    if result is None:
        return None
    return {
        "winner": result.winner,
        "turns": result.turns,
        "units_played": result.units_played,
        "spells_cast": result.spells_cast,
    }


class SyncDriver:
    """Run a prepared game to completion, inline. Identical to the historical
    ``GameLoop(gs).start()`` path (the golden fixture pins this behaviour)."""

    def __init__(self, gs, *, recorder=None, verbose: bool = False):
        self.gs = gs
        self.recorder = recorder
        self.verbose = verbose

    def run(self) -> Result:
        return GameLoop(self.gs, recorder=self.recorder, verbose=self.verbose).start()


class RemoteAgent:
    """Agent whose choices come from outside the engine thread. Implements the
    full Agent decision surface; for each decision it posts a DecisionRequest to
    an out-queue and blocks on the in-queue for the response."""

    name = "remote"

    def __init__(self, player, out_q: "queue.Queue", in_q: "queue.Queue"):
        self.player = player
        self._out = out_q
        self._in = in_q
        # GameLoop.__init__ injects these before any decision is asked:
        self.gs = None
        self.loop = None

    def _ask(self, point: DecisionPoint, legal) -> Any:
        side = self.player.name
        request = DecisionRequest(
            point=point,
            player=side,
            observation=Observation.from_state(self.gs, side),
            legal_actions=tuple(legal),
        )
        self._out.put(request)
        return self._in.get()

    def decide_action(self, opponent, cards_played: int = 0) -> tuple:
        legal = legal_actions(self.loop, DecisionPoint.TURN_ACTION, self.player.name)
        return _to_action_tuple(self._ask(DecisionPoint.TURN_ACTION, legal))

    def decide_mulligan(self) -> list:
        resp = self._ask(DecisionPoint.MULLIGAN, [])
        return list(resp) if resp else []

    def decide_showdown_action(self, opponent, bf_idx: int) -> tuple:
        legal = legal_actions(self.loop, DecisionPoint.SHOWDOWN_ACTION, self.player.name)
        return _to_action_tuple(self._ask(DecisionPoint.SHOWDOWN_ACTION, legal))

    def decide_reaction(self, opponent, chain) -> tuple:
        legal = legal_actions(self.loop, DecisionPoint.REACTION, self.player.name)
        return _to_action_tuple(self._ask(DecisionPoint.REACTION, legal))


class SessionDriver:
    """Holds a paused game for the web layer: it runs on a background thread and
    surfaces one :class:`DecisionRequest` at a time for the remote seat(s)."""

    _DONE = object()

    def __init__(self, gs, *, verbose: bool = False):
        self.gs = gs
        self.verbose = verbose
        self._out: "queue.Queue" = queue.Queue()
        self._in: "queue.Queue" = queue.Queue()
        self._current: Optional[DecisionRequest] = None
        self._done = False
        self.result: Optional[Result] = None
        self._thread: Optional[threading.Thread] = None
        # Wire the queues into any RemoteAgent already installed on the game.
        for p in (gs.A, gs.B):
            if isinstance(p.agent, RemoteAgent):
                p.agent._out = self._out
                p.agent._in = self._in

    def make_remote(self, side: str) -> RemoteAgent:
        """Install a RemoteAgent on ``side`` (the human seat). Call before start()."""
        p = self.gs.get_player(side)
        agent = RemoteAgent(p, self._out, self._in)
        p.agent = agent
        return agent

    def start(self) -> "SessionDriver":
        self._thread = threading.Thread(target=self._run, name="rbsim-session", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self.result = GameLoop(self.gs, verbose=self.verbose).start()
        finally:
            # Signal completion even if start() raised, so waiters don't block.
            self._out.put(self._DONE)

    def _pump(self) -> None:
        """Advance ``_current`` to the next pending decision (or mark done). Blocks
        until the game thread needs a remote decision or the game ends."""
        if self._current is not None or self._done:
            return
        item = self._out.get()
        if item is self._DONE:
            self._done = True
            self._current = None
        else:
            self._current = item

    def pending(self) -> Optional[DecisionRequest]:
        """The current DecisionRequest, or None if the game is over."""
        self._pump()
        return self._current

    def state(self) -> dict:
        """JSON-able snapshot for the web: observation + pending decision + legal
        actions, or the final result once the game is over."""
        self._pump()
        if self._done:
            return {"done": True, "result": _result_dict(self.result), "pending_decision": None}
        req = self._current
        assert req is not None
        return {
            "done": False,
            "pending_decision": req.point.value,
            "player": req.player,
            "observation": req.observation.to_dict(),
            "legal_actions": [a.to_dict() for a in req.legal_actions],
        }

    def submit(self, action: Any) -> None:
        """Resume the paused game with the chosen action (GameAction / raw tuple /
        list of mulligan indices)."""
        self._pump()
        if self._done:
            raise RuntimeError("game is already over")
        if self._current is None:
            raise RuntimeError("no pending decision to submit to")
        self._current = None
        self._in.put(action)

    def is_over(self) -> bool:
        self._pump()
        return self._done

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
