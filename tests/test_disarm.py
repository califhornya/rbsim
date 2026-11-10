"""DISARM X (Core Rules §831): when this unit attacks, give an enemy unit here -X
Might this turn. A bare DISARM is 1; instances add up."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CardSpec


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def test_disarm_value_bare_valued_and_granted():
    bare = UnitInPlay(UnitCard(name="Ahri", keywords=["DISARM"]))
    two = UnitInPlay(UnitCard(name="Chronomancer", keywords=["DISARM 2"]))
    granted = UnitInPlay(UnitCard(name="Mech", keywords=["DISARM"]))
    granted.passive_keywords.append("DISARM")
    assert GameLoop._disarm_value(bare) == 1
    assert GameLoop._disarm_value(two) == 2
    assert GameLoop._disarm_value(granted) == 2          # printed + granted add up
    assert GameLoop._disarm_value(UnitInPlay(UnitCard(name="Plain"))) == 0


def test_disarm_hits_strongest_enemy_this_turn():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    attacker = UnitInPlay(UnitCard(name="Disposal Expert", might=1, keywords=["DISARM 2"]))
    weak = UnitInPlay(UnitCard(name="Weak", might=1))
    strong = UnitInPlay(UnitCard(name="Strong", might=5))
    bf.add_unit("A", attacker)
    bf.add_unit("B", weak)
    bf.add_unit("B", strong)

    loop._apply_disarm(attacker, bf, "B")

    assert strong.might == 3 and weak.might == 1
    assert strong.temporary_might == -2                  # "this turn"


def test_disarm_swings_combat():
    # 3-Might attacker with DISARM 2 vs a 4-Might defender: the defender fights at
    # 2, so the attacker survives and conquers.
    loop = _loop()
    bf = loop.gs.battlefields[0]
    attacker = UnitInPlay(UnitCard(name="Siren", might=3, keywords=["DISARM 2"]))
    bf.add_unit("A", attacker)
    bf.add_unit("B", UnitInPlay(UnitCard(name="Defender", might=4)))
    bf.last_controller = "B"
    bf.contested_this_turn = True

    loop._phase_combat_and_conquer_single(0, "A")   # showdown combat (attack triggers)

    assert bf.controller() == "A"
    assert attacker in bf.units_A


def test_disarm_keyword_value_parsed_from_text():
    spec = CardSpec.from_dict({
        "name": "Test Disarm Two", "category": "Unit", "might": 2,
        "effect": "DISARM 2 (When I attack, give an enemy unit here -2 [Might] this turn.)"})
    assert "DISARM 2" in spec.keywords
