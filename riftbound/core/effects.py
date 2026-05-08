from __future__ import annotations

from typing import Any, Callable, Mapping

EffectHandler = Callable[["EffectContext", Mapping[str, Any]], None]

REGISTRY: dict[str, EffectHandler] = {}


def effect(name: str) -> Callable[[EffectHandler], EffectHandler]:
    """Decorator used to register effect handlers by name."""

    key = name.strip()
    if not key:
        raise ValueError("Effect name cannot be empty")

    def decorator(func: EffectHandler) -> EffectHandler:
        REGISTRY[key] = func
        return func

    return decorator


@effect("deal_damage")
def _deal_damage(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "opponent"))
    ctx.deal_damage(amount, target=target)


@effect("grant_might")
def _grant_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    scope = str(spec.get("scope", "all"))
    ctx.grant_might(amount, target=target, scope=scope)

@effect("draw_cards")
def _draw_cards(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    count = int(spec.get("count", spec.get("amount", 1)))
    target = str(spec.get("target", "actor"))
    source = str(spec.get("source", "effect"))
    ctx.draw_cards(count, target=target, source=source)


@effect("gain_energy")
def _gain_energy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    ctx.gain_energy(amount, target=target)


@effect("ready_units")
def _ready_units(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "actor"))
    scope = str(spec.get("scope", "all"))
    ctx.ready_units(target=target, scope=scope)


@effect("add_rune")
def _add_rune(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    if "domain" not in spec:
        raise ValueError("add_rune effect requires a 'domain' parameter")

    domain = spec.get("domain")
    target = str(spec.get("target", "actor"))
    ready_value = spec.get("ready", True)
    ready = _coerce_bool(ready_value)
    ctx.add_rune(domain, target=target, ready=ready)


@effect("grant_temporary_might")
def _grant_temporary_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    units = ctx._units_for_target(target)
    if not units:
        return
    unit = units[0]
    unit.temporary_might += amount


@effect("grant_temporary_might_per_enemy")
def _grant_temporary_might_per_enemy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    base_amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    units = ctx._units_for_target(target)
    if not units:
        return
    unit = units[0]
    # Count enemy units at the target battlefield
    enemy_count = len(ctx._units_for_target("opponent"))
    total_amount = base_amount * enemy_count
    unit.temporary_might += total_amount


@effect("grant_temporary_might_per_friendly")
def _grant_temporary_might_per_friendly(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    base_amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    units = ctx._units_for_target(target)
    if not units:
        return
    unit = units[0]
    # Count friendly units at the target battlefield
    friendly_count = len(ctx._units_for_target("actor"))
    total_amount = base_amount * friendly_count
    unit.temporary_might += total_amount


@effect("buff_unit")
def _buff_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "actor"))
    units = ctx._units_for_target(target)
    if not units:
        return
    unit = units[0]
    if unit.might_counters < 1:
        unit.might_counters += 1


@effect("stun_unit")
def _stun_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "opponent"))
    units = ctx._units_for_target(target)
    if units:
        units[0].stunned = True


@effect("recycle_card")
def _recycle_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    from .cards import RuneCard
    target = str(spec.get("target", "actor"))
    player = ctx._player_for_target(target)
    if player.hand:
        card = player.hand.pop(0)
        # Route card to correct deck by type (Rule 403: RECYCLE)
        if isinstance(card, RuneCard):
            player.rune_deck.cards.append(card)  # Bottom of rune deck
        else:
            player.deck.cards.append(card)  # Bottom of main deck (Units, Spells, Gear)


@effect("add_battlefield")
def _add_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    from .battlefield import Battlefield
    already_exists = any(
        getattr(bf, "card", None) and getattr(bf.card, "name", "") == "Baron Nashor"
        for bf in ctx.loop.gs.battlefields
    )
    if already_exists:
        return
    bf = Battlefield()
    bf.card = ctx.card
    ctx.loop.gs.battlefields.append(bf)
    actor_side = ctx.actor_side
    for existing_bf in ctx.loop.gs.battlefields[:-1]:
        units = existing_bf.units_A if actor_side == "A" else existing_bf.units_B
        for unit in units:
            unit.aura_might += 2
    from .combat import UnitInPlay
    baron_unit = UnitInPlay(card=ctx.card, ready=False)
    bf.add_unit(actor_side, baron_unit)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"false", "0", "no", "off"}:
            return False
        if lowered in {"true", "1", "yes", "on"}:
            return True
    return bool(value)



# Late import for type checking support without circular dependency
try:  # pragma: no cover - best effort typing support
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:  # pragma: no cover
        from riftbound.core.loop import EffectContext  # noqa: F401
except Exception:  # pragma: no cover - typing helper only
    pass