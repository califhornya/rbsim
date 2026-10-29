"""Spiritforged, card by card (BACKLOG.md section D): the sentences the corpus
pass found wrong or missing, each played through the engine."""

from __future__ import annotations

from riftbound.core.battlefield import DeployedGear
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext
from riftbound.core.player import Rune, RuneDeck
from riftbound.core.state import ChainItem
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import (_always, _cast_now, _deck, _fight, _pick, _play_spell, _setup,
                               _spec, _unit)


def _ctx(loop, p, card=None):
    o = loop.gs.get_player(loop.gs.other(p.name))
    return EffectContext(loop, card or SpellCard(name="Effect"), p, o, loop.gs.battlefields[0], {})


def _ability(loop, side, effect):
    return next(i for i, e in enumerate(loop.activatable_abilities(side))
                if e.get("eff") is not None and e["eff"].effect == effect)


def _attack_at(loop, bf_idx=0):
    """Put the combat at battlefield `bf_idx` in its showdown, A attacking."""
    bf = loop.gs.battlefields[bf_idx]
    loop.gs.showdown_active, loop.gs.showdown_bf_idx, loop.gs.showdown_attacker = True, bf_idx, "A"
    loop._open_combat(bf, "A")
    return bf


def test_counters_have_no_cost_limit_unless_printed():
    """'Counter a spell unless its controller pays [2]' (Hard Bargain) counters a
    [6] spell; Defy keeps its printed [4] limit."""
    loop, a, b = _setup()
    big = SpellCard(name="Big", cost_energy=6)
    loop.gs.chain.append(ChainItem(player="B", card=big, bf_idx=0))
    b.energy = 0
    _cast_now(loop, a, "Hard Bargain")
    assert not loop.gs.chain
    loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="Big2", cost_energy=6), bf_idx=0))
    _cast_now(loop, a, "Defy")
    assert loop.gs.chain


def test_not_so_fast_counters_only_an_enemy_spell_choosing_yours():
    """'Counter an enemy spell or ability that chooses a friendly unit or gear.'"""
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    loop.gs.battlefields[0].add_unit("A", mine)
    aimed = ChainItem(player="B", card=SpellCard(name="Aimed"), bf_idx=0)
    aimed.declared = {(0, 0, 0): ("target:deal_damage", 0, [mine])}
    loop.gs.chain.append(aimed)
    assert loop._spell_has_targets(CARD_REGISTRY["Not So Fast"].instantiate(), "A", 0)
    _cast_now(loop, a, "Not So Fast")
    assert not loop.gs.chain
    loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="Elsewhere"), bf_idx=0))
    assert not loop._spell_has_targets(CARD_REGISTRY["Not So Fast"].instantiate(), "A", 0)


def test_riposte_counters_and_pumps_by_the_spells_cost():
    """'Choose a friendly unit and a spell. Counter that spell and give that unit
    +[might] equal to that spell's energy cost this turn.'"""
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    a.base_units.append(mine)
    loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="Five", cost_energy=5), bf_idx=0))
    _cast_now(loop, a, "Riposte")
    assert not loop.gs.chain and mine.might == 7


def test_against_the_odds_counts_enemies_where_the_unit_is():
    """'Give a friendly unit at a battlefield +2 [might] this turn for each enemy
    unit there.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[1]
    mine = _unit("Mine", 1)
    bf.add_unit("A", mine)
    for i in range(3):
        bf.add_unit("B", _unit(f"E{i}", 1))
    _cast_now(loop, a, "Against the Odds")
    assert mine.might == 7


def test_targeted_pumps_choose_a_unit():
    """Blood Rush, Feral Strength, Punch First, Gem Jammer had no target."""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    loop.gs.battlefields[1].add_unit("A", unit)
    for name in ("Blood Rush", "Feral Strength", "Punch First"):
        _pick(loop, "Unit")
        _cast_now(loop, a, name)
    assert unit.keyword_value("ASSAULT") == 2 and unit.might == 2 + 2 + 5
    loop._play_unit(CARD_REGISTRY["Gem Jammer"].instantiate(), "A")
    assert any(u.has_keyword("GANKING") for u in a.base_units + loop.gs.battlefields[1].units_A)


def test_detonate_kills_a_gear_and_its_controller_draws():
    """'Kill a gear. Its controller draws 2.'"""
    loop, a, b = _setup()
    mine = GearCard(name="Mine")
    a.base_gear.append(mine)
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    loop.chooser = lambda _l, kind, side, options, default, source: (
        next(i for i, o in enumerate(options) if getattr(o[2], "name", "") == "Mine")
        if kind.startswith("target") else None)
    _cast_now(loop, a, "Detonate")
    assert mine in a.trash and len(a.hand) == 2


def test_angle_shot_detaches_an_enemy_equipment():
    """'Choose a unit and an Equipment with the same controller. Attach that
    Equipment to that unit or detach that Equipment from that unit. Draw 1.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 2)
    blade = CARD_REGISTRY["Serrated Dirk"].instantiate()
    enemy.gear.append(blade)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.deck.cards = [UnitCard(name="D", might=1)]
    _cast_now(loop, a, "Angle Shot")
    assert not enemy.gear and blade in b.base_gear and len(a.hand) == 1


