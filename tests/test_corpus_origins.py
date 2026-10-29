"""Origins, card by card (BACKLOG.md section D): the sentences the corpus pass
found wrong or missing, each played through the engine."""

from __future__ import annotations

from riftbound.core.battlefield import DeployedGear
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext
from riftbound.core.player import Rune, RuneDeck
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import (_always, _cast_now, _deck, _fight, _pick, _play_spell, _setup,
                               _spec, _unit)


def _ctx(loop, p, card_name="Effect"):
    o = loop.gs.get_player(loop.gs.other(p.name))
    return EffectContext(loop, SpellCard(name=card_name), p, o, loop.gs.battlefields[0], {})


def _ability(loop, side, effect):
    return next(i for i, e in enumerate(loop.activatable_abilities(side))
                if e.get("eff") is not None and e["eff"].effect == effect)


def test_disintegrate_draws_when_it_kills():
    """'Deal 3 to a unit at a battlefield. If this kills it, do this: draw 1.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="D", might=1)]
    small = _unit("Small", 3)
    loop.gs.battlefields[0].add_unit("B", small)
    _cast_now(loop, a, "Disintegrate")
    assert small.card in b.trash and len(a.hand) == 1
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="D", might=1)]
    loop.gs.battlefields[0].add_unit("B", _unit("Big", 5))
    _cast_now(loop, a, "Disintegrate")
    assert not a.hand


def test_get_excited_deals_the_discarded_cards_energy_cost():
    """'Discard 1. Deal its Energy cost as damage to a unit at a battlefield.'"""
    loop, a, b = _setup()
    a.hand = [UnitCard(name="Pricey", might=1, cost_energy=4)]
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Get Excited!")
    assert enemy.damage == 4 and not a.hand


def test_unlicensed_armory_may_save_a_unit_for_fury():
    """'Discard 1, [tap]: Choose a friendly unit. The next time it would die this
    turn, you may pay [fury] to heal it, exhaust it, and recall it instead.'"""
    loop, a, b = _setup()
    a.base_gear.append(CARD_REGISTRY["Unlicensed Armory"].instantiate())
    a.hand = [UnitCard(name="Spare", might=1)]
    unit = _unit("Saved", 2)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "ward_unit"))
    assert not a.hand and unit.ward_turn == loop.gs.turn
    bf.add_unit("B", _unit("Killer", 5))
    fury = a.power_pool[Domain.FURY]
    _fight(loop, attacker="B")
    assert unit in a.base_units and a.power_pool.get(Domain.FURY, 0) == fury - 1


def test_vayne_hunter_may_pay_one_to_return_to_hand_when_she_conquers():
    """'When I conquer, you may pay [1] to return me to my owner's hand.'"""
    loop, a, b = _setup()
    vayne = _unit("Vayne Hunter")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", vayne)
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert vayne.card in a.hand and a.energy == 19


def test_meditation_draws_two_with_the_exhaust_else_one():
    """'As an additional cost to play this, you may exhaust a friendly unit. If you
    do, draw 2. Otherwise, draw 1.'"""
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    a.base_units.append(_unit("Tapper", 1))
    _play_spell(loop, a, "Meditation")
    assert len(a.hand) == 2
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    _play_spell(loop, a, "Meditation")
    assert len(a.hand) == 1


def test_stand_united_makes_buffs_give_one_more_this_turn():
    """'Buff a friendly unit. Buffs give an additional +1 [might] to friendly units
    this turn.'"""
    loop, a, b = _setup()
    target, other = _unit("Target", 2), _unit("Other", 2)
    other.might_counters = 1
    a.base_units.extend([target, other])
    _pick(loop, "Target")
    _cast_now(loop, a, "Stand United")
    loop._recompute_passives()
    assert target.might == 4 and other.might == 4
    loop.gs.turn += 1
    loop._recompute_passives()
    assert other.might == 3


