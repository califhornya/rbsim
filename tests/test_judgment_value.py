"""The value from the user's judgments (riftbound/ai/judgment_value.py): one
case per judgment it encodes."""
from __future__ import annotations

from dataclasses import replace

from riftbound.ai.judgment_value import judgment_value
from riftbound.core.decisions import BattlefieldView, Observation, UnitView


def _unit(name, might=2):
    return UnitView(name=name, might=might, ready=True, stunned=False, is_token=False, gear=())


def _obs(**kw) -> Observation:
    base = dict(viewer="A", turn=5, active="B", victory_score=8, my_points=3, opp_points=3,
                my_energy=0, opp_energy=0, my_power={}, opp_power={}, my_xp=0, opp_xp=0,
                my_hand=(), opp_hand_count=3, my_deck_count=20, opp_deck_count=20,
                my_trash=(), opp_trash=(), my_base_units=(), opp_base_units=(),
                my_runes=6, opp_runes=6,
                battlefields=(BattlefieldView(A=(_unit("Pyke Returned", 3),), B=(), controller="A", named=None),
                              BattlefieldView(A=(), B=(), controller=None, named=None)),
                my_legend="Evelynn Agony's Embrace", opp_legend="Kha'Zix Voidreaver")
    base.update(kw)
    return Observation(**base)


def test_a_hidden_card_is_worth_more_than_its_body_on_the_board():
    """S11b: keep the Stranger face down rather than flip it for its 2 Might."""
    bf0 = _obs().battlefields[0]
    hidden = _obs(battlefields=(replace(bf0, facedowns=("A",)),) + _obs().battlefields[1:])
    flipped = _obs(battlefields=(replace(bf0, A=bf0.A + (_unit("Bedeviling Stranger", 2),)),)
                   + _obs().battlefields[1:])
    assert judgment_value(hidden) > judgment_value(flipped) > judgment_value(_obs())


def test_an_out_the_open_runes_pay_for_counts(monkeypatch):
    """S8, S11a: Star-Crossed with 3 energy and a Chaos rune open is an out
    (the weight is 0 by default: measured, BOT_SCENARI.md)."""
    from riftbound.ai import judgment_value as J
    monkeypatch.setitem(J.W, "out", 0.05)
    hand = ("Star-Crossed", "Rengar Trophy Hunter")
    paid = _obs(my_hand=hand, my_energy=3, my_rune_domains={"CHAOS": 1})
    unpaid = _obs(my_hand=hand, my_energy=3, my_rune_domains={"BODY": 1})
    assert judgment_value(paid) > judgment_value(unpaid)


def test_points_by_the_deck_plan():
    """TEORIA_PUNTI.md: for Kha'Zix (two a turn) an odd point counts half; for
    Evelynn (hold) 7 counts half a point more."""
    from riftbound.ai.judgment_value import _points
    assert [_points(p, "two", 8) for p in (4, 5, 6, 7)] == [4, 4.5, 6, 6.5]
    assert [_points(p, "hold", 8) for p in (5, 6, 7)] == [5, 6, 7.5]
    assert _points(5, None, 8) == 5
    kz = dict(my_legend="Kha'Zix Voidreaver", opp_legend="Evelynn Agony's Embrace", opp_points=4)
    assert judgment_value(_obs(my_points=5, **kz)) - judgment_value(_obs(my_points=4, **kz)) < \
        judgment_value(_obs(my_points=6, **kz)) - judgment_value(_obs(my_points=5, **kz))


def test_the_threats_the_user_named():
    """S7, S10: Faefolk on the board; Vex at a battlefield, not in base."""
    with_faefolk = _obs(opp_base_units=(_unit("Irresistible Faefolk", 1),))
    plain = _obs(opp_base_units=(_unit("Traveling Merchant", 1),))
    assert judgment_value(with_faefolk) < judgment_value(plain)
    vex_base = _obs(opp_base_units=(_unit("Vex Apathetic", 4),))
    bf1 = _obs().battlefields[1]
    vex_bf = _obs(battlefields=_obs().battlefields[:1] + (replace(bf1, B=(_unit("Vex Apathetic", 4),)),))
    assert judgment_value(vex_bf) < judgment_value(vex_base) - 0.05


def test_this_turn_might_does_not_count():
    bf0 = _obs().battlefields[0]
    pumped = _obs(battlefields=(replace(bf0, A=(replace(bf0.A[0], might=8, lasting_might=3),)),)
                  + _obs().battlefields[1:])
    assert judgment_value(pumped) == judgment_value(_obs())
