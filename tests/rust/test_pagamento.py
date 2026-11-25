"""The page's "Come paghi?" on Rust (rbsim-core payment.rs, human.rs; py: coach.payment_options,
gold_only_plays, CoachAgent._coached / _gold_step, CoachLoop.recycle_first), historical profile "6427b90"
(Rust = Python), ES EK RS IS KS x seeds 3, 4, both seats.

a) Ways: in a Python game (simple_trade) at every decision of one seat the ways `payment_options` gives
   (where there is more than one) and the plays `gold_only_plays` gives equal the `pay` / `gold_only` of the
   event the Rust human seat is asked at the same decision (the Rust game answers the Python game's moves).
b) End to end: the seat is the page's CoachAgent (a mock session answers it: a move picked by a seeded policy,
   at every decision with more than one way the LAST way, and Gold-only plays when offered); the same policy
   answers the Rust human seat through `ask` ({"index": i, "via": w}, {"solo_gold": j, "via": w}). The two
   games' events (diff_trace's comparison: seat, window, canonical state, menu, action, choices, draws) and
   final states are identical, and ways other than the engine's own were played."""
from __future__ import annotations

import contextlib
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))

PROFILO = "6427b90"
MATCHUPS = ["ES", "EK", "RS", "IS", "KS"]
SEEDS = [3, 4]
GAMES = [(mu, seed, seat) for mu in MATCHUPS for seed in SEEDS for seat in "AB"]
WAYS_GAMES = [g for g in GAMES if (SEEDS.index(g[1]) + "AB".index(g[2])) % 2 == 0]    # each seed on one seat, the next on the other
KINDS = ("decision", "choice", "decide_mulligan", "decide_optional", "decide_mode", "decide_predict_recycle")
_LANE: dict = {}


@contextlib.contextmanager
def plain_copies():
    """The page's computations on copies of the game, made without the trace's deepcopy hook (which only
    matters to the traced game itself) and with `spell_lane_free` asked once per (state, move)."""
    import copy
    from riftbound.ai import coach
    from riftbound.rs import trace_py
    orig, hooked = coach.spell_lane_free, copy.deepcopy
    _LANE.clear()

    def lane_free(loop, side, point, idx):
        key = (id(loop), side, point, idx)
        if key not in _LANE:
            _LANE[key] = orig(loop, side, point, idx)
        return _LANE[key]
    coach.spell_lane_free = lane_free
    if trace_py._DEEPCOPY is not None:
        copy.deepcopy = trace_py._DEEPCOPY
    try:
        yield
    finally:
        coach.spell_lane_free, copy.deepcopy = orig, hooked
        _LANE.clear()


def way_json(w) -> dict:
    """A python way as the Rust event carries it (no Italian `text`)."""
    name = lambda d: None if d is None else d.name  # noqa: E731
    return {"golds": w["golds"], "gold_domain": name(w["gold_domain"]), "prefer": name(w["prefer"]),
            "recycled": [[d, n] for d, n in w["recycled"]]}


def pick(rng, n, g):
    """The seeded policy of both seats: a move among the `n` of the menu and the `g` Gold-only plays."""
    if g and rng.random() < 0.5:
        return n + rng.randrange(g)
    if n > 1 and rng.random() < 0.8:
        return 1 + rng.randrange(n - 1)
    return 0


def loop_class():
    from riftbound.ai.coach import CoachLoop
    from riftbound.rs.trace_py import _to_real

    class _TraceLoop(CoachLoop):
        tr = None

        def _consult(self, loop, kind, side, options, default, source):
            tr = self.tr
            st = tr.state()
            real = [_to_real(o, loop.gs) for o in options] if loop is not self else options
            opts = [tr.option(o) for o in real]
            src_real = _to_real(source, loop.gs) if loop is not self and source is not None else source
            src = tr.option(src_real) if src_real is not None else None
            i = super()._consult(loop, kind, side, options, default, source)
            tr.add({"k": "choice", "seat": side, "kind": kind, "options": opts, "default": default,
                    "chosen": default if i is None else int(i), "by": "base" if i is None else "agent",
                    "declaring": loop is not self, "source": src, "state": st})
            return i
    return _TraceLoop


