"""Radiance, card by card (BACKLOG.md section D): the sentences the corpus pass
found wrong or missing, each played through the engine."""

from __future__ import annotations

from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.player import Rune, RuneDeck
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import (_always, _cast_now, _deck, _fight, _pick, _setup, _unit)
from test_corpus_vendetta import (_ability, _attack_at, _ctx, _runes, _start_turn, _usable)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _tired(name, might=None):
    unit = _unit(name, might)
    unit.ready = False
    return unit


def _bf_gear(loop, side, name):
    return [(bf, dg) for bf in loop.gs.battlefields for dg in bf.gear_for(side) if dg.card.name == name]


# -- Part 1 (BACKLOG.md D, Radiance RAD-001..055) ---------------------------------

def test_amateur_demolitionist_deploys_a_bomb_that_hits_an_enemy_there():
    """'When you play me, play a Bomb gear token to a battlefield. (It has DEPLOY.
    When it dies, deal 2 to an enemy there and kill your other Bombs there.)'"""
    loop, a, b = _setup()
    loop._play_unit(_card("Amateur Demolitionist"), "A")
    loop._play_unit(_card("Amateur Demolitionist"), "A")
    bombs = _bf_gear(loop, "A", "Bomb")
    assert len(bombs) == 2 and not a.base_gear
    bf = bombs[0][0]
    enemy = _unit("Enemy", 5)
    bf.add_unit("B", enemy)
    loop._kill_deployed_gear(bf, "A", [bombs[0][1]])
    assert enemy.damage == 4 and not bf.gear_A     # the other Bomb there dies too


def test_banner_of_conquest_gives_units_here_assault():
    """'Friendly units here have ASSAULT.'"""
    loop, a, b = _setup()
    loop._play_gear(_card("Banner of Conquest"), "A", 0)
    here, there = _unit("Here", 2), _unit("There", 2)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    loop._recompute_passives()
    assert here.has_keyword("ASSAULT") and not there.has_keyword("ASSAULT")


def test_bilgewater_tracker_deals_one_to_each_of_two_units():
    """'When you play me, deal 1 to each of up to 2 units.'"""
    loop, a, b = _setup()
    e1, e2 = _unit("E1", 3), _unit("E2", 3)
    loop.gs.battlefields[0].add_unit("B", e1)
    loop.gs.battlefields[1].add_unit("B", e2)
    loop._play_unit(_card("Bilgewater Tracker"), "A")
    assert (e1.damage, e2.damage) == (1, 1)


def test_brawl_gives_assault_equal_to_the_units_might():
    """'Give a unit ASSAULT this turn equal to its Might.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 3)
    loop.gs.battlefields[0].add_unit("A", unit)
    _pick(loop, "Unit")
    _cast_now(loop, a, "Brawl")
    assert unit.keyword_value("ASSAULT") == 3


def test_lingering_animus_enters_ready_after_a_friendly_gear_died():
    """'I enter ready if a friendly unit or gear died this turn.'"""
    loop, a, b = _setup()
    assert not loop._play_unit(_card("Lingering Animus"), "A").ready
    loop, a, b = _setup()
    loop._deploy_gear("A", loop.gs.battlefields[0], _card("Banner of Conquest"))
    loop._kill_deployed_gear(loop.gs.battlefields[0], "A", list(loop.gs.battlefields[0].gear_A))
    assert loop._play_unit(_card("Lingering Animus"), "A").ready


def test_scorched_earth_splits_five_at_one_battlefield():
    """'Deal 5 damage split among units at a single battlefield.'"""
    loop, a, b = _setup()
    e1, e2, far = _unit("E1", 3), _unit("E2", 2), _unit("Far", 9)
    loop.gs.battlefields[0].add_unit("B", e1)
    loop.gs.battlefields[0].add_unit("B", e2)
    loop.gs.battlefields[1].add_unit("B", far)
    _cast_now(loop, a, "Scorched Earth")
    assert not loop.gs.battlefields[0].units_B and far.damage == 0


def test_rally_for_war_plays_three_recruits_at_an_occupied_enemy_battlefield():
    """'Choose an occupied enemy battlefield. Play three 1 [might] Recruit unit
    tokens there.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[1].add_unit("B", _unit("Enemy", 2))
    _cast_now(loop, a, "Rally for War")
    recruits = loop.gs.battlefields[1].units_A
    assert [u.card.name for u in recruits] == ["Recruit"] * 3 and all(u.might == 1 for u in recruits)


