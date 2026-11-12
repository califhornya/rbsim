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


# -- D33. Ambessa's legend readies only a friendly exhausted unit ------------------

def test_ambessa_legend_can_choose_any_unit():
    """Ambessa, Matriarch of War: 'Disempower me, [Rune], [Tap]: Ready a
    unit.' (As D28: 'a unit' is any unit.)"""
    loop, a, b, _c = _board("Ambessa Matriarch of War")
    loop.gs.legend_unit_A.empowered = True
    mine, theirs = unit("mine", 2, ready=False), unit("theirs", 2, ready=False)
    b.base_units.append(theirs)
    seen = choices(loop, {})
    act(loop, "A", "Activate ready_unit (Ambessa")       # an enemy unit is enough
    assert seen[0][2] == ["theirs"] and theirs.ready

    loop, a, b, _c = _board("Ambessa Matriarch of War")
    loop.gs.legend_unit_A.empowered = True
    a.base_units.append(mine)
    b.base_units.append(unit("theirs", 2, ready=False))
    act(loop, "A", "Activate ready_unit (Ambessa")       # the baseline readies its own
    assert mine.ready and not b.base_units[0].ready


# -- D34. [rune][rune] can't be paid with Power of two domains ---------------------

def test_generic_power_is_paid_with_any_mix_of_domains():
    """§ costs: [rune] is 1 Power of any domain, each one on its own. Jayce,
    Defender of Tomorrow: '[Empower][2][Rune][Rune]'."""
    from riftbound.core.enums import Domain
    loop, a, b = setup(active="A", rich=())
    legend(loop, "A", "Jayce Defender of Tomorrow")
    a.energy = 2
    a.add_power(Domain.FURY, 1)
    a.add_power(Domain.CHAOS, 1)
    act(loop, "A", "Activate empower_self (Jayce")
    assert loop.gs.legend_unit_A.empowered and not any(a.power_pool.values())


# -- D35-D49. Card data against the print (piltover_sync compare, 131 cards) -------

def _data(name: str) -> dict:
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "riftbound" / "data" / "cards" / "all_cards.json"
    return next(c for c in json.loads(path.read_text(encoding="utf-8")) if c["name"] == name)


def test_printed_stats():
    """Spectral Centaur (UNL-068): Might 6. Fallen Feline (VEN-132): Might 3.
    Brittle Steel (VEN-003): [2][Fury]. Grand Strategem (OGN-233): [ACTION]."""
    assert card("Spectral Centaur").might == 6
    assert card("Fallen Feline").might == 3
    assert (_data("Brittle Steel")["cost_power"], _data("Brittle Steel")["cost_power_domain"]) == (1, "Fury")
    assert "ACTION" in card("Grand Strategem").keywords


def test_premonition_draws_three():
    """Premonition (SFD-087): '[REACTION] Draw 3.' It had no effect."""
    loop, a, b = setup(active="A")
    a.deck.cards[:] = [card("Stacked Deck") for _ in range(5)]
    a.hand.append(card("Premonition"))
    act(loop, "A", "Cast Premonition")
    assert len(a.hand) == 3