def test_battering_ram_costs_at_least_one():
    """'I cost [1] less for each card you've played this turn, to a minimum of [1].'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Battering Ram"].instantiate()
    loop.gs.cards_played_this_turn["A"] = 20
    assert loop._effective_cost(card, a)[0] == 1


def test_sudden_storm_deals_four_to_an_attacker():
    """'Deal 2 to a unit at a battlefield. If it's attacking, deal 4 to it instead.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    atk = _unit("Atk", 9)
    bf.add_unit("B", _unit("Def", 9))
    bf.add_unit("A", atk)
    _attack_at(loop, 0)
    _pick(loop, "Atk")
    _cast_now(loop, b, "Sudden Storm")
    assert atk.damage == 4


def test_thwonk_stuns_only_an_attacking_unit():
    """'Stun an attacking unit.'"""
    loop, a, b = _setup()
    assert not loop._spell_has_targets(CARD_REGISTRY["Thwonk!"].instantiate(), "B", 0)
    bf = loop.gs.battlefields[0]
    atk = _unit("Atk", 3)
    bf.add_unit("B", _unit("Def", 3))
    bf.add_unit("A", atk)
    _attack_at(loop, 0)
    _cast_now(loop, b, "Thwonk!")
    assert atk.stunned


def test_piercing_light_hits_a_second_other_unit():
    """'Deal 2 to a unit at a battlefield, then deal 2 to up to one other unit.'"""
    loop, a, b = _setup()
    e1, e2 = _unit("E1", 9), _unit("E2", 9)
    loop.gs.battlefields[0].add_unit("B", e1)
    b.base_units.append(e2)
    _cast_now(loop, a, "Piercing Light")
    assert e1.damage == 2 and e2.damage == 2


def test_rell_magnetic_plays_and_attaches_a_cheap_equipment_when_she_attacks():
    """'When I attack, you may play an Equipment with Energy cost no more than [2],
    ignoring its cost. If you do, then do this: Attach it to me.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    rell = _unit("Rell Magnetic")
    bf.add_unit("A", rell)
    bf.add_unit("B", _unit("Def", 9))
    dirk = CARD_REGISTRY["Serrated Dirk"].instantiate()
    a.hand = [dirk]
    loop._open_combat(bf, "A")
    assert dirk in rell.gear and a.energy == 20


def test_rumble_hotheaded_recycles_a_unit_to_play_a_mech_cheaper():
    """'When I conquer, you may recycle another friendly unit to play a Mech from
    your trash. Reduce its Energy cost by the Might of the unit you recycled.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    rumble, fodder = _unit("Rumble Hotheaded"), _unit("Fodder", 3)
    bf.add_unit("A", rumble)
    a.base_units.append(fodder)
    mech = UnitCard(name="Old Mech", might=4, cost_energy=5, tags=["Mech"])
    a.trash.append(mech)
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert any(u.card is mech for u in a.base_units) and a.energy == 18
    assert fodder.card in a.deck.cards


