"""Proving Grounds, card by card (BACKLOG.md section D): every card with text,
each sentence played through the engine."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _cast_now, _play_spell, _setup, _spell, _unit
from test_corpus_vendetta import _ctx, _runes, _usable


def _legend(loop, side, name):
    unit = UnitInPlay(card=CARD_REGISTRY[name].instantiate())
    setattr(loop.gs, f"legend_unit_{side}", unit)
    return unit


def test_annie_fiery_adds_one_to_each_spell_damage():
    """'Your spells and abilities deal 1 Bonus Damage.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Annie Fiery"))
    enemy = _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Incinerate")
    assert enemy.damage == 3


def test_annie_fiery_adds_nothing_to_a_fight():
    """Challenge's damage 'is dealt by the chosen units, not by Challenge'
    (Core Rules): no spell Bonus Damage."""
    loop, a, b = _setup()
    a.base_units.append(_unit("Annie Fiery"))
    friend, enemy = _unit("Friend", 5), _unit("Enemy", 9)
    loop.gs.battlefields[0].add_unit("A", friend)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Challenge")
    assert enemy.damage == 5


def test_firestorm_hits_only_the_enemies_at_the_chosen_battlefield():
    """'Deal 3 to all enemy units at a battlefield.'"""
    loop, a, b = _setup()
    here, there, mine = _unit("Here", 5), _unit("There", 5), _unit("Mine", 5)
    loop.gs.battlefields[1].add_unit("B", here)
    loop.gs.battlefields[1].add_unit("A", mine)
    loop.gs.battlefields[0].add_unit("B", there)
    _play_spell(loop, a, "Firestorm", lane=1)
    loop._resolve_chain()
    assert here.damage == 3 and there.damage == 0 and mine.damage == 0


def test_incinerate_and_blast_of_power_only_reach_battlefields():
    """'Deal 2 to a unit at a battlefield.' / 'Kill a unit at a battlefield.'"""
    loop, a, b = _setup()
    home, out = _unit("Home", 5), _unit("Out", 5)
    b.base_units.append(home)
    loop.gs.battlefields[0].add_unit("B", out)
    _cast_now(loop, a, "Incinerate")
    assert out.damage == 2 and home.damage == 0
    _cast_now(loop, a, "Blast of Power")
    assert not loop.gs.battlefields[0].units_B and home in b.base_units


def test_master_yi_meditative_has_plus_four_with_eight_runes():
    """'While you have 8+ runes, I have +4 [might].'"""
    loop, a, b = _setup()
    yi = _unit("Master Yi Meditative")
    a.base_units.append(yi)
    _runes(a, 7)
    loop._recompute_passives()
    assert yi.might == 4
    _runes(a, 8)
    loop._recompute_passives()
    assert yi.might == 8


def test_keyword_units_carry_their_printed_keywords():
    """Zephyr Sage SHIELD; Garen Rugged ASSAULT 2, SHIELD 2; Master Yi Honed
    GANKING."""
    assert _unit("Zephyr Sage").has_keyword("SHIELD")
    garen = _unit("Garen Rugged")
    assert garen.has_keyword("ASSAULT") and garen.has_keyword("SHIELD")
    assert _unit("Master Yi Honed").has_keyword("GANKING")


def test_lux_illuminated_grows_on_a_spell_that_costs_five_even_if_paid_less():
    """'When you play a spell that costs 5 or more, give me +3 [might] this
    turn.' The printed cost counts, not what was paid (Core Rules, Sky
    Splitter example)."""
    loop, a, b = _setup()
    lux = _unit("Lux Illuminated")
    a.base_units.append(lux)
    _play_spell(loop, a, _spell(4))
    assert lux.might == 5
    _play_spell(loop, a, _spell(5))
    assert lux.might == 8
    loop, a, b = _setup()
    lux = _unit("Lux Illuminated")
    a.base_units.append(lux)
    trigger = SpellCard(name="Cheap Five", cost_energy=5)
    loop._fire_spell_played(trigger, "A", 1)
    loop._recompute_passives()
    assert lux.might == 8


def test_lux_lady_of_luminosity_draws_on_a_five_cost_spell():
    """'When you play a spell that costs 5 or more, draw 1.'"""
    loop, a, b = _setup()
    _legend(loop, "A", "Lux Lady of Luminosity")
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    _play_spell(loop, a, _spell(4))
    assert len(a.hand) == 0
    _play_spell(loop, a, _spell(5))
    assert len(a.hand) == 1


def test_gentlemens_duel_buffs_a_friend_then_it_fights_an_enemy():
    """'Give a friendly unit +3 [might] this turn. Then, choose an enemy unit.
    They deal damage equal to their Mights to each other.'"""
    loop, a, b = _setup()
    friend, enemy = _unit("Friend", 3), _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("A", friend)
    b.base_units.append(enemy)          # "an enemy unit": in base too
    _cast_now(loop, a, "Gentlemen's Duel")
    assert enemy not in b.base_units
    assert friend.might == 6 and friend.damage == 5


