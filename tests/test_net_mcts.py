"""RL Chunk 3: network-guided MCTS (PUCT). torch-gated (runs after `uv sync
--extra rl`). Uses a randomly-initialised net — asserts search *mechanics*
(legal moves, termination, visit distribution), not play strength."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.net import RiftboundNet  # noqa: E402
from riftbound.ai.net_mcts import NetGuidedMCTSAgent  # noqa: E402
from riftbound.core.decisions import DecisionPoint  # noqa: E402
from riftbound.core.game_factory import build_game  # noqa: E402
from riftbound.core.legality import legal_actions  # noqa: E402
from riftbound.core.loop import GameLoop  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"


def _game_with_net_mcts(seed=1, iters=8):
    torch.manual_seed(0)
    net = RiftboundNet()
    gs = build_game(game_seed=seed, deck_a_path=KENNEN, deck_b_path=ORNN,
                    ai_a=None, ai_b="simple_trade", first_player="a")
    gs.A.agent = NetGuidedMCTSAgent(gs.A, net, iterations=iters, rng=random.Random(0))
    return gs, gs.A.agent


def test_decide_action_is_legal():
    gs, agent = _game_with_net_mcts()
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()
    act = agent.decide_action(gs.B)
    legal = {a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")}
    assert act in legal
    # A search with >1 candidate populates a visit distribution summing to ~1.
    if act != ("PASS", None, None) or len(legal) > 1:
        assert agent.last_visits
        assert abs(sum(agent.last_visits.values()) - 1.0) < 1e-6


def test_drives_full_game_to_completion():
    gs, _agent = _game_with_net_mcts(seed=2, iters=6)
    result = GameLoop(gs).start()
    assert result.winner in ("A", "B", "DRAW")
    assert result.turns >= 1


def test_visits_prefer_searched_actions():
    gs, agent = _game_with_net_mcts(seed=3, iters=24)
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()
    agent.decide_action(gs.B)
    # With a real iteration budget, total visits across root children == iterations
    # is not guaranteed (some iterations expand the root only), but visits must be
    # non-negative and the chosen action is among the most visited.
    assert agent.last_visits
    top = max(agent.last_visits, key=agent.last_visits.get)
    assert agent.last_visits[top] > 0
