"""BACKLOG G2, Spiritforged approximations. Emperor's Divide moves any number
of friendly units (chosen, any number of them); Assembly Rig's cost recycles a unit from
the trash; Arcane Shift's unit is played to its owner's base or a battlefield
they control (§355.2.a), chosen; The Zero Drive is banished to pay its
ability; Kato the Arm lends every keyword he has (§801.3: granted ones too);
Undertitan's ADD fires when a look reveals him ("you may reveal a unit from
among them")."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.loop import NO_MORE
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _cast_now, _deck, _play_spell, _setup, _unit
from test_corpus_vendetta import _ability


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def test_emperors_divide_moves_any_number_of_friendly_units():
    """'Move any number of friendly units at a battlefield to their base.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    stay, go = _unit("Stay", 3), _unit("Go", 2)
    bf.add_unit("A", stay)
    bf.add_unit("A", go)
    bf.add_unit("B", _unit("Enemy", 9))
    loop.chooser = lambda _l, kind, side, options, default, source: next(
        i for i, o in enumerate(options) if o is NO_MORE or o[1].card.name == "Go")
    _play_spell(loop, a, "Emperor's Divide")
    assert stay in bf.units_A and go in a.base_units
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    units = [_unit("One", 3), _unit("Two", 2)]
    for u in units:
        bf.add_unit("A", u)
    _play_spell(loop, a, "Emperor's Divide")        # baseline: all of them
    assert not bf.units_A and all(u in a.base_units for u in units)


def test_assembly_rig_recycles_a_unit_from_the_trash():
    """'[1] [fury], Recycle a unit from your trash, [tap]: Play a 3 [might] Mech
    unit token to your base.'"""
    loop, a, b = _setup()
    a.base_gear.append(_card("Assembly Rig"))
    spell = SpellCard(name="Old Spell")
    a.trash = [spell]
    entry = loop.activatable_abilities("A")[_ability(loop, "A", "play_token")]
    assert not loop._ability_usable(a, entry)
    unit = UnitCard(name="Old Unit", might=2)
    a.trash.append(unit)
    assert loop._ability_usable(a, entry)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "play_token"))
    assert a.trash == [spell] and a.deck.cards[0] is unit
    assert any(u.card.name == "Mech" for u in a.base_units)


def test_arcane_shift_plays_the_unit_to_base_or_a_battlefield_its_owner_controls():
    """'Banish a friendly unit, then its owner plays it, ignoring its cost.' No
    place named: its base or a battlefield they control (§355.2.a)."""
    loop, a, b = _setup()
    friend = _unit("Friend", 2)
    friend.damage = 1
    loop.gs.battlefields[1].add_unit("A", friend)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 9))
    seen = []

    def chooser(_l, kind, side, options, default, source):
        if kind.startswith("destination:blink_unit"):
            seen.append(list(options))
        return None
    loop.chooser = chooser
    _play_spell(loop, a, "Arcane Shift")
    # Baseline: back where it was (still A's: it was the only unit there).
    back = loop.gs.battlefields[1].units_A
    assert len(back) == 1 and back[0] is not friend and back[0].card is friend.card and back[0].damage == 0
    assert seen and len(seen[0]) == 2 and seen[0][0] is None        # not B's battlefield
    loop, a, b = _setup()
    friend = _unit("Friend", 2)
    loop.gs.battlefields[1].add_unit("A", friend)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 9))
    loop.chooser = lambda _l, kind, side, options, default, source: (
        options.index(None) if kind.startswith("destination:blink_unit") else None)
    _play_spell(loop, a, "Arcane Shift")
    assert not loop.gs.battlefields[1].units_A and any(u.card is friend.card for u in a.base_units)


def test_arcane_shift_sends_a_unit_losing_its_fight_to_base():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    friend = _unit("Friend", 2)
    bf.add_unit("A", friend)
    bf.add_unit("B", _unit("Enemy", 9))
    _play_spell(loop, a, "Arcane Shift")
    assert not bf.units_A and any(u.card is friend.card for u in a.base_units)


def test_the_zero_drive_is_banished_to_pay_its_ability():
    """'[3] [mind], Banish this: Play all units banished with this, ignoring
    their costs.'"""
    loop, a, b = _setup()
    drive = _card("The Zero Drive")
    unit = _unit("Carrier", 3)
    unit.gear.append(drive)
    loop._route_deaths([(unit, "A")], loop.gs.battlefields[0], in_base=True)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "play_banished_with_this"))
    assert any(u.card is unit.card for u in a.base_units)
    assert any(c is drive for c in a.banished) and not any(c is drive for c in a.trash)


def test_kato_the_arm_lends_every_keyword_he_has():
    """'When I move to a battlefield, give another friendly unit my keywords and
    +[might] equal to my Might this turn.' Granted keywords are his too
    (§801.3), for the turn or the combat. With Svellsongur he has DEFLECT twice
    (§809.2) and the ability twice: two DEFLECT 1, two times."""
    loop, a, b = _setup()
    kato, friend = _unit("Kato the Arm"), _unit("Friend", 1)
    kato.turn_keywords.append("ASSAULT 2")
    kato.combat_keywords.append("SHIELD")
    a.base_units.extend([kato, friend])
    loop._move_unit_by_effect(kato, loop.gs.battlefields[0])
    assert friend.keyword_value("ASSAULT") == 2 and friend.has_keyword("SHIELD")
    assert friend.keyword_value("DEFLECT") == 1
    loop, a, b = _setup()
    kato, friend = _unit("Kato the Arm"), _unit("Friend", 1)
    kato.gear.append(_card("Svellsongur"))
    a.base_units.extend([kato, friend])
    loop._move_unit_by_effect(kato, loop.gs.battlefields[0])
    assert friend.keyword_value("DEFLECT") == 4


def test_undertitan_adds_when_a_look_reveals_him():
    """'As I'm revealed from your deck, ADD [2].' Double Trouble: 'Look at the
    top 3 cards of your Main Deck. You may reveal a unit from among them and
    draw it.'"""
    loop, a, b = _setup()
    titan = _card("Undertitan")
    _deck(a, SpellCard(name="S1"), titan, UnitCard(name="Small", might=1))
    energy = a.energy
    _cast_now(loop, a, "Double Trouble")
    assert any(c is titan for c in a.hand) and a.energy == energy + 2


def test_undertitan_doesnt_add_when_a_look_only_takes_him():
    """'Look at the top 3 ... You may choose a card from among them and draw it'
    (Lightning Rush) and 'Put 1 into your hand' (Stacked Deck) reveal nothing."""
    for name in ("Lightning Rush", "Stacked Deck"):
        loop, a, b = _setup()
        titan = _card("Undertitan")
        _deck(a, SpellCard(name="S1"), titan, SpellCard(name="S2"))
        energy = a.energy
        _cast_now(loop, a, name)
        assert any(c is titan for c in a.hand) and a.energy == energy, name
