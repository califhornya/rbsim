"""Neeko Blending In (BACKLOG E): "If Neeko is in your deck, choose up to 3
different legends in addition to your starting legend. When you play me,
choose one of those Legends and add it to your Legend Zone while I'm on the
board." The deckbuilding legends are `GameState.extra_legends` (deck JSON
"extra_legends"); the ones she added are `GameState.added_legends`, and
`GameLoop._legend_units` lists every legend in a Legend Zone. Her cost's
power is [A] (a Neutral card, §135.2.e.6.b); a multi-domain card's power is
any power of its domains (§135.2.e.6.c)."""

from __future__ import annotations

import json

import pytest

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import Observation
from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import CARD_REGISTRY, load_extra_legends_json

from test_corpus_cards import _deck, _setup, _unit
from test_corpus_radiance import _card, _die
from test_corpus_vendetta import _start_turn, _usable


def _champion_legend(loop, side, name):
    unit = UnitInPlay(card=_card(name), ready=True)
    setattr(loop.gs, f"legend_unit_{side}", unit)
    return unit


def _pool(loop, side, *names):
    loop.gs.extra_legends[side] = [_card(n) for n in names]


def _play_neeko(loop, p):
    p.hand.append(_card("Neeko Blending In"))
    loop._apply_action(p, ("UNIT", len(p.hand) - 1, None, None))
    loop._recompute_passives()
    return [u for u in p.base_units if u.card.name == "Neeko Blending In"][-1]


def _legend_names(loop, side):
    return [lu.card.name for lu in loop._legend_units(side)]


def _no_power(p):
    p.power_pool, p.floating_power, p.rune_pool = {}, {}, {}


def test_playing_her_adds_the_first_listed_legend_ready():
    loop, a, b = _setup()
    _champion_legend(loop, "A", "Sett The Boss")
    _pool(loop, "A", "Diana Scorn of the Moon", "Jinx Loose Cannon")
    _play_neeko(loop, a)
    assert _legend_names(loop, "A") == ["Sett The Boss", "Diana Scorn of the Moon"]
    added = loop._legend_units("A")[1]
    assert added.ready
    assert loop.gs.legend_unit_A.card.name == "Sett The Boss"     # still the Champion Legend
    assert _legend_names(loop, "B") == []


def test_her_player_chooses_which_legend():
    loop, a, b = _setup()
    _pool(loop, "A", "Diana Scorn of the Moon", "Jinx Loose Cannon")

    def chooser(_loop, kind, side, options, default, source):
        if kind == "target:add_extra_legend":
            return [o.name for o in options].index("Jinx Loose Cannon")
        return None
    loop.chooser = chooser
    _play_neeko(loop, a)
    assert _legend_names(loop, "A") == ["Jinx Loose Cannon"]


def test_without_deckbuilding_legends_she_adds_nothing():
    loop, a, b = _setup()
    _play_neeko(loop, a)
    assert loop._legend_units("A") == []
    assert len(a.base_units) == 1


def test_the_legend_leaves_when_she_leaves_the_board():
    loop, a, b = _setup()
    _pool(loop, "A", "Diana Scorn of the Moon")
    neeko = _play_neeko(loop, a)
    assert _legend_names(loop, "A") == ["Diana Scorn of the Moon"]
    a.base_units.remove(neeko)
    loop._route_deaths([(neeko, "A")], loop.gs.battlefields[0])
    loop._recompute_passives()
    assert loop._legend_units("A") == []
    assert [c.name for c in a.trash] == ["Neeko Blending In"]       # the legend isn't a card there


