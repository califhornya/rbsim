"""Rules audit, priority 1 (docs/audit/AUDIT.md): the rules the training precons
(precon_zed, precon_shen) play by. One test per deviation from
docs/rules/CORE_RULES.md, each playing the situation and checking what the
rules say."""

from __future__ import annotations

import copy

import pytest

from riftbound.core.cards import UnitCard
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions

from audit_helpers import act, card, choices, hide, labels, legend, scripted, setup, unit


# -- D1. BURN past the end of the Main Deck is a Burn Out ----------------------

@pytest.mark.xfail(strict=True, reason="§441.4 / §432.2: BURN with too few cards in the Main Deck "
                                       "stops at the empty deck: no Burn Out, no point, the rest not burned")
def test_burn_with_too_few_cards_burns_out():
    """Death Mark: 'BURN 3.' with one card left: burn it, Burn Out (the trash is
    recycled into the Main Deck, an opponent gains 1 point), burn two more."""
    loop, a, b = setup()
    a.deck.cards = [UnitCard(name="Last", might=1)]
    a.trash = [UnitCard(name=f"Old{i}", might=1) for i in range(4)]
    a.hand.append(card("Death Mark"))
    act(loop, "A", "Cast Death Mark")
    assert loop.gs.points_B == 1                 # §432.2.c
    assert len(a.deck.cards) == 3                # 5 recycled, 2 more burned (§432.2.d)
    assert len(a.trash) == 3                     # those 2, and Death Mark


@pytest.mark.xfail(strict=True, reason="§441.4 / §432.2: a player made to BURN with an empty Main "
                                       "Deck doesn't Burn Out (Blade Twirler: 'They BURN 1')")
def test_blade_twirler_burns_out_the_player_it_chooses():
    """'The first time I move each turn, choose a player. They BURN 1.'"""
    loop, a, b = setup()
    twirler = unit("Blade Twirler")
    loop.gs.battlefields[0].add_unit("A", twirler)
    b.trash = [UnitCard(name=f"Old{i}", might=1) for i in range(2)]
    seen = choices(loop, {"player": lambda l, o: [p.name for p in o].index("B")})
    act(loop, "A", "Move Blade Twirler BF0→base")
    assert any(kind == "player" for kind, _side, _opts in seen)      # the Twirler did ask
    assert loop.gs.points_A == 1                 # B burned out: its opponent gains 1 point
    assert len(b.deck.cards) == 1 and len(b.trash) == 1


# -- D2. The Chosen Champion is played like any unit ---------------------------

def _champion_board():
    loop, a, b = setup()
    loop.gs.champion_A = card("Shen Leader of the Kinkou Order")
    loop.gs.battlefields[0].add_unit("A", unit("Holder", 2))     # A controls battlefield 0
    return loop, a


@pytest.mark.xfail(strict=True, reason="§108.3.d / §355.2.a: the Chosen Champion can only be played "
                                       "to base, never to a battlefield its player controls")
def test_the_chosen_champion_can_be_played_to_a_battlefield_you_control():
    """'The Chosen Champion can be played from here as normal' (§108.3.d); a unit
    is played to 'the controller's Base or a Battlefield the controller
    controls' (§355.2.a)."""
    loop, a = _champion_board()
    n = len([ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if ga.kind == "CHAMPION"])
    landed = []
    for i in range(n):
        loop, a = _champion_board()
        ga = [g for g in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if g.kind == "CHAMPION"][i]
        loop._apply_action(a, ga.to_engine())
        where = [u.card.name for u in loop.gs.battlefields[0].units_A]
        landed.append("BF0" if "Shen Leader of the Kinkou Order" in where else "base")
    assert sorted(landed) == ["BF0", "base"]


# -- D3. A facedown card goes when its player loses the battlefield -------------

@pytest.mark.xfail(strict=True, reason="§323.6.a / §107.3.d: a facedown card stays until the end of "
                                       "the turn after its player lost control of the battlefield, and "
                                       "can still be played there")
