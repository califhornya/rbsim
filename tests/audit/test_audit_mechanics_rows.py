"""Sixth pass: the PARTIAL / GAP rows of docs/MECHANICS.md, each against the
rule and a game situation (BACKLOG O2). Deviations found are D56 on."""

from __future__ import annotations

from audit_helpers import act, card, choices, labels, setup, unit


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


# --- Rows checked, no deviation: each pinned by a game situation ---

def test_deflect_taxes_an_ability_too():
    """§809.1.c: 'Spells and abilities an opponent controls that target me cost
    [Deflect Value] more'. Mel Defiant Soul's 'When I become EMPOWERED, banish
    an enemy unit at a battlefield with 3 [might] or less' can't choose Steel
    Paws without the [rune], and pays it when it does."""
    from riftbound.core.enums import Domain
    loop, a, b = setup(active="A", rich=())
    mel, paws = unit("Mel Defiant Soul"), unit("Steel Paws")
    loop.gs.battlefields[0].add_unit("A", mel)
    loop.gs.battlefields[1].add_unit("B", paws)
    seen = choices(loop, {})
    loop._empower(mel.card, "A")
    assert paws in loop.gs.battlefields[1].units_B and not seen
    loop._disempower(mel.card)
    a.add_power(Domain.CALM, 1)
    loop._empower(mel.card, "A")
    assert [c.name for c in b.banished] == ["Steel Paws"] and not a.power_pool.get(Domain.CALM)


def test_hunt_gains_xp_for_each_unit_on_conquer_and_on_hold():
    """§823.1.c.1: 'When I Conquer or Hold, my controller gains X XP.'"""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit("Voracious Gromp"))          # HUNT 3
    bf.add_unit("A", unit("Herald of Spring"))         # HUNT
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert loop.gs.get_xp("A") == 4
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert loop.gs.get_xp("A") == 8 and loop.gs.get_xp("B") == 0


def test_hunt_values_granted_by_more_sources_add_up():
    """§823.2: the Hunt Value of all granted Hunt keywords is summed."""
    gromp = unit("Voracious Gromp")
    gromp.turn_keywords.append("HUNT 2")
    assert gromp.keyword_value("HUNT") == 5


def test_level_follows_the_xp_of_whoever_controls_the_card():
    """§824.1.c.1: 'If the controller of the card with Level changes, then the
    Dependent Ability will be rendered Active or Inactive based on the new
    controller's XP.' Gemhand Hunter: 'LEVEL 6[>] I have +1 [might].'"""
    loop, a, b = setup(active="A")
    hunter = unit("Gemhand Hunter")
    loop.gs.battlefields[0].add_unit("B", hunter)
    loop.gs.add_xp("B", 6)
    loop._recompute_passives()
    assert hunter.might == 3
    loop._take_control(hunter, "A")
    loop._recompute_passives()
    assert hunter.might == 2
    loop.gs.add_xp("A", 6)
    loop._recompute_passives()
    assert hunter.might == 3


def test_backline_units_take_lethal_after_every_other_unit():
    """§826.4.b: 'Units with Backline are invalid assignments until all units
    without Backline have lethal damage assigned to them.'"""
    from riftbound.core.combat import _ordered_targets
    pyke, other_backline = unit("Pyke Returned"), unit("Pyke Returned")
    front = unit("front", 2)
    order = _ordered_targets([pyke, front, other_backline])
    assert order[0] is front and {id(u) for u in order[1:]} == {id(pyke), id(other_backline)}


def test_deploy_gear_can_be_played_to_any_battlefield():
    """§830.1.b.1: 'Deploy grants permission for Gear to be played to any
    Battlefield, including enemy occupied and open battlefields.' The Good
    Stuff, with an enemy at one battlefield and nobody at the other."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("B", unit("enemy", 2))
    a.hand.append(card("The Good Stuff"))
    offered = [lb for lb in labels(loop, "A") if "The Good Stuff" in lb]
    assert offered == ["Play gear The Good Stuff @BF0", "Play gear The Good Stuff @BF1"]


# --- Replacement effects (§367-373) and layers (§475-482): the decks' cards ---

def test_ki_barrier_prevents_the_bonus_damage_too():
    """§438.1.a.1: 'Prevent includes any applied Bonus Damage'; §438.3: the
    Prevent Value goes down by what it prevented. Hextech Ray at Void Gate
    deals 3 + 1 to a unit under Ki Barrier: none dealt, 3 left to prevent."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.card = card("Void Gate")
    target = unit("target", 2)
    bf.add_unit("B", target)
    target.damage_shield = 7                       # Ki Barrier resolved on it
    a.hand.append(card("Hextech Ray"))
    act(loop, "A", "Cast Hextech Ray @BF0")
    assert target.damage == 0 and target.damage_shield == 3 and target in bf.units_B
    assert target.damaged_turn != loop.gs.turn     # §438.4: not dealt at all


def test_a_minimum_of_one_is_snapshotted_as_it_applies():
    """§479.4.b: '-4 [M] to a min of 1 this turn' on a 2 [M] unit 'will
    generate -1 [M] this turn'. Thousand-Tailed Watcher's -3 to a minimum of 1
    on a 2 [might] enemy, then +3: 4, not 1."""
    loop, a, b = setup(active="A")
    enemy = unit("enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop._play_unit(card("Thousand-Tailed Watcher"), "A")
    assert enemy.might == 1
    enemy.temporary_might += 3
    assert enemy.might == 4


def test_a_base_might_set_is_applied_before_the_arithmetic():
    """§479.2 before §479.4: Dragon Form 'Its base Might becomes 5 this turn'
    on a 3 [might] unit with a buff and -1 this turn: 5 + 1 - 1."""
    loop, a, b = setup(active="A")
    u = unit("u", 3)
    u.might_counters, u.temporary_might = 1, -1
    loop.gs.battlefields[0].add_unit("A", u)
    a.hand.append(card("Dragon Form"))
    choices(loop, {})
    act(loop, "A", "Cast Dragon Form")
    assert u.might == 5
    u.temporary_might -= 2
    assert u.might == 3


def test_switcheroo_swaps_and_later_changes_still_apply():
    """Switcheroo: 'Swap the Might of two units at the same battlefield this
    turn.' (arithmetic, §479.4); a later +1 applies on top (§482 timestamps)."""
    loop, a, b = setup(active="A")
    x, y = unit("x", 2), unit("y", 5)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", x)
    bf.add_unit("B", y)
    a.hand.append(card("Switcheroo"))
    act(loop, "A", "Cast Switcheroo @BF0")
    assert (x.might, y.might) == (5, 2)
    x.temporary_might += 1
    assert x.might == 6
