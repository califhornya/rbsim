"""Movement-triggered card effects.

When a unit moves (base→bf, bf→base, or bf→bf), its "When I move" effects fire.
This module centralizes those effects for all cards with movement triggers.
"""

from typing import Optional, Callable

# Handler signature: (actor, opponent, gs, unit, src_kind, dst_kind, target_bf) -> None
# src_kind/dst_kind: "base" or "bf"
# target_bf: Battlefield or None (None for bf→base moves)
MovementHandler = Callable[..., None]

MOVEMENT_REGISTRY: dict[str, MovementHandler] = {}


def register_movement(card_name: str):
    """Decorator to register a movement effect handler."""
    def decorator(fn: MovementHandler) -> MovementHandler:
        MOVEMENT_REGISTRY[card_name] = fn
        return fn
    return decorator


def _spawn_token_to_base(actor, card_name: str, ready: bool) -> None:
    """Create a token unit and add it to the actor's base."""
    from riftbound.registry.cards_registry import CARD_REGISTRY
    from riftbound.core.combat import UnitInPlay

    card = CARD_REGISTRY.get(card_name)
    if card is None:
        return
    token = UnitInPlay(card=card, ready=ready, is_token=True)
    actor.base_units.append(token)


def _spawn_token_at_bf(actor, target_bf, side: str, card_name: str, ready: bool, fixed_might: Optional[int] = None) -> None:
    """Create a token unit and add it directly to a battlefield."""
    from riftbound.registry.cards_registry import CARD_REGISTRY
    from riftbound.core.combat import UnitInPlay

    card = CARD_REGISTRY.get(card_name)
    if card is None:
        return
    token = UnitInPlay(card=card, ready=ready, is_token=True)
    if fixed_might is not None:
        # Create a shallow copy of the card with modified might
        from copy import copy
        token.card = copy(card)
        token.card.might = fixed_might
    target_bf.add_unit(side, token)


def _grant_another_unit(actor, gs, unit, target_bf, side: str, amount: int) -> None:
    """Grant +might to another friendly unit at the same battlefield."""
    units = target_bf.units_A if side == "A" else target_bf.units_B
    others = [u for u in units if u is not unit]
    if others:
        others[0].temporary_might += amount


# === Simple Movement Effects ===

@register_movement("Treasure Hunter")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if dst_kind == "bf":
        _spawn_token_to_base(actor, "Gold", ready=False)


@register_movement("Stellacorn Herder")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    actor.draw()


@register_movement("Traveling Merchant")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if actor.hand:
        actor.trash.append(actor.hand.pop(0))
    actor.draw()


@register_movement("Mister Root")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    actor.energy += 2


@register_movement("Harpoon Squad")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if src_kind == "bf":
        unit.temporary_might += 2


@register_movement("Ribbon Dancer")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if dst_kind == "bf" and target_bf:
        side = "A" if actor is gs.A else "B"
        _grant_another_unit(actor, gs, unit, target_bf, side, 1)


@register_movement("Kato the Arm")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if dst_kind == "bf" and target_bf:
        side = "A" if actor is gs.A else "B"
        _grant_another_unit(actor, gs, unit, target_bf, side, 1)


@register_movement("Corrupt Enforcer")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if dst_kind == "bf" and actor.hand:
        actor.trash.append(actor.hand.pop(0))


@register_movement("Noxian Drummer")
def _(actor, opponent, gs, unit, src_kind, dst_kind, target_bf):
    if dst_kind == "bf" and target_bf:
        side = "A" if actor is gs.A else "B"
        _spawn_token_at_bf(actor, target_bf, side, "Recruit", ready=False, fixed_might=1)


# === Stub Handlers (Complex effects, deferred) ===

_stub_cards = [
    "Fae Porter",
    "Rift Herald",
    "Irresistible Faefolk",
    "Imposing Challenger",
    "Nilah Joyful Ascetic",
    "Lillia Fae Fawn",
    "Hwei Brooding Painter",
    "Jhin Murderous Artist",
    "Corina Veraza",
]

for _card in _stub_cards:
    MOVEMENT_REGISTRY[_card] = lambda *args: None