def test_zaunite_bouncer_returns_another_unit_at_a_battlefield():
    """Zaunite Bouncer (OGN-188): 'When you play me, return another unit at a
    battlefield to its owner's hand.' It had no effect."""
    loop, a, b = setup(active="A")
    enemy, home = unit("enemy", 3), unit("home", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    b.base_units.append(home)
    a.hand.append(card("Zaunite Bouncer"))
    seen = choices(loop, {})
    act(loop, "A", "Play Zaunite Bouncer")
    assert enemy.card in b.hand and home in b.base_units
    assert [opts for kind, _s, opts in seen if kind == "target:recall_unit"] == [["enemy"]]


def test_kings_edict_kills_the_unit_the_opponent_chooses():
    """King's Edict (OGN-237): 'Starting with the next player, each other
    player chooses a unit you don't control that hasn't been chosen for this
    spell. Kill those units.' It had no effect."""
    loop, a, b = setup(active="A")
    weak, strong, mine = unit("weak", 1), unit("strong", 5), unit("mine", 1)
    b.base_units.extend([weak, strong])
    a.base_units.append(mine)
    a.hand.append(card("King's Edict"))
    seen = choices(loop, {"target:each_opponent_kills_own_unit": lambda _l, options: options.index(strong)})
    act(loop, "A", "Cast King's Edict")
    assert b.base_units == [weak] and a.base_units == [mine]
    asked = {(side, tuple(opts)) for kind, side, opts in seen if kind.startswith("target:each")}
    assert asked == {("B", ("weak", "strong"))}


def test_overloaded_traveler_has_one_more_might_next_to_a_deployed_gear():
    """Overloaded Traveler (RAD-072): 'While there's a friendly gear with
    [Deploy] at my battlefield, I have +1 [Might].' It had no effect."""
    from riftbound.core.battlefield import DeployedGear
    loop, a, b = setup(active="A")
    traveler = unit("Overloaded Traveler")
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", traveler)
    bf1.gear_for("A").append(DeployedGear(card=card("Seal of Rage")))
    loop._recompute_passives()
    assert traveler.might == 2                           # the gear is elsewhere
    bf0.gear_for("A").append(DeployedGear(card=card("Seal of Rage")))
    loop._recompute_passives()
    assert traveler.might == 3


def test_harnessed_dragon_kills_only_an_enemy_unit():
    """Harnessed Dragon (OGN-234): 'When you play me, kill an enemy unit.'"""
    loop, a, b = setup(active="A")
    mine = unit("mine", 2)
    a.base_units.append(mine)
    a.hand.append(card("Harnessed Dragon"))
    act(loop, "A", "Play Harnessed Dragon")
    assert [u.card.name for u in a.base_units] == ["mine", "Harnessed Dragon"]


def test_carnivorous_snapvine_fights_an_enemy_unit_at_a_battlefield():
    """Carnivorous Snapvine (OGN-149): 'choose an enemy unit at a battlefield.'"""
    loop, a, b = setup(active="A")
    b.base_units.append(unit("home", 2))
    loop.gs.battlefields[0].add_unit("B", unit("out", 2))
    a.hand.append(card("Carnivorous Snapvine"))
    seen = choices(loop, {})
    act(loop, "A", "Play Carnivorous Snapvine")
    assert [opts for kind, _s, opts in seen if kind == "target:fight"] == [["out"]]


def test_lillia_protector_of_dreams_gains_might_for_the_turn():
    """Lillia, Protector of Dreams (UNL-058): 'When you play a token unit,
    give me +1 [Might] this turn.' It kept the Might for good."""
    loop, a, b = setup(active="A")
    lillia = unit("Lillia Protector of Dreams")
    a.base_units.append(lillia)
    a.base_gear.append(card("Long Sword"))
    a.hand.append(card("Arise!"))                        # one Sand Soldier token
    act(loop, "A", "Cast Arise!")
    assert lillia.might == 5
    lillia.clear_turn_end_bonuses()
    assert lillia.might == 4


def test_apprentice_mage_empowered_has_one_more_might():
    """Apprentice Mage (VEN-047): '[Empowered] I have +1 [Might].'"""
    loop, a, b = setup(active="A")
    mage = unit("Apprentice Mage")
    a.base_units.append(mage)
    a.deck.cards[:] = [card("Stacked Deck") for _ in range(4)]
    act(loop, "A", "Activate empower_self (Apprentice Mage")
    assert mage.might == 4


def test_elnuk_herd_can_give_its_might_to_itself():
    """Elnuk Herd (RAD-081, errata): 'give a friendly unit +3 [Might] this
    turn' (it read 'another friendly unit')."""
    loop, a, b = setup(active="A")
    a.hand.append(card("Elnuk Herd"))
    act(loop, "A", "Play Elnuk Herd")
    assert a.base_units[0].might == 8


def test_iridescent_avian_buffs_only_a_friendly_unit():
    """Iridescent Avian (RAD-027): '[Tap]: [Buff] a friendly unit.'"""
    loop, a, b = setup(active="A")
    a.base_units.append(unit("Iridescent Avian"))
    b.base_units.append(unit("enemy", 2))
    seen = choices(loop, {})
    act(loop, "A", "Activate buff_unit (Iridescent Avian")
    assert [opts for kind, _s, opts in seen if kind == "target:buff_unit"] == [["Iridescent Avian"]]


def test_meticulous_restorationist_is_paid_with_any_power():
    """Meticulous Restorationist (RAD-120): 'you may play me from your trash
    for [Rune]' (it asked for Order Power)."""
    from riftbound.core.enums import Domain
    loop, a, b = setup(active="A", rich=())
    a.energy = 7
    a.add_power(Domain.CHAOS, 2)
    a.trash.append(card("Meticulous Restorationist"))
    a.hand.append(card("Maduli the Gatekeeper"))         # Energy cost 7
    choices(loop, {"optional": lambda _l, options: options.index(True)})
    act(loop, "A", "Play Maduli")
    assert sorted(u.card.name for u in a.base_units) == ["Maduli the Gatekeeper", "Meticulous Restorationist"]


def test_blighted_battleaxe_is_equipped_for_any_power():
    """Blighted Battleaxe (UNL-019): '[Equip][1][Rune]' (it asked for Fury)."""
    from riftbound.core.enums import Domain
    loop, a, b = setup(active="A", rich=())
    a.energy = 1
    a.add_power(Domain.MIND, 1)
    a.base_units.append(unit("x", 2))
    a.base_gear.append(card("Blighted Battleaxe"))
    act(loop, "A", "Equip Blighted Battleaxe")
    assert a.base_units[0].might == 6


def test_reinforce_banishes_the_unit_it_plays():
    """Reinforce (OGN-062, errata): 'You may banish a unit from among them,
    then play it, reducing its cost by [5].' Zed, Master of Shadows: 'When you
    banish a card you own, empower me.'"""
    loop, a, b = setup(active="A")
    zed = legend(loop, "A", "Zed Master of Shadows")
    a.deck.cards[:] = [card("Maduli the Gatekeeper")]
    a.hand.append(card("Reinforce"))
    choices(loop, {"optional": lambda _l, options: options.index(True)})
    act(loop, "A", "Cast Reinforce")
    assert [u.card.name for u in a.base_units] == ["Maduli the Gatekeeper"] and zed.empowered


def test_mageseeker_investigator_is_paid_in_power():
    """Mageseeker Investigator (UNL-163): 'Opponents must pay [Rune] for each
    unit beyond the first to move multiple units to my battlefield at the same
    time.' It took Energy."""
    from riftbound.core.enums import Domain
    loop, a, b = setup(active="A", rich=())
    a.energy = 5
    loop.gs.battlefields[1].add_unit("B", unit("Mageseeker Investigator"))
    a.base_units.extend([unit("x", 2), unit("y", 2)])
    act(loop, "A", "Move x base→BF1")
    assert not [lb for lb in labels(loop, "A") if lb.startswith("Move y base→BF1")]
    a.add_power(Domain.BODY, 1)
    act(loop, "A", "Move y base→BF1")
    assert a.energy == 5 and not any(a.power_pool.values())
