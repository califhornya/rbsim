"""BACKLOG G1, engine bugs. A unit dying in base doesn't die "here" at
battlefield 0 (_route_deaths in_base: Black Rose Sanctum, Storm Raptor, Lonely
Poro). A base unit's "your units here" passives reach its base, not battlefield
0 (Alpha Wildclaw). PREDICT 2+ (§437.1.a): recycle any number, put the rest
back in any order. What a card spends to cost less (GameLoop._cost_extras,
KNOWN_ISSUES #27) applies from any zone (§356.2) and every paid play spends it
(_pay_card)."""

from __future__ import annotations

import pytest

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _always, _battlefield, _deck, _setup, _unit
from test_corpus_vendetta import _ctx
from test_endless_riches import _play_from_trash, _riches, _trash_plays


def _recruits(p):
    return [u for u in p.base_units if u.card.name == "Recruit"]


@pytest.mark.parametrize("at_battlefield", [False, True])
def test_a_temporary_unit_dying_in_base_doesnt_die_at_battlefield_0(at_battlefield):
    """Black Rose Sanctum: 'the first time each turn a non-token unit they
    control dies here, they play a 1 [might] Recruit unit token to their base.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Black Rose Sanctum")
    temp = UnitInPlay(card=UnitCard(name="Temp", might=1, keywords=["TEMPORARY"]))
    if at_battlefield:
        loop.gs.battlefields[0].add_unit("A", temp)
    else:
        a.base_units.append(temp)
    loop._phase_beginning("A")
    assert temp not in a.base_units and len(_recruits(a)) == int(at_battlefield)


def test_bottled_constellations_kills_in_base_arent_here():
    loop, a, b = _setup()
    loop.chooser = _always(True)
    _battlefield(loop, 0, "Black Rose Sanctum")
    a.base_gear.append(CARD_REGISTRY["Bottled Constellation"].instantiate())
    a.base_units.extend([_unit("U1", 1), _unit("U2", 1), _unit("U3", 1)])
    loop._fire_turn_trigger("on_start_of_main", "A")
    assert loop.gs.points_A == 1 and not a.base_units


def test_storm_raptor_and_lonely_poro_see_a_death_in_base():
    """Storm Raptor: 'When a stunned enemy unit dies here, draw 1.' Lonely Poro:
    'DEATHKNELL - If I died alone, draw 1.' (alone = no other friendly unit
    where it died)."""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Storm Raptor"))
    _deck(a, *[UnitCard(name=f"A{i}", might=1) for i in range(3)])
    _deck(b, *[UnitCard(name=f"B{i}", might=1) for i in range(3)])
    stunned = _unit("Stunned", 1)
    stunned.stunned = True
    loop._route_deaths([(stunned, "B")], bf, in_base=True)
    assert not a.hand
    b.base_units.append(_unit("Friend", 1))
    loop._route_deaths([(_unit("Lonely Poro"), "B")], bf, in_base=True)
    assert not b.hand
    b.base_units.clear()
    loop._route_deaths([(_unit("Lonely Poro"), "B")], bf, in_base=True)
    assert len(b.hand) == 1


def test_alpha_wildclaw_in_base_protects_its_base_not_battlefield_0():
    """'Your units here with less Might than me can't be chosen by enemy spells
    and abilities.'"""
    loop, a, b = _setup()
    wildclaw, near, far = _unit("Alpha Wildclaw"), _unit("Near", 1), _unit("Far", 1)
    a.base_units.extend([wildclaw, near])
    loop.gs.battlefields[0].add_unit("A", far)
    loop._recompute_passives()
    assert near.unchoosable and not far.unchoosable


def test_predict_2_plus_recycles_any_then_orders_the_rest():
    loop, a, b = _setup()
    low, mid, high, under = (UnitCard(name=n, might=m) for n, m in
                             (("Low", 1), ("Mid", 2), ("High", 3), ("Under", 0)))
    a.deck.cards = [under, low, mid, high]                 # top = end
    REGISTRY["predict"](_ctx(loop, a), {"amount": 3})
    assert [c.name for c in a.deck.cards] == ["Under", "Low", "Mid", "High"]   # baseline: mightiest on top

    def chooser(_l, kind, side, options, default, source):
        if kind == "predict_recycle":
            return options.index(source.name == "Mid")
        if kind == "predict_order":
            return next((i for i, c in enumerate(options) if c.name == "Low"), None)
        return None
    loop.chooser = chooser
    REGISTRY["predict"](_ctx(loop, a), {"amount": 3})
    assert [c.name for c in a.deck.cards] == ["Mid", "Under", "High", "Low"]   # Low drawn next


def test_here_to_help_spends_brazen_buccaneers_discard():
    """Here to Help: 'play a unit from your hand to a battlefield you control,
    reducing its cost by [3].' Brazen Buccaneer [6]: 'you may discard a card as
    an additional cost. If you do, reduce my cost by [2].'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Holder", 1))
    brazen, junk = CARD_REGISTRY["Brazen Buccaneer"].instantiate(), UnitCard(name="Junk", might=1)
    a.hand = [brazen, junk]
    a.energy = 1
    REGISTRY["play_unit_to_controlled_battlefield"](_ctx(loop, a), {"reduce": 3})
    assert any(u.card is brazen for u in bf.units_A)
    assert a.energy == 0 and a.trash == [junk] and not a.hand


def test_kraken_hunter_spends_buffs_from_the_trash():
    """Endless Riches lets you play Kraken Hunter [3][body][body] from the
    trash: 'As you play me, you may spend any number of buffs ... [body] less
    for each' still applies there."""
    loop, a, b = _setup()
    _riches(a)
    kraken = CARD_REGISTRY["Kraken Hunter"].instantiate()
    a.trash = [kraken]
    for i in range(2):
        u = _unit(f"Buffed{i}", 1)
        u.might_counters = 1
        a.base_units.append(u)
    a.energy, a.power_pool = 3, {}
    loop._recompute_passives()
    assert _trash_plays(loop)
    _play_from_trash(loop, a, "Kraken Hunter")
    assert any(u.card is kraken for u in a.base_units)
    assert a.energy == 0 and all(u.might_counters == 0 for u in a.base_units if u.card is not kraken)