def test_a_facedown_card_is_trashed_as_its_player_loses_the_battlefield():
    """Zed kills Shen's only unit at a battlefield in the Main Phase: Shen
    loses control in the next Cleanup (§323.5) and the card hidden there goes to
    its owner's trash in the same Cleanup (§323.6.a). Zed then moves in: Shen
    has nothing to play from facedown."""
    loop, a, b = setup(active="A")
    loop.gs.turn = 5
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("B", unit("Lone", 2))
    hidden = hide(loop, "B", 0, "Disciple of Shen")
    a.base_units.append(unit("Mover", 4))
    a.hand.append(card("Ruthless Strike"))
    A, B = scripted(loop, a, b, A={"main": ["Cast Ruthless Strike @BF0", "Move Mover base→BF0", "PASS"]})
    loop._run_main_actions()
    assert not any("from Hidden" in lbl for lbl in B.offered("showdown_action"))
    assert not bf0.facedowns and any(c is hidden for c in b.trash)


# -- D4. A Combat Cleanup heals all units ---------------------------------------

@pytest.mark.xfail(strict=True, reason="§468.1.a.1: the Combat Cleanup heals only the units that "
                                       "fought, not all units")
def test_a_combat_heals_the_units_everywhere():
    """'Invoke a Combat Special Cleanup. Insert "3c. Heal all Units."' Ruthless
    Strike deals 3 to a 5 [might] unit at one battlefield, then a combat ends at
    the other: the damage is healed, a second Ruthless Strike doesn't kill."""
    loop, a, b = setup(active="A")
    bf0, bf1 = loop.gs.battlefields
    far = unit("Far", 5)
    bf1.add_unit("B", far)
    bf0.add_unit("B", unit("Defender", 2))
    a.base_units.append(unit("Mover", 4))
    a.hand += [card("Ruthless Strike"), card("Ruthless Strike")]
    choices(loop, {"target": lambda l, o: next(i for i, u in enumerate(o) if u is far),
                   "optional:additional_cost": lambda l, o: o.index(False)})
    A, B = scripted(loop, a, b, A={"main": ["Cast Ruthless Strike @BF1", "Move Mover base→BF0", "PASS",
                                             "Cast Ruthless Strike @BF1"]})
    loop._run_main_actions()
    assert not bf0.units_B                       # the combat happened
    assert far in bf1.units_B and far.damage == 3


# -- D5. STUN ends with the turn, wherever the unit is --------------------------

@pytest.mark.xfail(strict=True, reason="§424.1.a.2: a stunned unit in a base stays stunned turn after "
                                       "turn (the status is only cleared from units at battlefields)")
def test_a_unit_stunned_in_its_base_is_no_longer_stunned_next_turn():
    """Kennen Keeper of Balance: 'When you play me ..., you may pay [2] to STUN
    a unit.' 'Stunned Units lose the Stunned status during step 3d of the end
    of turn cleanup.'"""
    loop, a, b = setup(active="B")
    sleeper = unit("Sleeper", 3)
    a.base_units.append(sleeper)
    a.deck.cards = [UnitCard(name=f"Deck{i}", might=1) for i in range(3)]
    b.hand.append(card("Kennen Keeper of Balance"))
    choices(loop, {"target": lambda l, o: next(i for i, u in enumerate(o) if u is sleeper)})
    act(loop, "B", "Play Kennen Keeper of Balance")
    assert sleeper.stunned
    loop._end_turn()
    loop._begin_turn()                           # A's turn
    assert not sleeper.stunned


# -- D6. The game ends when a player reaches the Victory Score ------------------

@pytest.mark.xfail(strict=True, reason="§323.1 / §194.2: the game goes on to the end of the turn "
                                       "after a player reached the Victory Score in the Main Phase")
