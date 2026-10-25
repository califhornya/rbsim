"""Equipment texts and WEAPONMASTER units: Experimental Hexplate ("I am a
Mech"), Rabadon's Deathcrown (Bonus Damage only while attached), Hand Hammer,
Skyfall of Areion, Blighted Battleaxe, "When you attach an Equipment to me"
(Jax Unrelenting, Aphelios), Ornn Forge God, Riven Shattered, Yone
Blademaster, Jax Grandmaster at Arms, Arise!, Azir Sovereign."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _u(name, might, tags=None):
    return UnitInPlay(card=UnitCard(name=name, might=might, tags=list(tags or [])))


def _fire(loop, card, trigger, bf=None, **extra):
    bf = bf or loop.gs.battlefields[0]
    loop._resolve_triggered_effects(card, trigger, bf, loop.gs.A, loop.gs.B,
                                    context_extra={"battlefield": bf, **extra})


def test_hexplate_makes_its_unit_a_mech():
    loop = _loop()
    unit = _u("U", 2)
    unit.gear = [_card("Experimental Hexplate")]
    loop.gs.battlefields[0].add_unit("A", unit)
    loop.gs.A.base_units.append(UnitInPlay(card=_card("Rumble Hotheaded")))
    loop._recompute_passives()
    assert "Mech" in unit.tags and unit.has_keyword("ASSAULT")


def test_rabadons_deathcrown_only_while_attached():
    loop = _loop()
    crown = _card("Rabadon's Deathcrown")
    enemy = _u("E", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop.gs.A.base_gear.append(crown)
    ctx = EffectContext(loop, SpellCard(name="Z"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    ctx.damage_units([enemy], 1)
    assert enemy.damage == 1
    loop.gs.A.base_gear.remove(crown)
    holder = _u("H", 2)
    holder.gear = [crown]
    loop.gs.A.base_units.append(holder)
    ctx.damage_units([enemy], 1)
    assert enemy.damage == 5


def test_hand_hammer_with_exactly_one_other_unit():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    unit = _u("U", 2)
    unit.gear = [_card("Hand Hammer")]                     # +1 Equipment bonus
    bf0.add_unit("A", unit)
    loop._recompute_passives()
    assert unit.might == 3
    bf0.add_unit("A", _u("Pal", 1))
    loop._recompute_passives()
    assert unit.might == 5


def test_skyfall_of_areion_makes_hold_effects_conquer_effects():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    ahri = UnitInPlay(card=_card("Ahri Alluring"))         # "When I hold, you score 1 point"
    ahri.gear = [_card("Skyfall of Areion")]
    bf0.add_unit("A", ahri)
    loop._fire_scoring_trigger("on_conquer", bf0, "A")
    assert loop.gs.points_A == 1


def test_blighted_battleaxe_falls_off_unless_its_unit_conquered():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    axe = _card("Blighted Battleaxe")
    unit = _u("U", 9)
    unit.gear = [axe]
    bf0.add_unit("A", unit)
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert axe in loop.gs.A.base_gear and unit.damage == 4
    unit.gear = [axe]
    loop.gs.A.base_gear.remove(axe)
    unit.conquered_turn = loop.gs.turn
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert unit.gear == [axe]


def test_attaching_fires_jax_unrelenting_and_aphelios_modes_once_each():
    loop = _loop()
    ap = loop.gs.A
    jax = UnitInPlay(card=_card("Jax Unrelenting"))
    loop.gs.battlefields[0].add_unit("A", jax)
    ap.energy = 1
    loop._fire_attached(jax, "A")
    assert len(ap.hand) == 1 and ap.energy == 0
    aph = UnitInPlay(card=_card("Aphelios Exalted"))
    loop.gs.battlefields[1].add_unit("A", aph)
    for _ in range(4):
        loop._fire_attached(aph, "A")
    assert len(loop.gs.modes_chosen[(id(aph.card), loop.gs.turn)]) == 3


def test_ornn_forge_god_grows_with_gear_and_riven_cuts_per_equipment():
    loop = _loop()
    ornn = UnitInPlay(card=_card("Ornn Forge God"))
    loop.gs.A.base_units.append(ornn)
    loop.gs.A.base_gear = [GearCard(name="G1"), GearCard(name="G2")]
    loop._recompute_passives()
    assert ornn.might == 6
    riven = UnitInPlay(card=_card("Riven Shattered"))
    riven.gear = [_card("Long Sword"), _card("Boneshiver")]
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", riven)
    enemy = _u("E", 9)
    bf0.add_unit("B", enemy)
    _fire(loop, riven.card, "on_attack")
    assert enemy.damage == 4


def test_yone_hits_a_base_unit_after_conquering_an_empty_battlefield():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    yone = UnitInPlay(card=_card("Yone Blademaster"), ready=True)
    loop.gs.A.base_units.append(yone)
    home = _u("Home", 9)
    loop.gs.B.base_units.append(home)
    loop.gs.A.base_units.remove(yone)
    loop._standard_move(yone, "A", len(loop.gs.battlefields), 0)
    _fire(loop, yone.card, "on_conquer", bf0)
    assert home.damage == yone.might


def test_jax_grandmaster_attaches_base_equipment():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Jax Grandmaster at Arms"), ready=True)
    sword = _card("Long Sword")
    loop.gs.A.base_gear.append(sword)
    unit = _u("U", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    ctx = EffectContext(loop, loop.gs.legend_unit_A.card, loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["attach_equipment"](ctx, {})
    assert unit.gear == [sword] and not loop.gs.A.base_gear


def test_arise_plays_a_soldier_per_equipment_and_readies_two():
    loop = _loop()
    loop.gs.A.base_gear = [_card("Long Sword"), _card("Boneshiver"), _card("Hand Hammer"), GearCard(name="Plain")]
    loop._resolve_card_effects(_card("Arise!"), loop.gs.battlefields[0], loop.gs.A, loop.gs.B)
    soldiers = [u for u in loop.gs.A.base_units if u.card.name == "Sand Soldier"]
    assert len(soldiers) == 3 and sum(u.ready for u in soldiers) == 2


def test_azir_sovereign_brings_tokens_into_the_attack():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    azir = UnitInPlay(card=_card("Azir Sovereign"))
    bf0.add_unit("A", azir)
    token = loop._play_token("Recruit", "A")
    _fire(loop, azir.card, "on_attack")
    assert token in bf0.units_A
