"""The last triggers: Bedeviling Stranger and Ripper's Bay, Stealthy Pursuer,
Battlefield Armorer, Seraphine Inspiring (three units moved together),
Forgotten Signpost, Mageseeker Investigator, Immortal Phoenix, Karma
Channeler (recycling goes to the bottom), Hexplosive Minefield, Ava Achiever,
Heimerdinger Inventor, Ivern Friend to All, Jhin Virtuoso, Zero Point
Inflection, Jarvan IV Exemplar, Forge of the Fluft."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, DeployedGear
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(12)]),
               rune_deck=RuneDeck([Rune(domain=Domain.FURY) for _ in range(6)]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _u(name, might=2, tags=None, **kw):
    return UnitInPlay(card=UnitCard(name=name, might=might, tags=list(tags or [])), **kw)


def _fire(loop, card, trigger, side="A", lane=0, **extra):
    bf = loop.gs.battlefields[lane]
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    loop._resolve_triggered_effects(card, trigger, bf, me, them, context_extra={"battlefield": bf, **extra})


def test_bedeviling_stranger_bounces_at_a_crowded_battlefield_and_rippers_bay_pays_back():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Ripper's Bay")
    big = _u("Big", 5)
    for u in (_u("a"), _u("b"), big):
        bf0.add_unit("B", u)
    bf0.add_unit("A", _u("Mine"))
    loop.gs.B.energy = 1
    loop.gs.B.rune_deck = RuneDeck([Rune(domain=Domain.CALM)])
    _fire(loop, _card("Bedeviling Stranger"), "on_play")
    assert big.card in loop.gs.B.hand
    assert loop.gs.B.energy == 0 and loop.gs.B.total_runes_in_play() == 1     # Ripper's Bay


def test_stealthy_pursuer_follows_a_friend_into_a_battlefield():
    loop = _loop()
    pursuer, friend = UnitInPlay(card=_card("Stealthy Pursuer")), _u("Friend", ready=True)
    loop.gs.A.base_units += [pursuer, friend]
    loop.gs.A.base_units.remove(friend)
    loop._standard_move(friend, "A", len(loop.gs.battlefields), 1)
    assert pursuer in loop.gs.battlefields[1].units_A


def test_battlefield_armorer_returns_a_dead_deployed_gear():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    loop.gs.A.base_units.append(UnitInPlay(card=_card("Battlefield Armorer")))
    gear = GearCard(name="Post", cost_energy=2)
    dg = DeployedGear(card=gear)
    bf0.gear_for("A").append(dg)
    loop.gs.A.energy = 1
    loop._kill_deployed_gear(bf0, "A", [dg])
    assert gear in loop.gs.A.hand and loop.gs.A.energy == 0


def test_seraphine_draws_when_three_units_move_together():
    loop = _loop()
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=_card("Seraphine Inspiring")))
    units = [_u(f"U{i}", ready=True) for i in range(3)]
    base = len(loop.gs.battlefields)
    for u in units:
        loop._standard_move(u, "A", base, 1)
    assert len(loop.gs.A.hand) == 1


def test_forgotten_signpost_moves_a_unit_to_an_exhausted_friend():
    loop = _loop()
    post = _card("Forgotten Signpost")
    loop.gs.A.base_gear.append(post)
    anchor = _u("Anchor", ready=True)
    loop.gs.battlefields[1].add_unit("A", anchor)
    mover = _u("Mover", 4)
    loop.gs.A.base_units.append(mover)
    (idx, entry), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e.get("gear") is post]
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert mover in loop.gs.battlefields[1].units_A and not anchor.ready


def test_mageseeker_investigator_tolls_the_second_unit():
    loop = _loop()
    loop.gs.battlefields[1].add_unit("B", UnitInPlay(card=_card("Mageseeker Investigator")))
    a, b = _u("a", ready=True), _u("b", ready=True)
    loop.gs.A.base_units += [a, b]
    base = len(loop.gs.battlefields)
    loop._apply_action(loop.gs.A, ("MOVE", 0, base, 1))
    assert loop._group_move_toll("A", 1) == 1
    loop._apply_action(loop.gs.A, ("MOVE", 0, base, 1))
    assert b in loop.gs.A.base_units                 # no Energy for the toll
    loop.gs.A.energy = 1
    loop._apply_action(loop.gs.A, ("MOVE", 0, base, 1))
    assert b in loop.gs.battlefields[1].units_A and loop.gs.A.energy == 0


def test_immortal_phoenix_rises_when_a_spell_kills():
    loop = _loop()
    phoenix = _card("Immortal Phoenix")
    loop.gs.A.trash = [phoenix]
    loop.gs.A.energy = 1
    loop.gs.A.add_power(Domain.FURY, 1)
    victim = _u("V", 1)
    loop.gs.battlefields[0].add_unit("B", victim)
    EffectContext(loop, SpellCard(name="Bolt"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {}).damage_units([victim], 3)
    assert any(u.card is phoenix for u in loop.gs.A.base_units)


def test_recycle_costs_go_to_the_bottom_and_karma_buffs():
    loop = _loop()
    loop.gs.A.base_units.append(UnitInPlay(card=_card("Karma Channeler")))
    old = UnitCard(name="Old")
    loop.gs.A.trash = [old]
    loop._recycle_from_trash(loop.gs.A, 1)
    assert loop.gs.A.deck.cards[0] is old
    assert any(u.might_counters for u in loop.gs.A.base_units)


def test_hexplosive_minefield_rebuilds_its_bombs_at_end_of_turn():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    for _ in range(2):
        loop._play_token("Bomb", "A")
    bombs = sum(1 for bf in loop.gs.battlefields for dg in bf.gear_for("A") if dg.card.name == "Bomb")
    assert bombs == 2
    loop._resolve_card_effects(_card("Hexplosive Minefield"), bf0, loop.gs.A, loop.gs.B)
    assert not any(dg.card.name == "Bomb" for bf in loop.gs.battlefields for dg in bf.gear_for("A"))
    loop._resolve_delayed_effects()
    assert sum(1 for bf in loop.gs.battlefields for dg in bf.gear_for("A") if dg.card.name == "Bomb") == 2


def test_ava_achiever_plays_a_hidden_unit_into_the_attack():
    loop = _loop()
    ava = UnitInPlay(card=_card("Ava Achiever"))
    loop.gs.battlefields[0].add_unit("A", ava)
    hidden = next(CARD_REGISTRY[n].instantiate() for n in CARD_REGISTRY
                  if "HIDDEN" in CARD_REGISTRY[n].keywords and CARD_REGISTRY[n].category.name == "UNIT")
    loop.gs.A.hand = [hidden]
    loop.gs.A.add_power(Domain.MIND, 1)
    _fire(loop, ava.card, "on_attack")
    assert any(u.card is hidden for u in loop.gs.battlefields[0].units_A)


def test_heimerdinger_inventor_borrows_tap_abilities():
    loop = _loop()
    heimer = UnitInPlay(card=_card("Heimerdinger Inventor"), ready=True)
    loop.gs.A.base_units.append(heimer)
    loop.gs.A.base_gear.append(_card("Seal of Rage"))
    mine = [e for e in loop.activatable_abilities("A") if e.get("unit") is heimer]
    assert mine and mine[0]["eff"].effect in ("add_power", "gain_power")


def test_ivern_scores_with_all_four_tags():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    for tag in ("Bird", "Cat", "Dog"):
        loop.gs.A.base_units.append(_u(tag, 1, [tag]))
    ivern = UnitInPlay(card=_card("Ivern Friend to All"))
    bf0.add_unit("A", ivern)
    _fire(loop, ivern.card, "on_play")
    assert "Poro" in ivern.tags
    _fire(loop, ivern.card, "on_hold")
    assert loop.gs.points_A == 1


def test_jhin_banishes_big_spells_and_pays_off_at_four():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Jhin Virtuoso"))
    for i in range(4):
        loop._spell_to_trash(loop.gs.A, SpellCard(name=f"Big{i}", cost_energy=4))
    assert len(loop.gs.A.trash) == 4 and not loop.gs.A.banished
    assert loop.gs.A.total_runes_in_play() == 4 and len(loop.gs.A.hand) == 1
    loop._spell_to_trash(loop.gs.A, SpellCard(name="Small", cost_energy=1))
    assert len(loop.gs.A.trash) == 5


def test_zero_point_inflection_overflows():
    loop = _loop()
    zpi = _card("Zero Point Inflection")
    loop.gs.A.base_gear.append(zpi)
    loop.gs.A.hand = [UnitCard(name=f"H{i}") for i in range(9)]
    loop._draw_one(loop.gs.A)
    assert not loop.gs.A.hand and zpi in loop.gs.A.trash and loop.gs.points_B == 1


def test_jarvan_exemplar_follows_a_deploy():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Jarvan IV Exemplar of Demacia"), ready=True)
    unit = _u("Soldier", 3)
    loop.gs.A.base_units.append(unit)
    loop.gs.A.add_power(Domain.ORDER, 1)
    deploy = next(CARD_REGISTRY[n].instantiate() for n in CARD_REGISTRY
                  if "DEPLOY" in CARD_REGISTRY[n].keywords and CARD_REGISTRY[n].category.name == "GEAR"
                  and not n.startswith("Bomb"))
    loop._play_gear(deploy, "A", 1)
    assert unit in loop.gs.battlefields[1].units_A


def test_forge_of_the_fluft_lends_the_legend_an_attach():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Forge of the Fluft")
    legend = UnitInPlay(card=_card("Jinx Loose Cannon") if "Jinx Loose Cannon" in CARD_REGISTRY
                        else UnitCard(name="L"), ready=True)
    loop.gs.legend_unit_A = legend
    holder = _u("Holder")
    bf0.add_unit("A", holder)
    sword = _card("Long Sword")
    loop.gs.A.base_gear.append(sword)
    (idx, entry), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A"))
                     if e.get("unit") is legend and e["eff"].effect == "attach_equipment"]
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert holder.gear == [sword]