class Session:
    """The page's session, answering by the seeded policy (see `pick`)."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.ways = self.gold_ways = self.solo = 0

    def __getattr__(self, name):                 # show_looked, thinking, notice_chain, event, record...
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None

    def ask_decision(self, point, side, infos, suggestions, context=""):
        solo = sum(1 for a in infos if a["text"].endswith(" (col Gold)"))
        i = pick(self.rng, len(infos) - solo, solo)
        self.solo += i >= len(infos) - solo
        return {"action": i}

    def ask_choice(self, kind, side, options, default, source):
        if kind != "payment":
            return default
        self.ways += 1
        self.gold_ways += "Gold" in options[-1]["text"]
        return len(options) - 1                  # the last way


def play_python(mu, seed, seat, drive):
    """A traced Python game, simple_trade on the other seat; `seat` is simple_trade whose decisions' ways are
    recorded (drive False) or the page's CoachAgent (drive True). -> (events, trees, recorded ways, session)."""
    from riftbound.ai import coach
    from riftbound.ai.ppo.agent import PPOChooser
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.legality import legal_actions
    from riftbound.rs.mazzi import decks
    from riftbound.rs.trace_py import _unhook_deepcopy, instrument

    starter = "a" if seed % 2 == 0 else "b"
    gs = build_game(game_seed=seed, deck_a_path=decks(mu)[0], deck_b_path=decks(mu)[1], ai_a=None, ai_b=None,
                    max_turns=40, first_player=starter)
    session = Session(seed * 7 + 1)
    recs: list = []

    class Driver(coach.CoachAgent):
        """The page's agent; what the page leaves to the chooser takes the engine's defaults."""
        def decide_mulligan(self):
            return []

        def decide_optional(self, card, name):
            return True

        def decide_mode(self, card, n):
            return None

        def decide_predict_recycle(self, card):
            return False

        def _coached(self, *a, **kw):
            with plain_copies():
                return super()._coached(*a, **kw)

    class PassChooser(coach._CoachChooser):
        """The coach's chooser answers by the engine's defaults here."""
        def __call__(self, loop, kind, side, options, default, source):
            return self.previous(loop, kind, side, options, default, source) if self.previous else None

    for s in "AB":
        p = gs.get_player(s)
        p.agent = make_agent("simple_trade", p)
    me = gs.get_player(seat)
    if drive:
        me.agent = Driver(me, None, session, iterations=1, rng=random.Random(seed))
    loop = loop_class()(gs)
    if drive:
        me.agent.gs, me.agent.loop = gs, loop
    tr = instrument(gs, loop, with_obs=False, keep_states=True)      # no chooser yet: the loop records the choices
    loop.tr = tr
    loop.chooser = PPOChooser(gs)

    if not drive:
        agent = me.agent
        for name, point in (("decide_action", DecisionPoint.TURN_ACTION), ("decide_reaction", DecisionPoint.REACTION),
                            ("decide_showdown_action", DecisionPoint.SHOWDOWN_ACTION)):
            def wrapped(*a, _orig=getattr(agent, name), _point=point, **kw):
                with plain_copies():
                    tuples = [g.to_engine() for g in legal_actions(loop, _point, seat)]
                    pay, solo = [None] * len(tuples), []
                    if len(tuples) > 1:
                        for i, t in enumerate(tuples):
                            w = coach.payment_options(loop, seat, _point, t)
                            pay[i] = [way_json(x) for x in w] if len(w) > 1 else None
                        solo = [{"action": list(t), "ways": [way_json(x) for x in coach.payment_options(loop, seat, _point, t)]}
                                for t, _info in coach.gold_only_plays(loop, seat, _point, tuples)]
                recs.append({"point": _point.value, "menu": [list(t) for t in tuples], "pay": pay, "gold_only": solo})
                return _orig(*a, **kw)
            setattr(agent, name, wrapped)

    saved = coach._CoachChooser
    coach._CoachChooser = PassChooser
    tr.add({"k": "start", "seed": seed, "starter": starter, "state": tr.state()})
    try:
        res = loop.start()
    finally:
        coach._CoachChooser = saved
        _unhook_deepcopy()
    tr.add({"k": "end", "winner": res.winner, "turns": gs.turn, "points": [gs.points_A, gs.points_B],
            "state": tr.state()})
    return tr.events, tr.states, recs, session


def play_rust(mu, seed, seat, ask):
    """The same game on Rust with a human on `seat` asking `ask`, simple_trade on the other. -> start, events, end."""
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.mazzi import decks
    g = rb.build(seed, *decks(mu), "a" if seed % 2 == 0 else "b", 40, regole=PROFILO)
    for s in "AB":
        if s == seat:
            g.set_human_agent(s, ask, payments=True)
        else:
            g.set_agent(s, "simple_trade", 0)
    g.set_side_chooser()
    start = json.loads(g.raw_dump())
    g.trace_on()
    g.start()
    return start, json.loads(g.events()), json.loads(g.raw_dump())


