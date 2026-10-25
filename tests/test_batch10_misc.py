"""Excess combat damage (Yeti Brawler, Sivir Ambitious), spending buffs
(Wildclaw Shaman, Udyr Wildman, Albus Ferros), VISION on every card that
prints it, "once each turn" abilities (Hungry Wolf), and one-offs: Scryer's
Bloom, Siren's Song, Stare Down, Tricksy Tentacles, Temptation, Firelights'
Hideout, Card Sharp, Divine Judgment, Twisted Fate Gambler, Fox-Fire, Swain
Visionary, Kai'Sa Evolutionary, Mechanical Bandit, Friendship, Malzahar."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop(deck_a=None, deck_b=None):
    a = Player(name="A", deck=Deck(cards=list(deck_a or [UnitCard(name=f"C{i}") for i in range(5)])),
               rune_deck=RuneDeck([Rune(domain=Domain.FURY) for _ in range(4)]))
    b = Player(name="B", deck=Deck(cards=list(deck_b or [UnitCard(name=f"D{i}") for i in range(5)])),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _real(name, **kw):
    return UnitInPlay(card=_card(name), **kw)


def _u(name, might=2, **kw):
    return UnitInPlay(card=UnitCard(name=name, might=might), **kw)


def _cast(loop, name, side="A", lane=0):
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_card_effects(_card(name), loop.gs.battlefields[lane], me, them)


def _fire(loop, card, trigger, side="A", lane=0):
    bf = loop.gs.battlefields[lane]
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_triggered_effects(card, trigger, bf, me, them, context_extra={"battlefield": bf})


def test_yeti_brawler_plays_gold_after_three_excess_damage():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    yeti = _real("Yeti Brawler")                            # 6 Might
    bf0.add_unit("A", yeti)
    bf0.add_unit("B", _u("Small", 2))
    loop._phase_combat_and_conquer_single(0, "A")
    assert bf0.excess_damage["A"][1] == 4
    gold = [g for g in loop.gs.A.base_gear if g.name == "Gold"]
    assert len(gold) == 2


def test_wildclaw_shaman_spends_another_units_buff():
    loop = _loop()
    donor = _u("Donor")
    donor.might_counters = 1
    loop.gs.A.base_units.append(donor)
    shaman = _real("Wildclaw Shaman", ready=False)
    loop.gs.battlefields[0].add_unit("A", shaman)
    _fire(loop, shaman.card, "on_play")
    assert donor.might_counters == 0 and shaman.might_counters == 1 and shaman.ready


def test_udyr_spends_his_buff_for_a_new_mode_each_time():
    loop = _loop()
    udyr = _real("Udyr Wildman", ready=True)
    loop.gs.battlefields[0].add_unit("A", udyr)
    enemy = _u("E", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    entries = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e.get("unit") is udyr]
    (idx, entry), = entries
    assert not loop._ability_usable(loop.gs.A, entry)        # no buff
    udyr.might_counters = 1
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert enemy.damage == 2 and udyr.might_counters == 0
    udyr.might_counters = 1
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert enemy.stunned                                       # the next mode


def test_albus_ferros_turns_base_buffs_into_runes():
    loop = _loop()
    for i in range(2):
        u = _u(f"B{i}")
        u.might_counters = 1
        loop.gs.A.base_units.append(u)
    _fire(loop, _card("Albus Ferros"), "on_play")
    assert sum(len(v) for v in loop.gs.A.rune_pool.values()) == 2


def test_vision_looks_at_the_top_card_when_played():
    loop = _loop()
    seen = []
    from riftbound.core import effects
    orig = effects.REGISTRY["predict"]
    effects.REGISTRY["predict"] = lambda ctx, spec: seen.append(spec.get("amount"))
    try:
        loop._play_unit(_card("Jeweled Colossus"), "A")
        loop._play_unit(_card("Mystic Poro"), "A")          # its spec already predicts
    finally:
        effects.REGISTRY["predict"] = orig
    assert seen == [1, 1]


def test_hungry_wolf_once_per_turn_after_choosing_an_enemy():
    loop = _loop()
    wolf = _real("Hungry Wolf", ready=False)
    loop.gs.battlefields[0].add_unit("A", wolf)
    loop.gs.A.add_power(Domain.ORDER, 2)
    (idx, entry), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e.get("unit") is wolf]
    assert not loop._ability_usable(loop.gs.A, entry)
    loop.gs.enemy_choices_this_turn["A"] = 1
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert wolf.ready and wolf.might == int(wolf.card.might) + 1
    assert not loop._ability_usable(loop.gs.A, entry)


def test_scryers_bloom_and_divining_shells_sacrifice_themselves():
    loop = _loop()
    bloom = _card("Scryer's Bloom")
    loop.gs.A.base_gear.append(bloom)
    loop.gs.A.energy = 1
    (idx, _), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e.get("gear") is bloom]
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert bloom in loop.gs.A.trash and len(loop.gs.A.hand) == 1 and loop.gs.get_xp("A") == 1


def test_sirens_song_moves_an_enemy_that_moved():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    still, mover = _u("Still", 5), _u("Mover", 3)
    bf0.add_unit("B", still)
    bf0.add_unit("B", mover)
    mover.moves_this_turn = 1
    _cast(loop, "Siren's Song")
    assert still in bf0.units_B and mover not in bf0.units_B


def test_stare_down_and_tricksy_tentacles_send_enemies_home():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    loop.gs.A.base_units.append(_u("Big", 5))
    a, b, c = _u("a", 2), _u("b", 4), _u("c", 6)
    bf1.add_unit("B", a)
    bf1.add_unit("B", b)
    bf1.add_unit("B", c)
    _cast(loop, "Stare Down")
    assert {u.card.name for u in loop.gs.B.base_units} == {"a", "b"} and loop.gs.get_xp("A") == 1
    loop = _loop()
    bf1 = loop.gs.battlefields[1]
    for n, m in (("x", 5), ("y", 3), ("z", 4)):
        bf1.add_unit("B", _u(n, m))
    _cast(loop, "Tricksy Tentacles")
    assert sum(u.might for u in loop.gs.B.base_units) == 8


def test_temptation_moves_an_enemy_next_to_its_friends():
    loop = _loop()
    loop.gs.B.base_units.append(_u("Home", 1))
    away = _u("Away", 5)
    loop.gs.battlefields[1].add_unit("B", away)
    _cast(loop, "Temptation")
    assert away in loop.gs.B.base_units


def test_firelights_hideout_gives_the_next_unit_accelerate():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Firelights' Hideout")
    loop._fire_scoring_trigger("on_conquer", bf0, "A")
    card = UnitCard(name="Next", domain=Domain.FURY)
    loop.gs.A.energy = 1
    loop.gs.A.add_power(Domain.FURY, 1)
    unit = loop._play_unit(card, "A")
    assert unit.ready and loop.gs.A.energy == 0


def test_card_sharp_party_favors_and_mechanical_bandit():
    loop = _loop()
    _fire(loop, _card("Card Sharp"), "on_play")
    assert [g.name for g in loop.gs.A.base_gear] == ["Gold", "Gold"]
    assert [g.name for g in loop.gs.B.base_gear] == ["Gold"]
    _cast(loop, "Party Favors")
    assert len(loop.gs.A.hand) == 1 and len(loop.gs.B.hand) == 1
    cheap, dear = UnitCard(name="Cheap", cost_energy=1), UnitCard(name="Dear", cost_energy=5)
    loop = _loop(deck_a=[cheap], deck_b=[dear])
    _fire(loop, _card("Mechanical Bandit"), "on_start_of_turn")
    assert loop.gs.A.hand == [cheap] and loop.gs.B.deck.cards == [dear]


def test_divine_judgment_keeps_two_of_each():
    loop = _loop()
    for i in range(4):
        loop.gs.A.base_units.append(_u(f"U{i}", i + 1))
    loop.gs.A.hand = [UnitCard(name=f"H{i}", cost_energy=i) for i in range(4)]
    loop.gs.A.rune_pool[Domain.FURY] = [Rune(domain=Domain.FURY) for _ in range(5)]
    _cast(loop, "Divine Judgment")
    assert sorted(u.might for u in loop.gs.A.base_units) == [3, 4]
    assert sorted(c.name for c in loop.gs.A.hand) == ["H2", "H3"]
    assert len(loop.gs.A.rune_pool[Domain.FURY]) == 2


def test_twisted_fate_reads_the_top_rune():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    tf = _real("Twisted Fate Gambler")
    bf0.add_unit("A", tf)
    e1, e2 = _u("E1", 5), _u("E2", 5)
    bf0.add_unit("B", e1)
    bf0.add_unit("B", e2)
    _fire(loop, tf.card, "on_attack")
    assert sorted(u.damage for u in (e1, e2)) == [1, 2]
    loop.gs.A.rune_deck.runes[0] = Rune(domain=Domain.MIND)
    _fire(loop, tf.card, "on_attack")
    assert len(loop.gs.A.hand) == 1


def test_fox_fire_kills_up_to_four_might_at_one_battlefield():
    loop = _loop()
    bf1 = loop.gs.battlefields[1]
    for n, m in (("a", 3), ("b", 1), ("c", 2)):
        bf1.add_unit("B", _u(n, m))
    _cast(loop, "Fox-Fire")
    assert [u.card.name for u in bf1.units_B] == ["c"]


def test_swain_scores_after_a_unit_a_gear_and_a_spell():
    loop = _loop()
    swain = _real("Swain Visionary")
    loop.gs.battlefields[0].add_unit("A", swain)
    loop.gs.played_cards_this_turn["A"] = [UnitCard(name="U"), GearCard(name="G")]
    _fire(loop, swain.card, "on_conquer")
    assert loop.gs.points_A == 0
    loop.gs.played_cards_this_turn["A"].append(SpellCard(name="S"))
    _fire(loop, swain.card, "on_conquer")
    assert loop.gs.points_A == 1


def test_kaisa_evolutionary_replays_a_cheaper_spell_then_recycles_it():
    loop = _loop()
    loop.gs.points_A = 3
    cheap, dear = _card("Dredge Up"), _card("Grand Strategem")
    loop.gs.A.trash = [cheap, dear]
    _fire(loop, _card("Kai'Sa Evolutionary"), "on_conquer")
    assert cheap not in loop.gs.A.trash and dear in loop.gs.A.trash
    assert loop.gs.A.deck.cards[0] is cheap


def test_friendship_counts_bird_cat_dog_poro():
    loop = _loop()
    target = _u("T", 1)
    loop.gs.battlefields[0].add_unit("A", target)
    for tag in ("Bird", "Cat", "Yordle"):
        loop.gs.A.base_units.append(UnitInPlay(card=UnitCard(name=tag, might=1, tags=[tag])))
    _cast(loop, "Friendship")
    assert target.might == 3


def test_malzahar_gives_up_only_a_token():
    loop = _loop()
    mal = _real("Malzahar Fanatic", ready=True)
    loop.gs.battlefields[0].add_unit("A", mal)
    loop.gs.A.base_units.append(_u("Real"))
    (idx, entry), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e.get("unit") is mal]
    assert not loop._ability_usable(loop.gs.A, entry)
    token = loop._play_token("Recruit", "A")
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert token not in loop.gs.A.base_units and sum(loop.gs.A.power_pool.values()) == 2
