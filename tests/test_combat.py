from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay


def test_might_combat_resolves_and_tracks_kills():
    bf = Battlefield()
    bf.add_unit("A", UnitInPlay(UnitCard(name="Striker", might=2)))
    bf.add_unit("A", UnitInPlay(UnitCard(name="Scout", might=1)))
    bf.add_unit("B", UnitInPlay(UnitCard(name="Guard", might=2, keywords=["Guard"])))
    bf.add_unit("B", UnitInPlay(UnitCard(name="Aux", might=1)))

    stats = bf.resolve_combat_might()

    assert bf.count("A") == 0
    assert bf.count("B") == 0
    assert stats.kills_A == 2
    assert stats.kills_B == 2
    assert bf.kills_A == 2
    assert bf.kills_B == 2


def test_guard_priority_absorbs_spell_damage_first():
    bf = Battlefield()
    guard = UnitInPlay(UnitCard(name="Shieldbearer", might=3, keywords=["Guard"]))
    ally = UnitInPlay(UnitCard(name="Archer", might=1))
    bf.add_unit("B", guard)
    bf.add_unit("B", ally)

    _, _ = bf.apply_spell_damage("B", 2)

    assert bf.count("B") == 2
    assert guard.damage == 2          # damage stays until the turn ends (§317.2.b)
    assert ally.damage == 0

    bf.apply_spell_damage("B", 3)     # 1 finishes the guard, 1 kills the archer

    assert bf.count("B") == 0
    assert guard not in bf.units_B


def test_kill_order_kills_the_most_might():
    from riftbound.core.combat import kill_order
    two, three, five = (UnitInPlay(UnitCard(name=n, might=m)) for n, m in (("2", 2), ("3", 3), ("5", 5)))
    # 5 damage: the 5 alone or 2 + 3 kill the same Might; two kills win the tie.
    assert kill_order([five, two, three], 5)[:2] == [three, two]
    # 8 damage: 5 + 3 beats 5 + 2 and 2 + 3.
    assert kill_order([two, three, five], 8)[:2] == [five, three]
    # 4 damage: the 3 beats the 2.
    assert kill_order([two, three, five], 4)[0] is three
    # Nothing killable: list order.
    assert kill_order([five, three], 2) == [five, three]
