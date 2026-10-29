"""simple_trade used an activated ability whose condition failed (Ezreal
Prodigal Explorer's "use only if you've chosen enemy units and/or gear twice
this turn"): a no-op that ended its turn, so the Ezreal precon never played a
card (0 wins in 100). It now picks only abilities the engine lets it use."""

from __future__ import annotations

from pathlib import Path

from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop

DECKS = Path(__file__).resolve().parents[1] / "riftbound" / "data" / "decks"


def test_ezreal_uses_only_usable_abilities_and_plays_cards():
    gs = build_game(game_seed=3, deck_a_path=DECKS / "vendetta_ezreal.json",
                    deck_b_path=DECKS / "vendetta_kennen.json", ai_a=None, ai_b=None)
    agent = SimpleTradeAgent(gs.A)
    gs.A.agent, gs.B.agent = agent, SimpleTradeAgent(gs.B)
    loop = GameLoop(gs)
    bad, played = [], []
    find, decide = agent._find_activated_ability, agent.decide_action

    def checked_find(side):
        act = find(side)
        if act is not None and not loop._ability_usable(gs.A, loop.activatable_abilities(side)[act[2]]):
            bad.append(act)
        return act

    def noted_decide(opponent, cards_played=0):
        act = decide(opponent, cards_played)
        played.append(act[0])
        return act
    agent._find_activated_ability, agent.decide_action = checked_find, noted_decide
    loop.start()
    assert not bad
    assert {"UNIT", "SPELL", "GEAR", "CHAMPION"} & set(played)
