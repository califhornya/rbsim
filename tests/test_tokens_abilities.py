"""Tokens, mana abilities, ability timing windows and movement triggers.

- Token units are real units: they take the Standard Move and fight, and cease
  to exist when they leave the board (Core Rules §185-186). Gold is a gear
  token whose "Kill this, [tap]: ADD [rune]" adds one Power once.
- "ADD" effects give floating Power that is spent without recycling a rune.
- REACTION abilities can be used in the main phase and in reaction windows;
  activated abilities check their condition.
- Every "when I move" fires once (no hardcoded duplicate), with where the unit
  came from and went; a Standard Move to base exhausts the unit.
- Kill effects and spell damage run the same death steps as combat.
"""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import ChainItem, GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _register(monkeypatch, name, effects, category="Unit"):
    spec = CardSpec.from_dict({"name": name, "category": category, "effects": effects})
    monkeypatch.setitem(CARD_REGISTRY, spec.name, spec)


def _abilities(loop, side="A", point=DecisionPoint.TURN_ACTION):
    return [ga for ga in legal_actions(loop, point, side) if ga.kind == "ABILITY"]


def test_recruit_token_moves_and_ceases_to_exist_when_it_dies():
    loop = _loop()
    a = loop.gs.A
    recruit = loop._play_token("Recruit", "A", ready=True)
    assert recruit.is_token and isinstance(recruit.card, UnitCard)
    loop._apply_action(a, ("MOVE", None, 2, 0))
    assert recruit in loop.gs.battlefields[0].units_A
    assert not recruit.ready                      # the move exhausted it
    ctx = EffectContext(loop, UnitCard(name="Zap"), loop.gs.B, a, loop.gs.battlefields[0])
    REGISTRY["kill_unit"](ctx, {"target": "enemy_unit"})
    assert not loop.gs.battlefields[0].units_A
    assert a.trash == []                          # tokens don't go to the trash
    assert loop.gs.friendly_unit_died_this_turn["A"]


def test_gold_is_a_gear_token_that_adds_one_power_once():
    loop = _loop()
    a = loop.gs.A
    gold = loop._play_token("Gold", "A", ready=True)
    assert gold in a.base_gear
    a.hand.append(SpellCard(name="Chaos Spell", cost_energy=0, cost_power=1,
                            cost_power_domain=Domain.CHAOS))
    gold_uses = [ga for ga in _abilities(loop) if "Gold" in ga.label]
    assert len(gold_uses) == 1
    loop._apply_action(a, gold_uses[0].to_engine())
    assert a.base_gear == [] and a.trash == []    # killed: gone
    assert a.total_runes_in_play() == 0           # no permanent rune
    assert a.power_pool.get(Domain.CHAOS) == 1    # the Power the hand needed
    loop._apply_action(a, ("SPELL", 0, 0, None))  # paid without any rune
    assert a.hand == [] and a.power_pool.get(Domain.CHAOS, 0) == 0


def test_seal_is_usable_in_a_reaction_window():
    loop = _loop()
    b = loop.gs.B
    b.base_gear.append(CARD_REGISTRY["Seal of Discord"].instantiate())
    loop.gs.chain.append(ChainItem(player="A", card=SpellCard(name="X"), bf_idx=0))
    uses = _abilities(loop, "B", DecisionPoint.REACTION)
    assert len(uses) == 1
    loop._use_ability_now(b, "ACTIVATED", uses[0].to_engine()[2])
    assert b.power_pool.get(Domain.CHAOS) == 1


def test_activated_ability_checks_its_condition():
    loop = _loop()
    legend = CARD_REGISTRY["Darius Hand of Noxus"].instantiate()
    loop.gs.legend_unit_A = UnitInPlay(card=legend, ready=True)
    assert _abilities(loop) == []                 # LEGION: no card played yet
    loop._count_card_played(SpellCard(name="Anything"), "A")
    assert len(_abilities(loop)) == 1


def test_treasure_hunter_makes_one_gold_and_stellacorn_draws_one():
    loop = _loop()
    a = loop.gs.A
    a.base_units.append(UnitInPlay(card=CARD_REGISTRY["Treasure Hunter"].instantiate(), ready=True))
    loop._apply_action(a, ("MOVE", None, 2, 0))
    assert [g.name for g in a.base_gear] == ["Gold"]
    assert [u.card.name for u in a.base_units] == []
    loop = _loop()
    a = loop.gs.A
    a.base_units.append(UnitInPlay(card=CARD_REGISTRY["Stellacorn Herder"].instantiate(), ready=True))
    loop._apply_action(a, ("MOVE", None, 2, 0))
    assert len(a.hand) == 1


