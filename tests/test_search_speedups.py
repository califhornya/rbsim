"""Search speed-ups that must not change a move (20/11).

- `_iterate` reuses the root's menu at the first step of every simulation
  instead of rebuilding it in each determinized world: the player's own
  options must not depend on what is hidden from them. Checked here on every
  deck, at every main-turn decision of a random game, against 3 worlds.
- `legal_actions` during a declared move builds only PASS and the moves that
  can join it (legality._move_actions).

Also checked when they were made: 12 hand-bot games (6 deck pairs, 40
iterations) identical move by move, visits and Q included, before and after
(CPU 122.5 s -> 105.6 s)."""
import random
from pathlib import Path

import pytest

from riftbound.core.decisions import DecisionPoint
from riftbound.core.game_factory import build_game, make_agent
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.state import determinize

DECKS = sorted((Path(__file__).resolve().parents[1] / "riftbound/data/decks").glob("*.json"))


@pytest.mark.parametrize("deck", DECKS, ids=lambda p: p.stem)
def test_own_menu_is_the_same_in_every_world(deck):
    other = DECKS[(DECKS.index(deck) + 1) % len(DECKS)]
    gs = build_game(game_seed=77, deck_a_path=deck, deck_b_path=other, ai_a=None, ai_b=None, max_turns=12)
    checked, mismatches = 0, []
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        p.agent = make_agent("random", p)
        p.agent.rng = random.Random(seat == "B")
        decide = p.agent.decide_action

        def check(opponent, cards_played=0, _p=p, _decide=decide):
            nonlocal checked
            loop = _p.agent.loop
            real = [a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, _p.name)]
            for w in range(3):
                clone = loop.gs.clone()
                clone.rng = random.Random(w)
                determinize(clone, observer=_p.name, rng=clone.rng)
                seen = [a.to_engine() for a in
                        legal_actions(GameLoop(clone), DecisionPoint.TURN_ACTION, _p.name)]
                if seen != real:
                    mismatches.append((loop.gs.turn, real, seen))
            checked += 1
            return _decide(opponent, cards_played)
        p.agent.decide_action = check
    GameLoop(gs).start()
    assert checked > 5
    assert not mismatches, mismatches[:2]
