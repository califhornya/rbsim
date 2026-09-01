"""Modal "choose one" (mode_choice): the actor picks one mode; its sub-effect(s)
resolve. Default (heuristic / no agent) is the first mode; an agent can pick another.
A mode may hold multiple effects (e.g. "each player draws 1").
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


class _PickMode:
    def __init__(self, i): self.i = i
    def decide_mode(self, card, n_modes) -> int: return self.i


_MODES = {"modes": [
    [{"effect": "draw_cards", "target": "actor", "count": 1}],
    [{"effect": "gain_energy", "target": "actor", "amount": 5}],
]}


def test_default_picks_first_mode():
    loop = _loop()
    loop.gs.A.deck.cards = [UnitCard(name="C", might=1)]
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["mode_choice"](ctx, _MODES)
    assert len(loop.gs.A.hand) == 1          # mode 0 = draw
    assert loop.gs.A.energy == 0


def test_agent_picks_second_mode():
    loop = _loop(); loop.gs.A.agent = _PickMode(1)
    ctx = EffectContext(loop, None, loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["mode_choice"](ctx, _MODES)
    assert loop.gs.A.energy == 5             # mode 1 = gain energy
    assert loop.gs.A.hand == []


def test_multi_effect_mode_runs_all():
    # Minah Swiftfoot: mode 0 = each player discards 1.
    loop = _loop(); loop.gs.active = "A"
    loop.gs.A.hand.append(UnitCard(name="Ah", might=1))
    loop.gs.B.hand.append(UnitCard(name="Bh", might=1))
    minah = UnitInPlay(card=CARD_REGISTRY["Minah Swiftfoot"].instantiate(), ready=True)
    bf = loop.gs.battlefields[0]
    loop._resolve_triggered_effects(minah.card, "on_move", bf, loop.gs.A, loop.gs.B,
                                    context_extra={"battlefield": bf})
    assert loop.gs.A.hand == [] and loop.gs.B.hand == []      # both discarded
    assert len(loop.gs.A.trash) == 1 and len(loop.gs.B.trash) == 1