def test_war_scout_gives_a_unit_two():
    """'When you play me, give a unit +2 [might] this turn.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    _pick(loop, "Unit")
    loop._play_unit(_card("War Scout"), "A")
    assert unit.might == 4


def test_antagonistic_apparatus_enters_ready_with_a_ready_mech_here():
    """'I enter ready. When you play me, play a ready 3 [might] Mech unit token
    here.'"""
    loop, a, b = _setup()
    me = loop._play_unit(_card("Antagonistic Apparatus"), "A", bf=loop.gs.battlefields[0])
    mech = next(u for u in loop.gs.battlefields[0].units_A if u.card.name == "Mech")
    assert me.ready and mech.ready and mech.might == 3


def test_forbidden_technique_comes_back_from_the_trash_after_a_seven_cost_card():
    """'Ready a unit. When you play a card with Energy cost [7] or more, you may
    play this from your trash for [1][fury][fury]. Then banish this.'"""
    loop, a, b = _setup()
    unit = _tired("Unit", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    tech = _card("Forbidden Technique")
    a.trash.append(tech)
    loop.chooser = _always(True)
    loop._play_unit(UnitCard(name="Small", might=1, cost_energy=6), "A")
    assert tech in a.trash and not unit.ready
    energy, fury = a.energy, a.power_pool[Domain.FURY]
    loop._play_unit(UnitCard(name="Big", might=7, cost_energy=7), "A")
    assert unit.ready and tech in a.banished and tech not in a.trash
    assert a.energy == energy - 1 and a.power_pool[Domain.FURY] == fury - 2


def test_incorrigible_construct_enters_ready_showing_off_a_mech():
    """'SHOW OFF a Mech. I enter ready if you showed off.'"""
    loop, a, b = _setup()
    assert not loop._play_unit(_card("Incorrigible Construct"), "A").ready
    loop, a, b = _setup()
    mech = _unit("Mech")
    a.base_units.append(mech)
    loop.chooser = _always(True)
    assert loop._play_unit(_card("Incorrigible Construct"), "A").ready


def test_runeblade_anvil_banishes_the_top_card_to_play_and_kills_itself():
    """'When you play this or when this leaves the board, banish the top card of
    your Main Deck. Until your next Ending Phase, you may play that card.
    [2] [fury], [tap]: Kill this.'"""
    loop, a, b = _setup()
    _deck(a, UnitCard(name="Top", might=1), UnitCard(name="Second", might=1), UnitCard(name="Third", might=1))
    anvil = _card("Runeblade Anvil")
    loop._play_gear(anvil, "A")
    assert [c.name for c in a.banished] == ["Top"]
    assert loop._banished_playable(a.banished[0], "A")
    loop._apply_activated_ability(a, b, _ability(loop, "A", "kill_gear"))
    assert anvil not in a.base_gear and anvil in a.trash
    assert [c.name for c in a.banished] == ["Top", "Second"]


def test_lost_to_the_sands_deals_four_or_kills_a_gear():
    """'Choose one - Deal 4 to a unit at a battlefield. - Kill a gear.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Lost to the Sands")
    assert enemy.damage == 4
    loop, a, b = _setup()
    gear = GearCard(name="Their Gear", cost_energy=3)
    b.base_gear.append(gear)
    _cast_now(loop, a, "Lost to the Sands")
    assert gear not in b.base_gear


def test_shimmering_swimmer_kills_a_friendly_gear_to_deal_two():
    """'You may kill a friendly unit or gear as an additional cost to play me.
    When you play me, if you paid the additional cost, deal 2 to a unit.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    gold = GearCard(name="Gold")
    a.base_gear.append(gold)
    loop.chooser = _always(True)
    loop._play_unit(_card("Shimmering Swimmer"), "A")
    assert enemy.damage == 2 and gold not in a.base_gear


def test_akali_brash_adds_on_the_first_move_and_banishes_on_the_second():
    """'The first time I move each turn, ADD [1] [rune]. The second time I move
    each turn, banish the top card of your Main Deck. Until your next Ending
    Phase, you may play that card.'"""
    loop, a, b = _setup()
    akali = _unit("Akali Brash")
    a.base_units.append(akali)
    _deck(a, UnitCard(name="Top", might=1), UnitCard(name="Second", might=1))
    energy, power = a.energy, sum(a.power_pool.values())
    loop._move_unit_by_effect(akali, loop.gs.battlefields[0])
    assert a.energy == energy + 1 and sum(a.power_pool.values()) == power + 1 and not a.banished
    loop._move_unit_by_effect(akali, loop.gs.battlefields[1])
    assert [c.name for c in a.banished] == ["Top"] and a.energy == energy + 1


def test_coalesced_energy_recycles_all_runes_and_channels_four():
    """'At the end of your turn, recycle all your runes, then channel 4 runes
    exhausted.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Coalesced Energy"))
    _runes(a, 2)
    a.rune_deck = RuneDeck([Rune(Domain.CALM) for _ in range(5)])
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert a.total_runes_in_play() == 4


def test_detonation_amplifier_draws_for_a_kill_and_doubles_deathknell_here():
    """'When you play this, you may kill another friendly unit or gear to draw 1.
    Friendly DEATHKNELL effects here trigger an additional time.'"""
    loop, a, b = _setup()
    _deck(a, *[UnitCard(name=f"D{i}", might=1) for i in range(4)])
    gold = GearCard(name="Gold")
    a.base_gear.append(gold)
    loop.chooser = _always(True)
    loop._play_gear(_card("Detonation Amplifier"), "A", 0)
    assert len(a.hand) == 1 and gold not in a.base_gear
    bf = loop.gs.battlefields[0]
    loop._deploy_gear("A", bf, _card("Bomb"), is_token=True)
    enemy = _unit("Enemy", 9)
    bf.add_unit("B", enemy)
    loop._kill_deployed_gear(bf, "A", [dg for dg in bf.gear_A if dg.card.name == "Bomb"])
    assert enemy.damage == 4                    # its DEATHKNELL twice


def test_drakehound_packmaster_plays_the_opponents_top_card_for_free():
    """'When you play me, reveal the top card of each opponent's Main Deck.
    Choose one and banish it, then play it, ignoring its cost.'"""
    loop, a, b = _setup()
    _deck(b, UnitCard(name="Their Top", might=4, cost_energy=5), UnitCard(name="Next", might=1))
    energy = a.energy
    loop._play_unit(_card("Drakehound Packmaster"), "A")
    assert any(u.card.name == "Their Top" for u in a.base_units) and a.energy == energy
    assert [c.name for c in b.deck.cards] == ["Next"]


def test_firebrand_raider_readies_enemies_and_stops_the_awaken_ready():
    """'I enter ready. When you play me, ready all enemy units. Other units enter
    ready. Units don't ready during the Awaken Phase.'"""
    loop, a, b = _setup()
    e1, e2 = _tired("E1", 2), _tired("E2", 2)
    loop.gs.battlefields[1].add_unit("B", e1)
    b.base_units.append(e2)
    raider = loop._play_unit(_card("Firebrand Raider"), "A")
    assert raider.ready and e1.ready and e2.ready
    assert loop._play_unit(UnitCard(name="Other", might=1), "B").ready
    tired = _tired("Tired", 2)
    a.base_units.append(tired)
    _start_turn(loop, "A")
    assert not tired.ready


def test_mordekaiser_twice_slain_kills_a_friend_to_come_back_once():
    """'Once each turn, if I would die, you may kill a friendly unit to heal me,
    exhaust me, and recall me instead.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    morde, friend = _unit("Mordekaiser Twice Slain"), _unit("Friend", 1)
    bf.add_unit("A", morde)
    bf.add_unit("A", friend)
    morde.damage = 9
    loop.chooser = _always(True)
    loop._route_deaths([(morde, "A")], bf)
    assert morde in a.base_units and morde.damage == 0 and not morde.ready
    assert friend not in bf.units_A


def test_ekko_revolutionary_replays_himself_to_base():
    """'I enter ready. ASSAULT. ACTION Discard 1, [1] [fury]: Banish me, then play
    me to your base, ignoring my cost.'"""
    loop, a, b = _setup()
    ekko = loop._play_unit(_card("Ekko Revolutionary"), "A", bf=loop.gs.battlefields[0])
    assert ekko.ready
    loop.gs.battlefields[0].add_unit("B", _unit("Defender", 1))
    bf = _attack_at(loop)
    assert ekko.might == 5
    a.hand.append(SpellCard(name="Junk"))
    ekko.ready = False
    energy, fury = a.energy, a.power_pool[Domain.FURY]
    loop._apply_activated_ability(a, b, _ability(loop, "A", "replay_self_to_base"))
    back = next(u for u in a.base_units if u.card.name == "Ekko Revolutionary")
    assert back.ready and ekko not in bf.units_A and not a.hand and a.energy == energy - 1
    assert a.power_pool[Domain.FURY] == fury - 1


def test_whirling_twirligig_makes_gold_recruits_and_mechs():
    """'[tap]: Play a Gold gear token exhausted. Kill a friendly gear, [tap]: Play
    a 1 [might] Recruit unit token. Kill a friendly unit, [tap]: Play a 3 [might]
    Mech unit token.'"""
    loop, a, b = _setup()
    twirl = _card("Whirling Twirligig")
    a.base_gear.append(twirl)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "play_token"))
    gold = next(g for g in a.base_gear if g.name == "Gold")
    assert gold.tapped and twirl.tapped
    twirl.tapped = False
    abilities = [i for i, e in enumerate(loop.activatable_abilities("A"))
                 if e.get("eff") is not None and e["eff"].effect == "play_token"
                 and e["eff"].params.get("token_name") == "Recruit"]
    loop._apply_activated_ability(a, b, abilities[0])
    assert any(u.card.name == "Recruit" for u in a.base_units) and gold not in a.base_gear
    twirl.tapped = False
    abilities = [i for i, e in enumerate(loop.activatable_abilities("A"))
                 if e.get("eff") is not None and e["eff"].effect == "play_token"
                 and e["eff"].params.get("token_name") == "Mech"]
    loop._apply_activated_ability(a, b, abilities[0])
    assert [u.card.name for u in a.base_units] == ["Mech"] and a.base_units[0].might == 3


