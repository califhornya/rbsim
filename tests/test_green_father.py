"""Battlefield tokens (BACKLOG E): Ivern Green Father, "When you conquer or hold,
you may exhaust me to replace that battlefield with a Brush battlefield token",
and the Brush (§187.8): "Bird, Cat, Dog, Poro, and Ivern units here have +1
[might]" and "When you score here, you may replace this with the battlefield it
replaced" (Replace §439)."""
from __future__ import annotations

from riftbound.core.battlefield import FacedownCard
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import CardType
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _battlefield, _conquer, _deck, _fight, _hold, _setup, _unit


def _ivern(loop, side="A", ready=True):
    legend = UnitInPlay(card=CARD_REGISTRY["Ivern Green Father"].instantiate(), ready=ready)
    if side == "A":
        loop.gs.legend_unit_A = legend
    else:
        loop.gs.legend_unit_B = legend
    return legend


def _pet(tag="Cat", might=2):
    return UnitInPlay(card=UnitCard(name=f"Pet {tag}", might=might, tags=[tag]), ready=True)


def _answer(loop, kind, yes):
    def chooser(_loop, k, side, options, default, source):
        return options.index(yes) if k == kind else None
    loop.chooser = chooser


def test_brush_is_a_battlefield_token():
    assert CARD_REGISTRY["Brush"].category is CardType.BATTLEFIELD
    assert CARD_REGISTRY["Baron Pit"].category is CardType.BATTLEFIELD


def test_ivern_replaces_a_held_battlefield_with_brush_after_its_hold_effect():
    loop, a, b = _setup()
    legend = _ivern(loop)
    _deck(a, SpellCard(name="S1"))
    pet = _pet()
    bf = _hold(loop, "Grove of the God-Willow", unit=pet)
    assert [c.name for c in a.hand] == ["S1"]          # "When you hold here, draw 1" resolved
    assert bf.card.name == "Brush" and bf.replaced.name == "Grove of the God-Willow"
    assert not legend.ready
    assert pet in bf.units_A and pet.might == 3


def test_ivern_conquers_by_combat_and_replaces_that_battlefield():
    loop, a, b = _setup()
    _ivern(loop)
    _battlefield(loop, 0, "Zaun Warrens")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _pet("Dog", 3))
    bf.add_unit("B", _unit("Defender", 1))
    _fight(loop)
    assert loop.gs.points_A == 1
    assert bf.card.name == "Brush" and bf.replaced.name == "Zaun Warrens"


def test_ivern_keeps_the_battlefield_with_no_pet_there():
    loop, a, b = _setup()
    legend = _ivern(loop)
    bf = _hold(loop, "Grove of the God-Willow")
    assert bf.card.name == "Grove of the God-Willow" and bf.replaced is None
    assert legend.ready


def test_ivern_may_decline_and_cant_when_exhausted():
    loop, a, b = _setup()
    legend = _ivern(loop)
    _answer(loop, "optional:green_father_brush", False)
    bf = _hold(loop, "Grove of the God-Willow", unit=_pet())
    assert bf.card.name == "Grove of the God-Willow" and legend.ready
    loop, a, b = _setup()
    _ivern(loop, ready=False)
    bf = _hold(loop, "Grove of the God-Willow", unit=_pet())
    assert bf.card.name == "Grove of the God-Willow"


def test_brush_gives_bird_cat_dog_poro_and_ivern_units_here_plus_one_for_both_players():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Brush")
    bf = loop.gs.battlefields[0]
    bird, poro, plain = _pet("Bird", 1), _pet("Poro", 1), _unit("Plain", 2)
    nurturer, dog = _unit("Ivern Nurturer"), _pet("Dog", 1)
    for u in (bird, poro, plain, nurturer):
        bf.add_unit("A", u)
    bf.add_unit("B", dog)
    elsewhere = _pet("Cat", 2)
    loop.gs.battlefields[1].add_unit("A", elsewhere)
    loop._recompute_passives()
    assert (bird.might, poro.might, plain.might, nurturer.might, dog.might) == (2, 2, 2, 5, 2)
    assert elsewhere.might == 2


def test_brush_swaps_back_when_scored_and_its_battlefield_returns_with_its_units():
    loop, a, b = _setup()
    legend = _ivern(loop)
    _deck(a, SpellCard(name="S1"), SpellCard(name="S2"))
    pet = _pet()
    bf = _hold(loop, "Grove of the God-Willow", unit=pet)
    assert bf.card.name == "Brush"
    legend.ready = True
    _answer(loop, "optional:brush_swap_back", True)
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert bf.card.name == "Grove of the God-Willow" and bf.replaced is None
    assert [c.name for c in a.hand] == ["S1"]          # scored at the Brush: no Grove draw
    assert legend.ready                                 # Ivern doesn't replace a Brush
    assert pet in bf.units_A and pet.might == 2


def test_brush_baseline_swaps_back_only_when_no_friendly_pet_is_there():
    loop, a, b = _setup()
    bf = _conquer(loop, "Brush", unit=_pet())
    bf.replaced = CARD_REGISTRY["Zaun Warrens"].instantiate()
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert bf.card.name == "Brush"
    bf.units_A.clear()
    bf.add_unit("A", _unit("Plain", 2))
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert bf.card.name == "Zaun Warrens"


def test_a_brush_with_nothing_replaced_never_swaps_back():
    loop, a, b = _setup()
    bf = _hold(loop, "Brush")
    assert bf.card.name == "Brush"


def test_replacing_aspirants_climb_lowers_the_points_to_win_until_it_swaps_back():
    loop, a, b = _setup()
    _ivern(loop)
    _battlefield(loop, 0, "Aspirant's Climb")
    loop.gs.victory_score = 9
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _pet())
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert bf.card.name == "Brush" and loop.gs.victory_score == 8
    loop._swap_back_battlefield(bf)
    assert bf.card.name == "Aspirant's Climb" and loop.gs.victory_score == 9


def test_brush_at_bandle_tree_leaves_room_for_one_facedown_card():
    loop, a, b = _setup()
    _ivern(loop)
    _battlefield(loop, 0, "Bandle Tree")
    bf = loop.gs.battlefields[0]
    one, two = UnitCard(name="One", might=1), UnitCard(name="Two", might=1)
    bf.facedowns = [FacedownCard(card=one, owner="A", turn_hidden=1),
                    FacedownCard(card=two, owner="A", turn_hidden=1)]
    bf.add_unit("A", _pet())
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert bf.card.name == "Brush"
    assert [fd.card for fd in bf.facedowns] == [one] and two in a.trash


def test_an_opponents_ivern_replaces_the_battlefield_they_conquered():
    loop, a, b = _setup()
    legend = _ivern(loop, side="B")
    bf = _conquer(loop, "Zaun Warrens", side="B", unit=_pet("Poro"))
    assert bf.card.name == "Brush" and not legend.ready