def test_lucian_gunslinger_deals_his_assault():
    """'When I attack, deal damage equal to my ASSAULT to an enemy unit here.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    lucian = _unit("Lucian Gunslinger")
    lucian.turn_keywords.append("ASSAULT 2")
    enemy = _unit("Enemy", 9)
    bf.add_unit("A", lucian)
    bf.add_unit("B", enemy)
    loop._open_combat(bf, "A")
    assert enemy.damage == lucian.keyword_value("ASSAULT") == 3


def test_brutalizer_gives_two_only_the_turn_it_is_attached():
    """'If this was attached to me this turn, I have an additional +2 [might].'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    brut = CARD_REGISTRY["Brutalizer"].instantiate()
    unit.gear.append(brut)
    loop._fire_attached(unit, "A")
    loop._recompute_passives()
    with_bonus = unit.might
    loop.gs.turn += 1
    loop._recompute_passives()
    assert with_bonus - unit.might == 2


def test_poro_snax_kills_itself_to_draw():
    """'[1] [calm], [tap], Kill this: Draw 1.'"""
    loop, a, b = _setup()
    snax = CARD_REGISTRY["Poro Snax"].instantiate()
    a.base_gear.append(snax)
    a.deck.cards = [UnitCard(name="D", might=1)]
    loop._apply_activated_ability(a, b, _ability(loop, "A", "draw_cards"))
    assert len(a.hand) == 1 and snax not in a.base_gear and snax in a.trash


def test_azir_ascendant_swaps_once_a_turn_and_may_take_an_equipment():
    """'[calm]: Choose a unit you control. Move me to its location and it to my
    original location. If it's equipped, you may attach one of its Equipment to
    me. Use only once per turn.'"""
    loop, a, b = _setup()
    azir = _unit("Azir Ascendant")
    a.base_units.append(azir)
    other = _unit("Other", 2)
    dirk = CARD_REGISTRY["Serrated Dirk"].instantiate()
    other.gear.append(dirk)
    loop.gs.battlefields[0].add_unit("A", other)
    idx = _ability(loop, "A", "swap_position")
    loop._apply_activated_ability(a, b, idx)
    assert azir in loop.gs.battlefields[0].units_A and dirk in azir.gear
    assert not loop._ability_usable(a, loop.activatable_abilities("A")[idx])


def test_jax_unmatched_gives_equipment_in_hand_quick_draw():
    """'Your Equipment everywhere have QUICK-DRAW.'"""
    from riftbound.core.legality import _reaction_actions
    loop, a, b = _setup()
    a.hand = [CARD_REGISTRY["Serrated Dirk"].instantiate()]
    assert not any(ga.kind == "GEAR" for ga in _reaction_actions(loop, a))
    a.base_units.append(_unit("Jax Unmatched"))
    assert any(ga.kind == "GEAR" for ga in _reaction_actions(loop, a))


def test_needlessly_large_yordle_also_costs_calm_less():
    """'I cost [2] [calm] less for each point you scored from holding this turn.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Needlessly Large Yordle"].instantiate()
    energy, power = loop._effective_cost(card, a)
    loop.gs.hold_points_this_turn["A"] = 1
    e2, p2 = loop._effective_cost(card, a)
    assert energy - e2 == 2 and (power or 0) - (p2 or 0) == min(1, power or 0)


def test_forecaster_gives_mechs_you_play_vision(monkeypatch):
    """'Your Mechs have VISION.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Forecaster"))
    seen = []
    monkeypatch.setitem(REGISTRY, "predict", lambda ctx, spec: seen.append(1))
    loop._play_unit(UnitCard(name="Plain", might=1), "A")
    loop._play_token("Mech", "A")
    assert seen == [1]


def test_breakneck_mech_enters_ready_with_another_mech():
    """'I enter ready if you control another Mech.'"""
    loop, a, b = _setup()
    alone = loop._play_unit(CARD_REGISTRY["Breakneck Mech"].instantiate(), "A")
    loop2, a2, b2 = _setup()
    loop2._play_token("Mech", "A")
    with_mech = loop2._play_unit(CARD_REGISTRY["Breakneck Mech"].instantiate(), "A")
    assert not alone.ready and with_mech.ready