def test_wielder_of_water_has_two_more_fighting_alone():
    """'While I'm attacking or defending alone, I have +2 [might].'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    wielder = _unit("Wielder of Water")
    foe = _unit("Foe", wielder.card.might + 1)
    bf.add_unit("A", wielder)
    bf.add_unit("B", foe)
    _fight(loop)
    assert foe not in bf.units_B and wielder in bf.units_A


def test_adaptatron_may_kill_a_gear_and_then_buffs_itself():
    """'When I conquer, you may kill a gear. If you do, buff me.'"""
    loop, a, b = _setup()
    adapt = _unit("Adaptatron")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", adapt)
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert adapt.might_counters == 0                       # no gear: nothing
    gear = GearCard(name="Kit")
    b.base_gear.append(gear)
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert gear in b.trash and adapt.might_counters == 1


def test_spirits_refuge_gives_buffed_friendly_units_deflect():
    """'Friendly buffed units have DEFLECT if they didn't already.'"""
    loop, a, b = _setup()
    a.base_gear.append(CARD_REGISTRY["Spirit's Refuge"].instantiate())
    buffed, plain = _unit("Buffed", 2), _unit("Plain", 2)
    buffed.might_counters = 1
    loop.gs.battlefields[0].add_unit("A", buffed)
    loop.gs.battlefields[1].add_unit("A", plain)
    loop._recompute_passives()
    assert buffed.has_keyword("DEFLECT") and not plain.has_keyword("DEFLECT")


def test_caitlyn_patrolling_takes_combat_damage_last_and_shoots_only_from_a_battlefield():
    """'I must be assigned combat damage last. [tap]: Deal damage equal to my Might
    to a unit at a battlefield. Use this ability only while I'm at a battlefield.'"""
    loop, a, b = _setup()
    cait = _unit("Caitlyn Patrolling")
    a.base_units.append(cait)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 9))
    loop._recompute_passives()
    assert cait.has_keyword("BACKLINE")
    usable = [e for e in loop.activatable_abilities("A") if e["eff"].effect == "deal_damage"]
    assert usable and not loop._ability_usable(a, usable[0])
    a.base_units.remove(cait)
    loop.gs.battlefields[1].add_unit("A", cait)
    usable = [e for e in loop.activatable_abilities("A") if e["eff"].effect == "deal_damage"]
    assert loop._ability_usable(a, usable[0])


def test_lee_sin_ascetic_can_have_any_number_of_buffs():
    """'[tap]: Buff me. I can have any number of buffs.'"""
    loop, a, b = _setup()
    lee = _unit("Lee Sin Ascetic")
    lee.might_counters = 1
    a.base_units.append(lee)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "buff_unit"))
    assert lee.might_counters == 2


def test_leona_zealot_shrinks_stunned_enemies_there_to_one():
    """'Stunned enemy units here have -8 [might], to a minimum of 1 [might].'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Leona Zealot"))
    stunned, awake = _unit("Stunned", 6), _unit("Awake", 6)
    stunned.stunned = True
    bf.add_unit("B", stunned)
    bf.add_unit("B", awake)
    loop._recompute_passives()
    assert stunned.might == 1 and awake.might == 6


def test_garbage_grabber_recycles_three_pays_one_and_taps_to_draw():
    """'Recycle 3 from your trash, [1], [tap]: Draw 1.'"""
    loop, a, b = _setup()
    a.base_gear.append(CARD_REGISTRY["Garbage Grabber"].instantiate())
    a.trash = [UnitCard(name=f"T{i}", might=1) for i in range(3)]
    a.deck.cards = [UnitCard(name="D", might=1)]
    loop._apply_activated_ability(a, b, _ability(loop, "A", "draw_cards"))
    assert not a.trash and len(a.hand) == 1 and a.energy == 19
    assert not loop._ability_usable(a, loop.activatable_abilities("A")[_ability(loop, "A", "draw_cards")])


def test_gemcraft_seer_gives_other_units_you_play_vision():
    """'Other friendly units have VISION.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Gemcraft Seer"))
    seen = []
    REGISTRY_predict = REGISTRY["predict"]
    try:
        REGISTRY["predict"] = lambda ctx, spec: ctx.loop is loop and seen.append(ctx.actor.name)
        loop._play_unit(UnitCard(name="New", might=1), "A")
    finally:
        REGISTRY["predict"] = REGISTRY_predict
    assert seen == ["A"]


