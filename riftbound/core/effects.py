from __future__ import annotations

from typing import Any, Callable, Mapping

from riftbound.registry.cards_registry import CARD_REGISTRY

from .battlefield import Battlefield
from .cards import SpellCard

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
    """Deal damage. A single target ("deal 3 to an enemy unit") takes it all,
    excess is lost; `count` targets ("each of up to two units") each take it;
    a group ("all enemy units here", `filter: all_units_at_battlefields`) each
    take it; `split: true` divides the amount among the enemies here, killing
    in order ("5 damage split among enemy units here"). Baseline pick for a
    single target: an enemy over a friend, one the damage kills, the mightiest."""
    amount = _amount(ctx, spec)
    if amount <= 0:
        return
    target = str(spec.get("target", "enemy_unit")).lower()
    if target in ("opponent", "enemy"):
        target = "enemy_unit"
    if spec.get("split"):
        ctx.deal_damage(amount, target="opponent")
        return
    tf = spec.get("target_filter")
    gs = ctx.loop.gs
    if spec.get("filter") == "all_units_at_battlefields":
        units = [u for bf in gs.battlefields for u in bf.units_A + bf.units_B]
        if tf:
            units = [u for u in units if _passes_filter(u, tf, ctx)]
    elif target.startswith("all") or target in _BOTH_SIDES_TARGETS \
            or str(spec.get("scope", "")).lower() == "all":
        units = _resolve_targets(ctx, {**spec, "target": target, "scope": "all"})
    else:
        cands = _resolve_targets(ctx, {**spec, "target": target, "scope": "all"})
        if not cands and not isinstance(ctx.card, SpellCard):
            cands = _fallback_units(ctx, target, "enemy")
            if tf:
                cands = [u for u in cands if _passes_filter(u, tf, ctx)]
        enemies = ctx._units_for_side(ctx.opponent_side)
        enemy_ids = {id(u) for u in enemies}
        for bf in gs.battlefields:
            enemy_ids |= {id(u) for u in bf._units_for(ctx.opponent_side)}
        enemy_ids |= {id(u) for u in ctx.opponent.base_units}

        def value(u):
            kills = amount >= max(0, u.might - u.damage)
            return (id(u) in enemy_ids, kills, u.might)

        units = sorted(_choosable(ctx, cands), key=value, reverse=True)[:int(spec.get("count", 1))]
        if units:
            ctx.loop._note_chosen(ctx.card, ctx.actor_side, units)
    ctx.damage_units(units, amount)


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
    if spec.get("restriction") == "spells_only":
        # "Use only to play spells": earmarked, spent first on spells.
        ctx._player_for_target(target).earmarked_energy_spell += amount
        return
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
    if spec.get("unique_per_turn"):
        # "Choose one that hasn't been chosen this turn" (Aphelios).
        used = ctx.loop.gs.modes_chosen.setdefault((id(ctx.card), ctx.loop.gs.turn), set())
        free = [j for j in range(len(modes)) if j not in used]
        if not free:
            return
        i = i if i in free else free[0]
        used.add(i)
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


@effect("at_end_of_turn")
def _at_end_of_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "At the end of this turn, <then>" (Targon's Peak): schedule `then` (an
    effect dict) for this turn's end, with this effect's controller, source and
    battlefield."""
    sub = spec.get("then")
    if not isinstance(sub, Mapping):
        return
    gs = ctx.loop.gs
    bf_idx = next((i for i, b in enumerate(gs.battlefields) if b is ctx.battlefield), 0)
    gs.delayed_effects.append((ctx.actor_side, ctx.card, bf_idx, dict(sub)))


@effect("discount_next_card")
def _discount_next_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "The next card (spell, ...) you play this turn costs [energy] [power]
    less" (Astral Heron, Raging Firebrand): used by that card (filter)."""
    ctx.loop.gs.next_card_discounts[ctx.actor_side].append({
        "filter": dict(spec.get("filter") or {}),
        "energy": int(spec.get("energy", 0)),
        "power": int(spec.get("power", 0)),
    })


@effect("units_enter_ready_this_turn")
def _units_enter_ready_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Units you play this turn enter ready" (Confront, Bushwhack)."""
    ctx.loop.gs.units_enter_ready_turn[ctx.actor_side] = ctx.loop.gs.turn


@effect("next_unit_enters_ready")
def _next_unit_enters_ready(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "The next unit you play this turn enters ready" (Sun Disc)."""
    ctx.loop.gs.next_units_enter_ready[ctx.actor_side] += int(spec.get("amount", 1))


@effect("fight")
def _fight(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit and an enemy unit. They deal damage equal to
    their Mights to each other" (Challenge). `first`: "friendly" (default),
    "self" ("We deal ...", Carnivorous Snapvine) or "any" (Clash of Giants:
    "two units", two enemies when there are two). The enemy is at a
    battlefield. Baseline pick: the enemy our unit kills without dying, else
    one it kills, else one it survives, mightiest first; our mightiest unit."""
    loop = ctx.loop
    gs = loop.gs
    me, them = ctx.actor_side, ctx.opponent_side
    enemies = _choosable(ctx, [u for bf in gs.battlefields for u in bf._units_for(them)])
    first = str(spec.get("first", "friendly")).lower()
    if first == "any" and len(enemies) >= 2:
        a, b = sorted(enemies, key=lambda u: u.might, reverse=True)[:2]
    else:
        if first == "self":
            a = _source_unit(ctx)
        else:
            mine = _units_at(ctx, me, "anywhere")
            a = max(mine, key=lambda u: u.might) if mine else None
        if a is None or not enemies:
            return

        def value(e):
            kills = a.might >= e.might - e.damage
            survives = e.might < a.might - a.damage
            return (kills and survives, kills, survives, e.might)
        b = max(enemies, key=value)
    loop._note_chosen(ctx.card, me, [a, b])
    a_might, b_might = a.might, b.might
    ctx.damage_units([b], a_might)
    ctx.damage_units([a], b_might)


@effect("set_base_might")
def _set_base_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Its base Might becomes N this turn" (Herald of the Emperor, Dragon
    Form, Lulu). `amount`, or `amount_source: triggering_energy` (the played
    card's Energy cost, Piltovan Guidebot). Target per the spec; a chooser target
    picks the unit it helps most (a friendly unit raised, an enemy lowered)."""
    if spec.get("amount_source") == "triggering_energy":
        trig = ctx.extra.get("triggering_card")
        amount = int(getattr(trig, "cost_energy", 0) or 0)
    else:
        amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "friendly_unit")).lower()
    if target in ("self", "this", "me"):
        units = _resolve_targets(ctx, spec)
    else:
        units = _resolve_targets(ctx, {**spec, "scope": "all"})
        if not units and not isinstance(ctx.card, SpellCard):
            units = _fallback_units(ctx, target, "none")
        units = _choosable(ctx, units)
        if spec.get("other"):
            units = [u for u in units if u.card is not ctx.card]
        friends = {id(u) for u in _friendly_units(ctx)}

        def gain(u):
            base = u.base_might_override if u.base_might_override is not None else int(u.card.might or 0)
            return amount - base if id(u) in friends else base - amount
        units = sorted(units, key=gain, reverse=True)[:1]
        if units and gain(units[0]) <= 0:
            return       # "you may": it helps no one
        ctx.loop._note_chosen(ctx.card, ctx.actor_side, units)
    for unit in units:
        current = unit.base_might_override if unit.base_might_override is not None else int(unit.card.might or 0)
        if spec.get("only_if_higher") and amount <= current:
            continue     # "you may": only when it raises me
        unit.base_might_override = amount


@effect("match_might")
def _match_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit. This turn, increase its Might to the Might of
    another friendly unit" (Convergent Mutation): the weakest friendly unit at a
    battlefield rises to the mightiest friendly unit."""
    mine = _units_at(ctx, ctx.actor_side, "anywhere")
    if len(mine) < 2:
        return
    top = max(mine, key=lambda u: u.might)
    at_bf = [u for u in mine if u is not top and ctx.loop._locate_unit(u)[1] is not None]
    low = min(at_bf or [u for u in mine if u is not top], key=lambda u: u.might)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [low])
    low.temporary_might += max(0, top.might - low.might)