def test_ziggs_short_fused_bombs_deal_one_bonus_damage():
    """'When you play me, play a Bomb gear token to a battlefield. Abilities of
    friendly gear deal 1 Bonus Damage.'"""
    loop, a, b = _setup()
    loop._play_unit(_card("Ziggs Short-Fused"), "A")
    (bf, bomb), = _bf_gear(loop, "A", "Bomb")
    enemy = _unit("Enemy", 9)
    bf.add_unit("B", enemy)
    loop._kill_deployed_gear(bf, "A", [bomb])
    assert enemy.damage == 3


def test_blossoming_dreamroot_draws_when_you_win_a_combat_here():
    """'When you win a combat here, draw 1.'"""
    loop, a, b = _setup()
    _deck(a, *[UnitCard(name=f"D{i}", might=1) for i in range(3)])
    loop._play_gear(_card("Blossoming Dreamroot"), "A", 0)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 4))
    bf.add_unit("B", _unit("Def", 1))
    _fight(loop)
    assert len(a.hand) == 1


def test_consult_the_heavens_gives_shield_two_and_predicts():
    """'Give a unit SHIELD 2 this turn. PREDICT.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    _deck(a, UnitCard(name="Top", might=1))
    _pick(loop, "Unit")
    _cast_now(loop, a, "Consult the Heavens")
    assert unit.keyword_value("SHIELD") == 2


def test_entrenched_boar_may_enter_ready_but_cant_move():
    """'You may have me enter ready. If you do, I can't move this turn.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    boar = loop._play_unit(_card("Entrenched Boar"), "A")
    assert boar.ready and boar.cant_move_turn == loop.gs.turn
    loop, a, b = _setup()
    loop.chooser = _always(False)
    boar = loop._play_unit(_card("Entrenched Boar"), "A")
    assert not boar.ready and boar.cant_move_turn != loop.gs.turn