def test_dr_mundo_recycles_three_from_the_trash_not_the_hand():
    """'At the start of your Beginning Phase, recycle 3 from your trash.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Dr. Mundo Expert"))
    a.trash = [UnitCard(name=f"T{i}", might=1) for i in range(4)]
    a.hand = [UnitCard(name="Keep", might=1)]
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert len(a.trash) == 1 and len(a.deck.cards) == 3 and [c.name for c in a.hand] == ["Keep"]


def test_ekko_recurrent_recycles_himself_and_readies_runes():
    """'DEATHKNELL - Recycle me to ready your runes.'"""
    loop, a, b = _setup()
    ekko = _unit("Ekko Recurrent")
    a.base_units.append(ekko)
    a.hand = [UnitCard(name="Keep", might=1)]
    a.rune_pool = {Domain.FURY: [Rune(Domain.FURY, ready=False)]}
    a.base_units.remove(ekko)
    loop._route_deaths([(ekko, "A")], loop.gs.battlefields[0], in_base=True)
    assert ekko.card in a.deck.cards and ekko.card not in a.trash
    assert [c.name for c in a.hand] == ["Keep"]


def test_unchecked_power_exhausts_every_friendly_unit():
    """'Exhaust all friendly units, then deal 12 to all units at battlefields.'"""
    loop, a, b = _setup()
    home = _unit("Home", 1)
    a.base_units.append(home)
    _cast_now(loop, a, "Unchecked Power")
    assert not home.ready


def test_warwick_hunter_kills_damaged_enemies_when_he_attacks():
    """'When I attack, destroy all damaged enemy units here.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Warwick Hunter"))
    hurt, fine = _unit("Hurt", 9), _unit("Fine", 9)
    hurt.damage = 1
    bf.add_unit("B", hurt)
    bf.add_unit("B", fine)
    loop._open_combat(bf, "A")
    assert hurt not in bf.units_B and fine in bf.units_B


def test_overt_operation_readies_for_buffs_then_buffs_everyone():
    """'For each friendly unit, you may spend its buff to ready it. Then buff all
    friendly units.'"""
    loop, a, b = _setup()
    tired = _unit("Tired", 2)
    tired.ready, tired.might_counters = False, 1
    plain = _unit("Plain", 2)
    a.base_units.append(tired)
    loop.gs.battlefields[1].add_unit("A", plain)
    _cast_now(loop, a, "Overt Operation")
    assert tired.ready and tired.might_counters == 1 and plain.might_counters == 1


def test_sabotage_recycles_a_non_unit_card_from_their_hand():
    """'Choose an opponent. They reveal their hand. Choose a non-unit card from it,
    and recycle that card.'"""
    loop, a, b = _setup()
    unit, spell = UnitCard(name="U", might=9), SpellCard(name="S")
    b.hand = [unit, spell]
    _cast_now(loop, a, "Sabotage")
    assert b.hand == [unit] and b.deck.cards[0] is spell


def test_pit_rookie_buffs_another_unit():
    """'When you play me, buff another friendly unit.'"""
    loop, a, b = _setup()
    rookie = loop._play_unit(CARD_REGISTRY["Pit Rookie"].instantiate(), "A")
    assert rookie.might_counters == 0                      # alone: no other unit
    other = _unit("Other", 1)
    a.base_units.append(other)
    second = loop._play_unit(CARD_REGISTRY["Pit Rookie"].instantiate(), "A")
    assert second.might_counters == 0 and rookie.might_counters + other.might_counters == 1


