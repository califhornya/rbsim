"""Rules audit, fourth pass (docs/audit/AUDIT.md): the cards outside the ten
decks, by class of deviation, against the printed text
(riftbound/data/reference/piltover_archive.json) and played in the engine."""

from __future__ import annotations

import pytest

from riftbound.core.combat import UnitInPlay

from audit_helpers import act, card, choices, labels, legend, setup, unit


def _abilities(loop, side: str, name: str) -> list:
    """The activated abilities of `name` offered to `side` now."""
    return [lb for lb in labels(loop, side) if lb.startswith(("Activate", "Gear")) and name in lb]


def _board(name: str):
    """`name` alone on A's side: a legend, a gear in base, or a unit at
    battlefield 0. A can pay for anything and has a card to discard."""
    loop, a, b = setup(active="A")
    a.hand.append(card("Stacked Deck"))
    a.deck.cards[:] = [card("Stacked Deck") for _ in range(6)]
    c = card(name)
    kind = c.category.name
    if kind == "LEGEND":
        legend(loop, "A", name)
    elif kind == "GEAR":
        a.base_gear.append(c)
    else:
        loop.gs.battlefields[0].units_A.append(UnitInPlay(card=c, ready=True))
    return loop, a, b, c


# -- D29. An activated ability that chooses something other than one unit is ------
# -- offered with nothing to choose ----------------------------------------------
# §403.3: "If legal options are not available for an Activated Ability, it is not
# legal to activate it." §355.5: "If a card requires you to specifically choose
# one or more Game Objects, that choice is made now."

@pytest.mark.parametrize("name, printed", [
    ("Jax Grandmaster at Arms", "Attach a detached Equipment you control to a unit you control"),
    ("Pyke Bloodharbor Ripper", "Return a friendly unit at a battlefield to its owner's hand"),
    ("Jayce Defender of Tomorrow", "Ready a gear"),
    ("Teemo Swift Scout", "Put a Teemo unit you own into your hand from your Champion Zone or the board"),
    ("Akali Rogue Assassin", "move a friendly unit in a showdown to base"),
    ("Maduli the Gatekeeper", "Move me to an occupied enemy battlefield"),
    ("Unlicensed Armory", "Choose a friendly unit"),
    ("Pack of Wonders", "Return another friendly gear, unit, or facedown card"),
    ("Baited Hook", "Kill a friendly unit"),
    ("Cursed Sarcophagus", "Play a unit banished with this"),
])
def test_an_ability_with_nothing_to_choose_is_not_offered(name, printed):
    loop, a, b, _c = _board(name)
    assert [lb for lb in _abilities(loop, "A", name) if "empower_self" not in lb] == [], printed


def test_jax_legend_is_offered_with_an_equipment_and_a_unit():
    loop, a, b, _c = _board("Jax Grandmaster at Arms")
    a.base_units.append(unit("x", 2))
    assert _abilities(loop, "A", "Jax") == []
    a.base_gear.append(card("Long Sword"))
    assert len(_abilities(loop, "A", "Jax")) == 1          # the detached one
    a.base_units[0].gear.append(a.base_gear.pop())
    assert _abilities(loop, "A", "Jax") == []              # attached, no other unit
    a.base_units.append(unit("y", 2))
    assert len(_abilities(loop, "A", "Jax")) == 1


def test_pyke_legend_is_offered_with_a_unit_at_a_battlefield():
    loop, a, b, _c = _board("Pyke Bloodharbor Ripper")
    a.base_units.append(unit("x", 2))
    assert _abilities(loop, "A", "Pyke") == []
    loop.gs.battlefields[1].units_A.append(unit("y", 2))
    act(loop, "A", "Activate sequence (Pyke")
    assert [c.name for c in a.hand] == ["Stacked Deck", "y"]
    assert [g.name for g in a.base_gear] == ["Gold"]


def test_jayce_legend_is_offered_with_an_exhausted_gear():
    loop, a, b, _c = _board("Jayce Defender of Tomorrow")
    seal = card("Seal of Rage")
    seal.tapped = True
    a.base_gear.append(seal)
    act(loop, "A", "Activate ready_gear (Jayce")
    assert not seal.tapped


