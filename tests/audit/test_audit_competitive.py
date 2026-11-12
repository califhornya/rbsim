"""Rules audit, the two competitive decks (docs/audit/AUDIT.md, fifth pass):
competitive_kaisa and competitive_kennen, given by the owner on 2026-11-12.
Their cards new to the audit, read against the printed text
(riftbound/data/reference/piltover_archive.json) and played in the engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import load_deck_json

from audit_helpers import act, card, choices, hide, labels, legend, setup, unit

DECKS = Path(__file__).resolve().parents[2] / "riftbound" / "data" / "decks"


# -- D50. A HIDDEN gear played from face down goes nowhere -------------------------

def test_edge_of_night_played_from_face_down_attaches_to_a_unit_here():
    """Edge of Night (errata): '[Hidden] When you play this from face down,
    attach it to a unit you control (here).' §737.1: a hidden card is played
    for [0]; a gear is played as a gear. It used to vanish."""
    loop, a, b = setup(active="A")
    here, there = unit("here", 2), unit("there", 3)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    a.base_units.append(unit("home", 4))
    hide(loop, "A", 0, "Edge of Night")
    seen = choices(loop, {})
    act(loop, "A", "Play Edge of Night from Hidden @BF0")
    assert [g.name for g in here.gear] == ["Edge of Night"] and here.might == 4
    assert [opts for kind, _s, opts in seen if kind == "target:attach_gear"] == [["here"]]


def test_zhonyas_hourglass_played_from_face_down_goes_to_base():
    """Zhonya's Hourglass: '[Hidden] If a friendly unit would die, kill this
    instead.' Played from face down it is a gear in its player's base."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("here", 2))
    hide(loop, "A", 0, "Zhonya's Hourglass")
    act(loop, "A", "Play Zhonya's Hourglass from Hidden @BF0")
    assert [g.name for g in a.base_gear] == ["Zhonya's Hourglass"]
