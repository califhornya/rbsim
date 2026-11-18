"""Three faults of the search found in the user's scenarios (18/11,
docs/bot/BOT_SCENARI.md), one test each, and the scenario that showed them."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

from riftbound.ai.net_mcts import NetGuidedMCTSAgent, _Node
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.game_factory import build_game

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "diag"))


def test_lasting_might_drops_what_ends_with_the_turn():
    """A "+5 this turn" (Punch First) is not a gain once the turn is over:
    lasting_might is the Might after clear_turn_end_bonuses."""
    u = UnitInPlay(UnitCard(name="X", might=3))
    u.might_counters = 1                       # a buff stays
    u.temporary_might, u.combat_might, u.bonus_might = 5, 2, 1
    u.base_might_override = 7                  # Switcheroo-like, this turn
    assert u.might == 7 + 5 + 2 + 1 + 1
    assert u.lasting_might == 3 + 1
    u.clear_turn_end_bonuses()
    u.clear_combat_bonuses()
    u.bonus_might = 0
    assert u.might == u.lasting_might == 4


def test_the_value_ignores_a_pump_with_nothing_to_fight():
    from handwritten_value import table_value
    from riftbound.core.decisions import Observation
    gs = build_game(game_seed=1, deck_a_path=ROOT / "riftbound/data/decks/competitive_evelynn.json",
                    deck_b_path=ROOT / "riftbound/data/decks/competitive_khazix.json",
                    ai_a=None, ai_b=None)
    gs.A.base_units.append(UnitInPlay(UnitCard(name="X", might=2)))
    before = table_value(Observation.from_state(gs, "A"))
    gs.A.base_units[-1].temporary_might = 5
    assert table_value(Observation.from_state(gs, "A")) == before


def test_an_untried_move_is_worth_what_the_position_is_worth():
    """20 moves with equal priors, the one tried worth +0.9: with an untried
    move worth 0 it was never challenged (the bot passed while ahead, S9)."""
    keys = [("M", i, None) for i in range(20)]
    node = _Node()
    node.N, node.Q = 10, 0.9
    node.P = {k: 1 / 20 for k in keys}
    node.children = {k: _Node() for k in keys}
    node.children[keys[0]].N, node.children[keys[0]].Q = 10, 0.9
    pick = NetGuidedMCTSAgent._puct_select(SimpleNamespace(c_puct=1.5), node, keys)
    assert pick != keys[0]
    assert math.isclose(node.Q, 0.9)


def test_a_reaction_searches_as_much_as_a_turn_action():
    gs = build_game(game_seed=1, deck_a_path=ROOT / "riftbound/data/decks/competitive_evelynn.json",
                    deck_b_path=ROOT / "riftbound/data/decks/competitive_khazix.json",
                    ai_a=None, ai_b=None)
    assert NetGuidedMCTSAgent(gs.A, None, iterations=100).reaction_iterations == 100


def test_s11a_the_bot_returns_the_kingpin_and_pyke_lives():
    """S11a (G3 turn 7): Rampage on the chain, Kingpin against Pyke. The bot
    flips the Stranger, draws Star-Crossed and returns the Kingpin (with a
    quarter of the iterations it returned First Mate, the first option, and
    Pyke died)."""
    from scenari_bot import run
    after = run("S11a", 100, 0)["after"]
    assert "Pyke Returned (4) esausta" in after["me"]["Packed Amphitheater"]
    assert not any(u.startswith("Sett Kingpin") for u in after["opp"]["Rakelstake"])
