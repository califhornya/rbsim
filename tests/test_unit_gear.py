"""Unit gear (BACKLOG E): Orianna Lady of Clockwork, "At the start of your Main
Phase, you may pay [1] to choose a friendly gear. It becomes a unit gear with
Might equal to its Energy cost until you choose another gear with me", and
The Ball (RAD-146) as a unit."""
from __future__ import annotations

from riftbound.core.cards import SpellCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _fight, _setup, _unit
from test_corpus_vendetta import _ctx


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _orianna(loop, side="A"):
    unit = UnitInPlay(card=_card("Orianna Lady of Clockwork"), ready=True)
    if side == "A":
        loop.gs.legend_unit_A = unit
    else:
        loop.gs.legend_unit_B = unit


def _main_starts(loop, side="A"):
    """The start of the Main Phase (as _begin_turn, after the draw)."""
    loop._fire_turn_trigger("on_start_of_main", side)
    loop._recompute_passives()
    loop._run_staged_showdowns()


def _deploy_ball(loop, side="A", bf=0):
    ball = _card("The Ball")
    loop._deploy_gear(side, loop.gs.battlefields[bf], ball)
    return ball


def _choose(loop, name, pay=True):
    """Orianna pays (or not) and chooses the gear called `name`."""
    def chooser(_loop, kind, side, options, default, source):
        if kind == "optional:clockwork_animate":
            return options.index(pay)
        if kind == "target:clockwork_animate":
            return next(i for i, (_s, _h, g) in enumerate(options)
                        if getattr(g, "card", g).name == name)
        return None
    loop.chooser = chooser


def test_the_ball_deployed_at_a_battlefield_becomes_a_five_might_unit_there():
    loop, a, b = _setup()
    _orianna(loop)
    ball = _deploy_ball(loop)
    b.base_units.append(_unit("Far", 1))
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Friend", 1))      # we hold it already: no conquer
    _main_starts(loop)
    unit = next(u for u in bf.units_A if u.card is ball)
    assert unit.gear_unit and unit.might == 5 and unit.ready
    assert not bf.gear_A
    assert a.energy == 19


def test_a_gear_unit_at_an_empty_battlefield_conquers_it():
    loop, a, b = _setup()
    _orianna(loop)
    _deploy_ball(loop)
    _main_starts(loop)
    assert loop.gs.points_A == 1
    assert loop.gs.battlefields[0].control() == "A"


def test_no_gear_no_payment():
    loop, a, b = _setup()
    _orianna(loop)
    _main_starts(loop)
    assert a.energy == 20 and not a.base_units


def test_orianna_only_at_the_start_of_her_own_main_phase():
    loop, a, b = _setup()
    _orianna(loop, "B")
    _deploy_ball(loop, "B")
    _main_starts(loop, "A")
    assert loop.gs.battlefields[0].gear_B and b.energy == 20


def test_baseline_keeps_a_bigger_unit_gear_rather_than_a_smaller_gear():
    loop, a, b = _setup()
    _orianna(loop)
    _deploy_ball(loop)
    loop.gs.battlefields[0].add_unit("A", _unit("Friend", 1))
    _main_starts(loop)
    a.base_gear.append(_card("Iron Ballista"))
    _main_starts(loop)
    assert a.energy == 19 and len(a.base_gear) == 1


def test_choosing_another_gear_turns_the_first_back_into_a_gear():
    """The Ball goes back to being a deployed gear where it is, exhausted if the
    unit was; the new gear in base becomes a unit in base."""
    loop, a, b = _setup()
    _orianna(loop)
    ball = _deploy_ball(loop)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Friend", 1))
    _main_starts(loop)
    unit = next(u for u in bf.units_A if u.card is ball)
    unit.ready = False
    ballista = _card("Iron Ballista")
    a.base_gear.append(ballista)
    _choose(loop, "Iron Ballista")
    _main_starts(loop)
    assert unit not in bf.units_A
    assert [dg.card for dg in bf.gear_A] == [ball] and ball.tapped
    new = next(u for u in a.base_units if u.card is ballista)
    assert new.gear_unit and new.might == 3 and ballista not in a.base_gear


def test_a_non_deploy_gear_unit_at_a_battlefield_goes_back_to_base_as_a_gear():
    loop, a, b = _setup()
    _orianna(loop)
    ballista = _card("Iron Ballista")
    a.base_gear.append(ballista)
    _main_starts(loop)
    unit = next(u for u in a.base_units if u.card is ballista)
    loop._standard_move(unit, "A", 2, 0)
    loop._flush_pending_move()
    assert unit in loop.gs.battlefields[0].units_A
    _deploy_ball(loop, bf=1)
    _choose(loop, "The Ball")
    _main_starts(loop)
    assert ballista in a.base_gear and unit not in loop.gs.battlefields[0].units_A


