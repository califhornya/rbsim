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

    bf.apply_spell_damage("B", 2)

    assert bf.count("B") == 2
    assert guard.damage == 0
    assert ally.damage == 0

    bf.apply_spell_damage("B", 3)

    assert bf.count("B") == 1
    assert guard not in bf.units_B