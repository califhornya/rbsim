"""LEGION keyword effects mapping.

LEGION is a conditional keyword that enables card effects when another card has been played this turn.
Different cards have different LEGION effects. This module centralizes the effect definitions.
"""

from typing import Optional


def get_legion_cost_reduction(card_name: str) -> Optional[int]:
    """
    Get the energy cost reduction for a LEGION card, if any.

    Args:
        card_name: Name of the card

    Returns:
        Energy cost reduction (as positive number), or None if card has no cost-reducing LEGION effect
    """
    # Cards that reduce their energy cost when LEGION triggers
    cost_reducing_legion = {
        "Noxus Hopeful": 2,  # LEGION — I cost [2] less
    }
    return cost_reducing_legion.get(card_name)


def has_legion_cost_reduction(card_name: str) -> bool:
    """Check if a card has a LEGION-triggered cost reduction."""
    return get_legion_cost_reduction(card_name) is not None