def test_mindsplitter_lets_you_pick_the_discard():
    """'They reveal their hand. Choose a card from it, and they discard that card.'"""
    loop, a, b = _setup()
    cheap, pricey = UnitCard(name="Cheap", might=1, cost_energy=1), UnitCard(name="Pricey", might=1, cost_energy=8)
    b.hand = [cheap, pricey]
    asked = []
    loop.chooser = lambda _l, kind, side, options, default, source: (
        asked.append(side) if kind == "discard" else None)
    _cast_now(loop, a, "Mindsplitter")
    assert asked == ["A"] and b.hand == [cheap] and pricey in b.trash


def test_invert_timelines_discards_whole_hands_then_draws_four():
    """'Each player discards their hand, then draws 4.'"""
    loop, a, b = _setup()
    for p in (a, b):
        p.hand = [UnitCard(name=f"H{i}", might=1) for i in range(3)]
        p.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    _cast_now(loop, a, "Invert Timelines")
    assert len(a.trash) == 3 and len(b.trash) == 3 and len(a.hand) == 4 and len(b.hand) == 4


def test_wallop_is_free_for_a_buff():
    """'As you play this, you may spend a buff as an additional cost. If you do,
    ignore this spell's cost. Ready a unit.'"""
    loop, a, b = _setup()
    buffed = _unit("Buffed", 2)
    buffed.might_counters = 1
    tired = _unit("Tired", 2)
    tired.ready = False
    a.base_units.extend([buffed, tired])
    _pick(loop, "Tired")
    _play_spell(loop, a, "Wallop")
    assert a.energy == 20 and buffed.might_counters == 0 and tired.ready


