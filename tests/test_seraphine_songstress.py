"""Seraphine Starry-Eyed Songstress (BACKLOG E): "As an additional cost to play
a spell, you may exhaust me and three friendly units to reduce the cost of that
spell by [2]." Every spell payment (_can_pay_card / _pay_card, FLOW) may take
it (GameLoop._songstress_discount); baseline: only when the spell can't be paid
without it."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.legality import legal_actions
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _always, _deck, _play_spell, _setup, _unit


def _seraphine(loop, side="A"):
    unit = UnitInPlay(card=CARD_REGISTRY["Seraphine Starry-Eyed Songstress"].instantiate(), ready=True)
    setattr(loop.gs, f"legend_unit_{side}", unit)
    return unit


def _friends(p, n, prefix="U"):
    units = [_unit(f"{prefix}{i}", might=i + 1) for i in range(n)]
    p.base_units.extend(units)
    return units


def _spells(loop, p):
    return [a for a in legal_actions(loop, player=p.name) if a.kind == "SPELL"]


def test_a_spell_short_two_energy_is_played_by_exhausting_her_and_three_units():
    loop, a, b = _setup()
    legend = _seraphine(loop)
    units = _friends(a, 3)
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    a.energy = 4                                        # Progress Day costs [6] [mind]
    a.hand.append(CARD_REGISTRY["Progress Day"].instantiate())
    assert _spells(loop, a)
    loop._apply_action(a, ("SPELL", len(a.hand) - 1, 0))
    assert a.energy == 0 and len(a.hand) == 4
    assert not legend.ready and not any(u.ready for u in units)


def test_without_three_ready_units_it_cant_be_paid():
    loop, a, b = _setup()
    _seraphine(loop)
    units = _friends(a, 3)
    units[0].ready = False
    a.energy = 4
    a.hand.append(CARD_REGISTRY["Progress Day"].instantiate())
    assert not _spells(loop, a)


def test_an_exhausted_seraphine_cant_pay_it():
    loop, a, b = _setup()
    _seraphine(loop).ready = False
    _friends(a, 3)
    a.energy = 4
    a.hand.append(CARD_REGISTRY["Progress Day"].instantiate())
    assert not _spells(loop, a)


def test_only_spells():
    loop, a, b = _setup()
    _seraphine(loop)
    _friends(a, 3)
    a.energy = 2
    a.hand.append(UnitCard(name="Dear", might=3, cost_energy=4))
    assert not [x for x in legal_actions(loop, player="A") if x.kind == "UNIT"]


def test_baseline_pays_in_full_when_it_can():
    loop, a, b = _setup()
    legend = _seraphine(loop)
    units = _friends(a, 3)
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    _play_spell(loop, a, "Progress Day")
    assert a.energy == 14 and legend.ready and all(u.ready for u in units)


def test_the_player_may_pay_it_anyway():
    loop, a, b = _setup()
    legend = _seraphine(loop)
    _friends(a, 3)
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    loop.chooser = _always(True)
    _play_spell(loop, a, "Progress Day")
    assert a.energy == 16 and not legend.ready


def test_baseline_exhausts_units_at_battlefields_then_tokens_then_the_weakest():
    loop, a, b = _setup()
    _seraphine(loop)
    there = _unit("There", might=5)
    loop.gs.battlefields[0].add_unit("A", there)
    token = _unit("Token", might=4, is_token=True)
    weak, strong = _unit("Weak", might=1), _unit("Strong", might=3)
    a.base_units.extend([strong, token, weak])
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    a.energy = 4
    _play_spell(loop, a, "Progress Day")
    assert not there.ready and not token.ready and not weak.ready and strong.ready


def test_the_player_chooses_the_units():
    loop, a, b = _setup()
    _seraphine(loop)
    units = _friends(a, 4)
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    a.energy = 4

    def chooser(_loop, kind, side, options, default, source):
        if kind == "cost_unit:exhaust":
            return next(i for i, o in enumerate(options) if o.card.name != "U0")
        return None
    loop.chooser = chooser
    _play_spell(loop, a, "Progress Day")
    assert units[0].ready and not any(u.ready for u in units[1:])


def test_three_units_exhausted_at_once_fire_seraphine_inspiring_and_not_alone():
    """Seraphine Inspiring: "when you exhaust three or more friendly units at the
    same time, you may draw 1". Seraphine Not Alone: "when I become exhausted,
    play a 1 [might] Recruit unit token to your base"."""
    loop, a, b = _setup()
    _seraphine(loop)
    inspiring, alone = _unit("Seraphine Inspiring"), _unit("Seraphine Not Alone")
    a.base_units.extend([inspiring, alone, _unit("Other", might=1)])
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(5)])
    a.energy = 4
    _play_spell(loop, a, "Progress Day")
    assert len(a.hand) == 5                             # 4 + Inspiring's 1
    assert any(u.card.name == "Recruit" for u in a.base_units)


def test_a_flow_spell_from_the_trash():
    loop, a, b = _setup()
    legend = _seraphine(loop)
    _friends(a, 3)
    _deck(a, SpellCard(name="C"))
    dredge = CARD_REGISTRY["Dredge Up"].instantiate()   # FLOW [2]
    a.trash = [dredge]
    a.energy = 0
    (idx, entry), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "flow"]
    assert loop._ability_usable(a, entry)
    loop._apply_action(a, ("ABILITY", "ACTIVATED", idx, None))
    assert len(a.hand) == 1 and dredge in a.banished and not legend.ready


def test_the_energy_spent_is_what_was_paid():
    loop, a, b = _setup()
    _seraphine(loop)
    _friends(a, 3)
    _deck(a, *[SpellCard(name=f"C{i}") for i in range(4)])
    a.energy = 4
    card = CARD_REGISTRY["Progress Day"].instantiate()
    a.hand.append(card)
    loop._apply_action(a, ("SPELL", len(a.hand) - 1, 0))
    assert card._spent == 4
