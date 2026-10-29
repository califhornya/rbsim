"""Void Hatchling (BACKLOG E): "If you would reveal cards from a deck, look at
the top card first. You may recycle it. Then reveal those cards." A
replacement on every reveal its controller makes (GameLoop._before_deck_reveal),
once per Hatchling (§370.2); looks ("look at the top 3") aren't reveals."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.player import Rune

from test_corpus_cards import _cast_now, _deck, _setup, _unit
from test_corpus_vendetta import _ctx, _equip
from test_corpus_radiance import _card
from test_green_father import _answer


def _hatchling(p):
    unit = _unit("Void Hatchling")
    p.base_units.append(unit)
    return unit


def _witness_moves(loop, p):
    """Raving Witness: 'When I move, reveal the top card of your Main Deck. If
    it's MIGHTY, draw it. Otherwise, recycle it.'"""
    witness = _unit("Raving Witness")
    p.base_units.append(witness)
    loop._move_unit_by_effect(witness, loop.gs.battlefields[0])


def _names(cards):
    return [c.name for c in cards]


def test_it_recycles_a_miss_so_the_reveal_finds_the_next_card():
    loop, a, b = _setup()
    _hatchling(a)
    _deck(a, SpellCard(name="Miss"), UnitCard(name="Big", might=6), SpellCard(name="Bottom"))
    _witness_moves(loop, a)
    assert _names(a.hand) == ["Big"]
    assert _names(reversed(a.deck.cards)) == ["Bottom", "Miss"]


def test_without_it_the_miss_is_revealed():
    loop, a, b = _setup()
    _deck(a, SpellCard(name="Miss"), UnitCard(name="Big", might=6))
    _witness_moves(loop, a)
    assert a.hand == [] and _names(reversed(a.deck.cards)) == ["Big", "Miss"]


def test_a_hit_on_top_is_kept():
    loop, a, b = _setup()
    _hatchling(a)
    _deck(a, UnitCard(name="Big", might=6), SpellCard(name="Miss"))
    _witness_moves(loop, a)
    assert _names(a.hand) == ["Big"]


def test_declining_reveals_the_top_card():
    """Pakaa Protector: 'If it's a unit, draw it. Otherwise, put it in your
    trash and give me +2 [might] this turn.'"""
    loop, a, b = _setup()
    _hatchling(a)
    _answer(loop, "optional:recycle", False)
    _deck(a, SpellCard(name="Miss"), UnitCard(name="Next", might=1))
    pakaa = _unit("Pakaa Protector")
    a.base_units.append(pakaa)
    loop._move_unit_by_effect(pakaa, loop.gs.battlefields[0])
    assert _names(a.trash) == ["Miss"] and a.hand == []


def test_only_its_controllers_reveals():
    loop, a, b = _setup()
    _hatchling(b)
    _deck(a, SpellCard(name="Miss"), UnitCard(name="Big", might=6))
    _witness_moves(loop, a)
    assert a.hand == []


def test_two_hatchlings_look_twice():
    loop, a, b = _setup()
    _hatchling(a)
    _hatchling(a)
    _deck(a, SpellCard(name="Miss1"), SpellCard(name="Miss2"), UnitCard(name="Big", might=6),
          SpellCard(name="Bottom"))
    _witness_moves(loop, a)
    assert _names(a.hand) == ["Big"]


def test_svellsongur_copies_it():
    loop, a, b = _setup()
    _equip(_hatchling(a), "Svellsongur")
    _deck(a, SpellCard(name="Miss1"), SpellCard(name="Miss2"), UnitCard(name="Big", might=6),
          SpellCard(name="Bottom"))
    _witness_moves(loop, a)
    assert _names(a.hand) == ["Big"]


def test_a_look_is_not_a_reveal():
    """Fate Weaver 'look at the top 4 cards ... You may reveal a spell': no
    Hatchling look."""
    loop, a, b = _setup()
    _hatchling(a)
    asked = []
    loop.chooser = lambda _l, kind, *rest: asked.append(kind)
    _deck(a, *[SpellCard(name=f"S{i}") for i in range(5)])
    loop._play_unit(_card("Fate Weaver"), "A")
    assert "optional:recycle" not in asked


def test_nocturne_seen_by_its_look_may_be_played():
    """'As you look at or reveal me from the top of your deck, you may banish
    me. If you do, you may play me for [rune].'"""
    loop, a, b = _setup()
    _hatchling(a)
    _deck(a, _card("Nocturne Horrifying"), SpellCard(name="Miss"), UnitCard(name="Big", might=6))
    _witness_moves(loop, a)
    assert any(u.card.name == "Nocturne Horrifying" for u in a.base_units)