def test_iridescent_avian_buffs_or_gives_two_to_a_buffed_unit():
    """'[tap]: BUFF a unit. If it's already buffed, give it +2 [might] this turn
    instead.'"""
    loop, a, b = _setup()
    avian, unit = _unit("Iridescent Avian"), _unit("Unit", 2)
    a.base_units.extend([avian, unit])
    _pick(loop, "Unit")
    loop._apply_activated_ability(a, b, _ability(loop, "A", "buff_unit"))
    assert unit.might_counters == 1 and unit.might == 3
    avian.ready = True
    loop._apply_activated_ability(a, b, _ability(loop, "A", "buff_unit"))
    assert unit.might_counters == 1 and unit.might == 5


def test_ki_burst_exhausts_a_friend_to_stun():
    """'As an additional cost to play this, exhaust a friendly unit. STUN a
    unit.'"""
    loop, a, b = _setup()
    friend, enemy = _unit("Friend", 2), _unit("Enemy", 4)
    a.base_units.append(friend)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.hand.append(_card("Ki Burst"))
    loop._apply_action(a, ("SPELL", 0, 0))
    loop._resolve_chain() if loop.gs.chain else None
    assert enemy.stunned and not friend.ready


def test_life_from_stone_exhausts_one_friend_to_draw_and_channel():
    """'As an additional cost to play this, exhaust a friendly unit. Draw 1 and
    channel 1 rune exhausted.'"""
    loop, a, b = _setup()
    f1, f2 = _unit("F1", 2), _unit("F2", 3)
    a.base_units.extend([f1, f2])
    _deck(a, UnitCard(name="Top", might=1))
    a.rune_deck = RuneDeck([Rune(Domain.CALM) for _ in range(3)])
    runes = a.total_runes_in_play()
    a.hand.append(_card("Life from Stone"))
    loop._apply_action(a, ("SPELL", 0, 0))
    assert [c.name for c in a.hand] == ["Top"] and a.total_runes_in_play() == runes + 1
    assert [f1.ready, f2.ready].count(False) == 1


