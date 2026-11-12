"""Rules audit, priority 3 (docs/audit/AUDIT.md): cards of the other eight decks
whose data differs from the printed card
(riftbound/data/reference/piltover_archive.json; BACKLOG.md O1)."""

from __future__ import annotations

import pytest

from riftbound.core.enums import Domain

from audit_helpers import act, card, choices, labels, scripted, setup, unit


# -- D13. Stupefy (OGN-095) -------------------

def test_stupefy_gives_minus_one():
    """'Give a unit -1 [Might] this turn, to a minimum of 1 [Might]. Draw 1.'"""
    loop, a, b = setup(active="A")
    big = unit("Big", 3)
    loop.gs.battlefields[0].add_unit("B", big)
    a.hand.append(card("Stupefy"))
    choices(loop, {"target": lambda l, o: next(i for i, u in enumerate(o) if u is big)})
    act(loop, "A", "Cast Stupefy @BF0")
    assert big.might == 2


# -- D14. Noxus Hopeful (OGN-012) --------------

def test_noxus_hopeful_has_four_might():
    loop, a, b = setup(active="A")
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", unit("Noxus Hopeful"))
    bf0.add_unit("B", unit("Wall", 4))
    loop._phase_combat_and_conquer_single(0, "A")
    assert not bf0.units_B                       # 4 damage kills a 4 [might] unit


# -- D15. Thrill of the Hunt (UNL-184) --------------------------

def test_thrill_of_the_hunt_costs_one_power():
    loop, a, b = setup(active="A", rich=())
    a.rune_energy = 2
    a.add_power(Domain.FURY, 1)
    a.base_units.append(unit("Friend", 2))
    a.hand.append(card("Thrill of the Hunt"))
    assert any("Thrill of the Hunt" in lbl for lbl in labels(loop, "A"))


# -- D16. Pit Crew (OGN-091) --------------------------------------

def test_pit_crew_readies_when_you_play_a_gear():
    loop, a, b = setup(active="A")
    crew = unit("Pit Crew", ready=False)
    a.base_units.append(crew)
    a.hand += [card("Punching Poro"), card("Hand Hammer")]
    act(loop, "A", "Play Punching Poro")
    assert not crew.ready                        # a unit is not a gear
    act(loop, "A", "Play gear Hand Hammer")
    assert crew.ready


# -- D17. The Harrowing (OGN-198) -------------------------------

def test_the_harrowing_plays_a_unit_from_your_trash():
    loop, a, b = setup(active="A", rich=())
    a.rune_energy = 6
    a.add_power(Domain.CHAOS, 2)                 # The Harrowing: [6] and two Chaos
    back = card("Shadow Assassin")               # [5], no Power cost
    a.trash.append(back)
    a.hand.append(card("The Harrowing"))
    act(loop, "A", "Cast The Harrowing")
    assert [u.card for u in a.base_units + loop.gs.battlefields[0].units_A] == [back]
    assert a.energy == 0 and not any(c is back for c in a.trash)


def test_the_harrowing_needs_a_unit_in_the_trash_and_its_power_cost():
    """§355.8: no unit in the trash, no play. "(You must still pay its Power
    cost.)": Zed From the Shadows ([4] and one Fury) comes back for the Fury."""
    loop, a, b = setup(active="A", rich=())
    a.rune_energy = 6
    a.add_power(Domain.CHAOS, 2)
    a.hand.append(card("The Harrowing"))
    assert not any("The Harrowing" in lbl for lbl in labels(loop, "A"))
    back = card("Zed From the Shadows")
    a.trash.append(back)
    a.add_power(Domain.FURY, 1)
    choices(loop, {"optional:additional_cost": lambda l, o: o.index(False)})
    act(loop, "A", "Cast The Harrowing")
    assert [u.card for u in a.base_units] == [back] and a.power_pool.get(Domain.FURY, 0) == 0


# -- D18. Existential Dread (UNL-134) --------------------------

def test_existential_dread_chooses_an_attacking_enemy_unit():
    """The attacker has no attacking enemy unit to choose: it can't play it
    (§355.8); the defender can."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("B", unit("Defender", 2))
    a.base_units.append(unit("Mover", 2))
    a.hand.append(card("Existential Dread"))
    b.hand.append(card("Existential Dread"))
    A, B = scripted(loop, a, b, A={"main": ["Move Mover base→BF0", "PASS"]})
    loop._run_main_actions()
    assert any("Existential Dread" in lbl for lbl in B.offered("showdown_action"))
    assert not any("Existential Dread" in lbl for lbl in A.offered("showdown_action"))


# -- D21. Moonfall (UNL-198) -----------------------------------

def test_moonfall_chooses_a_battlefield_where_its_player_has_units():
    """'Choose a battlefield where you have units. You may move up to one enemy
    unit to that battlefield. Then give enemy units there -2 [Might] this
    turn.' With units at one battlefield only, that is the one it is played at."""
    loop, a, b = setup(active="A")
    bf0, bf1 = loop.gs.battlefields
    mine, home = unit("Mine", 3), unit("Home", 3)
    bf1.add_unit("A", mine)
    b.base_units.append(home)
    a.hand.append(card("Moonfall"))
    assert [lbl for lbl in labels(loop, "A") if "Moonfall" in lbl] == ["Cast Moonfall @BF1"]
    act(loop, "A", "Cast Moonfall @BF1")
    # Moved there with -2: it contests the battlefield and loses the combat.
    assert home.might == 1 and home.card in b.trash and bf1.units_A == [mine]


def test_moonfall_cannot_be_played_with_no_units_at_a_battlefield():
    loop, a, b = setup(active="A")
    a.base_units.append(unit("AtHome", 3))
    b.base_units.append(unit("Home", 3))
    a.hand.append(card("Moonfall"))
    assert not [lbl for lbl in labels(loop, "A") if "Moonfall" in lbl]
