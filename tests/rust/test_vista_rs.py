"""La vista della pagina coach da un dump grezzo (riftbound/rs/vista_rs.py).

a) Fedeltà su Python: a ogni decisione e a ogni scelta di partite Python
   (simple_trade, 5 matchup x 2 semi) la vista sullo stato vivo = la vista su
   `carica(raw_state(gs))`, per i due osservatori; il dump dello stato
   ricaricato = l'originale (forma canonica, salvo `$rng`) e i tipi dei campi
   (tupla / lista, enum / stringa, insieme) sono quelli dell'originale.
b) Stato Rust sul profilo storico: le stesse partite rigiocate su Rust
   (replay delle tracce, `trace_on()`): per ogni decisione / scelta la vista da
   `carica(event["state_raw"])` (+ `valore` per le opzioni) = la vista sullo
   stato Python vivo nello stesso punto (stesso ordine degli eventi).
Dieci partite (ES, EK, RS, IS, KS x semi 3 e 4); l'insieme sta sotto i 60 s."""
import contextlib
import dataclasses
import enum
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))

MATCHUPS = ["ES", "EK", "RS", "IS", "KS"]
SEEDS = [3, 4]
GAMES = [(mu, seed) for mu in MATCHUPS for seed in SEEDS]


def _safe(f, *a):
    try:
        return f(*a)
    except Exception as e:  # noqa: BLE001 — a view that fails must fail the same on both sides
        return ("EXC", type(e).__name__)


def _types_diff(a, b, path="gs", seen=None):
    """First place where the rebuilt object `b` has another type than the
    live one `a` (tuple / list, enum / str, set / frozenset, int / bool), or
    another set of attributes. Cards' static fields (CARD_STATIC) are the registry's."""
    from riftbound.rs.canon import CARD_STATIC
    seen = set() if seen is None else seen
    if type(a) is not type(b):
        return path, type(a).__name__, type(b).__name__
    if a is None or isinstance(a, (bool, int, float, str, enum.Enum)):
        return None if a == b else (path, a, b)
    if (id(a), id(b)) in seen:
        return None
    seen.add((id(a), id(b)))
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return path + ".len", len(a), len(b)
        for i, (x, y) in enumerate(zip(a, b)):
            d = _types_diff(x, y, f"{path}[{i}]", seen)
            if d:
                return d
        return None
    if isinstance(a, (set, frozenset)):
        return None if len(a) == len(b) else (path + ".len", len(a), len(b))
    if isinstance(a, dict):
        if len(a) != len(b):
            return path + ".len", len(a), len(b)
        for (k1, v1), (k2, v2) in zip(a.items(), b.items()):
            d = _types_diff(k1, k2, f"{path}.key", seen) or _types_diff(v1, v2, f"{path}[{k1!r}]", seen)
            if d:
                return d
        return None
    if hasattr(a, "__dict__") or dataclasses.is_dataclass(a):
        card = type(a).__mro__[-2].__name__ == "Card" or hasattr(a, "cost_energy")
        skip = CARD_STATIC if card else frozenset()
        # a card's dynamic attribute set to None is left out of the dump (reads as absent)
        va = {k: v for k, v in vars(a).items() if k not in skip and k not in ("agent", "rng", "uuid")
              and not (card and v is None)}
        vb = {k: v for k, v in vars(b).items() if k not in skip and k not in ("agent", "rng", "uuid")}
        if va.keys() != vb.keys():
            return path + ".attrs", sorted(va.keys() ^ vb.keys()), None
        for k, v in va.items():
            d = _types_diff(v, vb[k], f"{path}.{k}", seen)
            if d:
                return d
        return None
    return None


_LANE: dict = {}


@contextlib.contextmanager
def _views():
    """Views of one point of the game, faster: `spell_lane_free` (it plays the
    spell on copies) is asked once per (state, move) instead of once per viewer
    and action, and the copies are made without the trace's deepcopy hook
    (which only matters to the traced game itself)."""
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