def test_sanctum_conservator_readies_after_a_seven_cost_card():
    """'When you play a card with Energy cost [7] or more, ready me.'"""
    loop, a, b = _setup()
    me = _tired("Sanctum Conservator")
    a.base_units.append(me)
    loop._play_unit(UnitCard(name="Six", might=1, cost_energy=6), "A")
    assert not me.ready
    loop._play_unit(UnitCard(name="Seven", might=1, cost_energy=7), "A")
    assert me.ready


def test_stoic_ferryman_sends_another_unit_here_to_base():
    """'When you play me to a battlefield, you may move another unit you control
    here to your base.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    friend = _unit("Friend", 2)
    bf.add_unit("A", friend)
    loop.chooser = _always(True)
    loop._play_unit(_card("Stoic Ferryman"), "A", bf=bf)
    assert friend in a.base_units and [u.card.name for u in bf.units_A] == ["Stoic Ferryman"]


def test_battle_preparations_readies_two_runes_showing_off_a_gear():
    """'SHOW OFF a gear. Give a unit +2 [might] this turn. If you showed off,
    ready up to 2 runes.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    a.base_gear.append(GearCard(name="Shown"))
    a.rune_pool = {Domain.FURY: [Rune(Domain.FURY, ready=False) for _ in range(3)]}
    loop.chooser = _always(True)
    a.hand.append(_card("Battle Preparations"))
    energy = a.energy
    loop._apply_action(a, ("SPELL", 0, 0))
    assert unit.might == 4
    assert a.energy == energy - 2 + 2          # a readied rune is its Energy back