def test_it_stays_while_she_moves_and_a_second_neeko_adds_another():
    loop, a, b = _setup()
    _pool(loop, "A", "Diana Scorn of the Moon", "Jinx Loose Cannon")
    first = _play_neeko(loop, a)
    a.base_units.remove(first)
    loop.gs.battlefields[0].add_unit("A", first)          # at a battlefield: still on the board
    loop._recompute_passives()
    _play_neeko(loop, a)
    assert _legend_names(loop, "A") == ["Diana Scorn of the Moon", "Jinx Loose Cannon"]
    _die(loop, first)                                     # the first one's legend goes
    loop._recompute_passives()
    assert _legend_names(loop, "A") == ["Jinx Loose Cannon"]


def test_replayed_she_adds_a_legend_again():
    loop, a, b = _setup()
    _pool(loop, "A", "Diana Scorn of the Moon")
    neeko = _play_neeko(loop, a)
    a.base_units.remove(neeko)
    loop._recompute_passives()
    assert loop._legend_units("A") == []
    _play_neeko(loop, a)
    assert _legend_names(loop, "A") == ["Diana Scorn of the Moon"]


def test_an_added_legends_ability_is_usable_and_exhausts_it():
    loop, a, b = _setup()
    sett = _champion_legend(loop, "A", "Sett The Boss")
    _pool(loop, "A", "Diana Scorn of the Moon")
    _play_neeko(loop, a)
    diana = loop._legend_units("A")[1]
    loop._apply_action(a, ("ABILITY", "ACTIVATED", _usable(loop, "A", "add_earmarked_energy"), None))
    assert a.earmarked_energy_showdown == 1
    assert not diana.ready and sett.ready


def test_an_added_legends_trigger_fires():
    """Jinx Loose Cannon: 'At the start of your Beginning Phase, draw 1 if you
    have one or fewer cards in your hand.'"""
    loop, a, b = _setup()
    _pool(loop, "A", "Jinx Loose Cannon")
    _play_neeko(loop, a)
    _deck(a, UnitCard(name="Top", might=1))
    a.hand = []
    _start_turn(loop, "A")
    assert [c.name for c in a.hand] == ["Top"]


def test_an_added_legends_passive_applies():
    """Renata Glasc Chem-Baroness: 'While your score is within 3 points of the
    Victory Score, your Gold ADD an additional [1].'"""
    loop, a, b = _setup()
    loop.gs.points_A = loop.gs.victory_score - 2
    assert not loop._gold_bonus("A")
    _pool(loop, "A", "Renata Glasc Chem-Baroness")
    _play_neeko(loop, a)
    assert loop._gold_bonus("A")


def test_every_legend_readies_in_the_awaken_phase():
    loop, a, b = _setup()
    sett = _champion_legend(loop, "A", "Sett The Boss")
    _pool(loop, "A", "Diana Scorn of the Moon")
    _play_neeko(loop, a)
    for lu in loop._legend_units("A"):
        lu.ready = False
    loop._begin_turn()
    assert sett.ready and loop._legend_units("A")[1].ready


def test_ready_your_legend_takes_an_exhausted_one():
    """Heartening Soul: 'When you play me, ready a friendly legend.' With the
    Champion Legend ready, the added one is readied (§355.10.g)."""
    loop, a, b = _setup()
    sett = _champion_legend(loop, "A", "Sett The Boss")
    _pool(loop, "A", "Diana Scorn of the Moon")
    _play_neeko(loop, a)
    diana = loop._legend_units("A")[1]
    diana.ready = False
    assert loop._check_condition({"type": "your_legend_exhausted"}, _card("Hall of Legends"), a, b, {})
    a.hand.append(_card("Heartening Soul"))
    loop._apply_action(a, ("UNIT", len(a.hand) - 1, None, None))
    assert diana.ready and sett.ready


def test_friendly_legends_have_abilities_reach_every_legend():
    """Heartening Soul: 'Friendly legends have "[tap]: Give a unit +3 [might]
    this turn."'"""
    loop, a, b = _setup()
    sett = _champion_legend(loop, "A", "Sett The Boss")
    _pool(loop, "A", "Diana Scorn of the Moon")
    _play_neeko(loop, a)
    a.base_units.append(_unit("Heartening Soul"))
    holders = [e["unit"] for e in loop.activatable_abilities("A")
               if e.get("eff") is not None and e["eff"].effect == "grant_temporary_might"]
    assert sett in holders and loop._legend_units("A")[1] in holders


