"""Where units are played: a unit goes to its controller's base or a
battlefield they control (§813.3.a); cards widen that (an open battlefield,
an occupied enemy one, one where an enemy is alone, any after Last Caress) or
narrow it (Perched Grimwyrm, Rockfall Path, Mageseeker Warden). Playing to a
battlefield contests it like a move. AMBUSH and REACTION units at reaction
speed; Here to Help; Valley of Idols; the RL action slots."""

from __future__ import annotations

import random

from riftbound.ai.encoding import N_BF, action_to_index
from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint, GameAction
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _u(name, might=2):
    return UnitInPlay(card=UnitCard(name=name, might=might))


def test_units_go_to_base_or_a_battlefield_you_control():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", _u("Holder"))
    card = UnitCard(name="New", cost_energy=0)
    assert loop._unit_play_destinations(card, "A") == [None, 0]
    loop.gs.A.hand = [card]
    loop._apply_action(loop.gs.A, ("UNIT", 0, 0, 0))
    assert [u.card for u in bf0.units_A][-1] is card


def test_open_and_occupied_enemy_permissions():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf1.add_unit("B", _u("Enemy"))
    assert loop._unit_play_destinations(_card("Sneaky Deckhand"), "A") == [None, 0]
    assert loop._unit_play_destinations(_card("Dauntless Vanguard"), "A") == [None, 1]


def test_playing_to_an_enemy_battlefield_starts_the_fight():
    loop = _loop()
    bf1 = loop.gs.battlefields[1]
    bf1.add_unit("B", _u("Enemy", 1))
    vanguard = _card("Dauntless Vanguard")
    vanguard.cost_energy, vanguard.cost_power = 0, None
    loop.gs.A.hand = [vanguard]
    loop._apply_action(loop.gs.A, ("UNIT", 0, 0, 1))
    # The showdown starts as soon as the play is done (§323.11): nothing joins it.
    assert bf1.contested_this_turn and loop.gs.pending_move is None
    assert not bf1.units_B and [u.card for u in bf1.units_A] == [vanguard]


def test_miss_fortune_buccaneer_lets_friendly_units_take_open_battlefields():
    loop = _loop()
    loop.gs.A.base_units.append(UnitInPlay(card=_card("Miss Fortune Buccaneer")))
    assert loop._unit_play_destinations(UnitCard(name="Any"), "A") == [None, 0, 1]
    assert loop._unit_play_destinations(UnitCard(name="Any"), "B") == [None]


def test_perched_grimwyrm_only_where_you_conquered_this_turn():
    loop = _loop()
    grim = _card("Perched Grimwyrm")
    assert loop._unit_play_destinations(grim, "A") == []
    loop.gs.battlefields[1].conquered_turn["A"] = loop.gs.turn
    assert loop._unit_play_destinations(grim, "A") == [1]


def test_rockfall_path_and_mageseeker_warden_block_battlefield_plays():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", _u("Mine"))
    bf1.add_unit("A", _u("Mine2"))
    bf0.card = _card("Rockfall Path")
    assert loop._unit_play_destinations(UnitCard(name="X"), "A") == [None, 1]
    loop.gs.battlefields[1].add_unit("B", UnitInPlay(card=_card("Mageseeker Warden")))
    assert loop._unit_play_destinations(UnitCard(name="X"), "A") == [None]


def test_last_caress_sends_the_next_unit_anywhere_buffed():
    loop = _loop()
    loop._resolve_card_effects(_card("Last Caress"), loop.gs.battlefields[0], loop.gs.A, loop.gs.B)
    card = UnitCard(name="Next")
    assert loop._unit_play_destinations(card, "A") == [None, 0, 1]
    unit = loop._play_unit(card, "A", bf=loop.gs.battlefields[1])
    assert unit.might_counters == 1
    assert loop._unit_play_destinations(UnitCard(name="After"), "A") == [None, 1]   # used up; BF1 is ours


def test_ambush_units_are_offered_at_reaction_speed():
    loop = _loop()
    loop.gs.battlefields[1].add_unit("B", _u("Mine"))
    ambusher = next(CARD_REGISTRY[n].instantiate() for n in CARD_REGISTRY
                    if "AMBUSH" in CARD_REGISTRY[n].keywords and CARD_REGISTRY[n].category.name == "UNIT")
    ambusher.cost_energy, ambusher.cost_power = 0, None
    loop.gs.B.hand = [ambusher]
    acts = [a for a in legal_actions(loop, DecisionPoint.REACTION, "B") if a.kind == "UNIT"]
    assert [a.dst_lane for a in acts] == [1]
    assert loop._play_ambush_unit(loop.gs.B, 0, 1)
    assert any(u.card is ambusher for u in loop.gs.battlefields[1].units_B)


def test_here_to_help_plays_a_unit_to_your_battlefield_three_cheaper():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("A", _u("Holder"))
    big = UnitCard(name="Big", might=5, cost_energy=4)
    loop.gs.A.hand = [big]
    loop.gs.A.energy = 1
    loop._resolve_card_effects(_card("Here to Help"), bf0, loop.gs.A, loop.gs.B)
    assert any(u.card is big for u in bf0.units_A) and loop.gs.A.energy == 0


def test_valley_of_idols_buffs_a_unit_played_there():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Valley of Idols")
    bf0.add_unit("A", _u("Holder"))
    card = UnitCard(name="New", cost_energy=0)
    loop.gs.A.hand = [card]
    loop.gs.A.energy = 1
    loop._apply_action(loop.gs.A, ("UNIT", 0, 0, 0))
    unit = next(u for u in bf0.units_A if u.card is card)
    assert unit.might_counters == 1 and loop.gs.A.energy == 0


def test_unit_destinations_have_their_own_action_slots():
    base = action_to_index(GameAction.play("UNIT", 2, 0, ""))
    there = [action_to_index(GameAction("UNIT", 2, 0, d, "")) for d in range(N_BF)]
    assert len({base, *there}) == N_BF + 1
