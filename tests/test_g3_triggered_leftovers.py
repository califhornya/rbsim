"""BACKLOG G3 "Triggered leftovers" and "Leftovers of E" (B33): delayed
triggers (§391.2: "at end of turn", "at the start of your next Main Phase",
"when it dies this turn") and reflexive triggers ("do this", §388) go on the
chain like any triggered ability (§389, §393); an "if" that is part of the
effect (Jinx Loose Cannon, §383.2.a.1) is checked as it resolves. A unit gear
(Orianna Lady of Clockwork) is a gear for every "a gear" effect (§143
example); Svellsongur's copies of "once each turn" abilities, passive keyword
grants (summed, §807.2) and "trigger an additional time" each count."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.effects import REGISTRY, _banish_gear
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _play_spell, _setup, _unit
from test_corpus_vendetta import _ctx, _equip
from test_g2_vendetta import _sanction
from test_g3_triggered_on_chain import _Script
from test_simple_triggers import _kill
from test_unit_gear import _card, _main_starts, _orianna


def _library(p, n=4):
    _deck(p, *[SpellCard(name=f"S{i}") for i in range(n)])


def _triggered(script, name):
    """Whether `script` saw `name`'s triggered ability on the chain."""
    return any((name, "A", "triggered") in chain for chain in script.saw)


# ---------------------------------------------------------------- delayed

def test_an_end_of_turn_delayed_ability_goes_on_the_chain():
    loop, a, b = _setup()
    _library(a)
    loop._delay_to_end("A", _card("Targon's Peak"), loop.gs.battlefields[0],
                       {"effect": "draw_cards", "count": 1})
    b.agent = _Script()
    loop.gs.in_ending_phase = True
    loop._ending_step("A")
    assert _triggered(b.agent, "Targon's Peak") and len(a.hand) == 1
    assert loop.gs.delayed_effects == [] and not loop.gs.chain


def test_no_delayed_ability_is_made_once_the_ending_step_began():
    """§359.3.e.16 (Targon's Peak conquered in the Ending Phase)."""
    loop, a, b = _setup()
    loop.gs.in_ending_phase = True
    loop._delay_to_end("A", _card("Targon's Peak"), None, {"effect": "draw_cards", "count": 1})
    assert loop.gs.delayed_effects == []


def test_sanctions_disempower_at_end_of_turn_is_a_chain_item():
    loop, a, b = _setup()
    enemy = _unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _sanction(loop, 0, "Enemy")
    assert enemy.empowered
    b.agent = _Script()
    loop.gs.in_ending_phase = True
    loop._ending_step("A")
    assert not enemy.empowered and _triggered(b.agent, "Sanction")


def test_hostile_takeover_recalls_the_unit_on_the_chain_at_end_of_turn():
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _play_spell(loop, a, "Hostile Takeover")
    assert enemy in loop.gs.battlefields[0].units_A
    b.agent = _Script()
    loop.gs.in_ending_phase = True
    loop._ending_step("A")
    assert enemy in b.base_units and enemy.borrowed is None
    assert _triggered(b.agent, "Hostile Takeover")


def test_deadly_flourish_when_it_dies_later_is_a_trigger_of_the_spell():
    loop, a, b = _setup()
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _play_spell(loop, a, "Deadly Flourish")
    assert enemy.damage == 3 and not any(g.name == "Gold" for g in a.base_gear)
    b.agent = _Script()
    _kill(loop, enemy)
    assert any(g.name == "Gold" for g in a.base_gear) and _triggered(b.agent, "Deadly Flourish")


def test_deadly_flourish_killing_at_once_still_triggers_after_the_spell():
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    b.agent = _Script()
    _play_spell(loop, a, "Deadly Flourish")
    assert any(g.name == "Gold" for g in a.base_gear) and _triggered(b.agent, "Deadly Flourish")


def test_iascyllas_delayed_move_and_a_start_of_main_trigger_go_together():
    """Orianna Lady of Clockwork's "At the start of your Main Phase" and
    Iascylla's delayed ability trigger at the same time: one batch (the turn
    player orders them, choice trigger_order)."""
    loop, a, b = _setup()
    _orianna(loop)
    a.base_gear.append(_card("Iron Ballista"))
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 2))
    loop.gs.delayed_main.append(("A", _card("Iascylla"), 1,
                                 {"effect": "move_unit", "target": "enemy_unit", "destination": "here",
                                  "optional": True}))
    asked = []

    def chooser(_loop, kind, side, options, default, source):
        if kind == "trigger_order":
            asked.append(sorted(p.card.name for p in options))
        return None
    loop.chooser = chooser
    loop._start_of_main("A")
    assert asked[0] == ["Iascylla", "Orianna Lady of Clockwork"]      # then the rest
    assert [u.card.name for u in loop.gs.battlefields[1].units_B] == ["Enemy"]


# -------------------------------------------------------------- reflexive