def test_the_game_ends_as_soon_as_a_player_has_the_victory_score():
    """'If a player has points greater than or equal to the Victory Score, and
    more points than every opponent, that player wins' in the next Cleanup."""
    loop, a, b = setup(active="A")
    loop.gs.points_A = 7
    bf0, bf1 = loop.gs.battlefields
    bf1.add_unit("A", unit("Holder", 1))
    bf1.scored_this_turn_A = True                # every other battlefield scored: the Final Point
    a.base_units += [unit("Mover", 4), unit("Second", 4)]
    A, B = scripted(loop, a, b, A={"main": ["Move Mover base→BF0", "PASS", "Move Second base→BF0"]})
    result = loop._run_main_actions() or loop._end_turn()
    assert loop.gs.points_A == 8 and result is not None and result.winner == "A"
    # Asked for the move and for the end of the move, never again.
    assert len([p for p, _ in A.log if p == "turn_action"]) == 2


@pytest.mark.xfail(strict=True, reason="§323.1 / §432.2.c: a point that takes a player to the Victory "
                                       "Score outside scoring (a Burn Out in the Draw Phase) doesn't "
                                       "end the game: the turn is played on and the other may still win")
def test_a_burn_out_that_gives_the_last_point_ends_the_game():
    loop, a, b = setup(active="A")
    loop.gs.points_B = 7                         # A's Main Deck and trash are empty
    result = loop._begin_turn()
    assert loop.gs.points_B == 8
    assert result is not None and result.winner == "B"


# -- D7. An Equipment outlives the unit it is attached to -----------------------

@pytest.mark.xfail(strict=True, reason="§719.5 / §436.4.b: an Equipment goes to the trash when the "
                                       "unit it is attached to is banished")
def test_an_equipment_stays_when_its_unit_is_banished():
    """Wind and Ghosts: 'Choose a unit at a battlefield. If it has 3 [might] or
    less, banish it.' 'When a Top-Most Card changes zones from a board zone to a
    non-board zone, all Attached cards Detach from it, remaining in their
    current zones': the Hand Hammer is recalled to its controller's base."""
    loop, a, b = setup(active="A")
    holder = unit("Holder", 1)
    hammer = card("Hand Hammer")
    holder.gear.append(hammer)
    loop.gs.battlefields[0].add_unit("B", holder)
    a.hand.append(card("Wind and Ghosts"))
    act(loop, "A", "Cast Wind and Ghosts @BF0")
    assert [c.name for c in b.banished] == ["Holder"]
    assert any(g is hammer for g in b.base_gear) and not any(c is hammer for c in b.trash)


# -- D8. A unit played from facedown chooses at its battlefield ------------------

@pytest.mark.xfail(strict=True, reason="§811.1.d.3: the play effect of a unit played from facedown in "
                                       "its player's Main Phase chooses among units anywhere")
def test_a_unit_played_from_facedown_in_the_main_phase_chooses_at_its_battlefield():
    """Kennen Keeper of Balance hidden, then played: 'If a play effect of a
    hidden permanent chooses any targets, those targets must be chosen from
    among options at the battlefield it was played to.'"""
    loop, a, b = setup(active="A")
    loop.gs.turn = 5
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", unit("Holder", 2))
    bf1.add_unit("B", unit("Elsewhere", 3))
    b.base_units.append(unit("In Base", 3))
    hide(loop, "A", 0, "Kennen Keeper of Balance")
    seen = choices(loop, {})
    act(loop, "A", "Play Kennen Keeper of Balance from Hidden")
    stun = [opts for kind, _side, opts in seen if kind == "target:stun_unit"]
    assert stun and all(set(opts) <= {"Holder", "Kennen Keeper of Balance"} for opts in stun)


# -- D9. An activated ability needs a legal choice for its target ----------------

@pytest.mark.xfail(strict=True, reason="§403.3 / §355.8: an activated ability can be activated (its "
                                       "cost paid) with no legal target")
def test_shen_eye_of_twilight_needs_a_friendly_unit():
    """'ACTION [tap]: Give a friendly unit TANK this turn.' 'If legal options
    are not available for an Activated Ability, it is not legal to activate it.'"""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Shen Eye of Twilight")
    assert not any("Shen Eye of Twilight" in lbl for lbl in labels(loop, "A"))
    a.base_units.append(unit("Friend", 2))
    assert any("Shen Eye of Twilight" in lbl for lbl in labels(loop, "A"))


