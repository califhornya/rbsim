"""A card has only the keywords it prints: not one its abilities mention ("give
me ASSAULT 4", "Your Mechs have SHIELD", "EMPOWERED[>] I have GANKING",
"[tap]: REACTION - ADD"). Conditional and counted keywords come from passives:
"If you've gained XP this turn, I have GANKING", "ASSAULT equal to the number
of gear you control", "Your Equipment each give ASSAULT"."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, _printed_keyword_heads


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _kw(name):
    return set(CARD_REGISTRY[name].keywords)


def test_keywords_an_ability_mentions_are_not_the_cards_own():
    assert "TEMPORARY" not in _kw("Sprite Mother")          # its token has it
    assert "ACTION" not in _kw("Jarvan IV Martial Paragon")  # its gear get it
    assert "ASSAULT" not in _kw("Captain Farron")            # other units get it
    assert "HIDDEN" not in _kw("Noxus Saboteur")
    assert not _kw("Shadow Clone")                          # "give me ASSAULT 4"
    assert "GANKING" not in _kw("Brutal Hunter")            # EMPOWERED[>] header


def test_printed_keywords_are_kept():
    assert {"ASSAULT 2", "SHIELD 2"} <= _kw("Garen Rugged")
    assert {"QUICK-DRAW", "TEMPORARY"} <= _kw("Spinning Axe")
    assert "TANK" in _kw("Protector's Shield")              # its Equipment text
    assert "FLOW" in _kw("Dragon Form")                     # "... this turn. FLOW [3]"
    assert {"SHIELD", "PREDICT 1"} <= _kw("Jeweled Colossus")  # after VISION's reminder


def test_printed_keyword_reading():
    assert _printed_keyword_heads("SHIELD 3 (+3) TANK (first.) When an opponent moves") == {"SHIELD", "TANK"}
    assert _printed_keyword_heads("If you've discarded, I have ASSAULT and GANKING.") == set()
    assert _printed_keyword_heads("[tap]: REACTION - ADD [rune].") == set()
    assert _printed_keyword_heads("LEVEL 6[>] I have +1 [might].") == set()


def test_wily_newtfish_ganks_after_gaining_xp():
    loop = _loop()
    newt = UnitInPlay(card=CARD_REGISTRY["Wily Newtfish"].instantiate())
    loop.gs.battlefields[0].add_unit("A", newt)
    loop._recompute_passives()
    assert not newt.has_keyword("GANKING")
    loop.gs.add_xp("A", 1)
    loop._recompute_passives()
    assert newt.has_keyword("GANKING") and newt.might == int(newt.card.might) + 1


def test_repair_specialist_has_assault_per_gear():
    loop = _loop()
    spec = UnitInPlay(card=CARD_REGISTRY["Repair Specialist"].instantiate())
    loop.gs.battlefields[0].add_unit("A", spec)
    loop.gs.A.base_gear = [GearCard(name="G1"), GearCard(name="G2")]
    loop._recompute_passives()
    assert spec.keyword_value("ASSAULT") == 2


def test_lucian_purifier_equipment_each_give_assault():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=CARD_REGISTRY["Lucian Purifier"].instantiate())
    unit = UnitInPlay(card=UnitCard(name="Hero", might=3))
    unit.gear = [CARD_REGISTRY["Long Sword"].instantiate(), CARD_REGISTRY["Boneshiver"].instantiate()]
    bare = UnitInPlay(card=UnitCard(name="Bare", might=3))
    loop.gs.battlefields[1].add_unit("A", unit)
    loop.gs.A.base_units.append(bare)
    loop._recompute_passives()
    assert unit.keyword_value("ASSAULT") == 2 and bare.keyword_value("ASSAULT") == 0


def test_rumble_gives_mechs_everywhere_assault():
    loop = _loop()
    loop.gs.A.base_units.append(UnitInPlay(card=CARD_REGISTRY["Rumble Hotheaded"].instantiate()))
    mech = UnitInPlay(card=UnitCard(name="Mech", might=2, tags=["Mech"]))
    other = UnitInPlay(card=UnitCard(name="Yordle", might=2))
    loop.gs.battlefields[1].add_unit("A", mech)
    loop.gs.battlefields[1].add_unit("A", other)
    loop._recompute_passives()
    assert mech.has_keyword("ASSAULT") and not other.has_keyword("ASSAULT")
