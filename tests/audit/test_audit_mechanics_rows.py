"""Sixth pass: the PARTIAL / GAP rows of docs/MECHANICS.md, each against the
rule and a game situation (BACKLOG O2). Deviations found are D56 on."""

from __future__ import annotations

from audit_helpers import act, card, choices, setup, unit


def _kayle(loop, side="B", times=3):
    kayle = unit("Kayle Justified")
    loop.gs.battlefields[0].add_unit(side, kayle)
    loop._empower(kayle.card, side)
    kayle.empower_times = times
    loop._recompute_passives()
    return kayle


def test_disempower_removes_one_of_several_empowered_statuses():
    """D56. §443.1.b: 'Disempowering a Game Object that has multiple Empowered
    statuses will remove one of those statuses.' Lacerate on Kayle Justified
    empowered three times ('+2 [might] for each time') left her with none, so
    she died at 3 [might]; she keeps two, at 7, and lives."""
    loop, a, b = setup(active="A")
    kayle = _kayle(loop)
    assert kayle.might == 9
    a.hand.append(card("Lacerate"))
    choices(loop, {"target": lambda _l, opts: next(i for i, u in enumerate(opts) if u is kayle)})
    act(loop, "A", "Cast Lacerate")
    assert kayle.empowered and kayle.empower_times == 2 and kayle.might == 7
    assert kayle in loop.gs.battlefields[0].units_B


def test_weighing_a_lacerate_target_leaves_the_others_statuses_alone():
    """D56. Lacerate's baseline weighed each unit as if disempowered and put
    back only 'empowered', not how many times: Kayle Justified, not chosen,
    lost two of her three statuses."""
    loop, a, b = setup(active="A")
    kayle = _kayle(loop)
    small = unit("small", 2)
    loop.gs.battlefields[1].add_unit("B", small)
    a.hand.append(card("Lacerate"))
    act(loop, "A", "Cast Lacerate")
    assert small not in loop.gs.battlefields[1].units_B
    assert kayle.empower_times == 3 and kayle.might == 9