def test_moving_to_base_exhausts_and_direction_conditions():
    loop = _loop()
    a = loop.gs.A
    root = UnitInPlay(card=CARD_REGISTRY["Mister Root"].instantiate(), ready=True)
    loop.gs.battlefields[0].add_unit("A", root)
    loop._apply_action(a, ("MOVE", None, 0, 2))
    assert root in a.base_units and not root.ready
    assert loop.gs.get_xp("A") == 0               # "to a battlefield" only
    root.ready = True
    loop._apply_action(a, ("MOVE", None, 2, 1))
    assert loop.gs.get_xp("A") == 2


def test_corina_recruits_arrive_before_the_fight():
    loop = _loop()
    a = loop.gs.A
    corina = UnitInPlay(card=CARD_REGISTRY["Corina Veraza"].instantiate(), ready=True)
    a.base_units.append(corina)
    loop._apply_action(a, ("MOVE", None, 2, 0))
    names = sorted(u.card.name for u in loop.gs.battlefields[0].units_A)
    assert names == ["Corina Veraza", "Recruit", "Recruit", "Recruit"]


def test_kill_effect_fires_deathknell(monkeypatch):
    _register(monkeypatch, "Last Words", [{"effect": "draw_cards", "trigger": "on_death", "count": 1}])
    loop = _loop()
    a = loop.gs.A
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=UnitCard(name="Last Words")))
    ctx = EffectContext(loop, UnitCard(name="Zap"), loop.gs.B, a, loop.gs.battlefields[0])
    REGISTRY["kill_unit"](ctx, {"target": "enemy_unit"})
    assert [c.name for c in a.trash] == ["Last Words"]
    assert len(a.hand) == 1


def test_pyke_legend_bounces_and_makes_gold_in_one_activation():
    loop = _loop()
    a = loop.gs.A
    loop.gs.legend_unit_A = UnitInPlay(card=CARD_REGISTRY["Pyke Bloodharbor Ripper"].instantiate(),
                                       ready=True)
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=UnitCard(name="Returner")))
    a.energy = 1
    uses = _abilities(loop)
    assert len(uses) == 1
    loop._apply_action(a, uses[0].to_engine())
    assert [c.name for c in a.hand] == ["Returner"]
    assert [g.name for g in a.base_gear] == ["Gold"]
    assert a.energy == 0 and not loop.gs.legend_unit_A.ready


def test_kaisa_power_only_pays_for_spells():
    loop = _loop()
    a = loop.gs.A
    a.earmarked_power_spell = 1
    spell = SpellCard(name="S", cost_energy=0, cost_power=1, cost_power_domain=Domain.FURY)
    unit = UnitCard(name="U", cost_energy=0, cost_power=1, domain=Domain.FURY)
    unit.cost_power_domain = Domain.FURY
    assert loop._can_pay_card(a, spell, 0, 1)
    assert not loop._can_pay_card(a, unit, 0, 1)
    assert loop._pay_card(a, spell, 0, 1) and a.earmarked_power_spell == 0


def test_equipment_triggers_fire_with_the_equipped_unit():
    loop = _loop()
    a = loop.gs.A
    bf = loop.gs.battlefields[0]
    archer = UnitInPlay(card=UnitCard(name="Archer", might=1))
    archer.gear.append(CARD_REGISTRY["Recurve Bow"].instantiate())
    archer.gear.append(CARD_REGISTRY["Sacred Shears"].instantiate())
    bf.add_unit("A", archer)
    target = UnitInPlay(card=UnitCard(name="Target", might=2))
    brute = UnitInPlay(card=UnitCard(name="Brute", might=5))
    bf.add_unit("B", target)
    bf.add_unit("B", brute)
    loop._phase_combat_and_conquer_single(0, "A")
    # "When I attack, deal 2 to an enemy unit here", then the fight kills Archer.
    assert target not in bf.units_B
    assert archer not in bf.units_A
    assert len(a.hand) == 1                       # Sacred Shears: DEATHKNELL draw 1
    assert sorted(g.name for g in a.base_gear) == ["Recurve Bow", "Sacred Shears"]


def test_trinity_force_scores_when_its_unit_holds():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    holder = UnitInPlay(card=UnitCard(name="Holder", might=2))
    holder.gear.append(CARD_REGISTRY["Trinity Force"].instantiate())
    bf.add_unit("A", holder)
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert loop.gs.points_A == 1


def test_equipment_might_bonus_and_gearhead_doubles_it():
    loop = _loop()
    holder = UnitInPlay(card=UnitCard(name="Holder", might=2))
    holder.gear.append(CARD_REGISTRY["Jagged Cutlass"].instantiate())     # [might] +2
    loop.gs.A.base_units.append(holder)
    assert holder.might == 4
    gearhead = UnitInPlay(card=CARD_REGISTRY["Gearhead"].instantiate())
    gearhead.gear.append(CARD_REGISTRY["Jagged Cutlass"].instantiate())
    loop.gs.A.base_units.append(gearhead)
    loop._recompute_passives()
    assert gearhead.might == int(gearhead.card.might) + 4