def test_pickpocket_gold_only_if_it_killed_a_gear():
    """'You may kill a gear with Energy cost no more than [1]. If you do, play a
    Gold gear token exhausted.'"""
    loop, a, b = _setup()
    loop._play_unit(CARD_REGISTRY["Pickpocket"].instantiate(), "A")
    assert not a.base_gear
    cheap = GearCard(name="Cheap", cost_energy=1)
    b.base_gear.append(cheap)
    loop._play_unit(CARD_REGISTRY["Pickpocket"].instantiate(), "A")
    assert cheap in b.trash and [g.name for g in a.base_gear] == ["Gold"]


def test_rocket_barrage_hits_a_unit_in_a_base():
    """'Choose one - Deal 4 damage to a unit in a base. - Kill a gear.'"""
    loop, a, b = _setup()
    at_bf, in_base = _unit("AtBf", 9), _unit("InBase", 9)
    loop.gs.battlefields[0].add_unit("B", at_bf)
    b.base_units.append(in_base)
    loop.chooser = lambda _l, kind, side, options, default, source: 0 if kind == "mode" else None
    _cast_now(loop, a, "Rocket Barrage")
    assert in_base.damage == 4 and at_bf.damage == 0


def test_bard_mercurial_moves_to_an_open_battlefield():
    """'... move any number of your units to an open battlefield.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Sivir Battle Mistress")
    loop.gs.battlefields[0].add_unit("B", _unit("Theirs", 1))
    x = _unit("X", 1)
    a.base_units.append(x)
    a.hand = [CARD_REGISTRY["Bard Mercurial"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert x in loop.gs.battlefields[1].units_A


def test_bellows_breath_hits_up_to_three():
    """'Deal 1 to up to three units at the same location.'"""
    loop, a, b = _setup()
    units = [_unit(f"E{i}", 5) for i in range(3)]
    for u in units:
        loop.gs.battlefields[0].add_unit("B", u)
    _cast_now(loop, a, "Bellows Breath")
    assert [u.damage for u in units] == [1, 1, 1]


def test_rumble_scrapper_and_danger_zone_reach_every_mech():
    """'Your Mechs have +1 [might].' / 'Give your Mechs +1 [might] this turn.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Rumble Scrapper"))
    far = loop._play_token("Mech", "A")
    loop._recompute_passives()
    assert far.might == 4
    _cast_now(loop, a, "Danger Zone")
    assert far.might == 5


def test_fae_dragon_buffs_four_and_makes_gold_when_you_spend_a_buff():
    """'When you play me, buff up to four friendly units. When you spend a buff,
    play a Gold gear token exhausted.'"""
    loop, a, b = _setup()
    units = [_unit(f"U{i}", 1) for i in range(4)]
    a.base_units.extend(units)
    loop._play_unit(CARD_REGISTRY["Fae Dragon"].instantiate(), "A")
    assert sum(u.might_counters for u in units) >= 3
    loop._spend_buff(units[0], "A")
    assert [g.name for g in a.base_gear] == ["Gold"]


def test_strike_down_hits_with_an_equipped_unit_then_detaches():
    """'Choose an equipped friendly unit. It deals damage equal to its Might to an
    enemy unit. Then detach an Equipment from it.'"""
    loop, a, b = _setup()
    unit = _unit("Equipped", 3)
    dirk = CARD_REGISTRY["Serrated Dirk"].instantiate()
    unit.gear.append(dirk)
    a.base_units.append(unit)
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    might = unit.might
    _cast_now(loop, a, "Strike Down")
    assert enemy.damage == might and not unit.gear and dirk in a.base_gear


def test_kato_the_arm_lends_his_keywords():
    """'When I move to a battlefield, give another friendly unit my keywords and +
    [might] equal to my Might this turn.'"""
    loop, a, b = _setup()
    kato, friend = _unit("Kato the Arm"), _unit("Friend", 1)
    a.base_units.extend([kato, friend])
    loop._move_unit_by_effect(kato, loop.gs.battlefields[0])
    assert friend.has_keyword("DEFLECT") and friend.might == 1 + kato.might


