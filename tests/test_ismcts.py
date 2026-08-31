"""Step 3: ISMCTS search agent. Kept fast (tiny iteration budget); the full
"ismcts beats simple_trade / mc" validation is a slow head-to-head run."""

from __future__ import annotations

import random
from pathlib import Path

from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.ai.search.ismcts_agent import ISMCTSAgent
from riftbound.core.decisions import DecisionPoint
from riftbound.core.game_factory import AI_REGISTRY, build_game
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop

REPO = Path(__file__).resolve().parent.parent
AKALI = REPO / "riftbound" / "data" / "decks" / "vendetta_akali.json"
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"


def test_registered():
    assert AI_REGISTRY["ismcts"] is ISMCTSAgent


def test_ismcts_action_is_legal_and_drives_game():
    gs = build_game(game_seed=2, deck_a_path=AKALI, deck_b_path=KENNEN, ai_a=None, ai_b=None)
    gs.A.agent = ISMCTSAgent(gs.A, iterations=8, k_mulligan=0, rollout="simple_trade",
                             rng=random.Random(0))
    gs.B.agent = SimpleTradeAgent(gs.B)
    result = GameLoop(gs).start()
    assert result.winner in ("A", "B", "DRAW")
    assert result.turns >= 1


def test_ismcts_decision_is_a_legal_action():
    gs = build_game(game_seed=1, deck_a_path=AKALI, deck_b_path=KENNEN, ai_a=None, ai_b=None)
    agent = ISMCTSAgent(gs.A, iterations=8, k_mulligan=0, rollout="simple_trade", rng=random.Random(0))
    gs.A.agent = agent
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()
    act = agent.decide_action(gs.B)
    legal = {a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")}
    assert act in legal
