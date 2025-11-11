import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player
from riftbound.core.state import GameState


def make_game() -> GameState:
    rng = random.Random(0)
    player_a = Player(name="A", deck=Deck([]))
    player_b = Player(name="B", deck=Deck([]))
    gs = GameState(rng=rng, A=player_a, B=player_b)
    gs.battlefields = [Battlefield(), Battlefield()]
    return gs


def test_hold_scoring_awards_vp():
    gs = make_game()
    bf = gs.battlefields[0]
    bf.add_unit("A", UnitInPlay(UnitCard(name="Sentinel", might=2)))

    loop = GameLoop(gs)
    gained = loop._phase_beginning("A")

    assert gained == 1
    assert gs.battlefields[0].scored_this_turn_A is True


def test_conquer_scoring_triggers_after_combat():
    gs = make_game()
    bf = gs.battlefields[0]
    bf.add_unit("A", UnitInPlay(UnitCard(name="Vanguard", might=2)))
    bf.add_unit("B", UnitInPlay(UnitCard(name="Grunt", might=1)))
    bf.last_controller = "B"
    bf.contested_this_turn = True

    loop = GameLoop(gs)
    gs.points_A = 0
    gs.points_B = 0

    loop._phase_combat_and_conquer("A")

    assert gs.points_A == 1
    assert bf.controller() == "A"