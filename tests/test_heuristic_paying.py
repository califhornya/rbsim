"""BACKLOG F, heuristic agents: they check a card's cost as the engine pays it
(GameLoop._effective_cost and _can_pay_card via legality._affordable: what it
costs now, a multi-domain card's Power from its own domains, Seraphine
Starry-Eyed Songstress's discount ...), and use an Add ability (a Seal, Gold)
only right before the play it pays for (§430.3; what it adds is lost as the
turn ends), never on its own (Agent._paying)."""

from __future__ import annotations

from riftbound.ai.heuristics.diana_agent import DianaAgent
from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _setup, _unit
from test_g3_rune_pool import _pool
from test_seraphine_songstress import _friends, _seraphine


def _agent(loop, p, cls=SimpleTradeAgent):
    agent = cls(p)
    p.agent = agent
    agent.loop, agent.gs, p.battlefields = loop, loop.gs, loop.gs.battlefields
    return agent


def _gear(p, name):
    gear = CARD_REGISTRY[name].instantiate()
    p.base_gear.append(gear)
    return gear


def _brute():
    return UnitCard(name="Brute", might=3, cost_energy=2, cost_power=1, cost_power_domain=Domain.FURY)


def _ability_source(loop, p, action):
    assert action[:2] == ("ABILITY", "ACTIVATED")
    entry = loop.activatable_abilities(p.name)[action[2]]
    return entry.get("gear") or entry["unit"].card


def test_an_add_with_nothing_to_pay_is_not_used():
    loop, a, b = _setup()
    _pool(a, 2, Domain.CALM)
    _gear(a, "Seal of Rage")
    assert _agent(loop, a).decide_action(b)[0] == "PASS"


def test_an_add_is_used_right_before_the_card_it_pays_for():
    loop, a, b = _setup()
    _pool(a, 2, Domain.CALM)                        # [2], no [fury]
    seal = _gear(a, "Seal of Rage")
    brute = _brute()
    a.hand.append(brute)
    agent = _agent(loop, a)
    first = agent.decide_action(b)
    assert _ability_source(loop, a, first) is seal
    loop._apply_action(a, first)
    assert seal.tapped and a.hand == [brute]
    second = agent.decide_action(b)
    assert second[:2] == ("UNIT", 0)
    loop._apply_action(a, second)
    assert any(u.card is brute for u in a.base_units) and a.energy == 0


def test_an_add_that_doesnt_pay_for_it_is_not_used():
    loop, a, b = _setup()
    _pool(a, 2, Domain.CALM)
    _gear(a, "Seal of Focus")                       # [calm]: Brute needs [fury]
    a.hand.append(_brute())
    assert _agent(loop, a).decide_action(b)[0] == "PASS"


def test_an_add_that_only_exhausts_goes_before_gold():
    loop, a, b = _setup()
    _pool(a, 2, Domain.CALM)
    _gear(a, "Gold")                                # kills itself
    seal = _gear(a, "Seal of Rage")
    a.hand.append(_brute())
    assert _ability_source(loop, a, _agent(loop, a).decide_action(b)) is seal


def test_two_adds_for_one_card():
    loop, a, b = _setup()
    _pool(a, 2, Domain.CALM)
    s1, s2 = _gear(a, "Seal of Rage"), _gear(a, "Seal of Rage")
    big = UnitCard(name="Big", might=5, cost_energy=2, cost_power=2, cost_power_domain=Domain.FURY)
    a.hand.append(big)
    agent = _agent(loop, a)
    for _ in range(2):
        act = agent.decide_action(b)
        assert _ability_source(loop, a, act) in (s1, s2)
        loop._apply_action(a, act)
    loop._apply_action(a, agent.decide_action(b))
    assert any(u.card is big for u in a.base_units)


def test_a_multi_domain_cards_power_is_from_its_own_domains():
    loop, a, b = _setup()
    _pool(a, 8, Domain.CALM)                        # Tibbers: [8] and 2 [fury/chaos]
    a.hand.append(CARD_REGISTRY["Tibbers"].instantiate())
    agent = _agent(loop, a)
    assert agent.decide_action(b)[0] == "PASS"
    _pool(a, 8, Domain.CHAOS)
    assert agent.decide_action(b)[:2] == ("UNIT", 0)


def test_a_spell_only_songstress_makes_affordable_is_played():
    loop, a, b = _setup()
    _seraphine(loop)
    _friends(a, 3)                                  # Might 1, 2, 3 at base
    loop.gs.battlefields[0].units_A.append(_unit("Mine", might=1))
    loop.gs.battlefields[0].units_B.append(_unit("Theirs", might=10))
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    a.energy = 4                                    # Progress Day costs [6] [mind]
    a.hand.append(CARD_REGISTRY["Progress Day"].instantiate())
    assert _agent(loop, a).decide_action(b) == ("SPELL", 0, 0)


def test_the_diana_agent_checks_what_a_card_costs_now_too():
    loop, a, b = _setup()
    _pool(a, 8, Domain.CALM)
    a.hand.append(CARD_REGISTRY["Tibbers"].instantiate())
    agent = _agent(loop, a, DianaAgent)
    act = agent.decide_action(b)
    assert act[0] != "UNIT"
    _pool(a, 2, Domain.CALM)
    a.hand[:] = [_brute()]
    seal = _gear(a, "Seal of Rage")
    assert _ability_source(loop, a, agent.decide_action(b)) is seal
