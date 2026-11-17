"""Rules audit, the owner's post-ban decks (docs/audit/AUDIT.md, seventh pass):
competitive_evelynn and competitive_khazix, given by the owner on 2026-11-17.
Their cards new to the audit, read against the printed text
(riftbound/data/reference/piltover_archive.json) and played in the engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riftbound.core.cards import UnitCard
from riftbound.registry.cards_registry import BANNED_CARDS, load_deck_json

from audit_helpers import act, card, choices, hide, legend, scripted, setup, unit

DECKS = Path(__file__).resolve().parents[2] / "riftbound" / "data" / "decks"


def _decks(*players):
    for p in players:
        p.deck.cards = [UnitCard(name=f"Deck{i}", might=1) for i in range(5)]


def _names(options):
    return [getattr(getattr(o, "card", None), "name", None) or getattr(o, "name", o)
            for o in options]


@pytest.mark.parametrize("name", ["competitive_evelynn", "competitive_khazix"])
def test_the_deck_is_the_list_given(name):
    """40 cards with the Chosen Champion, 12 runes, 3 battlefields, 10 in the
    sideboard, no banned card; every name is a card of the corpus."""
    cards, runes, champion, legend_spec, battlefields = load_deck_json(DECKS / f"{name}.json")
    data = json.loads((DECKS / f"{name}.json").read_text(encoding="utf-8"))
    assert sum(c["count"] for c in data["cards"]) + 1 == 40 and champion is not None
    assert sum(r["count"] for r in data["runes"]) == 12 and len(battlefields) == 3
    assert sum(c["count"] for c in data["sideboard"]) == 10 and legend_spec is not None
    names = {data["legend"], data["champion"]} | {b["name"] for b in data["battlefields"]}
    names |= {c["name"] for c in data["cards"] + data["sideboard"]}
    assert not names & BANNED_CARDS


# -- D57. Evelynn's legend: two cards from face down, discard before draw ------------

def test_evelynn_legend_draws_before_it_discards_with_two_plays_on_the_chain():
    """Evelynn, Agony's Embrace: 'Once each turn, when you play a card from face
    down, draw 1. Then, if it's not your turn, discard 1.' One ability, once each
    turn (§383.3.e.1). Two cards played from face down in a row on the
    opponent's turn: the second play's ability skipped the draw (used by the
    first, on the chain) and kept the discard, which resolved first: the
    player discarded from a hand without the card drawn."""
    loop, a, b = setup(active="B")
    _decks(a, b)
    legend(loop, "A", "Evelynn Agony's Embrace")
    a.hand.append(card("Rampage"))
    loop.gs.battlefields[0].add_unit("A", unit("mine", 2))
    loop.gs.battlefields[1].add_unit("B", unit("theirs", 2))
    hide(loop, "A", 0, "Momentary Companion")
    hide(loop, "A", 0, "Gutter Guardian")
    b.hand.append(card("Onslaught"))
    seen = choices(loop, {})
    scripted(loop, a, b, A={"reaction": ["Play Momentary Companion from Hidden",
                                         "Play Gutter Guardian from Hidden"]})
    act(loop, "B", "Cast Onslaught")
    assert [opts for kind, _s, opts in seen if kind == "discard"] == [["Rampage", "Deck4"]]
    assert len(a.hand) == 1 and len(a.deck.cards) == 4


def test_evelynn_legend_on_your_turn_draws_once_and_never_discards():
    loop, a, b = setup(active="A")
    _decks(a, b)
    legend(loop, "A", "Evelynn Agony's Embrace")
    loop.gs.battlefields[0].add_unit("A", unit("mine", 2))
    hide(loop, "A", 0, "Momentary Companion")
    hide(loop, "A", 0, "Gutter Guardian")
    seen = choices(loop, {})
    act(loop, "A", "Play Momentary Companion from Hidden @BF0")
    act(loop, "A", "Play Gutter Guardian from Hidden @BF0")
    assert len(a.hand) == 1 and not a.trash
    assert not [k for k, _s, _o in seen if k == "discard"]


# -- D58. Kha'Zix's legend buffs only a unit at the first battlefield ----------------

def test_khazix_legend_buffs_a_unit_anywhere():
    """Kha'Zix, Voidreaver: 'Spend 1 XP, [Tap]: [Buff] a unit.' A legend is at
    no battlefield: "a unit" is any unit, friendly or enemy, base included. The
    choice was the units at the first battlefield (a legend's "here")."""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Kha'Zix Voidreaver")
    loop.gs.xp_A = 1
    loop.gs.battlefields[0].add_unit("A", unit("first", 1))
    loop.gs.battlefields[1].add_unit("A", unit("second", 1))
    loop.gs.battlefields[1].add_unit("B", unit("enemy", 1))
    target = unit("home", 1)
    a.base_units.append(target)
    seen = choices(loop, {"target:buff_unit": lambda _l, o: _names(o).index("home")})
    act(loop, "A", "Activate buff_unit")
    assert sorted(*[opts for kind, _s, opts in seen if kind == "target:buff_unit"]) == \
        ["enemy", "first", "home", "second"]
    assert target.might_counters == 1 and loop.gs.xp_A == 0
