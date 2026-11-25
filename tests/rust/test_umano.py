"""The human seat (Game.set_human_agent) and the live trace (trace_on(watch)):
a game of two simple_trade agents is recorded, then replayed with a human on
one or both seats whose `ask` checks the question against the recorded event
and answers what was recorded: same events, same final state. Exceptions of
`ask` / `watch` come out of start() as the same object."""
from __future__ import annotations

import json

import pytest

PROFILO = "6427b90+D72-D77"
MATCHUPS = ("EK", "ER", "KR", "EI", "KI", "RI", "ES", "KS", "RS", "IS")
SEEDS = (3, 4)
# `by`: who answered a choice. `correzioni`: the D72..D77 counters at the recording, taken
# after the agent's own work (simple_trade's lookups count; a human does none).
IGNORED = {"by", "correzioni"}
ANSWER = {"decision": ("action", "index"), "choice": ("chosen", "by")}


def build(mu, seed, first="a"):
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import rust_bridge as rb
    return rb.build(seed, DECK_OF[mu[0]], DECK_OF[mu[1]], first, 40, regole=PROFILO)


def fields(e):
    return ANSWER.get(e["k"], ("out",) if e["k"] != "rng" else ())


def question(e):
    """The recorded event as it is asked: no answer fields (`by` is the agent's)."""
    drop = set(fields(e)) | IGNORED
    return {k: v for k, v in e.items() if k not in drop}


def answer(e):
    # an action outside the menu (simple_trade plays some) is answered as the trace's `action` list
    return {"decision": lambda: e["index"] if e["index"] is not None else e["action"], "choice": lambda: e["chosen"]}.get(e["k"], lambda: e["out"])()


def record(mu, seed):
    import riftbound_rs
    riftbound_rs.azzera_correzioni()
    g = build(mu, seed)
    for s in "AB":
        g.set_agent(s, "simple_trade", 0)
    g.set_side_chooser()
    g.trace_on()
    g.start()
    return json.loads(g.events()), g.raw_dump()


def replay(mu, seed, humans, rec, watch=None):
    """The game with human seats answering from `rec`; -> (events, dump, asked)."""
    import riftbound_rs
    riftbound_rs.azzera_correzioni()
    g = build(mu, seed)
    queues = {s: [e for e in rec if e.get("seat") == s and e["k"] != "rng"] for s in humans}
    asked = []

    def make_ask(seat):
        def ask(ev):
            e = json.loads(ev)
            want = queues[seat].pop(0)
            check_actions(e, want)
            assert {k: v for k, v in e.items() if k not in IGNORED} == question(want)
            asked.append(e["k"])
            return answer(want)
        return ask

    for s in "AB":
        if s in humans:
            g.set_human_agent(s, make_ask(s))
        else:
            g.set_agent(s, "simple_trade", 0)
    g.set_side_chooser()
    g.trace_on(watch)
    g.start()
    assert all(not q for q in queues.values())
    return json.loads(g.events()), g.raw_dump(), asked


def check_actions(e, want):
    """`actions` is for `ask` alone: one trace-shaped action per menu item, on decisions only."""
    if e["k"] != "decision":
        assert "actions" not in e
        return
    acts = e.pop("actions")
    assert len(acts) == len(e["menu"])
    if want["index"] is not None:
        assert acts[want["index"]] == want["action"]


def same(ev, rec):
    """The events equal, IGNORED keys aside."""
    assert len(ev) == len(rec)
    for a, b in zip(ev, rec):
        assert {k: v for k, v in a.items() if k not in IGNORED} == {k: v for k, v in b.items() if k not in IGNORED}


@pytest.mark.parametrize("mu", MATCHUPS)
def test_replay_con_umano(mu):
    """A human on seat A, then on seat B, replays the recorded game."""
    for seed in SEEDS:
        rec, dump = record(mu, seed)
        for humans in ("A", "B"):
            ev, d, asked = replay(mu, seed, humans, rec)
            same(ev, rec)
            assert d == dump
            assert asked


