"""Restrictions: "can't be chosen by enemy spells and abilities", "can't move
to base", "I can't be readied", "opponents can't play cards this turn", "I
can't be played on your first three turns", a named spell, "opponents can't
gain points", "can't score here until their third turn", Otterpus, "you win
the game", Sandstone Chimera, Aspirant's Climb."""

from __future__ import annotations

import random
from pathlib import Path

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _real(name):
    return UnitInPlay(card=CARD_REGISTRY[name].instantiate())


def _u(name, might):
    return UnitInPlay(card=UnitCard(name=name, might=might))


def _ctx(loop, side="A"):
    me, them = loop.gs.get_player(side), loop.gs.get_player(loop.gs.other(side))
    return EffectContext(loop, SpellCard(name="S"), me, them, loop.gs.battlefields[0], {})


def test_ruin_runner_cant_be_chosen_by_enemy_spells():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    runner, other = _real("Ruin Runner"), _u("Other", 2)
    bf0.add_unit("B", runner)
    bf0.add_unit("B", other)
    loop._recompute_passives()
    REGISTRY["kill_unit"](_ctx(loop), {"target": "enemy_unit"})
    assert runner in bf0.units_B and other not in bf0.units_B
    REGISTRY["deal_damage"](_ctx(loop), {"target": "enemy_unit", "amount": 9})
    assert runner in bf0.units_B
    REGISTRY["deal_damage"](_ctx(loop), {"target": "all_enemy_units_here", "amount": 9})
    assert runner not in bf0.units_B                         # "all" doesn't choose


def test_alpha_wildclaw_shields_weaker_units_here():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.add_unit("B", _real("Alpha Wildclaw"))
    weak = _u("Weak", 2)
    bf0.add_unit("B", weak)
    loop._recompute_passives()
    assert not loop._can_choose(weak, "A") and loop._can_choose(weak, "B")


