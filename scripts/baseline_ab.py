#!/usr/bin/env python
"""A/B a candidate baseline rule for one kind of GameLoop.choose choice.

Each game is played twice with the same seed and decks (random legal decks over
the whole card pool, as in choice_audit.py; simple_trade on both seats): once
with the engine's baselines on both seats, once with one seat (A in even games,
B in odd) answering that kind of choice with the rule. Games are deterministic,
so a game where the rule never picked differently is the same game; the
difference in that seat's result is the rule's gain over the baseline.

Usage:
  uv run python scripts/baseline_ab.py 3000 eq_weakest dc_cheap kk_never

Prints, per rule: the games where the choice came up ("asked"), where the rule
picked differently ("deviated"), the gain per game and per deviated game (win
rate points, ± standard error). Runs gently (a quarter of the cores, low
priority).

B37 results (3000-4000 games): equip "weakest" +0.55 ± 0.20 per game (the old
baseline, the first unit on a battlefield, was no better than random); discard
"cheap" +0.43 ± 0.24, "costly" -0.53 ± 0.31; kicker "never" +0.43 ± 0.28 over
always paying, +0.07 ± 0.23 over paying only when what it unlocks has a target;
move targets / destinations: no difference from random measurable.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

DECKS: list = []


def _bf_of(loop, u):
    w = loop._locate_unit(u)
    return None if w is None else w[1]


def _cost(c):
    return int(c.cost_energy or 0) + int(c.cost_power or 0)


def _has_trigger(c, trig):
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get(c.name)
    return bool(spec) and any(es.trigger == trig for es in spec.effects)


def _runes(loop, side):
    p = loop.gs.get_player(side)
    return sum(len(rs) for rs in p.rune_pool.values())


# --- rules: (family prefix, fn(loop, kind, side, options, default, source, rng) -> option)

def eq_random(loop, kind, side, options, default, source, rng):
    return rng.choice(options)


def eq_mightiest(loop, kind, side, options, default, source, rng):
    return max(options, key=lambda u: (not u.stunned, u.might, _bf_of(loop, u) is not None, not u.is_token))


def eq_bf_mightiest(loop, kind, side, options, default, source, rng):
    return max(options, key=lambda u: (_bf_of(loop, u) is not None, not u.stunned, u.might, not u.is_token))


def eq_ready_mightiest(loop, kind, side, options, default, source, rng):
    return max(options, key=lambda u: (u.ready and not u.stunned, u.might, _bf_of(loop, u) is not None))


def eq_fight(loop, kind, side, options, default, source, rng):
    other = loop.gs.other(side)

    def key(u):
        bf = _bf_of(loop, u)
        contested = bf is not None and bool(bf._units_for(other))
        return (contested, u.ready and not u.stunned, bf is not None, u.might, not u.is_token)
    return max(options, key=key)


def eq_weakest(loop, kind, side, options, default, source, rng):
    return min(options, key=lambda u: (u.is_token, u.stunned, u.might))


def eq_weakest_nogear(loop, kind, side, options, default, source, rng):
    return min(options, key=lambda u: (u.is_token, u.stunned, len(u.gear), u.might))


def eq_weakest_bf(loop, kind, side, options, default, source, rng):
    return min(options, key=lambda u: (u.is_token, u.stunned, _bf_of(loop, u) is None, u.might))


def eq_weakest_ready(loop, kind, side, options, default, source, rng):
    return min(options, key=lambda u: (u.is_token, u.stunned or not u.ready, u.might))


def eq_weakest_tok(loop, kind, side, options, default, source, rng):
    return min(options, key=lambda u: (u.stunned, u.might))


def kk_energy(loop, kind, side, options, default, source, rng):
    if kind != "optional:additional_cost":
        return None
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get(source.name)
    acs = [es.additional_cost for es in spec.effects if getattr(es, "additional_cost", None)]
    return None if all(set(ac) <= {"energy"} for ac in acs) else False


def mv_weak(loop, kind, side, options, default, source, rng):
    d = options[default]
    if not isinstance(d, tuple) or d[0] != side:
        return None
    mine = [o for o in options if isinstance(o, tuple) and o[0] == side]
    return min(mine, key=lambda o: (o[1].stunned, o[1].might))


def _own(loop, side, options):
    return all(any(c is h for h in loop.gs.get_player(side).hand) for c in options)


def dc_random(loop, kind, side, options, default, source, rng):
    return rng.choice(options)


def dc_cheap(loop, kind, side, options, default, source, rng):
    if not _own(loop, side, options):
        return None
    return min(options, key=lambda c: (not _has_trigger(c, "on_discarded"), _cost(c), int(c.might or 0)))


def dc_costly(loop, kind, side, options, default, source, rng):
    if not _own(loop, side, options):
        return None
    return min(options, key=lambda c: (not _has_trigger(c, "on_discarded"), -_cost(c)))


def dc_unaffordable(loop, kind, side, options, default, source, rng):
    if not _own(loop, side, options):
        return None
    have = _runes(loop, side)

    def key(c):
        far = int(c.cost_energy or 0) > have + 2
        return (not _has_trigger(c, "on_discarded"), not far, -_cost(c) if far else _cost(c))
    return min(options, key=key)


def kk_never(loop, kind, side, options, default, source, rng):
    return False if kind == "optional:additional_cost" else None


def kk_resources(loop, kind, side, options, default, source, rng):
    if kind != "optional:additional_cost":
        return None
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get(source.name)
    acs = [es.additional_cost for es in spec.effects if getattr(es, "additional_cost", None)]
    res = all(set(ac) <= {"energy", "power", "domain", "spend_xp"} for ac in acs)
    return None if res else False


def kk_targets(loop, kind, side, options, default, source, rng):
    """Pay only if an instruction the kicker unlocks has something to choose."""
    if kind != "optional:additional_cost":
        return None
    from riftbound.core.effects import has_valid_target
    from riftbound.core.loop import EffectContext
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get(source.name)
    gated = [es for es in spec.effects if (es.condition or {}).get("type") == "kicker_paid"]
    if not gated:
        return None
    gs = loop.gs
    ctx = EffectContext(loop, source, gs.get_player(side), gs.get_player(gs.other(side)),
                        gs.battlefields[0], {})
    checks = []
    for es in gated:
        d = {**es.merged_params(), "effect": es.effect}
        try:
            checks.append(has_valid_target(ctx, d))
        except Exception:  # noqa: BLE001
            checks.append(None)
    if checks and all(c is False for c in checks):
        return False
    return None


def mv_random(loop, kind, side, options, default, source, rng):
    return rng.choice(options)


RULES = {
    "eq_random": ("equip", eq_random), "eq_mightiest": ("equip", eq_mightiest),
    "eq_bf_mightiest": ("equip", eq_bf_mightiest), "eq_ready_mightiest": ("equip", eq_ready_mightiest),
    "eq_fight": ("equip", eq_fight), "eq_weakest": ("equip", eq_weakest),
    "dc_random": ("discard", dc_random), "dc_cheap": ("discard", dc_cheap),
    "dc_costly": ("discard", dc_costly), "dc_unaffordable": ("discard", dc_unaffordable),
    "kk_never": ("optional:additional_cost", kk_never), "kk_resources": ("optional:additional_cost", kk_resources),
    "kk_targets": ("optional:additional_cost", kk_targets),
    "eq_weakest_nogear": ("equip", eq_weakest_nogear), "eq_weakest_bf": ("equip", eq_weakest_bf),
    "eq_weakest_ready": ("equip", eq_weakest_ready), "eq_weakest_tok": ("equip", eq_weakest_tok),
    "kk_energy": ("optional:additional_cost", kk_energy), "mv_weak": ("target:move_unit", mv_weak),
    "mv_random_t": ("target:move_unit", mv_random), "mv_random_d": ("destination", mv_random),
    "mvb_random_t": ("target:move_units_to_base", mv_random),
}


class Chooser:
    def __init__(self, game, rule=None, side=None):
        self.rule = RULES[rule] if rule else None
        self.side = side
        self.rng = random.Random(game * 7919 + 13)
        self.dev = 0
        self.n = 0

    def __call__(self, loop, kind, side, options, default, source):
        if self.rule is None or side != self.side or not kind.startswith(self.rule[0]):
            return None
        if len(options) < 2:
            return None
        self.n += 1
        got = self.rule[1](loop, kind, side, options, default, source, self.rng)
        if got is None:
            return None
        i = next((i for i, o in enumerate(options) if o is got or (isinstance(got, bool) and o == got)), None)
        if i is None:
            return None
        if i != default:
            self.dev += 1
        return i


def _init(decks):
    global DECKS
    from riftbound.compute import be_gentle
    be_gentle()
    import warnings
    warnings.filterwarnings("ignore")
    DECKS = decks


def play(game, rule=None):
    from choice_audit import _agent
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    a, b = random.Random(game).sample(DECKS, 2)
    gs = build_game(game_seed=game, deck_a_path=a, deck_b_path=b, ai_a=None, ai_b=None)
    for p in (gs.A, gs.B):
        p.agent = _agent("simple_trade", p, game)
    side = "A" if game % 2 == 0 else "B"
    ch = Chooser(game, rule, side)
    loop = GameLoop(gs)
    loop.chooser = ch
    try:
        w = loop.start().winner
    except Exception as e:  # noqa: BLE001
        return game, side, "ERR:" + type(e).__name__, ch.dev, ch.n
    return game, side, w, ch.dev, ch.n


def job(args):
    game, rule = args
    return rule, play(game, rule)


def score(w, side):
    return 1.0 if w == side else 0.5 if w == "DRAW" else 0.0


def main():
    games = int(sys.argv[1])
    rules = sys.argv[2:]
    from choice_audit import random_decks
    import tempfile
    decks = random_decks(120, 7, Path(tempfile.mkdtemp(prefix="ab_")))
    from riftbound.compute import default_workers
    jobs = [(g, None) for g in range(games)] + [(g, r) for r in rules for g in range(games)]
    res: dict = {}
    with Pool(default_workers(), initializer=_init, initargs=(decks,)) as pool:
        for rule, (g, side, w, dev, n) in pool.imap_unordered(job, jobs, chunksize=4):
            res[(rule, g)] = (side, w, dev, n)
    errs = sum(1 for v in res.values() if str(v[1]).startswith("ERR"))
    print(f"errors: {errs}")
    for r in rules:
        deltas, dev_d, devs, asked = [], [], 0, 0
        for g in range(games):
            side, w0, _, _ = res[(None, g)]
            _, w1, dev, n = res[(r, g)]
            if str(w0).startswith("ERR") or str(w1).startswith("ERR"):
                continue
            d = score(w1, side) - score(w0, side)
            deltas.append(d)
            asked += n > 0
            if dev:
                devs += 1
                dev_d.append(d)
            elif d:
                print(f"  nondeterministic: rule {r} game {g}")
        se = pstdev(deltas) / len(deltas) ** 0.5 if len(deltas) > 1 else 0
        se2 = pstdev(dev_d) / len(dev_d) ** 0.5 if len(dev_d) > 1 else 0
        print(f"{r:20s} games {len(deltas)} asked {asked} deviated {devs} | per game "
              f"{100 * mean(deltas):+.2f} ± {100 * se:.2f} | per deviated game "
              f"{100 * mean(dev_d) if dev_d else 0:+.1f} ± {100 * se2:.1f}", flush=True)


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        env = {**os.environ, "PYTHONHASHSEED": "0"}
        sys.exit(subprocess.call([sys.executable, *sys.argv], env=env))
    main()