def test_command_attack_moves_a_deploy_gear_or_digs_a_gear():
    """'Choose one - Move a friendly gear with DEPLOY to a battlefield. - Look at
    the top 5 cards of your Main Deck. You may reveal a gear from among them and
    draw it. Recycle the rest.'"""
    loop, a, b = _setup()
    _deck(a, UnitCard(name="U1", might=1), GearCard(name="Found"), UnitCard(name="U2", might=1))
    _cast_now(loop, a, "Command: Attack")
    assert [c.name for c in a.hand] == ["Found"] and len(a.deck.cards) == 2
    loop, a, b = _setup()
    banner = _card("Banner of Conquest")
    loop._deploy_gear("A", loop.gs.battlefields[0], banner)
    loop.chooser = lambda _l, kind, side, options, default, source: 0 if kind == "mode" else None
    _cast_now(loop, a, "Command: Attack")
    assert [dg.card for dg in loop.gs.battlefields[1].gear_A] == [banner]


def test_hunker_down_readies_a_friend_that_cant_move_and_draws():
    """'Ready a friendly unit. It can't move this turn. Draw 1.'"""
    loop, a, b = _setup()
    friend = _tired("Friend", 3)
    a.base_units.append(friend)
    _deck(a, UnitCard(name="Top", might=1))
    _cast_now(loop, a, "Hunker Down")
    assert friend.ready and friend.cant_move_turn == loop.gs.turn and len(a.hand) == 1


def test_invigorating_bloom_gives_three_and_draws_off_a_mighty_unit():
    """'When you play this, give a friendly unit +3 [might] this turn. Exhaust a
    friendly MIGHTY unit, [tap]: Draw 1.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    _deck(a, *[UnitCard(name=f"D{i}", might=1) for i in range(2)])
    bloom = _card("Invigorating Bloom")
    loop._play_gear(bloom, "A")
    assert unit.might == 5
    loop._apply_activated_ability(a, b, _usable(loop, "A", "draw_cards"))
    assert len(a.hand) == 1 and not unit.ready and bloom.tapped


def test_storm_raptor_draws_when_a_stunned_enemy_dies_here():
    """'When a stunned enemy unit dies here, draw 1.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Storm Raptor"))
    _deck(a, *[UnitCard(name=f"D{i}", might=1) for i in range(3)])
    calm, stunned = _unit("Calm", 1), _unit("Stunned", 1)
    stunned.stunned = True
    bf.add_unit("B", calm)
    bf.add_unit("B", stunned)
    loop._route_deaths([(calm, "B")], bf)
    assert not a.hand
    loop._route_deaths([(stunned, "B")], bf)
    assert len(a.hand) == 1


def test_watchful_curator_makes_an_enemy_pay_to_choose_your_gear():
    """'Your gear have DEFLECT. (Opponents must pay [rune] to choose each with a
    spell or ability.)'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Watchful Curator"))
    gear = GearCard(name="Mine", cost_energy=3)
    a.base_gear.append(gear)
    power = sum(b.power_pool.values())
    _cast_now(loop, b, "Lost to the Sands")
    assert gear not in a.base_gear and sum(b.power_pool.values()) == power - 1
    loop, a, b = _setup()
    a.base_units.append(_unit("Watchful Curator"))
    gear = GearCard(name="Mine", cost_energy=3)
    a.base_gear.append(gear)
    b.power_pool = {}
    _cast_now(loop, b, "Lost to the Sands")
    assert gear in a.base_gear


def test_ahri_confident_grows_when_her_disarm_shrinks_an_enemy():
    """'DISARM. When you reduce the Might of an enemy unit here by 1 or more,
    give me +1 [might] this turn.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    ahri, enemy = _unit("Ahri Confident"), _unit("Enemy", 3)
    bf.add_unit("A", ahri)
    bf.add_unit("B", enemy)
    _attack_at(loop)
    assert enemy.might == 2 and ahri.might == 5