def test_kharox_playing_an_opponents_neeko_adds_his_players_legend():
    """FAQ (Kharox + Neeko): playing the opponent's Neeko from their trash adds
    one of your own deckbuilding legends, to your Legend Zone."""
    loop, a, b = _setup()
    _pool(loop, "A", "Diana Scorn of the Moon")
    _pool(loop, "B", "Jinx Loose Cannon")
    kharox = _unit("Kharox")
    a.base_units.append(kharox)
    _deck(b, UnitCard(name="S1", might=1), _card("Neeko Blending In"), UnitCard(name="S3", might=1))
    _kharox_takes_neeko(loop)
    loop._empower(kharox.card, "A")
    loop._recompute_passives()
    assert any(u.card.name == "Neeko Blending In" for u in a.base_units)
    assert _legend_names(loop, "A") == ["Diana Scorn of the Moon"]
    assert _legend_names(loop, "B") == []


def _kharox_takes_neeko(loop):
    def chooser(_loop, kind, side, options, default, source):
        names = [getattr(o, "name", None) for o in options]
        return names.index("Neeko Blending In") if kind.startswith("target") and \
            "Neeko Blending In" in names else None
    loop.chooser = chooser


def test_an_opponents_neeko_with_no_legends_of_yours_adds_none():
    loop, a, b = _setup()
    _pool(loop, "B", "Jinx Loose Cannon")
    kharox = _unit("Kharox")
    a.base_units.append(kharox)
    _deck(b, UnitCard(name="S1", might=1), _card("Neeko Blending In"), UnitCard(name="S3", might=1))
    _kharox_takes_neeko(loop)
    loop._empower(kharox.card, "A")
    loop._recompute_passives()
    assert any(u.card.name == "Neeko Blending In" for u in a.base_units)
    assert loop._legend_units("A") == [] and loop._legend_units("B") == []


def test_the_observation_shows_added_legends():
    loop, a, b = _setup()
    _pool(loop, "A", "Diana Scorn of the Moon")
    _play_neeko(loop, a)
    mine, theirs = Observation.from_state(loop.gs, "A"), Observation.from_state(loop.gs, "B")
    assert mine.my_added_legends == (("Diana Scorn of the Moon", True),)
    assert theirs.opp_added_legends == (("Diana Scorn of the Moon", True),)
    assert mine.to_dict()["my_added_legends"] == [["Diana Scorn of the Moon", True]]


# -- Her cost's [A], and multi-domain cards' power --------------------------

def test_her_power_is_any_domain():
    loop, a, b = _setup()
    neeko = _card("Neeko Blending In")
    _no_power(a)
    a.energy = 6
    assert not loop._can_pay_card(a, neeko, 6, 1)
    a.add_power(Domain.ORDER, 1)
    assert loop._can_pay_card(a, neeko, 6, 1)
    assert loop._pay_card(a, neeko, 6, 1)
    assert a.energy == 0 and a.power_pool == {}


def test_a_multi_domain_cards_power_comes_from_its_domains():
    """Moonfall: [3] and one [mind] or [chaos]."""
    loop, a, b = _setup()
    moonfall = _card("Moonfall")
    assert moonfall.cost_power == 1 and moonfall.cost_power_domain is None
    _no_power(a)
    a.energy = 3
    a.add_power(Domain.FURY, 2)
    assert not loop._can_pay_card(a, moonfall, 3, 1)
    a.add_power(Domain.CHAOS, 1)
    assert loop._pay_card(a, moonfall, 3, 1)
    assert a.power_pool == {Domain.FURY: 2}