def test_disintegrates_do_this_draw_is_its_own_chain_item():
    loop, a, b = _setup()
    _library(a)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    b.agent = _Script()
    _play_spell(loop, a, "Disintegrate")
    assert len(a.hand) == 1 and _triggered(b.agent, "Disintegrate")


def test_disintegrate_that_does_not_kill_draws_nothing():
    loop, a, b = _setup()
    _library(a)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 5))
    b.agent = _Script()
    _play_spell(loop, a, "Disintegrate")
    assert a.hand == [] and not _triggered(b.agent, "Disintegrate")


def test_arise_readies_two_of_its_tokens_as_a_reflexive_trigger():
    loop, a, b = _setup()
    a.base_gear.extend(_card("Long Sword") for _ in range(3))
    b.agent = _Script()
    _play_spell(loop, a, "Arise!")
    soldiers = [u for u in a.base_units if u.card.name.startswith("Sand Sol")]
    assert len(soldiers) == 3 and sum(u.ready for u in soldiers) == 2
    assert _triggered(b.agent, "Arise!")


def test_dragons_rage_fight_is_a_reflexive_trigger_after_the_move():
    loop, a, b = _setup()
    mover, there = _unit("Mover", 4), _unit("There", 3)
    loop.gs.battlefields[0].add_unit("B", mover)
    loop.gs.battlefields[1].add_unit("B", there)
    b.agent = _Script()
    _play_spell(loop, a, "Dragon's Rage")
    assert _triggered(b.agent, "Dragon's Rage")


# ------------------------------------------------------- effect conditions

def _jinx_trigger(loop, a, b, hand_at_trigger, hand_at_resolution):
    jinx = _card("Jinx Loose Cannon")
    _library(a)
    a.hand = [SpellCard(name=f"H{i}") for i in range(hand_at_trigger)]
    loop._task_depth += 1
    loop._resolve_triggered_effects(jinx, "on_start_of_turn", loop.gs.battlefields[0], a, b)
    assert len(loop._pending_triggers) == 1           # it triggered either way
    a.hand = a.hand[:hand_at_resolution]
    loop._task_depth -= 1
    loop._flush_triggers()


def test_loose_cannons_if_is_checked_as_it_resolves():
    """'At the start of your Beginning Phase, draw 1 if you have one or fewer
    cards in your hand': part of the effect (§383.2.a.1 example)."""
    loop, a, b = _setup()
    _jinx_trigger(loop, a, b, hand_at_trigger=3, hand_at_resolution=1)
    assert len(a.hand) == 2


def test_loose_cannon_draws_nothing_with_two_cards_as_it_resolves():
    """One card as it triggers, two more by the time it resolves: no draw."""
    loop, a, b = _setup()
    jinx = _card("Jinx Loose Cannon")
    _library(a)
    a.hand = [SpellCard(name="H0")]
    loop._task_depth += 1
    loop._resolve_triggered_effects(jinx, "on_start_of_turn", loop.gs.battlefields[0], a, b)
    a.hand.extend([SpellCard(name="H1"), SpellCard(name="H2")])
    loop._task_depth -= 1
    loop._flush_triggers()
    assert len(a.hand) == 3


def test_leblancs_draw_two_instead_is_one_instruction():
    """'DEATHKNELL - Draw 1. If it's your Beginning Phase, draw 2 instead.'"""
    for beginning, drawn in ((False, 1), (True, 2)):
        loop, a, b = _setup()
        _library(a)
        leblanc = _unit("Leblanc Fragmented")
        loop.gs.battlefields[0].add_unit("A", leblanc)
        loop.gs.in_beginning_phase = beginning
        _kill(loop, leblanc)
        assert len(a.hand) == drawn


# ------------------------------------------------------------- unit gear

def _ballista_unit(loop, a):
    _orianna(loop)
    ballista = _card("Iron Ballista")
    a.base_gear.append(ballista)
    _main_starts(loop)
    unit = next(u for u in a.base_units if u.card is ballista)
    return ballista, unit


def test_factory_recall_returns_a_unit_gear_to_hand():
    loop, a, b = _setup()
    ballista, _unit_gear = _ballista_unit(loop, a)
    REGISTRY["return_gear_to_hand"](_ctx(loop, b), {"effect": "return_gear_to_hand"})
    assert ballista in a.hand and not a.base_units


def test_ready_a_gear_readies_an_exhausted_unit_gear():
    loop, a, b = _setup()
    _ballista, unit = _ballista_unit(loop, a)
    unit.ready = False
    REGISTRY["ready_gear"](_ctx(loop, a), {"effect": "ready_gear"})
    assert unit.ready


def test_turn_to_dust_gives_a_unit_gear_temporary():
    loop, a, b = _setup()
    _ballista, unit = _ballista_unit(loop, a)
    REGISTRY["give_gear_temporary"](_ctx(loop, b), {"effect": "give_gear_temporary"})
    assert unit.has_keyword("TEMPORARY")