def test_ephemeral_ward_gives_two_until_you_play_a_unit():
    """'Your units have +2 [might]. When you play a unit, kill this.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    ward = _card("Ephemeral Ward")
    loop._play_gear(ward, "A")
    loop._recompute_passives()
    assert unit.might == 4
    loop._play_unit(UnitCard(name="New", might=1), "A")
    loop._recompute_passives()
    assert ward not in a.base_gear and unit.might == 2


def test_heartening_soul_readies_your_legend_and_lends_it_a_buff():
    """'When you play me, ready a friendly legend. Friendly legends have "[tap]:
    Give a unit +3 [might] this turn."'"""
    loop, a, b = _setup()
    legend = _tired("Legend", 0)
    loop.gs.legend_unit_A = legend
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    loop._play_unit(_card("Heartening Soul"), "A")
    assert legend.ready
    _pick(loop, "Unit")
    loop._apply_activated_ability(a, b, _usable(loop, "A", "grant_temporary_might"))
    assert unit.might == 5 and not legend.ready


def test_hush_counters_only_a_spell_costing_two_power():
    """'Counter a spell with Power cost [rune] [rune] or more.'"""
    from riftbound.core.state import ChainItem
    for power, countered in ((2, True), (1, False)):
        loop, a, b = _setup()
        loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="Theirs", cost_power=power), bf_idx=0))
        _cast_now(loop, a, "Hush")
        assert (not loop.gs.chain) == countered


def test_orianna_exquisite_deals_no_combat_damage_without_gear_here():
    """'I don't deal combat damage unless there's a friendly gear here.'"""
    for gear, survives in ((False, True), (True, False)):
        loop, a, b = _setup()
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Orianna Exquisite"))
        enemy = _unit("Enemy", 9)
        enemy.damage = 5
        bf.add_unit("B", enemy)
        if gear:
            loop._deploy_gear("A", bf, _card("Banner of Conquest"))
        _fight(loop)
        assert (enemy in bf.units_B) == survives


def test_riven_broken_blade_buffs_then_spends_it_to_stun_or_ready():
    """'When I become exhausted, choose one that hasn't been chosen this turn -
    BUFF me. - Spend my buff to STUN an enemy unit. - Spend my buff to ready me.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    riven, enemy = _unit("Riven Broken Blade"), _unit("Enemy", 3)
    bf.add_unit("A", riven)
    bf.add_unit("B", enemy)
    loop._exhaust(riven)
    assert riven.might_counters == 1
    riven.ready = True
    loop._exhaust(riven)
    assert riven.might_counters == 0 and (enemy.stunned or riven.ready)


def test_hunting_blind_pulls_an_enemy_here_and_gives_shield_two():
    """'When you play this, you may move an enemy unit to this battlefield.
    Friendly units here have SHIELD 2.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 2)
    b.base_units.append(enemy)
    mine = _unit("Mine", 2)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.chooser = _always(True)
    loop._play_gear(_card("Hunting Blind"), "A", 0)
    loop._recompute_passives()
    assert enemy in loop.gs.battlefields[0].units_B and mine.keyword_value("SHIELD") == 2


def test_ksante_dauntless_doubles_a_shield_when_he_defends():
    """'When I attack or defend, double the SHIELD of a unit you control here this
    turn.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    ksante = _unit("K'Sante Dauntless")
    bf.add_unit("B", _unit("Atk", 9))
    bf.add_unit("A", ksante)
    loop.gs.showdown_active, loop.gs.showdown_bf_idx, loop.gs.showdown_attacker = True, 0, "B"
    loop._open_combat(bf, "B")
    assert ksante.keyword_value("SHIELD") == 2


def test_resplendent_rostrum_draws_channels_and_gives_three():
    """'[tap]: Draw 1 and channel 1 rune exhausted. When this become exhausted,
    give a friendly unit +3 [Might] this turn.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    a.base_units.append(unit)
    rostrum = _card("Resplendent Rostrum")
    a.base_gear.append(rostrum)
    _deck(a, UnitCard(name="Top", might=1))
    a.rune_deck = RuneDeck([Rune(Domain.CALM) for _ in range(3)])
    runes = a.total_runes_in_play()
    loop._apply_activated_ability(a, b, _ability(loop, "A", "sequence"))
    assert len(a.hand) == 1 and a.total_runes_in_play() == runes + 1 and unit.might == 5
    assert rostrum.tapped


