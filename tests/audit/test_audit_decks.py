"""Rules audit, third pass (docs/audit/AUDIT.md): the other eight decks read
card by card against the printed text
(riftbound/data/reference/piltover_archive.json) and played in the engine."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from riftbound.core.enums import Domain

from audit_helpers import act, card, choices, labels, legend, scripted, setup, unit

CARDS = Path(__file__).resolve().parents[2] / "riftbound" / "data" / "cards" / "all_cards.json"


def _names(options) -> list:
    return [getattr(getattr(o, "card", None), "name", None) for o in options]


def _pick(name: str):
    return lambda _loop, options: _names(options).index(name)


# -- D23. An ability with no [Action] is used in a showdown ----------------------

def test_a_gear_ability_with_no_action_is_not_used_in_a_showdown():
    """§151.2: 'The Activated Ability of Gear may be executed at any time during
    the controlling player's Main Phase during an Open State, and not during a
    Showdown.' Heart of Dark Ice: '[Tap]: Give a unit +3 [Might] this turn.'"""
    loop, a, b = setup(active="A")
    loop.gs.turn = 5
    loop.gs.battlefields[0].add_unit("B", unit("Defender", 2))
    a.base_units.append(unit("Mover", 3))
    for p in (a, b):
        p.base_gear.append(card("Heart of Dark Ice"))
    assert any("Heart of Dark Ice" in lbl for lbl in labels(loop, "A"))      # its Main Phase
    A, B = scripted(loop, a, b, A={"main": ["Move Mover base→BF0", "PASS"]})
    loop._run_main_actions()
    offered = A.offered("showdown_action") + B.offered("showdown_action")
    assert offered and not any("Heart of Dark Ice" in lbl for lbl in offered)


def test_an_ability_has_only_the_timing_its_card_prints():
    """§145.2, §151.2: an activated ability is used in a showdown or on a chain
    only with [Action] or [Reaction] ("Activate this any time" on older cards)."""
    wrong = []
    for c in json.loads(CARDS.read_text(encoding="utf-8")):
        text = re.sub(r"\([^)]*\)", "", (c.get("effect") or "").lower())     # no reminder text
        for e in c.get("effects") or []:
            timing = e.get("timing")
            if e.get("trigger") == "activated" and timing and "any time" not in text \
                    and not re.search(rf"\b{timing}\b", text):
                wrong.append((c["name"], timing))
    assert not wrong


# -- D24. QUICK-DRAW attaches only at the battlefield it is played "at" ----------

def test_quick_draw_attaches_to_a_unit_in_base():
    """§819.1.d: 'When you play this, attach it to a Unit you control.' Cloth
    Armor, the only unit of its player in base."""
    loop, a, b = setup(active="A")
    wearer = unit("Wearer", 2)
    a.base_units.append(wearer)
    a.hand.append(card("Cloth Armor"))
    act(loop, "A", "Play gear Cloth Armor")
    assert [g.name for g in wearer.gear] == ["Cloth Armor"] and not a.base_gear


def test_quick_draw_chooses_among_all_the_units_you_control():
    loop, a, b = setup(active="A")
    front, back = unit("Front", 2), unit("Back", 2)
    loop.gs.battlefields[0].add_unit("A", front)
    a.base_units.append(back)
    a.hand.append(card("Cloth Armor"))
    seen = choices(loop, {"equip": _pick("Back")})
    act(loop, "A", "Play gear Cloth Armor @BF0")
    assert [g.name for g in back.gear] == ["Cloth Armor"] and not front.gear
    assert [names for kind, _side, names in seen if kind == "equip"] == [["Front", "Back"]]


# -- D25. Bellows Breath (SFD-080; vendetta_ezreal) ------------------------------

