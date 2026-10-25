"""Damage rules (GameLoop._take_damage) for spells, abilities and combat: Bonus
Damage (Annie Fiery, Ravenborn Tome), prevention (Unyielding Spirit, Ki
Barrier, Esteemed Hierophant, Kayn), doubling (Lotus Trap), Imperial Decree;
combat-only rules (Galio, Orianna, Forbidding Waste, Crimson Pigeons, Dune
Surfer, Symbol of the Solari, Threshold of the Gray); Alpha Strike, Shakedown,
K'Sante Dauntless."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _u(name, might, keywords=None):
    return UnitInPlay(card=UnitCard(name=name, might=might, keywords=list(keywords or [])))


def _real(name):
    return UnitInPlay(card=CARD_REGISTRY[name].instantiate())


def _zap(loop, unit, amount, side="A", card=None):
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    EffectContext(loop, card or SpellCard(name="Zap"), me, them, loop.gs.battlefields[0], {}).damage_units([unit], amount)


def _cast(loop, name, side="A"):
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_card_effects(CARD_REGISTRY[name].instantiate(), loop.gs.battlefields[0], me, them)


def test_annie_adds_one_to_her_controllers_spell_damage():
    loop = _loop()
    loop.gs.A.base_units.append(_real("Annie Fiery"))
    enemy = _u("E", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _zap(loop, enemy, 2)
    assert enemy.damage == 3
    mine = _u("M", 9)
    loop.gs.battlefields[0].add_unit("A", mine)
    _zap(loop, mine, 2, side="B")
    assert mine.damage == 2


def test_ravenborn_tome_bonus_goes_to_the_next_spell():
    loop = _loop()
    enemy = _u("E", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    REGISTRY["next_spell_bonus_damage"](EffectContext(loop, GearCard(name="Tome"), loop.gs.A, loop.gs.B,
                                                      loop.gs.battlefields[0], {}), {})
    spell = SpellCard(name="Bolt")
    loop._spell_played(spell, loop.gs.A)
    _zap(loop, enemy, 2, card=spell)
    assert enemy.damage == 3
    later = SpellCard(name="Later")
    loop._spell_played(later, loop.gs.A)
    _zap(loop, enemy, 2, card=later)
    assert enemy.damage == 5


def test_unyielding_spirit_prevents_spell_damage_not_combat():
    loop = _loop()
    _cast(loop, "Unyielding Spirit", side="B")
    unit = _u("U", 5)
    loop.gs.battlefields[0].add_unit("B", unit)
    _zap(loop, unit, 4)
    assert unit.damage == 0
    assert loop._take_damage(unit, 3, "combat") == 3


def test_ki_barrier_absorbs_seven():
    loop = _loop()
    unit = _u("U", 5)
    loop.gs.battlefields[0].add_unit("A", unit)
    loop.gs.battlefields[0].add_unit("B", _u("Big", 9))
    _cast(loop, "Ki Barrier")
    _zap(loop, unit, 4, side="B")
    _zap(loop, unit, 4, side="B")
    assert unit.damage == 1 and unit in loop.gs.battlefields[0].units_A


def test_hierophant_ignores_enemy_spells_with_seven_runes():
    loop = _loop()
    hiero = _real("Esteemed Hierophant")
    loop.gs.battlefields[0].add_unit("B", hiero)
    loop.gs.B.rune_pool[Domain.CALM] = [Rune(domain=Domain.CALM) for _ in range(7)]
    loop._recompute_passives()
    _zap(loop, hiero, 2)
    assert hiero.damage == 0
    loop.gs.B.rune_pool[Domain.CALM] = [Rune(domain=Domain.CALM) for _ in range(6)]
    loop._recompute_passives()
    _zap(loop, hiero, 2)
    assert hiero.damage == 2


def test_lotus_trap_doubles_and_imperial_decree_kills():
    loop = _loop()
    enemy = _u("E", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast(loop, "Lotus Trap")
    _zap(loop, enemy, 3)
    assert enemy.damage == 6
    other = _u("O", 9)
    loop.gs.battlefields[1].add_unit("B", other)
    _cast(loop, "Imperial Decree")
    EffectContext(loop, SpellCard(name="Z"), loop.gs.A, loop.gs.B, loop.gs.battlefields[1], {}).damage_units([other], 1)
    assert other not in loop.gs.battlefields[1].units_B


def test_kayn_takes_no_damage_after_moving_twice():
    loop = _loop()
    kayn = _real("Kayn Unleashed")
    loop.gs.battlefields[0].add_unit("B", kayn)
    kayn.moves_this_turn = 2
    _zap(loop, kayn, 3)
    assert kayn.damage == 0


def _fight(loop, attacker="A"):
    loop._phase_combat_and_conquer_single(0, attacker)


def test_galio_deals_no_combat_damage_and_orianna_needs_gear():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    galio, foe = _real("Galio Indefatigable"), _u("Foe", 3)
    bf0.add_unit("A", galio)
    bf0.add_unit("B", foe)
    _fight(loop)
    assert foe in bf0.units_B and foe.damage == 0
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    ori, foe = _real("Orianna Exquisite"), _u("Foe", 2)
    ori.gear = [GearCard(name="Gear")]
    bf0.add_unit("A", ori)
    bf0.add_unit("B", foe)
    _fight(loop)
    assert foe not in bf0.units_B


def test_forbidding_waste_weakens_a_lone_defender():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = CARD_REGISTRY["Forbidding Waste"].instantiate()
    atk, dfn = _u("Atk", 3), _u("Def", 4)
    bf0.add_unit("A", atk)
    bf0.add_unit("B", dfn)
    _fight(loop)
    assert dfn not in bf0.units_B and atk in bf0.units_A    # 4 - 2 = 2 < 3


def test_crimson_pigeons_hit_harder_attacking_with_another():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    pigeons = _real("Crimson Pigeons")                     # 3 Might
    bf0.add_unit("A", pigeons)
    bf0.add_unit("A", _u("Friend", 1))
    wall = _u("Wall", 6)
    bf0.add_unit("B", wall)
    _fight(loop)
    assert wall not in bf0.units_B                          # 3 + 2 + 1 = 6


def test_dune_surfer_ignores_tank():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", _real("Dune Surfer"))
    tank, soft = _u("Tank", 9, ["TANK"]), _u("Soft", 1)
    bf0.add_unit("B", tank)
    bf0.add_unit("B", soft)
    _fight(loop)
    assert soft not in bf0.units_B


def test_symbol_of_the_solari_recalls_everyone_on_a_tie():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    loop.gs.A.base_gear.append(CARD_REGISTRY["Symbol of the Solari"].instantiate())
    atk, dfn = _u("Atk", 2), _u("Def", 5)
    dfn.stunned = True                                      # both survive: a tie
    bf0.add_unit("A", atk)
    bf0.add_unit("B", dfn)
    _fight(loop)
    assert atk in loop.gs.A.base_units and dfn in loop.gs.B.base_units


def test_threshold_of_the_gray_gives_both_fighters_energy():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = CARD_REGISTRY["Threshold of the Gray"].instantiate()
    bf0.add_unit("A", _u("Atk", 2))
    bf0.add_unit("B", _u("Def", 2))
    _fight(loop)
    assert loop.gs.A.energy == 1 and loop.gs.B.energy == 1


def test_alpha_strike_splits_might_and_gains_xp_per_kill():
    loop = _loop()
    loop.gs.A.base_units.append(_u("Striker", 5))
    a, b, c = _u("A1", 2), _u("B1", 3), _u("C1", 9)
    loop.gs.battlefields[0].add_unit("B", a)
    loop.gs.battlefields[0].add_unit("B", b)
    loop.gs.battlefields[1].add_unit("B", c)
    _cast(loop, "Alpha Strike")
    assert a not in loop.gs.battlefields[0].units_B and b not in loop.gs.battlefields[0].units_B
    assert loop.gs.get_xp("A") == 2


def test_shakedown_draws_when_the_damage_would_kill():
    loop = _loop()
    small = _u("Small", 4)
    loop.gs.battlefields[0].add_unit("B", small)
    _cast(loop, "Shakedown")
    assert len(loop.gs.A.hand) == 2 and small.damage == 0
    loop = _loop()
    big = _u("Big", 9)
    loop.gs.battlefields[0].add_unit("B", big)
    _cast(loop, "Shakedown")
    assert big.damage == 6 and not loop.gs.A.hand


def test_ksante_doubles_a_shield_here():
    loop = _loop()
    ksante = _real("K'Sante Dauntless")
    loop.gs.battlefields[0].add_unit("A", ksante)
    loop._resolve_triggered_effects(ksante.card, "on_defend", loop.gs.battlefields[0], loop.gs.A,
                                    loop.gs.B, context_extra={"battlefield": loop.gs.battlefields[0]})
    assert ksante.keyword_value("SHIELD") == 2
