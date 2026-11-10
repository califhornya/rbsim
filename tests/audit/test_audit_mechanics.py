"""Rules audit, priority 2 (docs/audit/AUDIT.md): the PARTIAL / GAP rows of
docs/MECHANICS.md checked against docs/rules/CORE_RULES.md."""

from __future__ import annotations

import pytest

from audit_helpers import choices, setup, unit


# -- D12. TANK and BACKLINE on one unit: the assigning player chooses -----------

def test_the_assigner_chooses_between_tank_and_backline_on_one_unit():
    """'If a Unit has one or more Abilities ... that demand it be assigned damage
    in a specific way that is exclusionary, then the assigning player chooses
    only one of those abilities to apply' (the Caitlyn example: first, or last)."""
    loop, a, b = setup(active="A")
    bf0 = loop.gs.battlefields[0]
    both, small = unit("Both", 5), unit("Small", 1)
    both.granted_keywords += ["TANK", "BACKLINE"]
    bf0.add_unit("B", both)
    bf0.add_unit("B", small)
    bf0.add_unit("A", unit("Attacker", 1))
    # The attacker applies BACKLINE: its 1 damage goes to Small first.
    seen = choices(loop, {"combat_tank_or_backline": lambda l, o: o.index("BACKLINE")})
    loop._phase_combat_and_conquer_single(0, "A")
    assert [u.card.name for u in bf0.units_B] == ["Both"]
    assert [(kind, side) for kind, side, _ in seen if kind == "combat_tank_or_backline"] == \
        [("combat_tank_or_backline", "A")]             # the assigner chose, once


def test_tank_applies_to_a_unit_with_both_when_the_assigner_says_so():
    loop, a, b = setup(active="A")
    bf0 = loop.gs.battlefields[0]
    both, small = unit("Both", 5), unit("Small", 1)
    both.granted_keywords += ["TANK", "BACKLINE"]
    bf0.add_unit("B", both)
    bf0.add_unit("B", small)
    bf0.add_unit("A", unit("Attacker", 1))
    choices(loop, {"combat_tank_or_backline": lambda l, o: o.index("TANK")})
    loop._phase_combat_and_conquer_single(0, "A")
    assert sorted(u.card.name for u in bf0.units_B) == ["Both", "Small"]
