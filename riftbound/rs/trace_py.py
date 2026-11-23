"""Traccia di una partita del motore Python, per il confronto con Rust
(porting, F1). Avvolge, senza toccare il motore:
- gli agenti dei due posti (decide_action / reaction / showdown / mulligan /
  optional / mode / predict_recycle): chi decide, la finestra (fase, catena,
  showdown, focus, movimento in sospeso), il menu legale ordinato (etichette),
  l'osservazione del posto (hash del vettore codificato), l'azione scelta e
  il suo indice, l'hash dello stato canonico;
- il chooser del loop, se c'è (PPOChooser): tipo di scelta, opzioni
  canoniche, scelta di base, indice scelto, se sta dichiarando (su una copia);
  non si aggiunge un chooser dove non c'era (cambierebbe choose_many);
- il generatore della partita: ogni `_randbelow(n)` e `random()` con l'esito.
Gli eventi vanno in una lista; `Trace.lines()` li dà in JSON.

Una partita tracciata deve giocare identica a una non tracciata
(`tests/rust/test_trace_py.py`).
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Optional

import numpy as np

from riftbound.rs.canon import Canon, RawDumper, rng_digest


class RecordingRandom(random.Random):
    """random.Random that tells a sink each primitive draw. A copy (pickle,
    the search's clones) has no sink and records nothing."""

    def __init__(self, x=None):
        super().__init__(x)
        self._sink: Optional[list] = None

    def _randbelow(self, n):  # noqa: D401 - the CPython primitive
        r = super()._randbelow(n)
        if getattr(self, "_sink", None) is not None:
            self._sink.append({"k": "rng", "op": "randbelow", "n": n, "r": r})
        return r

    def random(self):
        r = super().random()
        if getattr(self, "_sink", None) is not None:
            self._sink.append({"k": "rng", "op": "random", "r": repr(r)})
        return r


def recording_rng(rng: random.Random, sink: list) -> RecordingRandom:
    r = RecordingRandom()
    r.setstate(rng.getstate())
    r._sink = sink
    return r


def _digest_array(x) -> str:
    return hashlib.sha256(np.ascontiguousarray(x, dtype=np.float32).tobytes()).hexdigest()[:16]


class Trace:
    def __init__(self, gs, loop, *, with_obs: bool = True, with_state: bool = True, keep_states: bool = False):
        self.gs, self.loop = gs, loop
        self.events: list = []
        self.canon = Canon()
        self.with_obs, self.with_state = with_obs, with_state
        self.keep_states = keep_states
        self.states: dict = {}          # digest -> full canonical tree (keep_states)
        self.n = 0

    # -- helpers ----------------------------------------------------------
    def window(self) -> dict:
        gs = self.gs
        return {"turn": gs.turn, "active": gs.active, "chain": len(gs.chain),
                "showdown": gs.showdown_bf_idx if gs.showdown_active else None,
                "focus": gs.focus_player, "pending_move": list(gs.pending_move) if gs.pending_move else None,
                "points": [gs.points_A, gs.points_B]}

    def state(self) -> Optional[str]:
        if not self.with_state:
            return None
        d = RawDumper()
        root = d.fields(self.gs)
        root["$rng"] = rng_digest(self.gs.rng)
        tree = self.canon.canonical({"root": root, "objs": d.objs}, dumper_keep=d.keep)
        self.last_state = tree
        h = hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest()[:16]
        if self.keep_states:
            self.states[h] = tree
        return h

    def obs(self, seat: str) -> Optional[str]:
        if not self.with_obs:
            return None
        from riftbound.ai.encoding import encode_observation
        from riftbound.core.decisions import Observation
        return _digest_array(encode_observation(Observation.from_state(self.gs, seat)))

    def option(self, o):
        """A choose() option, canonical."""
        d = RawDumper()
        v = d.value(o) if not isinstance(o, tuple) or len(o) != 2 else [d.value(o[0]), d.value(o[1])]
        # Canonical ids through the game's Canon (first sight while tracing).
        tree = self.canon.canonical({"root": {"o": v}, "objs": d.objs}, dumper_keep=d.keep)
        return tree["root"]["o"]

    def add(self, ev: dict) -> None:
        ev["i"] = self.n
        self.n += 1
        self.events.append(ev)

    def lines(self) -> list[str]:
        return [json.dumps(e, sort_keys=True) for e in self.events]


def _menu(loop, point, seat):
    from riftbound.core.legality import legal_actions
    return legal_actions(loop, point, seat)


_COPY_BACK: dict = {}      # id(copied GameState) -> {id(copy object): original object}
_DEEPCOPY = None


def _hook_deepcopy() -> None:
    """Record, for each deepcopy of a GameState (a declaration's copy, a
    mode's lookahead), the map from the copy's objects back to the originals
    (as GameLoop._declare_choices' `back`): a choice made on a copy is traced
    with the real game's objects, as the Rust engine (one arena) has them."""
    global _DEEPCOPY
    import copy as _copy
    if _DEEPCOPY is not None:
        return
    _DEEPCOPY = _copy.deepcopy

    def deepcopy(x, memo=None, _nil=[]):
        from riftbound.core.loop import GameLoop
        from riftbound.core.state import GameState
        if memo is None:
            memo = {}
        out = _DEEPCOPY(x, memo)
        srcs = x if isinstance(x, tuple) else (x,)
        dsts = out if isinstance(out, tuple) else (out,)
        for src, dst in zip(srcs, dsts):
            g_src = src.gs if isinstance(src, GameLoop) else src
            g_dst = dst.gs if isinstance(dst, GameLoop) else dst
            if isinstance(g_src, GameState) and isinstance(g_dst, GameState):
                back = {id(memo[id(o)]): o for o in memo.get(id(memo), []) if id(o) in memo}
                outer = _COPY_BACK.get(id(g_src))
                if outer is not None:         # a copy of a copy: through to the real game
                    back = {k: outer[0].get(id(v), v) for k, v in back.items()}
                _COPY_BACK[id(g_dst)] = (back, g_dst)
        return out
    _copy.deepcopy = deepcopy


def _unhook_deepcopy() -> None:
    global _DEEPCOPY
    import copy as _copy
    if _DEEPCOPY is not None:
        _copy.deepcopy = _DEEPCOPY
        _DEEPCOPY = None
    _COPY_BACK.clear()


def _to_real(o, gs_of_loop):
    """An option of a choice made on a copy of the game, as the real game's object."""
    entry = _COPY_BACK.get(id(gs_of_loop))
    if entry is None:
        return o
    back = entry[0]
    if isinstance(o, tuple):
        return tuple(_to_real(x, gs_of_loop) for x in o)
    if o is None or isinstance(o, (bool, int, str)):
        return o
    return back.get(id(o), o)


def _to_real_any(o):
    """An object passed to an agent from a copy of the game (decide_mode on a
    declaration's copy), as the real game's object."""
    for back, _g in _COPY_BACK.values():
        if id(o) in back:
            return back[id(o)]
    return o


def instrument(gs, loop, *, with_obs: bool = True, with_state: bool = True, keep_states: bool = False) -> Trace:
    """Wrap the seats' agents, the loop's chooser and the game's RNG."""
    from riftbound.core.decisions import DecisionPoint
    tr = Trace(gs, loop, with_obs=with_obs, with_state=with_state, keep_states=keep_states)
    _hook_deepcopy()
    gs.rng = recording_rng(gs.rng, tr.events)

    for seat in ("A", "B"):
        agent = gs.get_player(seat).agent
        if agent is None:
            continue

        def wrap_menu(name, point, agent=agent, seat=seat):
            orig = getattr(agent, name)

            def wrapped(*a, **kw):
                win = tr.window()
                st = tr.state()
                ob = tr.obs(seat)
                legal = _menu(loop, point, seat)
                labels = [g.label for g in legal]
                act = orig(*a, **kw)
                idx = next((i for i, g in enumerate(legal) if g.to_engine() == tuple(act)), None)
                tr.add({"k": "decision", "seat": seat, "point": point.value, "win": win, "state": st, "obs": ob,
                        "menu": labels, "action": list(act), "index": idx})
                return act
            setattr(agent, name, wrapped)

        wrap_menu("decide_action", DecisionPoint.TURN_ACTION)
        wrap_menu("decide_reaction", DecisionPoint.REACTION)
        wrap_menu("decide_showdown_action", DecisionPoint.SHOWDOWN_ACTION)

        def wrap_simple(name, agent=agent, seat=seat):
            if not hasattr(agent, name):
                return
            orig = getattr(agent, name)

            def wrapped(*a, **kw):
                win = tr.window()
                st = tr.state()
                out = orig(*a, **kw)
                args = [tr.option(_to_real_any(x)) if not isinstance(x, (int, str, bool, type(None))) else x for x in a]
                tr.add({"k": name, "seat": seat, "win": win, "state": st, "args": args,
                        "out": out if isinstance(out, (int, bool, type(None))) else list(out)})
                return out
            setattr(agent, name, wrapped)

        for name in ("decide_mulligan", "decide_optional", "decide_mode", "decide_predict_recycle"):
            wrap_simple(name)

    if loop.chooser is not None:
        inner = loop.chooser

        class _Chooser:
            def __call__(self, lp, kind, side, options, default, source):
                st = tr.state()
                real = [_to_real(o, lp.gs) for o in options] if lp is not loop else options
                opts = [tr.option(o) for o in real]
                src_real = _to_real(source, lp.gs) if lp is not loop and source is not None else source
                src = tr.option(src_real) if src_real is not None else None
                i = inner(lp, kind, side, options, default, source)
                tr.add({"k": "choice", "seat": side, "kind": kind, "options": opts, "default": default,
                        "chosen": default if i is None else int(i), "by": "base" if i is None else "agent",
                        "declaring": lp is not loop, "source": src, "state": st})
                return i

            def __deepcopy__(self, memo):
                return self
        loop.chooser = _Chooser()
    return tr


def traced_game(seed: int, deck_a, deck_b, agents: dict, *, starter: str = "a", max_turns: int = 40,
                chooser: str = "ppo", with_obs: bool = True, with_state: bool = True, keep_states: bool = False):
    """A game with `agents` {"A": factory(player), "B": ...}, traced. ->
    (result, Trace)."""
    from riftbound.ai.ppo.agent import PPOChooser
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b, ai_a=None, ai_b=None,
                    max_turns=max_turns, first_player=starter)
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        p.agent = agents[seat](p)
    loop = GameLoop(gs)
    if chooser == "ppo":
        loop.chooser = PPOChooser(gs)
    tr = instrument(gs, loop, with_obs=with_obs, with_state=with_state, keep_states=keep_states)
    tr.add({"k": "start", "seed": seed, "starter": starter, "state": tr.state()})
    try:
        res = loop.start()
    finally:
        _unhook_deepcopy()
    tr.add({"k": "end", "winner": res.winner, "turns": gs.turn, "points": [gs.points_A, gs.points_B],
            "state": tr.state()})
    return res, tr
