"""Rules audit, priority 2 (docs/audit/AUDIT.md): the PARTIAL / GAP rows of
docs/MECHANICS.md checked against docs/rules/CORE_RULES.md."""

from __future__ import annotations

import pytest

from riftbound.core.cards import UnitCard
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.player import Rune

from audit_helpers import act, card, choices, legend, scripted, setup, unit


def _decks(*players):
    for p in players:
        p.deck.cards = [UnitCard(name=f"Deck{i}", might=1) for i in range(5)]


# -- D12. TANK and BACKLINE on one unit: the assigning player chooses -----------

def test_the_assigner_chooses_between_tank_and_backline_on_one_unit():
    """'If a Unit has one or more Abilities ... that demand it be assigned damage
    in a specific way that is exclusionary, then the assigning player chooses
    only one of those abilities to apply' (the Caitlyn example: first, or last)."""
    loop, a, b = setup(active="A")
    bf0 = loop.gs.battlefields[0]
    both, small = unit("Both", 5), unit("Small", 1)
    both.granted_keywords += ["TANK", "BACKLINE"]
    bf0.add_unit("B", both)
    bf0.add_unit("B", small)
    bf0.add_unit("A", unit("Attacker", 1))
    # The attacker applies BACKLINE: its 1 damage goes to Small first.
    seen = choices(loop, {"combat_tank_or_backline": lambda l, o: o.index("BACKLINE")})
    loop._phase_combat_and_conquer_single(0, "A")
    assert [u.card.name for u in bf0.units_B] == ["Both"]
    assert [(kind, side) for kind, side, _ in seen if kind == "combat_tank_or_backline"] == \
        [("combat_tank_or_backline", "A")]             # the assigner chose, once


def test_tank_applies_to_a_unit_with_both_when_the_assigner_says_so():
    loop, a, b = setup(active="A")
    bf0 = loop.gs.battlefields[0]
    both, small = unit("Both", 5), unit("Small", 1)
    both.granted_keywords += ["TANK", "BACKLINE"]
    bf0.add_unit("B", both)
    bf0.add_unit("B", small)
    bf0.add_unit("A", unit("Attacker", 1))
    choices(loop, {"combat_tank_or_backline": lambda l, o: o.index("TANK")})
    loop._phase_combat_and_conquer_single(0, "A")
    assert sorted(u.card.name for u in bf0.units_B) == ["Both", "Small"]


# -- D19. Start of Turn: Awaken, Beginning (start effects, then Hold), Channel ---

def test_frozen_fortress_deals_its_damage_before_the_hold():
    """Frozen Fortress: 'At the start of each player's Beginning Phase, deal 1 to
    each unit here. (This happens before scoring.)' §315.2.a: the Beginning Step,
    then §315.2.b the Scoring Step."""
    loop, a, b = setup(active="A")
    _decks(a, b)
    bf0 = loop.gs.battlefields[0]
    bf0.card = card("Frozen Fortress")
    bf0.add_unit("A", unit("Frail", 1))
    loop._begin_turn()
    assert bf0.units_A == []
    assert loop.gs.points_A == 0                 # nobody there at the Scoring Step


def test_a_start_of_beginning_ability_resolves_before_a_hold_that_wins():
    """Jinx Loose Cannon: 'At the start of your Beginning Phase, draw 1 if you
    have one or fewer cards in your hand.' The Hold that gives the last point
    comes after it."""
    loop, a, b = setup(active="A")
    _decks(a, b)
    legend(loop, "A", "Jinx Loose Cannon")
    loop.gs.points_A = loop.gs.victory_score - 1
    loop.gs.battlefields[0].add_unit("A", unit("Holder", 2))
    result = loop._begin_turn()
    assert result is not None and result.winner == "A"
    assert len(a.hand) == 1                      # Jinx drew, then the Hold won


