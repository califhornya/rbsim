"""Reveal / banish the top card and play it (Blind Fury, Void Rush, Dazzling
Aurora, Baited Hook, Clocktower Guardian), "you may play that card until your
next Ending Phase" (Runeblade Anvil, Akali Brash), unattached gear hearing
"when you ..." and turn triggers (Pirate's Haven, Mistfall, Frigid Jewel,
Sumpworks Map, Mask of Foresight, Vanguard of Helm), and TEMPORARY units
dying in base too."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop(deck_a=None, deck_b=None):
    a = Player(name="A", deck=Deck(cards=list(deck_a or [])), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=list(deck_b or [])), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _cast(loop, name):
    loop._resolve_card_effects(_card(name), loop.gs.battlefields[0], loop.gs.A, loop.gs.B)


def _fire(loop, card, trigger, side="A"):
    bf = loop.gs.battlefields[0]
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_triggered_effects(card, trigger, bf, me, them, context_extra={"battlefield": bf})


def test_blind_fury_plays_the_opponents_top_card_for_free():
    ogre = UnitCard(name="Ogre", might=6, cost_energy=6)
    loop = _loop(deck_b=[UnitCard(name="Under"), ogre])          # top = last
    _cast(loop, "Blind Fury")
    assert [u.card for u in loop.gs.A.base_units] == [ogre]
    assert len(loop.gs.B.deck.cards) == 1


def test_void_rush_plays_one_two_cheaper_and_draws_the_other():
    cheap, big = UnitCard(name="Cheap", cost_energy=1), UnitCard(name="Big", cost_energy=4)
    loop = _loop(deck_a=[cheap, big])
    loop.gs.A.energy = 2
    _cast(loop, "Void Rush")
    assert [u.card for u in loop.gs.A.base_units] == [big] and loop.gs.A.energy == 0
    assert loop.gs.A.hand == [cheap]


def test_dazzling_aurora_reveals_until_a_unit_at_the_end_of_turn():
    spell, unit = SpellCard(name="Spell"), UnitCard(name="Found", might=4, cost_energy=5)
    loop = _loop(deck_a=[UnitCard(name="Deep"), unit, spell])
    loop.gs.A.base_gear.append(_card("Dazzling Aurora"))
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert [u.card for u in loop.gs.A.base_units] == [unit]
    assert loop.gs.A.deck.cards[0] is spell                     # recycled to the bottom


def test_baited_hook_trades_a_unit_for_one_up_to_one_mightier():
    four, three = UnitCard(name="Four", might=4, cost_energy=4), UnitCard(name="Three", might=3, cost_energy=3)
    loop = _loop(deck_a=[three, four])
    small = UnitInPlay(card=UnitCard(name="Small", might=2))
    loop.gs.battlefields[0].add_unit("A", small)
    hook = _card("Baited Hook")
    ctx = EffectContext(loop, hook, loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    spec = CARD_REGISTRY["Baited Hook"].effects[0].merged_params()
    REGISTRY["reveal_play_top"](ctx, spec)
    assert small not in loop.gs.battlefields[0].units_A
    assert [u.card for u in loop.gs.A.base_units] == [three]


def test_clocktower_guardian_deathknell_plays_the_banished_top_card():
    unit = UnitCard(name="Free", might=3, cost_energy=7)
    loop = _loop(deck_a=[unit])
    _fire(loop, _card("Clocktower Guardian"), "on_death")
    assert [u.card for u in loop.gs.A.base_units] == [unit]


def test_runeblade_anvil_banishes_a_card_playable_until_your_next_ending_phase():
    top = UnitCard(name="Later", might=2, cost_energy=2)
    loop = _loop(deck_a=[UnitCard(name="Next"), top])
    ap = loop.gs.A
    anvil = _card("Runeblade Anvil")
    ap.base_gear.append(anvil)
    _fire(loop, anvil, "on_play")
    assert top in ap.banished
    entries = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "banished_play"]
    (idx, entry), = entries
    assert not loop._ability_usable(ap, entry)                  # still pays its cost
    ap.energy = 2
    loop._apply_action(ap, ("ABILITY", "ACTIVATED", idx, None))
    assert [u.card for u in ap.base_units] == [top] and ap.energy == 0
    # Killing it banishes the next one; on the opponent's turn it lasts into ours.
    loop.gs.active = "B"
    ctx = EffectContext(loop, anvil, ap, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["kill_gear"](ctx, {"target": "self"})
    assert anvil in ap.trash and len(ap.banished) == 1
    loop.gs.turn += 1
    assert loop._banished_playable(ap.banished[0], "A")
    loop.gs.turn += 1
    assert not loop._banished_playable(ap.banished[0], "A")


def test_akali_brash_adds_on_her_first_move_and_banishes_on_her_second():
    loop = _loop(deck_a=[UnitCard(name="Top")])
    bf0, bf1 = loop.gs.battlefields
    akali = UnitInPlay(card=_card("Akali Brash"))
    bf0.add_unit("A", akali)
    loop._move_unit_by_effect(akali, bf1)
    assert loop.gs.A.energy == 1 and sum(loop.gs.A.power_pool.values()) == 1
    loop._move_unit_by_effect(akali, bf0)
    assert [c.name for c in loop.gs.A.banished] == ["Top"]


def test_pirates_haven_pumps_a_unit_you_ready():
    loop = _loop()
    loop.gs.A.base_gear.append(_card("Pirate's Haven"))
    unit = UnitInPlay(card=UnitCard(name="U", might=2), ready=False)
    loop.gs.battlefields[0].add_unit("A", unit)
    ctx = EffectContext(loop, SpellCard(name="S"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["ready_unit"](ctx, {"target": "friendly_unit"})
    assert unit.ready and unit.might == 3


def test_mistfall_readies_a_buffed_unit_once_paying_body():
    from riftbound.core.enums import Domain
    loop = _loop()
    ap = loop.gs.A
    mist = _card("Mistfall")
    ap.base_gear.append(mist)
    a, b = UnitInPlay(card=UnitCard(name="A1", might=2)), UnitInPlay(card=UnitCard(name="A2", might=2))
    loop.gs.battlefields[0].add_unit("A", a)
    loop.gs.battlefields[1].add_unit("A", b)
    ap.add_power(Domain.BODY, 2)
    ctx = EffectContext(loop, SpellCard(name="S"), ap, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["buff_unit"](ctx, {"target": "friendly_unit"})
    assert a.ready and mist.tapped
    ctx = EffectContext(loop, SpellCard(name="S"), ap, loop.gs.B, loop.gs.battlefields[1], {})
    REGISTRY["buff_unit"](ctx, {"target": "friendly_unit"})
    assert not b.ready                                       # Mistfall is exhausted


def test_frigid_jewel_fires_on_the_second_draw():
    loop = _loop(deck_a=[UnitCard(name=f"C{i}") for i in range(3)])
    loop.gs.A.base_gear.append(_card("Frigid Jewel"))
    unit = UnitInPlay(card=UnitCard(name="U", might=2))
    loop.gs.battlefields[0].add_unit("A", unit)
    loop._draw_one(loop.gs.A)
    assert unit.might == 2
    loop._draw_one(loop.gs.A)
    assert unit.might == 4
    loop._draw_one(loop.gs.A)
    assert unit.might == 4


def test_sumpworks_map_draws_when_an_opponent_scores():
    loop = _loop(deck_a=[UnitCard(name="C")])
    loop.gs.A.base_gear.append(_card("Sumpworks Map"))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "B")
    assert len(loop.gs.A.hand) == 1


def test_mask_of_foresight_pumps_a_lone_attacker():
    loop = _loop()
    loop.gs.A.base_gear.append(_card("Mask of Foresight"))
    bf0 = loop.gs.battlefields[0]
    lone = UnitInPlay(card=UnitCard(name="Lone", might=3))
    bf0.add_unit("A", lone)
    for u in (UnitInPlay(card=UnitCard(name="D1", might=1)), UnitInPlay(card=UnitCard(name="D2", might=1))):
        bf0.add_unit("B", u)
    loop._fire_units_trigger("on_friendly_attack", "A", extra={"triggering_unit": lone, "alone": True})
    loop._fire_units_trigger("on_friendly_attack", "A", extra={"triggering_unit": lone, "alone": False})
    assert lone.might == 4


def test_vanguard_of_helm_passes_a_dead_units_buff_on():
    loop = _loop()
    loop.gs.A.base_gear.append(_card("Vanguard of Helm"))
    bf0 = loop.gs.battlefields[0]
    buffed, other = UnitInPlay(card=UnitCard(name="B", might=1)), UnitInPlay(card=UnitCard(name="O", might=1))
    buffed.might_counters = 1
    bf0.add_unit("A", buffed)
    bf0.add_unit("A", other)
    ctx = EffectContext(loop, SpellCard(name="Zap"), loop.gs.B, loop.gs.A, bf0, {})
    ctx.damage_units([buffed], 5)
    assert other.might_counters == 1


def test_temporary_units_in_base_die_with_their_deathknell():
    loop = _loop()
    sprite = UnitInPlay(card=UnitCard(name="Sprite", might=3, keywords=["TEMPORARY"]))
    loop.gs.A.base_units.append(sprite)
    died = []
    orig = loop._route_deaths
    loop._route_deaths = lambda pairs, bf: (died.extend(pairs), orig(pairs, bf))
    loop._phase_beginning("A")
    assert sprite not in loop.gs.A.base_units and died == [(sprite, "A")]


def test_mordekaiser_banishes_from_the_trash_for_power_only_units_and_gear_use():
    loop = _loop()
    ap = loop.gs.A
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Mordekaiser Iron Revenant"), ready=True)
    entries = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "ability"]
    (idx, entry), = entries
    assert not loop._ability_usable(ap, entry)                   # nothing to banish
    fodder = UnitCard(name="Fodder")
    ap.trash = [SpellCard(name="Spell"), fodder]
    loop._apply_action(ap, ("ABILITY", "ACTIVATED", idx, None))
    assert ap.banished == [fodder] and ap.earmarked_power_permanent == 1
    from riftbound.core.enums import Domain
    spell = SpellCard(name="S", cost_energy=0, cost_power=1, cost_power_domain=Domain.ORDER)
    unit = UnitCard(name="U", cost_energy=0, cost_power=1, cost_power_domain=Domain.ORDER)
    assert not loop._can_pay_card(ap, spell, 0, 1)
    assert loop._pay_card(ap, unit, 0, 1) and ap.earmarked_power_permanent == 0