def test_ancient_henge_and_hextech_anomaly_convert_any_amount():
    """'Pay any amount of Energy to ADD that much [rune]' / 'Pay any amount of
    [rune] to ADD that much Energy.'"""
    loop, a, b = _setup()
    a.energy = 3
    a.base_gear.append(CARD_REGISTRY["Ancient Henge"].instantiate())
    power = sum(a.power_pool.values())
    loop._apply_activated_ability(a, b, _ability(loop, "A", "convert_x"))
    assert a.energy == 0 and sum(a.power_pool.values()) == power + 3
    loop, a, b = _setup()
    a.energy = 0
    a.base_gear.append(CARD_REGISTRY["Hextech Anomaly"].instantiate())
    a.power_pool, a.floating_power = {Domain.FURY: 2}, {Domain.FURY: 2}
    loop._apply_activated_ability(a, b, _ability(loop, "A", "convert_x"))
    assert a.energy == 2 and not a.power_pool.get(Domain.FURY)


def test_factory_recall_can_return_your_own_gear():
    """'Return a gear to its owner's hand.'"""
    loop, a, b = _setup()
    mine = GearCard(name="Mine")
    a.base_gear.append(mine)
    _cast_now(loop, a, "Factory Recall")
    assert mine in a.hand


def test_edge_of_night_attaches_only_from_face_down():
    """'When you play this from face down, attach it to a unit you control.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    edge = CARD_REGISTRY["Edge of Night"].instantiate()
    loop._play_gear(edge, "A", 0, from_zone="hand")
    assert edge in a.base_gear and not unit.gear
    edge2 = CARD_REGISTRY["Edge of Night"].instantiate()
    loop._play_gear(edge2, "A", 0, from_zone="facedown")
    assert edge2 in unit.gear


def test_draven_audacious_scores_once_a_turn_and_gives_a_point_only_dying_in_combat():
    """'The first time I win a combat each turn, you score 1 point. When I die in
    combat, choose an opponent. They score 1 point.'"""
    loop, a, b = _setup()
    draven = _unit("Draven Audacious")
    a.base_units.append(draven)
    loop._fire_units_trigger("on_win_combat", "A")
    loop._fire_units_trigger("on_win_combat", "A")
    assert loop.gs.points_A == 1
    a.base_units.remove(draven)
    loop._route_deaths([(draven, "A")], loop.gs.battlefields[0], in_base=True)
    assert loop.gs.points_B == 0


def test_ezreal_prodigy_makes_optional_costs_cheaper():
    """'Optional additional costs you pay cost [1] or [rune] less.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Ezreal Prodigy"))
    a.hand = [CARD_REGISTRY["Sea Monkey"].instantiate()]
    cost = a.hand[0].cost_energy
    loop._apply_action(a, ("UNIT", 0, 0))
    monkey = next(u for u in a.base_units if u.card.name == "Sea Monkey")
    assert a.energy == 20 - cost and monkey.might_counters == 1


def test_guards_may_pay_order_to_ready_the_soldier():
    """'Play a 2 [might] Sand Soldier unit token. You may pay [order] to ready it.'"""
    loop, a, b = _setup()
    order = a.power_pool[Domain.ORDER]
    _cast_now(loop, a, "Guards!")
    soldier = next(u for u in a.base_units if u.card.name == "Sand Soldier")
    assert soldier.ready and a.power_pool.get(Domain.ORDER, 0) == order - 1


def test_blood_money_gives_two_gold_for_a_friendly_kill():
    """'Kill a unit at a battlefield with 2 [might] or less. If it was an enemy
    unit, play a Gold gear token exhausted. If it was a friendly unit, play two.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 2))
    _cast_now(loop, a, "Blood Money")
    assert len(a.base_gear) == 1
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Mine", 2))
    _pick(loop, "Mine")
    _cast_now(loop, a, "Blood Money")
    assert len(a.base_gear) == 2


def test_deathgrip_kills_a_friend_to_pump_another():
    """'Kill a friendly unit. If you do, give +[might] equal to its Might to another
    friendly unit this turn. Draw 1.'"""
    loop, a, b = _setup()
    fodder, hero = _unit("Fodder", 4), _unit("Hero", 2)
    a.base_units.extend([fodder, hero])
    a.deck.cards = [UnitCard(name="D", might=1)]
    _pick(loop, "Fodder")
    loop.chooser = (lambda _l, kind, side, options, default, source:
                    next((i for i, o in enumerate(options) if getattr(getattr(o, "card", None), "name", "")
                          == ("Fodder" if kind == "target:kill_unit" else "Hero")), None)
                    if kind.startswith("target") else None)
    _cast_now(loop, a, "Deathgrip")
    assert fodder.card in a.trash and hero.might == 6 and len(a.hand) == 1


