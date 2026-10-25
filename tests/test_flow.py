"""FLOW: "You may play this from your trash for its Flow cost. Then banish it."
A spell with FLOW in the trash is offered as an ability at its own timing,
costs its printed FLOW cost (less cost auras: Stargazer), and is banished
after it resolves or is countered. Kennen gives a spell FLOW for a turn;
Shadow Clone pays by banishing a unit from the trash."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import ChainItem, GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _flow_entries(loop, side="A"):
    return [(i, e) for i, e in enumerate(loop.activatable_abilities(side)) if e["type"] == "flow"]


def test_a_flow_spell_in_the_trash_is_played_for_its_flow_cost_then_banished():
    loop = _loop()
    ap = loop.gs.A
    dredge = _card("Dredge Up")                      # Draw 1. FLOW [2]
    ap.trash = [dredge, _card("Challenge")]          # Challenge has no FLOW
    ap.energy = 1
    (idx, entry), = _flow_entries(loop)
    assert entry["card"] is dredge and not loop._ability_usable(ap, entry)
    ap.energy = 3
    hand = len(ap.hand)
    loop._apply_action(ap, ("ABILITY", "ACTIVATED", idx, None))
    assert len(ap.hand) == hand + 1 and ap.energy == 1
    assert dredge in ap.banished and dredge not in ap.trash


def test_flow_power_cost_and_timing():
    loop = _loop()
    ap = loop.gs.A
    steel = _card("Brittle Steel")                   # FLOW [4] [fury], no ACTION
    ap.trash = [steel]
    ap.energy = 4
    (_, entry), = _flow_entries(loop)
    assert not loop._ability_usable(ap, entry)
    ap.add_power(Domain.FURY, 1)
    assert loop._ability_usable(ap, entry)
    loop.gs.showdown_active = True                   # not an ACTION spell
    assert _flow_entries(loop) == []


def test_stargazer_makes_flow_spells_cheaper_to_a_minimum_of_one():
    loop = _loop()
    ap = loop.gs.A
    dredge, onslaught = _card("Dredge Up"), _card("Onslaught")    # FLOW 2 / FLOW 4
    ap.trash = [dredge, onslaught]
    ap.base_units.append(UnitInPlay(card=_card("Stargazer")))
    assert loop._flow_cost(dredge, "A")[0] == 1
    assert loop._flow_cost(onslaught, "A")[0] == 2
    assert loop._effective_cost(onslaught, ap)[0] == 4          # from hand: no discount


def test_kennen_gives_a_spell_flow_this_turn():
    loop = _loop()
    ap = loop.gs.A
    kennen = UnitInPlay(card=_card("Kennen Storm of Shuriken"))
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", kennen)
    challenge = _card("Challenge")
    ap.trash = [challenge]
    assert loop._flow_cost(challenge, "A") is None
    loop._resolve_triggered_effects(kennen.card, "on_conquer", bf0, ap, loop.gs.B,
                                    context_extra={"battlefield": bf0})
    assert loop._flow_cost(challenge, "A") == (2, 1, Domain.BODY)     # its own cost
    loop.gs.turn += 1
    assert loop._flow_cost(challenge, "A") is None


def test_a_countered_flow_spell_is_banished():
    loop = _loop()
    ap, opp = loop.gs.A, loop.gs.B
    dredge = _card("Dredge Up")
    dredge._flow_banish = True
    loop.gs.chain.append(ChainItem(player="A", card=dredge, bf_idx=0))
    counter = _card("Hard Bargain")
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    REGISTRY["counter_spell"](EffectContext(loop, counter, opp, ap, loop.gs.battlefields[0], {}), {})
    assert dredge in ap.banished and dredge not in ap.trash


def test_shadow_clone_banishes_a_unit_from_the_trash_for_assault():
    loop = _loop()
    ap = loop.gs.A
    bf0 = loop.gs.battlefields[0]
    clone = UnitInPlay(card=_card("Shadow Clone"))
    bf0.add_unit("A", clone)
    loop._resolve_triggered_effects(clone.card, "on_attack", bf0, ap, loop.gs.B,
                                    context_extra={"battlefield": bf0})
    assert clone.keyword_value("ASSAULT") == 0       # nothing to banish
    fodder = UnitCard(name="Fodder")
    ap.trash = [_card("Dredge Up"), fodder]
    loop._resolve_triggered_effects(clone.card, "on_attack", bf0, ap, loop.gs.B,
                                    context_extra={"battlefield": bf0})
    assert clone.keyword_value("ASSAULT") == 4
    assert ap.banished == [fodder] and len(ap.trash) == 1
