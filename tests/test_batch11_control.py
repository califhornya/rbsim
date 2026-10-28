"""Hand disruption (Ashe Focused, Insightful Investigator, Bone Skewer), taking
control (Hostile Takeover, Conscription), granted REPEAT (Temporal Portal,
Syndra), token replacements (Heimerdinger Academy Instructor, Zilean), rune
effects (Seraphic Wyvern, Coalesced Energy), Mordekaiser Twice Slain, Ahri
Confident, Vex Mocking, Tornado Warrior, Meticulous Restorationist, Mystic
Vortex, Jayce Hammer in Hand, Lillia, Ravenbloom Prefect, Shard of Undoing."""

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
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]),
               rune_deck=RuneDeck([Rune(domain=Domain.FURY) for _ in range(8)]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _u(name, might=2, **kw):
    return UnitInPlay(card=UnitCard(name=name, might=might), **kw)


def _cast(loop, name, side="A", lane=0):
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_card_effects(_card(name), loop.gs.battlefields[lane], me, them)


def _fire(loop, card, trigger, side="A", lane=0, **extra):
    bf = loop.gs.battlefields[lane]
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_triggered_effects(card, trigger, bf, me, them, context_extra={"battlefield": bf, **extra})


def test_ashe_banishes_their_best_card_until_they_hold():
    loop = _loop()
    big, small = UnitCard(name="Big", cost_energy=6), UnitCard(name="Small", cost_energy=1)
    loop.gs.B.hand = [small, big]
    _fire(loop, _card("Ashe Focused"), "on_play")
    assert loop.gs.B.hand == [small] and big in loop.gs.B.banished
    loop.gs.battlefields[1].add_unit("B", _u("Holder"))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[1], "B")
    assert big in loop.gs.B.hand


def test_insightful_investigator_pays_xp_to_strip_a_card():
    loop = _loop()
    loop.gs.B.hand = [UnitCard(name="Best", cost_energy=7)]
    loop.gs.add_xp("A", 2)
    _fire(loop, _card("Insightful Investigator"), "on_play")
    assert [c.name for c in loop.gs.B.trash] == ["Best"] and len(loop.gs.B.hand) == 1
    assert loop.gs.get_xp("A") == 0


def test_bone_skewer_drags_a_stunned_unit_into_our_strongest_battlefield():
    loop = _loop()
    bf1 = loop.gs.battlefields[1]
    bf1.add_unit("A", _u("Wall", 6))
    victim = UnitCard(name="Victim", might=4)
    loop.gs.B.hand = [victim, UnitCard(name="Huge", might=9)]
    _cast(loop, "Bone Skewer")
    pulled = next(u for u in bf1.units_B if u.card is victim)
    assert pulled.stunned and bf1.contested_this_turn


def test_hostile_takeover_borrows_a_unit_until_end_of_turn():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    enemy = _u("Enemy", 5, ready=False)
    bf0.add_unit("B", enemy)
    _cast(loop, "Hostile Takeover")
    assert enemy in bf0.units_A and enemy.ready
    loop._return_borrowed_units()
    assert enemy in loop.gs.B.base_units


def test_conscription_steals_a_small_unit_or_any_with_five_xp():
    loop = _loop()
    small, big = _u("Small", 3), _u("Big", 7)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.gs.battlefields[1].add_unit("B", big)
    _cast(loop, "Conscription")
    assert small in loop.gs.A.base_units
    loop.gs.add_xp("A", 5)
    _cast(loop, "Conscription")
    assert big in loop.gs.A.base_units and loop.gs.get_xp("A") == 0


def test_temporal_portal_gives_the_next_spell_repeat():
    loop = _loop()
    ap = loop.gs.A
    REGISTRY["next_spell_repeat"](EffectContext(loop, GearCard(name="Portal"), ap, loop.gs.B,
                                                loop.gs.battlefields[0], {}), {})
    spell = _card("Dredge Up")                      # Draw 1, costs 2
    ap.energy = 2
    loop._spell_played(spell, ap)
    assert spell._repeat_paid and ap.energy == 0
    loop._resolve_card_effects(spell, loop.gs.battlefields[0], ap, loop.gs.B)
    assert len(ap.hand) == 2


def test_heimerdinger_upgrades_tokens_and_zilean_copies_one():
    loop = _loop()
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=_card("Heimerdinger Academy Instructor")))
    token = loop._play_token("Recruit", "A")
    assert token.card.name == "Mech" and token.might == 3
    loop = _loop()
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=_card("Zilean Time Mage")))
    loop._play_token("Recruit", "A")
    loop._play_token("Recruit", "A")
    assert sum(1 for u in loop.gs.A.base_units if u.card.name == "Recruit") == 3


def test_seraphic_wyvern_and_coalesced_energy():
    loop = _loop()
    loop.gs.A.base_units.append(UnitInPlay(card=_card("Seraphic Wyvern")))
    loop.gs.turn = 5
    loop._phase_beginning("A")
    assert loop.gs.A.total_runes_in_play() == 3
    _fire(loop, _card("Coalesced Energy"), "on_end_of_turn")
    assert loop.gs.A.total_runes_in_play() == 5      # "channel 4" + the Wyvern's 1