def test_twilight_shroud_protects_for_the_turn():
    loop = _loop()
    unit = _u("U", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    loop._resolve_card_effects(CARD_REGISTRY["Twilight Shroud"].instantiate(),
                               loop.gs.battlefields[0], loop.gs.A, loop.gs.B)
    assert unit.might == 3 and not loop._can_choose(unit, "B")
    loop.gs.turn += 1
    assert loop._can_choose(unit, "B")


def test_units_cant_move_to_base():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    sentry, free = _real("Determined Sentry"), _u("Free", 2)
    bf0.add_unit("A", sentry)
    bf0.add_unit("A", free)
    loop._recompute_passives()
    assert not loop._move_unit_by_effect(sentry, None)
    assert loop._move_unit_by_effect(free, None)
    bf1.add_unit("B", _real("Minotaur Reckoner"))
    loop._recompute_passives()
    assert loop._move_unit_by_effect(free, bf0)              # from base: fine
    assert not loop._move_unit_by_effect(free, None)         # "Units can't move to base"


def test_vilemaws_lair_holds_units_here():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = CARD_REGISTRY["Vilemaw's Lair"].instantiate()
    unit = _u("U", 2)
    bf0.add_unit("A", unit)
    assert not loop._move_unit_by_effect(unit, None)
    assert loop._move_unit_by_effect(unit, loop.gs.battlefields[1]) is True


def test_maduli_cant_be_readied():
    loop = _loop()
    maduli = _real("Maduli the Gatekeeper")
    maduli.ready = False
    loop.gs.A.base_units.append(maduli)
    loop._recompute_passives()
    REGISTRY["ready_unit"](_ctx(loop), {"target": "friendly_unit"})
    loop._ready_active_units("A")
    assert not maduli.ready


def test_brynhir_stops_the_opponent_playing_cards_this_turn():
    loop = _loop()
    loop._resolve_triggered_effects(CARD_REGISTRY["Brynhir Thundersong"].instantiate(), "on_play",
                                    loop.gs.battlefields[0], loop.gs.A, loop.gs.B,
                                    context_extra={"battlefield": loop.gs.battlefields[0]})
    cheap = UnitCard(name="Free", cost_energy=0)
    assert not loop._can_pay_card(loop.gs.B, cheap, 0, 0)
    assert loop._can_pay_card(loop.gs.A, cheap, 0, 0)
    loop.gs.turn += 1
    assert loop._can_pay_card(loop.gs.B, cheap, 0, 0)


def test_ol_poro_waits_for_your_fourth_turn():
    loop = _loop()
    poro = CARD_REGISTRY["Ol' Poro"].instantiate()
    loop.gs.turns_taken["A"] = 3
    assert not loop._can_pay_card(loop.gs.A, poro, 0, 0)
    loop.gs.turns_taken["A"] = 4
    assert loop._can_pay_card(loop.gs.A, poro, 0, 0)


def test_fallen_feline_names_a_spell_from_the_opponents_trash():
    loop = _loop()
    loop.gs.B.trash = [SpellCard(name="Bolt", cost_energy=1), SpellCard(name="Nuke", cost_energy=6)]
    feline = _real("Fallen Feline")
    loop.gs.battlefields[0].add_unit("A", feline)
    loop._resolve_triggered_effects(feline.card, "on_play", loop.gs.battlefields[0], loop.gs.A,
                                    loop.gs.B, context_extra={"battlefield": loop.gs.battlefields[0]})
    assert not loop._can_pay_card(loop.gs.B, SpellCard(name="Nuke"), 0, 0)
    assert loop._can_pay_card(loop.gs.B, SpellCard(name="Bolt"), 0, 0)


def test_tianna_stops_opponents_scoring():
    loop = _loop()
    loop.gs.battlefields[0].add_unit("B", _real("Tianna Crownguard"))
    REGISTRY["score_point"](_ctx(loop), {"amount": 1})
    assert loop.gs.points_A == 0
    REGISTRY["score_point"](_ctx(loop, "B"), {"amount": 1})
    assert loop.gs.points_B == 1


def test_forgotten_monument_and_otterpus():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = CARD_REGISTRY["Forgotten Monument"].instantiate()
    loop.gs.turns_taken["A"] = 2
    assert loop._gain_points("A", 1, "conquer", bf0) == 0
    loop.gs.turns_taken["A"] = 3
    assert loop._gain_points("A", 1, "conquer", bf0) == 1
    loop.gs.battlefields[1].add_unit("B", _real("Otterpus"))
    loop.gs.turns_taken["B"] = 2
    hand = len(loop.gs.B.hand)
    assert loop._gain_points("B", 1, "hold", loop.gs.battlefields[1]) == 0
    assert len(loop.gs.B.hand) == hand + 1


def test_the_grand_plaza_wins_with_seven_units():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = CARD_REGISTRY["The Grand Plaza"].instantiate()
    for i in range(7):
        bf0.add_unit("A", _u(f"U{i}", 1))
    loop._fire_scoring_trigger("on_hold", bf0, "A")
    assert loop.gs.points_A >= loop.gs.victory_score


def test_sandstone_chimera_channels_one_rune():
    from riftbound.core.enums import Domain
    from riftbound.core.player import Rune
    loop = _loop()
    loop.gs.A.rune_deck = RuneDeck([Rune(domain=Domain.FURY) for _ in range(6)])
    loop.gs.battlefields[0].add_unit("B", _real("Sandstone Chimera"))
    loop.gs.turn = 5
    loop._phase_beginning("A")
    assert len(loop.gs.A.rune_deck.runes) == 5


def test_aspirants_climb_raises_the_victory_score():
    from riftbound.core.game_factory import build_game
    import riftbound.core.game_factory as gf
    decks = sorted(Path("riftbound/data/decks").glob("*.json"))
    orig = gf._select_battlefield
    climb = CARD_REGISTRY["Aspirant's Climb"].instantiate()
    gf._select_battlefield = lambda bfs, pick, rng: climb
    try:
        gs = build_game(game_seed=1, deck_a_path=decks[0], deck_b_path=decks[1], ai_a=None, ai_b=None)
    finally:
        gf._select_battlefield = orig
    assert gs.victory_score == 10
