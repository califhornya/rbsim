"""tie_break="mean" (19/11): under backup="best", among root moves level in Q
the bot takes the highest W/N, then the most visits, then the first.

s3012 (docs/bot/posizioni/, TURNO_AVVERSARIO.md): Zed defending BF0 and
attacking BF1 have the same Q to the last digit, and the last digit chose
(Linux attacked, the Mac defended); W/N prefers the defence (0.445 / 0.414),
the right move (forcing only that first move: 23/24 against 8/24)."""
import pickle
import random
from pathlib import Path

from riftbound.ai.handwritten import HandwrittenAgent
from riftbound.ai.net_mcts import _break_tie, _Node
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.state import determinize

POS = Path(__file__).resolve().parents[1] / "docs/bot/posizioni/s3012_B_t07_05.pkl"


def _node(q, w, n):
    c = _Node()
    c.Q, c.W, c.N = q, w, n
    return c


def test_break_tie_rule():
    a, b, c = _node(0.5, 4.0, 10), _node(0.5, 4.5, 10), _node(0.4, 9.0, 10)
    assert _break_tie([("a", a), ("b", b), ("c", c)], "a") == "b"     # higher W/N among the level
    a, b = _node(0.5, 4.0, 10), _node(0.5 - 1e-12, 8.0, 20)
    assert _break_tie([("a", a), ("b", b)], "a") == "b"               # same mean: more visits
    a, b = _node(0.5, 4.0, 10), _node(0.5, 4.0, 10)
    assert _break_tie([("a", a), ("b", b)], "a") == "a"               # all level: the first
    a, b = _node(0.5, 1.0, 10), _node(0.49, 9.0, 10)
    assert _break_tie([("a", a), ("b", b)], "a") == "a"               # not level: Q decides


def test_s3012_defends_with_the_mean_tie_break():
    d = pickle.load(open(POS, "rb"))
    side = d["side"]
    for w in range(3):
        gs = d["state"].clone()
        gs.rng = random.Random(10_000 + w)
        determinize(gs, observer=side, rng=gs.rng)
        p = gs.get_player(side)
        p.agent = HandwrittenAgent(p, rng=random.Random(20_000 + w), tie_break="mean")
        GameLoop(gs)
        root = p.agent.search(DecisionPoint.TURN_ACTION,
                              legal_actions(p.agent.loop, DecisionPoint.TURN_ACTION, side),
                              cards_played=d["cards_played"])
        defend, attack = root.children[d["reply"]], root.children[d["ref"]]
        assert abs(defend.Q - attack.Q) < 1e-9
        assert p.agent._play(root, side) == d["reply"]