@effect("grant_flow")
def _grant_flow(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Give a spell in your trash FLOW equal to its cost this turn" (Kennen
    Storm of Shuriken): baseline pick, the costliest spell the player can pay
    for now, else the costliest."""
    loop = ctx.loop
    side = ctx.actor_side
    spells = [c for c in ctx.actor.trash if isinstance(c, SpellCard)]
    if not spells:
        return
    for card in spells:
        card._flow_granted_turn = loop.gs.turn
    payable = [c for c in spells if loop._can_pay_flow(ctx.actor, c, side)]
    for card in spells:
        card._flow_granted_turn = None
    pick = max(payable or spells, key=lambda c: (c.cost_energy or 0) + (c.cost_power or 0))
    pick._flow_granted_turn = loop.gs.turn


@effect("next_unit_any_battlefield")
def _next_unit_any_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "The next unit you play this turn, even from face down, can be played to
    any battlefield. When you play it, BUFF it." (Last Caress)"""
    ctx.loop.gs.next_unit_any_bf[ctx.actor_side] = ctx.loop.gs.turn


@effect("play_unit_to_controlled_battlefield")
def _play_unit_to_controlled_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may play a unit from your hand to a battlefield you control,
    reducing its cost by [3]" (Here to Help): the costliest unit that can go,
    to the battlefield where the fight is hardest."""
    from .cards import UnitCard
    loop = ctx.loop
    side, ap = ctx.actor_side, ctx.actor
    reduce = int(spec.get("reduce", 3))
    best = None
    for card in ap.hand:
        if not isinstance(card, UnitCard):
            continue
        dests = [d for d in loop._unit_play_destinations(card, side)
                 if d is not None and loop.gs.battlefields[d].controller() == side]
        energy, power = loop._effective_cost(card, ap)
        energy = max(0, energy - reduce)
        if dests and loop._can_pay_card(ap, card, energy, power) and \
                (best is None or _zone_value(card) > _zone_value(best[0])):
            best = (card, dests, energy, power)
    if best is None:
        return
    card, dests, energy, power = best
    loop._pay_card(ap, card, energy, power)
    ap.hand.remove(card)
    bf = max((loop.gs.battlefields[d] for d in dests),
             key=lambda b: sum(u.might for u in b._units_for(ctx.opponent_side)))
    unit = loop._play_unit(card, side, bf=bf)
    loop._unit_played_here(bf, side, unit)


@effect("ready_legend")
def _ready_legend(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Ready your legend" (Hall of Legends, Heartening Soul)."""
    legend = ctx.loop._legend_unit(ctx.actor_side)
    if legend is not None and not legend.ready:
        legend.ready = True
        ctx.loop._fire_readied(legend, ctx.actor_side)


@effect("return_gear_to_hand")
def _return_gear_to_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Return a gear to its owner's hand" (Factory Recall): the opponent's
    costliest gear (a token ceases to exist)."""
    entries = [(s, h, g) for s, h, g in _gear_entries(ctx, enemy_first=True) if s == ctx.opponent_side]
    if not entries:
        return
    side, holder, gear = max(entries, key=lambda e: _zone_value(getattr(e[2], "card", e[2])))
    owner = ctx.loop.gs.get_player(side)
    card = getattr(gear, "card", gear)
    if isinstance(holder, Battlefield):
        holder.gear_for(side).remove(gear)
    elif holder is not None:
        holder.gear.remove(gear)
    else:
        owner.base_gear.remove(gear)
    ctx.loop._fire_leaves_board(card, side, ctx.loop.gs.battlefields[0])
    if not getattr(card, "is_token", False):
        card.empowered = False
        owner.hand.append(card)


@effect("give_this_to_opponent")
def _give_this_to_opponent(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a player. They gain control of this and recall it" (Glowstone):
    it goes to the opponent's base."""
    loop = ctx.loop
    me = ctx.actor
    if ctx.card in me.base_gear:
        me.base_gear.remove(ctx.card)
    else:
        holder = next((u for u in _units_at(ctx, ctx.actor_side, "anywhere") if ctx.card in u.gear), None)
        if holder is None:
            return
        holder.gear.remove(ctx.card)
    ctx.opponent.base_gear.append(ctx.card)


