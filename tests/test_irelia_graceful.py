"""Irelia Graceful (BACKLOG E): "Your spells that choose me cost [1] or [rune]
less." The engine pays a spell's cost before its choices, so the discount is
taken as the spell chooses her (GameLoop._graceful_discount), as DEFLECT's
[rune] is paid then: off that [rune] first, else Energy back, else Power."""

from __future__ import annotations

from riftbound.core.cards import SpellCard

from test_corpus_cards import _deck, _pick, _play_spell, _setup, _unit
from test_corpus_vendetta import _equip


def _irelia(p):
    unit = _unit("Irelia Graceful")
    p.base_units.append(unit)
    return unit


def _picks(loop, *names):
    """Each target choice picks the next unit named."""
    left = list(names)

    def chooser(_loop, kind, side, options, default, source):
        if not kind.startswith("target") or not left:
            return None
        i = next((i for i, o in enumerate(options)
                  if getattr(getattr(o, "card", None), "name", None) == left[0]), None)
        if i is not None:
            left.pop(0)
        return i
    loop.chooser = chooser


def _power(p):
    return sum(p.power_pool.values())


def test_a_spell_choosing_her_costs_one_less():
    loop, a, b = _setup()
    irelia = _irelia(a)
    _deck(a, SpellCard(name="Card"))
    _pick(loop, "Irelia Graceful")
    _play_spell(loop, a, "Discipline")
    assert a.energy == 19 and irelia.temporary_might == 2


def test_choosing_another_unit_pays_in_full():
    loop, a, b = _setup()
    _irelia(a)
    a.base_units.append(_unit("Other", might=2))
    _deck(a, SpellCard(name="Card"))
    _pick(loop, "Other")
    _play_spell(loop, a, "Discipline")
    assert a.energy == 18


def test_the_baselines_choice_of_her():
    loop, a, b = _setup()
    irelia = _irelia(a)
    _deck(a, SpellCard(name="Card"))
    _play_spell(loop, a, "Discipline")
    assert irelia.temporary_might == 2 and a.energy == 19


def test_chosen_as_it_resolves_in_a_lookahead():
    """A lookahead doesn't declare choices: she is chosen as the spell resolves."""
    loop, a, b = _setup()
    loop._lookahead = True
    irelia = _irelia(a)
    _deck(a, SpellCard(name="Card"))
    _play_spell(loop, a, "Discipline")
    assert irelia.temporary_might == 2 and a.energy == 19


def test_choosing_her_twice_is_one_discount():
    loop, a, b = _setup()
    _irelia(a)
    _picks(loop, "Irelia Graceful", "Irelia Graceful")
    _play_spell(loop, a, "Falling Star")
    assert a.energy == 19


def test_her_discount_takes_off_an_enemy_deflect():
    """Falling Star chooses her and Irelia Fervent (DEFLECT): the [rune] it adds
    is the [rune] she takes off."""
    loop, a, b = _setup()
    _irelia(a)
    b.base_units.append(_unit("Irelia Fervent"))
    before = _power(a)
    _picks(loop, "Irelia Graceful", "Irelia Fervent")
    _play_spell(loop, a, "Falling Star")
    assert a.energy == 18 and _power(a) == before - 2


def test_without_her_the_deflect_is_paid():
    loop, a, b = _setup()
    a.base_units.append(_unit("Other", might=5))
    b.base_units.append(_unit("Irelia Fervent"))
    before = _power(a)
    _picks(loop, "Other", "Irelia Fervent")
    _play_spell(loop, a, "Falling Star")
    assert a.energy == 18 and _power(a) == before - 3


def test_an_opponents_spell_choosing_her_pays_in_full():
    loop, a, b = _setup()
    _irelia(a)
    _deck(b, SpellCard(name="Card"))
    _pick(loop, "Irelia Graceful")
    _play_spell(loop, b, "Discipline")
    assert b.energy == 18


def test_svellsongur_copies_give_more_discounts_power_last():
    """Two Svellsongurs: three discounts on Falling Star ([2] and [fury][fury]):
    the Energy, then one Power, come back."""
    loop, a, b = _setup()
    irelia = _irelia(a)
    _equip(irelia, "Svellsongur")
    _equip(irelia, "Svellsongur")
    before = _power(a)
    _pick(loop, "Irelia Graceful")
    _play_spell(loop, a, "Falling Star")
    assert a.energy == 20 and _power(a) == before - 1
