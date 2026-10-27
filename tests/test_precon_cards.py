"""The precon decks (precon_zed, precon_shen), card by card: each sentence of
the printed text played through the engine (BACKLOG.md section A)."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    a.energy = 20
    for d in Domain:
        a.add_power(d, 5)
    return GameLoop(gs), a, b


def _unit(name, might=None, **kw):
    card = CARD_REGISTRY[name].instantiate() if name in CARD_REGISTRY else UnitCard(name=name, might=might)
    return UnitInPlay(card=card, ready=True, **kw)


def _choose(loop, name, asked=None):
    """The player picks the unit called `name` at any target choice."""
    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target"):
            if asked is not None:
                asked.append([getattr(getattr(o, "card", None), "name", o) for o in options])
            return next((i for i, o in enumerate(options)
                         if getattr(getattr(o, "card", None), "name", None) == name), None)
        return None
    loop.chooser = chooser


def _cast(loop, a, name, lane=0):
    a.hand.append(CARD_REGISTRY[name].instantiate())
    loop._apply_action(a, ("SPELL", len(a.hand) - 1, lane))
    loop._recompute_passives()


def _castable(loop, a, name) -> bool:
    a.hand.append(CARD_REGISTRY[name].instantiate())
    try:
        return any(ga.kind == "SPELL" and a.hand[ga.to_engine()[1]].name == name
                   for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A"))
    finally:
        a.hand.pop()


def _on_board(loop, unit) -> bool:
    return loop._locate_unit(unit) is not None


# -- Lacerate: "Choose a unit. If it's EMPOWERED, disempower it. Then kill it if
# it has 3 [might] or less." -------------------------------------------------------

def test_lacerate_chooses_any_unit_disempowers_then_kills_at_three_or_less():
    loop, a, b = _setup()
    witness = _unit("Mournful Witness", empowered=True)     # EMPOWERED: +2 [might]
    big = _unit("Big", 5)
    a.base_units.append(witness)                             # mine, in base
    loop.gs.battlefields[1].add_unit("B", big)
    loop._recompute_passives()
    assert witness.might == witness.card.might + 2
    asked = []
    _choose(loop, "Mournful Witness", asked)
    _cast(loop, a, "Lacerate")
    assert sorted(asked[0]) == ["Big", "Mournful Witness"]  # both sides, base too
    assert not witness.empowered and not _on_board(loop, witness)
    assert witness.card in a.trash


def test_lacerate_disempowers_but_spares_a_unit_still_above_three():
    loop, a, b = _setup()
    big = _unit("Big", 5)
    loop.gs.battlefields[0].add_unit("B", big)
    _choose(loop, "Big")
    _cast(loop, a, "Lacerate")
    assert _on_board(loop, big)


def test_lacerate_needs_a_unit():
    loop, a, b = _setup()
    assert not _castable(loop, a, "Lacerate")


# -- Pakaa Protector: "When I move, reveal the top card of your Main Deck. If it's
# a unit, draw it. Otherwise, put it in your trash and give me +2 [might] this
# turn." --------------------------------------------------------------------------

def _move_pakaa(top):
    loop, a, b = _setup()
    pakaa = _unit("Pakaa Protector")
    a.base_units.append(pakaa)
    a.deck.cards = [UnitCard(name="Bottom", might=1), top]
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()
    return loop, a, pakaa


def test_pakaa_protector_draws_a_revealed_unit():
    loop, a, pakaa = _move_pakaa(UnitCard(name="Top", might=1))
    assert [c.name for c in a.hand] == ["Top"] and not a.trash
    assert pakaa.might == pakaa.card.might


def test_pakaa_protector_trashes_anything_else_and_gets_two():
    loop, a, pakaa = _move_pakaa(SpellCard(name="Top Spell"))
    assert not a.hand and [c.name for c in a.trash] == ["Top Spell"]
    assert [c.name for c in a.deck.cards] == ["Bottom"]
    assert pakaa.might == pakaa.card.might + 2


# -- Shadow Dash: "Move an enemy unit to a battlefield where you have units. If
# you have exactly two units there, they each get +1 [might] this turn." -------

def test_shadow_dash_moves_an_enemy_where_you_have_two_units_and_they_get_one():
    loop, a, b = _setup()
    mine = [_unit("M1", 2), _unit("M2", 2)]
    for u in mine:
        loop.gs.battlefields[1].add_unit("A", u)
    enemy = _unit("Enemy", 3)
    b.base_units.append(enemy)
    _choose(loop, "Enemy")
    _cast(loop, a, "Shadow Dash", lane=0)
    assert enemy in loop.gs.battlefields[1].units_B
    assert [u.might for u in mine] == [3, 3] and enemy.might == 3


def test_shadow_dash_gives_nothing_without_exactly_two_units_there():
    loop, a, b = _setup()
    mine = [_unit(f"M{i}", 2) for i in range(3)]
    for u in mine:
        loop.gs.battlefields[1].add_unit("A", u)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    _cast(loop, a, "Shadow Dash", lane=0)
    assert len(loop.gs.battlefields[1].units_B) == 1
    assert [u.might for u in mine] == [2, 2, 2]


def test_shadow_dash_needs_a_battlefield_with_your_units():
    loop, a, b = _setup()
    a.base_units.append(_unit("Home", 2))
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    assert not _castable(loop, a, "Shadow Dash")


# -- Dragon Form: "Choose a unit. Its base Might becomes 5 this turn." ---------

def test_dragon_form_chooses_any_unit_even_in_base():
    loop, a, b = _setup()
    small = _unit("Small", 1)
    a.base_units.append(small)
    _choose(loop, "Small")
    _cast(loop, a, "Dragon Form", lane=0)
    assert small.might == 5


# -- Ki Barrier: "Choose a unit. Prevent the next 7 damage that would be dealt to
# it this turn." -------------------------------------------------------------------

def test_ki_barrier_may_choose_any_unit():
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 3), _unit("Theirs", 3)
    loop.gs.battlefields[0].add_unit("A", mine)
    b.base_units.append(theirs)
    asked = []
    _choose(loop, "Theirs", asked)
    _cast(loop, a, "Ki Barrier")
    assert sorted(asked[0]) == ["Mine", "Theirs"]
    assert theirs.damage_shield == 7 and mine.damage_shield == 0