def test_a_multi_domain_cards_power_can_mix_its_domains():
    """Icathian Rain: three power from [fury] and [mind]."""
    loop, a, b = _setup()
    rain = _card("Icathian Rain")
    _no_power(a)
    a.energy = 20
    a.add_power(Domain.FURY, 2)
    a.add_power(Domain.MIND, 1)
    a.add_power(Domain.CHAOS, 3)
    assert loop._pay_card(a, rain, rain.cost_energy, 3)
    assert a.power_pool == {Domain.CHAOS: 3}


def test_a_player_can_pay_domainless_power_with_any():
    """Player.can_pay_cost with no domain is [A] (it was free)."""
    loop, a, b = _setup()
    _no_power(a)
    assert not a.can_pay_cost(0, 1, None)
    a.add_power(Domain.BODY, 1)
    assert a.can_pay_cost(0, 1, None) and a.pay_cost(0, 1, None)
    assert a.power_pool == {}


# -- Deckbuilding ------------------------------------------------------------

def _deck_file(tmp_path, **data):
    path = tmp_path / "deck.json"
    base = {"name": "t", "legend": "Sett The Boss", "cards": [{"name": "Neeko Blending In", "count": 1}]}
    base.update(data)
    path.write_text(json.dumps(base), encoding="utf-8")
    return path


def test_a_deck_with_neeko_lists_up_to_three_legends(tmp_path):
    path = _deck_file(tmp_path, extra_legends=["Diana Scorn of the Moon", "Jinx Loose Cannon",
                                               "Renata Glasc Chem-Baroness"])
    assert [s.name for s in load_extra_legends_json(path)] == [
        "Diana Scorn of the Moon", "Jinx Loose Cannon", "Renata Glasc Chem-Baroness"]


def test_neeko_in_the_sideboard_is_enough(tmp_path):
    path = _deck_file(tmp_path, cards=[], sideboard=[{"name": "Neeko Blending In", "count": 1}],
                      extra_legends=["Jinx Loose Cannon"])
    assert [s.name for s in load_extra_legends_json(path)] == ["Jinx Loose Cannon"]


@pytest.mark.parametrize("data", [
    {"extra_legends": ["Diana Scorn of the Moon", "Jinx Loose Cannon",
                       "Renata Glasc Chem-Baroness", "Teemo Swift Scout"]},          # four
    {"extra_legends": ["Jinx Loose Cannon", "Jinx Loose Cannon"]},                   # same name
    {"extra_legends": ["Sett The Boss"]},                                             # the starting one
    {"extra_legends": ["Neeko Blending In"]},                                         # not a legend
    {"cards": [], "extra_legends": ["Jinx Loose Cannon"]},                            # no Neeko
])
def test_bad_extra_legends_are_refused(tmp_path, data):
    with pytest.raises(ValueError):
        load_extra_legends_json(_deck_file(tmp_path, **data))


def test_a_deck_without_extra_legends_has_none(tmp_path):
    assert load_extra_legends_json(_deck_file(tmp_path)) == []


def test_build_game_puts_each_decks_legends_in_the_pool(tmp_path):
    from pathlib import Path
    from riftbound.core.game_factory import build_game
    decks = Path(__file__).parent.parent / "riftbound" / "data" / "decks"
    data = json.loads((decks / "precon_shen.json").read_text(encoding="utf-8"))
    data["cards"][0] = {"name": "Neeko Blending In", "count": data["cards"][0].get("count", 1)}
    data["extra_legends"] = ["Jinx Loose Cannon"]
    data.pop("sideboard", None)
    data.pop("sideboard_plans", None)
    path = tmp_path / "neeko.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    gs = build_game(game_seed=1, deck_a_path=path, deck_b_path=decks / "precon_zed.json",
                    ai_a=None, ai_b=None)
    assert [c.name for c in gs.extra_legends["A"]] == ["Jinx Loose Cannon"]
    assert gs.extra_legends["B"] == []
    assert CARD_REGISTRY["Jinx Loose Cannon"].effects
