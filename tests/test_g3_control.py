"""BACKLOG G3, Control (§190.4). A unit arriving at a battlefield its side
doesn't control makes it Contested (§190.3.a); control then stays with the side
that held it until the showdown or combat there establishes it (§190.4.b,
§348.2.a, §468.5): a side moving alone onto an uncontrolled battlefield controls
it after its showdown, and a holder whose units all die mid-showdown still
controls it until the combat is over. A unit an effect plays or takes control
of there gets its showdown too (§344.2); a contest whose units are gone before
it ends without one (§190.3.b.1)."""

from __future__ import annotations

from riftbound.core.cards import UnitCard

from test_corpus_cards import _setup, _unit


class _Watch:
    """An agent that plays `actions` in its turn, then passes; in a showdown it
    runs `on_showdown` (once) and notes battlefield 0's control each time."""

    def __init__(self, loop, actions=(), on_showdown=None):
        self.loop, self.actions, self.on_showdown = loop, list(actions), on_showdown
        self.turn_seen, self.showdown_seen = [], []

    def decide_action(self, opponent, cards_played=0):
        self.turn_seen.append(self.loop.gs.battlefields[0].control())
        return self.actions.pop(0) if self.actions else ("PASS", None, None)

    def decide_showdown_action(self, opponent, bf_idx):
        if self.on_showdown is not None:
            self.on_showdown()
            self.on_showdown = None
        self.showdown_seen.append(self.loop.gs.battlefields[0].control())
        return ("PASS", None, None)

    def decide_reaction(self, opponent, chain):
        return ("PASS", None, None)


def _controls(loop, side, bf):
    p = loop.gs.get_player(side)
    return loop._check_condition({"type": "you_control_this_battlefield"}, UnitCard(name="X"),
                                 p, loop.gs.get_player(loop.gs.other(side)), {"battlefield": bf})


def test_moving_alone_onto_an_empty_battlefield_controls_it_after_its_showdown():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    a.base_units.append(_unit("Hero", 3))
    a.agent = _Watch(loop, [("MOVE", 0, 2, 0)])
    b.agent = _Watch(loop)
    loop._run_main_actions()
    # Asked before moving, while the move is held, and after the showdown.
    assert a.agent.turn_seen == [None, None, "A"]
    assert a.agent.showdown_seen == [None] and b.agent.showdown_seen == [None]
    assert bf.control() == "A" and bf.contested_by is None
    assert loop.gs.points_A == 1                                  # conquered (§348.2.a.1)


def test_in_its_own_showdown_the_mover_cant_play_to_it_as_a_battlefield_it_controls():
    loop, a, b = _setup()
    a.base_units.append(_unit("Hero", 3))
    seen = []
    a.agent = _Watch(loop, [("MOVE", 0, 2, 0)], on_showdown=lambda: seen.append(
        loop._unit_play_destinations(UnitCard(name="Next"), "A")))
    b.agent = _Watch(loop)
    loop._run_main_actions()
    assert seen == [[None]]
    assert loop._unit_play_destinations(UnitCard(name="Next"), "A") == [None, 0]


def test_a_holder_whose_units_die_mid_showdown_controls_it_until_the_combat_ends():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    wall = _unit("Wall", 1)
    bf.add_unit("B", wall)
    a.base_units.append(_unit("Hero", 3))
    checks = []

    def kill_the_wall():
        bf.remove_unit("B", wall)                  # as a spell killing it would
        checks.append((bf.control(), _controls(loop, "B", bf), _controls(loop, "A", bf)))

    a.agent = _Watch(loop, [("MOVE", 0, 2, 0)], on_showdown=kill_the_wall)
    b.agent = _Watch(loop)
    loop._run_main_actions()
    assert checks == [("B", True, False)]
    assert b.agent.showdown_seen == ["B"]
    assert bf.control() == "A" and loop.gs.points_A == 1


def test_a_token_an_effect_plays_to_an_empty_battlefield_conquers_it_after_its_showdown():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[1]
    loop._play_token("Recruit", "A", bf=bf)
    assert bf.control() is None and bf.contested_by == "A"
    loop._run_staged_showdowns()
    assert bf.control() == "A" and loop.gs.points_A == 1


def test_taking_control_of_a_lone_unit_takes_the_battlefield_after_its_showdown():
    """§190.3.a.2: a unit changing controller at a battlefield contests it."""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    lone = _unit("Lone", 2)
    bf.add_unit("B", lone)
    assert bf.control() == "B"
    loop._take_control(lone, "A")
    assert bf.control() == "B" and bf.contested_by == "A"
    loop._run_staged_showdowns()
    assert bf.control() == "A" and loop.gs.points_A == 1


def test_a_contest_whose_units_are_gone_ends_with_no_showdown():
    """§190.3.b.1: moved in by an effect, killed before its showdown."""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("B", _unit("Wall", 1))
    hero = _unit("Hero", 3)
    a.base_units.append(hero)
    loop._move_unit_by_effect(hero, bf)
    assert bf.contested_by == "A" and bf.control() == "B"
    bf.remove_unit("A", hero)
    ran = []
    loop._run_showdown = lambda *args, **kw: ran.append(args)
    loop._run_staged_showdowns()
    assert ran == [] and bf.contested_by is None and bf.control() == "B"


def test_a_contest_left_with_no_showdown_is_settled_at_the_end_of_turn():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Hero", 3))
    bf.contest("A", None)
    assert bf.control() is None
    loop._phase_combat_and_conquer("A")
    assert bf.control() == "A" and bf.contested_by is None


def test_a_side_reinforcing_its_own_battlefield_doesnt_contest_it():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Holder", 1))
    assert bf.control() == "A"
    loop._play_token("Recruit", "A", bf=bf)
    assert bf.contested_by is None and bf.control() == "A" and not loop.gs.staged_showdowns
