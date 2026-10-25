"""Batch of one-line cards and the triggers they needed: board-wide targets
(Grand Strategem, Avalanche), legends hearing "when you ..." (Draven),
DEATHKNELL "if I was MIGHTY" and twice (Unsung Hero, Karthus), "when an enemy
unit here dies" (Nasus), "when you discard me" (Flame Chompers), Fanfare,
Mushroom Pouch, Downwell, Cataclysmic Duel, Keeper's Verdict, Ephemeral Ward."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, FacedownCard
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(6)]),
               rune_deck=RuneDeck([Rune(domain=Domain.FURY) for _ in range(4)]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(6)]),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _u(name, might, side_list=None):
    return UnitInPlay(card=UnitCard(name=name, might=might))


def _real(name):
    return UnitInPlay(card=CARD_REGISTRY[name].instantiate())


def _cast(loop, name):
    loop._resolve_card_effects(CARD_REGISTRY[name].instantiate(), loop.gs.battlefields[0],
                               loop.gs.A, loop.gs.B)


def _kill(loop, unit):
    where = loop._locate_unit(unit)
    ctx = EffectContext(loop, SpellCard(name="Zap"), loop.gs.get_player(loop.gs.other(where[0])),
                        loop.gs.get_player(where[0]), where[1] or loop.gs.battlefields[0], {})
    ctx.damage_units([unit], 99)


def test_grand_strategem_pumps_friendly_units_everywhere():
    loop = _loop()
    here, there, home = _u("H", 1), _u("T", 1), _u("B", 1)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    loop.gs.A.base_units.append(home)
    enemy = _u("E", 1)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _cast(loop, "Grand Strategem")
    assert [u.might for u in (here, there, home, enemy)] == [6, 6, 6, 1]


def test_avalanche_hits_only_units_in_bases():
    loop = _loop()
    mine, theirs, out = _u("M", 5), _u("T", 2), _u("O", 1)
    loop.gs.A.base_units.append(mine)
    loop.gs.B.base_units.append(theirs)
    loop.gs.battlefields[0].add_unit("B", out)
    _cast(loop, "Avalanche")
    assert mine.damage == 3 and theirs not in loop.gs.B.base_units and out.damage == 0


def test_draven_legend_draws_when_you_win_a_combat():
    loop = _loop()
    loop.gs.legend_unit_A = _real("Draven Glorious Executioner")
    loop._fire_units_trigger("on_win_combat", "A")
    assert len(loop.gs.A.hand) == 1


def test_unsung_hero_draws_two_only_if_it_died_mighty_and_karthus_doubles_it():
    loop = _loop()
    hero = _real("Unsung Hero")
    loop.gs.battlefields[0].add_unit("A", hero)
    _kill(loop, hero)
    assert len(loop.gs.A.hand) == 0
    hero = _real("Unsung Hero")
    hero.temporary_might = 3
    loop.gs.battlefields[0].add_unit("A", hero)
    _kill(loop, hero)
    assert len(loop.gs.A.hand) == 2
    loop.gs.A.base_units.append(_real("Karthus Eternal"))
    hero = _real("Unsung Hero")
    hero.temporary_might = 3
    loop.gs.battlefields[0].add_unit("A", hero)
    _kill(loop, hero)
    assert len(loop.gs.A.hand) == 6


def test_nasus_channels_once_per_turn_when_an_enemy_dies_here():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", _real("Nasus Guardian of Knowledge"))
    far, near1, near2 = _u("Far", 1), _u("N1", 1), _u("N2", 1)
    bf1.add_unit("B", far)
    bf0.add_unit("B", near1)
    bf0.add_unit("B", near2)
    runes = len(loop.gs.A.rune_deck.runes)
    _kill(loop, far)
    assert len(loop.gs.A.rune_deck.runes) == runes
    _kill(loop, near1)
    _kill(loop, near2)
    assert len(loop.gs.A.rune_deck.runes) == runes - 1


def test_flame_chompers_plays_itself_when_discarded():
    loop = _loop()
    ap = loop.gs.A
    chompers = CARD_REGISTRY["Flame Chompers"].instantiate()
    ap.hand = [chompers]
    ap.add_power(Domain.FURY, 1)
    ctx = EffectContext(loop, SpellCard(name="S"), ap, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["discard_card"](ctx, {"count": 1})
    assert [u.card for u in ap.base_units] == [chompers] and chompers not in ap.trash


def test_fanfare_draws_on_the_next_three_unit_plays():
    loop = _loop()
    _cast(loop, "Fanfare")
    for i in range(4):
        loop._play_unit(UnitCard(name=f"U{i}"), "A")
    assert len(loop.gs.A.hand) == 3


def test_mushroom_pouch_draws_with_a_facedown_card():
    loop = _loop()
    pouch = CARD_REGISTRY["Mushroom Pouch"].instantiate()
    loop.gs.A.base_gear.append(pouch)
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert len(loop.gs.A.hand) == 0
    loop.gs.battlefields[1].facedown = FacedownCard(card=SpellCard(name="Hidden"), owner="A", turn_hidden=0)
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert len(loop.gs.A.hand) == 1


def test_downwell_returns_units_and_gear_to_hands_and_tokens_vanish():
    loop = _loop()
    unit = _u("U", 3)
    unit.gear = [GearCard(name="Sword")]
    token = _real("Recruit")
    token.is_token = True
    loop.gs.battlefields[0].add_unit("A", unit)
    loop.gs.battlefields[0].add_unit("A", token)
    loop.gs.B.base_gear.append(GearCard(name="Relic"))
    _cast(loop, "Downwell")
    assert sorted(c.name for c in loop.gs.A.hand) == ["Sword", "U"]
    assert [c.name for c in loop.gs.B.hand] == ["Relic"]
    assert not loop.gs.battlefields[0].units_A


def test_cataclysmic_duel_keeps_each_players_mightiest():
    loop = _loop()
    a1, a2, b1, b2 = _u("a1", 2), _u("a2", 5), _u("b1", 4), _u("b2", 1)
    loop.gs.battlefields[0].add_unit("A", a1)
    loop.gs.A.base_units.append(a2)
    loop.gs.battlefields[1].add_unit("B", b1)
    loop.gs.battlefields[1].add_unit("B", b2)
    _cast(loop, "Cataclysmic Duel")
    assert loop.gs.A.base_units == [a2] and not loop.gs.battlefields[0].units_A
    assert loop.gs.battlefields[1].units_B == [b1]


def test_keepers_verdict_puts_the_mightiest_enemy_on_top_of_its_deck():
    loop = _loop()
    big = _u("Big", 6)
    loop.gs.battlefields[1].add_unit("B", big)
    loop.gs.battlefields[1].add_unit("B", _u("Small", 1))
    _cast(loop, "Keeper's Verdict")
    assert loop.gs.B.deck.cards[-1] is big.card


def test_ephemeral_ward_gives_two_until_you_play_a_unit():
    loop = _loop()
    ward = CARD_REGISTRY["Ephemeral Ward"].instantiate()
    loop.gs.A.base_gear.append(ward)
    unit = _u("U", 2)
    loop.gs.battlefields[0].add_unit("A", unit)
    loop._recompute_passives()
    assert unit.might == 4
    loop._play_unit(UnitCard(name="New"), "A")
    loop._recompute_passives()
    assert ward in loop.gs.A.trash and unit.might == 2
