"""Rules audit, the two competitive decks (docs/audit/AUDIT.md, fifth pass):
competitive_kaisa and competitive_kennen, given by the owner on 2026-11-12.
Their cards new to the audit, read against the printed text
(riftbound/data/reference/piltover_archive.json) and played in the engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import load_deck_json

from audit_helpers import act, card, choices, hide, labels, legend, setup, unit

DECKS = Path(__file__).resolve().parents[2] / "riftbound" / "data" / "decks"


@pytest.mark.parametrize("name", ["competitive_kaisa", "competitive_kennen"])
def test_the_deck_is_the_list_given(name):
    """40 cards with the Chosen Champion, 12 runes, 3 battlefields, 10 in the
    sideboard; every name is a card of the corpus (load_deck_json checks)."""
    cards, runes, champion, legend_spec, battlefields = load_deck_json(DECKS / f"{name}.json")
    data = json.loads((DECKS / f"{name}.json").read_text(encoding="utf-8"))
    assert sum(c["count"] for c in data["cards"]) + 1 == 40 and champion is not None
    assert sum(r["count"] for r in data["runes"]) == 12 and len(battlefields) == 3
    assert sum(c["count"] for c in data["sideboard"]) == 10 and legend_spec is not None


# -- D50. A HIDDEN gear played from face down goes nowhere -------------------------

def test_edge_of_night_played_from_face_down_attaches_to_a_unit_here():
    """Edge of Night (errata): '[Hidden] When you play this from face down,
    attach it to a unit you control (here).' §737.1: a hidden card is played
    for [0]; a gear is played as a gear. It used to vanish."""
    loop, a, b = setup(active="A")
    here, there = unit("here", 2), unit("there", 3)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    a.base_units.append(unit("home", 4))
    hide(loop, "A", 0, "Edge of Night")
    seen = choices(loop, {})
    act(loop, "A", "Play Edge of Night from Hidden @BF0")
    assert [g.name for g in here.gear] == ["Edge of Night"] and here.might == 4
    assert [opts for kind, _s, opts in seen if kind == "target:attach_gear"] == [["here"]]


def test_zhonyas_hourglass_played_from_face_down_goes_to_base():
    """Zhonya's Hourglass: '[Hidden] If a friendly unit would die, kill this
    instead.' Played from face down it is a gear in its player's base."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("here", 2))
    hide(loop, "A", 0, "Zhonya's Hourglass")
    act(loop, "A", "Play Zhonya's Hourglass from Hidden @BF0")
    assert [g.name for g in a.base_gear] == ["Zhonya's Hourglass"]


# -- D51. A Standard Move doesn't fire "when I become exhausted" -------------------

def test_a_standard_move_fires_when_i_become_exhausted():
    """Reckless Innovator: 'When I become exhausted choose one - Play a Gold
    gear token exhausted. - Pay [Chaos] to draw 1.' §144.2: exhausting the unit
    is the cost of a Standard Move. The unit had left its location as it was
    exhausted, so its controller wasn't found and nothing fired."""
    loop, a, b = setup(active="A")
    innovator = unit("Reckless Innovator")
    a.base_units.append(innovator)
    seen = choices(loop, {"mode": lambda _l, options: 0})
    act(loop, "A", "Move Reckless Innovator base→BF0")
    assert [k for k, _s, _o in seen if k.startswith("mode")]
    assert [(g.name, g.tapped) for g in a.base_gear] == [("Gold", True)]


# -- D52. Decree of Unity is cast with no enemy Chaos unit or gear -----------------

def test_decree_of_unity_needs_an_enemy_chaos_unit_or_gear():
    """Decree of Unity: 'Kill an enemy Chaos unit or gear.' §355.8: valid
    choices must be made for all targets to put a spell on the chain."""
    loop, a, b = setup(active="A")
    a.base_units.append(unit("Reckless Innovator"))          # Chaos, but friendly
    b.base_units.append(unit("plain", 2))
    a.hand.append(card("Decree of Unity"))
    assert not [lb for lb in labels(loop, "A") if "Decree of Unity" in lb]
    b.base_units.append(unit("Reckless Innovator"))
    act(loop, "A", "Cast Decree of Unity")
    assert [u.card.name for u in b.base_units] == ["plain"]


