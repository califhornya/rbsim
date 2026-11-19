"""advance_forced_move (19/11, boot1 arena): the PASS that closes a move, when
no other unit can join, is played at once in the search instead of valuing
the half-declared move; the hybrid NetValueAgent searches with equal priors.

s3048 (docs/bot/posizioni/): Evelynn Entrancing moving to BF0 or BF1 leaves
PASS as the only legal action (checked here)."""
import pickle
import random
from pathlib import Path

import pytest

from riftbound.ai.handwritten import HandwrittenAgent
from riftbound.ai.net_mcts import _PASS
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.state import determinize

POS = Path(__file__).resolve().parents[1] / "docs/bot/posizioni/s3048_A_t03_01.pkl"


def _setup(advance: bool):
    d = pickle.load(open(POS, "rb"))
    side = d["side"]
    gs = d["state"].clone()
    gs.rng = random.Random(10_000)
    determinize(gs, observer=side, rng=gs.rng)
    p = gs.get_player(side)
    p.agent = HandwrittenAgent(p, iterations=200, rng=random.Random(20_000))
    p.agent.advance_forced_move = advance
    loop = GameLoop(gs)
    legal = legal_actions(loop, DecisionPoint.TURN_ACTION, side)
    return p.agent, legal, d["cards_played"]


def _move_children(root, legal):
    keys = [a.to_engine() for a in legal if a.kind == "MOVE"]
    assert len(keys) == 2
    return [root.children[k] for k in keys]


def test_without_advance_the_move_node_has_only_the_pass_child():
    agent, legal, cp = _setup(False)
    root = agent.search(DecisionPoint.TURN_ACTION, legal, cards_played=cp)
    for child in _move_children(root, legal):
        assert child.expanded
        assert list(child.children) == [_PASS]


def test_with_advance_the_move_node_is_valued_after_the_pass():
    agent, legal, cp = _setup(True)
    root = agent.search(DecisionPoint.TURN_ACTION, legal, cards_played=cp)
    for child in _move_children(root, legal):
        # Valued after the move's showdown: expanded at the turn's next actions,
        # or below the choices the conquest asks (Zaun Warrens: a discard),
        # never at the lone PASS of the half-declared move.
        assert child.expanded or child.choices
        assert list(child.children) != [_PASS]
    assert agent._play(root, agent.player.name) in {a.to_engine() for a in legal}


def test_net_value_agent_has_equal_priors_and_the_net_value():
    torch = pytest.importorskip("torch")
    from riftbound.ai.handwritten import NetValueAgent
    from riftbound.ai.net import RiftboundNet
    torch.manual_seed(0)
    net = RiftboundNet().eval()
    d = pickle.load(open(POS, "rb"))
    gs = d["state"].clone()
    p = gs.get_player(d["side"])
    agent = NetValueAgent(p, net, rng=random.Random(0))
    loop = GameLoop(gs)
    legal = legal_actions(loop, DecisionPoint.TURN_ACTION, d["side"])
    priors, value = agent._evaluate(gs, d["side"], legal)
    assert len(priors) == len(legal)
    assert all(p == pytest.approx(1 / len(legal)) for p in priors.values())
    assert value == pytest.approx(agent._value_only(gs, d["side"]))
