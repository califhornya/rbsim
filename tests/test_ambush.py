"""AMBUSH keyword: a champion may be played at REACTION speed directly onto a
battlefield lane (Rengar Trophy Hunter, the extended 'even without your own units
there' variant). Behavior lives on GameLoop._ambush_legal_lanes /
_deploy_ambush_champion and is enumerated in reaction/showdown legality."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop_with_rengar(power: int = 5) -> GameLoop:
    """A minimal game with A's champion = Rengar Trophy Hunter (AMBUSH), given
    enough Body power/energy to deploy (cost 5 energy + 1 Body power)."""
    from riftbound.core.enums import Domain
    from riftbound.core.player import Rune

    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]), energy=10)
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    a.power_pool[Domain.BODY] = power
    a.rune_pool[Domain.BODY] = [Rune(domain=Domain.BODY) for _ in range(power)]
    rengar = CARD_REGISTRY["Rengar Trophy Hunter"].instantiate()
    gs = GameState(rng=random.Random(1), A=a, B=b, active="A",
                   champion_A=rengar, champion_B=None)
    return GameLoop(gs)


def _enemy(loop, lane):
    loop.gs.battlefields[lane].units_B.append(UnitInPlay(UnitCard(name="Foe", might=2), ready=True))


def _friendly(loop, lane):
    loop.gs.battlefields[lane].units_A.append(UnitInPlay(UnitCard(name="Ally", might=2), ready=True))


def test_ambush_legal_lanes_friendly_or_enemy():
    loop = _loop_with_rengar()
    _friendly(loop, 0)
    _enemy(loop, 1)
    lanes = loop._ambush_legal_lanes("A")
    assert 0 in lanes                 # friendly-occupied lane
    assert 1 in lanes                 # enemy-occupied lane (Rengar's enemy_ok variant)
    # An empty lane (neither side) is not legal.
    empty = [i for i in range(len(loop.gs.battlefields)) if i not in (0, 1)]
    for i in empty:
        assert i not in lanes


def test_ambush_no_lanes_when_deployed_or_no_champion():
    loop = _loop_with_rengar()
    _friendly(loop, 0)
    loop.gs.champion_A_deployed = True
    assert loop._ambush_legal_lanes("A") == []
    # No champion at all → no lanes.
    loop.gs.champion_A = None
    assert loop._ambush_legal_lanes("A") == []


def test_deploy_ambush_champion_places_and_pays():
    loop = _loop_with_rengar()
    _enemy(loop, 1)
    ok = loop._deploy_ambush_champion("A", 1)
    assert ok is True
    assert any(u.card.name == "Rengar Trophy Hunter" for u in loop.gs.battlefields[1].units_A)
    assert loop.gs.champion_A_deployed is True
    assert loop.gs.A.energy == 5                       # 10 - 5 cost
    # Illegal lane (empty) → no deploy.
    loop2 = _loop_with_rengar()
    assert loop2._deploy_ambush_champion("A", 0) is False


def test_deploy_ambush_unaffordable():
    loop = _loop_with_rengar(power=0)   # no Body power → can't pay the [Body] pip
    _friendly(loop, 0)
    assert loop._deploy_ambush_champion("A", 0) is False
    assert loop.gs.champion_A_deployed is False


def test_reaction_legality_offers_ambush_deploy():
    loop = _loop_with_rengar()
    _friendly(loop, 0)
    acts = {a.to_engine() for a in legal_actions(loop, DecisionPoint.REACTION, "A")}
    assert ("CHAMPION", None, 0) in acts
    # Once deployed, it's no longer offered.
    loop.gs.champion_A_deployed = True
    acts2 = {a.to_engine() for a in legal_actions(loop, DecisionPoint.REACTION, "A")}
    assert not any(k == "CHAMPION" for (k, _i, _l) in acts2)


def test_showdown_legality_offers_ambush_at_showdown_lane():
    loop = _loop_with_rengar()
    _enemy(loop, 1)
    loop.gs.showdown_bf_idx = 1
    acts = {a.to_engine() for a in legal_actions(loop, DecisionPoint.SHOWDOWN_ACTION, "A")}
    assert ("CHAMPION", None, 1) in acts
    # A showdown at a lane with no legal AMBUSH target → not offered.
    loop.gs.showdown_bf_idx = 0
    acts0 = {a.to_engine() for a in legal_actions(loop, DecisionPoint.SHOWDOWN_ACTION, "A")}
    assert not any(k == "CHAMPION" for (k, _i, _l) in acts0)