def _decision_view(vista_rs, gs, loop, side, point, tuples):
    with _views():
        return {v: _safe(vista_rs.vista, gs, loop, side, v, point, tuples) for v in ("A", "B")}


def _choice_view(vista_rs, gs, options, source):
    return {v: _safe(vista_rs.vista_scelta, gs, v, options, source) for v in ("A", "B")}


def play(mu: str, seed: int) -> dict:
    """A traced Python game (simple_trade both, the choice hook of the PPO
    parity runs), with, at each decision and choice, the view on the live
    state and on the state rebuilt from its raw dump."""
    from riftbound.ai.ppo.agent import PPOChooser
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    from riftbound.rs import vista_rs
    from riftbound.rs.canon import Canon, RawDumper, first_diff, raw_state
    from riftbound.rs.mazzi import decks
    from riftbound.rs.trace_py import _to_real, _unhook_deepcopy, instrument

    starter = "a" if seed % 2 == 0 else "b"
    gs = build_game(game_seed=seed, deck_a_path=decks(mu)[0], deck_b_path=decks(mu)[1], ai_a=None, ai_b=None,
                    max_turns=40, first_player=starter)
    for s in "AB":
        p = gs.get_player(s)
        p.agent = make_agent("simple_trade", p)
    loop = GameLoop(gs)
    loop.chooser = PPOChooser(gs)
    tr = instrument(gs, loop, with_obs=False, with_state=False)
    recs: list = []

    def reload(real_gs):
        raw = raw_state(real_gs)
        gs2, objs = vista_rs.carica(raw)
        same = Canon().canonical(raw)
        again = Canon().canonical(raw_state(gs2))
        for t in (same, again):
            t["root"].pop("$rng", None)
        return gs2, objs, first_diff(same, again), _types_diff(real_gs, gs2)

    for seat in "AB":
        agent = gs.get_player(seat).agent
        for name, point in (("decide_action", DecisionPoint.TURN_ACTION), ("decide_reaction", DecisionPoint.REACTION),
                            ("decide_showdown_action", DecisionPoint.SHOWDOWN_ACTION)):
            def wrapped(*a, _orig=getattr(agent, name), _point=point, _seat=seat, **kw):
                legal = legal_actions(loop, _point, _seat)
                tuples = [g.to_engine() for g in legal]
                live = _decision_view(vista_rs, gs, loop, _seat, _point, tuples)
                gs2, _objs, canon_diff, types_diff = reload(gs)
                loop2 = vista_rs.vista_loop(gs2)
                legal2 = legal_actions(loop2, _point, _seat)
                tuples2 = [g.to_engine() for g in legal2]
                rec = {"k": "decision", "seat": _seat, "point": _point.value, "turn": gs.turn, "live": live,
                       "tuples": tuples, "labels": [g.label for g in legal], "canon_diff": canon_diff,
                       "types_diff": types_diff, "re_tuples": tuples2, "re_labels": [g.label for g in legal2],
                       "re": _decision_view(vista_rs, gs2, loop2, _seat, _point, tuples2)}
                out = _orig(*a, **kw)
                rec["action"] = list(out)
                recs.append(rec)
                return out
            setattr(agent, name, wrapped)

    inner = loop.chooser

    class _Chooser:
        def __call__(self, lp, kind, side, options, default, source):
            real = [_to_real(o, lp.gs) for o in options] if lp is not loop else list(options)
            src = _to_real(source, lp.gs) if lp is not loop and source is not None else source
            live = _choice_view(vista_rs, gs, real, src)
            gs2, objs, canon_diff, types_diff = reload(gs)

            def raw_of(o):
                d = RawDumper()
                return {"root": {"o": d.value(o)}, "objs": d.objs}, d.keep
            held = [raw_of(o) for o in real] + ([raw_of(src)] if src is not None else [])
            opts2 = [vista_rs.valore(r, objs) for r, _k in held[:len(real)]]
            src2 = vista_rs.valore(held[-1][0], objs) if src is not None else None
            rec = {"k": "choice", "kind": kind, "seat": side, "declaring": lp is not loop, "turn": gs.turn,
                   "live": live, "canon_diff": canon_diff, "types_diff": types_diff,
                   "re": _choice_view(vista_rs, gs2, opts2, src2)}
            recs.append(rec)
            return inner(lp, kind, side, options, default, source)

        def __deepcopy__(self, memo):
            return self
    loop.chooser = _Chooser()
    try:
        res = loop.start()
    finally:
        _unhook_deepcopy()
    return {"res": res, "events": tr.events, "recs": recs, "mu": mu, "seed": seed, "starter": starter}