def test_drag_under_is_cheaper_from_outside_the_hand():
    """'I cost [2] less to play from anywhere other than your hand.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Drag Under"].instantiate()
    assert loop._effective_cost(card, a, from_zone="trash")[0] == loop._effective_cost(card, a)[0] - 2


def test_rally_the_troops_buffs_units_played_this_turn():
    """'When a friendly unit is played this turn, buff it. Draw 1.'"""
    loop, a, b = _setup()
    _cast_now(loop, a, "Rally the Troops")
    unit = loop._play_unit(UnitCard(name="New", might=1), "A")
    token = loop._play_token("Recruit", "A")
    assert unit.might_counters == 1 and token.might_counters == 1


def test_soraka_wanderer_saves_a_weaker_unit_there():
    """'If another unit you control here would die, if it has less Might than me,
    instead heal it, exhaust it, and recall it.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    soraka, weak = _unit("Soraka Wanderer"), _unit("Weak", 1)
    bf.add_unit("A", soraka)
    bf.add_unit("A", weak)
    _ctx(loop, b).damage_units([weak], 5)
    assert weak in a.base_units and weak.damage == 0


def test_undertitan_adds_two_when_revealed():
    """'As I'm revealed from your deck, ADD [2].'"""
    loop, a, b = _setup()
    a.deck.cards = [CARD_REGISTRY["Undertitan"].instantiate()]
    _deck(a, CARD_REGISTRY["Undertitan"].instantiate())
    energy = a.energy
    REGISTRY["reveal_top"](_ctx(loop, a), {"target_filter": {"is_spell": True}})
    assert a.energy == energy + 2


def test_undertitan_pumps_every_other_unit_of_yours():
    """'When you play me, give your other units +2 [might] this turn.'"""
    loop, a, b = _setup()
    far = _unit("Far", 1)
    loop.gs.battlefields[1].add_unit("A", far)
    loop._play_unit(CARD_REGISTRY["Undertitan"].instantiate(), "A")
    assert far.might == 3


def test_fiora_worthy_readies_a_unit_that_becomes_mighty():
    """'When a unit you control becomes MIGHTY, you may pay [order] to ready it.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Fiora Worthy"))
    unit = _unit("Grower", 4)
    unit.ready = False
    a.base_units.append(unit)
    loop._recompute_passives()
    assert not unit.ready
    unit.might_counters = 1
    loop._recompute_passives()
    assert unit.ready


def test_relentless_pursuit_moves_attaches_and_may_return_after_conquering():
    """'Move a friendly unit. You may attach an Equipment with the same controller
    to it. This turn, that unit has "When I conquer, you may move me to my base."'"""
    loop, a, b = _setup()
    unit = _unit("Runner", 2)
    a.base_units.append(unit)
    dirk = CARD_REGISTRY["Serrated Dirk"].instantiate()
    a.base_gear.append(dirk)
    _cast_now(loop, a, "Relentless Pursuit")
    where = loop._locate_unit(unit)[1]
    assert where is not None and dirk in unit.gear
    loop.chooser = _always(True)
    loop._fire_scoring_trigger("on_conquer", where, "A")
    assert unit in a.base_units


def test_shurelyas_requiem_and_on_the_hunt_ready_all_your_units():
    """'Ready your units.'"""
    loop, a, b = _setup()
    x, y = _unit("X", 1), _unit("Y", 1)
    x.ready = y.ready = False
    loop.gs.battlefields[1].add_unit("A", x)
    a.base_units.append(y)
    _cast_now(loop, a, "On the Hunt")
    assert x.ready and y.ready