def test_replay_due_umani_e_domande_di_ogni_tipo():
    kinds = set()
    for mu in ("EK", "RS"):
        rec, dump = record(mu, 3)
        ev, d, asked = replay(mu, 3, "AB", rec)
        same(ev, rec)
        assert d == dump
        kinds |= set(asked)
        # every decision and choice of the recorded game was asked
        assert len(asked) == sum(1 for e in rec if e["k"] != "rng")
    assert {"decision", "choice", "decide_mulligan"} <= kinds


def test_watch_uguale_a_events():
    rec, _ = record("EK", 3)
    seen = []
    ev, _, _ = replay("EK", 3, "A", rec, watch=lambda s: seen.append(json.loads(s)))
    assert seen == ev


class Stop(BaseException):
    pass


def test_eccezione_di_ask_stessa_istanza():
    import riftbound_rs
    boom = Stop("fermo")
    n = []

    def ask(ev):
        n.append(1)
        if len(n) == 5:
            raise boom
        e = json.loads(ev)
        return 0 if e["k"] in ("decision", "choice") else ([] if e["k"] == "decide_mulligan" else True)

    g = build("EK", 3)
    g.set_human_agent("A", ask)
    g.set_agent("B", "simple_trade", 0)
    with pytest.raises(Stop) as ei:
        g.start()
    assert ei.value is boom and len(n) == 5
    # nothing is poisoned: a fresh game plays to the end, traced
    riftbound_rs.azzera_correzioni()
    rec, dump = record("EK", 3)
    ev, d, _ = replay("EK", 3, "A", rec)
    assert d == dump


def test_eccezione_di_watch_stessa_istanza():
    boom = RuntimeError("watch")
    n = []

    def watch(s):
        n.append(1)
        if len(n) == 7:
            raise boom

    g = build("EK", 3)
    for s in "AB":
        g.set_agent(s, "simple_trade", 0)
    g.trace_on(watch)
    with pytest.raises(RuntimeError) as ei:
        g.start()
    assert ei.value is boom
    rec, dump = record("EK", 3)
    assert replay("EK", 3, "B", rec)[1] == dump


def test_eccezione_in_run_segment():
    boom = Stop("seg")

    def ask(ev):
        raise boom

    g = build("EK", 3)
    g.set_human_agent("A", ask)
    g.set_agent("B", "simple_trade", 0)
    with pytest.raises(Stop) as ei:
        g.run_segment(1)
    assert ei.value is boom


@pytest.mark.parametrize("bad", ["x", True, -1, 10**6, None, 1.5, [0]])
def test_risposta_non_valida_e_valueerror(bad):
    g = build("EK", 3)
    g.set_human_agent("A", lambda ev: bad)
    g.set_agent("B", "simple_trade", 0)
    with pytest.raises(ValueError):
        g.start()


def test_senza_trace_stesse_domande_e_stesso_stato():
    """Without trace_on the human is asked the same events and the game ends in the same state."""
    import riftbound_rs
    rec, dump = record("ER", 3)
    asked = []
    riftbound_rs.azzera_correzioni()
    g = build("ER", 3)
    queue = [e for e in rec if e.get("seat") == "B" and e["k"] != "rng"]

    def ask(ev):
        e = json.loads(ev)
        want = queue.pop(0)
        check_actions(e, want)
        asked.append(e)
        return answer(want)

    g.set_agent("A", "simple_trade", 0)
    g.set_human_agent("B", ask)  # sets the side chooser itself
    g.start()
    assert g.raw_dump() == dump
    assert [{k: v for k, v in e.items() if k not in IGNORED} for e in asked] == [
        question(e) for e in rec if e.get("seat") == "B" and e["k"] != "rng"]


@pytest.mark.parametrize("bad", [True, 99, "0", None, ["XX", 0, 0], [0], 1.0])
def test_risposta_non_valida_a_una_decisione(bad):
    g = build("EK", 3)

    def ask(ev):
        return [] if json.loads(ev)["k"] == "decide_mulligan" else bad

    g.set_human_agent("A", ask)
    g.set_agent("B", "simple_trade", 0)
    with pytest.raises(ValueError):
        g.start()