def test_the_runes_of_the_turn_are_channeled_after_the_hold():
    """Grove of the God-Willow: 'When you hold here, draw 1.' Ki Barrier costs
    [2] and one Order Power. With one rune in play the player can't react to the
    Hold ability with it: the two runes of the turn come in the Channel Phase
    (§315.3), after the Scoring Step (§315.2.b)."""
    loop, a, b = setup(active="A", rich=())
    _decks(a, b)
    bf0 = loop.gs.battlefields[0]
    bf0.card = card("Grove of the God-Willow")
    bf0.add_unit("A", unit("Holder", 2))
    a.rune_pool[Domain.ORDER] = [Rune(Domain.ORDER)]
    a.rune_deck.runes = [Rune(Domain.ORDER), Rune(Domain.ORDER)]
    a.hand.append(card("Ki Barrier"))
    scripted(loop, a, b)
    loop.gs.turn = 3
    loop._begin_turn()
    assert loop.gs.points_A == 1
    assert a.agent.log, "the Hold ability gives no priority"
    assert not [lbl for lbl in a.agent.offered(DecisionPoint.REACTION.value) if "Ki Barrier" in lbl]
    assert a.total_runes_in_play() == 3 and a.energy == 3      # channeled since


def test_the_runes_in_play_pay_for_a_reaction_to_a_hold_ability():
    """The runes readied in the Awaken Phase (§315.1) are there for it."""
    loop, a, b = setup(active="A", rich=())
    _decks(a, b)
    bf0 = loop.gs.battlefields[0]
    bf0.card = card("Grove of the God-Willow")
    bf0.add_unit("A", unit("Holder", 2))
    a.rune_pool[Domain.ORDER] = [Rune(Domain.ORDER, ready=False) for _ in range(2)]
    a.rune_deck.runes = [Rune(Domain.ORDER), Rune(Domain.ORDER)]
    a.hand.append(card("Ki Barrier"))
    scripted(loop, a, b)
    loop.gs.turn = 3
    loop._begin_turn()
    assert [lbl for lbl in a.agent.offered(DecisionPoint.REACTION.value) if "Ki Barrier" in lbl]
    assert a.total_runes_in_play() == 4 and a.energy == 4


# -- D20. Conquer: gaining Control of a battlefield not yet scored this turn -----

def test_a_player_conquers_a_battlefield_lost_and_taken_back_in_one_turn():
    """Charm: 'Move an enemy unit.' §471.1: 'Conquer: A player gains Control of a
    Battlefield they did not yet Score this turn.' A's unit, alone at a
    battlefield as B's turn starts, is moved to its base and back: A lost
    Control, then gained it, and hasn't scored there this turn."""
    loop, a, b = setup(active="B")
    _decks(a, b)
    bf0 = loop.gs.battlefields[0]
    wanderer = unit("Wanderer", 3)
    bf0.add_unit("A", wanderer)
    scripted(loop, a, b)
    loop._begin_turn()
    assert bf0.control() == "A" and loop.gs.points_A == 0
    b.energy = 20
    b.add_power(Domain.CALM, 5)
    b.hand += [card("Charm"), card("Charm")]
    choices(loop, {})
    act(loop, "B", "Cast Charm @BF0")            # out of the only battlefield it can leave: to base
    assert wanderer in a.base_units and bf0.control() is None
    act(loop, "B", "Cast Charm @BF0")
    assert bf0.units_A == [wanderer] and bf0.control() == "A"
    assert loop.gs.points_A == 1


def test_a_defender_who_keeps_the_battlefield_does_not_conquer_it():
    """Maintaining Control is no Conquer (§471.1: 'gains Control')."""
    loop, a, b = setup(active="B")
    _decks(a, b)
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", unit("Wall", 5))
    scripted(loop, a, b)
    loop._begin_turn()
    raider = unit("Raider", 1)
    b.base_units.append(raider)
    act(loop, "B", "Move Raider base→BF0")
    loop._flush_pending_move()                   # done moving: the showdown, the combat
    assert bf0.units_B == [] and raider.card in b.trash and bf0.control() == "A"
    assert loop.gs.points_A == 0 and loop.gs.points_B == 0


# -- Q3. The turn cap is a draw, whatever the score (the owner's decision) -------

def test_a_game_that_reaches_the_turn_cap_is_a_draw_even_with_a_lead():
    """Riftbound has no turn limit: the cap is a stall guard, and a two-point
    lead at the cap wins nothing (AUDIT Q3)."""
    loop, a, b = setup(active="A")
    loop.gs.turn, loop.gs.max_turns = 41, 40
    loop.gs.points_A, loop.gs.points_B = 6, 1
    assert loop._play_all_turns().winner == "DRAW"