def test_fanfare_draws_for_the_next_three_units():
    """'The next three times you play a unit this turn, draw 1.'"""
    loop, a, b = _setup()
    _deck(a, *[UnitCard(name=f"D{i}", might=1) for i in range(6)])
    _cast_now(loop, a, "Fanfare")
    for i in range(4):
        loop._play_unit(UnitCard(name=f"P{i}", might=1), "A")
    assert len(a.hand) == 3


def test_high_note_shrinks_a_unit_by_your_exhausted_units():
    """'Give a unit -[might] this turn equal to the number of exhausted units you
    control.'"""
    loop, a, b = _setup()
    a.base_units.extend([_tired("T1", 1), _tired("T2", 1), _unit("Ready", 1)])
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _pick(loop, "Enemy")
    _cast_now(loop, a, "High Note")
    assert enemy.might == 3


def test_industrious_mechsmith_plays_a_mech_here():
    """'When you play me, play a 3 [might] Mech unit token here.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    loop._play_unit(_card("Industrious Mechsmith"), "A", bf=bf)
    mech = next(u for u in bf.units_A if u.card.name == "Mech")
    assert mech.might == 3 and mech.is_token


def test_mysterious_chronomancer_predicts_two_and_disarms_two():
    """'When you play me, PREDICT 2. DISARM 2.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    _deck(a, UnitCard(name="T1", might=1), UnitCard(name="T2", might=1), UnitCard(name="T3", might=1))
    loop._play_unit(_card("Mysterious Chronomancer"), "A", bf=bf)
    enemy = _unit("Enemy", 5)
    bf.add_unit("B", enemy)
    _attack_at(loop)
    assert enemy.might == 3


def test_parallel_convergence_returns_a_friend_to_deal_five():
    """'As an additional cost to play this, return a friendly unit to its owner's
    hand. Deal 5 to a unit at a battlefield.'"""
    loop, a, b = _setup()
    friend = _unit("Friend", 1)
    a.base_units.append(friend)
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.hand.append(_card("Parallel Convergence"))
    loop._apply_action(a, ("SPELL", 0, 0))
    assert enemy.damage == 5 and friend not in a.base_units and [c.name for c in a.hand] == ["Friend"]


def test_resource_extractor_makes_an_exhausted_gold_if_you_control_here():
    """'At the end of your turn, if you control this battlefield, play a Gold gear
    token exhausted.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    loop._deploy_gear("A", bf, _card("Resource Extractor"))
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert not any(g.name == "Gold" for g in a.base_gear)
    bf.add_unit("A", _unit("Holder", 2))
    bf._note_control()
    loop._fire_turn_trigger("on_end_of_turn", "A")
    gold = [g for g in a.base_gear if g.name == "Gold"]
    assert len(gold) == 1 and gold[0].tapped


def test_strigian_oracle_predicts_when_exhausted():
    """'When I become exhausted, PREDICT.'"""
    from test_corpus_cards import _Predictor
    loop, a, b = _setup()
    oracle = _unit("Strigian Oracle")
    a.base_units.append(oracle)
    _deck(a, UnitCard(name="Top", might=1))
    a.agent = _Predictor()
    loop._exhaust(oracle)
    assert a.agent.seen == ["Top"]


def test_clanging_sentry_gives_mechs_disarm():
    """'Your Mechs have DISARM.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    a.base_units.append(_unit("Clanging Sentry"))
    loop._play_unit(_card("Industrious Mechsmith"), "A", bf=bf)
    enemy = _unit("Enemy", 5)
    bf.add_unit("B", enemy)
    loop._recompute_passives()
    _attack_at(loop)
    assert enemy.might == 4          # the Mech's DISARM; the Mechsmith has none