def first_difference(py_events, py_trees, start, events, end):
    """diff_trace's comparison of the Python game and the Rust one (who answers a choice aside)."""
    import diff_trace
    rs, rs_trees = diff_trace.canonical_rust_events(start, events, end)
    py = [e for e in py_events if e["k"] in diff_trace.FIELDS or e["k"].startswith("decide_")]
    unby = lambda es: [{**e, "by": None} if e["k"] == "choice" else e for e in es]  # noqa: E731
    return diff_trace.first_difference(unby(py), unby(rs), py_trees, rs_trees)


def _answer_py_event(e):
    """What the Python game's event says, as the answer of the human seat."""
    return {"decision": lambda: e["action"], "choice": lambda: e["chosen"]}.get(e["k"], lambda: e["out"])()


_CACHE: dict = {}


def ways_game(mu, seed, seat):
    if (mu, seed, seat) not in _CACHE:
        events, trees, recs, _ = play_python(mu, seed, seat, drive=False)
        queue = [e for e in events if e.get("seat") == seat and e["k"] in KINDS]
        asked: list = []

        def ask(ev):
            e = json.loads(ev)
            want = queue.pop(0)
            assert e["k"] == want["k"], (e["k"], want["k"])
            if e["k"] == "decision":
                assert e["menu"] == want["menu"]
                asked.append({"point": e["point"], "menu": e["menu"], "pay": e["pay"], "gold_only": e["gold_only"]})
            return _answer_py_event(want)
        play_rust(mu, seed, seat, ask)
        assert not queue
        _CACHE[(mu, seed, seat)] = (recs, asked)
    return _CACHE[(mu, seed, seat)]


@pytest.mark.parametrize("mu,seed,seat", WAYS_GAMES)
def test_ways_equal_python(mu, seed, seat):
    recs, asked = ways_game(mu, seed, seat)
    assert len(recs) == len(asked) > 20
    for k, (py, rs) in enumerate(zip(recs, asked)):
        assert py["point"] == rs["point"]
        assert py["pay"] == rs["pay"], (k, py["pay"], rs["pay"])
        assert py["gold_only"] == rs["gold_only"], (k, py["gold_only"], rs["gold_only"])


def test_ways_exist():
    """The comparison is not empty: decisions with a choice of ways, and (if any deck has Golds) Gold-only plays."""
    pay = sum(sum(w is not None for w in r["pay"]) for mu, seed, seat in WAYS_GAMES for r in ways_game(mu, seed, seat)[0])
    solo = sum(len(r["gold_only"]) for mu, seed, seat in WAYS_GAMES for r in ways_game(mu, seed, seat)[0])
    print(f"moves with more than one way: {pay}; Gold-only plays offered: {solo}")
    assert pay > 0


@pytest.mark.parametrize("mu,seed,seat", GAMES)
def test_end_to_end(mu, seed, seat):
    events, trees, _, session = play_python(mu, seed, seat, drive=True)
    rng = random.Random(seed * 7 + 1)
    stats = {"ways": 0, "gold_ways": 0, "solo": 0}

    def ask(ev):
        e = json.loads(ev)
        k = e["k"]
        if k == "decision":
            n = len(e["menu"])
            if n <= 1:
                return 0 if n else None
            solo = e["gold_only"]
            i = pick(rng, n, len(solo))
            if i >= n:
                ways = solo[i - n]["ways"]
                stats["solo"] += 1
                if len(ways) > 1:                # asked of the page only then
                    stats["ways"] += 1
                    stats["gold_ways"] += ways[-1]["golds"] > 0
                return {"solo_gold": i - n, "via": len(ways) - 1}
            ways = e["pay"][i]
            if ways:
                stats["ways"] += 1
                stats["gold_ways"] += ways[-1]["golds"] > 0
                return {"index": i, "via": len(ways) - 1}
            return i
        if k == "choice":
            return e["default"]
        return {"decide_mulligan": [], "decide_optional": True, "decide_mode": None, "decide_predict_recycle": False}[k]
    start, rs_events, end = play_rust(mu, seed, seat, ask)
    d = first_difference(events, trees, start, rs_events, end)
    assert d is None, d
    assert stats == {"ways": session.ways, "gold_ways": session.gold_ways, "solo": session.solo}
    _TOTALS.append((mu, seed, seat, stats["ways"], stats["gold_ways"], stats["solo"]))


_TOTALS: list = []


def test_non_default_ways_were_played():
    """After the end-to-end games: ways other than the engine's own were played, Gold plays too if any deck has Golds."""
    if not _TOTALS:
        pytest.skip("run with the end-to-end games")
    ways = sum(t[3] for t in _TOTALS)
    gold = sum(t[4] for t in _TOTALS)
    solo = sum(t[5] for t in _TOTALS)
    print(f"non-default ways played: {ways} (with Golds: {gold}); Gold-only plays: {solo}")
    assert ways > 0
