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
        unit.ready = False


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


@effect("move_units_to_base")
def _move_units_to_base(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    side = ctx.actor_side
    bf = ctx.battlefield
    units = list(ctx._units_for_side(side))
    for unit in units:
        bf.remove_unit(side, unit)
        unit.ready = True
        ctx.actor.base_units.append(unit)


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
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "opponent")}, bias="enemy"):
        unit.stunned = True


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
    """The UnitInPlay whose card is this effect's source (for self_might etc.)."""
    for bf in ctx.loop.gs.battlefields:
        for u in bf.units_A + bf.units_B:
            if u.card is ctx.card:
                return u
    for u in ctx.actor.base_units:
        if u.card is ctx.card:
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
    return int(spec.get("amount", 0))


@effect("kill_unit")
def _kill_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    gs = ctx.loop.gs
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        # The owner is found per unit so both-sides targets route each card to
        # the right trash.
        for side in ("A", "B"):
            units = _bf_units(ctx, side)
            if unit in units:
                units.remove(unit)
                owner = gs.get_player(side)
                owner.trash.append(unit.card)
                owner.base_gear.extend(unit.gear)
                break


@effect("kill_gear")
def _kill_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Destroy gear in play ('Kill all gear'): attached gear anywhere plus
    unattached base gear goes to its owner's trash."""
    gs = ctx.loop.gs
    for side in ("A", "B"):
        player = gs.get_player(side)
        in_play = [u for bf in gs.battlefields
                   for u in (bf.units_A if side == "A" else bf.units_B)]
        in_play.extend(player.base_units)
        for u in in_play:
            if u.gear:
                player.trash.extend(u.gear)
                u.gear.clear()
        if player.base_gear:
            player.trash.extend(player.base_gear)
            player.base_gear.clear()


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
                break


@effect("move_unit")
def _move_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    # Minimal: move target friendly unit from current BF to its base (the only
    # destination we can resolve without an explicit target lane from the agent).
    side = ctx.actor_side
    units = _bf_units(ctx, side)
    player = ctx.loop.gs.get_player(side)
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")}):
        if unit in units:
            units.remove(unit)
            unit.ready = True
            unit.reset_damage()
            player.base_units.append(unit)


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


@effect("return_from_trash")
def _return_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "actor"))
    player = ctx._player_for_target(target)
    tf = spec.get("target_filter") or {}
    count = int(spec.get("count", spec.get("amount", 1)))
    moved = 0
    for card in list(player.trash):
        if moved >= count:
            break
        if "tag" in tf and tf["tag"] not in getattr(card, "tags", []):
            continue
        if "card_type" in tf and _card_category_name(card) != str(tf["card_type"]).upper():
            continue
        if tf.get("is_spell") and _card_category_name(card) != "SPELL":
            continue
        if tf.get("is_unit") and _card_category_name(card) not in ("UNIT", "CHAMPION", "LEGEND"):
            continue
        player.trash.remove(card)
        player.hand.append(card)
        moved += 1


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
    from .movement_effects import _spawn_token_to_base
    token_name = str(spec.get("token_name", "Recruit"))
    count = int(spec.get("count", spec.get("amount", 1)))
    ready = _coerce_bool(spec.get("ready", False))
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    for _ in range(count):
        _spawn_token_to_base(player, token_name, ready=ready)


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
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    for runes in player.rune_pool.values():
        for rune in runes:
            rune.refresh()


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
    amount = int(spec.get("amount", spec.get("count", 1)))
    deck = ctx.actor.deck
    n = max(0, min(amount, len(deck.cards)))
    if n <= 1:
        return
    top = deck.cards[-n:]
    rest = deck.cards[:-n]
    top_sorted = sorted(top, key=lambda c: int(getattr(c, "might", 0) or 0))
    deck.cards[:] = rest + top_sorted  # best might ends up last == drawn next


@effect("dig")
@effect("reveal_and_choose")
def _reveal_and_choose(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Look at the top N cards, keep the best (highest might) into hand, recycle
    the rest to the bottom of the deck. Deterministic stand-in for player choice."""
    amount = int(spec.get("amount", spec.get("count", 1)))
    deck = ctx.actor.deck
    n = max(0, min(amount, len(deck.cards)))
    if n == 0:
        return
    top = deck.cards[-n:]
    del deck.cards[-n:]
    best = max(top, key=lambda c: int(getattr(c, "might", 0) or 0))
    top.remove(best)
    ctx.actor.hand.append(best)
    deck.cards[:0] = top  # recycle remainder to the bottom


@effect("play_from_trash")
def _play_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Return matching card(s) from the trash into play. Units enter Base exhausted;
    other card types go to hand (ignore-cost play resolves on the controller's turn)."""
    from .cards import UnitCard
    from .combat import UnitInPlay
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    tf = spec.get("target_filter") or {}
    count = int(spec.get("count", spec.get("amount", 1)))
    moved = 0
    for card in list(player.trash):
        if moved >= count:
            break
        if "tag" in tf and tf["tag"] not in getattr(card, "tags", []):
            continue
        player.trash.remove(card)
        if isinstance(card, UnitCard):
            player.base_units.append(UnitInPlay(card=card, ready=False))
        else:
            player.hand.append(card)
        moved += 1


@effect("banish_card")
def _banish_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Move card(s) from a zone into the banished zone (removed from the game)."""
    src = str(spec.get("from", "trash")).lower()
    count = int(spec.get("count", spec.get("amount", 1)))
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    pool = {"trash": player.trash, "hand": player.hand,
            "deck": player.deck.cards}.get(src, player.trash)
    for _ in range(count):
        if not pool:
            break
        player.banished.append(pool.pop())


@effect("play_from_banish")
def _play_from_banish(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Play matching card(s) from the banished zone (ignore cost). Mirrors
    play_from_trash but pulls from `banished`."""
    from .cards import UnitCard
    from .combat import UnitInPlay
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    tf = spec.get("target_filter") or {}
    count = int(spec.get("count", spec.get("amount", 1)))
    moved = 0
    for card in list(player.banished):
        if moved >= count:
            break
        if "tag" in tf and tf["tag"] not in getattr(card, "tags", []):
            continue
        player.banished.remove(card)
        if isinstance(card, UnitCard):
            player.base_units.append(UnitInPlay(card=card, ready=False))
        else:
            player.hand.append(card)
        moved += 1


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