def test_cruel_patron_needs_a_friendly_unit_to_kill_as_its_cost():
    """'As an additional cost to play me, kill a friendly unit.'"""
    loop, a, b = _setup()
    assert loop._play_forbidden(a, CARD_REGISTRY["Cruel Patron"].instantiate())
    victim = _unit("Victim", 1)
    a.base_units.append(victim)
    a.hand = [CARD_REGISTRY["Cruel Patron"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert victim.card in a.trash and any(u.card.name == "Cruel Patron" for u in a.base_units)


def test_cull_the_weak_has_each_player_kill_their_own_choice():
    """'Each player kills one of their units.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Mine", 1))
    big, small = _unit("Big", 9), _unit("Small", 1)
    b.base_units.extend([big, small])
    asked = []
    loop.chooser = lambda _l, kind, side, options, default, source: (
        asked.append(side) if kind.startswith("kill_own") else None)
    _cast_now(loop, a, "Cull the Weak")
    assert asked == ["A", "B"] and small.card in b.trash and big in b.base_units


def test_acceptable_losses_each_player_kills_one_of_their_gear():
    """'Each player kills one of their gear.'"""
    loop, a, b = _setup()
    mine, theirs = GearCard(name="Mine"), GearCard(name="Theirs")
    a.base_gear.append(mine)
    b.base_gear.append(theirs)
    _cast_now(loop, a, "Acceptable Losses")
    assert mine in a.trash and theirs in b.trash


def test_forge_of_the_future_kills_itself_to_recycle_four_from_trashes():
    """'Kill this: Recycle up to 4 cards from trashes.'"""
    loop, a, b = _setup()
    forge = CARD_REGISTRY["Forge of the Future"].instantiate()
    a.base_gear.append(forge)
    b.trash = [UnitCard(name=f"T{i}", might=1) for i in range(5)]
    loop._apply_activated_ability(a, b, _ability(loop, "A", "recycle_from_trashes"))
    assert forge not in a.base_gear and len(b.trash) == 1 and len(b.deck.cards) == 4


def test_hidden_blade_kills_any_unit_there_and_its_controller_draws_two():
    """'Kill a unit at a battlefield. Its controller draws 2.'"""
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    loop.gs.battlefields[0].add_unit("A", mine)
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    _pick(loop, "Mine")
    _cast_now(loop, a, "Hidden Blade")
    assert mine.card in a.trash and len(a.hand) == 2 and not b.hand


def test_salvage_may_kill_up_to_one_gear_of_either_side():
    """'You may kill up to one gear. Draw 1.'"""
    loop, a, b = _setup()
    mine = GearCard(name="Mine")
    a.base_gear.append(mine)
    a.deck.cards = [UnitCard(name="D", might=1)]
    loop.chooser = lambda _l, kind, side, options, default, source: (
        next(i for i, o in enumerate(options) if getattr(o[2], "name", "") == "Mine")
        if kind.startswith("target") else None)
    _cast_now(loop, a, "Salvage")
    assert mine in a.trash and len(a.hand) == 1


def test_solari_chief_kills_a_stunned_enemy_else_stuns_it():
    """'Choose an enemy unit. If it is stunned, kill it. Otherwise, stun it.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Solari Chief")
    assert enemy.stunned and enemy in loop.gs.battlefields[0].units_B
    _cast_now(loop, a, "Solari Chief")
    assert enemy.card in b.trash


def test_spoils_of_war_is_cheaper_after_an_enemy_death():
    """'If an enemy unit has died this turn, this costs [2] less.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Spoils of War"].instantiate()
    full = loop._effective_cost(card, a)[0]
    loop.gs.friendly_unit_died_this_turn["A"] = True
    assert loop._effective_cost(card, a)[0] == full
    loop.gs.friendly_unit_died_this_turn["B"] = True
    assert loop._effective_cost(card, a)[0] == full - 2


def test_stormbringer_hits_a_battlefield_with_a_base_units_might_then_moves_it_there():
    """'Choose a friendly unit in your base. Deal damage equal to its Might to all
    enemies at a battlefield, then move your unit there.'"""
    loop, a, b = _setup()
    hero = _unit("Hero", 4)
    a.base_units.append(hero)
    bf = loop.gs.battlefields[1]
    e1, e2 = _unit("E1", 3), _unit("E2", 9)
    bf.add_unit("B", e1)
    bf.add_unit("B", e2)
    _cast_now(loop, a, "Stormbringer")
    assert e1.card in b.trash and e2.damage == 4 and hero in bf.units_A


def test_super_mega_death_rocket_comes_back_when_you_conquer():
    """'When you conquer, you may discard 1 to return this from your trash to your
    hand.'"""
    loop, a, b = _setup()
    rocket = CARD_REGISTRY["Super Mega Death Rocket!"].instantiate()
    a.trash.append(rocket)
    a.hand = [UnitCard(name="Spare", might=1)]
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Conqueror", 1))
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert a.hand == [rocket] and rocket not in a.trash


def test_noxian_guillotine_kills_at_the_next_damage_or_now_with_legion():
    """'Choose a unit. Kill it the next time it takes damage this turn. LEGION -
    Kill it now instead.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Noxian Guillotine")
    assert enemy in loop.gs.battlefields[0].units_B
    _ctx(loop, a).damage_units([enemy], 1)
    assert enemy.card in b.trash


def test_dragons_rage_moves_an_enemy_then_it_fights_another_there():
    """'Move an enemy unit. Then do this: Choose another enemy unit at its
    destination. They deal damage equal to their Mights to each other.'"""
    loop, a, b = _setup()
    mover, other = _unit("Mover", 3), _unit("Other", 2)
    loop.gs.battlefields[0].add_unit("B", mover)
    b.base_units.append(other)
    _cast_now(loop, a, "Dragon's Rage")
    assert mover in b.base_units and other.card in b.trash and mover.damage == 2


def test_last_breath_readies_a_unit_that_then_hits_an_enemy():
    """'Ready a friendly unit. It deals damage equal to its Might to an enemy at a
    battlefield.'"""
    loop, a, b = _setup()
    hero = _unit("Hero", 5)
    hero.ready = False
    a.base_units.append(hero)
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Last Breath")
    assert hero.ready and enemy.damage == 5


def test_zenith_blade_moves_a_friend_to_the_stunned_enemys_battlefield():
    """'Stun an enemy at a battlefield. You may move a friendly unit to that enemy
    unit's battlefield.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[1].add_unit("B", enemy)
    friend = _unit("Friend", 2)
    a.base_units.append(friend)
    _cast_now(loop, a, "Zenith Blade")
    assert enemy.stunned and friend in loop.gs.battlefields[1].units_A


def test_guerilla_warfare_lets_you_hide_for_free_this_turn():
    """'You can hide ignoring costs this turn.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    a.power_pool, a.floating_power, a.rune_pool = {}, {}, {}
    a.hand = [CARD_REGISTRY["Pakaa Cub"].instantiate()]
    assert not loop._hide_card("A", 0, 0)
    _cast_now(loop, a, "Guerilla Warfare")
    assert loop._hide_card("A", 0, 0)


def test_miss_fortune_bounty_hunter_taps_once():
    """'[tap]: Give a unit GANKING this turn.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Miss Fortune Bounty Hunter")
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    idx = _ability(loop, "A", "give_keyword")
    loop._apply_activated_ability(a, b, idx)
    assert unit.has_keyword("GANKING") and not loop.gs.legend_unit_A.ready
    assert not loop._ability_usable(a, loop.activatable_abilities("A")[idx])


def test_bullet_time_pays_x_power_for_x_damage_to_every_enemy_there():
    """'Pay an amount of [rune] to deal that much damage to all enemy units at a
    battlefield.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    e1, e2 = _unit("E1", 2), _unit("E2", 3)
    bf.add_unit("B", e1)
    bf.add_unit("B", e2)
    power = sum(a.power_pool.values())
    _cast_now(loop, a, "Bullet Time")
    assert e1.card in b.trash and e2.card in b.trash
    assert sum(a.power_pool.values()) == power - 3


def test_sett_the_boss_saves_a_buffed_unit_for_one_power():
    """'If a buffed unit you control would die, you may pay [rune], exhaust me, and
    spend its buff to heal it, exhaust it, and recall it instead.'"""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Sett The Boss")
    unit = _unit("Buffed", 2)
    unit.might_counters = 1
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit)
    bf.add_unit("B", _unit("Killer", 9))
    _fight(loop, attacker="B")
    assert unit in a.base_units and unit.might_counters == 0
    assert not loop.gs.legend_unit_A.ready


def test_zhonyas_hourglass_dies_instead_of_a_friendly_unit():
    """'If a friendly unit would die, kill this instead. Heal that unit, exhaust
    it, and recall it.'"""
    loop, a, b = _setup()
    hourglass = CARD_REGISTRY["Zhonya's Hourglass"].instantiate()
    a.base_gear.append(hourglass)
    unit = _unit("Saved", 2)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit)
    bf.add_unit("B", _unit("Killer", 9))
    _fight(loop, attacker="B")
    assert unit in a.base_units and hourglass in a.trash


