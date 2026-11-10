"""Rules audit, priority 2 (docs/audit/AUDIT.md): the PARTIAL / GAP rows of
docs/MECHANICS.md checked against docs/rules/CORE_RULES.md."""

from __future__ import annotations

import pytest

from audit_helpers import choices, setup, unit


# -- D12. TANK and BACKLINE on one unit: the assigning player chooses -----------

@pytest.mark.xfail(strict=True, reason="§467.2.c.8: a unit with both TANK and BACKLINE is always "
                                       "assigned combat damage first; the assigning player isn't asked")
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
    choices(loop, {"combat_damage_order": lambda l, o: [u.card.name for u in o].index("Small")})
    loop._phase_combat_and_conquer_single(0, "A")
    assert [u.card.name for u in bf0.units_B] == ["Both"]