_CACHE: dict = {}


def game(mu, seed):
    if (mu, seed) not in _CACHE:
        _CACHE[(mu, seed)] = play(mu, seed)
    return _CACHE[(mu, seed)]


def _where(r):
    return f"{r['k']} turn {r['turn']} seat {r['seat']} {r.get('point') or r.get('kind')}"


def _view_diff(a, b):
    from riftbound.rs.canon import first_diff
    return first_diff(json.loads(json.dumps(a, default=str)), json.loads(json.dumps(b, default=str)))


@pytest.mark.parametrize("mu,seed", GAMES)
def test_fidelity_on_python(mu, seed):
    g = game(mu, seed)
    recs = g["recs"]
    assert sum(r["k"] == "decision" for r in recs) > 50
    for r in recs:
        assert r["canon_diff"] is None, (_where(r), r["canon_diff"])
        assert r["types_diff"] is None, (_where(r), r["types_diff"])
        if r["k"] == "decision":
            assert r["re_labels"] == r["labels"] and r["re_tuples"] == r["tuples"], _where(r)
        for viewer in "AB":
            assert not (isinstance(r["live"][viewer], tuple) and r["live"][viewer][:1] == ("EXC",)), \
                (_where(r), r["live"][viewer])
            assert r["live"][viewer] == r["re"][viewer], (_where(r), viewer, _view_diff(r["live"][viewer], r["re"][viewer]))


def test_python_games_have_choices():
    kinds = {r["kind"].partition(":")[0] for mu, seed in GAMES for r in game(mu, seed)["recs"] if r["k"] == "choice"}
    assert len(kinds) >= 5, kinds


@pytest.mark.parametrize("mu,seed", GAMES)
def test_rust_state_on_historical_profile(mu, seed):
    import diff_trace
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.rs import vista_rs
    g = game(mu, seed)
    start, events, end, rres, err, _ = diff_trace.rust_events(seed, g["events"], g["starter"], mu)
    assert err is None and (rres[0], rres[1]) == (g["res"].winner, g["res"].turns)
    rs = [e for e in events if e["k"] in ("decision", "choice")]
    py = g["recs"]
    assert len(rs) == len(py)
    for e, r in zip(rs, py):
        assert e["k"] == r["k"] and e["seat"] == r["seat"]
        gs3, objs = vista_rs.carica(e["state_raw"])
        if e["k"] == "decision":
            point = DecisionPoint(e["point"])
            loop3 = vista_rs.vista_loop(gs3)
            legal = legal_actions(loop3, point, e["seat"])
            tuples = [a.to_engine() for a in legal]
            assert [a.label for a in legal] == e["menu"] == r["labels"], _where(r)
            assert tuples == r["tuples"] and e["action"] == r["action"], _where(r)
            if e["index"] is not None:
                assert list(tuples[e["index"]]) == e["action"], _where(r)
            view = _decision_view(vista_rs, gs3, loop3, e["seat"], point, tuples)
        else:
            assert e["kind"] == r["kind"] and e["declaring"] == r["declaring"], _where(r)
            options = [vista_rs.valore(o, objs) for o in e["options_raw"]]
            source = vista_rs.valore(e["source_raw"], objs) if e["source_raw"] is not None else None
            view = _choice_view(vista_rs, gs3, options, source)
        for viewer in "AB":
            assert view[viewer] == r["live"][viewer], (_where(r), viewer, _view_diff(r["live"][viewer], view[viewer]))
