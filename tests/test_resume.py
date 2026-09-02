"""Step 1 of the search-agent roadmap: the resumable engine.

`start()` is now `_setup()` + `_play_all_turns()`, and `resume_to_completion()`
continues a game from inside the active player's main action phase (where a
search agent's decision fires) to the end. Rollout/search agents run this on a
clone. The golden fixture (tests/test_golden_games.py) guards that the normal
`start()` path is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from riftbound.core.game_factory import build_game, make_agent
from riftbound.core.loop import GameLoop

REPO = Path(__file__).resolve().parent.parent
PYKE = REPO / "riftbound" / "data" / "decks" / "fury_chaos_pyke.json"
DIANA = REPO / "riftbound" / "data" / "decks" / "chaos_mind_diana.json"
AKALI = REPO / "riftbound" / "data" / "decks" / "vendetta_akali.json"
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"


def _public_sig(gs):
    return (
        gs.points_A, gs.points_B, gs.A.energy, gs.B.energy, gs.turn, gs.active,
        [c.name for c in gs.A.hand], [c.name for c in gs.B.hand],
        len(gs.A.deck.cards), len(gs.B.deck.cards),
        [[u.card.name for u in bf.units_A] for bf in gs.battlefields],
        [[u.card.name for u in bf.units_B] for bf in gs.battlefields],
    )


def test_start_still_produces_valid_result():
    gs = build_game(game_seed=7, deck_a_path=PYKE, deck_b_path=DIANA, ai_a="pyke", ai_b="diana")
    result = GameLoop(gs).start()
    assert result.winner in ("A", "B", "DRAW")
    assert result.turns >= 1


def test_resume_from_mid_turn_finishes_the_game():
    # Drive a real game up to the active player's main action phase...
    gs = build_game(game_seed=3, deck_a_path=AKALI, deck_b_path=KENNEN,
                    ai_a="simple_trade", ai_b="simple_trade")
    loop = GameLoop(gs)
    loop._setup()
    begin_result = loop._begin_turn()          # now inside turn 1's main phase
    assert begin_result is None                # no instant win in the beginning phase

    # ...clone at that mid-turn point and resume the CLONE to completion.
    clone = gs.clone()
    before = _public_sig(gs)
    clone.A.agent = make_agent("simple_trade", clone.A)
    clone.B.agent = make_agent("simple_trade", clone.B)
    result = GameLoop(clone).resume_to_completion()

    assert result.winner in ("A", "B", "DRAW")
    assert _public_sig(gs) == before           # the original state is untouched


def test_resume_is_deterministic():
    # Two clones from the same mid-turn point, resumed with same-seeded agents,
    # reach the same result — the property a search agent relies on.
    gs = build_game(game_seed=11, deck_a_path=AKALI, deck_b_path=KENNEN,
                    ai_a="simple_trade", ai_b="simple_trade")
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()

    def rollout():
        c = gs.clone()
        c.A.agent = make_agent("simple_trade", c.A)
        c.B.agent = make_agent("simple_trade", c.B)
        return GameLoop(c).resume_to_completion().winner

    assert rollout() == rollout()


def test_clone_preserves_session_state_fields():
    # Regression: clone must deep-copy the state added this session (empowered,
    # legend units, battlefield identity, burn counter) or search would be blind
    # to it. deepcopy handles this; lock it in.
    gs = build_game(game_seed=1, deck_a_path=AKALI, deck_b_path=KENNEN,
                    ai_a="simple_trade", ai_b="simple_trade")
    GameLoop(gs)._setup()  # creates legend units
    gs.legend_unit_A.empowered = True
    gs.cards_burned_this_turn["A"] = 3

    clone = gs.clone()
    assert clone.legend_unit_A is not None and clone.legend_unit_A is not gs.legend_unit_A
    assert clone.legend_unit_A.empowered is True
    assert clone.cards_burned_this_turn["A"] == 3
    assert all(bf.card is not None for bf in clone.battlefields)  # battlefield identities survive

    # Independence: flipping the clone doesn't touch the original.
    clone.legend_unit_A.empowered = False
    assert gs.legend_unit_A.empowered is True
