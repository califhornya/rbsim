from __future__ import annotations

from typing import Any, Callable, Mapping

from riftbound.registry.cards_registry import CARD_REGISTRY

from .battlefield import Battlefield

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
    amount = _amount(ctx, spec)
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
    if spec.get("amount_source"):
        count = _amount(ctx, spec)  # "draw 1 for each of your MIGHTY units"
    else:
        count = int(spec.get("count", spec.get("amount", 1)))
    target = str(spec.get("target", "actor"))
    source = str(spec.get("source", "effect"))
    ctx.draw_cards(count, target=target, source=source)


@effect("gain_energy")
def _gain_energy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    ctx.gain_energy(amount, target=target)


@effect("mode_choice")
def _mode_choice(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Modal "choose one" (§ modal): the actor picks one mode; its sub-effect(s)
    resolve. A mode is either a single effect dict or a list of effect dicts.
    Default (heuristic / no agent): the first mode."""
    modes = spec.get("modes") or []
    if not modes:
        return
    agent = getattr(ctx.actor, "agent", None)
    i = 0
    if agent is not None and hasattr(agent, "decide_mode"):
        try:
            i = int(agent.decide_mode(ctx.card, len(modes)))
        except Exception:  # noqa: BLE001
            i = 0
    i = max(0, min(i, len(modes) - 1))
    chosen = modes[i]
    subs = chosen if isinstance(chosen, list) else [chosen]
    for sub in subs:
        handler = REGISTRY.get(sub.get("effect"))
        if handler:
            handler(ctx, sub)


@effect("sequence")
def _sequence(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Several effects resolved in order as ONE ability or trigger, paid once
    ("[1], [tap]: Return a friendly unit ... Play a Gold gear token"): `steps`
    is a list of effect dicts, resolved like mode_choice's sub-effects."""
    for sub in spec.get("steps") or []:
        handler = REGISTRY.get(sub.get("effect"))
        if handler:
            handler(ctx, sub)


@effect("reveal_top_draw_if_spell")
def _reveal_top_draw_if_spell(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    ctx.reveal_top_draw_if_spell(target=str(spec.get("target", "actor")))


@effect("gain_power_any_domain")
def _gain_power_any_domain(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ADD [rune] (§ "add"): gain `amount` Power of a domain of the player's
    choice into the pool. Baseline policy: the domain the hand most lacks (power
    cost still unpayable from the pool), else the most plentiful rune domain."""
    from collections import Counter
    from .enums import Domain
    amount = int(spec.get("amount", 1))
    if amount <= 0:
        return
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    need: Counter = Counter()
    for c in player.hand:
        d, n = getattr(c, "cost_power_domain", None), int(getattr(c, "cost_power", 0) or 0)
        if d is not None and n > player.power_pool.get(d, 0):
            need[d] += n - player.power_pool.get(d, 0)
    if need:
        domain = need.most_common(1)[0][0]
    else:
        runes = {d: len(rs) for d, rs in player.rune_pool.items() if rs}
        domain = max(runes, key=runes.get) if runes else next(iter(Domain))
    player.add_power(domain, amount)


@effect("add_power")
def _add_power(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ADD [fury] (§ "add"): gain `amount` Power of a named domain (the Seals)."""
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    player.add_power(ctx._coerce_domain(spec.get("domain")), int(spec.get("amount", 1)))


@effect("add_earmarked_energy")
def _add_earmarked_energy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    ctx.add_earmarked_energy(int(spec.get("amount", 1)),
                             target=str(spec.get("target", "actor")))


@effect("add_earmarked_power")
def _add_earmarked_power(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    ctx.add_earmarked_power(int(spec.get("amount", 1)),
                            target=str(spec.get("target", "actor")),
                            use=str(spec.get("use", "gear")))


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


@effect("channel_rune")
def _channel_rune(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Channel runes from the rune deck into play ('channel N rune(s)[, exhausted]')."""
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    count = int(spec.get("count", spec.get("amount", 1)))
    player.unlock_runes(count, exhausted=_coerce_bool(spec.get("exhausted", False)))


@effect("grant_temporary_might")
def _grant_temporary_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = _amount(ctx, spec)
    for unit in _resolve_targets(ctx, spec):
        unit.temporary_might += amount


@effect("grant_temporary_might_if_alone")
def _grant_temporary_might_if_alone(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    units = ctx._units_for_target(target)
    if not units:
        return
    if len(units) > 1:
        return
    units[0].temporary_might += amount


@effect("debuff_might")
def _debuff_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Negative this-turn might with an optional floor (min resulting might)."""
    amount = abs(_amount(ctx, spec))
    floor = int(spec.get("min_floor", 0))
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        base = unit.might
        reduction = min(amount, max(0, base - floor))
        unit.temporary_might -= reduction


@effect("double_might")
def _double_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, spec):
        unit.temporary_might += unit.might  # this-turn doubling


@effect("exhaust_unit")
def _exhaust_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        ctx.loop._exhaust(unit)


@effect("ready_unit")
def _ready_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")}):
        unit.ready = True


@effect("score_point")
def _score_point(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 1))
    side = _target_side(ctx, str(spec.get("target", "actor")))
    if side == "A":
        ctx.loop.gs.points_A += amount
    else:
        ctx.loop.gs.points_B += amount


@effect("counter_spell")
def _counter_spell(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    max_energy = int(spec.get("max_energy", 4))
    max_power = int(spec.get("max_power", 1))
    chain = ctx.loop.gs.chain
    if not chain:
        return
    target_item = chain[-1]
    target_card = target_item.card
    if target_card.cost_energy > max_energy:
        return
    if (target_card.cost_power or 0) < int(spec.get("min_power", 0)):
        return
    if (target_card.cost_power or 0) > max_power:
        return
    chain.pop()
    owner = ctx.loop.gs.get_player(target_item.player)
    owner.trash.append(target_card)


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
    for unit in _resolve_targets(ctx, spec):
        if unit.might_counters < 1:  # BUFF is non-stacking (max 1 per unit)
            unit.might_counters += 1


@effect("spend_buff")
def _spend_buff(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Remove BUFF counters (might_counters) from target units — used as a cost
    by 'spend a buff to ...' effects. Defaults to friendly units."""
    count = int(spec.get("count", spec.get("amount", 1)))
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")}):
        unit.might_counters -= min(count, unit.might_counters)


@effect("stun_unit")
def _stun_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    enemies = ctx._units_for_side(ctx.opponent_side)
    stunned_enemy = False
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "opponent")}, bias="enemy"):
        unit.stunned = True
        stunned_enemy = stunned_enemy or any(unit is e for e in enemies)
    if stunned_enemy:
        ctx.loop._fire_stun_enemy(ctx.actor_side)


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


def _target_side(ctx: "EffectContext", target: str) -> str:
    key = target.lower()
    if key in {"actor", "ally", "self", "friendly_unit", "all_friendly_units_here"}:
        return ctx.actor_side
    return ctx.opponent_side


def _bf_units(ctx: "EffectContext", side: str) -> list:
    return ctx.battlefield.units_A if side == "A" else ctx.battlefield.units_B


def _card_category_name(card) -> str:
    cat = getattr(card, "category", None)
    return getattr(cat, "name", str(cat)).upper()


def _zone_card_matches(card, tf: Mapping[str, Any]) -> bool:
    """Card-type filter for cards sitting in a zone (trash/hand/deck), where we
    have a bare Card rather than a UnitInPlay. Used by banish/recycle-all paths."""
    if not tf:
        return True
    cat = _card_category_name(card)
    if tf.get("is_unit") and cat not in ("UNIT", "CHAMPION", "LEGEND"):
        return False
    if tf.get("is_spell") and cat != "SPELL":
        return False
    if tf.get("is_gear") and cat != "GEAR":
        return False
    if tf.get("is_champion") and cat != "CHAMPION":
        return False
    if tf.get("is_legend") and cat != "LEGEND":
        return False
    if "card_type" in tf and cat != str(tf["card_type"]).upper():
        return False
    if "subtype" in tf and str(tf["subtype"]) not in (getattr(card, "tags", None) or []):
        return False
    return True


def _passes_filter(unit, tf: Mapping[str, Any], ctx: "EffectContext") -> bool:
    """Apply a target_filter dict to a single unit (Round 4 Tier 1)."""
    if not tf:
        return True
    card = unit.card
    if tf.get("exclude_self") and card is ctx.card:
        return False
    if "has_keyword" in tf and not card.has_keyword(str(tf["has_keyword"])):
        return False
    if "lacks_keyword" in tf and card.has_keyword(str(tf["lacks_keyword"])):
        return False
    cat = _card_category_name(card)
    if tf.get("is_gear") and cat != "GEAR":
        return False
    if tf.get("is_spell") and cat != "SPELL":
        return False
    if tf.get("is_unit") and cat not in ("UNIT", "CHAMPION", "LEGEND"):
        return False
    if tf.get("is_token") and not getattr(unit, "is_token", False):
        return False
    if tf.get("non_token") and getattr(unit, "is_token", False):
        return False
    if tf.get("is_legend") and cat != "LEGEND":
        return False
    if tf.get("is_champion") and cat != "CHAMPION":
        return False
    if "card_type" in tf and cat != str(tf["card_type"]).upper():
        return False
    if "subtype" in tf and str(tf["subtype"]) not in (card.tags or []):
        return False
    if tf.get("is_buffed") and getattr(unit, "might_counters", 0) <= 0:
        return False
    if tf.get("is_exhausted") and getattr(unit, "ready", True):
        return False
    if tf.get("is_ready") and not getattr(unit, "ready", True):
        return False
    if tf.get("is_mighty") and unit.might < 5:
        return False
    if "might_at_most" in tf and unit.might > int(tf["might_at_most"]):
        return False
    if "might_at_least" in tf and unit.might < int(tf["might_at_least"]):
        return False
    if tf.get("might_less_than_self"):
        # Reference is the effect's source unit (ctx.card). If it isn't on the
        # board (e.g. a spell), the filter is a no-op rather than excluding all.
        src = _source_unit(ctx)
        if src is not None and unit.might >= src.might:
            return False
    return True


# Targets that mean "units on both sides of this battlefield" (board-wide
# spells like 'Kill all units' / 'return all units with 2 [might] or less').
_BOTH_SIDES_TARGETS = {"battlefield", "both", "both_players", "everyone", "all_units"}

# "Player picks a unit" — unrestricted, may be on EITHER side (KNOWN_ISSUES #16).
# These resolve to a both-sides candidate pool; `bias` orders the deterministic
# single-target pick so a harmful effect doesn't auto-hit the caster's own unit.
_CHOOSER_TARGETS = {"chosen_unit", "chosen", "any_unit", "a_unit", "unit"}


def _resolve_targets(ctx: "EffectContext", spec: Mapping[str, Any], *, bias: str = "none") -> list:
    """Return the list of units an effect should hit, honoring target + scope + target_filter.

    `bias` ("enemy" | "friendly" | "none") only affects a chooser target ("a unit"):
    it decides which side the deterministic baseline picks first for a single target.
    """
    target = str(spec.get("target", "actor")).lower()
    scope = str(spec.get("scope", "single")).lower()
    if target in ("self", "this", "me"):
        # "me" is the source unit itself wherever it is (base included), not the
        # first friendly unit at the effect's battlefield.
        src = _source_unit(ctx)
        return [src] if src is not None else []
    if target == "triggering_unit":
        # The unit that caused this trigger ("give it +1 [might]").
        unit = ctx.extra.get("triggering_unit")
        return [unit] if unit is not None else []
    if target in _BOTH_SIDES_TARGETS:
        units = list(ctx.battlefield.units_A) + list(ctx.battlefield.units_B)
    elif target in _CHOOSER_TARGETS:
        friendly = list(ctx._units_for_side(ctx.actor_side))
        enemy = list(ctx._units_for_side(ctx.opponent_side))
        units = enemy + friendly if bias == "enemy" else friendly + enemy
    else:
        units = ctx._units_for_target(target)
    tf = spec.get("target_filter")
    if tf:
        units = [u for u in units if _passes_filter(u, tf, ctx)]
    if not units:
        return []
    return list(units) if scope != "single" else units[:1]


def _source_unit(ctx: "EffectContext"):
    """The UnitInPlay whose card is this effect's source (for self_might etc.).
    For an attached Equipment it is the equipped unit ("When I move" on gear)."""
    units = [u for bf in ctx.loop.gs.battlefields for u in bf.units_A + bf.units_B]
    units += ctx.actor.base_units
    for u in units:
        if u.card is ctx.card:
            return u
    for u in units:
        if any(g is ctx.card for g in u.gear):
            return u
    return None


def _friendly_units(ctx: "EffectContext") -> list:
    """All friendly UnitInPlay: every battlefield + the actor's base."""
    side = ctx.actor_side
    units = [u for bf in ctx.loop.gs.battlefields
             for u in (bf.units_A if side == "A" else bf.units_B)]
    units.extend(ctx.actor.base_units)
    return units


def _amount(ctx: "EffectContext", spec: Mapping[str, Any]) -> int:
    """Resolve a fixed `amount` or a dynamic `amount_source` (Round 4 Tier 1)."""
    src = spec.get("amount_source")
    if not src:
        return int(spec.get("amount", 0))
    if src == "self_might":
        u = _source_unit(ctx)
        return u.might if u else int(spec.get("amount", 0))
    if src == "trash_count":
        return len(ctx.actor.trash)
    if src in ("points", "controller_points"):
        gs = ctx.loop.gs
        return gs.points_A if ctx.actor_side == "A" else gs.points_B
    if src == "opponent_points":
        gs = ctx.loop.gs
        return gs.points_A if ctx.opponent_side == "A" else gs.points_B
    if src in ("friendly_mighty_units", "count:friendly_mighty_units"):
        side = ctx.actor_side
        return sum(1 for bf in ctx.loop.gs.battlefields
                   for u in (bf.units_A if side == "A" else bf.units_B) if u.might >= 5)
    if src == "highest_might_friendly":
        units = _friendly_units(ctx)
        return max((u.might for u in units), default=0)
    if src == "cards_in_hand":
        return len(ctx.actor.hand)
    if src == "enemies_here":
        return len(ctx._units_for_side(ctx.opponent_side))
    if src == "friendly_units_here":
        return len(ctx._units_for_side(ctx.actor_side))
    if src == "n_friendly_with_tag":
        tag = str(spec.get("tag", ""))
        return sum(1 for u in _friendly_units(ctx) if tag in (u.card.tags or []))
    if src == "n_distinct_tags_among_friendlies":
        return len({t for u in _friendly_units(ctx) for t in (u.card.tags or [])})
    if src == "cards_with_my_name_in_trash":
        return sum(1 for c in ctx.actor.trash if c.name == ctx.card.name and c is not ctx.card)
    if src == "battlefields_conquered_this_turn":
        return int(ctx.loop.gs.conquered_this_turn.get(ctx.actor_side, 0))
    if src == "hold_points_this_turn":
        return int(ctx.loop.gs.hold_points_this_turn.get(ctx.actor_side, 0))
    if src == "cards_played_this_turn":
        return int(ctx.loop.gs.cards_played_this_turn.get(ctx.actor_side, 0))
    if src == "friendly_exhausted_units":
        return sum(1 for u in _friendly_units(ctx) if not u.ready)
    if src in ("shown_might", "shown_power_cost", "shown_energy_cost"):
        shown = getattr(ctx.card, "_shown", None) or {}
        return int(shown.get(src[len("shown_"):], 0))
    return int(spec.get("amount", 0))


@effect("kill_unit")
def _kill_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    dead = []
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        # The owner is found per unit so both-sides targets route each card to
        # the right trash.
        for side in ("A", "B"):
            units = _bf_units(ctx, side)
            if unit in units:
                units.remove(unit)
                dead.append((unit, side))
                break
    # They die together: replacements, DEATHKNELL, "when a friendly unit dies".
    ctx.loop._route_deaths(dead, ctx.battlefield)


def _gear_entries(ctx: "EffectContext", enemy_first: bool) -> list[tuple[str, object, object]]:
    """All gear in play as (owner_side, holder_or_None, gear). holder is the
    UnitInPlay wearing it, None for unattached base gear, or the Battlefield a
    DEPLOY gear sits on (gear is then its DeployedGear wrapper)."""
    gs = ctx.loop.gs
    # enemy_first means the opponent's side comes first in the pick order.
    order = (ctx.opponent_side, ctx.actor_side) if enemy_first else (ctx.actor_side, ctx.opponent_side)
    entries: list[tuple[str, object, object]] = []
    for side in order:
        player = gs.get_player(side)
        in_play = [u for bf in gs.battlefields
                   for u in (bf.units_A if side == "A" else bf.units_B)]
        in_play.extend(player.base_units)
        for u in in_play:
            for g in u.gear:
                entries.append((side, u, g))
        for g in player.base_gear:
            entries.append((side, None, g))
        for bf in gs.battlefields:
            for dg in bf.gear_for(side):
                entries.append((side, bf, dg))
    return entries


def _gear_matches(gear_card, tf: Mapping[str, Any]) -> bool:
    gear_card = getattr(gear_card, "card", gear_card)  # unwrap a DeployedGear
    if "energy_at_most" in tf and int(getattr(gear_card, "cost_energy", 0) or 0) > int(tf["energy_at_most"]):
        return False
    if "energy_at_least" in tf and int(getattr(gear_card, "cost_energy", 0) or 0) < int(tf["energy_at_least"]):
        return False
    return True


@effect("kill_gear")
def _kill_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Destroy gear in play. Default ('Kill all gear') wipes every gear both
    sides; when a target_filter, a single scope, or a chooser target is given,
    kills ONE matching gear (enemy-biased) instead of board-wiping — KNOWN_ISSUES #17."""
    gs = ctx.loop.gs
    tf = spec.get("target_filter") or {}
    scope = str(spec.get("scope", "")).lower()
    target = str(spec.get("target", "")).lower()
    single = bool(tf) or scope == "single" or target in _CHOOSER_TARGETS or target in _ENEMY_GEAR_HINTS

    entries = _gear_entries(ctx, enemy_first=True)
    entries = [(s, h, g) for (s, h, g) in entries if _gear_matches(g, tf)]
    if single:
        entries = entries[:1]

    for side, holder, gear in entries:
        player = gs.get_player(side)
        if isinstance(holder, Battlefield):
            ctx.loop._kill_deployed_gear(holder, side, [gear])
        elif holder is not None:
            if gear in holder.gear:
                holder.gear.remove(gear)
                ctx.loop._to_trash(player, gear)
        elif gear in player.base_gear:
            player.base_gear.remove(gear)
            ctx.loop._to_trash(player, gear)


_ENEMY_GEAR_HINTS = {"enemy_gear", "chosen_gear", "gear"}


@effect("heal_unit")
def _heal_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")}):
        unit.damage = 0


@effect("recall_unit")
def _recall_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Return units to their owner's hand. Every recall_unit card reads
    'return ... to its owner's hand': the card leaves play (tokens cease to
    exist) and attached gear is recovered to the owner's base."""
    gs = ctx.loop.gs
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")}):
        for side in ("A", "B"):
            units = _bf_units(ctx, side)
            if unit in units:
                units.remove(unit)
                owner = gs.get_player(side)
                owner.base_gear.extend(unit.gear)
                unit.gear = []
                if not getattr(unit, "is_token", False):
                    owner.hand.append(unit.card)
                # Recall/bounce is a board exit → leaves_board fires (KNOWN_ISSUES #9).
                ctx.loop._fire_leaves_board(unit.card, side, ctx.battlefield)
                break


def _units_at(ctx: "EffectContext", side: str, where: str) -> list:
    """`side`'s units at a location kind: "here" (the effect's battlefield),
    "battlefield" (any battlefield), "base", or "anywhere"."""
    gs = ctx.loop.gs
    if where == "here":
        return list(ctx.battlefield._units_for(side)) if ctx.battlefield in gs.battlefields else []
    units = []
    if where in ("battlefield", "anywhere"):
        units += [u for bf in gs.battlefields for u in bf._units_for(side)]
    if where in ("base", "anywhere"):
        units += list(gs.get_player(side).base_units)
    return units


def _attack_value(ctx: "EffectContext", side: str, unit, bf) -> int:
    """How good moving `unit` (of `side`) into `bf` is for its controller:
    winning a fight beats claiming an empty battlefield beats reinforcing."""
    mine = sum(u.might for u in bf._units_for(side) if u is not unit)
    theirs = sum(u.might for u in bf._units_for("B" if side == "A" else "A"))
    if theirs and mine + unit.might >= theirs:
        return 3
    if not theirs and bf.controller() != side:
        return 2
    if bf.controller() == side:
        return 1
    return 0


@effect("move_unit")
def _move_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    _move_units(ctx, spec, to_base_verb=False)


@effect("move_units_to_base")
def _move_units_to_base(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    _move_units(ctx, spec, to_base_verb=True)


def _move_units(ctx: "EffectContext", spec: Mapping[str, Any], *, to_base_verb: bool) -> None:
    """Move unit(s) as the effect says. `target`: friendly_unit / enemy_unit /
    chosen_unit (either side; an enemy first) / self / all_*_here. `from`: here,
    battlefield, base or anywhere (default: here for move_units_to_base and
    *_here targets, else anywhere). `destination`: base (move_units_to_base's
    default), here (this battlefield), battlefield (a battlefield), other_
    battlefield, or to_or_from_base; move_unit's default is base for an enemy,
    a battlefield for a friendly unit. `ready`: ready it after.

    Baseline policy (the effect's controller's choice): an enemy goes to its
    base / away from the fight, picking its mightiest unit at a battlefield, or
    into "here" picking its weakest; a friendly unit goes where it attacks best
    (_attack_value), picking its mightiest unit; a friendly unit sent to base
    is the one losing its fight."""
    loop = ctx.loop
    gs = loop.gs
    me, them = ctx.actor_side, ctx.opponent_side
    target = str(spec.get("target", "friendly_unit")).lower()
    scope_all = str(spec.get("scope", "")).lower() == "all" or target.startswith("all_")
    count = len(gs.battlefields) * 99 if scope_all else int(spec.get("count", 1))
    tf = spec.get("target_filter")

    if target in ("self", "this", "me"):
        src = _source_unit(ctx)
        candidates = [(me, src)] if src is not None else []
    else:
        enemy = any(k in target for k in ("enemy", "opponent"))
        friendly = any(k in target for k in ("friendly", "ally", "actor"))
        default_from = "here" if (to_base_verb or target.endswith("_here")) else "anywhere"
        frm = str(spec.get("from", default_from)).lower()
        sides = [them] if enemy else [me] if friendly else [them, me]
        candidates = [(s, u) for s in sides for u in _units_at(ctx, s, frm)]
    if tf:
        candidates = [(s, u) for s, u in candidates if _passes_filter(u, tf, ctx)]
    if not candidates:
        return

    dest = spec.get("destination")
    if dest is None:
        dest = "base" if to_base_verb or candidates[0][0] == them else "battlefield"
    dest = str(dest).lower()

    def destination_for(side, unit):
        where = loop._locate_unit(unit)
        cur = where[1] if where else None
        if dest == "base":
            return None, True
        if dest in ("here", "this_battlefield"):
            ok = ctx.battlefield in gs.battlefields and cur is not ctx.battlefield
            return ctx.battlefield, ok
        if dest == "to_or_from_base" and cur is not None:
            return None, True
        others = [bf for bf in gs.battlefields if bf is not cur]
        if not others:
            return None, False
        if side == me:
            best = max(others, key=lambda bf: _attack_value(ctx, side, unit, bf))
            return best, _attack_value(ctx, side, unit, best) > 0
        # An enemy is moved where it fights worst for them.
        return min(others, key=lambda bf: _attack_value(ctx, side, unit, bf)), True

    def priority(item):
        side, unit = item
        where = loop._locate_unit(unit)
        at_bf = where is not None and where[1] is not None
        if side == them:
            if dest in ("here", "this_battlefield"):
                return (-unit.might,)                      # pull their weakest in
            return (at_bf, unit.might)                     # push their mightiest out
        if dest == "base":
            bf = where[1] if where else None
            losing = bf is not None and sum(u.might for u in bf._units_for(them)) > \
                sum(u.might for u in bf._units_for(me))
            return (losing, unit.might)
        return (not at_bf, unit.might)                     # send a base unit in

    moved = 0
    for side, unit in sorted(candidates, key=priority, reverse=True):
        if moved >= count:
            break
        dst_bf, ok = destination_for(side, unit)
        if not ok:
            continue
        if loop._move_unit_by_effect(unit, dst_bf):
            if spec.get("ready"):
                unit.ready = True
            moved += 1


@effect("give_keyword")
def _give_keyword(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    keyword = str(spec.get("keyword", "")).strip()
    if not keyword:
        return
    for unit in _resolve_targets(ctx, spec):
        if keyword not in unit.card.keywords:
            unit.card.keywords.append(keyword)


def _give_temp_keyword(ctx: "EffectContext", spec: Mapping[str, Any], kw: str) -> None:
    amount = int(spec.get("amount", 1))
    token = f"{kw} {amount}"
    for unit in _resolve_targets(ctx, spec):
        unit.card.keywords.append(token)


@effect("give_temporary_assault")
def _give_temporary_assault(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    _give_temp_keyword(ctx, spec, "ASSAULT")


@effect("give_temporary_shield")
def _give_temporary_shield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    _give_temp_keyword(ctx, spec, "SHIELD")


@effect("give_temporary_deflect")
def _give_temporary_deflect(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    _give_temp_keyword(ctx, spec, "DEFLECT")


@effect("swap_might")
def _swap_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Switcheroo: 'Swap the Might of two units at the same battlefield this turn.'
    Deterministic stand-in for the player's choice (like dig/predict): pick the
    battlefield and the (friendly, enemy) pair maximizing the caster's gain —
    raise the caster's weakest to the enemy's strongest and vice versa — and swap
    their effective Might for the turn via temporary_might (cleared at end of turn).
    No beneficial pair → no-op."""
    gs = ctx.loop.gs
    side = ctx.actor_side
    best = None
    best_gain = 0
    for bf in gs.battlefields:
        friendly = bf.units_A if side == "A" else bf.units_B
        enemy = bf.units_B if side == "A" else bf.units_A
        if not friendly or not enemy:
            continue
        u_f = min(friendly, key=lambda u: u.might)
        u_e = max(enemy, key=lambda u: u.might)
        gain = u_e.might - u_f.might
        if gain > best_gain:
            best_gain, best = gain, (u_f, u_e)
    if best is not None:
        u_f, u_e = best
        m_f, m_e = u_f.might, u_e.might
        u_f.temporary_might += (m_e - m_f)
        u_e.temporary_might += (m_f - m_e)


@effect("swap_position")
def _swap_position(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Tideturner: 'Move me to its location and it to my original location.'
    Deterministic stand-in: swap this unit's position with the highest-might
    friendly non-token unit at a DIFFERENT location (base or another battlefield).
    No eligible other-location unit → no-op."""
    loop = ctx.loop
    gs = loop.gs
    side = ctx.actor_side
    me = loop._find_unit_by_card(ctx.card)
    if me is None:
        return

    def locate(unit):
        if unit in ctx.actor.base_units:
            return ("base", ctx.actor.base_units)
        for i, bf in enumerate(gs.battlefields):
            lst = bf.units_A if side == "A" else bf.units_B
            if unit in lst:
                return (("bf", i), lst)
        return (None, None)

    my_loc, my_list = locate(me)
    if my_loc is None:
        return
    # Friendly, non-token units at a different location; pick the strongest.
    candidates = []
    for i, bf in enumerate(gs.battlefields):
        lst = bf.units_A if side == "A" else bf.units_B
        for u in lst:
            if u is not me and not u.is_token and ("bf", i) != my_loc:
                candidates.append(u)
    for u in ctx.actor.base_units:
        if u is not me and not u.is_token and my_loc != "base":
            candidates.append(u)
    if not candidates:
        return
    target = max(candidates, key=lambda u: u.might)
    tgt_loc, tgt_list = locate(target)

    def place(unit, loc):
        if loc == "base":
            ctx.actor.base_units.append(unit)
        else:
            gs.battlefields[loc[1]].add_unit(side, unit)

    my_list.remove(me)
    tgt_list.remove(target)
    place(me, tgt_loc)
    place(target, my_loc)


_LEGACY_ZONE_FILTERS = {
    "gear": ("GEAR",),
    "unit": ("UNIT", "CHAMPION"),
    "unit_or_gear": ("UNIT", "CHAMPION", "GEAR"),
}


def _zone_effect_card_ok(card, spec: Mapping[str, Any]) -> bool:
    """Whether a card in a zone (trash / banishment) matches a zone effect's
    filter: its target_filter (type, tag, keyword, Energy/Power bounds) plus the
    older `filter` strings ("gear", "unit_or_gear") some specs still use."""
    legacy = _LEGACY_ZONE_FILTERS.get(str(spec.get("filter") or "").lower())
    if legacy and _card_category_name(card) not in legacy:
        return False
    tf = spec.get("target_filter") or {}
    if not _zone_card_matches(card, tf):
        return False
    if "tag" in tf and tf["tag"] not in (getattr(card, "tags", None) or []):
        return False
    if "has_keyword" in tf and not card.has_keyword(str(tf["has_keyword"])):
        return False
    energy = int(getattr(card, "cost_energy", 0) or 0)
    power = int(getattr(card, "cost_power", 0) or 0)
    if "energy_at_most" in tf and energy > int(tf["energy_at_most"]):
        return False
    if "energy_at_least" in tf and energy < int(tf["energy_at_least"]):
        return False
    if "power_at_most" in tf and power > int(tf["power_at_most"]):
        return False
    return True


def _zone_value(card) -> tuple[int, int]:
    """Baseline pick among zone cards: the most expensive, then the mightiest."""
    return (int(getattr(card, "cost_energy", 0) or 0), int(getattr(card, "might", 0) or 0))


@effect("return_from_trash")
def _return_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "actor"))
    player = ctx._player_for_target(target)
    count = int(spec.get("count", spec.get("amount", 1)))
    picks = sorted((c for c in player.trash if _zone_effect_card_ok(c, spec)),
                   key=_zone_value, reverse=True)[:count]
    for card in picks:
        player.trash.remove(card)
        player.hand.append(card)


@effect("discard_card")
def _discard_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "actor"))
    player = ctx._player_for_target(target)
    count = int(spec.get("count", spec.get("amount", 1)))
    side = "A" if player is ctx.loop.gs.A else "B"
    for _ in range(count):
        if not player.hand:
            break
        player.trash.append(player.hand.pop(0))
        ctx.loop.gs.discarded_this_turn[side] = True


@effect("play_token")
def _play_token(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Play `count` tokens (GameLoop._play_token). `location`: "base" (default),
    "here" (this battlefield; base if the source is in base) or "moved_from"
    (where the moving unit left, Lillia: "play a Sprite there"). `might`
    overrides the token's Might ("a 2 [might] Sand Soldier")."""
    token_name = str(spec.get("token_name", "Recruit"))
    count = int(spec.get("count", spec.get("amount", 1)))
    ready = _coerce_bool(spec.get("ready", False))
    # You always play YOUR token; `target` here often names the destination
    # (e.g. "battlefield"), not a player, so fall back to the actor rather than
    # erroring on a non-player target.
    try:
        player = ctx._player_for_target(str(spec.get("target", "actor")))
    except ValueError:
        player = ctx.actor
    token_spec = CARD_REGISTRY.get(token_name)
    if token_spec is not None and "DEPLOY" in token_spec.keywords:
        # Gear token with DEPLOY (§830): all `count` go to a single battlefield.
        side = ctx._side_for_player(player)
        bf = _deploy_destination(ctx, spec, side)
        for _ in range(count):
            ctx.loop._deploy_gear(side, bf, token_spec, is_token=True)
        return
    side = ctx._side_for_player(player)
    location = str(spec.get("location", "base")).lower()
    bf = None
    if location == "here":
        here = ctx.battlefield
        src = ctx.loop._find_unit_by_card(ctx.card)
        in_base = src is not None and src in player.base_units
        bf = None if in_base or here not in ctx.loop.gs.battlefields else here
    elif location == "moved_from":
        origin = ctx.extra.get("moved_from")
        bf = origin if origin in ctx.loop.gs.battlefields else None
    for _ in range(count):
        ctx.loop._play_token(token_name, side, bf=bf, ready=ready, might=spec.get("might"))


def _deploy_destination(ctx: "EffectContext", spec: Mapping[str, Any], side: str) -> Battlefield:
    """Battlefield a DEPLOY gear goes to. `battlefield: "here"` keeps the effect's
    own battlefield; otherwise (baseline policy) the one with the most enemy units,
    where a Bomb will hit hardest when the opponent holds it."""
    if str(spec.get("battlefield", "")).lower() == "here":
        return ctx.battlefield
    bfs = ctx.loop.gs.battlefields
    enemy = "B" if side == "A" else "A"
    return max(bfs, key=lambda b: (b.count(enemy), -bfs.index(b)))


@effect("kill_other_deployed_here")
def _kill_other_deployed_here(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Kill the actor's other deployed gear at this battlefield, optionally only
    those named `name` (Bomb: "kill all other Bombs you control here"). They die
    together, then each one's DEATHKNELL resolves. Used from a DEATHKNELL, when the
    source has already left the battlefield, so every match is an "other" one."""
    name = str(spec.get("name", "") or "").strip().lower()
    side = ctx.actor_side
    bf = ctx.battlefield
    dead = [dg for dg in bf.gear_for(side)
            if dg.card is not ctx.card or dg.is_token]
    if name:
        dead = [dg for dg in dead if dg.card.name.lower() == name]
    ctx.loop._kill_deployed_gear(bf, side, dead)


@effect("move_deployed_gear")
def _move_deployed_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Move one of the actor's DEPLOY gear to another battlefield (§830.1.d).
    Baseline policy: the gear from the battlefield with the fewest friendly units
    to the one with the most."""
    side = ctx.actor_side
    bfs = ctx.loop.gs.battlefields
    sources = [b for b in bfs if b.gear_for(side)]
    if not sources:
        return
    src = min(sources, key=lambda b: b.count(side))
    dests = [b for b in bfs if b is not src]
    if not dests:
        return
    dst = max(dests, key=lambda b: b.count(side))
    dg = src.gear_for(side).pop(0)
    dst.gear_for(side).append(dg)
    ctx.loop._recompute_passives()


@effect("burn")
def _burn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Vendetta BURN X: move the top X cards of the target's Main Deck to trash,
    and track the count this turn (for 'cards burned this turn' conditions)."""
    amount = int(spec.get("amount", spec.get("count", 1)))
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    burned = player.burn(amount)
    side = ctx._side_for_player(player)
    gs = ctx.loop.gs
    gs.cards_burned_this_turn[side] = gs.cards_burned_this_turn.get(side, 0) + len(burned)


@effect("empower_self")
def _empower_self(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Vendetta EMPOWER: give the source unit the empowered status. Usually an
    activated ability (`trigger: activated`) whose cost the player pays first, but
    also usable from a trigger ("when ..., empower me"). Idempotent."""
    unit = ctx.loop._find_unit_by_card(ctx.card)
    if unit is not None:
        unit.empowered = True


@effect("disempower")
def _disempower(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Remove the empowered status from the resolved target(s). Used as an
    instruction or a cost ("disempower a unit that's EMPOWERED")."""
    target = str(spec.get("target", "enemy_unit"))
    if target in ("self", "this"):
        unit = ctx.loop._find_unit_by_card(ctx.card)
        units = [unit] if unit is not None else []
    else:
        units = _resolve_targets(ctx, {**spec, "target": target, "scope": spec.get("scope", "single")})
    for u in units:
        if getattr(u, "empowered", False):
            u.empowered = False


@effect("attach_gear")
def _attach_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    player = ctx.actor
    if not player.base_gear:
        return
    units = _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor"), "scope": "single"})
    if not units:
        return
    units[0].gear.append(player.base_gear.pop(0))


@effect("ready_runes")
def _ready_runes(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Ready exhausted runes: "ready up to N runes" honors `amount`; without one
    ("ready your runes") every rune is readied."""
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    left = spec.get("amount")
    left = None if left is None else int(left)
    for runes in player.rune_pool.values():
        for rune in runes:
            if left is not None and left <= 0:
                return
            if not rune.ready:
                rune.refresh()
                if left is not None:
                    left -= 1


@effect("gain_xp")
def _gain_xp(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 1))
    side = _target_side(ctx, str(spec.get("target", "actor")))
    ctx.loop.gs.add_xp(side, amount)


@effect("scry")
@effect("predict")
def _predict(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """PREDICT/SCRY X: look at the top X cards of your deck and reorder them.
    Deterministic policy: arrange so the highest-might card is drawn next (placed
    on top). No card leaves the deck. Top of deck = end of the cards list."""
    if spec.get("amount_source"):
        amount = _amount(ctx, spec)  # e.g. The Empyrean: shown_power_cost
    else:
        amount = int(spec.get("amount", spec.get("count", 1)))
    deck = ctx.actor.deck
    n = max(0, min(amount, len(deck.cards)))
    if n == 0:
        return
    look = deck.cards[-n:]
    # Cards with an on_reveal_from_top ability (Nocturne) may banish + play now.
    ctx.loop._offer_reveal_from_top(ctx.actor, look)
    if n == 1:
        # PREDICT 1 / VISION (§743): look at the top card; you MAY recycle it to
        # the bottom of the deck. Deterministic default is to keep (a null action);
        # a learning agent can override decide_predict_recycle.
        if not deck.cards:
            return
        top = deck.cards[-1]
        agent = getattr(ctx.actor, "agent", None)
        if agent is not None and hasattr(agent, "decide_predict_recycle") \
                and agent.decide_predict_recycle(top):
            deck.cards.pop()
            deck.cards.insert(0, top)   # recycle to bottom (front of the list)
        return
    rest = deck.cards[:-n]
    top_sorted = sorted(look, key=lambda c: int(getattr(c, "might", 0) or 0))
    deck.cards[:] = rest + top_sorted  # best might ends up last == drawn next


@effect("dig")
@effect("reveal_and_choose")
def _reveal_and_choose(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Look at the top N cards, keep the best (highest might) into hand, recycle
    the rest to the bottom of the deck. Deterministic stand-in for player choice.
    A card filter ("reveal a gear from among them") limits what may be kept; with
    no match, nothing is kept."""
    amount = int(spec.get("amount", spec.get("count", 1)))
    deck = ctx.actor.deck
    n = max(0, min(amount, len(deck.cards)))
    if n == 0:
        return
    top = deck.cards[-n:]
    del deck.cards[-n:]
    # Cards with an on_reveal_from_top ability (Nocturne) may banish + play now,
    # removing themselves from the looked-at set before we keep the best.
    ctx.loop._offer_reveal_from_top(ctx.actor, top)
    if not top:
        return
    tf = spec.get("target_filter") or spec.get("reveal_filter") or spec.get("filter")
    tf = tf if isinstance(tf, Mapping) else {}
    def _energy_ok(c) -> bool:
        e = int(getattr(c, "cost_energy", 0) or 0)
        return (("energy_at_most" not in tf or e <= int(tf["energy_at_most"]))
                and ("energy_at_least" not in tf or e >= int(tf["energy_at_least"])))

    keepable = [c for c in top if _zone_card_matches(c, tf) and _energy_ok(c)]
    if keepable:
        best = max(keepable, key=lambda c: int(getattr(c, "might", 0) or 0))
        top.remove(best)
        ctx.actor.hand.append(best)
    deck.cards[:0] = top  # recycle remainder to the bottom


def _play_from_zone(ctx: "EffectContext", spec: Mapping[str, Any], zone: str) -> None:
    """Play matching card(s) from the trash or banishment, through the engine's
    play procedure ("when you play me", play counters, ...). Costs are ignored,
    except the Power cost when the card says "ignoring its Energy cost"
    (`ignore_energy_cost` / `pay_power`); an unaffordable card is skipped. Units
    go to base, gear to base, spells are cast at this battlefield (`then:
    recycle` recycles the spell afterwards, e.g. Fizz Trickster)."""
    from .cards import GearCard, SpellCard, UnitCard
    loop = ctx.loop
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    side = ctx._side_for_player(player)
    pool = player.trash if zone == "trash" else player.banished
    count = int(spec.get("count", spec.get("amount", 1)))
    pay_power = bool(spec.get("ignore_energy_cost") or spec.get("pay_power"))
    pay_cost = bool(spec.get("pay_cost"))   # "You still pay its costs" (Last Rites)
    lane = loop.gs.battlefields.index(ctx.battlefield) if ctx.battlefield in loop.gs.battlefields else 0
    picks = sorted((c for c in pool if _zone_effect_card_ok(c, spec)),
                   key=_zone_value, reverse=True)
    if spec.get("cost_at_most_cost_unit"):
        # "costs no more Energy and no more Power than the killed unit": the unit
        # the card's additional cost killed (GameLoop._pay_one_additional_cost).
        victim = getattr(ctx.card, "_cost_unit", None)
        if victim is None:
            return
        picks = [c for c in picks
                 if int(c.cost_energy or 0) <= int(victim.cost_energy or 0)
                 and int(c.cost_power or 0) <= int(victim.cost_power or 0)]
    played = 0
    for card in picks:
        if played >= count:
            break
        if card not in pool:
            continue
        if pay_cost:
            energy, power = loop._effective_cost(card, player)
            if not loop._pay_card(player, card, energy, power):
                continue
        elif pay_power:
            power = int(card.cost_power or 0)
            domain = card.cost_power_domain
            if domain is None:
                if not loop._pay_generic_power(player, power):
                    continue
            elif not player.pay_cost(0, power, domain):
                continue
        pool.remove(card)
        if isinstance(card, UnitCard):
            loop._play_unit(card, side, from_zone=zone)
        elif isinstance(card, GearCard):
            loop._play_gear(card, side, lane, from_zone=zone)
        elif isinstance(card, SpellCard):
            loop._cast_spell_now(card, side, lane, from_zone=zone)
            if spec.get("then") == "recycle" and card in player.trash:
                player.trash.remove(card)
                player.deck.cards.insert(0, card)
        else:
            player.hand.append(card)
        played += 1


@effect("play_from_trash")
def _play_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    _play_from_zone(ctx, spec, "trash")


@effect("banish_card")
def _banish_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Move card(s) from a zone into the banished zone (removed from the game).

    Honors scope:"all" ("banish ALL units from your trash") and a card-type
    target_filter (is_unit/is_spell/is_gear/card_type) — KNOWN_ISSUES #13.
    """
    src = str(spec.get("from", "trash")).lower()
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    pool = {"trash": player.trash, "hand": player.hand,
            "deck": player.deck.cards}.get(src, player.trash)
    tf = spec.get("target_filter") or {}
    scope = str(spec.get("scope", "")).lower()
    count = len(pool) if scope == "all" else int(spec.get("count", spec.get("amount", 1)))

    banished = 0
    # Iterate from the END so the no-filter case matches the historical
    # `pool.pop()` selection (behaviour-preserving); filter/scope just narrow it.
    for card in reversed(list(pool)):
        if banished >= count:
            break
        if not _zone_card_matches(card, tf):
            continue
        pool.remove(card)
        player.banished.append(card)
        banished += 1


@effect("play_from_banish")
def _play_from_banish(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Play matching card(s) from the banished zone (ignore cost). Mirrors
    play_from_trash but pulls from `banished`."""
    _play_from_zone(ctx, spec, "banished")


@effect("prevent_death")
@effect("replace_death_with_recall")
def _replace_death_with_recall(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    # Death-replacement is a replacement effect: it is applied by the kill path in
    # GameLoop._try_replace_death (which has the dying-unit + source-gear context),
    # not via normal on_play dispatch. This registry entry documents the verb and
    # is a no-op if ever dispatched directly.
    return


@effect("take_control")
def _take_control(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Take control of an enemy unit at the effect's battlefield: move it from the
    opponent's side to the actor's side at the same battlefield."""
    bf = ctx.battlefield
    actor_side = ctx.actor_side
    enemy = bf.units_B if actor_side == "A" else bf.units_A
    friendly = bf.units_A if actor_side == "A" else bf.units_B
    tf = spec.get("target_filter")
    candidates = [u for u in enemy if _passes_filter(u, tf, ctx)] if tf else list(enemy)
    if not candidates:
        return
    unit = candidates[0]
    enemy.remove(unit)
    friendly.append(unit)


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