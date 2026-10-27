"""Rulings from the official Radiance Rules FAQ (playriftbound.com, 2026-10-26)
where the engine differed (DEFERRED.md "Radiance Rules FAQ")."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    loop = GameLoop(gs)
    riven = UnitInPlay(card=CARD_REGISTRY["Riven Broken Blade"].instantiate(), ready=True)
    enemy = UnitInPlay(card=CARD_REGISTRY["Punching Poro"].instantiate(), ready=True)
    gs.battlefields[0].add_unit("A", riven)
    gs.battlefields[0].add_unit("B", enemy)
    loop._recompute_passives()
    return loop, riven, enemy


class _Picks:
    """An agent whose "choose one" answers come from a list."""
    def __init__(self, *picks):
        self.picks = list(picks)

    def decide_mode(self, card, n):
        return self.picks.pop(0)


def _exhaust_again(loop, riven):
    riven.ready = True
    loop._exhaust(riven)


def test_riven_spends_her_buff_and_each_mode_once_per_turn():
    loop, riven, enemy = _setup()
    loop.gs.A.agent = _Picks(1, 1, 2)
    loop._exhaust(riven)                     # asks STUN, but no buff to spend -> BUFF me
    assert riven.might_counters == 1 and not enemy.stunned
    _exhaust_again(loop, riven)              # STUN, spending the buff
    assert enemy.stunned and riven.might_counters == 0
    _exhaust_again(loop, riven)              # only "ready me" left, and no buff to spend
    assert not riven.ready
    assert loop.gs.A.agent.picks == [2]      # nothing was chosen


def test_runeblade_anvil_card_lasts_to_the_next_ending_phase():
    loop, _, _ = _setup()
    gs, a = loop.gs, loop.gs.A
    a.deck.cards = [UnitCard(name=f"C{i}") for i in range(3)]
    anvil = EffectContext(loop, CARD_REGISTRY["Runeblade Anvil"].instantiate(), a, gs.B,
                          gs.battlefields[0])
    gs.turn = 5
    REGISTRY["banish_top_playable"](anvil, {})          # my turn: through this turn
    gs.in_ending_phase = True
    REGISTRY["banish_top_playable"](anvil, {})          # my Ending Phase: my next turn
    gs.in_ending_phase = False
    gs.active = "B"
    REGISTRY["banish_top_playable"](anvil, {})          # their turn: my next turn
    assert [c._banish_play_until for c in a.banished] == [5, 7, 6]


def test_riven_ready_mode_needs_a_buff():
    loop, riven, enemy = _setup()
    riven.might_counters = 1
    loop.gs.A.agent = _Picks(2, 0)
    loop._exhaust(riven)                     # spends the buff to ready her
    assert riven.ready and riven.might_counters == 0
    loop._exhaust(riven)                     # ready -> exhausted again: BUFF me
    assert not riven.ready and riven.might_counters == 1
    riven.ready = True
    loop.gs.turn += 1                        # a new turn: every mode is free again
    loop.gs.A.agent = _Picks(2)
    loop._exhaust(riven)
    assert riven.ready and riven.might_counters == 0
