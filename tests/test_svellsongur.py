"""Svellsongur (BACKLOG E): "As this is attached to a unit, copy that unit's
text to this Equipment's effect text for as long as this is attached to it."
A copy effect (§479.1); effect text is appended to the unit's (§136.2.c), so
the unit has each of its abilities twice (GameLoop._card_effects)."""

from __future__ import annotations

from riftbound.core.cards import SpellCard
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _setup, _unit
from test_corpus_vendetta import _equip
from test_simple_triggers import _kill


def _library(p, n=6):
    _deck(p, *[SpellCard(name=f"S{i}") for i in range(n)])


def test_equipped_by_its_equip_ability_a_move_draws_twice():
    """Stellacorn Herder 'When I move, draw 1', wearing Svellsongur (EQUIP [1]
    [calm], on a unit in base: "a unit you control", §818.1.c.2): the copy
    draws again; another Herder draws once."""
    loop, a, b = _setup()
    herder, other = _unit("Stellacorn Herder"), _unit("Stellacorn Herder")
    a.base_units.append(herder)
    svell = CARD_REGISTRY["Svellsongur"].instantiate()
    a.base_gear.append(svell)
    cost = loop._equip_cost(svell)
    assert cost["energy"] == 1 and cost["domain_power"] == {"calm": 1}
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A"))
               if e["type"] == "equip" and e["gear"] is svell)
    loop._apply_activated_ability(a, b, idx)
    assert svell in herder.gear
    a.base_units.append(other)
    _library(a)
    loop._move_unit_by_effect(herder, loop.gs.battlefields[0])
    assert len(a.hand) == 2
    loop._move_unit_by_effect(other, loop.gs.battlefields[1])
    assert len(a.hand) == 3


def test_two_svellsongurs_copy_the_printed_text_twice():
    """Each copies the unit's own text, not the other's copy (§479.1.b.1)."""
    loop, a, b = _setup()
    herder = _unit("Stellacorn Herder")
    a.base_units.append(herder)
    _equip(herder, "Svellsongur")
    _equip(herder, "Svellsongur")
    _library(a)
    loop._move_unit_by_effect(herder, loop.gs.battlefields[0])
    assert len(a.hand) == 3


def test_the_copy_ends_when_it_is_unattached():
    loop, a, b = _setup()
    herder = _unit("Stellacorn Herder")
    a.base_units.append(herder)
    svell = _equip(herder, "Svellsongur")
    herder.gear.remove(svell)
    a.base_gear.append(svell)
    _library(a)
    loop._move_unit_by_effect(herder, loop.gs.battlefields[0])
    assert len(a.hand) == 1


def test_deathknell_triggers_twice():
    """Watchful Sentry 'DEATHKNELL - Draw 1': it dies wearing Svellsongur, both
    instances trigger (§808.2), as it was when it died (§808.1.d.3)."""
    loop, a, b = _setup()
    sentry = _unit("Watchful Sentry")
    loop.gs.battlefields[0].add_unit("A", sentry)
    _equip(sentry, "Svellsongur")
    _library(a)
    _kill(loop, sentry)
    assert sentry.card in a.trash and len(a.hand) == 2


def test_printed_assault_adds_up_with_the_copy():
    """Laurent Duelist ASSAULT 2 + the copied ASSAULT 2 = ASSAULT 4 (§807.2)."""
    loop, a, b = _setup()
    duelist = _unit("Laurent Duelist")
    a.base_units.append(duelist)
    assert duelist.keyword_value("ASSAULT") == 2
    _equip(duelist, "Svellsongur")
    assert duelist.keyword_value("ASSAULT") == 4 and duelist.keyword_value("SHIELD") == 0


def test_a_passive_applies_twice():
    """Soul Shepherd 'Your token units have +1 [might]', copied: +2."""
    loop, a, b = _setup()
    shepherd = _unit("Soul Shepherd")
    a.base_units.append(shepherd)
    _equip(shepherd, "Svellsongur")
    token = loop._play_token("Recruit", "A")
    loop._recompute_passives()
    assert token.might == token.base_might + 2


def test_a_cost_aura_counts_twice():
    """Eager Apprentice 'While I'm at a battlefield, spells you play cost [1]
    less, to a minimum of [1]', copied: [2] less."""
    loop, a, b = _setup()
    apprentice = _unit("Eager Apprentice")
    loop.gs.battlefields[0].add_unit("A", apprentice)
    spell = SpellCard(name="Spell", cost_energy=4)
    assert loop._aura_reduction(spell, a) == (1, 1)
    _equip(apprentice, "Svellsongur")
    assert loop._aura_reduction(spell, a) == (2, 1)
