"""Batch of inert cards brought to life: "they deal damage equal to their Mights
to each other" (fight), "its base Might becomes N this turn", banish-and-replay
to base, once-per-turn and Nth-move triggers, "when you buff me", "when a
stunned enemy unit dies here", "when an opponent moves", and REPEAT costs read
from the printed text."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _u(name, might, ready=False):
    return UnitInPlay(card=UnitCard(name=name, might=might), ready=ready)


def _real(name, ready=False):
    return UnitInPlay(card=CARD_REGISTRY[name].instantiate(), ready=ready)


def _cast(loop, card_name, lane=0):
    card = CARD_REGISTRY[card_name].instantiate()
    loop._resolve_card_effects(card, loop.gs.battlefields[lane], loop.gs.A, loop.gs.B)


def _fire(loop, unit, trigger, bf=None, side="A", **extra):
    bf = bf or loop.gs.battlefields[0]
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_triggered_effects(unit.card, trigger, bf, me, them,
                                    context_extra={"battlefield": bf, **extra})


def test_challenge_picks_the_enemy_it_kills_and_survives():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    mine = _u("Mine", 5)
    small, big = _u("Small", 3), _u("Big", 7)
    bf0.add_unit("A", mine)
    bf0.add_unit("B", small)
    bf0.add_unit("B", big)
    _cast(loop, "Challenge")
    assert small not in bf0.units_B and big in bf0.units_B
    assert mine.damage == 3


def test_clash_of_giants_makes_two_enemies_fight():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    six, four = _u("Six", 6), _u("Four", 4)
    bf0.add_unit("B", six)
    bf1.add_unit("B", four)
    _cast(loop, "Clash of Giants")
    assert four not in bf1.units_B
    assert six.damage == 4


def test_carnivorous_snapvine_fights_when_played():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    vine = _real("Carnivorous Snapvine")
    enemy = _u("Enemy", 5)
    bf0.add_unit("A", vine)
    bf0.add_unit("B", enemy)
    _fire(loop, vine, "on_play")
    assert enemy not in bf0.units_B and vine.damage == 5


def test_dragon_form_sets_base_might_until_end_of_turn():
    loop = _loop()
    unit = _u("Small", 2)
    unit.might_counters = 1
    loop.gs.battlefields[0].add_unit("A", unit)
    _cast(loop, "Dragon Form")
    assert unit.might == 6                      # base 5, plus its buff
    unit.clear_turn_end_bonuses()
    assert unit.might == 3


def test_piltovan_guidebot_takes_the_played_cards_cost_only_when_higher():
    loop = _loop()
    bot = _real("Piltovan Guidebot")
    loop.gs.A.base_units.append(bot)
    _fire(loop, bot, "on_card_played", triggering_card=SpellCard(name="Big", cost_energy=7))
    assert bot.might == 7
    _fire(loop, bot, "on_card_played", triggering_card=SpellCard(name="Cheap", cost_energy=1))
    assert bot.might == 7


def test_convergent_mutation_raises_one_unit_to_another():
    loop = _loop()
    low, top = _u("Low", 2), _u("Top", 6)
    loop.gs.battlefields[0].add_unit("A", low)
    loop.gs.A.base_units.append(top)
    _cast(loop, "Convergent Mutation")
    assert low.might == 6


def test_portal_rescue_saves_a_losing_unit_to_base():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    loser = _u("Saved", 3)
    loser.damage = 2
    bf0.add_unit("A", loser)
    bf0.add_unit("B", _u("Bully", 9))
    _cast(loop, "Portal Rescue")
    back = [u for u in loop.gs.A.base_units if u.card is loser.card]
    assert back and back[0].damage == 0 and loser not in bf0.units_A


def test_yasuo_scores_on_his_third_move_only():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    yasuo = _real("Yasuo Windrider")
    bf0.add_unit("A", yasuo)
    for dst in (bf1, bf0):
        loop._move_unit_by_effect(yasuo, dst)
    assert loop.gs.points_A == 0
    loop._move_unit_by_effect(yasuo, bf1)
    assert loop.gs.points_A == 1
    loop._move_unit_by_effect(yasuo, bf0)
    assert loop.gs.points_A == 1


def test_blade_twirler_burns_only_on_its_first_move():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    twirler = _real("Blade Twirler")
    bf0.add_unit("A", twirler)
    before = len(loop.gs.B.deck.cards)
    loop._move_unit_by_effect(twirler, bf1)
    loop._move_unit_by_effect(twirler, bf0)
    assert len(loop.gs.B.deck.cards) == before - 1


def test_volibear_draws_when_an_opponent_moves_elsewhere():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bear = _real("Volibear Imposing")
    bf0.add_unit("A", bear)
    enemy = _u("Enemy", 2)
    loop.gs.B.base_units.append(enemy)
    hand = len(loop.gs.A.hand)
    loop._move_unit_by_effect(enemy, bf0)          # to Volibear's battlefield
    assert len(loop.gs.A.hand) == hand
    loop._move_unit_by_effect(enemy, bf1)
    assert len(loop.gs.A.hand) == hand + 1


def test_wraith_of_echoes_draws_on_the_first_friendly_death_each_turn():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    loop.gs.A.base_units.append(_real("Wraith of Echoes"))
    a, b = _u("A1", 1), _u("A2", 1)
    bf0.add_unit("A", a)
    bf0.add_unit("A", b)
    hand = len(loop.gs.A.hand)
    ctx = EffectContext(loop, a.card, loop.gs.B, loop.gs.A, bf0, {})
    ctx.damage_units([a], 5)
    ctx.damage_units([b], 5)
    assert len(loop.gs.A.hand) == hand + 1
    loop.gs.turn += 1
    c = _u("A3", 1)
    bf0.add_unit("A", c)
    ctx.damage_units([c], 5)
    assert len(loop.gs.A.hand) == hand + 2


def test_simian_ancestor_readies_when_buffed():
    loop = _loop()
    ape = _real("Simian Ancestor")
    loop.gs.battlefields[0].add_unit("A", ape)
    ctx = EffectContext(loop, SpellCard(name="Buff"), loop.gs.A, loop.gs.B,
                        loop.gs.battlefields[0], {})
    from riftbound.core.effects import REGISTRY
    REGISTRY["buff_unit"](ctx, {"target": "friendly_unit"})
    assert ape.ready and ape.might_counters == 1


def test_storm_raptor_draws_when_a_stunned_enemy_dies_here():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", _real("Storm Raptor"))
    stunned, plain = _u("Stunned", 1), _u("Plain", 1)
    stunned.stunned = True
    bf0.add_unit("B", stunned)
    bf0.add_unit("B", plain)
    hand = len(loop.gs.A.hand)
    ctx = EffectContext(loop, SpellCard(name="Zap"), loop.gs.A, loop.gs.B, bf0, {})
    ctx.damage_units([plain], 3)
    assert len(loop.gs.A.hand) == hand
    ctx.damage_units([stunned], 3)
    assert len(loop.gs.A.hand) == hand + 1


def test_dune_drake_gets_two_when_a_ready_enemy_is_here():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    drake = _real("Dune Drake")
    bf0.add_unit("A", drake)
    enemy = _u("Enemy", 2)
    bf0.add_unit("B", enemy)
    _fire(loop, drake, "on_attack")
    assert drake.might == 5
    enemy.ready = True
    _fire(loop, drake, "on_attack")
    assert drake.might == 7


def test_jae_medarda_draws_when_chosen_by_a_spell():
    loop = _loop()
    jae = _real("Jae Medarda")
    loop.gs.battlefields[0].add_unit("A", jae)
    hand = len(loop.gs.A.hand)
    loop._note_chosen(SpellCard(name="Spell"), "A", [jae])
    assert len(loop.gs.A.hand) == hand + 1


def test_repeat_pays_its_printed_power():
    loop = _loop()
    ap = loop.gs.A
    light = CARD_REGISTRY["Piercing Light"].instantiate()      # REPEAT [2] [fury]
    ap.energy = 5
    assert not loop._pay_repeat(light, ap) and ap.energy == 5
    ap.add_power(Domain.FURY, 1)
    assert loop._pay_repeat(light, ap)
    assert ap.energy == 3 and ap.power_pool.get(Domain.FURY, 0) == 0


def test_repeat_by_discard():
    loop = _loop()
    ap = loop.gs.A
    square = CARD_REGISTRY["Square Up"].instantiate()          # REPEAT - Discard 1
    ap.hand = [square]
    assert not loop._pay_repeat(square, ap)
    ap.hand.append(UnitCard(name="Fodder"))
    assert loop._pay_repeat(square, ap)
    assert [c.name for c in ap.trash] == ["Fodder"]
