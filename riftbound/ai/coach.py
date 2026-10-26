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
`answer()`, `new_game()`, `report()` and `abandon()`.
"""

from __future__ import annotations

import json
import queue
import random
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

from riftbound.ai.encoding import ACTION_DIM, action_to_index, encode_observation, legal_mask
from riftbound.ai.net_mcts import _PASS, NetGuidedMCTSAgent, _ForcedChoice, _split_key
from riftbound.core.decisions import DecisionPoint, Observation, describe_option
from riftbound.core.legality import legal_actions
from riftbound.registry.cards_registry import CARD_REGISTRY


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


class _CoachChooser:
    """While a move the coach picked resolves: its player's choices (any kind
    with more than one option) are asked to the coach."""

    def __init__(self, me: str, session: "CoachSession", loop, previous):
        self.me, self.session, self.loop, self.previous = me, session, loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if side == self.me and len(options) > 1:
            labels = [describe_option(loop, side, o) for o in options]
            return self.session.ask_choice(kind, side, labels, default, getattr(source, "name", None))
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

    def _release_coach(self) -> None:
        chooser = getattr(self.loop, "chooser", None)
        if isinstance(chooser, _CoachChooser) and chooser.me == self.player.name:
            chooser.release()

    def _coached(self, point: DecisionPoint, cards_played: int = 0, bf_idx: Optional[int] = None):
        self._ensure_rng()
        if point == DecisionPoint.TURN_ACTION:
            self._release_forced()
            self._release_coach()
        side = self.player.name
        legal = legal_actions(self.loop, point, side)
        if len(legal) <= 1:
            return legal[0].to_engine() if legal else _PASS
        self.session.thinking(point)
        root = self.search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
        labels = {a.to_engine(): a.label for a in legal}
        total = sum(c.N for c in root.children.values()) or 1
        ranked = sorted(root.children.items(), key=lambda kv: -kv[1].N)[:3]
        suggestions = []
        for key, child in ranked:
            action, force = _split_key(key)
            label = labels.get(action, str(action))
            if force is not None and key in root.labels:
                label += f" → {root.labels[key]}"
            q = child.W / child.N if child.N else 0.0
            suggestions.append({"key": key, "label": label, "share": child.N / total,
                                "win": (q + 1) / 2})
        answer = self.session.ask_decision(point, side, [labels[a.to_engine()] for a in legal],
                                           suggestions)
        if "suggestion" in answer:
            action, force = _split_key(suggestions[int(answer["suggestion"])]["key"])
            if force is not None:
                self.loop.chooser = _ForcedChoice(side, force, self.loop, self.loop.chooser)
            corrected = int(answer["suggestion"]) != 0
        else:
            action = legal[int(answer["action"])].to_engine()
            self.loop.chooser = _CoachChooser(side, self.session, self.loop, self.loop.chooser)
            best = _split_key(suggestions[0]["key"])[0] if suggestions else None
            corrected = action != best
        self.session.record(self.gs, side, legal, action, corrected)
        return action


class CoachSession:
    """One coached game at a time, on its own thread, for the web page."""

    def __init__(self, net_path: Path, out_dir: Path, iterations: int = 100):
        self.net_path = Path(net_path)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.iterations = iterations
        self._lock = threading.Lock()
        self._answers: "queue.Queue" = queue.Queue()
        self._reset()

    def _reset(self) -> None:
        self.status = "idle"            # idle | thinking | waiting | over
        self.pending: Optional[dict] = None
        self.examples: list = []
        self.log: deque = deque(maxlen=400)
        self.result: Optional[dict] = None
        self.info: dict = {}
        self.view: Optional[dict] = None    # the board, snapshot on the game thread
        self.gs = None
        self.side: Optional[str] = None
        self._abandoned = False
        self._thread: Optional[threading.Thread] = None

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
        # The board the page shows follows the opponent's moves too.
        for name in ("decide_action", "decide_showdown_action", "decide_reaction"):
            inner = getattr(them.agent, name)

            def snapped(*a, _inner=inner, **k):
                self._snapshot()
                return _inner(*a, **k)
            setattr(them.agent, name, snapped)
        self.gs, self.side = gs, seat
        self.info = {"seed": seed, "seat": seat, "deck_mine": Path(deck_mine).stem,
                     "deck_opp": Path(deck_opp).stem, "opponent": opponent,
                     "net": str(self.net_path), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.status = "thinking"
        self._thread = threading.Thread(target=self._run, name="rbsim-coach", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        from riftbound.core.loop import GameLoop
        log = _thread_log()
        log.sinks[threading.get_ident()] = self.log
        try:
            result = GameLoop(self.gs, verbose=True).start()
            self.result = {"winner": result.winner, "turns": result.turns,
                           "you_won": result.winner == self.side}
            if not self._abandoned:
                self._save(result.winner)
        except Exception as exc:  # noqa: BLE001
            self.result = {"error": repr(exc)}
        finally:
            self._snapshot()
            log.sinks.pop(threading.get_ident(), None)
            self.pending = None
            self.status = "over"

    def _snapshot(self) -> None:
        """The coach's view of the board, taken on the game thread (the page
        never reads the live game)."""
        if self.gs is not None and self.side is not None:
            self.view = Observation.from_state(self.gs, self.side).to_dict()

    def thinking(self, point: DecisionPoint) -> None:
        self._snapshot()
        self.status = "thinking"

    def _wait(self, request: dict) -> dict:
        if self._abandoned:
            return {}
        self._snapshot()
        with self._lock:
            self.pending = request
            self.status = "waiting"
        answer = self._answers.get()
        with self._lock:
            self.pending = None
            self.status = "thinking"
        return answer

    def ask_decision(self, point: DecisionPoint, side: str, actions: list, suggestions: list) -> dict:
        answer = self._wait({"type": "decision", "point": point.value, "actions": actions,
                             "suggestions": [{k: v for k, v in s.items() if k != "key"}
                                             for s in suggestions]})
        if not answer:                     # abandoned: the net's move
            return {"suggestion": 0} if suggestions else {"action": 0}
        return answer

    def ask_choice(self, kind: str, side: str, options: list, default: int,
                   source: Optional[str]) -> int:
        answer = self._wait({"type": "choice", "kind": kind, "options": options,
                             "default": default, "source": source})
        return int(answer.get("option", default)) if answer else default

    # -- the page's side ---------------------------------------------------------

    def answer(self, payload: dict) -> None:
        if self.pending is None:
            raise RuntimeError("nothing is waiting for an answer")
        self._answers.put(payload)

    def abandon(self) -> None:
        """Let the net finish the game on its own; nothing is saved."""
        self._abandoned = True
        if self.pending is not None:
            self._answers.put({})

    def _log_lines(self) -> list:
        for _ in range(5):                  # the game thread may be appending
            try:
                return list(self.log)
            except RuntimeError:
                continue
        return []

    def state(self) -> dict:
        obs = self.view
        return {"status": self.status, "info": self.info, "pending": self.pending,
                "observation": obs, "log": self._log_lines()[-60:], "result": self.result,
                "decisions": len(self.examples),
                "corrections": sum(1 for e in self.examples if e["corrected"]),
                "cards": _card_texts(obs)}

    def report(self, note: str) -> Path:
        path = self.out_dir / "reports.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note,
                                 **self.state(), "log": self._log_lines()}, default=str) + "\n")
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


def _card_texts(obs: Optional[dict]) -> dict:
    """Printed text of the cards on view, for the page's tooltips."""
    if not obs:
        return {}
    names: set = set(obs.get("my_hand") or [])
    names |= set(obs.get("my_trash") or []) | set(obs.get("opp_trash") or [])
    names |= set(obs.get("my_base_gear") or []) | set(obs.get("opp_base_gear") or [])
    for key in ("my_legend", "opp_legend", "my_champion", "opp_champion"):
        if obs.get(key):
            names.add(obs[key])
    units = list(obs.get("my_base_units") or []) + list(obs.get("opp_base_units") or [])
    for bf in obs.get("battlefields") or []:
        units += list(bf.get("A") or []) + list(bf.get("B") or [])
        if bf.get("named"):
            names.add(bf["named"])
        names |= set(bf.get("gear_A") or []) | set(bf.get("gear_B") or [])
    for u in units:
        names.add(u["name"])
        names |= set(u.get("gear") or [])
    out = {}
    for n in names:
        spec = CARD_REGISTRY.get(n)
        if spec is not None:
            raw = spec.raw or {}
            out[n] = {"text": raw.get("effect") or "", "type": raw.get("category") or "",
                      "cost": raw.get("cost_energy"), "might": raw.get("might")}
    return out