@pytest.mark.xfail(strict=True, reason="AUDIT D25")
def test_bellows_breath_hits_units_at_the_same_location():
    """'Deal 1 to up to three units at the same location.'"""
    loop, a, b = setup(active="A", rich=())
    a.rune_energy = a.energy = 1
    a.add_power(Domain.MIND, 1)                  # no [Repeat]
    bf0, bf1 = loop.gs.battlefields
    here = [unit("Here 1", 3), unit("Here 2", 3)]
    there, home = unit("There", 3), unit("Home", 3)
    for u in here:
        bf0.add_unit("B", u)
    bf1.add_unit("B", there)
    b.base_units.append(home)
    a.hand.append(card("Bellows Breath"))
    choices(loop, {"target": lambda _loop, options: 0})      # the first unit offered, each time
    act(loop, "A", "Cast Bellows Breath")
    assert [u.damage for u in here] == [1, 1]
    assert (there.damage, home.damage) == (0, 0)


# -- D26. Ezreal Prodigal Explorer (SFD-199; vendetta_ezreal) --------------------

@pytest.mark.xfail(strict=True, reason="AUDIT D26")
def test_ezreal_legend_counts_an_enemy_gear_chosen():
    """'Use only if you've chosen enemy units and/or gear twice this turn with
    spells or unit abilities.' Stupefy on an enemy unit, Detonate on an enemy
    gear."""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Ezreal Prodigal Explorer")
    a.deck.cards[:] = [card("Stacked Deck") for _ in range(4)]
    b.deck.cards[:] = [card("Stacked Deck") for _ in range(4)]
    b.base_units.append(unit("Enemy", 5))
    b.base_gear.append(card("Seal of Focus"))
    a.hand += [card("Stupefy"), card("Detonate")]
    act(loop, "A", "Cast Stupefy")
    assert not any("Ezreal" in lbl for lbl in labels(loop, "A"))             # once
    act(loop, "A", "Cast Detonate")
    assert not b.base_gear
    assert any("Ezreal" in lbl for lbl in labels(loop, "A"))


# -- D27. Patched Porobot (VEN-058; vendetta_ornn) is a unit and a gear ----------

@pytest.mark.xfail(strict=True, reason="AUDIT D27 (open)")
def test_patched_porobot_is_a_gear_too():
    """Printed type 'Unit Gear'. §178.1: 'A Game Object that is more than one
    type has the properties of all of their types'. Pit Crew: 'When you play a
    gear, ready me.'"""
    loop, a, b = setup(active="A")
    crew = unit("Pit Crew", ready=False)
    a.base_units.append(crew)
    a.hand.append(card("Patched Porobot"))
    act(loop, "A", "Play Patched Porobot")
    assert crew.ready


@pytest.mark.xfail(strict=True, reason="AUDIT D27 (open)")
def test_patched_porobot_is_killed_as_a_gear():
    """§178.3: 'A unit that is also a gear can be targeted by spells and
    abilities ... that say "Kill a unit," or "Kill a gear."' Detonate: 'Kill a
    gear. Its controller draws 2.'"""
    loop, a, b = setup(active="A")
    b.deck.cards[:] = [card("Stacked Deck") for _ in range(4)]
    b.base_units.append(unit("Patched Porobot"))
    a.hand.append(card("Detonate"))
    act(loop, "A", "Cast Detonate")
    assert not b.base_units and len(b.hand) == 2


# -- D28. "a unit" read as "a friendly unit" (Rengar and Kennen's legends) -------

@pytest.mark.xfail(strict=True, reason="AUDIT D28")
def test_rengar_legend_can_choose_an_enemy_unit():
    """Rengar Pridestalker (UNL-183): 'When you play a unit, give a unit +1
    [Might] this turn.'"""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Rengar Pridestalker")
    enemy = unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.hand.append(card("Pakaa Cub"))
    choices(loop, {"target": _pick("Enemy")})
    act(loop, "A", "Play Pakaa Cub")
    assert enemy.might == 3


@pytest.mark.xfail(strict=True, reason="AUDIT D28")
def test_kennen_legend_can_choose_an_enemy_unit():
    """Kennen Heart of the Tempest (VEN-155): '[Action] Disempower me, [Tap]:
    Give a unit [Assault 2] this turn.'"""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Kennen Heart of the Tempest").empowered = True
    enemy = unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.base_units.append(unit("Friend", 2))
    choices(loop, {"target": _pick("Enemy")})
    act(loop, "A", "Activate give_temporary_assault")
    assert any(k.startswith("ASSAULT") for k in enemy.turn_keywords)
