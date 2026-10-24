"""DEPLOY (Core Rules §830) and the Bomb gear token (§187.12).

A DEPLOY gear is played only to a battlefield, stays there through cleanup, is
killed when an opponent holds there, and its "here" abilities act at that
battlefield. Bombs are DEPLOY gear tokens whose DEATHKNELL deals 2 to an enemy
unit there and kills the controller's other Bombs there.
"""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop(deck_cards=0):
    deck = Deck(cards=[UnitCard(name=f"C{i}", might=1) for i in range(deck_cards)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    loop = GameLoop(gs)
    gs.active = "A"
    return loop


def _register(monkeypatch, name, effects, keywords=("DEPLOY",), category="Gear"):
    spec = CardSpec.from_dict({"name": name, "category": category,
                               "keywords": list(keywords), "effects": effects})
    monkeypatch.setitem(CARD_REGISTRY, name, spec)
    return spec


def _play_gear(loop, card, lane):
    ap = loop.gs.A
    ap.hand.append(card)
    ap.energy = 5
    loop._apply_action(ap, ("GEAR", len(ap.hand) - 1, lane, None))


def test_deploy_gear_plays_to_chosen_battlefield(monkeypatch):
    _register(monkeypatch, "Test Banner", [])
    loop = _loop()
    _play_gear(loop, GearCard(name="Test Banner", keywords=["DEPLOY"]), lane=1)
    assert [dg.card.name for dg in loop.gs.battlefields[1].gear_A] == ["Test Banner"]
    assert not loop.gs.A.base_gear and not loop.gs.battlefields[0].gear_A


def test_gear_on_play_effect_fires(monkeypatch):
    # "When you play this, draw 1" — for deployed and ordinary gear alike.
    draw = [{"effect": "draw_cards", "trigger": "on_play", "count": 1}]
    _register(monkeypatch, "Test Deploy Draw", draw)
    _register(monkeypatch, "Test Plain Draw", draw, keywords=())
    loop = _loop(deck_cards=5)
    _play_gear(loop, GearCard(name="Test Deploy Draw", keywords=["DEPLOY"]), lane=0)
    _play_gear(loop, GearCard(name="Test Plain Draw"), lane=0)
    assert len(loop.gs.A.hand) == 2


def test_opponent_hold_kills_deployed_gear_and_fires_deathknell(monkeypatch):
    _register(monkeypatch, "Test Gravity", [
        {"effect": "draw_cards", "trigger": "on_death", "count": 1}])
    loop = _loop(deck_cards=5)
    bf = loop.gs.battlefields[0]
    card = GearCard(name="Test Gravity", keywords=["DEPLOY"])
    loop._deploy_gear("A", bf, card)
    bf.add_unit("B", UnitInPlay(UnitCard(name="Holder", might=2)))

    loop.gs.active = "B"
    loop._phase_beginning("B")

    assert not bf.gear_A
    assert card in loop.gs.A.trash          # non-token gear goes to the trash
    assert len(loop.gs.A.hand) == 1          # its DEATHKNELL drew for its owner


def test_own_hold_keeps_gear_and_fires_hold_here(monkeypatch):
    _register(monkeypatch, "Test Dockside", [
        {"effect": "draw_cards", "trigger": "on_hold", "count": 1}])
    loop = _loop(deck_cards=5)
    bf = loop.gs.battlefields[0]
    loop._deploy_gear("A", bf, GearCard(name="Test Dockside", keywords=["DEPLOY"]))
    bf.add_unit("A", UnitInPlay(UnitCard(name="Holder", might=2)))

    loop._phase_beginning("A")

    assert len(bf.gear_A) == 1               # survives its controller's hold
    assert len(loop.gs.A.hand) == 1          # "when you hold here, draw 1"


def test_friendly_units_here_passive(monkeypatch):
    _register(monkeypatch, "Test Banner Of Conquest", [
        {"effect": "give_keyword", "trigger": "passive",
         "target": "all_friendly_units_here", "keyword": "ASSAULT"}])
    loop = _loop()
    here, there = loop.gs.battlefields
    u_here = UnitInPlay(UnitCard(name="Here", might=2))
    u_there = UnitInPlay(UnitCard(name="There", might=2))
    enemy = UnitInPlay(UnitCard(name="Enemy", might=2))
    here.add_unit("A", u_here)
    there.add_unit("A", u_there)
    here.add_unit("B", enemy)

    loop._deploy_gear("A", here, GearCard(name="Test Banner Of Conquest", keywords=["DEPLOY"]))

    assert u_here.has_keyword("ASSAULT")
    assert not u_there.has_keyword("ASSAULT")
    assert not enemy.has_keyword("ASSAULT")


def test_bomb_token_goes_to_battlefield_with_most_enemies():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf1.add_unit("B", UnitInPlay(UnitCard(name="E1", might=3)))
    bf1.add_unit("B", UnitInPlay(UnitCard(name="E2", might=3)))
    ctx = EffectContext(loop, UnitCard(name="Amateur Demolitionist"), loop.gs.A, loop.gs.B, bf0)

    from riftbound.core.effects import REGISTRY
    REGISTRY["play_token"](ctx, {"token_name": "Bomb", "count": 3})

    assert len(bf1.gear_A) == 3 and not bf0.gear_A
    assert all(dg.is_token and dg.card.name == "Bomb" for dg in bf1.gear_A)
    assert not loop.gs.A.base_units          # not spawned as a unit at base


def test_bomb_chain_kills_other_bombs_and_hits_enemies():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    bombs = CARD_REGISTRY["Bomb"]
    loop._deploy_gear("A", bf, bombs, is_token=True)
    loop._deploy_gear("A", bf, bombs, is_token=True)
    bf.add_unit("B", UnitInPlay(UnitCard(name="E1", might=2)))
    bf.add_unit("B", UnitInPlay(UnitCard(name="E2", might=2)))
    bf.add_unit("B", UnitInPlay(UnitCard(name="E3", might=9)))

    # Kill one Bomb: its DEATHKNELL deals 2 and kills the other Bomb, whose own
    # DEATHKNELL deals 2 more.
    loop._kill_deployed_gear(bf, "A", [bf.gear_A[0]])

    assert not bf.gear_A
    assert len(bf.units_B) == 1              # two 2-Might enemies died
    assert not any(c.name == "Bomb" for c in loop.gs.A.trash)  # tokens vanish


def test_kill_gear_reaches_deployed_gear(monkeypatch):
    _register(monkeypatch, "Test Enemy Banner", [])
    loop = _loop()
    bf = loop.gs.battlefields[1]
    card = GearCard(name="Test Enemy Banner", keywords=["DEPLOY"])
    loop._deploy_gear("B", bf, card)
    ctx = EffectContext(loop, UnitCard(name="Breaker"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0])

    from riftbound.core.effects import REGISTRY
    REGISTRY["kill_gear"](ctx, {"target": "enemy_gear"})

    assert not bf.gear_B
    assert card in loop.gs.B.trash


def test_move_deployed_gear(monkeypatch):
    _register(monkeypatch, "Test Portal", [])
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    loop._deploy_gear("A", bf0, GearCard(name="Test Portal", keywords=["DEPLOY"]))
    bf1.add_unit("A", UnitInPlay(UnitCard(name="Ally", might=2)))
    ctx = EffectContext(loop, UnitCard(name="Commander"), loop.gs.A, loop.gs.B, bf0)

    from riftbound.core.effects import REGISTRY
    REGISTRY["move_deployed_gear"](ctx, {})

    assert not bf0.gear_A and len(bf1.gear_A) == 1


def test_deploy_keyword_ignores_reminder_text():
    maker = CardSpec.from_dict({
        "name": "Test Bomb Maker", "category": "Unit",
        "effect": "When you play me, play a Bomb gear token to a battlefield. "
                  "(It has DEPLOY. When it dies, deal 2 to an enemy there.)"})
    gear = CardSpec.from_dict({
        "name": "Test Deploy Gear", "category": "Gear",
        "effect": "DEPLOY (Play this only to a battlefield. When an opponent holds here, kill this.)"})
    assert "DEPLOY" not in maker.keywords
    assert "DEPLOY" in gear.keywords
