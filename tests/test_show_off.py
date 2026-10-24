"""SHOW OFF [Object] (Core Rules §832): as the card is played, its player may
reveal a matching card from hand or pick another matching friendly object on the
board. "If you showed off" effects and the shown object's numbers are read from
a snapshot taken as the card was played."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop():
    deck = Deck(cards=[UnitCard(name=f"C{i}", might=1) for i in range(5)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _register(monkeypatch, name, category, tf, payoff):
    spec = CardSpec.from_dict({
        "name": name, "category": category, "keywords": ["SHOW OFF"],
        "effects": [{"effect": "show_off", "trigger": "on_play", "target_filter": tf},
                    {**payoff, "condition": {"type": "showed_off"}}]})
    monkeypatch.setitem(CARD_REGISTRY, name, spec)


def _draw_if_showed_off(monkeypatch, name="Test Show Off Mech"):
    _register(monkeypatch, name, "Unit", {"subtype": "Mech"},
              {"effect": "draw_cards", "trigger": "on_play", "count": 1})
    return UnitCard(name=name, cost_energy=0, keywords=["SHOW OFF"])


def test_show_off_from_hand_enables_payoff(monkeypatch):
    loop = _loop()
    a = loop.gs.A
    card = _draw_if_showed_off(monkeypatch)
    a.hand.extend([card, UnitCard(name="Hand Mech", tags=["Mech"])])
    a.energy = 1
    loop._apply_action(a, ("UNIT", 0, 0, None))
    assert len(a.hand) == 2                  # kept the revealed Mech, drew 1


def test_no_matching_object_no_payoff(monkeypatch):
    loop = _loop()
    a = loop.gs.A
    card = _draw_if_showed_off(monkeypatch)
    a.hand.extend([card, UnitCard(name="Not A Mech")])
    a.energy = 1
    loop._apply_action(a, ("UNIT", 0, 0, None))
    assert len(a.hand) == 1                  # nothing drawn


def test_card_cannot_show_itself_off(monkeypatch):
    # "pick ANOTHER friendly Mech": the played Mech itself doesn't qualify.
    loop = _loop()
    a = loop.gs.A
    name = "Test Self Mech"
    _register(monkeypatch, name, "Unit", {"subtype": "Mech"},
              {"effect": "draw_cards", "trigger": "on_play", "count": 1})
    a.hand.append(UnitCard(name=name, cost_energy=0, tags=["Mech"], keywords=["SHOW OFF"]))
    a.energy = 1
    loop._apply_action(a, ("UNIT", 0, 0, None))
    assert len(a.hand) == 0


def test_shown_might_from_board_unit(monkeypatch):
    # Primordial Roar: deal damage equal to the shown unit's Might.
    loop = _loop()
    a, b = loop.gs.A, loop.gs.B
    bf = loop.gs.battlefields[0]
    name = "Test Roar"
    _register(monkeypatch, name, "Spell", {"is_unit": True},
              {"effect": "deal_damage", "trigger": "on_cast", "target": "enemy_unit",
               "amount_source": "shown_might"})
    big = UnitInPlay(UnitCard(name="Big", might=5))
    big.temporary_might = 1                  # current Might (6) is what counts
    bf.add_unit("A", big)
    bf.add_unit("B", UnitInPlay(UnitCard(name="Victim", might=6)))
    spell = SpellCard(name=name, keywords=["SHOW OFF"])

    loop._show_off(spell, a)
    assert spell._shown["might"] == 6
    loop._resolve_card_effects(spell, bf, a, b)

    assert not bf.units_B                    # 6 damage killed the 6-Might victim
    assert spell._showed_off is False and spell._shown is None  # consumed


def test_shown_costs_and_gear_filter(monkeypatch):
    loop = _loop()
    a = loop.gs.A
    name = "Test Show Gear"
    _register(monkeypatch, name, "Spell", {"is_gear": True},
              {"effect": "draw_cards", "trigger": "on_cast", "count": 1})
    a.base_gear.append(GearCard(name="Shiny", cost_energy=3, cost_power=1))
    spell = SpellCard(name=name, keywords=["SHOW OFF"])
    loop._show_off(spell, a)
    assert spell._showed_off is True
    assert spell._shown == {"might": 0, "power_cost": 1, "energy_cost": 3}


def test_agent_may_decline(monkeypatch):
    class Decliner:
        def decide_optional(self, card, name):
            return name != "SHOW OFF"

    loop = _loop()
    a = loop.gs.A
    a.agent = Decliner()
    card = _draw_if_showed_off(monkeypatch, "Test Declined Mech")
    a.hand.extend([card, UnitCard(name="Hand Mech", tags=["Mech"])])
    a.energy = 1
    loop._apply_action(a, ("UNIT", 0, 0, None))
    assert len(a.hand) == 1
