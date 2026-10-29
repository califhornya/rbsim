"""BACKLOG G3 "Enter ready" (B34): "I enter ready" / "If C, I enter ready" is a
conditional passive replacing how the unit enters (§364.3.a, §369.3: Master Yi
Honed's example), not a "when you play me" trigger: no chain item to answer
or counter, and it never enters exhausted then readies (§805.6), so "when you
ready a unit" doesn't see it. Its condition is checked as it enters, after
its additional costs and SHOW OFF."""

from __future__ import annotations

import json
import re

from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _always, _setup, _unit
from test_g3_triggered_on_chain import _Script, _hand
from test_unit_gear import _card

_UNCONDITIONAL = ("Warwick Hunter", "Master Yi Honed", "Vanguard Attendant", "Eager Drakehound",
                  "Arena Kingpin", "Daisy!", "Antagonistic Apparatus", "Firebrand Raider",
                  "Ekko Revolutionary", "Wrath of the Freljord")


def test_i_enter_ready_is_not_a_trigger_on_the_chain():
    loop, a, b = _setup()
    _hand(a, "Master Yi Honed")
    b.agent = _Script()
    loop._apply_action(a, ("UNIT", 0, None))
    yi = a.base_units[-1]
    assert yi.card.name == "Master Yi Honed" and yi.ready
    assert not any(name == "Master Yi Honed" for chain in b.agent.saw for name, *_ in chain)


def test_every_unconditional_one_enters_ready():
    for name in _UNCONDITIONAL:
        loop, a, b = _setup()
        assert loop._play_unit(_card(name), "A").ready, name


def test_entering_ready_is_not_readying():
    """Pirate's Haven: 'When you ready a friendly unit, give it +1 [might] this
    turn.'"""
    loop, a, b = _setup()
    a.base_gear.append(_card("Pirate's Haven"))
    unit = loop._play_unit(_card("Vanguard Attendant"), "A")
    assert unit.ready and unit.might == int(unit.card.might)


def test_the_condition_is_checked_as_it_enters():
    """Vayne Hunter: 'If an opponent controls a battlefield, I enter ready.'"""
    loop, a, b = _setup()
    assert not loop._play_unit(_card("Vayne Hunter"), "A").ready
    loop.gs.battlefields[1].add_unit("B", _unit("Holder", 2))
    assert loop.gs.battlefields[1].control() == "B"
    assert loop._play_unit(_card("Vayne Hunter"), "A").ready


def test_other_units_conditions_dont_count_the_unit_itself():
    """Disposal Expert: 'I enter ready if you control no other units.'
    Xin Zhao Vigilant: '... if you have two or more other units in your base.'"""
    loop, a, b = _setup()
    assert loop._play_unit(_card("Disposal Expert"), "A").ready
    assert not loop._play_unit(_card("Disposal Expert"), "A").ready
    loop, a, b = _setup()
    a.base_units.append(_unit("One", 1))
    assert not loop._play_unit(_card("Xin Zhao Vigilant"), "A").ready
    loop, a, b = _setup()
    a.base_units.extend([_unit("One", 1), _unit("Two", 1)])
    assert loop._play_unit(_card("Xin Zhao Vigilant"), "A").ready


def test_where_it_was_played_counts():
    """Shadow: 'If you play me to a battlefield, I enter ready.'"""
    loop, a, b = _setup()
    assert loop._play_unit(_card("Shadow"), "A", bf=loop.gs.battlefields[0]).ready
    assert not loop._play_unit(_card("Shadow"), "A").ready


def test_paid_as_it_is_played_then_it_enters_ready():
    """Incorrigible Construct: 'SHOW OFF a Mech. I enter ready if you showed
    off.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Mech"))
    loop.chooser = _always(True)
    assert loop._play_unit(_card("Incorrigible Construct"), "A").ready
    loop, a, b = _setup()
    loop.chooser = _always(False)
    a.base_units.append(_unit("Mech"))
    assert not loop._play_unit(_card("Incorrigible Construct"), "A").ready


def test_you_may_have_me_enter_ready_is_asked_once():
    """Entrenched Boar: 'You may have me enter ready. If you do, I can't move
    this turn.'"""
    loop, a, b = _setup()
    asked = []
    loop.chooser = lambda _l, kind, side, options, default, source: asked.append(kind)
    boar = loop._play_unit(_card("Entrenched Boar"), "A")
    assert asked == ["optional:enter_ready"]
    assert boar.ready and boar.cant_move_turn == loop.gs.turn
    loop, a, b = _setup()
    loop.chooser = _always(False)
    boar = loop._play_unit(_card("Entrenched Boar"), "A")
    assert not boar.ready and boar.cant_move_turn != loop.gs.turn


def test_already_ready_asks_nothing():
    """ACCELERATE or 'Units you play this turn enter ready' (Confront) first:
    the Boar enters ready anyway and nothing stops it moving."""
    loop, a, b = _setup()
    loop.gs.units_enter_ready_turn["A"] = loop.gs.turn
    loop.chooser = _always(True)
    boar = loop._play_unit(_card("Entrenched Boar"), "A")
    assert boar.ready and boar.cant_move_turn != loop.gs.turn


def test_every_i_enter_ready_card_is_encoded_as_one():
    """No card's own 'enter ready' is a 'when you play me, ready me' any more.
    'When you play me, ready me' cards (Darius Executioner, Dropboarder, Pyke,
    Poppy Paragon) stay triggers."""
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "riftbound" / "data" / "cards" / "all_cards.json"
    own = re.compile(r"\bI enter ready|and enter ready|You may have me enter ready")
    seen = set()
    for c in json.loads(path.read_text(encoding="utf-8")):
        if not own.search(c.get("effect") or ""):
            continue
        effects = c.get("effects") or []
        assert any(e.get("trigger") == "self_enter_ready" for e in effects), c["name"]
        assert not any(e.get("effect") == "ready_unit" and e.get("target") == "self"
                       for e in effects), c["name"]
        seen.add(c["name"])
    assert len(seen) == 29
    for name in ("Darius Executioner", "Dropboarder", "Pyke Dockside Butcher", "Poppy Paragon"):
        assert any(e.trigger == "on_play" and e.effect == "ready_unit"
                   for e in CARD_REGISTRY[name].effects), name
