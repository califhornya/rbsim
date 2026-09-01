"""Rules-based correctness tests for the combat keywords ASSAULT / SHIELD / TANK
(Core Rules §733, §740, §741). These assert the actual COMBAT EFFECT, not just that
the keyword is recognized — the gap MECHANICS.md flags for "recognized != correct".

Probe: `resolve_might_combat` sets each unit's transient combat bonus, then
`stats.damage_to_B` is the total might A's units deal (base + the bonus that applies
for A's role that combat). ASSAULT boosts an ATTACKER; SHIELD boosts a DEFENDER; so
A's contribution changes with `attacker_side`. A big might-10 absorber on B ensures
all incoming damage is assigned (assigned == incoming).
"""

from __future__ import annotations

from riftbound.core.cards import UnitCard
from riftbound.core.combat import (
    UnitInPlay,
    _apply_damage,
    _ordered_targets,
    resolve_might_combat,
)


def _unit(name: str, might: int, keywords=None) -> UnitInPlay:
    return UnitInPlay(UnitCard(name=name, might=might, keywords=list(keywords or [])))


def _damage_dealt_by_A(unit_kw_might, keywords, attacker_side):
    a = _unit("Probe", unit_kw_might, keywords)
    absorber = _unit("Wall", 10)
    stats = resolve_might_combat([a], [absorber], attacker_side=attacker_side)
    return stats.damage_to_B


# --- ASSAULT §733: +X might WHILE AN ATTACKER only; bare = 1 (§733.1.b.3) ---

def test_assault_applies_only_when_attacking():
    assert _damage_dealt_by_A(2, ["ASSAULT 2"], "A") == 4   # attacker: +2
    assert _damage_dealt_by_A(2, ["ASSAULT 2"], "B") == 2   # defender: no assault


def test_assault_bare_is_plus_one():
    assert _damage_dealt_by_A(2, ["ASSAULT"], "A") == 3


# --- SHIELD §740: +X might WHILE A DEFENDER only; bare = 1 ---

def test_shield_applies_only_when_defending():
    assert _damage_dealt_by_A(2, ["SHIELD 2"], "B") == 4    # defender: +2
    assert _damage_dealt_by_A(2, ["SHIELD 2"], "A") == 2    # attacker: no shield


def test_shield_bare_is_plus_one():
    assert _damage_dealt_by_A(2, ["SHIELD"], "B") == 3


def test_assault_boost_changes_lethality():
    # might-1 attacker with ASSAULT 2 deals 3 -> kills a might-3 defender it
    # could not kill at base might.
    attacker = _unit("Blade", 1, ["ASSAULT 2"])
    defender = _unit("Bruiser", 3)
    stats = resolve_might_combat([attacker], [defender], attacker_side="A")
    assert stats.kills_A == 1                        # the defender died


def test_shield_lets_defender_survive():
    # might-2 defender with SHIELD 2 (effective 4) survives 2 incoming damage;
    # the same unit attacking (shield inactive) dies to it.
    defender = _unit("Warden", 2, ["SHIELD 2"])
    attacker = _unit("Striker", 2)
    stats = resolve_might_combat([defender], [attacker], attacker_side="B")
    assert defender not in stats.dead_A              # shield kept it alive

    d2 = _unit("Warden", 2, ["SHIELD 2"])
    stats2 = resolve_might_combat([d2], [_unit("Striker", 2)], attacker_side="A")
    assert d2 in stats2.dead_A                        # attacking: no shield -> dead


# --- TANK §741 / §460.2.c: must be assigned lethal FIRST ---

def test_tank_ordered_first_for_damage():
    normal = _unit("Soldier", 2)
    tank = _unit("Bulwark", 2, ["TANK"])
    order = _ordered_targets([normal, tank])
    assert order[0] is tank                          # tank sorts to the front


def test_tank_absorbs_lethal_before_ally():
    normal = _unit("Soldier", 2)
    tank = _unit("Bulwark", 2, ["TANK"])
    # exactly lethal for one 2-might unit: the TANK must take it, ally untouched.
    kills, assigned = _apply_damage([normal, tank], 2)
    assert kills == 1
    assert tank.damage == 2 and normal.damage == 0
