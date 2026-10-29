"""Endless Riches (BACKLOG E): "When you play this, banish your hand and trash,
then BURN 7. Skip your Draw Phase. You may play cards from your trash. If a
card would go to your trash from anywhere other than your Main Deck, banish it
instead." Plays from the trash are `trash_play` entries with `cost` None (the
card's own cost); the replacement is GameLoop._put_in_trash."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _setup, _spell, _unit
from test_corpus_radiance import _card, _die


def _riches(p):
    card = _card("Endless Riches")
    p.base_gear.append(card)
    return card


def _names(cards):
    return [c.name for c in cards]


def _trash_plays(loop, side="A"):
    p = loop.gs.get_player(side)
    return [(i, e) for i, e in enumerate(loop.activatable_abilities(side))
            if e["type"] == "trash_play" and e["cost"] is None and loop._ability_usable(p, e)]


def _play_from_trash(loop, p, name):
    i = next(i for i, e in _trash_plays(loop, p.name) if e["card"].name == name)
    loop._apply_action(p, ("ABILITY", "ACTIVATED", i, None))
    loop._recompute_passives()


def test_playing_it_banishes_hand_and_trash_then_burns_7():
    loop, a, b = _setup()
    a.hand = [_card("Endless Riches"), SpellCard(name="Held")]
    a.trash = [SpellCard(name="Old")]
    _deck(a, *[UnitCard(name=f"D{i}", might=1) for i in range(9)])
    loop._apply_action(a, ("GEAR", 0, 0))
    loop._recompute_passives()
    assert _names(a.base_gear) == ["Endless Riches"]
    assert sorted(_names(a.banished)) == ["Held", "Old"] and a.hand == []
    assert _names(a.trash) == [f"D{i}" for i in range(7)]      # burned: from the Main Deck
    assert len(a.deck.cards) == 2


def test_it_skips_the_draw_phase():
    loop, a, b = _setup()
    _riches(a)
    _deck(a, UnitCard(name="Top", might=1))
    loop._begin_turn()
    assert a.hand == [] and len(a.deck.cards) == 1


def test_without_it_the_draw_phase_draws():
    loop, a, b = _setup()
    _deck(a, UnitCard(name="Top", might=1))
    loop._begin_turn()
    assert _names(a.hand) == ["Top"]


def test_a_unit_is_played_from_the_trash_for_its_cost():
    loop, a, b = _setup()
    _riches(a)
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=3)]
    a.energy = 3
    _play_from_trash(loop, a, "Grunt")
    assert a.trash == [] and _names(u.card for u in a.base_units) == ["Grunt"]
    assert a.energy == 0


def test_it_cant_be_played_without_paying():
    loop, a, b = _setup()
    _riches(a)
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=3)]
    a.energy = 2
    assert _trash_plays(loop) == []


def test_without_it_nothing_is_played_from_the_trash():
    loop, a, b = _setup()
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=1)]
    assert _trash_plays(loop) == []


def test_only_its_controllers_trash():
    loop, a, b = _setup()
    _riches(b)
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=1)]
    assert _trash_plays(loop) == []


def test_a_spell_from_the_trash_is_banished_after_it_resolves():
    loop, a, b = _setup()
    _riches(a)
    a.trash = [CARD_REGISTRY[_spell(1)].instantiate()]
    _play_from_trash(loop, a, "Test Spell 1")
    assert a.trash == [] and _names(a.banished) == ["Test Spell 1"]


def test_a_dying_unit_is_banished_instead():
    loop, a, b = _setup()
    _riches(a)
    unit = _unit("Grunt", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    _die(loop, unit)
    assert a.trash == [] and _names(a.banished) == ["Grunt"]


def test_a_discard_is_banished_instead():
    loop, a, b = _setup()
    _riches(a)
    a.hand = [SpellCard(name="Tossed")]
    loop._discard(a, a.hand[0])
    assert a.trash == [] and _names(a.banished) == ["Tossed"]


def test_the_opponents_cards_still_go_to_their_trash():
    loop, a, b = _setup()
    _riches(a)
    unit = _unit("Grunt", 2)
    loop.gs.battlefields[0].add_unit("B", unit)
    _die(loop, unit, side="B")
    assert _names(b.trash) == ["Grunt"] and b.banished == []


def test_killed_it_banishes_itself_then_cards_go_to_the_trash_again():
    """§370.4: it replaces its own move to the trash as it leaves the board."""
    loop, a, b = _setup()
    riches = _riches(a)
    a.base_gear.remove(riches)
    loop._to_trash(a, riches)
    assert _names(a.banished) == ["Endless Riches"] and a.trash == []
    a.hand = [SpellCard(name="Tossed")]
    loop._discard(a, a.hand[0])
    assert _names(a.trash) == ["Tossed"]