def test_mordekaiser_twice_slain_kills_a_friend_instead_once_a_turn():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    mord, friend, friend2 = UnitInPlay(card=_card("Mordekaiser Twice Slain")), _u("Friend", 1), _u("F2", 1)
    bf0.add_unit("A", mord)
    loop.gs.A.base_units += [friend, friend2]
    ctx = EffectContext(loop, SpellCard(name="Z"), loop.gs.B, loop.gs.A, bf0, {})
    ctx.damage_units([mord], 99)
    assert mord in loop.gs.A.base_units and mord.damage == 0 and not mord.ready
    assert len([u for u in (friend, friend2) if u in loop.gs.A.base_units]) == 1
    ctx.damage_units([mord], 99)
    assert mord not in loop.gs.A.base_units


def test_ahri_confident_grows_when_an_enemy_here_shrinks():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    ahri, enemy = UnitInPlay(card=_card("Ahri Confident")), _u("E", 5)
    bf0.add_unit("A", ahri)
    bf0.add_unit("B", enemy)
    before = ahri.might
    REGISTRY["grant_temporary_might"](EffectContext(loop, SpellCard(name="S"), loop.gs.A, loop.gs.B, bf0, {}),
                                      {"target": "enemy_unit", "amount": -1})
    assert ahri.might == before + 1


def test_vex_mocking_follows_a_stun():
    loop = _loop()
    vex = UnitInPlay(card=_card("Vex Mocking"))
    loop.gs.A.base_units.append(vex)
    enemy = _u("E", 3)
    loop.gs.battlefields[1].add_unit("B", enemy)
    ctx = EffectContext(loop, SpellCard(name="S"), loop.gs.A, loop.gs.B, loop.gs.battlefields[1], {})
    REGISTRY["stun_unit"](ctx, {"target": "enemy_unit"})
    assert vex in loop.gs.battlefields[1].units_A


def test_tornado_warrior_empowers_when_played_from_face_down():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    pal = _u("Pal")
    bf0.add_unit("A", pal)
    tornado = _card("Tornado Warrior")
    loop._play_unit(tornado, "A", bf=bf0, from_zone="facedown")
    assert any(u.empowered for u in bf0.units_A)


def test_meticulous_restorationist_returns_after_a_big_card():
    loop = _loop()
    resto = _card("Meticulous Restorationist")
    loop.gs.A.trash = [resto]
    loop.gs.A.add_power(Domain.ORDER, 1)
    loop._fire_card_played("A", UnitCard(name="Huge", cost_energy=7), "hand")
    assert any(u.card is resto for u in loop.gs.A.base_units)


def test_mystic_vortex_taxes_reactions_in_its_showdowns():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Mystic Vortex")
    react = SpellCard(name="R", cost_energy=1, keywords=["REACTION"])
    assert loop._effective_cost(react, loop.gs.A)[0] == 1
    loop.gs.showdown_active, loop.gs.showdown_bf_idx = True, 0
    assert loop._effective_cost(react, loop.gs.A)[0] == 2


def test_jayce_picks_a_keyword_when_readied():
    loop = _loop()
    jayce = UnitInPlay(card=_card("Jayce Hammer in Hand"), ready=False)
    loop.gs.battlefields[0].add_unit("A", jayce)
    REGISTRY["ready_unit"](EffectContext(loop, SpellCard(name="S"), loop.gs.A, loop.gs.B,
                                         loop.gs.battlefields[0], {}), {"target": "friendly_unit"})
    assert jayce.keyword_value("ASSAULT") == 2


def test_lillia_grows_per_token_and_tokens_tank():
    loop = _loop()
    lillia = UnitInPlay(card=_card("Lillia Protector of Dreams"))
    loop.gs.A.base_units.append(lillia)
    before = lillia.might
    token = loop._play_token("Recruit", "A")
    loop._recompute_passives()
    assert lillia.might == before + 1 and token.has_keyword("TANK")


def test_ravenbloom_prefect_trades_itself_for_a_big_gear():
    loop = _loop()
    prefect = UnitInPlay(card=_card("Ravenbloom Prefect"))
    loop.gs.A.base_units.append(prefect)
    gear = GearCard(name="Big Gear", cost_energy=4)
    loop.gs.B.hand = [gear]
    loop._play_gear(gear, "B", 0)
    assert gear in loop.gs.B.banished and prefect.card in loop.gs.A.banished


def test_shard_of_undoing_answers_a_death_in_your_beginning_phase():
    loop = _loop()
    loop.gs.A.base_gear.append(_card("Shard of Undoing"))
    loop.gs.A.base_units.append(UnitInPlay(card=UnitCard(name="Temp", might=1, keywords=["TEMPORARY"])))
    enemy = _u("Enemy", 3)
    loop.gs.B.base_units.append(enemy)
    loop._phase_beginning("A")
    assert enemy not in loop.gs.B.base_units