@pytest.mark.xfail(strict=True, reason="§403.3 / §355.4.a: Zed Without a Sound's swap can be paid for "
                                       "with no Shadow Clone at another location (nothing moves)")
def test_zed_without_a_sound_needs_a_shadow_clone_somewhere_else():
    """'ACTION [1] [Chaos]: Move me and a Shadow Clone you control to each
    other's locations.' 'A valid Location for a Move Effect is one other than
    the Units' current Location.'"""
    loop, a, b = setup(active="A")
    a.base_units += [unit("Zed Without a Sound"), unit("Shadow Clone", is_token=True)]
    assert not any("Zed Without a Sound" in lbl and "Activate" in lbl for lbl in labels(loop, "A"))


# -- D10. A REACTION unit may be played to base too ------------------------------

@pytest.mark.xfail(strict=True, reason="§813.1.c.1 / §813.3.a: a REACTION unit can be played at "
                                       "reaction speed only to a battlefield its player controls, "
                                       "not to their base")
def test_a_reaction_unit_can_be_played_to_base_in_a_closed_state():
    """Shen Kinkou: 'REACTION (Play any time, ..., including to a battlefield
    you control.)' 'It can only be played to the controlling player's base or a
    battlefield they control.'"""
    loop, a, b = setup(active="B")
    a.hand.append(card("Shen Kinkou"))           # A controls no battlefield
    b.base_units.append(unit("Target", 1))
    b.hand.append(card("Discipline"))
    A, B = scripted(loop, a, b, B={"main": ["Cast Discipline"]})
    loop._run_main_actions()
    assert "Pass" in A.offered("reaction")       # A did get priority on the chain
    assert any("Shen Kinkou" in lbl for lbl in A.offered("reaction"))


@pytest.mark.xfail(strict=True, reason="§813.1.b / §806.1.c.1: a REACTION unit isn't offered during a "
                                       "showdown unless its player controls the showdown's battlefield")
def test_a_reaction_unit_can_be_played_to_base_during_a_showdown():
    loop, a, b = setup(active="B")
    a.hand.append(card("Shen Kinkou"))
    b.base_units.append(unit("Mover", 2))
    A, B = scripted(loop, a, b, B={"main": ["Move Mover base→BF0", "PASS"]})
    loop._run_main_actions()                     # a showdown at the open battlefield 0
    assert "Pass" in A.offered("showdown_action")
    assert any("Shen Kinkou" in lbl for lbl in A.offered("showdown_action"))


# -- D11. REACTION plays during a showdown aren't tied to its battlefield --------

@pytest.mark.xfail(strict=True, reason="§822.1.b / §811.6: during a showdown an AMBUSH unit and a "
                                       "facedown card can be played only at the showdown's battlefield")
def test_ambush_and_facedown_plays_at_another_battlefield_during_a_showdown():
    """AMBUSH: 'I have [Reaction] as long as I'm being played to a battlefield
    where you control Units.' A facedown card 'may be played any time a card
    with Reaction may be played.'"""
    loop, a, b = setup(active="A")
    loop.gs.turn = 5
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("B", unit("Defender", 2))
    bf1.add_unit("B", unit("Elsewhere", 2))
    hide(loop, "B", 1, "Disciple of Shen")
    b.hand.append(card("Soulspinner"))
    a.base_units.append(unit("Mover", 3))
    A, B = scripted(loop, a, b, A={"main": ["Move Mover base→BF0", "PASS"]})
    loop._run_main_actions()
    offered = B.offered("showdown_action")
    assert any("Soulspinner" in lbl and "BF0" in lbl for lbl in offered)     # here it can
    assert any("Soulspinner" in lbl and "BF1" in lbl for lbl in offered)
    assert any("from Hidden" in lbl and "BF1" in lbl for lbl in offered)
