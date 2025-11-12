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


# Late import for type checking support without circular dependency
try:  # pragma: no cover - best effort typing support
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:  # pragma: no cover
        from riftbound.core.loop import EffectContext  # noqa: F401
except Exception:  # pragma: no cover - typing helper only
    pass
