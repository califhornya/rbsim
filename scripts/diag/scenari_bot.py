"""The bot in the user's scenarios: what the search of today (hand-written value,
`handwritten_value.py`) chooses where the user answered (docs/bot/GIUDIZI.md).

The scenario is played up to the user's first decision (riftbound/ai/scenari.py);
there the user's seat becomes the bot and the other seat simple_trade, to the
end of that turn. Printed: the bot's moves with their visits, and the position
after the turn.

    PYTHONPATH=. python scripts/diag/scenari_bot.py S11a,S11b,S8 100 3   # ids, iterations, seeds
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handwritten_value import table_value  # noqa: E402

from riftbound.ai.coach import action_info  # noqa: E402
from riftbound.ai.net_mcts import NetGuidedMCTSAgent  # noqa: E402
from riftbound.ai.scenari import (  # noqa: E402
    ScenarioOver, ScriptedChooser, ScriptedSeat, _plan, _use_legend, build_state, get_scenario,
    position, stop_after_turn,
)
from riftbound.core.decisions import DecisionPoint, Observation  # noqa: E402
from riftbound.core.game_factory import make_agent  # noqa: E402
from riftbound.core.loop import GameLoop  # noqa: E402


class Bot(NetGuidedMCTSAgent):
    """The search with the hand-written value and uniform priors (as the baseline)."""

    def _evaluate(self, clone, side, legal_ga):
        ts = [a.to_engine() for a in legal_ga]
        return {t: 1.0 / max(1, len(ts)) for t in ts}, table_value(Observation.from_state(clone, side))

    def _net_value(self, clone, side):
        return table_value(Observation.from_state(clone, side))

    _value_only = _net_value


def run(sid: str, iters: int, seed: int) -> dict:
    sc = get_scenario(sid)
    gs = build_state(sc)
    plan = _plan(sc)
    side = sc["human"]
    moves: list = []
    state: dict = {}

    def logged(bot, name, point):
        inner = getattr(bot, name)

        def call(*a, **k):
            bot.last_visits = {}          # a decision with one option leaves the last ones
            act = inner(*a, **k)
            text = action_info(bot.loop, side, side, point, act)["text"]
            visits = sorted(((n, action_info(bot.loop, side, side, point, t)["text"])
                             for t, n in (bot.last_visits or {}).items()), reverse=True)[:4]
            moves.append({"turn": bot.gs.turn, "point": point.value, "move": text,
                          "visits": [(round(n, 2), t) for n, t in visits]})
            return act
        setattr(bot, name, call)

    def take_over(agent, point, bf_idx):
        """The user's first decision: the bot and simple_trade take the seats."""
        loop = agent.loop
        if sc.get("legend_used"):
            _use_legend(gs, side)
        state["before"] = position(gs, side)
        me, them = gs.get_player(side), gs.get_player(gs.other(side))
        bot = Bot(me, None, iterations=iters, rng=random.Random(seed), backup="best")
        for name, p in (("decide_action", DecisionPoint.TURN_ACTION),
                        ("decide_showdown_action", DecisionPoint.SHOWDOWN_ACTION),
                        ("decide_reaction", DecisionPoint.REACTION)):
            logged(bot, name, p)
        opp = make_agent("simple_trade", them)
        for p, a in ((me, bot), (them, opp)):
            p.agent, a.gs, a.loop = a, gs, loop
        if point == DecisionPoint.TURN_ACTION:
            return bot.decide_action(them)
        if point == DecisionPoint.SHOWDOWN_ACTION:
            return bot.decide_showdown_action(them, bf_idx)
        return bot.decide_reaction(them, gs.chain)

    for s in ("A", "B"):
        p = gs.get_player(s)
        p.agent = ScriptedSeat(p, sc, plan, human=take_over if s == side else None)
    loop = GameLoop(gs)
    loop.chooser = ScriptedChooser(plan, sc["id"])
    stop_after_turn(loop, int(sc["turn"]))
    try:
        loop.start()
    except ScenarioOver:
        pass
    state["after"] = position(gs, side)
    state["moves"] = moves
    return state


def _short(pos: dict) -> str:
    keep = ("score", "hand", "me", "my_facedown", "opp", "controls")
    return " | ".join(f"{k}={pos.get(k)}" for k in keep)


if __name__ == "__main__":
    ids = sys.argv[1].split(",")
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    seeds = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    for sid in ids:
        print(f"== {sid} ({iters} iterazioni)")
        for seed in range(seeds):
            r = run(sid, iters, seed)
            print(f"  seme {seed}:")
            for m in r["moves"]:
                print(f"    T{m['turn']} {m['point']}: {m['move']}   visite {m['visits']}")
            print(f"    dopo: {_short(r['after'])}")
