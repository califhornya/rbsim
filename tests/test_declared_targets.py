"""A spell's targets are chosen as it is put on the chain (§355.5, §355.8) and
used as it resolves; a target no longer legal then is not affected (§359.3.e)."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import ChainItem, GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    a.energy = 10
    for d in Domain:
        a.add_power(d, 3)
    return GameLoop(gs), a, b


def _unit(name, might):
    return UnitInPlay(card=UnitCard(name=name, might=might), ready=True)


def _picks(name):
    """A chooser that takes the unit called `name` for any target, and counts
    the target choices it is asked."""
    asked = []

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target"):
            asked.append(kind)
            return next((i for i, o in enumerate(options) if o.card.name == name), None)
        return None
    return chooser, asked


def _cast(loop, a, name):
    card = CARD_REGISTRY[name].instantiate()
    item = ChainItem(player="A", card=card, bf_idx=0)
    loop._put_on_chain(item)
    return item


def test_the_target_is_chosen_as_the_spell_is_played_and_kept():
    loop, a, b = _setup()
    big, small = _unit("Big", 8), _unit("Small", 3)
    loop.gs.battlefields[0].add_unit("B", big)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.chooser, asked = _picks("Small")
    item = _cast(loop, a, "Ruthless Strike")
    [(kind, n, chosen)] = item.declared.values()
    assert kind.startswith("target") and n == 2 and chosen == [small] and chosen[0] is small
    loop.chooser, later = _picks("Big")     # not asked again as it resolves
    loop._resolve_chain()
    assert small.damage == 3 and big.damage == 0 and asked and not later


def test_a_target_no_longer_legal_is_not_affected():
    """Void Seeker's example: the target moved to base in reaction, so the
    "unit at a battlefield" isn't dealt any damage, and no other unit is."""
    loop, a, b = _setup()
    big, small = _unit("Big", 8), _unit("Small", 3)
    loop.gs.battlefields[0].add_unit("B", big)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.chooser, _ = _picks("Small")
    _cast(loop, a, "Ruthless Strike")
    loop._move_unit_by_effect(small, None)              # Small goes to its base
    assert small in b.base_units
    loop._resolve_chain()
    assert small.damage == 0 and big.damage == 0


def test_a_spell_needs_a_valid_target_to_be_played():
    """§355.8: no unit at a battlefield, no Ruthless Strike; no enemy unit, no
    Charm. Once there is one, both can be played."""
    loop, a, b = _setup()
    a.hand = [CARD_REGISTRY["Ruthless Strike"].instantiate(), CARD_REGISTRY["Charm"].instantiate()]
    a.base_units.append(_unit("Mine", 2))

    def spells():
        return {a.hand[ga.to_engine()[1]].name
                for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if ga.kind == "SPELL"}
    assert spells() == set()
    loop._apply_action(a, ("SPELL", 0, 0))                # the engine refuses it too
    assert len(a.hand) == 2 and a.energy == 10
    loop.gs.battlefields[1].add_unit("A", _unit("Out", 2))
    assert spells() == {"Ruthless Strike"}                 # a unit at a battlefield, no enemy
    loop.gs.battlefields[1].add_unit("B", _unit("Theirs", 2))
    assert spells() == {"Charm", "Ruthless Strike"}


def test_the_declared_choice_is_told_once():
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Small", 3))
    told = []
    loop.on_choice = lambda kind, side, n, got, source: told.append((kind, side, n, source.name))
    _cast(loop, a, "Ruthless Strike")
    assert told == [("target:deal_damage", "A", 1, "Ruthless Strike")]
    loop._resolve_chain()
    assert len(told) == 1