def test_challenge_reaches_an_enemy_in_base_but_marching_orders_does_not():
    """Challenge: 'Choose a friendly unit and an enemy unit.' Marching Orders:
    '... an enemy unit at a battlefield.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Friend", 6))
    enemy = _unit("Enemy", 2)
    b.base_units.append(enemy)
    _cast_now(loop, a, "Challenge")
    assert enemy not in b.base_units
    loop, a, b = _setup()
    a.base_units.append(_unit("Friend", 6))
    enemy = _unit("Enemy", 2)
    b.base_units.append(enemy)
    _cast_now(loop, a, "Marching Orders")
    assert enemy in b.base_units and enemy.damage == 0


def test_units_that_enter_ready():
    """Master Yi Honed, Vanguard Attendant: 'I enter ready.'"""
    for name in ("Master Yi Honed", "Vanguard Attendant"):
        loop, a, b = _setup()
        a.hand.append(CARD_REGISTRY[name].instantiate())
        loop._apply_action(a, ("UNIT", 0, None))
        assert a.base_units and a.base_units[0].ready


def test_annie_stubborn_returns_a_spell_from_trash():
    """'When you play me, return a spell from your trash to your hand.'"""
    loop, a, b = _setup()
    spell, unit = CARD_REGISTRY["Incinerate"].instantiate(), UnitCard(name="Dead", might=1)
    a.trash = [unit, spell]
    a.hand.append(CARD_REGISTRY["Annie Stubborn"].instantiate())
    loop._apply_action(a, ("UNIT", 0, None))
    assert a.hand == [spell] and a.trash == [unit]


def test_flash_moves_up_to_two_friends_to_base():
    """'Move up to 2 friendly units to base.'"""
    loop, a, b = _setup()
    units = [_unit(f"U{i}", 2) for i in range(3)]
    for u in units:
        loop.gs.battlefields[0].add_unit("A", u)
    _cast_now(loop, a, "Flash")
    assert len(a.base_units) == 2 and len(loop.gs.battlefields[0].units_A) == 1


def test_garen_commander_gives_other_friends_here_plus_one():
    """'Other friendly units have +1 might here.'"""
    loop, a, b = _setup()
    garen, here, there = _unit("Garen Commander"), _unit("Here", 2), _unit("There", 2)
    loop.gs.battlefields[0].add_unit("A", garen)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    enemy = _unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    loop._recompute_passives()
    assert here.might == 3 and garen.might == 5 and there.might == 2 and enemy.might == 2


def test_lux_crownguard_taps_for_two_energy_for_spells():
    """'[tap]: REACTION - ADD [2] Use only to play spells.'"""
    loop, a, b = _setup()
    lux = _unit("Lux Crownguard")
    a.base_units.append(lux)
    loop._apply_activated_ability(a, b, _usable(loop, "A", "gain_energy"))
    assert a.earmarked_energy_spell == 2 and a.energy == 20 and not lux.ready


def test_recruit_the_vanguard_plays_four_one_might_recruits():
    """'Play four 1 might Recruit unit tokens.'"""
    loop, a, b = _setup()
    _cast_now(loop, a, "Recruit the Vanguard")
    recruits = [u for u in a.base_units + loop.gs.battlefields[0].units_A + loop.gs.battlefields[1].units_A
                if u.card.name == "Recruit"]
    assert len(recruits) == 4 and all(u.might == 1 for u in recruits)


def test_annie_dark_child_readies_two_runes_at_end_of_turn():
    """'At the end of your turn, ready up to 2 runes.'"""
    loop, a, b = _setup()
    _legend(loop, "A", "Annie Dark Child")
    _runes(a, 4)
    for r in a.rune_pool[Domain.FURY]:
        r.ready = False
    a.energy = 0
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert a.energy == 2


def test_tibbers_deals_three_to_every_unit_at_battlefields():
    """'When you play me, deal 3 damage to all units at battlefields.'"""
    loop, a, b = _setup()
    mine, theirs, home = _unit("Mine", 5), _unit("Theirs", 5), _unit("Home", 5)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.gs.battlefields[1].add_unit("B", theirs)
    b.base_units.append(home)
    a.hand.append(CARD_REGISTRY["Tibbers"].instantiate())
    loop._apply_action(a, ("UNIT", 0, None))
    loop._resolve_chain()
    assert mine.damage == 3 and theirs.damage == 3 and home.damage == 0
    assert a.base_units[0].damage == 0


def test_highlander_saves_a_friend_from_death_once():
    """'Choose a friendly unit. The next time it would die this turn, heal it,
    exhaust it, and recall it instead.'"""
    loop, a, b = _setup()
    unit = _unit("Unit", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    _cast_now(loop, a, "Highlander")
    _ctx(loop, b).damage_units([unit], 5)
    assert unit in a.base_units and unit.damage == 0 and not unit.ready
    _ctx(loop, b).damage_units([unit], 5)
    assert unit not in a.base_units


def test_final_spark_deals_eight_to_any_unit():
    """'Deal 8 to a unit.'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 9)
    b.base_units.append(enemy)
    _cast_now(loop, a, "Final Spark")
    assert enemy.damage == 8


def test_garen_might_of_demacia_draws_two_on_a_conquer_with_four_units():
    """'When you conquer, if you have 4+ units at that battlefield, draw 2.'"""
    loop, a, b = _setup()
    _legend(loop, "A", "Garen Might of Demacia")
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    bf = loop.gs.battlefields[0]
    for i in range(3):
        bf.add_unit("A", _unit(f"U{i}", 1))
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert len(a.hand) == 0
    bf.add_unit("A", _unit("U3", 1))
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert len(a.hand) == 2


def test_decisive_strike_buffs_every_friendly_unit():
    """'Give friendly units +2 [might] this turn.'"""
    loop, a, b = _setup()
    here, there, home = _unit("Here", 1), _unit("There", 1), _unit("Home", 1)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    a.base_units.append(home)
    enemy = _unit("Enemy", 1)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast_now(loop, a, "Decisive Strike")
    assert here.might == there.might == home.might == 3 and enemy.might == 1
