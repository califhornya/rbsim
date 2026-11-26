"""Candidate D83 (segnalazione 35, game 155859 T12): Reckless Innovator ("When I become exhausted, choose one
- Play a Gold ... - Pay [chaos] to draw 1.") on Rust, profile 6427b90+D72-D82. The Gold ("REACTION[>] Kill this,
[tap]: ADD [rune]") may pay the [chaos] (CORE_RULES 204.3.a, 430.3, 445.2.c: an ADD Reaction can be activated at
any time a resource must be paid, also inside an instruction), but the engine pays the cost of the mode only
from the runes (effects.rs mode_payable / run_mode -> pay_one_additional_cost_x -> pay_energy_and_generic) and
never asks how. The Python engine (frozen) does the same.

Position (Python, tests/audit/audit_helpers): A has Reckless Innovator in base, a ready Gold, `chaos` Chaos runes
and two cards in the deck; the human seat (payments=True, as the page) moves Reckless to BF0 and asks for the
"draw" mode whenever it is offered.

a) one Chaos rune + the Gold: the [chaos] can be paid either way. Today: the rune is recycled, the Gold stays
   ready, the seat is asked nothing ("Come paghi?" exists only for moves). Pinned.
b) no Chaos rune, only the Gold: today the draw mode is not offered at all (one mode only) and the unit plays a
   second Gold instead. Pinned; the correct behaviour is the xfail below (becomes the D83 test on the new
   profile: change `D72_D82` to `D72_D83` and drop the xfail).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))

from audit_helpers import card, setup, unit  # noqa: E402
from test_d72_d76 import rust  # noqa: E402

D72_D82 = "6427b90+D72-D82"


def _play(regole, chaos_runes):
    """-> (events of the game, kinds the seat was asked, offered modes, A's hand / gear after)."""
    from riftbound.core.player import Domain, Rune
    loop, a, _b = setup(active="A", rich=())
    a.rune_pool[Domain.CHAOS] = [Rune(Domain.CHAOS) for _ in range(chaos_runes)]
    a.channel()
    gold = card("Gold")
    gold.tapped = False
    a.base_gear.append(gold)
    a.base_units.append(unit("Reckless Innovator"))
    a.deck.cards.extend([card("Punch First"), card("Punch First")])
    g = rust(loop, regole)
    asked, moved = [], []

    def ask(ev):
        e = json.loads(ev)
        if e["k"] == "decision":
            hit = [i for i, m in enumerate(e["menu"]) if m.startswith("Move Reckless") and not moved]
            if hit:
                moved.append(1)
                return hit[0]
            return e["menu"].index("Pass")
        asked.append(e["k"] + (":" + e["kind"] if "kind" in e else ""))
        return 1 if e["k"] == "decide_mode" else e["default"]
    g.set_human_agent("A", ask, payments=True)
    g.run_segment(1)
    evs = json.loads(g.events())
    mode = next(e for e in evs if e["k"] == "choice" and e["kind"] == "mode")
    raw = evs[-1]["state_raw"]
    raw = json.loads(raw) if isinstance(raw, str) else raw
    objs = raw["objs"]
    pa = raw["objs"][raw["root"]["o"]["$ref"]]["A"]["$v"] if "o" in raw["root"] else raw["root"]["A"]["$v"]

    def name(r):
        o = objs[r["$ref"]]
        return o["name"]
    hand = [name(x) for x in pa["hand"]]
    gear = sorted((name(x), bool(objs[x["$ref"]].get("tapped"))) for x in pa["base_gear"])
    return asked, len(mode["options_raw"]), hand, gear, pa


def test_d83_a_chaos_rune_and_a_gold_the_rune_pays_and_nothing_is_asked():
    asked, modes, hand, gear, pa = _play(D72_D82, 1)
    assert modes == 2 and hand == ["Punch First"]
    assert gear == [("Gold", False)]                       # the Gold was not used
    assert pa["rune_pool"] == {} or not pa["rune_pool"].get("$dict")   # the rune left the pool (recycled)
    assert asked == ["decide_mode", "choice:mode"]          # no "Come paghi?" for the cost inside the effect


def test_d83_b_only_the_gold_can_pay_the_draw_mode_is_not_offered():
    asked, modes, hand, gear, _pa = _play(D72_D82, 0)
    assert modes == 1 and hand == []                       # the draw mode is missing, nothing is drawn
    assert gear == [("Gold", False), ("Gold", True)]       # the unit plays its second (exhausted) Gold instead


@pytest.mark.xfail(strict=True, reason="D83: the Gold's ADD cannot pay the cost inside an effect (rules 204.3.a, 430.3, 445.2.c)")
def test_d83_b_only_the_gold_can_pay_the_draw_mode_is_offered_and_paid_with_the_gold():
    asked, modes, hand, gear, _pa = _play(D72_D82, 0)      # D83: the new profile
    assert modes == 2 and hand == ["Punch First"]
    assert gear == []                                      # the Gold was killed to Add the [chaos] that was paid


@pytest.mark.xfail(strict=True, reason="D83: no 'Come paghi?' for the cost inside an effect when rune and Gold both pay")
def test_d83_a_chaos_rune_and_a_gold_the_seat_is_asked_how_to_pay():
    asked, modes, hand, gear, _pa = _play(D72_D82, 1)      # D83: the new profile, human seat with payments=True
    assert modes == 2 and len(asked) > 2                   # a question beyond the mode (the way to pay)