def test_maduli_is_offered_with_a_weaker_enemy_battlefield():
    loop, a, b, _c = _board("Maduli the Gatekeeper")
    loop.gs.battlefields[1].units_B.append(unit("big", 6))
    assert _abilities(loop, "A", "Maduli") == []           # 6 is not greater than 6
    loop.gs.battlefields[1].units_B[0] = unit("small", 5)
    assert len(_abilities(loop, "A", "Maduli")) == 1


def test_baited_hook_is_offered_with_a_friendly_unit():
    loop, a, b, _c = _board("Baited Hook")
    a.base_units.append(unit("x", 2))
    assert len(_abilities(loop, "A", "Baited Hook")) == 1


# -- D30. Jax's legend moves an attached Equipment only from base to a battlefield -

def test_jax_legend_moves_an_attached_equipment_between_any_two_units():
    """Jax, Grandmaster at Arms: '[Tap]: Attach an attached Equipment you
    control to a unit you control.' No place is named for either unit."""
    loop, a, b, _c = _board("Jax Grandmaster at Arms")
    wearer, other = unit("wearer", 2), unit("other", 2)
    sword = card("Long Sword")
    wearer.gear.append(sword)
    loop.gs.battlefields[0].units_A.append(wearer)        # worn at a battlefield
    a.base_units.append(other)                            # the other unit in base
    act(loop, "A", "Activate attach_equipment (Jax")
    assert other.gear == [sword] and wearer.gear == []


# -- D31. Teemo's legend takes a Teemo only from the Champion Zone -----------------

def test_teemo_legend_takes_a_teemo_from_the_board():
    """Teemo, Swift Scout: '[1], [Tap]: Put a Teemo unit you own into your
    hand from your Champion Zone or the board.'"""
    loop, a, b, _c = _board("Teemo Swift Scout")
    loop.gs.champion_A_deployed = True
    teemo = unit("Teemo Scout")
    loop.gs.battlefields[1].units_A.append(teemo)
    act(loop, "A", "Activate champion_to_hand (Teemo")
    assert teemo.card in a.hand and not loop.gs.battlefields[1].units_A


def test_teemo_legend_takes_the_teemo_in_the_champion_zone():
    loop, a, b, _c = _board("Teemo Swift Scout")
    loop.gs.champion_A = card("Teemo Scout")
    a.base_units.append(unit("x", 2))
    act(loop, "A", "Activate champion_to_hand (Teemo")
    assert loop.gs.champion_A in a.hand and loop.gs.champion_A_deployed


# -- D32. Baited Hook kills the weakest unit that isn't a token, unasked -----------

def test_baited_hook_kills_the_friendly_unit_its_player_chooses():
    """Baited Hook: 'Kill a friendly unit. Look at the top 5 cards of your Main
    Deck. You may banish a unit from among them that has Might up to 1 more
    than the killed unit and play it, ignoring its cost.' A token is a unit."""
    loop, a, b, _c = _board("Baited Hook")
    weak, strong = unit("weak", 1), unit("strong", 5)
    token = unit("Recruit", 1)
    token.is_token = True
    a.base_units.extend([weak, strong])
    seen = choices(loop, {"target:reveal_play_top": lambda _loop, options: options.index(strong)})
    a.deck.cards[:] = [card("Maduli the Gatekeeper")] + [card("Stacked Deck") for _ in range(4)]
    act(loop, "A", "Gear reveal_play_top (Baited Hook")
    assert strong not in a.base_units and weak in a.base_units
    assert [u.card.name for u in a.base_units] == ["weak", "Maduli the Gatekeeper"]   # Might 6 <= 5 + 1
    assert any(kind == "target:reveal_play_top" for kind, _side, _opts in seen)

    loop, a, b, _c = _board("Baited Hook")
    a.base_units.append(token)                            # only a token to kill
    assert len(_abilities(loop, "A", "Baited Hook")) == 1
