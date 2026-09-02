"""Step 2: the no-heuristics search agents (RandomAgent, MonteCarloAgent).

These are kept fast (tiny K / candidate caps) — the full "mc beats simple_trade"
validation is a slow head-to-head run, not a unit test. Here we assert the agents
are wired correctly, produce sound actions, and drive a game to completion.
"""

from __future__ import annotations

import random
from pathlib import Path

from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.ai.search.monte_carlo_agent import MonteCarloAgent
from riftbound.ai.search.random_agent import RandomAgent
from riftbound.core.decisions import DecisionPoint
from riftbound.core.game_factory import AI_REGISTRY, build_game
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop

REPO = Path(__file__).resolve().parent.parent
AKALI = REPO / "riftbound" / "data" / "decks" / "vendetta_akali.json"
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"


def test_agents_registered():
    assert AI_REGISTRY["random"] is RandomAgent
    assert AI_REGISTRY["mc"] is MonteCarloAgent


def test_random_agent_action_is_legal():
    gs = build_game(game_seed=1, deck_a_path=AKALI, deck_b_path=KENNEN, ai_a=None, ai_b=None)
    gs.A.agent = RandomAgent(gs.A, rng=random.Random(0))
    loop = GameLoop(gs)          # injects loop/gs into the agent
    loop._setup()
    loop._begin_turn()           # give the active player a hand + energy
    act = gs.A.agent.decide_action(gs.B)
    legal = {a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")}
    assert act in legal


def test_mc_agent_drives_a_game_to_completion():
    # Tiny budget so the test is fast; correctness of *strength* is validated
    # separately in a head-to-head run, not here.
    gs = build_game(game_seed=2, deck_a_path=AKALI, deck_b_path=KENNEN, ai_a=None, ai_b=None)
    gs.A.agent = MonteCarloAgent(gs.A, k=1, max_candidates=2, rollout="simple_trade",
                                 rng=random.Random(0))
    gs.B.agent = SimpleTradeAgent(gs.B)
    result = GameLoop(gs).start()
    assert result.winner in ("A", "B", "DRAW")
    assert result.turns >= 1


def test_mc_makes_at_least_one_non_pass_play():
    # Regression against the noisy-tie stall (mc must develop its board, not just
    # PASS every turn to the cap).
    gs = build_game(game_seed=5, deck_a_path=AKALI, deck_b_path=KENNEN, ai_a=None, ai_b=None)
    mc = MonteCarloAgent(gs.A, k=2, max_candidates=4, rollout="simple_trade", rng=random.Random(1))
    gs.A.agent = mc
    gs.B.agent = SimpleTradeAgent(gs.B)

    plays = {"n": 0}
    orig = mc.decide_action
    def counting(opponent, cards_played=0):
        act = orig(opponent, cards_played)
        if act[0] != "PASS":
            plays["n"] += 1
        return act
    mc.decide_action = counting
    GameLoop(gs).start()
    assert plays["n"] >= 1
