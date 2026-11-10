"""BACKLOG G3 "Up to N" picks (§355.13): "up to N" / "any number" lets the
player take fewer than the baseline, none at all, or more (up to N): each pick
of such a choice offers NO_MORE too (GameLoop.choose_many `up_to`, the card's
`up_to` spec flag). The baseline of a harmful "up to" takes no unit of mine."""

from __future__ import annotations

from riftbound.ai.coach import option_text
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import NO_MORE
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _cast_now, _play_spell, _setup, _unit
from test_corpus_vendetta import _attack_at


def _name(o):
    if isinstance(o, tuple):
        o = o[-1]
    return getattr(getattr(o, "card", o), "name", None)


class _Picks:
    """A chooser for "up to N" picks: the named options in turn (by name: a
    spell's choices are made on a copy of the game), then NO_MORE. `modes`:
    the modes a "choose two" takes."""

    def __init__(self, *names, modes=()):
        self.names, self.modes, self.asked = list(names), modes, 0

    def __call__(self, _loop, kind, side, options, default, source):
        if kind == "mode" and self.modes:
            return next(i for i, o in enumerate(options) if o in self.modes)
        if not any(o is NO_MORE for o in options):
            return None
        self.asked += 1
        if self.names:
            hit = next((i for i, o in enumerate(options) if _name(o) == self.names[0]), None)
            if hit is not None:
                self.names.pop(0)
                return hit
        return next(i for i, o in enumerate(options) if o is NO_MORE)


def test_choose_many_up_to_takes_fewer_none_or_more():
    loop, a, b = _setup()
    x, y, z = _unit("X", 1), _unit("Y", 1), _unit("Z", 1)
    assert loop.choose_many("target:t", "A", [x, y, z], [x], up_to=2) == [x]   # no chooser
    loop.chooser = lambda *_: None                     # the baseline's answers
    assert loop.choose_many("target:t", "A", [x, y, z], [x], up_to=2) == [x]
    loop.chooser = _Picks()
    assert loop.choose_many("target:t", "A", [x, y, z], [x], up_to=2) == []
    loop.chooser = picks = _Picks("Y", "Z", "X")
    assert loop.choose_many("target:t", "A", [x, y, z], [x], up_to=2) == [y, z]
    assert picks.asked == 2                            # N taken: no more asked
    loop.chooser = picks = _Picks()
    assert loop.choose_many("target:t", "A", [x, y, z], [x, y]) == [x, y]
    assert picks.asked == 0                            # not "up to": no NO_MORE


def test_singularity_baseline_spares_my_unit_and_may_hit_none_or_both():
    """'Deal 6 to each of up to two units.'"""
    def board():
        loop, a, b = _setup()
        enemy, mine = _unit("Enemy", 3), _unit("Mine", 3)
        loop.gs.battlefields[0].add_unit("B", enemy)
        loop.gs.battlefields[0].add_unit("A", mine)
        return loop, a, enemy, mine
    loop, a, enemy, mine = board()
    _play_spell(loop, a, "Singularity")
    assert enemy.card in loop.gs.B.trash and mine.damage == 0
    loop, a, enemy, mine = board()
    loop.chooser = _Picks()
    _play_spell(loop, a, "Singularity")                # none: played, nothing hit
    assert any(c.name == "Singularity" for c in a.trash)
    assert enemy.damage == 0 and mine.damage == 0
    loop, a, enemy, mine = board()
    loop.chooser = _Picks("Enemy", "Mine")
    _play_spell(loop, a, "Singularity")
    assert enemy.card in loop.gs.B.trash and mine.card in a.trash