def test_time_warp_takes_another_turn():
    """'Take a turn after this one. Banish this.'"""
    loop, a, b = _setup()
    _play_spell(loop, a, "Time Warp")
    loop._end_turn()
    assert loop.gs.active == "A"
    assert any(c.name == "Time Warp" for c in a.banished)


def test_brazen_buccaneer_discards_for_two_less():
    """'As you play me, you may discard a card as an additional cost. If you do,
    reduce my cost by [2].'"""
    loop, a, b = _setup()
    a.hand = [CARD_REGISTRY["Brazen Buccaneer"].instantiate(), UnitCard(name="Junk", might=1)]
    full = a.hand[0].cost_energy
    loop._apply_action(a, ("UNIT", 0, 0))
    assert a.energy == 20 - (full - 2) and [c.name for c in a.trash] == ["Junk"]


def test_blind_fury_plays_their_top_card_which_stays_theirs():
    """'Each opponent reveals the top card of their Main Deck. Choose one and banish
    it, then play it, ignoring its cost.'"""
    loop, a, b = _setup()
    top = UnitCard(name="TheirTop", might=3)
    b.deck.cards = [top]
    _cast_now(loop, a, "Blind Fury")
    mine = next(u for u in a.base_units if u.card is top)
    a.base_units.remove(mine)
    loop._route_deaths([(mine, "A")], loop.gs.battlefields[0], in_base=True)
    assert top in b.trash and top not in a.trash
