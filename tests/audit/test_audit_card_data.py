"""Rules audit, priority 3 (docs/audit/AUDIT.md): cards of the other eight decks
whose data differs from the printed card
(riftbound/data/reference/piltover_archive.json; BACKLOG.md O1)."""

from __future__ import annotations

import pytest

from riftbound.core.enums import Domain

from audit_helpers import act, card, choices, labels, scripted, setup, unit


# -- D13. Stupefy (OGN-095; chaos_mind_diana, vendetta_ezreal) -------------------

def test_stupefy_gives_minus_one():
    """'Give a unit -1 [Might] this turn, to a minimum of 1 [Might]. Draw 1.'"""
    loop, a, b = setup(active="A")
    big = unit("Big", 3)
    loop.gs.battlefields[0].add_unit("B", big)
    a.hand.append(card("Stupefy"))
    choices(loop, {"target": lambda l, o: next(i for i, u in enumerate(o) if u is big)})
    act(loop, "A", "Cast Stupefy @BF0")
    assert big.might == 2


# -- D14. Noxus Hopeful (OGN-012; fury_chaos_pyke, vendetta_rengar) --------------

def test_noxus_hopeful_has_four_might():
    loop, a, b = setup(active="A")
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", unit("Noxus Hopeful"))
    bf0.add_unit("B", unit("Wall", 4))
    loop._phase_combat_and_conquer_single(0, "A")
    assert not bf0.units_B                       # 4 damage kills a 4 [might] unit


# -- D15. Thrill of the Hunt (UNL-184; vendetta_rengar) --------------------------

def test_thrill_of_the_hunt_costs_one_power():
    loop, a, b = setup(active="A", rich=())
    a.rune_energy = 2
    a.add_power(Domain.FURY, 1)
    a.base_units.append(unit("Friend", 2))
    a.hand.append(card("Thrill of the Hunt"))
    assert any("Thrill of the Hunt" in lbl for lbl in labels(loop, "A"))


# -- D16. Pit Crew (OGN-091; vendetta_ornn) --------------------------------------

@pytest.mark.xfail(strict=True, reason="Pit Crew OGN-091: printed 'When you play a gear, ready me.', "
                                       "encoded with no text and no effect")
def test_pit_crew_readies_when_you_play_a_gear():
    loop, a, b = setup(active="A")
    crew = unit("Pit Crew", ready=False)
    a.base_units.append(crew)
    a.hand.append(card("Hand Hammer"))
    act(loop, "A", "Play gear Hand Hammer")
    assert crew.ready


# -- D17. The Harrowing (OGN-198; vendetta_kennen) -------------------------------

@pytest.mark.xfail(strict=True, reason="The Harrowing OGN-198: printed 'Play a unit from your trash, "
                                       "ignoring its Energy cost.', encoded with no text and no effect")
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


# -- D18. Existential Dread (UNL-134; chaos_mind_diana) --------------------------

@pytest.mark.xfail(strict=True, reason="Existential Dread UNL-134: printed '[Stun] an attacking enemy "
                                       "unit', encoded as any attacking unit (the attacker's own too)")
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