def test_piercing_light_up_to_one_other_unit_is_mine_only_if_chosen():
    """'Deal 2 to a unit at a battlefield, then deal 2 to up to one other unit':
    only my unit is left for the second (the BACKLOG example)."""
    loop, a, b = _setup()
    enemy, mine = _unit("Enemy", 2), _unit("Mine", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.gs.battlefields[0].add_unit("A", mine)
    _play_spell(loop, a, "Piercing Light")
    assert enemy.card in b.trash and mine.damage == 0
    loop, a, b = _setup()
    enemy, mine = _unit("Enemy", 2), _unit("Mine", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.chooser = _Picks("Mine")
    _play_spell(loop, a, "Piercing Light")
    assert enemy.card in b.trash and mine.damage == 2


def test_kinkou_monk_buffs_just_one_of_two():
    """'When you play me, buff up to two other friendly units.'"""
    loop, a, b = _setup()
    one, two = _unit("One", 1), _unit("Two", 1)
    a.base_units.extend([one, two])
    loop.chooser = _Picks("One")
    loop._play_unit(CARD_REGISTRY["Kinkou Monk"].instantiate(), "A")
    assert one.might_counters == 1 and two.might_counters == 0


def test_shadows_of_the_past_returns_just_one():
    """'Return up to 2 units from trashes to their owners' hands.'"""
    loop, a, b = _setup()
    u1, u2 = UnitCard(name="U1", might=1), UnitCard(name="U2", might=1)
    a.trash.extend([u1, u2])
    loop.chooser = _Picks("U2")
    _cast_now(loop, a, "Shadows of the Past")
    assert u2 in a.hand and u1 in a.trash


def test_remember_the_fallen_plays_just_the_one_chosen():
    """'Play up to 3 units and/or gear from your trash ...': no others stand in."""
    loop, a, b = _setup()
    u1, u2, u3 = (UnitCard(name=n, might=1, cost_energy=1) for n in ("U1", "U2", "U3"))
    a.trash.extend([u1, u2, u3])
    loop.chooser = _Picks("U2")
    _cast_now(loop, a, "Remember the Fallen")
    assert [u.card for u in a.base_units] == [u2] and u1 in a.trash and u3 in a.trash


def test_flash_moves_just_one_of_two():
    """'Move up to 2 friendly units to base.'"""
    loop, a, b = _setup()
    stay, go = _unit("Stay", 2), _unit("Go", 2)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", stay)
    bf.add_unit("A", go)
    loop.chooser = _Picks("Go")
    _play_spell(loop, a, "Flash")
    assert go in a.base_units and stay in bf.units_A


def test_elder_dragon_may_skip_a_location():
    """'... choose up to one enemy unit at each location. Deal 1 to them.'"""
    loop, a, b = _setup()
    e0, e1, home = _unit("E0", 9), _unit("E1", 9), _unit("Home", 9)
    loop.gs.battlefields[0].add_unit("B", e0)
    loop.gs.battlefields[1].add_unit("B", e1)
    b.base_units.append(home)
    loop.chooser = _Picks("E0", "Home")
    loop._play_unit(CARD_REGISTRY["Elder Dragon"].instantiate(), "A")
    assert e0.card in b.trash and home.card in b.trash
    assert e1 in loop.gs.battlefields[1].units_B and e1.damage == 0


def test_hexplosive_minefield_kills_just_one_bomb():
    """'Kill any number of friendly Bomb tokens. At end of turn, play that many
    Bomb tokens to a single battlefield.'"""
    loop, a, b = _setup()
    for _ in range(2):
        loop._play_token("Bomb", "A")
    # One at each battlefield (a Bomb's DEATHKNELL kills the other Bombs here).
    loop.gs.battlefields[1].gear_for("A").append(loop.gs.battlefields[0].gear_for("A").pop())

    def bombs():
        return sum(1 for bf in loop.gs.battlefields for dg in bf.gear_for("A") if dg.card.name == "Bomb")
    assert bombs() == 2
    loop.chooser = _Picks("Bomb")
    _cast_now(loop, a, "Hexplosive Minefield")
    assert bombs() == 1
    loop._resolve_delayed_effects()
    assert bombs() == 2


def test_encore_gives_up_to_two_units_not_all():
    """Encore's 'Give up to two units each +1 [Might] this turn' (was: every
    unit here)."""
    loop, a, b = _setup()
    one, two, three = _unit("One", 1), _unit("Two", 1), _unit("Three", 1)
    for u in (one, two, three):
        loop.gs.battlefields[0].add_unit("A", u)
    loop.chooser = _Picks("One", "Three", modes=(2, 3))
    _play_spell(loop, a, "Encore")
    assert (one.might, two.might, three.might) == (2, 1, 2)


def test_corrupted_dragon_may_leave_one_enemy():
    """'When I attack, you may move any number of enemy units here each with 5
    [might] or less to their base.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Corrupted Dragon"))
    small, other = _unit("Small", 2), _unit("Other", 3)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.gs.battlefields[0].add_unit("B", other)
    loop.chooser = _Picks("Small")
    _attack_at(loop)
    assert small in b.base_units and other not in b.base_units


def test_decree_of_discord_returns_just_one():
    """'Return any number of enemy Order units with total Might 5 or less to
    their owners' hands.'"""
    loop, a, b = _setup()
    two = UnitInPlay(card=UnitCard(name="Two", might=2, domain=Domain.ORDER), ready=True)
    three = UnitInPlay(card=UnitCard(name="Three", might=3, domain=Domain.ORDER), ready=True)
    loop.gs.battlefields[0].add_unit("B", two)
    loop.gs.battlefields[0].add_unit("B", three)
    loop.chooser = _Picks("Two")
    _play_spell(loop, a, "Decree of Discord")
    assert two.card in b.hand and three in loop.gs.battlefields[0].units_B


def test_acceleration_gate_readies_just_one():
    """'Ready up to 4 units, gear, and/or runes.'"""
    loop, a, b = _setup()
    one = UnitInPlay(card=UnitCard(name="One", might=1), ready=False)
    two = UnitInPlay(card=UnitCard(name="Two", might=1), ready=False)
    a.base_units.extend([one, two])
    loop.chooser = _Picks("One")
    _cast_now(loop, a, "Acceleration Gate")
    assert one.ready and not two.ready


def test_coach_names_no_more():
    loop, a, b = _setup()
    assert option_text(loop.gs, "A", NO_MORE) == "Nessun altro"