def test_an_attached_equipment_detaches_and_its_might_is_its_energy_cost():
    """B.F. Sword: Energy 4, [might] +3 as an Equipment; a 4 Might unit (§143.5.b)."""
    loop, a, b = _setup()
    _orianna(loop)
    holder = _unit("Holder", 2)
    sword = _card("B.F. Sword")
    holder.gear.append(sword)
    loop.gs.battlefields[1].add_unit("A", holder)
    _main_starts(loop)
    assert not holder.gear and holder.might == 2
    unit = next(u for u in loop.gs.battlefields[1].units_A if u.card is sword)
    assert unit.might == 4


def test_the_ball_unit_ganks_and_its_move_ability_fires():
    loop, a, b = _setup()
    _orianna(loop)
    ball = _deploy_ball(loop)
    loop.gs.battlefields[0].add_unit("A", _unit("Friend", 1))
    _main_starts(loop)
    unit = next(u for u in loop.gs.battlefields[0].units_A if u.card is ball)
    e1, e2 = _unit("E1", 2), _unit("E2", 2)
    loop.gs.battlefields[1].add_unit("B", e1)
    loop.gs.battlefields[1].add_unit("B", e2)
    _deck(a, SpellCard(name="S1"))
    assert loop._standard_move(unit, "A", 0, 1) is not False
    assert unit in loop.gs.battlefields[1].units_A
    assert (e1.card in b.trash and e2.card in b.trash) != (len(a.hand) == 1)


def test_a_unit_gear_dies_as_a_unit_and_as_a_gear():
    loop, a, b = _setup()
    _orianna(loop)
    ball = _deploy_ball(loop)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Friend", 1))
    _main_starts(loop)
    bf.add_unit("B", _unit("Big", 9))
    _fight(loop, "B")
    assert ball in a.trash
    assert loop.gs.friendly_unit_died_this_turn["A"] and loop.gs.friendly_gear_died_this_turn["A"]


def test_kill_a_gear_can_choose_a_unit_gear():
    loop, a, b = _setup()
    _orianna(loop)
    ballista = _card("Iron Ballista")
    a.base_gear.append(ballista)
    _main_starts(loop)
    REGISTRY["kill_gear"](_ctx(loop, b), {"effect": "kill_gear", "target": "enemy_gear", "scope": "single"})
    assert ballista in a.trash and not a.base_units


def test_orianna_exquisite_deals_damage_beside_a_unit_gear():
    """'I don't deal combat damage unless there's a friendly gear here.'"""
    loop, a, b = _setup()
    _orianna(loop)
    bf = loop.gs.battlefields[0]
    exq = _unit("Orianna Exquisite")
    bf.add_unit("A", exq)
    loop._recompute_passives()
    assert exq.no_combat_damage
    _deploy_ball(loop)
    loop.gs.battlefields[0].gear_A.clear()
    ballista = _card("Iron Ballista")
    a.base_gear.append(ballista)
    _main_starts(loop)
    unit = next(u for u in a.base_units if u.card is ballista)
    loop._standard_move(unit, "A", 2, 0)
    loop._flush_pending_move()
    loop._recompute_passives()
    assert not exq.no_combat_damage


def test_a_real_turn_start_makes_the_ball_a_unit_that_can_gank():
    """_begin_turn: Beginning Phase, draw, then the start of the Main Phase; the
    unit gear's moves are legal actions (bf -> bf with GANKING)."""
    from riftbound.core.legality import legal_actions
    from riftbound.core.player import Rune
    from riftbound.core.enums import Domain
    loop, a, b = _setup()
    _orianna(loop)
    ball = _deploy_ball(loop)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Friend", 1))
    a.rune_pool = {Domain.CALM: [Rune(Domain.CALM) for _ in range(3)]}
    _deck(a, SpellCard(name="S1"), SpellCard(name="S2"))
    loop.gs.turn, loop.gs.active = 3, "A"
    assert loop._begin_turn() is None
    unit = next(u for u in bf.units_A if u.card is ball)
    assert unit.might == 5 and a.energy == 2 and len(a.hand) == 1
    moves = [act.label for act in legal_actions(loop)]
    assert "Move The Ball BF0→BF1" in moves