def test_counter_strike_prevents_the_next_damage():
    """'Choose a unit. The next time that unit would be dealt damage this turn,
    prevent it. Draw 1.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 3)
    a.base_units.append(unit)
    _cast_now(loop, a, "Counter Strike")
    _ctx(loop, b).damage_units([unit], 2)
    assert unit.damage == 0
    _ctx(loop, b).damage_units([unit], 2)
    assert unit.damage == 2


def test_irelia_blade_dancer_readies_a_unit_you_choose():
    """'When you choose a friendly unit, you may exhaust me and pay [rune] to ready
    it.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Irelia Blade Dancer")
    unit = _unit("Unit", 2)
    unit.ready = False
    a.base_units.append(unit)
    loop._note_chosen(SpellCard(name="Aim"), "A", [unit])
    assert unit.ready and not loop.gs.legend_unit_A.ready


def test_defiant_dance_pumps_one_and_shrinks_another():
    """'Give a unit +2 [might] this turn and another unit -2 [might] this turn.'"""
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 3), _unit("Theirs", 3)
    a.base_units.append(mine)
    b.base_units.append(theirs)
    _pick(loop, "Mine")
    loop.chooser = (lambda _l, kind, side, options, default, source:
                    next((i for i, o in enumerate(options)
                          if getattr(getattr(o, "card", None), "name", "") in ("Mine", "Theirs")), None)
                    if kind.startswith("target") else None)
    _cast_now(loop, a, "Defiant Dance")
    assert sorted([mine.might, theirs.might]) == [1, 5]


def test_azir_emperor_needs_an_equipment_played_this_turn():
    """'[1], [tap]: Play a 2 [might] Sand Soldier unit token to your base. Use only if
    you've played an Equipment this turn.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Azir Emperor of the Sands")
    entry = loop.activatable_abilities("A")[_ability(loop, "A", "play_token")]
    assert not loop._ability_usable(a, entry)
    loop.gs.played_cards_this_turn["A"].append(CARD_REGISTRY["Serrated Dirk"].instantiate())
    assert loop._ability_usable(a, entry)


def test_arcane_shift_blinks_a_friend_hits_an_enemy_and_is_banished():
    """'Banish a friendly unit, then its owner plays it, ignoring its cost. Deal 3
    to an enemy unit at a battlefield. Banish this.'"""
    loop, a, b = _setup()
    friend = _unit("Friend", 2)
    friend.damage = 1
    loop.gs.battlefields[1].add_unit("A", friend)
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _play_spell(loop, a, "Arcane Shift")
    # Played back where it was (a battlefield A controls): tests/test_g2_spiritforged.py.
    back = loop.gs.battlefields[1].units_A
    assert friend not in back and len(back) == 1 and back[0].card is friend.card and back[0].damage == 0
    assert enemy.damage == 3 and any(c.name == "Arcane Shift" for c in a.banished)


def test_renata_chem_baroness_makes_gold_add_one_more_near_victory():
    """'While your score is within 3 points of the Victory Score, your Gold ADD an
    additional [1].'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Renata Glasc Chem-Baroness")
    a.base_gear.append(CARD_REGISTRY["Gold"].instantiate())
    a.energy = 0
    loop.gs.points_A = loop.gs.victory_score - 3
    loop._apply_activated_ability(a, b, _ability(loop, "A", "gain_power_any_domain"))
    assert a.energy == 1


def test_show_of_strength_counts_mighty_units_in_base():
    """'Draw 1 for each of your MIGHTY units.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Big", 5))
    loop.gs.battlefields[0].add_unit("A", _unit("Big2", 6))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    _cast_now(loop, a, "Show of Strength")
    assert len(a.hand) == 2


def test_the_zero_drive_banishes_its_dead_unit_and_plays_it_back():
    """'[3] [mind], Banish this: Play all units banished with this, ignoring their
    costs. (Use only if unattached.)' and its unit's 'DEATHKNELL - Banish me.'"""
    loop, a, b = _setup()
    drive = CARD_REGISTRY["The Zero Drive"].instantiate()
    unit = _unit("Carrier", 3)
    unit.gear.append(drive)
    a.base_units.append(unit)
    a.base_units.remove(unit)
    loop._route_deaths([(unit, "A")], loop.gs.battlefields[0], in_base=True)
    assert unit.card in a.banished and drive in a.base_gear
    loop._apply_activated_ability(a, b, _ability(loop, "A", "play_banished_with_this"))
    assert any(u.card is unit.card for u in a.base_units) and drive not in a.base_gear