@effect("ready_gear")
def _ready_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Ready a gear" / "Ready 2 gear" (Jayce Defender of Tomorrow): your
    exhausted gear, costliest first."""
    loop = ctx.loop
    gear = [g for g in list(ctx.actor.base_gear) + loop._controlled_attached_gear(ctx.actor_side)
            if getattr(g, "tapped", False)]
    for g in sorted(gear, key=_zone_value, reverse=True)[:int(spec.get("count", 1))]:
        g.tapped = False


@effect("disempower_then_kill")
def _disempower_then_kill(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit. If it's EMPOWERED, disempower it. Then kill it if it has
    3 [might] or less" (Lacerate): the mightiest enemy that ends at 3 or less."""
    loop = ctx.loop
    cap = int(spec.get("might_at_most", 3))
    enemies = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "anywhere"))
    if not enemies:
        return

    def after(u):
        was = u.empowered
        u.empowered = False
        loop._recompute_passives()
        m = u.might
        u.empowered = was
        loop._recompute_passives()
        return m
    killable = [u for u in enemies if after(u) <= cap]
    unit = max(killable or enemies, key=lambda u: (u.empowered, u.might))
    loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    unit.empowered = False
    loop._recompute_passives()
    if unit.might <= cap:
        where = loop._locate_unit(unit)
        if where[1] is None:
            ctx.opponent.base_units.remove(unit)
        else:
            where[1].remove_unit(ctx.opponent_side, unit)
        loop._route_deaths([(unit, ctx.opponent_side)], where[1] or loop.gs.battlefields[0],
                           in_base=where[1] is None)


@effect("move_empowerment")
def _move_empowerment(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may disempower something you control to empower a legend, unit, or
    gear" (Profiteer): only when an EMPOWERED ability would gain from it."""
    loop = ctx.loop
    side = ctx.actor_side
    mine = _units_at(ctx, side, "anywhere")
    legend = loop._legend_unit(side)
    holders = [u.card for u in mine + ([legend] if legend else [])] + \
        list(ctx.actor.base_gear) + loop._controlled_attached_gear(side)
    src = next((c for c in holders if loop._is_empowered(c) and not _uses_empowered(c)), None)
    dst = next((c for c in holders if not loop._is_empowered(c) and _uses_empowered(c)), None)
    if src is not None and dst is not None:
        loop._disempower(src)
        loop._empower(dst, side)


def _uses_empowered(card) -> bool:
    spec = CARD_REGISTRY.get(card.name)
    return bool(spec) and any((es.condition or {}).get("type") == "this_is_empowered"
                              for es in spec.effects)


@effect("unattach_and_damage_holder")
def _unattach_and_damage_holder(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Unattach this and deal 4 to me" (Blighted Battleaxe): the Equipment goes
    to base, its unit takes the damage."""
    holder = ctx.extra.get("triggering_unit")
    if holder is None or ctx.card not in holder.gear:
        return
    holder.gear.remove(ctx.card)
    where = ctx.loop._locate_unit(holder)
    if where is not None:
        ctx.loop.gs.get_player(where[0]).base_gear.append(ctx.card)
    ctx.damage_units([holder], int(spec.get("amount", 4)))


@effect("attach_equipment")
def _attach_equipment(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Attach a detached Equipment you control to a unit you control" (Jax
    Grandmaster at Arms; `from: attached` moves one from a unit in base): to
    the mightiest unit at a battlefield, else any."""
    loop = ctx.loop
    mine = _units_at(ctx, ctx.actor_side, "anywhere")
    at_bf = [u for u in mine if loop._locate_unit(u)[1] is not None]
    if not mine:
        return
    if str(spec.get("from", "detached")) == "attached":
        holders = [u for u in mine if u.gear and loop._locate_unit(u)[1] is None]
        gear = next((g for u in holders for g in u.gear if loop._equip_cost(g) is not None), None)
        if gear is None or not at_bf:
            return
        next(u for u in holders if gear in u.gear).gear.remove(gear)
        target = max(at_bf, key=lambda u: u.might)
    else:
        gear = next((g for g in ctx.actor.base_gear if loop._equip_cost(g) is not None), None)
        if gear is None:
            return
        ctx.actor.base_gear.remove(gear)
        target = max(at_bf or mine, key=lambda u: u.might)
    target.gear.append(gear)
    loop._fire_attached(target, ctx.actor_side)


@effect("arise")
def _arise(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Play a 2 [might] Sand Soldier unit token for each Equipment you
    control. Then do this: Ready up to two of them." (Arise!)"""
    n = _amount(ctx, {"amount_source": "equipment_you_control"})
    played = [ctx.loop._play_token(str(spec.get("token_name", "Sand Soldier")), ctx.actor_side,
                                   might=int(spec.get("might", 2)))
              for _ in range(n)]
    for unit in [u for u in played if u is not None][:int(spec.get("ready", 2))]:
        unit.ready = True


@effect("next_spell_bonus_damage")
def _next_spell_bonus_damage(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "The next spell you play this turn deals 1 Bonus Damage" (Ravenborn Tome)."""
    ctx.loop.gs.next_spell_bonus[ctx.actor_side] = ctx.loop.gs.turn


@effect("prevent_spell_damage_this_turn")
def _prevent_spell_damage_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Prevent all spell and ability damage this turn" (Unyielding Spirit)."""
    ctx.loop.gs.no_spell_damage_turn = ctx.loop.gs.turn


@effect("kill_damaged_this_turn")
def _kill_damaged_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When any unit takes damage this turn, kill it" (Imperial Decree)."""
    ctx.loop.gs.decree_turn = ctx.loop.gs.turn


@effect("damage_shield")
def _damage_shield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Prevent the next 7 damage that would be dealt to it this turn" (Ki
    Barrier): the friendly unit losing its fight, else the mightiest."""
    mine = _choosable(ctx, _units_at(ctx, ctx.actor_side, "anywhere"))
    if not mine:
        return

    def threatened(u):
        where = ctx.loop._locate_unit(u)
        bf = where[1] if where else None
        enemy = sum(x.might for x in bf._units_for(ctx.opponent_side)) if bf else 0
        return (enemy >= u.might - u.damage, u.might)
    unit = max(mine, key=threatened)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    unit.damage_shield += int(spec.get("amount", 7))


@effect("double_damage_this_turn")
def _double_damage_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit. Double all damage that would be dealt to it this turn"
    (Lotus Trap): an enemy unit, the mightiest at a battlefield."""
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        unit.double_damage_turn = ctx.loop.gs.turn


@effect("double_shield")
def _double_shield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Double the SHIELD of a unit you control here this turn" (K'Sante
    Dauntless): the unit here with the most SHIELD."""
    units = [u for u in ctx.battlefield._units_for(ctx.actor_side) if u.keyword_value("SHIELD")]
    if units:
        unit = max(units, key=lambda u: u.keyword_value("SHIELD"))
        unit.turn_keywords.append(f"SHIELD {unit.keyword_value('SHIELD')}")


@effect("unit_split_damage")
def _unit_split_damage(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit. It deals damage equal to its Might split among
    enemy units at battlefields. Then for each unit this kills: Gain 1 XP"
    (Alpha Strike): the mightiest friendly unit, killing the toughest enemies
    it can, the rest on the next."""
    mine = _units_at(ctx, ctx.actor_side, "anywhere")
    enemies = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "battlefield"))
    if not mine or not enemies:
        return
    source = max(mine, key=lambda u: u.might)
    pool = source.might
    plan = []
    for e in sorted(enemies, key=lambda u: u.might - u.damage):
        need = max(1, e.might - e.damage)
        if need <= pool:
            plan.append((e, need))
            pool -= need
    if pool and len(plan) < len(enemies):
        rest = [e for e in enemies if all(e is not p for p, _ in plan)]
        plan.append((max(rest, key=lambda u: u.might), pool))
    elif pool and plan:
        plan[-1] = (plan[-1][0], plan[-1][1] + pool)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [source] + [e for e, _ in plan])
    for e, n in plan:
        ctx.damage_units([e], n)
    alive = {id(u) for u in _units_at(ctx, ctx.opponent_side, "anywhere")}
    killed = sum(1 for e, _ in plan if id(e) not in alive)
    if killed:
        ctx.loop.gs.add_xp(ctx.actor_side, killed)