# -- Read, played and found right --------------------------------------------------

def test_kaisa_legend_adds_power_only_for_spells():
    """Kai'Sa, Daughter of the Void: '[Tap]: [Reaction] - [Add] [Rune]. Use
    only to play spells.'"""
    loop, a, b = setup(active="A", rich=())
    legend(loop, "A", "Kai'Sa Daughter of the Void")
    a.energy = 2
    a.hand.append(card("Hextech Ray"))
    a.hand.append(card("Bedeviling Stranger"))
    loop.gs.battlefields[0].add_unit("B", unit("target", 3))
    assert not [lb for lb in labels(loop, "A") if "Hextech Ray" in lb]
    act(loop, "A", "Activate add_earmarked_power (Kai'Sa")
    assert [lb for lb in labels(loop, "A") if "Hextech Ray" in lb]
    act(loop, "A", "Cast Hextech Ray @BF0")
    assert not loop.gs.battlefields[0].units_B


def test_plundering_poro_conquers_for_an_exhausted_gold():
    """Plundering Poro: 'When I conquer, play a Gold gear token exhausted.'"""
    loop, a, b = setup(active="A")
    poro = unit("Plundering Poro")
    a.base_units.append(poro)
    act(loop, "A", "Move Plundering Poro base→BF0")
    act(loop, "A", "Pass")
    assert [(g.name, g.tapped) for g in a.base_gear] == [("Gold", True)]


def test_an_offer_you_cant_refuse_gives_its_controller_an_exhausted_gold():
    """'Kill a gear. Its controller plays a Gold gear token exhausted.'"""
    loop, a, b = setup(active="A")
    b.base_gear.append(card("Seal of Rage"))
    a.hand.append(card("An Offer You Can't Refuse"))
    act(loop, "A", "Cast An Offer")
    assert [(g.name, g.tapped) for g in b.base_gear] == [("Gold", True)] and not a.base_gear


def test_smoke_screen_leaves_at_least_one_might():
    """Smoke Screen: 'Give a unit -4 [Might] this turn, to a minimum of 1.'"""
    loop, a, b = setup(active="A")
    target = unit("target", 3)
    b.base_units.append(target)
    a.hand.append(card("Smoke Screen"))
    act(loop, "A", "Cast Smoke Screen")
    assert target.might == 1


def test_bilgewater_tracker_deals_one_to_two_different_units():
    """Bilgewater Tracker: 'deal 1 to each of up to 2 units.'"""
    loop, a, b = setup(active="A")
    e1, e2 = unit("e1", 3), unit("e2", 3)
    b.base_units.extend([e1, e2])
    a.hand.append(card("Bilgewater Tracker"))
    seen = choices(loop, {"target:deal_damage": lambda _l, options: 0})
    act(loop, "A", "Play Bilgewater Tracker")
    asked = [opts for kind, _s, opts in seen if kind == "target:deal_damage"]
    assert len(asked) == 2 and asked[0][0] not in asked[1]
    assert (e1.damage, e2.damage) == (1, 1)


def test_brittle_steel_is_played_from_the_trash_with_flow():
    """Brittle Steel: 'Kill a gear. [Flow][4][Fury]'."""
    loop, a, b = setup(active="A", rich=())
    a.energy = 4
    a.add_power(Domain.FURY, 1)
    a.trash.append(card("Brittle Steel"))
    b.base_gear.append(card("Seal of Rage"))
    act(loop, "A", "Play Brittle Steel from trash (FLOW)")
    assert not b.base_gear and any(c.name == "Brittle Steel" for c in a.banished)
