"""BACKLOG G3 "Declared choices" (§355): every choice of a spell is made as it
is played, so a later instruction may name a unit an earlier one kills (it is
then not followed, §359.3.e); the declaration ran the instructions in turn and
a later one chose only among what was left."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
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


def _cast(loop, name, **flags):
    card = CARD_REGISTRY[name].instantiate()
    for k, v in flags.items():
        setattr(card, k, v)
    item = ChainItem(player="A", card=card, bf_idx=0)
    loop._put_on_chain(item)
    return item


def _targets(item):
    return [got for kind, _n, got in item.declared.values() if kind.startswith("target")]


def _on_board(loop, unit):
    return loop._locate_unit(unit) is not None


def test_falling_star_both_on_a_lone_enemy_spares_my_unit():
    """Deal 3 to a unit, deal 3 to a unit: the only enemy has 3 Might. Both
    can name it; the second isn't followed once it's dead, so my unit isn't
    hit (before: the second had to choose among what was left: mine)."""
    loop, a, b = _setup()
    enemy, mine = _unit("Enemy", 3), _unit("Mine", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.gs.battlefields[0].add_unit("A", mine)
    item = _cast(loop, "Falling Star")
    assert _targets(item) == [[enemy], [enemy]]
    loop._resolve_chain()
    assert not _on_board(loop, enemy) and mine.damage == 0


def test_icathian_rain_no_friendly_fire_once_the_enemies_are_dead():
    loop, a, b = _setup()
    e1, e2, mine = _unit("E1", 2), _unit("E2", 5), _unit("Mine", 9)
    loop.gs.battlefields[0].add_unit("B", e1)
    loop.gs.battlefields[1].add_unit("B", e2)
    loop.gs.battlefields[0].add_unit("A", mine)
    item = _cast(loop, "Icathian Rain")
    assert all(t[0] in (e1, e2) for t in _targets(item))
    loop._resolve_chain()
    assert not _on_board(loop, e1) and not _on_board(loop, e2) and mine.damage == 0


def test_the_chooser_is_offered_the_unit_the_first_instruction_kills():
    """The player may name the same unit twice; if it survives the first hit
    (here it got bigger in reaction) the second hits it too."""
    loop, a, b = _setup()
    enemy, other = _unit("Enemy", 3), _unit("Other", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.gs.battlefields[0].add_unit("B", other)
    offered = []

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target"):
            offered.append([o.card.name for o in options])
            return next(i for i, o in enumerate(options) if o.card.name == "Enemy")
        return None
    loop.chooser = chooser
    item = _cast(loop, "Falling Star")
    assert _targets(item) == [[enemy], [enemy]]
    assert all("Enemy" in names for names in offered) and len(offered) == 2
    enemy.card.might = 6                      # it survives the first 3
    loop.chooser = None
    loop._resolve_chain()
    assert not _on_board(loop, enemy) and other.damage == 0


def test_a_second_run_of_repeat_may_name_the_first_runs_target():
    """Piercing Light with REPEAT paid, one enemy of 2 Might at a battlefield
    and my unit there too: the second run's "deal 2 to a unit at a
    battlefield" names the dead enemy again, not my unit (before, the second
    run hit it; the "up to one other unit" baseline takes no unit of mine)."""
    loop, a, b = _setup()
    enemy, mine = _unit("Enemy", 2), _unit("Mine", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.gs.battlefields[0].add_unit("A", mine)
    item = _cast(loop, "Piercing Light", _repeat_paid=True)
    firsts = [got for (run, i, _n), (kind, _c, got) in item.declared.items() if i == 0]
    assert firsts == [[enemy], [enemy]]
    loop._resolve_chain()
    assert not _on_board(loop, enemy) and mine.damage == 0


def test_a_later_choice_still_sees_where_an_earlier_move_went():
    """Dragon's Rage: "Then do this: choose another enemy unit at its
    destination" is a reflexive trigger (§388): not declared with the spell
    (§355.5.b), chosen as it goes on the chain, at the destination the move
    declared."""
    loop, a, b = _setup()
    mover, there = _unit("Mover", 4), _unit("There", 3)
    loop.gs.battlefields[0].add_unit("B", mover)
    loop.gs.battlefields[1].add_unit("B", there)

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("destination"):         # the battlefield, not its base
            return next(i for i, o in enumerate(options) if isinstance(o, Battlefield))
        return None
    loop.chooser = chooser
    item = _cast(loop, "Dragon's Rage")
    assert not [t for t in _targets(item) if t is there or t == [there]]
    loop.chooser = None
    loop._resolve_chain()
    assert not _on_board(loop, there) and loop.gs.chain == []


def test_a_unit_the_spell_itself_kills_first_is_not_hit_twice():
    """No change when the targets differ: two enemies, one hit each."""
    loop, a, b = _setup()
    e1, e2 = _unit("E1", 3), _unit("E2", 3)
    loop.gs.battlefields[0].add_unit("B", e1)
    loop.gs.battlefields[0].add_unit("B", e2)
    item = _cast(loop, "Falling Star")
    assert _targets(item) == [[e1], [e2]]
    loop._resolve_chain()
    assert not _on_board(loop, e1) and not _on_board(loop, e2)