@effect("damage_unless_draw")
def _damage_unless_draw(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an enemy unit. Deal 6 to it unless its controller has you draw
    2" (Shakedown): they let you draw when the damage would kill it."""
    amount = int(spec.get("amount", 6))
    enemies = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "anywhere"))
    if not enemies:
        return
    unit = max(enemies, key=lambda u: (amount >= u.might - u.damage, u.might))
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    if amount >= unit.might - unit.damage:
        ctx.draw_cards(int(spec.get("draw", 2)), target="actor")
    else:
        ctx.damage_units([unit], amount)


@effect("cant_be_chosen_this_turn")
def _cant_be_chosen_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "It can't be chosen by enemy spells and abilities this turn" (Twilight
    Shroud)."""
    for unit in _resolve_targets(ctx, spec):
        unit.cant_be_chosen_turn = ctx.loop.gs.turn


@effect("opponents_cant_play_cards")
def _opponents_cant_play_cards(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Opponents can't play cards this turn" (Brynhir Thundersong)."""
    ctx.loop.gs.cant_play_cards_turn[ctx.opponent_side] = ctx.loop.gs.turn


@effect("name_spell")
def _name_spell(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Name a spell" (Fallen Feline): baseline, the costliest spell in the
    opponent's trash (they play it again), else none."""
    spells = [c for c in ctx.opponent.trash if isinstance(c, SpellCard)]
    if spells:
        ctx.card._named_spell = max(spells, key=_zone_value).name


@effect("win_game")
def _win_game(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You win the game" (The Grand Plaza, Gutter Palace)."""
    gs = ctx.loop.gs
    if ctx.actor_side == "A":
        gs.points_A = max(gs.points_A, gs.victory_score)
    else:
        gs.points_B = max(gs.points_B, gs.victory_score)


@effect("move_self_to_weaker_enemy_battlefield")
def _move_self_to_weaker_enemy_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Move me to an occupied enemy battlefield if my Might is greater than
    the total Might of enemy units there" (Maduli the Gatekeeper)."""
    me = _source_unit(ctx)
    if me is None:
        return
    gs = ctx.loop.gs
    opts = [bf for bf in gs.battlefields if bf._units_for(ctx.opponent_side)
            and me.might > sum(u.might for u in bf._units_for(ctx.opponent_side))
            and ctx.loop._locate_unit(me)[1] is not bf]
    if opts:
        ctx.loop._move_unit_by_effect(me, max(opts, key=lambda bf: len(bf._units_for(ctx.opponent_side))))


@effect("ready_or_exhaust_legend")
def _ready_or_exhaust_legend(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Ready or exhaust a legend" (Royal Entourage): ready yours if it is
    exhausted, else exhaust the opponent's."""
    loop = ctx.loop
    mine, theirs = loop._legend_unit(ctx.actor_side), loop._legend_unit(ctx.opponent_side)
    if mine is not None and not mine.ready:
        mine.ready = True
        loop._fire_readied(mine, ctx.actor_side)
    elif theirs is not None and theirs.ready:
        loop._exhaust(theirs)


@effect("draw_on_next_unit_plays")
def _draw_on_next_unit_plays(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "The next three times you play a unit this turn, draw 1" (Fanfare)."""
    gs = ctx.loop.gs
    gs.unit_play_draws[ctx.actor_side] = [gs.turn, int(spec.get("count", 3))]


@effect("hand_to_deck_bottom")
def _hand_to_deck_bottom(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Put a card from your hand on the top or bottom of your Main Deck"
    (Altar of Memories): the costliest card goes to the bottom."""
    hand = ctx.actor.hand
    if hand:
        card = max(hand, key=_zone_value)
        hand.remove(card)
        ctx.actor.deck.cards.insert(0, card)


def _unit_leaves_to(ctx: "EffectContext", unit, side: str, to: str) -> None:
    """Take a unit off the board to its owner's hand or the top of their Main
    Deck (`to`: "hand" / "deck_top"); its gear goes to its owner's hand when
    the unit goes to hand, else to base. A token ceases to exist."""
    loop = ctx.loop
    where = loop._locate_unit(unit)
    if where is None:
        return
    owner = loop.gs.get_player(side)
    if where[1] is None:
        owner.base_units.remove(unit)
    else:
        where[1].remove_unit(side, unit)
    if to == "hand":
        owner.hand.extend(g for g in unit.gear if not getattr(g, "is_token", False))
    else:
        owner.base_gear.extend(unit.gear)
    unit.gear = []
    loop._fire_leaves_board(unit.card, side, where[1] or loop.gs.battlefields[0])
    if unit.is_token:
        return
    if to == "hand":
        owner.hand.append(unit.card)
    else:
        owner.deck.cards.append(unit.card)


@effect("return_all_to_hand")
def _return_all_to_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Return all units and gear to their owners' hands" (Downwell)."""
    loop = ctx.loop
    for side in ("A", "B"):
        player = loop.gs.get_player(side)
        for unit in _units_at(ctx, side, "anywhere"):
            _unit_leaves_to(ctx, unit, side, "hand")
        for gear in list(player.base_gear):
            player.base_gear.remove(gear)
            if not getattr(gear, "is_token", False):
                player.hand.append(gear)
        for bf in loop.gs.battlefields:
            for dg in list(bf.gear_for(side)):
                bf.gear_for(side).remove(dg)
                if not getattr(dg.card, "is_token", False):
                    player.hand.append(dg.card)


@effect("keep_one_kill_rest")
def _keep_one_kill_rest(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Each player chooses a unit they control. Kill the rest." (Cataclysmic
    Duel): each keeps their mightiest."""
    loop = ctx.loop
    for side in ("A", "B"):
        units = _units_at(ctx, side, "anywhere")
        if len(units) < 2:
            continue
        keep = max(units, key=lambda u: u.might)
        by_bf = {}
        for unit in units:
            if unit is keep:
                continue
            where = loop._locate_unit(unit)
            if where[1] is None:
                loop.gs.get_player(side).base_units.remove(unit)
            else:
                where[1].remove_unit(side, unit)
            by_bf.setdefault(id(where[1]), (where[1], []))[1].append((unit, side))
        for bf, dead in by_bf.values():
            loop._route_deaths(dead, bf or loop.gs.battlefields[0], in_base=bf is None)


@effect("tuck_unit")
def _tuck_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an enemy unit at a battlefield. Its owner places it on the top or
    bottom of their Main Deck" (Keeper's Verdict): the mightiest; its owner
    puts it on top."""
    enemies = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "battlefield"))
    if enemies:
        unit = max(enemies, key=lambda u: u.might)
        ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
        _unit_leaves_to(ctx, unit, ctx.opponent_side, "deck_top")


@effect("each_player_bounces")
def _each_player_bounces(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Starting with the next player, each player may return a unit to its
    owner's hand" (Whirlwind): each returns the other's mightiest unit."""
    for chooser, victim in ((ctx.opponent_side, ctx.actor_side), (ctx.actor_side, ctx.opponent_side)):
        units = [u for u in _units_at(ctx, victim, "anywhere") if ctx.loop._can_choose(u, chooser)]
        if units:
            _unit_leaves_to(ctx, max(units, key=lambda u: u.might), victim, "hand")


@effect("activate_conquer_effects")
def _activate_conquer_effects(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When you hold here, activate the conquer effects of units here"
    (Reckoner's Arena)."""
    loop = ctx.loop
    for unit in list(ctx.battlefield._units_for(ctx.actor_side)):
        for card in [unit.card] + list(unit.gear):
            loop._resolve_triggered_effects(card, "on_conquer", ctx.battlefield, ctx.actor,
                                            ctx.opponent, context_extra={"battlefield": ctx.battlefield})


@effect("play_self_from_trash")
def _play_self_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "... you may pay [fury] to play me" from the trash (Flame Chompers):
    the cost is the effect's `cost`, paid before this runs."""
    if ctx.card in ctx.actor.trash:
        ctx.actor.trash.remove(ctx.card)
        ctx.loop._play_from_zone_now(ctx.actor, ctx.card, ctx.actor_side, "trash")


@effect("sacrifice_for_points")
def _sacrifice_for_points(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may kill 3 other friendly units and/or gear to score 1 point"
    (Bottled Constellation). Baseline: only when `count` tokens (units or gear)
    can pay it, so no real card is thrown away."""
    loop = ctx.loop
    me, side = ctx.actor, ctx.actor_side
    count = int(spec.get("count", 3))
    units = [u for u in _units_at(ctx, side, "anywhere") if u.is_token]
    gear = [g for g in me.base_gear if getattr(g, "is_token", False) and g is not ctx.card]
    if len(units) + len(gear) < count:
        return
    for g in gear[:count]:
        loop._remove_gear(g, me)
    for u in units[:max(0, count - len(gear))]:
        where = loop._locate_unit(u)
        if where[1] is None:
            me.base_units.remove(u)
        else:
            where[1].remove_unit(side, u)
        loop._route_deaths([(u, side)], where[1] or loop.gs.battlefields[0])
    _score_point(ctx, {"amount": int(spec.get("amount", 1))})


@effect("banish_top_playable")
def _banish_top_playable(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Banish the top card of your Main Deck. Until your next Ending Phase,
    you may play that card. (You still pay its costs.)" (Runeblade Anvil,
    Akali Brash): GameLoop offers it as a "banished_play" ability until the
    end of the player's next turn (this turn, if it is theirs)."""
    player, side = ctx.actor, ctx.actor_side
    if not player.deck.cards:
        return
    card = player.deck.cards.pop()
    player.banished.append(card)
    ctx.loop._note_banished(side)
    gs = ctx.loop.gs
    card._banish_play_side = side
    card._banish_play_until = gs.turn if gs.active == side else gs.turn + 1


@effect("reveal_play_top")
def _reveal_play_top(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Reveal (or look at) cards from the top of a Main Deck, banish one and
    play it (Blind Fury, Drakehound Packmaster, Void Rush, Rek'Sai, Dazzling
    Aurora, Baited Hook, Clocktower Guardian, Wild Claw, Promising Future).
    - `source`: "own" (default) or "opponent" (their deck; you play it).
      `each_player`: every player does it with their own deck, the opponent
      first ("Starting with the next player").
    - `look` (default 1) cards, or `until` a card of that type ("unit").
    - which can be played: `filter` / `target_filter`; `kill_friendly`: first
      kill your weakest unit, then only cards with Might up to `might_margin`
      more than it (Baited Hook).
    - `pay`: "ignore" (default), "ignore_energy" (still pay its Power),
      "cost" (pay it), or "reduce" by `reduce` Energy.
    - `rest`: "recycle" (default), "draw" (yours), "banish" or "trash".
    Baseline pick: the most expensive playable card."""
    loop = ctx.loop
    if spec.get("each_player"):
        for side in (ctx.opponent_side, ctx.actor_side):
            _reveal_play_for(ctx, spec, side, side)
    elif str(spec.get("source", "own")).lower() == "opponent":
        _reveal_play_for(ctx, spec, ctx.actor_side, ctx.opponent_side)
    else:
        _reveal_play_for(ctx, spec, ctx.actor_side, ctx.actor_side)
    loop._recompute_passives()


def _reveal_play_for(ctx: "EffectContext", spec: Mapping[str, Any], chooser_side: str,
                     owner_side: str) -> None:
    loop = ctx.loop
    gs = loop.gs
    chooser, owner = gs.get_player(chooser_side), gs.get_player(owner_side)
    might_cap = None
    if spec.get("kill_friendly"):
        mine = [u for u in _units_at(ctx, chooser_side, "anywhere") if not u.is_token]
        if not mine:
            return
        victim = min(mine, key=lambda u: u.might)
        might_cap = victim.might + int(spec.get("might_margin", 1))
        where = loop._locate_unit(victim)
        if where[1] is None:
            chooser.base_units.remove(victim)
        else:
            where[1].remove_unit(chooser_side, victim)
        loop._route_deaths([(victim, chooser_side)], where[1] or gs.battlefields[0])
    deck = owner.deck.cards
    revealed = []
    until = spec.get("until")
    if until:
        while deck:
            revealed.append(deck.pop())
            if _zone_effect_card_ok(revealed[-1], {"filter": until}):
                break
    else:
        for _ in range(min(int(spec.get("look", 1)), len(deck))):
            revealed.append(deck.pop())
    match = {"filter": spec.get("filter") or until, "target_filter": spec.get("target_filter") or {}}
    cands = [c for c in revealed if _zone_effect_card_ok(c, match)]
    if might_cap is not None:
        cands = [c for c in cands if int(getattr(c, "might", 0) or 0) <= might_cap]
    mode = str(spec.get("pay", "ignore")).lower()

    def price(card):
        """(Energy, Power) to pay for `card` under this effect, or None if the
        chooser can't."""
        if mode == "ignore":
            return 0, 0
        if mode == "ignore_energy":
            power = int(card.cost_power or 0)
            ok = (chooser.can_pay_cost(0, power, card.cost_power_domain) if card.cost_power_domain
                  else loop._can_pay_generic_power(chooser, power))
            return (0, power) if ok else None
        energy, power = loop._effective_cost(card, chooser)
        if mode == "reduce":
            energy = max(0, energy - int(spec.get("reduce", 0)))
        return (energy, power) if loop._can_pay_card(chooser, card, energy, power) else None

    playable = [c for c in cands if price(c) is not None]
    pick = max(playable, key=_zone_value) if playable else None
    if pick is not None:
        revealed.remove(pick)
        energy, power = price(pick)
        if mode == "ignore_energy":
            if power:
                if pick.cost_power_domain:
                    chooser.pay_cost(0, power, pick.cost_power_domain)
                else:
                    loop._pay_generic_power(chooser, power)
        elif mode != "ignore":
            loop._pay_card(chooser, pick, energy, power)
        if loop.verbose:
            print(f"  {chooser.name} banishes and plays {pick.name}")
        if owner is chooser:
            loop._note_banished(chooser_side)
        loop._play_from_zone_now(chooser, pick, chooser_side, "banished")
        if spec.get("empower") and loop._locate_unit_or_gear(pick, chooser_side):
            loop._empower(pick, chooser_side)          # Wild Claw: "Empower it."
    rest = str(spec.get("rest", "recycle")).lower()
    for card in revealed:
        if rest == "draw" and owner is chooser:
            chooser.hand.append(card)
        elif rest == "banish":
            owner.banished.append(card)
        elif rest == "trash":
            owner.trash.append(card)
        else:
            deck.insert(0, card)      # recycle: to the bottom


@effect("cant_move_this_turn")
def _cant_move_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "They can't move it this turn" (Vex Apathetic): no Standard Move."""
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "triggering_unit")}):
        unit.cant_move_turn = ctx.loop.gs.turn


@effect("give_gear_temporary")
def _give_gear_temporary(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Give a gear TEMPORARY" (Turn to Dust): it dies at the start of its
    controller's next Beginning Phase. Baseline pick: the opponent's most
    expensive gear (attached, in base or deployed), else none."""
    entries = [(side, holder, g) for side, holder, g in _gear_entries(ctx, enemy_first=True)
               if side == ctx.opponent_side]
    if not entries:
        return
    side, holder, gear = max(entries, key=lambda e: int(getattr(getattr(e[2], "card", e[2]),
                                                                 "cost_energy", 0) or 0))
    if isinstance(holder, Battlefield):
        holder.gear_for(side).remove(gear)        # a deployed gear: give it base status
        ctx.loop.gs.get_player(side).base_gear.append(gear.card)
        gear = gear.card
    gear._temporary = True


@effect("blink_unit")
def _blink_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Banish a friendly unit, then its owner plays it to any battlefield,
    ignoring its cost" (Thrill of the Hunt): it leaves the board (its gear goes
    to base) and is played again through the play procedure ("when you play
    me" fires again) at `destination` "any_battlefield" (where it attacks
    best) or "same_location". Baseline pick: the friendly unit with the best
    destination, then the mightiest."""
    loop = ctx.loop
    gs = loop.gs
    me = ctx.actor_side
    units = [u for u in _units_at(ctx, me, "anywhere") if not u.is_token]
    tf = spec.get("target_filter")
    if tf:
        units = [u for u in units if _passes_filter(u, tf, ctx)]
    if not units:
        return
    dest = str(spec.get("destination", "any_battlefield")).lower()

    def place(unit):
        where = loop._locate_unit(unit)
        if dest == "same_location":
            return where[1] if where else None
        if dest == "base":
            return None
        return max(gs.battlefields, key=lambda bf: _attack_value(ctx, me, unit, bf))

    if dest == "base":
        # "plays it to their base": save the unit losing its fight, else the mightiest.
        def losing(u):
            where = loop._locate_unit(u)
            bf = where[1] if where else None
            return bf is not None and sum(x.might for x in bf._units_for(ctx.opponent_side)) > \
                sum(x.might for x in bf._units_for(me))
        unit = max(units, key=lambda u: (losing(u), u.might))
    else:
        unit = max(units, key=lambda u: (_attack_value(ctx, me, u, place(u)) if place(u) else 0, u.might))
    bf = place(unit)
    where = loop._locate_unit(unit)
    if where is None:
        return
    side, src_bf = where
    owner = gs.get_player(side)
    if src_bf is None:
        owner.base_units.remove(unit)
    else:
        src_bf.remove_unit(side, unit)
    owner.base_gear.extend(unit.gear)
    loop._fire_leaves_board(unit.card, side, src_bf or gs.battlefields[0])
    loop._play_unit(unit.card, side, bf=bf, from_zone="banished")


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
    if spec.get("amount") is not None and target in _CHOOSER_TARGETS:
        # "Ready up to 4 units": the controller's exhausted units, mightiest first.
        exhausted = sorted((u for u in _friendly_units(ctx) if not u.ready and ctx.loop._can_ready(u)),
                           key=lambda u: u.might, reverse=True)
        for unit in exhausted[:int(spec["amount"])]:
            unit.ready = True
            ctx.loop._fire_readied(unit, ctx.actor_side)
        return
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
    floor = spec.get("minimum", spec.get("min_might"))
    for unit in _resolve_targets(ctx, spec):
        if amount < 0 and floor is not None:
            # "-2 [might] this turn, to a minimum of 1 [might]"
            unit.temporary_might -= min(-amount, max(0, unit.might - int(floor)))
        else:
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
    floor = int(spec.get("min_floor", spec.get("minimum", 0)))
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
        if not ctx.loop._can_ready(unit):
            continue
        was_ready = unit.ready
        unit.ready = True
        if not was_ready:
            where = ctx.loop._locate_unit(unit)
            if where is not None:
                ctx.loop._fire_readied(unit, where[0])


@effect("score_point")
def _score_point(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 1))
    side = _target_side(ctx, str(spec.get("target", "actor")))
    if ctx.loop._gain_points(side, amount, "effect"):
        ctx.loop._fire_units_trigger("on_opponent_scores", ctx.loop.gs.other(side))


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
    owner = ctx.loop.gs.get_player(target_item.player)
    tax = int(spec.get("unless_pays", 0) or 0)
    if tax and owner.energy >= tax:
        owner.energy -= tax          # "unless its controller pays [2]": they do
        return
    chain.pop()
    if spec.get("return_to_hand"):
        owner.hand.append(target_card)
    else:
        ctx.loop._spell_to_trash(owner, target_card)


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
            where = ctx.loop._locate_unit(unit)
            if where is not None:   # "When you buff me" (Simian Ancestor)
                bf = where[1] or ctx.loop.gs.battlefields[0]
                ctx.loop._resolve_triggered_effects(unit.card, "on_buffed", bf,
                                                    ctx.loop.gs.get_player(where[0]),
                                                    ctx.loop.gs.get_player(ctx.loop.gs.other(where[0])),
                                                    context_extra={"battlefield": bf})
                if where[0] == ctx.actor_side:   # "When you buff a friendly unit" (Mistfall)
                    ctx.loop._fire_units_trigger("on_friendly_unit_buffed", where[0],
                                                 triggering_card=unit.card,
                                                 extra={"triggering_unit": unit})


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
    if "subtype" in tf and str(tf["subtype"]) not in (getattr(unit, "tags", None) or card.tags or []):
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
_EVERYWHERE_TARGETS = {
    "all_friendly_units_anywhere": ("friendly", "anywhere"),
    "all_enemy_units_anywhere": ("enemy", "anywhere"),
    "all_units_anywhere": ("both", "anywhere"),
    "all_units_in_bases": ("both", "base"),
    "enemy_unit_in_base": ("enemy", "base"),     # "an enemy unit in a base" (Yone)
}

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
    if target in _EVERYWHERE_TARGETS:
        # "Give friendly units +5" / "Deal 3 to all units in bases": not only here.
        who, where = _EVERYWHERE_TARGETS[target]
        sides = {"friendly": [ctx.actor_side], "enemy": [ctx.opponent_side],
                 "both": [ctx.actor_side, ctx.opponent_side]}[who]
        units = [u for s in sides for u in _units_at(ctx, s, where)]
    elif target in _BOTH_SIDES_TARGETS:
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
    if not units and scope == "single" and not target.startswith("all")             and not isinstance(ctx.card, SpellCard) and target not in _BOTH_SIDES_TARGETS:
        # An ability or trigger isn't aimed at one battlefield the way a spell is
        # (a legend's "give a unit ASSAULT 2"): with no candidate here, look at
        # the other battlefields, then base.
        units = _fallback_units(ctx, target, bias)
        if tf:
            units = [u for u in units if _passes_filter(u, tf, ctx)]
    if not units:
        return []
    if scope != "single" or target.startswith("all"):
        return list(units)
    # Units picked one by one ("a unit", "up to two units" = count): that's a
    # choice, for "when you choose me" and "you've chosen enemy units twice".
    units = _choosable(ctx, units)
    picked = units[:max(1, int(spec.get("count", 1) or 1))]
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, picked)
    return picked


def _choosable(ctx: "EffectContext", units: list) -> list:
    """The units this effect's controller may choose (GameLoop._can_choose)."""
    return [u for u in units if ctx.loop._can_choose(u, ctx.actor_side)]


def _fallback_units(ctx: "EffectContext", target: str, bias: str) -> list:
    """Candidates for a single-unit target anywhere: the other battlefields, then
    base, for the side(s) the target names."""
    gs = ctx.loop.gs
    me, them = ctx.actor_side, ctx.opponent_side
    if target in _CHOOSER_TARGETS:
        sides = [them, me] if bias == "enemy" else [me, them]
    else:
        try:
            player = ctx._player_for_target(target)
        except ValueError:
            return []
        sides = [ctx._side_for_player(player)]
    units = []
    for side in sides:
        units += [u for bf in gs.battlefields if bf is not ctx.battlefield for u in bf._units_for(side)]
        units += list(gs.get_player(side).base_units)
    return units


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
    if src == "gear_you_control":
        loop = ctx.loop
        return len(ctx.actor.base_gear) + len(loop._controlled_attached_gear(ctx.actor_side)) + \
            sum(len(bf.gear_for(ctx.actor_side)) for bf in loop.gs.battlefields)
    if src == "enemies_here":
        return len(ctx._units_for_side(ctx.opponent_side))
    if src == "friendly_units_here":
        return len(ctx._units_for_side(ctx.actor_side))
    if src == "n_friendly_with_tag":
        tag = str(spec.get("tag", ""))
        return sum(1 for u in _friendly_units(ctx) if tag in u.tags)
    if src == "n_distinct_tags_among_friendlies":
        return len({t for u in _friendly_units(ctx) for t in u.tags})
    if src == "cards_with_my_name_in_trash":
        return sum(1 for c in ctx.actor.trash if c.name == ctx.card.name and c is not ctx.card)
    if src == "battlefields_conquered_this_turn":
        return int(ctx.loop.gs.conquered_this_turn.get(ctx.actor_side, 0))
    if src == "hold_points_this_turn":
        return int(ctx.loop.gs.hold_points_this_turn.get(ctx.actor_side, 0))
    if src == "cards_played_this_turn":
        return int(ctx.loop.gs.cards_played_this_turn.get(ctx.actor_side, 0))
    if src == "own_equipment":
        # "for each Equipment attached to me" (Riven Shattered), times `per`.
        u = _source_unit(ctx)
        n = sum(1 for g in (u.gear if u else []) if ctx.loop._equip_cost(g) is not None)
        return n * int(spec.get("per", 1))
    if src == "equipment_you_control":
        loop = ctx.loop
        gear = list(ctx.actor.base_gear) + loop._controlled_attached_gear(ctx.actor_side)
        return sum(1 for g in gear if loop._equip_cost(g) is not None)
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
    if target in ("self", "this"):
        # "Kill this" (Runeblade Anvil's ability).
        entries = [(s, h, g) for (s, h, g) in entries if getattr(g, "card", g) is ctx.card]
    elif single:
        entries = entries[:1]

    for side, holder, gear in entries:
        player = gs.get_player(side)
        if isinstance(holder, Battlefield):
            ctx.loop._kill_deployed_gear(holder, side, [gear])
            continue
        if holder is not None:
            if gear not in holder.gear:
                continue
            holder.gear.remove(gear)
        elif gear in player.base_gear:
            player.base_gear.remove(gear)
        else:
            continue
        ctx.loop._to_trash(player, gear)
        ctx.loop._gear_left_board(gear, side)


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
    if not target.startswith("all"):
        candidates = [(s, u) for s, u in candidates if loop._can_choose(u, me)]
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
            if spec.get("ready") and loop._can_ready(unit):
                unit.ready = True
            moved += 1


@effect("give_keyword")
def _give_keyword(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    keyword = str(spec.get("keyword", "")).strip()
    if not keyword:
        return
    this_turn = str(spec.get("duration", "")).lower() == "this_turn"
    for unit in _resolve_targets(ctx, spec):
        (unit.turn_keywords if this_turn else unit.granted_keywords).append(keyword)


def _give_temp_keyword(ctx: "EffectContext", spec: Mapping[str, Any], kw: str) -> None:
    amount = int(spec.get("amount", 1))
    token = f"{kw} {amount}"
    for unit in _resolve_targets(ctx, spec):
        unit.turn_keywords.append(token)    # "this turn"


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
    if "is_token" in tf and bool(getattr(card, "is_token", False)) != bool(tf["is_token"]):
        return False
    if "power_at_least" in tf and power < int(tf["power_at_least"]):
        return False
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
        ctx.loop._discard(player, player.hand[0])


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
    if spec.get("buff_by_burned_unit"):
        # "When you burn a unit this way, give a friendly unit +[might] equal to
        # the burned card's Might this turn" (Forgotten Relic): the mightiest
        # friendly unit at a battlefield, else any.
        from .cards import UnitCard
        mine = _units_at(ctx, ctx.actor_side, "anywhere")
        at_bf = [u for u in mine if ctx.loop._locate_unit(u)[1] is not None]
        for card in burned:
            if isinstance(card, UnitCard) and (at_bf or mine):
                max(at_bf or mine, key=lambda u: u.might).temporary_might += int(card.might or 0)


@effect("empower_self")
def _empower_self(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Vendetta EMPOWER: give the source unit the empowered status. Usually an
    activated ability (`trigger: activated`) whose cost the player pays first, but
    also usable from a trigger ("when ..., empower me"). Idempotent."""
    loop = ctx.loop
    target = str(spec.get("target", "self")).lower()
    tf = spec.get("target_filter") or {}
    if target in ("self", "this", "me"):
        loop._empower(ctx.card, ctx.actor_side)
    elif tf.get("is_gear"):
        # "Empower another gear" (Hextech Formula): one not yet empowered.
        gear = [g for g in list(ctx.actor.base_gear) + loop._controlled_attached_gear(ctx.actor_side)
                if g is not ctx.card and not getattr(g, "empowered", False)]
        if gear:
            loop._empower(max(gear, key=_zone_value), ctx.actor_side)
    else:
        for unit in _resolve_targets(ctx, {**spec, "target": target}):
            where = loop._locate_unit(unit)
            loop._empower(unit.card, where[0] if where else ctx.actor_side)
            if spec.get("until_end_of_turn") and not unit.empower_flip_at_end:
                unit.empower_flip_at_end = True     # Sanction: "Disempower it at end of turn"


@effect("disempower")
def _disempower(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Remove the empowered status from the resolved target(s). Used as an
    instruction or a cost ("disempower a unit that's EMPOWERED")."""
    target = str(spec.get("target", "enemy_unit"))
    if target in ("self", "this"):
        ctx.loop._disempower(ctx.card)
        return
    cands = _resolve_targets(ctx, {**spec, "target": target, "scope": "all"})
    cands = [u for u in _choosable(ctx, cands) if u.empowered] if spec.get("only_empowered", True) else cands
    for u in cands[:1] if str(spec.get("scope", "single")) == "single" else cands:
        u.empowered = False
        if spec.get("until_end_of_turn"):
            u.empower_flip_at_end = True             # "Empower it at end of turn"


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
    ("ready your runes") every rune is readied. The engine exhausts every rune
    for its Energy as the turn begins, so a readied rune is that Energy back:
    the rune is used again at once (it stays exhausted) for +1 Energy."""
    player = ctx._player_for_target(str(spec.get("target", "actor")))
    left = spec.get("amount")
    left = None if left is None else int(left)
    for runes in player.rune_pool.values():
        for rune in runes:
            if left is not None and left <= 0:
                return
            if not rune.ready:
                player.energy += 1
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
        ctx.loop._note_banished(ctx._side_for_player(player))


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