def test_drakehound_looks_at_the_opponents_top_card():
    """'Reveal the top card of each opponent's Main Deck. Choose one and banish
    it, then play it, ignoring its cost.' You reveal: your Hatchling."""
    loop, a, b = _setup()
    _hatchling(a)
    _deck(b, UnitCard(name="Cheap", might=1, cost_energy=1), UnitCard(name="Ogre", might=6, cost_energy=7),
          UnitCard(name="Mid", might=3, cost_energy=3))
    loop._play_unit(_card("Drakehound Packmaster"), "A")
    assert any(u.card.name == "Ogre" for u in a.base_units)
    assert _names(reversed(b.deck.cards)) == ["Mid", "Cheap"]


def test_blind_fury_is_revealed_by_the_opponent():
    """'Each opponent reveals the top card of their Main Deck': their
    Hatchling, which keeps a good card from you; yours doesn't apply."""
    loop, a, b = _setup()
    _hatchling(b)
    _deck(b, UnitCard(name="Ogre", might=6, cost_energy=7), UnitCard(name="Cheap", might=1, cost_energy=1),
          UnitCard(name="Mid", might=3, cost_energy=3))
    _cast_now(loop, a, "Blind Fury")
    assert any(u.card.name == "Cheap" for u in a.base_units)

    loop, a, b = _setup()
    _hatchling(a)
    _deck(b, UnitCard(name="Cheap", might=1, cost_energy=1), UnitCard(name="Ogre", might=6, cost_energy=7))
    _cast_now(loop, a, "Blind Fury")
    assert any(u.card.name == "Cheap" for u in a.base_units)


def test_twisted_fate_looks_at_the_top_rune():
    """'Reveal the top rune of your rune deck, then recycle it. ... [mind] -
    Draw 1.' A rune deck is a deck."""
    loop, a, b = _setup()
    _hatchling(a)
    a.rune_deck.runes = [Rune(domain=Domain.CALM), Rune(domain=Domain.MIND), Rune(domain=Domain.BODY)]
    _deck(a, SpellCard(name="Card"))
    REGISTRY["twisted_fate_reveal"](_ctx(loop, a), {})
    assert _names(a.hand) == ["Card"]
    assert [r.domain for r in a.rune_deck.runes] == [Domain.BODY, Domain.CALM, Domain.MIND]


def test_scrutinizing_scope_looks_for_another_type():
    """They guess unit (baseline); 'If it has that type, recycle it.
    Otherwise, draw it.'"""
    loop, a, b = _setup()
    _hatchling(a)
    _deck(a, UnitCard(name="Unit"), SpellCard(name="Spell"))
    REGISTRY["guess_type_draw"](_ctx(loop, a), {})
    assert _names(a.hand) == ["Spell"]


def test_teemo_strategist_looks_for_hidden():
    loop, a, b = _setup()
    _hatchling(a)
    enemy = _unit("Enemy", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    plain = [SpellCard(name=f"P{i}") for i in range(5)]
    _deck(a, *plain, _card("Teemo Strategist"))
    REGISTRY["teemo_reveal_damage"](_ctx(loop, a), {})
    assert enemy.damage == 1


def test_apprentice_smith_reveals_and_draws_a_gear():
    """'When I move, reveal the top card of your Main Deck. If it's a gear,
    draw it. Otherwise, recycle it.'"""
    loop, a, b = _setup()
    _deck(a, _card("Svellsongur"), SpellCard(name="Next"))
    smith = _unit("Apprentice Smith")
    a.base_units.append(smith)
    loop._move_unit_by_effect(smith, loop.gs.battlefields[0])
    assert _names(a.hand) == ["Svellsongur"]
    loop._move_unit_by_effect(smith, loop.gs.battlefields[1])
    assert _names(a.hand) == ["Svellsongur"] and _names(a.deck.cards) == ["Next"]


def test_undertitan_adds_for_its_owner():
    """'As I'm revealed from your deck, ADD [2]': Teemo's and Mechanical
    Bandit's reveals too; the opponent's Undertitan is theirs."""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 5))
    _deck(a, _card("Undertitan"))
    energy = a.energy
    REGISTRY["teemo_reveal_damage"](_ctx(loop, a), {})
    assert a.energy == energy + 2

    loop, a, b = _setup()
    _deck(a, SpellCard(name="Mine", cost_energy=0))
    _deck(b, _card("Undertitan"))
    ea, eb = a.energy, b.energy
    REGISTRY["mechanical_bandit"](_ctx(loop, a), {})
    assert a.energy == ea and b.energy == eb + 2
