"""BACKLOG G3 "Costs before choices" (§355-358): a spell's choices are made,
then its total cost is found and paid, then it is played ("when you play a
spell"). Irelia Graceful ("Your spells that choose me cost [1] or [rune]
less"): a spell only her discount makes affordable can be played, and then
must choose her (GameLoop._graceful_credit, _declare_choices); "if you spent
[N]" sees the Energy with her discount off (GameLoop._spell_finalized)."""

from __future__ import annotations

from riftbound.core.cards import SpellCard
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions

from test_corpus_cards import _deck, _pick, _play_spell, _setup, _unit


def _irelia(p):
    unit = _unit("Irelia Graceful")
    p.base_units.append(unit)
    return unit


def _castable(loop, p, name):
    from riftbound.registry.cards_registry import CARD_REGISTRY
    p.hand.append(CARD_REGISTRY[name].instantiate())
    return any(a.kind == "SPELL" and a.index == len(p.hand) - 1
               for a in legal_actions(loop, DecisionPoint.TURN_ACTION, p.name))


def test_a_spell_only_her_discount_pays_for_is_played():
    loop, a, b = _setup()
    irelia = _irelia(a)
    _deck(a, SpellCard(name="Card"))
    a.energy = 1                                   # Discipline costs [2]
    assert _castable(loop, a, "Discipline")
    a.hand.pop()
    _play_spell(loop, a, "Discipline")
    assert a.energy == 0 and irelia.temporary_might == 2
    assert not any(c.name == "Discipline" for c in a.hand)


def test_without_her_it_cant_be_played():
    loop, a, b = _setup()
    a.base_units.append(_unit("Other", might=2))
    a.energy = 1
    assert not _castable(loop, a, "Discipline")
    a.hand.pop()
    _play_spell(loop, a, "Discipline")
    assert a.energy == 1 and any(c.name == "Discipline" for c in a.hand)


def test_paid_for_with_her_it_must_choose_her():
    """The player would choose another unit: only she is offered (§355.16)."""
    loop, a, b = _setup()
    irelia = _irelia(a)
    other = _unit("Other", might=2)
    a.base_units.append(other)
    _deck(a, SpellCard(name="Card"))
    a.energy = 1
    _pick(loop, "Other")
    _play_spell(loop, a, "Discipline")
    assert a.energy == 0 and irelia.temporary_might == 2 and other.temporary_might == 0


def test_with_enough_energy_the_choice_stays_free():
    loop, a, b = _setup()
    _irelia(a)
    other = _unit("Other", might=2)
    a.base_units.append(other)
    _deck(a, SpellCard(name="Card"))
    a.energy = 2
    _pick(loop, "Other")
    _play_spell(loop, a, "Discipline")
    assert a.energy == 0 and other.temporary_might == 2


def test_her_discount_can_pay_the_power():
    """Falling Star ([2], [fury][fury]) with [2] and one [fury]: her [rune] off."""
    loop, a, b = _setup()
    irelia = _irelia(a)
    b.base_units.append(_unit("Enemy", might=9))
    a.energy = 2
    a.power_pool.clear()
    a.add_power(Domain.FURY, 1)
    _play_spell(loop, a, "Falling Star")
    assert a.energy == 0 and sum(a.power_pool.values()) == 0
    assert irelia.damage >= 3 or irelia not in a.base_units


def test_spent_counts_the_energy_after_her_discount():
    """Onslaught ([4]) choosing her: [3] spent, so Revna the Lorekeeper ("When
    you play a spell, if you spent [4] or more, ready me") stays exhausted."""
    loop, a, b = _setup()
    _irelia(a)
    revna = _unit("Revna the Lorekeeper")
    revna.ready = False
    a.base_units.append(revna)
    _pick(loop, "Irelia Graceful")
    _play_spell(loop, a, "Onslaught")
    assert a.energy == 17 and loop.gs.spell_spent["A"][1] == 3 and not revna.ready


def test_spent_four_readies_revna():
    loop, a, b = _setup()
    revna = _unit("Revna the Lorekeeper")
    revna.ready = False
    a.base_units.append(revna)
    a.base_units.append(_unit("Other", might=2))
    _pick(loop, "Other")
    _play_spell(loop, a, "Onslaught")
    assert a.energy == 16 and loop.gs.spell_spent["A"][1] == 4 and revna.ready


def test_an_opponents_irelia_gives_no_credit():
    loop, a, b = _setup()
    _irelia(b)
    a.energy = 1
    assert not _castable(loop, a, "Discipline")
