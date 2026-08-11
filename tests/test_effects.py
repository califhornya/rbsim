"""Regression tests for the Round 4 effects subsystems.

Each test injects a synthetic CardSpec into CARD_REGISTRY (cleaned up afterward)
so it can exercise a trigger/effect path without depending on the live corpus.
"""

import random

import pytest

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _make_loop() -> GameLoop:
    player_a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    player_b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=player_a, B=player_b)
    return GameLoop(gs)


def _register(name: str, effects: list, might: int = 2) -> None:
    CARD_REGISTRY[name] = CardSpec.from_dict(
        {"name": name, "category": "UNIT", "might": might, "effects": effects}
    )


@pytest.fixture
def cleanup_registry():
    added: list[str] = []
    yield added
    for name in added:
        CARD_REGISTRY.pop(name, None)


def test_passive_self_buff_gated_on_condition(cleanup_registry):
    name = "TST Passive Yi"
    _register(name, [{
        "effect": "grant_might", "trigger": "passive", "amount": 4,
        "condition": {"type": "controller_has_xp_at_least", "params": {"n": 3}},
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    unit = UnitInPlay(UnitCard(name=name, might=2), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)

    # Condition false (0 XP) → no passive bonus.
    loop._recompute_passives()
    assert unit.might == 2

    # Condition true (3 XP) → +4.
    loop.gs.add_xp("A", 3)
    loop._recompute_passives()
    assert unit.might == 6


def test_passive_anthem_buffs_all_friendlies(cleanup_registry):
    anthem = "TST Anthem"
    grunt = "TST Grunt"
    _register(anthem, [{
        "effect": "grant_might", "trigger": "passive", "amount": 1,
        "target": "actor", "scope": "all",
    }], might=3)
    _register(grunt, [], might=2)
    cleanup_registry.extend([anthem, grunt])

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    u_anthem = UnitInPlay(UnitCard(name=anthem, might=3), ready=True)
    u_grunt = UnitInPlay(UnitCard(name=grunt, might=2), ready=True)
    bf.units_A.extend([u_anthem, u_grunt])

    loop._recompute_passives()
    assert u_anthem.might == 4  # anthem buffs itself too
    assert u_grunt.might == 3


def test_passive_recompute_clears_when_condition_drops(cleanup_registry):
    name = "TST Pack Tactics"
    _register(name, [{
        "effect": "grant_might", "trigger": "passive", "amount": 2,
        "condition": {"type": "you_have_n_or_more_units_here", "params": {"n": 2}},
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    unit = UnitInPlay(UnitCard(name=name, might=2), ready=True)
    bf.units_A.append(unit)

    loop._recompute_passives()
    assert unit.might == 2  # alone — condition false

    ally = UnitInPlay(UnitCard(name="TST Ally", might=1), ready=True)
    bf.units_A.append(ally)
    loop._recompute_passives()
    assert unit.might == 4  # 2 units here — condition true

    bf.units_A.remove(ally)
    loop._recompute_passives()
    assert unit.might == 2  # overlay cleared when condition drops


def test_passive_keyword_grant(cleanup_registry):
    name = "TST Stoneguard"
    _register(name, [{
        "effect": "give_keyword", "trigger": "passive", "keyword": "TANK",
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    unit = UnitInPlay(UnitCard(name=name, might=2, keywords=[]), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)

    assert not unit.has_keyword("TANK")
    loop._recompute_passives()
    assert unit.has_keyword("TANK")


def test_passive_valued_keyword_feeds_keyword_value(cleanup_registry):
    name = "TST Bulwark"
    _register(name, [{
        "effect": "give_keyword", "trigger": "passive",
        "target": "all_friendly_units_here", "keyword": "SHIELD 2",
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    src = UnitInPlay(UnitCard(name=name, might=2, keywords=[]), ready=True)
    ally = UnitInPlay(UnitCard(name="TST Pal", might=1, keywords=[]), ready=True)
    bf.units_A.extend([src, ally])

    loop._recompute_passives()
    assert ally.has_keyword("SHIELD")
    assert ally.keyword_value("SHIELD") == 2


def test_activated_tap_ability(cleanup_registry):
    name = "TST Energy Font"
    _register(name, [{
        "effect": "gain_energy", "trigger": "activated", "cost": "tap", "amount": 2,
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    unit = UnitInPlay(UnitCard(name=name, might=2), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)
    loop.gs.A.energy = 0

    # Index 0 is this unit's only activated ability.
    loop._apply_activated_ability(loop.gs.A, loop.gs.B, 0)
    assert loop.gs.A.energy == 2
    assert unit.ready is False

    # Already tapped → second activation is a no-op (cost unaffordable).
    loop._apply_activated_ability(loop.gs.A, loop.gs.B, 0)
    assert loop.gs.A.energy == 2


def test_equip_via_activated_path():
    from riftbound.core.cards import GearCard

    loop = _make_loop()
    unit = UnitInPlay(UnitCard(name="Bearer", might=2), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)
    gear = GearCard(name="TST Blade", cost_energy=0)
    loop.gs.A.base_gear.append(gear)

    abilities = loop.activatable_abilities("A")
    equip_idx = next(i for i, e in enumerate(abilities) if e["type"] == "equip")
    loop._apply_activated_ability(loop.gs.A, loop.gs.B, equip_idx)

    assert gear in unit.gear
    assert gear not in loop.gs.A.base_gear


def test_static_cost_reduction(cleanup_registry):
    name = "TST Cheap Recruit"
    _register(name, [{
        "effect": "reduce_cost", "trigger": "cost_modifier", "amount": 2,
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    card = UnitCard(name=name, might=2)
    assert loop._cost_reduction(card, loop.gs.A) == 2


def test_conditional_cost_reduction(cleanup_registry):
    name = "TST XP Discount"
    _register(name, [{
        "effect": "reduce_cost", "trigger": "cost_modifier", "amount": 1,
        "condition": {"type": "controller_has_xp_at_least", "params": {"n": 3}},
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    card = UnitCard(name=name, might=2)
    assert loop._cost_reduction(card, loop.gs.A) == 0  # 0 XP — condition false
    loop.gs.add_xp("A", 3)
    assert loop._cost_reduction(card, loop.gs.A) == 1  # condition true


def test_predict_reorders_best_to_top(cleanup_registry):
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    # Top of deck = end of list. Seed unsorted mights.
    loop.gs.A.deck.cards = [
        UnitCard(name="m1", might=1), UnitCard(name="m5", might=5),
        UnitCard(name="m3", might=3),
    ]
    ctx = EffectContext(loop, SpellCard(name="Scry"), loop.gs.A, loop.gs.B,
                        loop.gs.battlefields[0])
    REGISTRY["predict"](ctx, {"amount": 3})
    # Highest might (5) should now be drawn next (top == last element).
    assert loop.gs.A.deck.cards[-1].might == 5


def test_reveal_and_choose_takes_best(cleanup_registry):
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    loop.gs.A.deck.cards = [
        UnitCard(name="m2", might=2), UnitCard(name="m7", might=7),
        UnitCard(name="m4", might=4),
    ]
    ctx = EffectContext(loop, SpellCard(name="Dig"), loop.gs.A, loop.gs.B,
                        loop.gs.battlefields[0])
    REGISTRY["reveal_and_choose"](ctx, {"amount": 3})
    assert any(c.might == 7 for c in loop.gs.A.hand)
    assert len(loop.gs.A.deck.cards) == 2  # the other two recycled to bottom


def test_play_from_trash_unit_to_base():
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    loop.gs.A.trash.append(UnitCard(name="Revenant", might=4))
    ctx = EffectContext(loop, SpellCard(name="Raise"), loop.gs.A, loop.gs.B,
                        loop.gs.battlefields[0])
    REGISTRY["play_from_trash"](ctx, {"target": "actor", "count": 1})
    assert any(u.card.name == "Revenant" for u in loop.gs.A.base_units)
    assert not loop.gs.A.trash


def test_banish_from_trash():
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    loop.gs.A.trash.append(UnitCard(name="Doomed", might=1))
    ctx = EffectContext(loop, SpellCard(name="Exile"), loop.gs.A, loop.gs.B,
                        loop.gs.battlefields[0])
    REGISTRY["banish_card"](ctx, {"from": "trash", "count": 1})
    assert any(c.name == "Doomed" for c in loop.gs.A.banished)
    assert not loop.gs.A.trash


def test_take_control_moves_enemy_unit():
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    enemy = UnitInPlay(UnitCard(name="Captured", might=3), ready=True)
    bf.units_B.append(enemy)
    ctx = EffectContext(loop, SpellCard(name="Possess"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["take_control"](ctx, {})
    assert enemy in bf.units_A
    assert enemy not in bf.units_B


def test_death_replacement_via_guardian_angel():
    loop = _make_loop()
    ga = CARD_REGISTRY["Guardian Angel"].instantiate()
    unit = UnitInPlay(UnitCard(name="Protected", might=3), ready=True)
    unit.gear.append(ga)
    unit.damage = 5  # lethal

    replaced = loop._try_replace_death(unit, "A")
    assert replaced is True
    assert unit in loop.gs.A.base_units
    assert unit.ready is False
    assert unit.damage == 0
    assert ga in loop.gs.A.trash      # the gear is destroyed instead of the unit
    assert ga not in unit.gear


def test_no_death_replacement_without_source():
    loop = _make_loop()
    unit = UnitInPlay(UnitCard(name="Plain", might=3), ready=True)
    unit.damage = 5
    assert loop._try_replace_death(unit, "A") is False


def test_spend_buff_removes_counters():
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    unit = UnitInPlay(UnitCard(name="Buffed", might=2), ready=True)
    unit.might_counters = 1
    bf.units_A.append(unit)

    ctx = EffectContext(loop, SpellCard(name="Spend"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["spend_buff"](ctx, {"count": 1, "target": "actor", "scope": "all"})
    assert unit.might_counters == 0


# --- KNOWN_ISSUES #16: chosen_unit must reach EITHER side, biased by intent ---

def test_chosen_unit_kill_hits_enemy_not_own(cleanup_registry):
    """A removal spell targeting `chosen_unit` must not auto-kill the caster's
    own unit — the enemy is the sane baseline pick."""
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    mine = UnitInPlay(UnitCard(name="Mine", might=3), ready=True)
    theirs = UnitInPlay(UnitCard(name="Theirs", might=3), ready=True)
    bf.units_A.append(mine)
    bf.units_B.append(theirs)

    ctx = EffectContext(loop, SpellCard(name="Kill"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["kill_unit"](ctx, {"target": "chosen_unit"})

    assert theirs not in bf.units_B          # enemy died
    assert mine in bf.units_A                # own unit spared
    assert theirs.card in loop.gs.B.trash


def test_chosen_unit_buff_hits_own_not_enemy(cleanup_registry):
    """A beneficial `chosen_unit` effect biases to a friendly unit."""
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    mine = UnitInPlay(UnitCard(name="Mine", might=2), ready=True)
    theirs = UnitInPlay(UnitCard(name="Theirs", might=2), ready=True)
    bf.units_A.append(mine)
    bf.units_B.append(theirs)

    ctx = EffectContext(loop, SpellCard(name="Pump"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["grant_temporary_might"](ctx, {"target": "chosen_unit", "amount": 2})

    assert mine.temporary_might == 2         # friendly buffed
    assert theirs.temporary_might == 0       # enemy untouched


# --- KNOWN_ISSUES #13: banish honors scope:all + card-type filter ---

def test_banish_all_units_from_trash_leaves_non_units():
    from riftbound.core.cards import SpellCard, GearCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    loop.gs.A.trash.extend([
        UnitCard(name="U1", might=1), GearCard(name="G1"), UnitCard(name="U2", might=1),
    ])
    ctx = EffectContext(loop, SpellCard(name="Sarcophagus"), loop.gs.A, loop.gs.B,
                        loop.gs.battlefields[0])
    REGISTRY["banish_card"](ctx, {"from": "trash", "scope": "all",
                                  "target_filter": {"is_unit": True}})
    assert sorted(c.name for c in loop.gs.A.banished) == ["U1", "U2"]
    assert [c.name for c in loop.gs.A.trash] == ["G1"]   # gear stays


# --- KNOWN_ISSUES #14: move_units_to_base honors an is_exhausted filter ---

def test_move_units_to_base_only_exhausted():
    from riftbound.core.cards import SpellCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    ready_u = UnitInPlay(UnitCard(name="Ready", might=2), ready=True)
    tired_u = UnitInPlay(UnitCard(name="Tired", might=2), ready=False)
    bf.units_A.extend([ready_u, tired_u])

    ctx = EffectContext(loop, SpellCard(name="KhaZix"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["move_units_to_base"](ctx, {"target_filter": {"is_exhausted": True}})

    assert tired_u in loop.gs.A.base_units   # exhausted moved
    assert ready_u in bf.units_A             # ready stayed


# --- KNOWN_ISSUES #17: kill_gear kills ONE filtered gear, not a board wipe ---

def test_kill_gear_single_energy_filter_enemy_first():
    from riftbound.core.cards import SpellCard, GearCard
    from riftbound.core.effects import REGISTRY

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    mine = UnitInPlay(UnitCard(name="Mine", might=2), ready=True)
    theirs = UnitInPlay(UnitCard(name="Theirs", might=2), ready=True)
    mine.gear.append(GearCard(name="MyGear", cost_energy=1))
    cheap = GearCard(name="CheapEnemyGear", cost_energy=1)
    dear = GearCard(name="DearEnemyGear", cost_energy=3)
    theirs.gear.extend([dear, cheap])
    bf.units_A.append(mine)
    bf.units_B.append(theirs)

    ctx = EffectContext(loop, SpellCard(name="Pickpocket"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["kill_gear"](ctx, {"target_filter": {"energy_at_most": 1}})

    # Exactly one gear killed: the enemy's cost<=1 gear (enemy-biased).
    assert cheap in loop.gs.B.trash
    assert dear in theirs.gear               # too expensive, untouched
    assert any(g.name == "MyGear" for g in mine.gear)  # own gear spared


# --- KNOWN_ISSUES #18: passive anthem honors target_filter ---

def test_passive_anthem_only_tokens(cleanup_registry):
    name = "TST Soul Shepherd"
    _register(name, [{
        "effect": "grant_might", "trigger": "passive", "amount": 1,
        "target": "all_friendly_units_here",
        "target_filter": {"is_token": True},
    }], might=2)
    cleanup_registry.append(name)

    loop = _make_loop()
    bf = loop.gs.battlefields[0]
    shepherd = UnitInPlay(UnitCard(name=name, might=2), ready=True)
    token = UnitInPlay(UnitCard(name="Sprite", might=1), ready=True)
    token.is_token = True
    normal = UnitInPlay(UnitCard(name="Regular", might=3), ready=True)
    bf.units_A.extend([shepherd, token, normal])

    loop._recompute_passives()
    assert token.might == 2      # token got +1
    assert normal.might == 3     # non-token untouched