def test_akshan_steals_a_unit_gear_and_it_goes_back():
    loop, a, b = _setup()
    ballista, unit = _ballista_unit(loop, a)
    akshan = _card("Akshan Mischievous")
    REGISTRY["steal_gear"](_ctx(loop, b, akshan), {"effect": "steal_gear"})
    assert unit in b.base_units and unit not in a.base_units
    loop._return_stolen_gear(akshan)
    assert unit in a.base_units and unit not in b.base_units


def test_tomb_raider_barbara_kills_a_unit_gear():
    loop, a, b = _setup()
    ballista, _unit_gear = _ballista_unit(loop, a)
    REGISTRY["disempower_or_kill_gear"](_ctx(loop, b), {"effect": "disempower_or_kill_gear"})
    assert ballista in a.trash and not a.base_units


def test_a_unit_gear_banished_as_a_gear_is_banished_as_a_unit():
    loop, a, b = _setup()
    ballista, _unit_gear = _ballista_unit(loop, a)
    _banish_gear(_ctx(loop, b), ballista)
    assert ballista in a.banished and not a.base_units


def test_divine_judgment_recycles_attached_gear_too():
    loop, a, b = _setup()
    holder = _unit("Holder", 3)
    a.base_units.append(holder)
    swords = [_equip(holder, "Long Sword") for _ in range(3)]
    REGISTRY["divine_judgment"](_ctx(loop, a), {"effect": "divine_judgment", "keep": 2})
    assert len(holder.gear) == 2 and sum(s in a.deck.cards for s in swords) == 1


# ------------------------------------------------------------ Svellsongur

def test_a_copied_once_each_turn_ability_has_its_own_use():
    loop, a, b = _setup()
    riven = _unit("Riven Deserter")
    a.base_units.append(riven)
    _equip(riven, "Svellsongur")
    entries = [e for e in loop.activatable_abilities("A") if e.get("unit") is riven]
    assert [e.get("copy") for e in entries] == [None, 1]
    loop.gs.once_per_turn_used[loop._once_key(riven.card, entries[0]["eff"], entries[0])] = loop.gs.turn
    a.base_units.append(_unit("Other", 1))
    assert not loop._ability_usable(a, entries[0]) and loop._ability_usable(a, entries[1])


def test_a_copied_keyword_grant_adds_up():
    """Captain Farron 'Other friendly units here have ASSAULT', copied: ASSAULT 2."""
    loop, a, b = _setup()
    farron, other = _unit("Captain Farron"), _unit("Other", 2)
    for u in (farron, other):
        loop.gs.battlefields[0].add_unit("A", u)
    loop._recompute_passives()
    assert other.keyword_value("ASSAULT") == 1 and farron.keyword_value("ASSAULT") == 0
    _equip(farron, "Svellsongur")
    loop._recompute_passives()
    assert other.keyword_value("ASSAULT") == 2


def test_a_printed_assault_and_a_granted_one_add_up():
    """§807.2: Laurent Duelist ASSAULT 2 beside Captain Farron: ASSAULT 3."""
    loop, a, b = _setup()
    duelist = _unit("Laurent Duelist")
    for u in (_unit("Captain Farron"), duelist):
        loop.gs.battlefields[0].add_unit("A", u)
    loop._recompute_passives()
    assert duelist.keyword_value("ASSAULT") == 3


def test_taric_gives_shield_to_the_others_only():
    loop, a, b = _setup()
    taric, other = _unit("Taric Protector"), _unit("Other", 2)
    for u in (taric, other):
        loop.gs.battlefields[0].add_unit("A", u)
    loop._recompute_passives()
    assert taric.keyword_value("SHIELD") == 1 and other.keyword_value("SHIELD") == 1


def test_karthus_copied_makes_deathknell_trigger_two_more_times():
    loop, a, b = _setup()
    karthus, sentry = _unit("Karthus Eternal"), _unit("Watchful Sentry")
    for u in (karthus, sentry):
        loop.gs.battlefields[0].add_unit("A", u)
    _equip(karthus, "Svellsongur")
    _library(a)
    _kill(loop, sentry)
    assert len(a.hand) == 3


def test_conditional_keywords_are_not_printed_ones():
    """Grumpy Rockbear 'EMPOWERED: I have DEFLECT and SHIELD 3', Brutal Hunter,
    Solari Sunhawk, Mosstomper: only while; Dramatic Visionary's PREDICT is its
    DEATHKNELL's, not a play's."""
    for name, kw in (("Grumpy Rockbear", "DEFLECT"), ("Grumpy Rockbear", "SHIELD"),
                     ("Brutal Hunter", "GANKING"), ("Solari Sunhawk", "DEFLECT"),
                     ("Mosstomper", "DEFLECT"), ("Dramatic Visionary", "PREDICT")):
        assert not _unit(name).has_keyword(kw), (name, kw)
    loop, a, b = _setup()
    rockbear = _unit("Grumpy Rockbear")
    a.base_units.append(rockbear)
    loop._empower(rockbear.card, "A")
    loop._recompute_passives()
    assert rockbear.keyword_value("SHIELD") == 3 and rockbear.keyword_value("DEFLECT") == 1
