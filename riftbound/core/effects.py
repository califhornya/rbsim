from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from riftbound.registry.cards_registry import CARD_REGISTRY

from .battlefield import Battlefield
from .cards import GearCard, SpellCard, UnitCard
from .combat import UnitInPlay

EffectHandler = Callable[["EffectContext", Mapping[str, Any]], None]

REGISTRY: dict[str, EffectHandler] = {}


def effect(name: str) -> Callable[[EffectHandler], EffectHandler]:
    """Decorator used to register effect handlers by name."""

    key = name.strip()
    if not key:
        raise ValueError("Effect name cannot be empty")

    def decorator(func: EffectHandler) -> EffectHandler:
        # A second handler under one name silently replaced the first.
        if key in REGISTRY:
            raise ValueError(f"Effect {key!r} is registered twice")
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
    single target: an enemy over a friend, one the damage kills, the mightiest.
    `amount_source: its_damage`: each target takes the damage marked on it
    (Morgana Vindictive)."""
    its_damage = spec.get("amount_source") == "its_damage"
    amount = 0 if its_damage else _amount(ctx, spec)
    if spec.get("bonus_source"):
        # "This deals 1 Bonus Damage for each card with this name in your trash"
        # (Consuming Curse)
        amount += _amount(ctx, {"amount_source": spec["bonus_source"]})
    if amount > 0 and isinstance(ctx.card, GearCard):
        # "Abilities of friendly gear deal 1 Bonus Damage" (Ziggs Short-Fused)
        amount += sum(int(es.params.get("amount", 1)) for src, _bf in ctx.loop._sources_in_play(ctx.actor_side)
                      for es in (CARD_REGISTRY[src.name].effects if src.name in CARD_REGISTRY else ())
                      if es.trigger == "passive" and es.effect == "gear_ability_bonus_damage")
    if amount <= 0 and not its_damage:
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
        if not cands and not isinstance(ctx.card, SpellCard) and getattr(ctx.card, "_hidden_bf", None) is None:
            cands = _fallback_units(ctx, target, "enemy")
            if tf:
                cands = [u for u in cands if _passes_filter(u, tf, ctx)]
        enemies = ctx._units_for_side(ctx.opponent_side)
        enemy_ids = {id(u) for u in enemies}
        for bf in gs.battlefields:
            enemy_ids |= {id(u) for u in bf._units_for(ctx.opponent_side)}
        enemy_ids |= {id(u) for u in ctx.opponent.base_units}

        def value(u):
            dealt = u.damage if its_damage else amount
            kills = dealt > 0 and dealt >= max(0, u.might - u.damage)
            return (id(u) in enemy_ids and dealt > 0, kills, u.might)

        cands = sorted(_choosable(ctx, cands), key=value, reverse=True)
        units = ctx.loop.choose_many(_kind("target", spec), ctx.actor_side, cands,
                                     cands[:int(spec.get("count", 1))], ctx.card)
        if units:
            ctx.loop._note_chosen(ctx.card, ctx.actor_side, units)
        ctx.extra["it"] = units
    if its_damage:
        for u in units:
            if u.damage > 0:
                ctx.damage_units([u], u.damage)
        return
    if spec.get("banish_if_dies"):
        # "If it would die this turn, banish it instead" (Smite): this damage too.
        for u in units:
            u.banish_if_dies_turn = ctx.loop.gs.turn
    if spec.get("amount_if_attacking"):
        # "If it's attacking, deal 4 to it instead" (Sudden Storm)
        for u in units:
            ctx.damage_units([u], int(spec["amount_if_attacking"]) if ctx.loop._is_attacking(u) else amount)
    else:
        ctx.damage_units(units, amount)
    then = spec.get("then_if_killed")
    if then and any(ctx.loop._locate_unit(u) is None for u in units):
        # "If this kills it, do this: draw 1" (Disintegrate).
        handler = REGISTRY.get(then.get("effect"))
        if handler:
            handler(ctx, then)


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
    if target == "it_controller":
        # "Kill a unit ... Its controller draws 2" (Hidden Blade)
        side = ctx.extra.get("it_controller")
        if side is None:
            return
        target = "actor" if side == ctx.actor_side else "opponent"
    ctx.draw_cards(count, target=target, source=source)


@effect("gain_energy")
def _gain_energy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = int(spec.get("amount", 0))
    target = str(spec.get("target", "actor"))
    if spec.get("restriction") == "spells_only":
        # "Use only to play spells": earmarked, spent first on spells.
        ctx._player_for_target(target).earmarked_energy_spell += amount
        return
    if spec.get("restriction") == "units_only":
        # "Spend this Energy only to play units or activated abilities of units"
        # (Renekton Butcher of the Sands).
        ctx._player_for_target(target).earmarked_energy_unit += amount
        return
    ctx.gain_energy(amount, target=target)


@effect("mode_choice")
def _mode_choice(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Modal "choose one" (§ modal): the actor picks one mode; its sub-effect(s)
    resolve. A mode is either a single effect dict or a list of effect dicts.
    An agent's decide_mode picks; without a preference the baseline tries each
    mode on a copy of the game and takes the best (_best_mode). `choose: N`
    ("Choose two", Encore): N different modes, one after another."""
    modes = spec.get("modes") or []
    if not modes:
        return
    taken: set = set()
    for _ in range(max(1, int(spec.get("choose", 1) or 1))):
        if not _choose_one_mode(ctx, spec, modes, taken):
            return


def _choose_one_mode(ctx: "EffectContext", spec: Mapping[str, Any], modes: list, taken: set) -> bool:
    free = [j for j in range(len(modes)) if j not in taken and _mode_payable(ctx, modes[j])]
    used = None
    if spec.get("unique_per_turn"):
        # "Choose one that hasn't been chosen this turn" (Aphelios). Keyed by the
        # card itself, not id(): a cloned game (search) keeps the record.
        used = ctx.loop.gs.modes_chosen.setdefault((ctx.card, ctx.loop.gs.turn), set())
        free = [j for j in free if j not in used]
    if not free:
        return False
    agent = getattr(ctx.actor, "agent", None)
    i = None
    if agent is not None and hasattr(agent, "decide_mode"):
        try:
            i = agent.decide_mode(ctx.card, len(modes))
            i = None if i is None else max(0, min(int(i), len(modes) - 1))
        except Exception:  # noqa: BLE001
            i = None
    if i is None:
        i = _best_mode(ctx, modes, free)
    i = i if i in free else free[0]
    i = ctx.loop.choose("mode", ctx.actor_side, free, free[free.index(i)], ctx.card)
    if used is not None:
        used.add(i)
    taken.add(i)
    _run_mode(ctx, modes[i])
    return True


def _mode_payable(ctx: "EffectContext", mode) -> bool:
    """A mode that starts by spending the source's buff ("Spend my buff to STUN
    an enemy unit", Riven Broken Blade) can only be chosen while it has one; the
    buff is spent when the mode resolves. A mode's `condition` ("if there are
    no open battlefields": Demon Shade) and `additional_cost` ("Pay [chaos] to
    draw 1": Reckless Innovator) gate it too."""
    steps = mode if isinstance(mode, list) else [mode]
    if steps and steps[0].get("effect") == "spend_buff" and steps[0].get("target") == "self":
        src = _source_unit(ctx)
        return src is not None and src.might_counters > 0
    if steps and steps[0].get("condition") and not ctx.loop._check_condition(
            steps[0]["condition"], ctx.card, ctx.actor, ctx.opponent, ctx.extra):
        return False
    if steps and steps[0].get("additional_cost") and not ctx.loop._pay_one_additional_cost(
            ctx.card, ctx.actor, steps[0]["additional_cost"], check_only=True):
        return False
    return True


def _run_mode(ctx: "EffectContext", mode) -> None:
    for sub in mode if isinstance(mode, list) else [mode]:
        if sub.get("additional_cost") and not ctx.loop._pay_one_additional_cost(
                ctx.card, ctx.actor, sub["additional_cost"]):
            return
        handler = REGISTRY.get(sub.get("effect"))
        if handler:
            handler(ctx, sub)


def _best_mode(ctx: "EffectContext", modes: list, free: list) -> int:
    """Baseline "choose one": each mode resolved on a copy of the game, the one
    leaving the best position for its player (_position_value) wins; ties go to
    the first. A spell a mode counters counts as what it would have been worth.
    (One level only: a modal effect inside the copy takes its first mode.)"""
    import copy
    from .loop import EffectContext, GameLoop
    if len(free) < 2 or getattr(ctx.loop, "_lookahead", False):
        return free[0]
    gs = ctx.loop.gs
    best, best_value = free[0], None
    for j in free:
        memo = {id(p.agent): None for p in (gs.A, gs.B) if p.agent is not None}
        gs2, card2, bf2, extra2 = copy.deepcopy((gs, ctx.card, ctx.battlefield, ctx.extra), memo)
        loop2 = GameLoop(gs2)
        loop2._lookahead = True
        ctx2 = EffectContext(loop2, card2, gs2.get_player(ctx.actor_side),
                             gs2.get_player(ctx.opponent_side), bf2, extra2)
        chain_before = list(gs2.chain)
        try:
            _run_mode(ctx2, modes[j])
        except Exception:  # noqa: BLE001
            continue
        value = _position_value(gs2, ctx.actor_side)
        for item in chain_before:
            if not any(item is x for x in gs2.chain):     # countered
                worth = 1 + 1.5 * (int(item.card.cost_energy or 0) + int(item.card.cost_power or 0))
                value += worth if item.player != ctx.actor_side else -worth
        if best_value is None or value > best_value:
            best, best_value = j, value
    return best


def _position_value(gs, side: str) -> float:
    """A rough score of `side`'s position against the opponent's, to compare
    the results of a choice: each unit counts its Might left (0 if stunned:
    it deals no combat damage) + 1, each card in hand and rune 1, each point 4,
    each battlefield controlled 2."""
    def score(s: str) -> float:
        p = gs.get_player(s)
        units = [u for bf in gs.battlefields for u in bf._units_for(s)] + list(p.base_units)
        v = sum(1 + (0 if u.stunned else max(0, u.might - u.damage)) for u in units)
        v += len(p.hand) + sum(len(rs) for rs in p.rune_pool.values())
        v += len(p.base_gear) + sum(len(u.gear) for u in units) + \
            sum(len(bf.gear_for(s)) for bf in gs.battlefields)
        v += 4 * (gs.points_A if s == "A" else gs.points_B)
        v += 2 * sum(1 for bf in gs.battlefields if bf.control() == s)
        return v
    return score(side) - score(gs.other(side))


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
    less" (Astral Heron, Raging Firebrand): used by that card (filter). `then`:
    an effect that card gets at the end of the turn ("give it 'Kill me at end of
    the turn'": Ekko Boy Who Shattered Time)."""
    ctx.loop.gs.next_card_discounts[ctx.actor_side].append({
        "filter": dict(spec.get("filter") or {}),
        "energy": int(spec.get("energy", 0)),
        "power": int(spec.get("power", 0)),
        "then": dict(spec["then"]) if spec.get("then") else None,
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
    "two units", two enemies when there are two). The enemy is anywhere,
    `where: battlefield` "an enemy unit at a battlefield" (Marching Orders). Baseline pick: the enemy our unit kills without dying, else
    one it kills, else one it survives, mightiest first; our mightiest unit.
    `friendly_might` / `enemy_might`: "Give an enemy unit -2 [might] this turn
    and a friendly unit +2 [might] this turn. They deal damage ..." (Realm of
    Death), given to the two chosen before they deal it."""
    loop = ctx.loop
    gs = loop.gs
    me, them = ctx.actor_side, ctx.opponent_side
    mod_a, mod_b = int(spec.get("friendly_might", 0)), int(spec.get("enemy_might", 0))
    enemies = _choosable(ctx, _units_at(ctx, them, str(spec.get("where", "anywhere"))))
    first = str(spec.get("first", "friendly")).lower()
    if first == "any" and len(enemies) >= 2:
        a, b = sorted(enemies, key=lambda u: u.might, reverse=True)[:2]
    else:
        if first == "it":
            # "Choose a friendly unit and an enemy unit. If you paid ..., give the
            # friendly unit +2 [might]. They deal damage ..." (Rampage)
            it = [u for u in ctx.extra.get("it") or [] if loop._locate_unit(u) is not None]
            mine = _units_at(ctx, me, "anywhere")
            a = it[0] if it else loop.choose(_kind("target", spec), me, mine,
                                              max(mine, key=lambda u: u.might), ctx.card) if mine else None
        elif first == "self":
            a = _source_unit(ctx)
        else:
            mine = _units_at(ctx, me, "anywhere")
            a = max(mine, key=lambda u: u.might) if mine else None
        if a is None or not enemies:
            return

        def value(e):
            kills = a.might + mod_a >= e.might + mod_b - e.damage
            survives = e.might + mod_b < a.might + mod_a - a.damage
            return (kills and survives, kills, survives, e.might)
        b = loop.choose(_kind("target", spec), me, enemies, max(enemies, key=value), ctx.card)
    loop._note_chosen(ctx.card, me, [a, b])
    for unit, amount in ((b, mod_b), (a, mod_a)):
        if amount:
            ctx.extra["it"] = [unit]
            REGISTRY["grant_temporary_might"](ctx, {"target": "it", "amount": amount, "duration": "this_turn"})
    a_might, b_might = a.might, b.might
    ctx.damage_units([b], a_might, "unit", me)
    ctx.damage_units([a], b_might, "unit", them)


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
            base = u.base_might
            return amount - base if id(u) in friends else base - amount
        units = sorted(units, key=gain, reverse=True)
        if not units or (gain(units[0]) <= 0 and not isinstance(ctx.card, SpellCard)):
            return       # "you may": it helps no one (a spell must choose one)
        units = [ctx.loop.choose(_kind("target", spec), ctx.actor_side, units, units[0], ctx.card)]
        ctx.loop._note_chosen(ctx.card, ctx.actor_side, units)
    for unit in units:
        current = unit.base_might
        if spec.get("only_if_higher") and amount <= current:
            continue     # "you may": only when it raises me
        unit.base_might_override = amount


@effect("match_might")
def _match_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit. This turn, increase its Might to the Might of
    another friendly unit" (Convergent Mutation): the weakest friendly unit at a
    battlefield rises to the mightiest friendly unit."""
    mine = _choosable(ctx, _units_at(ctx, ctx.actor_side, "anywhere"))
    if len(mine) < 2:
        return
    top = max(mine, key=lambda u: u.might)
    at_bf = [u for u in mine if u is not top and ctx.loop._locate_unit(u)[1] is not None]
    low = min(at_bf or [u for u in mine if u is not top], key=lambda u: u.might)
    # The player's two choices: the unit, then the other one it matches.
    low = ctx.loop.choose(_kind("target", spec), ctx.actor_side, mine, low, ctx.card)
    others = [u for u in mine if u is not low]
    top = ctx.loop.choose(_kind("target", spec) + ":other", ctx.actor_side, others,
                          max(others, key=lambda u: u.might), ctx.card)
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


def _return_gear(ctx: "EffectContext", pick) -> Optional[object]:
    """Return a friendly gear to its owner's hand (base first, then attached);
    `pick` chooses among them. Returns the card (a token ceases to exist)."""
    loop = ctx.loop
    side, ap = ctx.actor_side, ctx.actor
    pool = [(None, g) for g in ap.base_gear] + \
        [(u, g) for u in _units_at(ctx, side, "anywhere") for g in u.gear]
    if not pool:
        return None
    holder, gear = pick(pool)
    if holder is None:
        ap.base_gear.remove(gear)
    else:
        holder.gear.remove(gear)
    loop._fire_leaves_board(gear, side, loop.gs.battlefields[0])
    if not getattr(gear, "is_token", False):
        gear.empowered = False
        ap.hand.append(gear)
    return gear


@effect("return_gear_cost")
def _return_gear_cost(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "As an additional cost to play me, return a friendly gear to its
    owner's hand" (Legion Quartermaster): a token or the cheapest in base."""
    _return_gear(ctx, lambda pool: min(pool, key=lambda e: (e[0] is not None,
                                                           not getattr(e[1], "is_token", False),
                                                           e[1].cost_energy or 0)))


@effect("return_gear_ready_pump")
def _return_gear_ready_pump(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may return a friendly gear to its owner's hand as an additional
    cost to play me. If you paid, ready me and give me +[might] this turn
    equal to the Energy cost of the gear you returned." (Spirit of the Forge):
    the costliest friendly gear, in base or attached."""
    me = _source_unit(ctx)
    if me is None:
        return
    gear = _return_gear(ctx, lambda pool: max(pool, key=lambda e: (
        e[1].cost_energy or 0, not getattr(e[1], "is_token", False))))
    if gear is not None:
        if ctx.loop._can_ready(me):
            me.ready = True
        me.temporary_might += int(gear.cost_energy or 0)


@effect("swap_gear_free")
def _swap_gear_free(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may kill a friendly gear. If you do, you may play a gear with
    Energy cost no more than [7] from hand this turn, ignoring its Energy
    cost." (Jayce Man of Progress): a token or the cheapest gear goes, the
    costliest gear in hand comes in now."""
    from .cards import GearCard
    loop = ctx.loop
    ap, side = ctx.actor, ctx.actor_side
    hand = [c for c in ap.hand if isinstance(c, GearCard) and int(c.cost_energy or 0) <= 7
            and (not c.cost_power or (ap.can_pay_cost(0, c.cost_power, c.cost_power_domain)
                                      if c.cost_power_domain else loop._can_pay_generic_power(ap, c.cost_power)))]
    mine = list(ap.base_gear)
    if not hand or not mine:
        return
    victim = min(mine, key=lambda g: (not getattr(g, "is_token", False), g.cost_energy or 0))
    best = max(hand, key=_zone_value)
    if int(best.cost_energy or 0) <= int(victim.cost_energy or 0):
        return
    loop._remove_gear(victim, ap)
    if best.cost_power:
        if best.cost_power_domain:
            ap.pay_cost(0, best.cost_power, best.cost_power_domain)
        else:
            loop._pay_generic_power(ap, best.cost_power)
    ap.hand.remove(best)
    loop._play_gear(best, side, 0, from_zone="hand")


@effect("kill_pet_cost")
def _kill_pet_cost(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "As an additional cost to play me, kill a Bird, Cat, Dog, or Poro you
    control" (Stalking Wolf): the one at my battlefield, else the weakest."""
    loop = ctx.loop
    side = ctx.actor_side
    me = _source_unit(ctx)
    here = loop._locate_unit(me)[1] if me is not None else None
    pets = [u for u in _units_at(ctx, side, "anywhere") if u is not me
            and any(t in u.tags for t in ("Bird", "Cat", "Dog", "Poro"))]
    if not pets:
        return
    victim = min(pets, key=lambda u: (loop._locate_unit(u)[1] is not here, u.might))
    victim = loop.choose("cost_unit:kill_pet_cost", side, pets, victim, ctx.card)
    where = loop._locate_unit(victim)
    if where[1] is None:
        ctx.actor.base_units.remove(victim)
    else:
        where[1].remove_unit(side, victim)
    loop._route_deaths([(victim, side)], where[1] or loop.gs.battlefields[0], in_base=where[1] is None)


@effect("champion_to_hand")
def _champion_to_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Put a Teemo unit you own into your hand from your Champion Zone"
    (Teemo Swift Scout)."""
    gs = ctx.loop.gs
    side = ctx.actor_side
    champ = gs.champion_A if side == "A" else gs.champion_B
    deployed = gs.champion_A_deployed if side == "A" else gs.champion_B_deployed
    name = str(spec.get("name_prefix", ""))
    if champ is None or deployed or not champ.name.startswith(name):
        return
    ctx.actor.hand.append(champ)
    if side == "A":
        gs.champion_A_deployed = True
    else:
        gs.champion_B_deployed = True


def _copy_card(card):
    """A fresh instance of `card` (by name) to become: "a copy of that unit"."""
    spec = CARD_REGISTRY.get(card.name)
    return spec.instantiate() if spec is not None else card


@effect("copy_friendly_unit")
def _copy_friendly_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "As this is attached to a unit, choose another friendly unit. The
    equipped unit becomes a copy of that unit for as long as this is
    attached to it." (Shady Spectacles): the player's choice (baseline: the
    mightiest other friendly unit)."""
    unit = ctx.extra.get("triggering_unit")
    if unit is None or unit.copied_from is not None or ctx.card not in unit.gear:
        return
    others = [u for u in _units_at(ctx, ctx.actor_side, "anywhere") if u is not unit]
    if not others:
        return
    model = ctx.loop.choose(_kind("target", spec), ctx.actor_side, others,
                            max(others, key=lambda u: int(u.card.might or 0)), ctx.card)
    unit.copied_from = unit.card
    unit.card = _copy_card(model.card)


@effect("reflection_copy")
def _reflection_copy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may discard 1 and exhaust me to play a ready Reflection unit token
    there. It becomes a copy of another unit there. Give it TEMPORARY."
    (Leblanc Deceiver): the player picks the discard and the unit (baseline:
    the least useful card, the mightiest unit there)."""
    loop = ctx.loop
    bf = ctx.battlefield
    there = list(bf.units_A) + list(bf.units_B)
    if not there or not ctx.actor.hand:
        return
    loop._discard(ctx.actor, loop.choose("discard", ctx.actor_side, list(ctx.actor.hand),
                                         min(ctx.actor.hand, key=_zone_value), ctx.card))
    model = loop.choose(_kind("target", spec), ctx.actor_side, there,
                        max(there, key=lambda u: u.might), ctx.card)
    token = loop._play_token("Reflection", ctx.actor_side, bf=bf, ready=True)
    if token is None:
        return
    copy = _copy_card(model.card)
    copy.is_token = True
    token.card = copy
    token.granted_keywords.append("TEMPORARY")


@effect("chronobreak")
def _chronobreak(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "As an additional cost to play this, play any amount of Power. Banish
    that many units you control, then for each, its owner plays that unit back
    to the same location or to their base, ignoring its cost." (Chronobreak):
    the damaged units and those with a play effect, one generic Power each."""
    loop = ctx.loop
    side, ap = ctx.actor_side, ctx.actor

    def worth(u):
        spec_ = CARD_REGISTRY.get(u.card.name)
        return u.damage > 0 or bool(spec_ and any(es.trigger == "on_play" for es in spec_.effects))
    # "Any amount": one choice per unit you control (baseline: the worthwhile ones).
    picks = [u for u in _units_at(ctx, side, "anywhere")
             if loop.choose(_kind("optional", spec), side, [True, False], worth(u), u.card)]
    for unit in picks:
        if not loop._pay_generic_power(ap, 1):
            break
        where = loop._locate_unit(unit)
        if where is None:
            continue
        src = where[1]
        if src is None:
            ap.base_units.remove(unit)
        else:
            src.remove_unit(side, unit)
        ap.base_gear.extend(unit.gear)
        loop._fire_leaves_board(unit.card, side, src or loop.gs.battlefields[0])
        loop._note_banished(side)
        loop._play_unit(unit.card, side, bf=src, from_zone="banished")


@effect("steal_spell")
def _steal_spell(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Gain control of a spell. You may make new choices for it." (Mystic
    Reversal): the opponent's latest spell on the chain resolves as ours."""
    for item in reversed(ctx.loop.gs.chain):
        if item.player == ctx.opponent_side and item.card is not ctx.card:
            _take_over_spell(ctx, item)
            return


def _take_over_spell(ctx: "EffectContext", item) -> None:
    """We gain control of a spell on the chain and "may make new choices for
    it": it resolves as ours, every choice made again (by us, as it resolves);
    its card still goes to its owner's trash."""
    if item.owner is None:
        item.owner = item.player
    item.player = ctx.actor_side
    item.declared = None
    item.choices_noted = False


@effect("steal_or_counter_spell")
def _steal_or_counter_spell(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a spell with Energy cost no more than [4]. You may pay [rune].
    If you do, gain control of it and you may make new choices for it.
    Otherwise, counter it." (Rebuttal). Baseline: the opponent's latest such
    spell; pay unless it is a counter (ours would then counter our own spell)."""
    loop = ctx.loop
    items = [it for it in loop.gs.chain if it.card is not ctx.card
             and isinstance(it.card, SpellCard) and _counterable(it.card, spec)]
    if not items:
        return
    enemy = [it for it in items if it.player != ctx.actor_side]
    item = loop.choose("spell:steal_or_counter_spell", ctx.actor_side, items, (enemy or items)[-1], ctx.card)
    n = int(spec.get("pay_power", 1))
    if loop._can_pay_generic_power(ctx.actor, n):
        pay = item.player != ctx.actor_side and not loop._has_effect(item.card, "counter_spell")
        if loop.choose("optional:steal_or_counter_spell", ctx.actor_side, [True, False], pay, ctx.card) \
                and loop._pay_generic_power(ctx.actor, n):
            _take_over_spell(ctx, item)
            return
    if loop._uncounterable(item.player) or loop._has_effect(item.card, "cant_be_countered"):
        return
    loop.gs.chain.remove(item)
    loop._spell_to_trash(loop.gs.get_player(item.owner or item.player), item.card)


@effect("bounce_enemy_at_crowded_battlefield")
def _bounce_enemy_at_crowded_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a battlefield. If there are 4 or more units there, you may
    return an enemy unit there to its owner's hand" (Bedeviling Stranger)."""
    crowded = [bf for bf in ctx.loop.gs.battlefields if len(bf.units_A) + len(bf.units_B) >= 4
               and _choosable(ctx, list(bf._units_for(ctx.opponent_side)))]
    if not crowded:
        return
    bf = max(crowded, key=lambda b: max(u.might for u in b._units_for(ctx.opponent_side)))
    bf = ctx.loop.choose(_kind("battlefield", spec), ctx.actor_side, crowded, bf, ctx.card)
    enemies = _choosable(ctx, list(bf._units_for(ctx.opponent_side)))
    unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, enemies,
                           max(enemies, key=lambda u: u.might), ctx.card)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    _unit_leaves_to(ctx, unit, ctx.opponent_side, "hand")


@effect("follow_move")
def _follow_move(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When a friendly unit moves from my location, I may be moved with it"
    (Stealthy Pursuer): when it goes to a battlefield."""
    me = _source_unit(ctx)
    dst = ctx.extra.get("moved_to")
    if me is None or dst in (None, "base") or ctx.extra.get("triggering_unit") is me:
        return
    ctx.loop._move_unit_by_effect(me, dst)


@effect("return_triggering_gear")
def _return_triggering_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When a friendly gear at a battlefield dies, you may pay [1] to return
    it to its owner's hand" (Battlefield Armorer)."""
    gear = ctx.extra.get("triggering_card")
    if gear is not None and gear in ctx.actor.trash:
        ctx.actor.trash.remove(gear)
        ctx.actor.hand.append(gear)


@effect("signpost_move")
def _signpost_move(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Exhaust a unit you control, [tap]: Move a different unit you control to
    the location of the unit you exhausted" (Forgotten Signpost)."""
    pair = ctx.loop._signpost_pair(ctx.actor_side)
    if pair is None:
        return
    anchor, mover = pair
    ctx.loop._exhaust(anchor)
    ctx.loop._move_unit_by_effect(mover, ctx.loop._locate_unit(anchor)[1])


@effect("minefield")
def _minefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Kill any number of friendly Bomb tokens. At end of turn, play that many
    Bomb tokens to a single battlefield." (Hexplosive Minefield): all of them."""
    loop = ctx.loop
    side = ctx.actor_side
    n = 0
    for bf in loop.gs.battlefields:
        bombs = [dg for dg in bf.gear_for(side) if dg.card.name == "Bomb"]
        if bombs:
            n += len(bombs)
            loop._kill_deployed_gear(bf, side, bombs)
    if n:
        loop.gs.delayed_effects.append((side, ctx.card, 0, {"effect": "play_token", "token_name": "Bomb", "count": n}))


@effect("play_hidden_from_hand")
def _play_hidden_from_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may pay [mind] to play a card with HIDDEN from your hand, ignoring
    its cost. If it's a unit, play it here." (Ava Achiever): the costliest."""
    from .cards import GearCard, UnitCard
    loop = ctx.loop
    cards = [c for c in ctx.actor.hand if c.has_keyword("HIDDEN")]
    if not cards:
        return
    card = max(cards, key=_zone_value)
    ctx.actor.hand.remove(card)
    side = ctx.actor_side
    if isinstance(card, UnitCard):
        loop._play_unit(card, side, bf=ctx.battlefield if ctx.battlefield in loop.gs.battlefields else None)
    elif isinstance(card, GearCard):
        loop._play_gear(card, side, 0)
    else:
        loop._play_from_zone_now(ctx.actor, card, side, "hand")


@effect("choose_pet_tag")
def _choose_pet_tag(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "As you play me, choose Bird, Cat, Dog, or Poro. I gain that tag."
    (Ivern Friend to All): the one your units lack."""
    me = _source_unit(ctx)
    if me is None:
        return
    have = {t for u in _units_at(ctx, ctx.actor_side, "anywhere") for t in u.tags}
    tags = ["Bird", "Cat", "Dog", "Poro"]
    pick = next((t for t in tags if t not in have), "Bird")
    me.extra_tags.append(ctx.loop.choose(_kind("tag", spec), ctx.actor_side, tags, pick, ctx.card))


@effect("hostage_from_hand")
def _hostage_from_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "They reveal their hand. Choose a card revealed this way and banish it.
    When they hold, return it to their hand" (Ashe Focused): the costliest."""
    hand = ctx.opponent.hand
    if hand:
        card = max(hand, key=_zone_value)
        hand.remove(card)
        ctx.opponent.banished.append(card)
        ctx.loop.gs.held_hostage.append((ctx.opponent_side, card))


@effect("force_discard_redraw")
def _force_discard_redraw(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "They reveal their hand. You may pay 2 XP to choose a card from their
    hand. If you do, they discard that card and draw 1." (Insightful
    Investigator)"""
    gs = ctx.loop.gs
    xp = int(spec.get("xp", 2))
    hand = ctx.opponent.hand
    if hand and gs.get_xp(ctx.actor_side) >= xp:
        gs.add_xp(ctx.actor_side, -xp)
        ctx.loop._discard(ctx.opponent, max(hand, key=_zone_value))
        ctx.draw_cards(1, target="opponent")


@effect("pull_unit_from_hand")
def _pull_unit_from_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a battlefield. An opponent reveals their hand. You may choose a
    unit from it. Then play that unit to the battlefield, ignoring any and all
    costs. When they do, STUN it." (Bone Skewer): their unit comes, stunned, to
    the battlefield where we are strongest, the biggest one we beat there."""
    from .cards import UnitCard
    loop = ctx.loop
    units = [c for c in ctx.opponent.hand if isinstance(c, UnitCard)]
    if not units:
        return
    bf = max(loop.gs.battlefields, key=lambda b: sum(u.might for u in b._units_for(ctx.actor_side)))
    bf = loop.choose(_kind("battlefield", spec), ctx.actor_side, list(loop.gs.battlefields), bf, ctx.card)
    mine = sum(u.might for u in bf._units_for(ctx.actor_side))
    beaten = [c for c in units if int(c.might or 0) <= mine]
    card = loop.choose(_kind("card", spec), ctx.actor_side, units,
                       max(beaten or units, key=lambda c: int(c.might or 0)), ctx.card)
    ctx.opponent.hand.remove(card)
    prev = bf.controller()
    unit = loop._play_unit(card, ctx.opponent_side, bf=bf, from_zone="hand")
    unit.stunned = True
    loop._arrive_at(bf, ctx.opponent_side, prev)


@effect("take_control")
def _take_control(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Take control of an enemy unit at a battlefield. `until_end_of_turn`:
    ready it, and it goes back to its owner's base at end of turn (Hostile
    Takeover); else recall it to our base for good, exhausted when the text
    says so (Conscription: one with 3 Might or less, any if 5 XP was spent)."""
    loop = ctx.loop
    me = ctx.actor_side
    cands = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "battlefield"))
    cap = spec.get("might_at_most")
    xp = int(spec.get("xp_for_any", 0))
    if cap is not None and not (xp and loop.gs.get_xp(me) >= xp and
                                any(u.might > int(cap) for u in cands)):
        cands = [u for u in cands if u.might <= int(cap)]
    elif cap is not None and xp:
        loop.gs.add_xp(me, -xp)
    if not cands:
        return
    unit = loop.choose(_kind("target", spec), me, cands, max(cands, key=lambda u: u.might), ctx.card)
    loop._note_chosen(ctx.card, me, [unit])
    prev = loop._locate_unit(unit)[1].controller()
    bf = loop._take_control(unit, me)
    if spec.get("until_end_of_turn"):
        unit.borrowed = (ctx.opponent_side, loop.gs.turn)
        if loop._can_ready(unit):
            unit.ready = True
        loop._arrive_at(bf, me, prev)
    else:
        # A recall changes nothing about the unit (§460); Conscription says
        # "exhaust it" (`exhaust`), Possession doesn't.
        if spec.get("exhaust") and unit.ready:
            loop._exhaust(unit)
        bf.remove_unit(me, unit)
        ctx.actor.base_units.append(unit)


@effect("gain_permanent_might")
def _gain_permanent_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "I gain +1 Might" for good (Lillia Protector of Dreams)."""
    unit = _source_unit(ctx)
    if unit is not None:
        unit.aura_might += int(spec.get("amount", 1))


@effect("recycle_runes_channel")
def _recycle_runes_channel(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Recycle all your runes, then channel 4 runes exhausted" (Coalesced
    Energy)."""
    p = ctx.actor
    for dom in list(p.rune_pool):
        for rune in p.rune_pool.pop(dom):
            rune.ready = True
            p.rune_deck.runes.append(rune)
    p.unlock_runes(int(spec.get("amount", 4)), exhausted=True)
    ctx.loop._extra_channel(ctx.actor_side)


@effect("guess_type_draw")
def _guess_type_draw(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an opponent. They guess a card type. Reveal the top card of your
    Main Deck. If it has that type, recycle it. Otherwise, draw it."
    (Scrutinizing Scope): they guess unit."""
    from .cards import UnitCard
    ctx.loop._before_deck_reveal(ctx.actor_side, value=lambda c: not isinstance(c, UnitCard))
    deck = ctx.actor.deck.cards
    if not deck:
        return
    ctx.loop._note_revealed(ctx.actor_side, [deck[-1]])
    top = deck.pop()
    if isinstance(top, UnitCard):
        deck.insert(0, top)
    else:
        ctx.actor.hand.append(top)


@effect("banish_unit")
def _banish_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Banish an enemy unit at a battlefield with 3 Might or less" (Mel Defiant
    Soul): off the board into its owner's banishment — it doesn't die (no
    DEATHKNELL, not to the trash); a token just ceases to exist, its gear goes
    to the trash. `with_this`: the card is "banished with this" (Dockside
    Lock-Up, played back by play_banished_with_this)."""
    loop = ctx.loop
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")},
                                 bias="enemy"):
        where = loop._locate_unit(unit)
        if where is None:
            continue
        side = where[0]
        owner = loop.gs.get_player(side)
        loop._remove_unit_from_play(unit, side)
        for g in list(unit.gear):
            loop._to_trash(owner, g)
        unit.gear.clear()
        if not unit.is_token:
            owner.banished.append(unit.card)
            if spec.get("with_this"):
                ctx.card._banished_with = list(getattr(ctx.card, "_banished_with", [])) + [unit.card]


@effect("replay_self_to_base")
def _replay_self_to_base(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Banish me, then play me to your base, ignoring my cost" (Ekko
    Revolutionary): it comes back as a new object ("I enter ready")."""
    me = _source_unit(ctx)
    if me is None:
        return
    ctx.extra["it"] = [me]
    _banish_unit(ctx, {"target": "it"})
    if ctx.card in ctx.actor.banished:
        ctx.actor.banished.remove(ctx.card)
        ctx.loop._play_unit(ctx.card, ctx.actor_side, from_zone="banished")


@effect("banish_or_return")
def _banish_or_return(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Wind and Ghosts: "Choose a unit at a battlefield. If it has 3 [might] or
    less, banish it. Otherwise, return it to its owner's hand." One choice
    (baseline: an enemy), then the outcome by its Might."""
    limit = int(spec.get("might_at_most", 3))
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "chosen_unit")},
                                 bias="enemy"):
        ctx.extra["it"] = [unit]
        if unit.might <= limit:
            _banish_unit(ctx, {"target": "it"})
        else:
            _recall_unit(ctx, {"target": "it"})


@effect("banish_self_and_gear")
def _banish_self_and_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When an opponent plays a gear, you may banish me to banish it"
    (Ravenbloom Prefect)."""
    loop = ctx.loop
    gear = ctx.extra.get("triggering_card")
    me = _source_unit(ctx)
    if gear is None or me is None:
        return
    entry = next(((s, h, g) for s, h, g in _gear_entries(ctx, enemy_first=True)
                  if getattr(g, "card", g) is gear), None)
    if entry is None:
        return
    side, holder, g = entry
    owner = loop.gs.get_player(side)
    if isinstance(holder, Battlefield):
        holder.gear_for(side).remove(g)
    elif holder is not None:
        holder.gear.remove(g)
    else:
        owner.base_gear.remove(g)
    if not getattr(gear, "is_token", False):
        owner.banished.append(gear)
    where = loop._locate_unit(me)
    if where[1] is None:
        ctx.actor.base_units.remove(me)
    else:
        where[1].remove_unit(ctx.actor_side, me)
    ctx.actor.base_gear.extend(me.gear)
    loop._fire_leaves_board(me.card, ctx.actor_side, where[1] or loop.gs.battlefields[0])
    ctx.actor.banished.append(me.card)
    loop._note_banished(ctx.actor_side)


@effect("opponent_kills_own_unit")
def _opponent_kills_own_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Each opponent must kill one of their units" (Shard of Undoing): their
    choice, their weakest."""
    loop = ctx.loop
    units = _units_at(ctx, ctx.opponent_side, "anywhere")
    if not units:
        return
    victim = loop.choose(_kind("target", spec), ctx.opponent_side, units,
                         min(units, key=lambda u: (not u.is_token, u.might)), ctx.card)
    where = loop._locate_unit(victim)
    if where[1] is None:
        ctx.opponent.base_units.remove(victim)
    else:
        where[1].remove_unit(ctx.opponent_side, victim)
    loop._route_deaths([(victim, ctx.opponent_side)], where[1] or loop.gs.battlefields[0],
                       in_base=where[1] is None)


@effect("sacrifice_token_here_draw")
def _sacrifice_token_here_draw(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may kill a unit you control here to draw 1" (Dusk Rose Lab): any
    unit you control here; baseline yes only with a token there (its weakest)."""
    here = list(ctx.battlefield._units_for(ctx.actor_side))
    if not here:
        return
    tokens = [u for u in here if u.is_token]
    if not ctx.loop.choose("optional:" + str(spec.get("effect")), ctx.actor_side, [True, False],
                           bool(tokens), ctx.card):
        return
    victim = ctx.loop.choose("cost_unit:" + str(spec.get("effect")), ctx.actor_side, here,
                             min(tokens or here, key=lambda u: u.might), ctx.card)
    ctx.battlefield.remove_unit(ctx.actor_side, victim)
    ctx.loop._route_deaths([(victim, ctx.actor_side)], ctx.battlefield)
    ctx.draw_cards(1, target="actor")


@effect("opponent_kills_own_here")
def _opponent_kills_own_here(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When I attack, the defender must kill one of their units here"
    (Atakhan): the defender picks; baseline their weakest."""
    bf = ctx.extra.get("battlefield") or ctx.battlefield
    theirs = list(bf._units_for(ctx.opponent_side))
    if not theirs:
        return
    victim = ctx.loop.choose("kill_own:" + str(spec.get("effect")), ctx.opponent_side, theirs,
                             min(theirs, key=lambda u: u.might), ctx.card)
    _take_off_board(ctx, victim)
    ctx.loop._route_deaths([(victim, ctx.opponent_side)], bf, killer=(ctx.actor_side, ctx.card))


@effect("play_from_opponent_trash")
def _play_from_opponent_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit in their trash and play it, ignoring its cost" (Kharox):
    you control it, they still own it. Baseline: the mightiest."""
    units = [c for c in ctx.opponent.trash if _zone_effect_card_ok(c, {"target_filter": {"is_unit": True}})]
    if not units:
        return
    card = ctx.loop.choose(_kind("card", spec), ctx.actor_side, units,
                           max(units, key=lambda c: int(getattr(c, "might", 0) or 0)), ctx.card)
    ctx.opponent.trash.remove(card)
    card._owner = ctx.opponent_side
    ctx.loop._play_unit(card, ctx.actor_side, from_zone="trash")


@effect("steal_gear")
def _steal_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Move an enemy gear to your base. You control it until I leave the
    board. If it's an Equipment, attach it to me" (Akshan Mischievous): any
    enemy gear (base, attached, deployed); baseline the costliest. It goes back
    when this card leaves the board (GameLoop._return_stolen_gear)."""
    loop = ctx.loop
    entries = [(s, h, g) for s, h, g in _gear_entries(ctx, enemy_first=True) if s == ctx.opponent_side]
    if not entries:
        return
    pick = max(entries, key=lambda e: _zone_value(getattr(e[2], "card", e[2])))
    side, holder, gear = loop.choose(_kind("target", spec), ctx.actor_side, entries, pick, ctx.card)
    card = getattr(gear, "card", gear)
    if isinstance(holder, Battlefield):
        holder.gear_for(side).remove(gear)
    elif holder is not None:
        holder.gear.remove(gear)
    else:
        loop.gs.get_player(side).base_gear.remove(gear)
    card._owner, card._stolen_by = side, ctx.card
    me = _source_unit(ctx)
    if me is not None and loop._equip_cost(card) is not None:
        me.gear.append(card)
        loop._fire_attached(me, ctx.actor_side)
    else:
        ctx.actor.base_gear.append(card)


@effect("stun_or_kill")
def _stun_or_kill(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an enemy unit. If it is stunned, kill it. Otherwise, stun it"
    (Solari Chief). Baseline: a stunned one (killed), else the mightiest."""
    cands = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "anywhere"))
    if not cands:
        return
    unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, cands,
                           max(cands, key=lambda u: (u.stunned, u.might)), ctx.card)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    if unit.stunned:
        where = _take_off_board(ctx, unit)
        if where is not None:
            ctx.loop._route_deaths([(unit, where[0])], where[1] or ctx.battlefield,
                                   in_base=where[1] is None, killer=(ctx.actor_side, ctx.card))
    else:
        unit.stunned = True
        where = ctx.loop._locate_unit(unit)
        ctx.loop._fire_stun_enemy(ctx.actor_side, where[1] if where else None)


@effect("each_player_kills_unit")
def _each_player_kills_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Each player kills one of their units" (Cull the Weak): each player
    picks one of their own, the caster first; baseline their weakest."""
    for side in (ctx.actor_side, ctx.opponent_side):
        if side == ctx.actor_side and spec.get("skip_actor_if_paid") and getattr(ctx.card, "_kicker_paid", False):
            continue        # "If you paid my additional cost, you don't kill a unit this way"
        units = [u for u in _units_at(ctx, side, "anywhere") if u.card is not ctx.card or not spec.get("not_self")]
        if not units:
            continue
        unit = ctx.loop.choose("kill_own:" + str(spec.get("effect")), side, units,
                               min(units, key=lambda u: (not u.is_token, u.might)), ctx.card)
        where = _take_off_board(ctx, unit)
        if where is not None:
            ctx.loop._route_deaths([(unit, side)], where[1] or ctx.battlefield,
                                   in_base=where[1] is None, killer=(ctx.actor_side, ctx.card))


@effect("fight_it_with_another")
def _fight_it_with_another(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Move an enemy unit. Then do this: Choose another enemy unit at its
    destination. They deal damage equal to their Mights to each other"
    (Dragon's Rage): the unit the previous instruction moved ("it")."""
    it = [u for u in ctx.extra.get("it") or [] if ctx.loop._locate_unit(u) is not None]
    if not it:
        return
    a = it[0]
    side, bf = ctx.loop._locate_unit(a)
    others = [u for u in (bf._units_for(side) if bf is not None else ctx.loop.gs.get_player(side).base_units)
              if u is not a]
    others = _choosable(ctx, others)
    if not others:
        return
    b = ctx.loop.choose(_kind("target", spec), ctx.actor_side, others,
                        max(others, key=lambda u: u.might), ctx.card)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [b])
    a_might, b_might = a.might, b.might
    ctx.damage_units([b], a_might, "unit", side)
    ctx.damage_units([a], b_might, "unit", side)


@effect("stormbringer")
def _stormbringer(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit in your base. Deal damage equal to its Might to
    all enemies at a battlefield, then move your unit there" (Stormbringer).
    Baseline: the mightiest unit, the battlefield where it kills the most."""
    loop, gs = ctx.loop, ctx.loop.gs
    mine = list(ctx.actor.base_units)
    if not mine:
        return
    unit = loop.choose(_kind("target", spec), ctx.actor_side, mine,
                       max(mine, key=lambda u: u.might), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    might = unit.might
    bf = loop.choose(_kind("battlefield", spec), ctx.actor_side, list(gs.battlefields),
                     max(gs.battlefields, key=lambda b: sum(1 for e in b._units_for(ctx.opponent_side)
                                                             if e.might - e.damage <= might)),
                     ctx.card)
    ctx.damage_units(list(bf._units_for(ctx.opponent_side)), might)
    if loop._locate_unit(unit) is not None:
        loop._move_unit_by_effect(unit, bf)


@effect("doom_unit")
def _doom_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit. Kill it the next time it takes damage this turn"
    (Noxian Guillotine): marked, killed by GameLoop._take_damage."""
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "chosen_unit")}, bias="enemy"):
        unit.doomed_turn = ctx.loop.gs.turn


@effect("pay_x_damage")
def _pay_x_damage(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Pay an amount of [rune] to deal that much damage to all enemy units at
    a battlefield" (Bullet Time): X is chosen as it resolves (baseline: enough
    to kill the most, the least of that), paid as generic Power."""
    loop = ctx.loop
    enemies = list(ctx._units_for_side(ctx.opponent_side))
    most = 0
    while loop._can_pay_generic_power(ctx.actor, most + 1):
        most += 1
    if not enemies or most == 0:
        return
    options = list(range(0, most + 1))

    def kills(x):
        return sum(1 for e in enemies if x >= e.might - e.damage)
    best = min((x for x in options if kills(x) == kills(most)), default=0)
    x = loop.choose("amount:" + str(spec.get("effect")), ctx.actor_side, options, best, ctx.card)
    if x <= 0:
        return
    loop._pay_generic_power(ctx.actor, x)
    ctx.damage_units(enemies, x)


@effect("recycle_from_trashes")
def _recycle_from_trashes(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Recycle up to 4 cards from trashes" (Forge of the Future): from any
    player's trash to its owner's Main Deck bottom; baseline the opponent's
    costliest."""
    gs = ctx.loop.gs
    pool = [(ctx.opponent_side, c) for c in ctx.opponent.trash]
    if not spec.get("opponents_only"):       # "from opponents' trashes" (Disposal Order)
        pool += [(ctx.actor_side, c) for c in ctx.actor.trash]
    n = min(int(spec.get("amount", 4)), len(pool))
    picks = ctx.loop.choose_many("recycle:" + str(spec.get("effect")), ctx.actor_side, pool,
                                 sorted(pool, key=lambda e: (e[0] != ctx.opponent_side,
                                                             [-v for v in _zone_value(e[1])]))[:n],
                                 ctx.card)
    for side, card in picks:
        owner = gs.get_player(side)
        if any(c is card for c in owner.trash):
            owner.trash.remove(card)
            owner.deck.cards.insert(0, card)
            ctx.loop._note_recycled(side)


@effect("extra_turn")
def _extra_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Take a turn after this one" (Time Warp)."""
    ctx.loop.gs.extra_turns.append(ctx.actor_side)


@effect("free_hide_this_turn")
def _free_hide_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You can hide ignoring costs this turn" (Guerilla Warfare)."""
    ctx.loop.gs.free_hide[ctx.actor_side] = ctx.loop.gs.turn


@effect("ward_unit")
def _ward_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit. The next time it would die this turn, you may
    pay [fury] to heal it, exhaust it, and recall it instead" (Unlicensed
    Armory): GameLoop._try_replace_death."""
    for unit in _resolve_targets(ctx, {**spec, "target": "friendly_unit", "where": "anywhere"}):
        unit.ward_turn = ctx.loop.gs.turn
        unit.ward_free = bool(spec.get("free"))      # Tactical Retreat


@effect("buff_bonus_this_turn")
def _buff_bonus_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Buffs give an additional +1 [might] to friendly units this turn" (Stand
    United): GameLoop._recompute_passives."""
    ctx.loop.gs.buff_bonus_turn[ctx.actor_side] = ctx.loop.gs.turn


@effect("noop")
def _noop(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """An entry that only carries a cost ("As an additional cost to play me,
    kill a friendly unit": Cruel Patron)."""


@effect("return_self_to_hand")
def _return_self_to_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When you conquer, you may discard 1 to return this from your trash to
    your hand" (Super Mega Death Rocket!, from the trash)."""
    if any(c is ctx.card for c in ctx.actor.trash):
        ctx.actor.trash.remove(ctx.card)
        ctx.actor.hand.append(ctx.card)


@effect("spend_buffs_to_ready")
def _spend_buffs_to_ready(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "For each friendly unit, you may spend its buff to ready it" (Overt
    Operation): each buffed exhausted friendly unit, the player's choice
    (baseline: yes)."""
    for u in _friendly_units(ctx):
        if u.might_counters > 0 and not u.ready and ctx.loop._can_ready(u) and \
                ctx.loop.choose("optional:spend_buff", ctx.actor_side, [True, False], True, u.card):
            ctx.loop._spend_buff(u, ctx.actor_side)
            u.ready = True
            where = ctx.loop._locate_unit(u)
            if where is not None:
                ctx.loop._fire_readied(u, where[0])


@effect("prevent_next_damage")
def _prevent_next_damage(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit. The next time that unit would be dealt damage this
    turn, prevent it" (Counter Strike): GameLoop._take_damage."""
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "chosen_unit"),
                                       "where": spec.get("where", "anywhere")}):
        unit.prevent_next_turn = ctx.loop.gs.turn


@effect("rally_this_turn")
def _rally_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When a friendly unit is played this turn, buff it" (Rally the Troops)."""
    ctx.loop.gs.rally_turn[ctx.actor_side] = ctx.loop.gs.turn


@effect("conquer_return_this_turn")
def _conquer_return_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ 'This turn, that unit has "When I conquer, you may move me to my base"'
    (Relentless Pursuit): the unit the previous instruction moved."""
    for unit in ctx.extra.get("it") or []:
        ctx.loop.gs.conquer_return.append((id(unit), ctx.loop.gs.turn))


@effect("attach_equipment_to_it")
def _attach_equipment_to_it(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may attach an Equipment with the same controller to it"
    (Relentless Pursuit): one of your Equipment, in base or on another unit."""
    loop = ctx.loop
    it = [u for u in ctx.extra.get("it") or [] if loop._locate_unit(u) is not None]
    if not it:
        return
    unit = it[0]
    side = loop._locate_unit(unit)[0]
    owner = loop.gs.get_player(side)
    cands = [(None, g) for g in owner.base_gear if loop._equip_cost(g) is not None]
    cands += [(u, g) for u in loop._friendly_units_of(side) if u is not unit for g in u.gear]
    if not cands or not loop.choose("optional:attach", ctx.actor_side, [True, False], True, ctx.card):
        return
    holder, gear = loop.choose("equip", ctx.actor_side, cands,
                               max(cands, key=lambda c: int(getattr(c[1], "might", 0) or 0)), ctx.card)
    (owner.base_gear if holder is None else holder.gear).remove(gear)
    unit.gear.append(gear)
    loop._fire_attached(unit, side)


@effect("strike_down")
def _strike_down(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an equipped friendly unit. It deals damage equal to its Might to
    an enemy unit. Then detach an Equipment from it" (Strike Down)."""
    loop = ctx.loop
    mine = [u for u in _units_at(ctx, ctx.actor_side, "anywhere") if u.gear]
    enemies = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "anywhere"))
    if not mine or not enemies:
        return
    unit = loop.choose(_kind("target", spec), ctx.actor_side, mine, max(mine, key=lambda u: u.might), ctx.card)
    enemy = loop.choose(_kind("target", spec), ctx.actor_side, enemies,
                        max(enemies, key=lambda e: (unit.might >= e.might - e.damage, e.might)), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [unit, enemy])
    ctx.damage_units([enemy], unit.might)
    if unit.gear and loop._locate_unit(unit) is not None:
        gear = loop.choose("detach", ctx.actor_side, list(unit.gear), unit.gear[0], ctx.card)
        unit.gear.remove(gear)
        ctx.actor.base_gear.append(gear)


@effect("angle_shot")
def _angle_shot(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit and an Equipment with the same controller. Attach that
    Equipment to that unit or detach that Equipment from that unit" (Angle
    Shot). Baseline: detach an enemy's Equipment, else attach one of yours
    from base to your mightiest unit."""
    loop = ctx.loop
    pairs = []
    for side in (ctx.opponent_side, ctx.actor_side):
        units = _units_at(ctx, side, "anywhere")
        equipment = [(None, g) for g in loop.gs.get_player(side).base_gear if loop._equip_cost(g) is not None]
        equipment += [(u, g) for u in units for g in u.gear]
        pairs += [(side, u, holder, g) for u in units for holder, g in equipment]
    if not pairs:
        return

    def value(p):
        side, u, holder, g = p
        if side == ctx.opponent_side:
            return (2, 0) if holder is u else (-1, 0)
        return (1, u.might) if holder is None else (0, 0)
    side, unit, holder, gear = loop.choose(_kind("target", spec), ctx.actor_side, pairs,
                                           max(pairs, key=value), ctx.card)
    owner = loop.gs.get_player(side)
    if holder is unit:
        unit.gear.remove(gear)
        owner.base_gear.append(gear)            # detached, stays in base
    else:
        (owner.base_gear if holder is None else holder.gear).remove(gear)
        unit.gear.append(gear)
        loop._fire_attached(unit, side)


@effect("rumble_rebuild")
def _rumble_rebuild(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When I conquer, you may recycle another friendly unit to play a Mech
    from your trash. Reduce its Energy cost by the Might of the unit you
    recycled" (Rumble Hotheaded)."""
    loop = ctx.loop
    me = _source_unit(ctx)
    others = [u for u in _units_at(ctx, ctx.actor_side, "anywhere") if u is not me]
    mechs = [c for c in ctx.actor.trash if "Mech" in (getattr(c, "tags", None) or [])]
    if not others or not mechs:
        return
    victim = loop.choose("cost_unit:recycle", ctx.actor_side, others,
                         max(others, key=lambda u: (u.is_token, u.might)), ctx.card)
    might = victim.might
    affordable = []
    for c in mechs:
        energy, power = loop._effective_cost(c, ctx.actor, from_zone="trash")
        energy = max(0, energy - might)
        if loop._can_pay_card(ctx.actor, c, energy, power):
            affordable.append((c, energy, power))
    if not affordable:
        return
    card, energy, power = loop.choose(_kind("card", spec), ctx.actor_side, affordable,
                                      max(affordable, key=lambda x: _zone_value(x[0])), ctx.card)
    where = _take_off_board(ctx, victim)
    if where is not None:
        ctx.actor.base_gear.extend(victim.gear)
        victim.gear = []
        loop._fire_leaves_board(victim.card, where[0], where[1] or ctx.battlefield)
        if not victim.is_token:
            loop.gs.get_player(loop._owner_of(victim.card, where[0])).deck.cards.insert(0, victim.card)
            loop._note_recycled(ctx.actor_side)
    loop._pay_card(ctx.actor, card, energy, power)
    ctx.actor.trash.remove(card)
    loop._play_unit(card, ctx.actor_side, from_zone="trash")


@effect("convert_x")
def _convert_x(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Pay any amount of Energy to ADD that much [rune]" (Ancient Henge) /
    "Pay any amount of [rune] to ADD that much Energy" (Hextech Anomaly): X
    chosen (baseline: all of it)."""
    loop = ctx.loop
    me = ctx.actor
    if spec.get("from") == "power":
        most = 0
        while loop._can_pay_generic_power(me, most + 1):
            most += 1
    else:
        most = me.energy
    if most <= 0:
        return
    x = loop.choose("amount:" + str(spec.get("effect")), ctx.actor_side, list(range(most + 1)), most, ctx.card)
    if x <= 0:
        return
    if spec.get("from") == "power":
        loop._pay_generic_power(me, x)
        me.energy += x
    else:
        me.energy -= x
        _gain_power_any_domain(ctx, {"amount": x})


@effect("give_my_keywords")
def _give_my_keywords(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "give another friendly unit my keywords ... this turn" (Kato the Arm):
    the unit the previous instruction chose ("it")."""
    me = _source_unit(ctx)
    if me is None:
        return
    keywords = list(me.card.keywords or []) + sorted(me.passive_keywords) + me.turn_keywords + me.granted_keywords
    for unit in ctx.extra.get("it") or []:
        for kw in keywords:
            if kw.split()[0].upper() not in ("UNIQUE",):
                unit.turn_keywords.append(kw)


@effect("play_equipment_attach")
def _play_equipment_attach(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When I attack, you may play an Equipment with Energy cost no more than
    [2], ignoring its cost. If you do, then do this: Attach it to me" (Rell
    Magnetic): from hand."""
    loop = ctx.loop
    me = _source_unit(ctx)
    cap = int(spec.get("energy_at_most", 2))
    cands = [c for c in ctx.actor.hand
             if loop._equip_cost(c) is not None and int(getattr(c, "cost_energy", 0) or 0) <= cap]
    if me is None or not cands:
        return
    card = loop.choose(_kind("card", spec), ctx.actor_side, cands, max(cands, key=_zone_value), ctx.card)
    ctx.actor.hand.remove(card)
    loop._play_gear(card, ctx.actor_side, 0, from_zone="hand")
    if card in ctx.actor.base_gear and loop._locate_unit(me) is not None:
        ctx.actor.base_gear.remove(card)
        me.gear.append(card)
        loop._fire_attached(me, ctx.actor_side)


@effect("banish_with_this")
def _banish_with_this(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """The Zero Drive gives its unit "DEATHKNELL - Banish me": the unit that
    died goes from the trash to banishment, "banished with this"."""
    card = ctx.extra.get("died_card")
    for p in (ctx.actor, ctx.opponent):
        if card is not None and any(c is card for c in p.trash):
            p.trash.remove(card)
            p.banished.append(card)
            ctx.card._banished_with = list(getattr(ctx.card, "_banished_with", [])) + [card]
            return


@effect("play_banished_with_this")
def _play_banished_with_this(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "[3] [mind], Banish this: Play all units banished with this, ignoring
    their costs" (The Zero Drive). `kill_this`: "kill this to play the banished
    card" (Dockside Lock-Up), only while one is still banished."""
    waiting = [c for c in getattr(ctx.card, "_banished_with", [])
               if any(x is c for p in (ctx.actor, ctx.opponent) for x in p.banished)]
    if spec.get("kill_this"):
        if not waiting:
            return
        _kill_gear(ctx, {"target": "self"})
    for card in list(getattr(ctx.card, "_banished_with", [])):
        for p in (ctx.actor, ctx.opponent):
            if any(c is card for c in p.banished):
                p.banished.remove(card)
                ctx.loop._play_unit(card, ctx.actor_side, from_zone="banished")
                break
    ctx.card._banished_with = []


@effect("when_it_dies_this_turn")
def _when_it_dies_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When it dies this turn, play a Gold gear token exhausted" (Deadly
    Flourish), "... channel 1 rune exhausted" (Siphoning Strike): `then` runs
    for this effect's controller when "it" dies (GameLoop._route_deaths); at once
    when the damage before it already killed it."""
    gs = ctx.loop.gs
    for u in ctx.extra.get("it") or []:
        if ctx.loop._locate_unit(u) is not None:
            u.death_bonus = (ctx.actor_side, gs.turn, dict(spec["then"]))
        elif any(u.card in gs.get_player(s).trash for s in ("A", "B")):
            REGISTRY[spec["then"]["effect"]](ctx, spec["then"])


@effect("xp_when_it_wins")
def _xp_when_it_wins(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When it wins a combat this turn, gain 2 XP" (Grim Resolve)."""
    for u in ctx.extra.get("it") or []:
        u.win_xp_turn = ctx.loop.gs.turn


@effect("next_unit_ready_buff")
def _next_unit_ready_buff(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "the next time you play a unit this turn, ready it and BUFF it" (Nami Headstrong)."""
    ctx.loop.gs.next_unit_ready_buff[ctx.actor_side] = ctx.loop.gs.turn


@effect("dancing_grenade")
def _dancing_grenade(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Deal 2 to a unit. Its controller may play this spell again for [rune].
    If they do, this deals 1 additional Bonus Damage for each time this spell
    has dealt damage this turn" (Dancing Grenade): the replays resolve here,
    one after the other (no responses between them); each is chosen by the
    controller of the unit hit last."""
    loop = ctx.loop
    caster = ctx.actor_side
    hits = 0
    while True:
        enemy = loop.gs.other(caster)
        cands = [u for s in (enemy, caster) for u in _units_at(ctx, s, "anywhere")]
        cands = [u for u in cands if loop._can_choose(u, caster, ctx.card)]
        if not cands:
            return
        foes = [u for u in cands if loop._locate_unit(u)[0] == enemy]
        unit = loop.choose(_kind("target", spec), caster, cands, (foes or cands)[0], ctx.card)
        loop._note_chosen(ctx.card, caster, [unit])
        side = loop._locate_unit(unit)[0]
        thrower = loop.gs.get_player(caster)
        type(ctx)(loop, ctx.card, thrower, loop.gs.get_player(loop.gs.other(caster)),
                  ctx.battlefield, ctx.extra).damage_units([unit], 2 + hits)
        hits += 1
        holder = loop.gs.get_player(side)
        if not (loop._can_pay_generic_power(holder, 1) and loop.choose(
                "optional:replay", side, [True, False], side != caster, ctx.card)):
            return
        loop._pay_generic_power(holder, 1)
        caster = side


@effect("hwei_discard_bonus")
def _hwei_discard_bonus(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Then, do the following based on the discarded card's type: Spell - Draw
    1. Gear - Ready up to 2 runes. Unit - Give me +3 [might] this turn" (Hwei
    Brooding Painter)."""
    card = ctx.extra.get("discarded")
    kind = _card_category_name(card) if card is not None else None
    if kind == "SPELL":
        ctx.draw_cards(1)
    elif kind == "GEAR":
        REGISTRY["ready_runes"](ctx, {"amount": 2})
    elif kind in ("UNIT", "CHAMPION"):
        me = _source_unit(ctx)
        if me is not None:
            me.temporary_might += 3


@effect("tokens_become_copies_of_me")
def _tokens_become_copies_of_me(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "play two Reflection unit tokens here. They become copies of me" (Keeper
    of Masks): the tokens the previous instruction played."""
    for u in ctx.extra.get("it") or []:
        copy = _copy_card(ctx.card)
        copy.is_token = True
        u.card = copy


@effect("reflection_of_chosen")
def _reflection_of_chosen(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit. Play a ready Reflection unit token to your base. It
    becomes a copy of that unit. Give it TEMPORARY" (Mirror Image)."""
    loop = ctx.loop
    units = _choosable(ctx, [u for s in (ctx.actor_side, ctx.opponent_side) for u in _units_at(ctx, s, "anywhere")])
    if not units:
        return
    model = loop.choose(_kind("target", spec), ctx.actor_side, units, max(units, key=lambda u: u.might), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [model])
    token = loop._play_token("Reflection", ctx.actor_side, ready=True)
    if token is None:
        return
    copy = _copy_card(model.card)
    copy.is_token = True
    token.card = copy
    token.granted_keywords.append("TEMPORARY")


@effect("temporary_swap")
def _temporary_swap(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit you control and another unit you control at a different
    location. If at least one of them has TEMPORARY, move each to the other's
    location" (Smoke and Mirrors)."""
    loop = ctx.loop
    mine = _units_at(ctx, ctx.actor_side, "anywhere")
    pairs = [(x, y) for i, x in enumerate(mine) for y in mine[i + 1:]
             if loop._locate_unit(x)[1] is not loop._locate_unit(y)[1]
             and (x.has_keyword("TEMPORARY") or y.has_keyword("TEMPORARY"))]
    if not pairs:
        return
    x, y = loop.choose(_kind("target", spec), ctx.actor_side, pairs,
                       max(pairs, key=lambda p: p[0].might + p[1].might), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [x, y])
    bx, by = loop._locate_unit(x)[1], loop._locate_unit(y)[1]
    loop._move_unit_by_effect(x, by)
    loop._move_unit_by_effect(y, bx)


@effect("stun_or_return_attacker")
def _stun_or_return_attacker(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "STUN an attacking unit. If it's already stunned, return it to its
    owner's hand instead" (Existential Dread)."""
    loop = ctx.loop
    cands = _choosable(ctx, [u for s in ("A", "B") for u in _units_at(ctx, s, "battlefield")
                             if loop._is_attacking(u)])
    if not cands:
        return
    unit = loop.choose(_kind("target", spec), ctx.actor_side, cands,
                       max(cands, key=lambda u: (u.stunned, u.might)), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    if unit.stunned:
        _unit_leaves_to(ctx, unit, loop._locate_unit(unit)[0], "hand")
    else:
        unit.stunned = True
        where = loop._locate_unit(unit)
        if where[0] != ctx.actor_side:
            loop._fire_stun_enemy(ctx.actor_side, where[1])


@effect("draw_if_enemy_alone_at_origin")
def _draw_if_enemy_alone_at_origin(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Then, if there's an enemy unit alone at that battlefield, draw 1" (Isolate)."""
    bf = ctx.extra.get("last_move_src")
    if bf is not None and len(bf._units_for(ctx.opponent_side)) == 1:
        ctx.draw_cards(int(spec.get("count", 1)))


@effect("deal_one_each_location")
def _deal_one_each_location(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "choose up to one enemy unit at each location. Deal 1 to them" (Elder
    Dragon): each battlefield and the enemy base."""
    loop = ctx.loop
    groups = [list(bf._units_for(ctx.opponent_side)) for bf in loop.gs.battlefields]
    groups.append(list(ctx.opponent.base_units))
    picked = []
    for g in groups:
        g = _choosable(ctx, g)
        if g:
            picked.append(loop.choose(_kind("target", spec), ctx.actor_side, g,
                                      max(g, key=lambda u: u.might), ctx.card))
    if picked:
        loop._note_chosen(ctx.card, ctx.actor_side, picked)
        ctx.damage_units(picked, int(spec.get("amount", 1)))


@effect("name_tag")
def _name_tag(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "As you play this, name a tag" (The List): baseline the tag most
    common among enemy units."""
    from collections import Counter
    tags = Counter(t for u in _units_at(ctx, ctx.opponent_side, "anywhere") for t in u.tags)
    options = sorted(set(tags) | {t for u in _units_at(ctx, ctx.actor_side, "anywhere") for t in u.tags}) or ["Mech"]
    best = tags.most_common(1)[0][0] if tags else options[0]
    ctx.card._named_tag = ctx.loop.choose("tag", ctx.actor_side, options, best, ctx.card)


@effect("banish_trash_units_with_this")
def _banish_trash_units_with_this(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When you play this, banish all units from your trash" (Cursed
    Sarcophagus): they are "banished with this"."""
    units = [c for c in ctx.actor.trash if _card_category_name(c) in ("UNIT", "CHAMPION")]
    for c in units:
        ctx.actor.trash.remove(c)
        ctx.actor.banished.append(c)
    if units:
        ctx.loop._note_banished(ctx.actor_side, len(units))
    ctx.card._banished_with = list(getattr(ctx.card, "_banished_with", [])) + units


@effect("play_one_banished_with_this")
def _play_one_banished_with_this(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "[tap]: Play a unit banished with this" (Cursed Sarcophagus): paying its
    cost; baseline the costliest affordable one."""
    loop = ctx.loop
    options = []
    for c in getattr(ctx.card, "_banished_with", []):
        if any(x is c for x in ctx.actor.banished):
            energy, power = loop._effective_cost(c, ctx.actor, from_zone="banished")
            if loop._can_pay_card(ctx.actor, c, energy, power):
                options.append((c, energy, power))
    if not options:
        return
    card, energy, power = loop.choose(_kind("card", spec), ctx.actor_side, options,
                                      max(options, key=lambda o: _zone_value(o[0])), ctx.card)
    loop._pay_card(ctx.actor, card, energy, power)
    ctx.actor.banished.remove(card)
    ctx.card._banished_with = [c for c in ctx.card._banished_with if c is not card]
    loop._play_unit(card, ctx.actor_side, from_zone="banished")


@effect("play_unit_from_hand_free_energy")
def _play_unit_from_hand_free_energy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Play a unit from your hand to your base, ignoring its Energy cost. (You
    must still pay its Power cost.)" (Rift Herald's DEATHKNELL)."""
    loop = ctx.loop
    me = ctx.actor
    options = []
    for c in me.hand:
        if _card_category_name(c) in ("UNIT", "CHAMPION"):
            power = int(c.cost_power or 0)
            if loop._can_pay_card(me, c, 0, power):
                options.append(c)
    if not options:
        return
    card = loop.choose(_kind("card", spec), ctx.actor_side, options, max(options, key=_zone_value), ctx.card)
    loop._pay_card(me, card, 0, int(card.cost_power or 0), extras=False)
    me.hand.remove(card)
    loop._play_unit(card, ctx.actor_side, from_zone="hand")


@effect("replay_from_trash_if_small")
def _replay_from_trash_if_small(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Then, if it had 3 [might] or less, you may play this from your trash for
    [rune]" (Death from Below): it may be played from the trash this turn."""
    if "killed_might" in ctx.extra and ctx.extra["killed_might"] <= int(spec.get("might_at_most", 3)):
        ctx.card._trash_replay = (ctx.loop.gs.turn, {"power": 1})


@effect("disempower_or_kill_gear")
def _disempower_or_kill_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an enemy gear. If it's EMPOWERED, disempower it. Otherwise, kill
    it" (Tomb-Raider Barbara)."""
    entries = [e for e in _gear_entries(ctx, enemy_first=True) if e[0] == ctx.opponent_side]
    if not entries:
        return
    side, holder, gear = ctx.loop.choose(_kind("target", spec), ctx.actor_side, entries,
                                         max(entries, key=lambda e: _zone_value(getattr(e[2], "card", e[2]))),
                                         ctx.card)
    card = getattr(gear, "card", gear)
    if ctx.loop._is_empowered(card):
        ctx.loop._disempower(card)
    else:
        _kill_gear(ctx, {"target": "chosen_gear", "_only": card})


@effect("match_might_plus_one")
def _match_might_plus_one(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit here. Increase my Might to its Might this turn, then give
    me +1 [might] this turn" (Dame the Despoiler)."""
    me = _source_unit(ctx)
    where = ctx.loop._locate_unit(me) if me is not None else None
    if where is None or where[1] is None:
        return
    others = [u for s_ in ("A", "B") for u in where[1]._units_for(s_) if u is not me]
    if others:
        model = ctx.loop.choose(_kind("target", spec), ctx.actor_side, others,
                                max(others, key=lambda u: u.might), ctx.card)
        if model.might > me.might:
            me.temporary_might += model.might - me.might
    me.temporary_might += 1


@effect("recall_enemies_total_might")
def _recall_enemies_total_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Return any number of enemy Order units with total Might 5 or less to
    their owners' hands" (Decree of Discord): `domain`, `total`; baseline the
    mightiest ones that fit."""
    loop = ctx.loop
    tf = {"domain": spec.get("domain")} if spec.get("domain") else {}
    cands = [u for u in _choosable(ctx, _units_at(ctx, ctx.opponent_side, "anywhere"))
             if _passes_filter(u, tf, ctx)]
    room = int(spec.get("total", 5))
    picks = []
    for u in sorted(cands, key=lambda u: -u.might):
        if u.might <= room:
            picks.append(u)
            room -= u.might
    picks = loop.choose_many(_kind("target", spec), ctx.actor_side, cands, picks, ctx.card)
    if sum(u.might for u in picks) > int(spec.get("total", 5)):
        return
    for u in picks:
        where = loop._locate_unit(u)
        if where is not None:
            _unit_leaves_to(ctx, u, where[0], "hand")


@effect("akali_retreat")
def _akali_retreat(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "If it's your turn, move a friendly unit in a showdown to base and if I'm
    EMPOWERED ready it" (Akali Rogue Assassin)."""
    loop, gs = ctx.loop, ctx.loop.gs
    if gs.active != ctx.actor_side or not gs.showdown_active or gs.showdown_bf_idx is None:
        return
    units = list(gs.battlefields[gs.showdown_bf_idx]._units_for(ctx.actor_side))
    if not units:
        return
    unit = loop.choose(_kind("target", spec), ctx.actor_side, units, min(units, key=lambda u: u.might), ctx.card)
    loop._move_unit_by_effect(unit, None)
    if loop._is_empowered(ctx.card) and loop._can_ready(unit):
        unit.ready = True


@effect("grant_ready_ability")
def _grant_ready_ability(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ 'give it "[rune] [rune]: Ready me." this turn' (Dominus): "it"."""
    from riftbound.registry.cards_registry import EffectSpec
    eff = EffectSpec.from_dict({"effect": "ready_unit", "trigger": "activated", "target": "self",
                                "cost": {"power": 2}})
    for u in ctx.extra.get("it") or []:
        u.turn_abilities.append((ctx.loop.gs.turn, eff))


@effect("public_execution")
def _public_execution(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit. Kill an enemy unit with less Might than it"
    (Public Execution)."""
    loop = ctx.loop
    mine = _units_at(ctx, ctx.actor_side, "anywhere")
    enemies = _choosable(ctx, _units_at(ctx, ctx.opponent_side, "anywhere"))
    if not mine or not enemies:
        return
    hero = loop.choose(_kind("target", spec), ctx.actor_side, mine, max(mine, key=lambda u: u.might), ctx.card)
    weaker = [e for e in enemies if e.might < hero.might]
    if not weaker:
        return
    victim = loop.choose(_kind("target", spec), ctx.actor_side, weaker, max(weaker, key=lambda u: u.might), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [hero, victim])
    where = _take_off_board(ctx, victim)
    if where is not None:
        loop._route_deaths([(victim, where[0])], where[1] or ctx.battlefield, in_base=where[1] is None,
                           killer=(ctx.actor_side, ctx.card))


@effect("kill_unit_or_gear")
def _kill_unit_or_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Kill an enemy Chaos unit or gear" (Decree of Unity): one choice among
    both; baseline the mightiest unit, else the priciest gear. `side: any` ("a
    unit or gear", Mordekaiser Dominating: an enemy one is the baseline, none
    when only friendly ones are left), `where: here` (Mournful Spirit), `banish`
    ("Banish a unit with 3 [might] or less or a gear": Burn Away; the filter's
    Might is the unit's)."""
    loop = ctx.loop
    tf = spec.get("target_filter") or {}
    here = spec.get("where") == "here"
    sides = (ctx.opponent_side, ctx.actor_side) if spec.get("side") == "any" else (ctx.opponent_side,)
    units, gear = [], []
    for side in sides:
        units += [u for u in _choosable(ctx, _units_at(ctx, side, "here" if here else "anywhere"))
                  if _passes_filter(u, tf, ctx)]
        gear += [getattr(e[2], "card", e[2]) for e in _gear_entries(ctx, enemy_first=True)
                 if e[0] == side and _gear_matches(e[2], tf)
                 and (not here or e[1] is ctx.battlefield
                      or (isinstance(e[1], UnitInPlay) and e[1] in ctx.battlefield._units_for(side)))]
    enemy_units = [u for u in units if loop._locate_unit(u)[0] == ctx.opponent_side]
    enemy_gear = [g for g in gear if any(getattr(e[2], "card", e[2]) is g and e[0] == ctx.opponent_side
                                         for e in _gear_entries(ctx, enemy_first=True))]
    if not enemy_units and not enemy_gear:
        return
    default = max(enemy_units, key=lambda u: u.might) if enemy_units else max(enemy_gear, key=_zone_value)
    pick = loop.choose(_kind("target", spec), ctx.actor_side, units + gear, default, ctx.card)
    if any(pick is g for g in gear):
        if spec.get("banish"):
            _banish_gear(ctx, pick)
        else:
            _kill_gear(ctx, {"target": "chosen_gear", "_only": pick})
        return
    if spec.get("banish"):
        ctx.extra["it"] = [pick]
        _banish_unit(ctx, {"target": "it"})
        return
    where = _take_off_board(ctx, pick)
    if where is not None:
        loop._route_deaths([(pick, where[0])], where[1] or ctx.battlefield, in_base=where[1] is None,
                           killer=(ctx.actor_side, ctx.card))


def _banish_gear(ctx: "EffectContext", gear) -> None:
    """A gear in play goes to its owner's banishment (a token ceases to exist);
    it doesn't die."""
    entry = next(((s, h, g) for s, h, g in _gear_entries(ctx, enemy_first=True)
                  if getattr(g, "card", g) is gear), None)
    if entry is None:
        return
    side, holder, g = entry
    owner = ctx.loop.gs.get_player(side)
    if isinstance(holder, Battlefield):
        holder.gear_for(side).remove(g)
    elif holder is not None:
        holder.gear.remove(g)
    else:
        owner.base_gear.remove(g)
    if not getattr(gear, "is_token", False):
        owner.banished.append(gear)
    ctx.loop._fire_leaves_board(gear, side, holder if isinstance(holder, Battlefield) else ctx.battlefield)


@effect("look_recycle")
def _look_recycle(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Look at the top two cards of your Main Deck. You may recycle one or both
    of them. Put those you don't back in any order" (The Candlelit Sanctum):
    the player picks which go to the bottom, then the order of the rest (top
    first). Baseline: none recycled, the order kept."""
    deck = ctx.actor.deck
    n = max(0, min(int(spec.get("amount", 1)), len(deck.cards)))
    if n == 0:
        return
    look = list(reversed(deck.cards[-n:]))          # top first
    del deck.cards[-n:]
    ctx.loop._offer_reveal_from_top(ctx.actor, look)
    gone = [c for c in look
            if ctx.loop.choose("optional:recycle", ctx.actor_side, [True, False], False, c)]
    rest = [c for c in look if not any(c is g for g in gone)]
    order = []
    while rest:
        first = ctx.loop.choose(_kind("order", spec), ctx.actor_side, list(rest), rest[0], ctx.card)
        order.append(first)
        rest.remove(first)
    deck.cards.extend(reversed(order))               # the first chosen on top
    deck.cards[:0] = gone                            # recycled to the bottom
    if gone:
        ctx.loop._note_recycled(ctx.actor_side)


@effect("recycle_rune")
def _recycle_rune(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You must recycle one of your runes" (Sigil of the Storm): a rune you
    control goes to the bottom of your Rune Deck, your pick; baseline an
    exhausted one of your most plentiful domain."""
    player = ctx.actor
    runes = [r for rs in player.rune_pool.values() for r in rs]
    if not runes:
        return
    count = {d: len(rs) for d, rs in player.rune_pool.items()}
    pick = max(runes, key=lambda r: (not r.ready, count[r.domain]))
    rune = ctx.loop.choose("rune:" + str(spec.get("effect")), ctx.actor_side, runes, pick, ctx.card)
    player.rune_pool[rune.domain].remove(rune)
    if not player.rune_pool[rune.domain]:
        del player.rune_pool[rune.domain]
    player.rune_deck.recycle(rune)
    player.runes_recycled = getattr(player, "runes_recycled", 0) + 1


@effect("champion_from_trash")
def _champion_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may return your Chosen Champion from your trash to your Champion
    Zone if it is empty" (Hallowed Tomb)."""
    gs = ctx.loop.gs
    side = ctx.actor_side
    champ = gs.champion_A if side == "A" else gs.champion_B
    empty = gs.champion_A_deployed if side == "A" else gs.champion_B_deployed
    if champ is None or not empty or not any(c is champ for c in ctx.actor.trash):
        return
    ctx.actor.trash.remove(champ)
    if side == "A":
        gs.champion_A_deployed = False
    else:
        gs.champion_B_deployed = False


@effect("units_cost_more_this_turn")
def _units_cost_more_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Your non-token units cost [1] more to play this turn" (Vaults of Helia)."""
    gs = ctx.loop.gs
    gs.turn_cost_changes.append((ctx.actor_side, gs.turn, {"is_unit": True},
                                 int(spec.get("amount", 1))))


@effect("next_spell_repeat")
def _next_spell_repeat(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Give the next spell you play this turn REPEAT equal to its cost"
    (Temporal Portal)."""
    ctx.loop.gs.next_spell_repeat[ctx.actor_side] = ctx.loop.gs.turn


@effect("next_unit_accelerate")
def _next_unit_accelerate(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "The next unit you play this turn has ACCELERATE" (Firelights' Hideout)."""
    ctx.loop.gs.next_unit_accelerate[ctx.actor_side] = ctx.loop.gs.turn


@effect("spend_buffs_for_runes")
def _spend_buffs_for_runes(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Spend any number of buffs. For each buff spent, channel 1 rune
    exhausted" (Albus Ferros): the buffs of units in base (not fighting)."""
    spent = 0
    for unit in _friendly_units(ctx):
        # "Spend any number of buffs": each buffed unit's, the player's call
        # (baseline: those in base, not fighting).
        if unit.might_counters > 0 and unit.card is not ctx.card and ctx.loop.choose(
                "optional:spend_buff", ctx.actor_side, [True, False],
                ctx.loop._locate_unit(unit)[1] is None, unit.card):
            ctx.loop._spend_buff(unit, ctx.actor_side)
            spent += 1
    if spent:
        ctx.actor.unlock_runes(spent, exhausted=True)
        ctx.loop._extra_channel(ctx.actor_side)


def _send_home(ctx: "EffectContext", units: list) -> None:
    for u in units:
        ctx.loop._move_unit_by_effect(u, None)


@effect("stare_down")
def _stare_down(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a friendly unit and a battlefield. Move all enemy units at that
    battlefield with less Might than the chosen unit to their base. Gain 1
    XP." (Stare Down): the battlefield where the most Might goes home."""
    mine = _units_at(ctx, ctx.actor_side, "anywhere")
    if not mine:
        return
    ref = ctx.loop.choose(_kind("target", spec), ctx.actor_side, mine,
                          max(mine, key=lambda u: u.might), ctx.card)
    best = max(ctx.loop.gs.battlefields,
               key=lambda bf: sum(u.might for u in bf._units_for(ctx.opponent_side) if u.might < ref.might))
    best = ctx.loop.choose(_kind("battlefield", spec), ctx.actor_side, list(ctx.loop.gs.battlefields),
                           best, ctx.card)
    _send_home(ctx, [u for u in list(best._units_for(ctx.opponent_side)) if u.might < ref.might])
    ctx.loop.gs.add_xp(ctx.actor_side, int(spec.get("xp", 1)))


@effect("move_enemies_total_might")
def _move_enemies_total_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Move any number of enemy units with the same controller and a total
    Might of 8 or less to a single location" (Tricksy Tentacles): the
    mightiest enemy battlefield units that fit, to their base."""
    cap = int(spec.get("total", 8))
    picked, total = [], 0
    for u in sorted(_choosable(ctx, _units_at(ctx, ctx.opponent_side, "battlefield")),
                    key=lambda u: u.might, reverse=True):
        # "Any number": one choice per unit that still fits.
        if total + u.might <= cap and ctx.loop.choose(_kind("optional", spec), ctx.actor_side,
                                                      [True, False], True, u.card):
            picked.append(u)
            total += u.might
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, picked)
    _send_home(ctx, picked)


@effect("move_enemy_to_its_units")
def _move_enemy_to_its_units(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Move an enemy unit to a location where there's a unit with the same
    controller" (Temptation): their mightiest battlefield unit to their base
    if they have a unit there, else to another battlefield where they do."""
    loop = ctx.loop
    them = ctx.opponent_side

    def places(u):
        cur = loop._locate_unit(u)[1]
        out = [None] if cur is not None and [x for x in ctx.opponent.base_units if x is not u] else []
        return out + [bf for bf in loop.gs.battlefields
                      if bf is not cur and [x for x in bf._units_for(them) if x is not u]]
    cands = [u for u in sorted(_choosable(ctx, _units_at(ctx, them, "anywhere")), key=lambda u: -u.might)
             if places(u)]
    if not cands:
        return
    u = loop.choose(_kind("target", spec), ctx.actor_side, cands, cands[0], ctx.card)
    options = places(u)
    dst = loop.choose(_kind("destination", spec), ctx.actor_side, options, options[0], ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [u])
    loop._move_unit_by_effect(u, dst)


@effect("card_sharp")
def _card_sharp(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You and each opponent may play a Gold gear token exhausted. For each
    opponent who did, you play a Gold gear token exhausted." (Card Sharp):
    the opponent takes theirs."""
    loop = ctx.loop
    loop._play_token("Gold", ctx.actor_side)
    loop._play_token("Gold", ctx.opponent_side)
    loop._play_token("Gold", ctx.actor_side)


@effect("party_favors")
def _party_favors(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Each other player chooses Cards or Runes ..." (Party Favors): the
    opponent chooses Cards, so both players draw 1."""
    ctx.draw_cards(1, target="actor")
    ctx.draw_cards(1, target="opponent")


@effect("divine_judgment")
def _divine_judgment(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Each player chooses 2 units, 2 gear, 2 runes, and 2 cards in their
    hands. Recycle the rest." (Divine Judgment): each keeps the mightiest
    units, the costliest gear and cards."""
    loop = ctx.loop
    keep = int(spec.get("keep", 2))
    for side in ("A", "B"):
        p = loop.gs.get_player(side)
        units = sorted(_units_at(ctx, side, "anywhere"), key=lambda u: u.might, reverse=True)
        kept = loop.choose_many("keep:units", side, units, units[:keep], ctx.card)
        for u in [u for u in units if not any(u is k for k in kept)]:
            where = loop._locate_unit(u)
            if where[1] is None:
                p.base_units.remove(u)
            else:
                where[1].remove_unit(side, u)
            p.base_gear.extend(u.gear)
            u.gear = []
            loop._fire_leaves_board(u.card, side, where[1] or loop.gs.battlefields[0])
            if not u.is_token:
                p.deck.cards.insert(0, u.card)
        gear = sorted(p.base_gear, key=_zone_value, reverse=True)
        kept = loop.choose_many("keep:gear", side, gear, gear[:keep], ctx.card)
        for g in [g for g in gear if not any(g is k for k in kept)]:
            p.base_gear.remove(g)
            if not getattr(g, "is_token", False):
                p.deck.cards.insert(0, g)
        runes = [r for d in list(p.rune_pool) for r in p.rune_pool[d]]
        for r in runes[keep:]:
            p.rune_pool[r.domain].remove(r)
            r.ready = True
            p.rune_deck.runes.append(r)
        hand = sorted(p.hand, key=_zone_value, reverse=True)
        kept = loop.choose_many("keep:hand", side, hand, hand[:keep], ctx.card)
        for c in [c for c in hand if not any(c is k for k in kept)]:
            p.hand.remove(c)
            p.deck.cards.insert(0, c)


@effect("twisted_fate_reveal")
def _twisted_fate_reveal(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Reveal the top rune of your rune deck, then recycle it. [fury] - Deal 2
    to an enemy unit here and 1 to all other enemy units here. [mind] - Draw
    1. [order] - Stun an enemy unit." (Twisted Fate Gambler)"""
    from .enums import Domain
    enemies = _choosable(ctx, list(ctx.battlefield._units_for(ctx.opponent_side)))
    useful = {Domain.MIND} | ({Domain.FURY, Domain.ORDER} if enemies else set())
    ctx.loop._before_deck_reveal(ctx.actor_side, value=lambda r: r.domain in useful, rune=True)
    runes = ctx.actor.rune_deck.runes
    if not runes:
        return
    rune = runes.pop(0)
    runes.append(rune)
    if rune.domain is Domain.FURY and enemies:
        first = ctx.loop.choose(_kind("target", spec), ctx.actor_side, enemies,
                                max(enemies, key=lambda u: (2 >= u.might - u.damage, u.might)), ctx.card)
        ctx.damage_units([first], 2)
        ctx.damage_units([u for u in ctx.battlefield._units_for(ctx.opponent_side) if u is not first], 1)
    elif rune.domain is Domain.MIND:
        ctx.draw_cards(1, target="actor")
    elif rune.domain is Domain.ORDER:
        REGISTRY["stun_unit"](ctx, {"target": "enemy_unit"})


@effect("teemo_reveal_damage")
def _teemo_reveal_damage(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an enemy unit here and reveal the top 5 cards of your Main Deck.
    Deal 1 to that unit for each card with HIDDEN revealed this way, then
    recycle the revealed cards." (Teemo Strategist)"""
    enemies = _choosable(ctx, list(ctx.battlefield._units_for(ctx.opponent_side)))
    if not enemies:
        return
    # Chosen first, then the reveal (baseline: the mightiest).
    unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, enemies,
                           max(enemies, key=lambda u: u.might), ctx.card)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    ctx.loop._before_deck_reveal(ctx.actor_side, value=lambda c: c.has_keyword("HIDDEN"))
    deck = ctx.actor.deck.cards
    ctx.loop._note_revealed(ctx.actor_side, deck[-5:])
    revealed = [deck.pop() for _ in range(min(5, len(deck)))]
    n = sum(1 for c in revealed if c.has_keyword("HIDDEN"))
    for c in revealed:
        deck.insert(0, c)
    if n:
        ctx.damage_units([unit], n)


@effect("kill_total_might_at_battlefield")
def _kill_total_might_at_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Kill any number of units at a battlefield with total Might 4 or less"
    (Fox-Fire): the enemy units, mightiest first, at the battlefield where
    that kills the most Might."""
    cap = int(spec.get("total", 4))
    loop = ctx.loop

    def plan(bf):
        picked, total = [], 0
        for u in sorted(_choosable(ctx, list(bf._units_for(ctx.opponent_side))), key=lambda u: -u.might):
            if total + u.might <= cap:
                picked.append(u)
                total += u.might
        return picked
    best = max(loop.gs.battlefields, key=lambda bf: sum(u.might for u in plan(bf)))
    best = loop.choose(_kind("battlefield", spec), ctx.actor_side, list(loop.gs.battlefields), best, ctx.card)
    baseline = plan(best)
    victims, total = [], 0
    # "Any number of units" (either player's): one choice per unit that still fits.
    for u in _choosable(ctx, list(best.units_A) + list(best.units_B)):
        if total + u.might <= cap and loop.choose(_kind("optional", spec), ctx.actor_side, [True, False],
                                                  any(u is b for b in baseline), u.card):
            victims.append(u)
            total += u.might
    if not victims:
        return
    loop._note_chosen(ctx.card, ctx.actor_side, victims)
    dead = []
    for u in victims:
        side = loop._locate_unit(u)[0]
        best.remove_unit(side, u)
        dead.append((u, side))
    loop._route_deaths(dead, best)


@effect("mechanical_bandit")
def _mechanical_bandit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Each player reveals the top card of their Main Deck. If you revealed a
    card with the lowest Energy cost, draw it. Recycle the rest." (Mechanical
    Bandit). With a Void Hatchling, each player wants a cheap card on top."""
    for side in (ctx.actor_side, ctx.opponent_side):
        ctx.loop._before_deck_reveal(side, value=lambda c: -int(c.cost_energy or 0))
    mine, theirs = ctx.actor.deck.cards, ctx.opponent.deck.cards
    my_top = mine[-1] if mine else None
    their_top = theirs[-1] if theirs else None
    ctx.loop._note_revealed(ctx.actor_side, [my_top] if my_top is not None else [])
    ctx.loop._note_revealed(ctx.opponent_side, [their_top] if their_top is not None else [])
    if their_top is not None:
        theirs.insert(0, theirs.pop())
    if my_top is None:
        return
    if their_top is None or (my_top.cost_energy or 0) <= (their_top.cost_energy or 0):
        ctx.draw_cards(1)
    else:
        mine.insert(0, mine.pop())


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
                 if d is not None and loop.gs.battlefields[d].control() == side]
        energy, power = loop._effective_cost(card, ap)
        energy = max(0, energy - reduce)
        if dests and loop._can_pay_card(ap, card, energy, power) and \
                (best is None or _zone_value(card) > _zone_value(best[0])):
            best = (card, dests, energy, power)
    if best is None:
        return
    playable = []
    for card in ap.hand:
        if not isinstance(card, UnitCard):
            continue
        dests = [d for d in loop._unit_play_destinations(card, side)
                 if d is not None and loop.gs.battlefields[d].control() == side]
        energy, power = loop._effective_cost(card, ap)
        energy = max(0, energy - reduce)
        if dests and loop._can_pay_card(ap, card, energy, power):
            playable.append((card, dests, energy, power))
    best = next(x for x in playable if x[0] is best[0])
    best = loop.choose(_kind("card", spec), side, playable, best, ctx.card)
    card, dests, energy, power = best
    loop._pay_card(ap, card, energy, power)
    ap.hand.remove(card)
    options = [loop.gs.battlefields[d] for d in dests]
    bf = loop.choose(_kind("battlefield", spec), side, options,
                     max(options, key=lambda b: sum(u.might for u in b._units_for(ctx.opponent_side))),
                     ctx.card)
    loop._play_unit(card, side, bf=bf)


@effect("ready_legend")
def _ready_legend(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Ready your legend" (Hall of Legends, Heartening Soul). With several
    (Neeko Blending In), its player picks an exhausted one (§355.10.g; baseline:
    the Champion Legend first)."""
    loop, side = ctx.loop, ctx.actor_side
    tired = [lu for lu in loop._legend_units(side) if not lu.ready]
    if tired:
        legend = loop.choose(_kind("target", spec), side, tired, tired[0], ctx.card)
        legend.ready = True
        loop._fire_readied(legend, side)


@effect("add_extra_legend")
def _add_extra_legend(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When you play me, choose one of those Legends and add it to your Legend
    Zone while I'm on the board" (Neeko Blending In): one of the legends her
    player chose while building the deck, not in the zone already. Theirs, also
    for an opponent's Neeko played from the trash (Kharox FAQ). Baseline: the
    first the deck lists."""
    loop, side = ctx.loop, ctx.actor_side
    neeko = loop._find_unit_by_card(ctx.card)
    if neeko is None:
        return                      # she left the board before this resolved
    there = {lu.card.name for lu in loop._legend_units(side)}
    options = [c for c in loop.gs.extra_legends[side] if c.name not in there]
    if options:
        pick = loop.choose(_kind("target", spec), side, options, options[0], ctx.card)
        loop._add_legend(side, pick, neeko)


@effect("return_gear_to_hand")
def _return_gear_to_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Return a gear to its owner's hand" (Factory Recall): the opponent's
    costliest gear (a token ceases to exist). `target: self`: "return this to
    its owner's hand" (The Good Stuff, Demacian Standard)."""
    if spec.get("target") == "self":
        entries = [(s, h, g) for s, h, g in _gear_entries(ctx, enemy_first=False)
                   if getattr(g, "card", g) is ctx.card]
    else:
        entries = _gear_entries(ctx, enemy_first=True)
    if not entries:
        return
    pick = max(entries, key=lambda e: (e[0] == ctx.opponent_side, _zone_value(getattr(e[2], "card", e[2]))))
    side, holder, gear = ctx.loop.choose(_kind("target", spec), ctx.actor_side, entries, pick, ctx.card)
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
    who = loop.choose("player", ctx.actor_side, [ctx.opponent, me], ctx.opponent, ctx.card)
    if ctx.card in me.base_gear:
        me.base_gear.remove(ctx.card)
    else:
        holder = next((u for u in _units_at(ctx, ctx.actor_side, "anywhere") if ctx.card in u.gear), None)
        if holder is None:
            return
        holder.gear.remove(ctx.card)
    who.base_gear.append(ctx.card)          # recalled to that player's base


@effect("ready_gear")
def _ready_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Ready a gear" / "Ready 2 gear" (Jayce Defender of Tomorrow): your
    exhausted gear (in base, attached or deployed), chosen; baseline the
    costliest. `may_detach`: "If it's an equipment, you may detach it"
    (Veiled Temple; baseline: it stays)."""
    loop = ctx.loop
    if loop._readying_blocked(ctx.actor_side):
        return                                   # Mageseeker Warden
    holders = {id(getattr(g, "card", g)): h for side, h, g in _gear_entries(ctx, enemy_first=False)
               if side == ctx.actor_side}
    gear = [getattr(g, "card", g) for side, _h, g in _gear_entries(ctx, enemy_first=False)
            if side == ctx.actor_side and getattr(getattr(g, "card", g), "tapped", False)]
    picks = sorted(gear, key=_zone_value, reverse=True)[:int(spec.get("count", 1))]
    for g in loop.choose_many(_kind("target", spec), ctx.actor_side, gear, picks, ctx.card):
        g.tapped = False
        holder = holders.get(id(g))
        attached = holder is not None and not isinstance(holder, Battlefield)
        if spec.get("may_detach") and attached and \
                loop.choose("optional:detach", ctx.actor_side, [True, False], False, ctx.card):
            holder.gear.remove(g)
            ctx.actor.base_gear.append(g)


@effect("disempower_then_kill")
def _disempower_then_kill(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose a unit. If it's EMPOWERED, disempower it. Then kill it if it has
    3 [might] or less" (Lacerate): any unit, anywhere (`target` / `where`,
    default chosen_unit anywhere). Baseline: an enemy it kills (the mightiest),
    else an empowered enemy."""
    loop = ctx.loop
    cap = int(spec.get("might_at_most", 3))
    pool = {**spec, "target": spec.get("target", "chosen_unit"),
            "where": spec.get("where", "anywhere"), "scope": "all"}
    units = _choosable(ctx, _resolve_targets(ctx, pool))
    if not units:
        return
    enemies = {id(u) for u in _units_at(ctx, ctx.opponent_side, "anywhere")}

    def after(u):
        was = u.empowered
        u.empowered, u.empower_times = False, 0
        loop._recompute_passives()
        m = u.might
        u.empowered = was
        loop._recompute_passives()
        return m

    def value(u):
        return (id(u) in enemies, after(u) <= cap, u.empowered, u.might)
    unit = loop.choose(_kind("target", spec), ctx.actor_side, units, max(units, key=value), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    loop._disempower(unit.card)
    loop._recompute_passives()
    if unit.might <= cap:
        side, bf = _take_off_board(ctx, unit)
        loop._route_deaths([(unit, side)], bf or ctx.battlefield, in_base=bf is None,
                           killer=(ctx.actor_side, ctx.card))


@effect("move_empowerment")
def _move_empowerment(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may disempower something you control to empower a legend, unit, or
    gear" (Profiteer): only when an EMPOWERED ability would gain from it."""
    loop = ctx.loop
    side = ctx.actor_side
    mine = _units_at(ctx, side, "anywhere")
    holders = [u.card for u in mine + loop._legend_units(side)] + \
        list(ctx.actor.base_gear) + loop._controlled_attached_gear(side)
    src = next((c for c in holders if loop._is_empowered(c) and not _uses_empowered(c)), None)
    dst = next((c for c in holders if not loop._is_empowered(c) and _uses_empowered(c)), None)
    if src is not None and dst is not None:
        # The player's choices (baseline: from one that doesn't use it to one that does).
        froms = [c for c in holders if loop._is_empowered(c)]
        src = loop.choose(_kind("target", spec) + ":from", side, froms, src, ctx.card)
        tos = [c for c in holders if not loop._is_empowered(c) and c is not src]
        dst = loop.choose(_kind("target", spec), side, tos, dst, ctx.card)
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
        gears = [g for u in holders for g in u.gear if loop._equip_cost(g) is not None]
        if not gears or not at_bf:
            return
        gear = loop.choose(_kind("card", spec), ctx.actor_side, gears, gears[0], ctx.card)
        next(u for u in holders if gear in u.gear).gear.remove(gear)
        target = loop.choose("equip", ctx.actor_side, at_bf, max(at_bf, key=lambda u: u.might), ctx.card)
    else:
        gears = [g for g in ctx.actor.base_gear if loop._equip_cost(g) is not None]
        if not gears:
            return
        gear = loop.choose(_kind("card", spec), ctx.actor_side, gears, gears[0], ctx.card)
        ctx.actor.base_gear.remove(gear)
        target = loop.choose("equip", ctx.actor_side, mine,
                             max(at_bf or mine, key=lambda u: u.might), ctx.card)
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
    """ "Choose a unit. Prevent the next 7 damage that would be dealt to it
    this turn" (Ki Barrier): any unit (`target` / `where`, default chosen_unit
    anywhere). Baseline: the friendly unit losing its fight, else the mightiest."""
    pool = {**spec, "target": spec.get("target", "chosen_unit"),
            "where": spec.get("where", "anywhere"), "scope": "all"}
    units = _choosable(ctx, _resolve_targets(ctx, pool))
    if not units:
        return
    friends = {id(u) for u in _friendly_units(ctx)}

    def threatened(u):
        where = ctx.loop._locate_unit(u)
        bf = where[1] if where else None
        enemy = sum(x.might for x in bf._units_for(ctx.opponent_side)) if bf else 0
        return (id(u) in friends, enemy >= u.might - u.damage, u.might)
    unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, units, max(units, key=threatened), ctx.card)
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
    units = list(ctx.battlefield._units_for(ctx.actor_side))
    if units:
        unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, units,
                               max(units, key=lambda u: u.keyword_value("SHIELD")), ctx.card)
        if unit.keyword_value("SHIELD"):
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
    source = ctx.loop.choose(_kind("target", spec), ctx.actor_side, mine,
                             max(mine, key=lambda u: u.might), ctx.card)
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
    unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, enemies,
                           max(enemies, key=lambda u: (amount >= u.might - u.damage, u.might)), ctx.card)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    # Its controller chooses: let you draw, or take the damage.
    if ctx.loop.choose(_kind("optional", spec), ctx.opponent_side, [True, False],
                       amount >= unit.might - unit.damage, ctx.card):
        ctx.draw_cards(int(spec.get("draw", 2)), target="actor")
    else:
        ctx.damage_units([unit], amount)


@effect("cant_be_chosen_this_turn")
def _cant_be_chosen_this_turn(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "It can't be chosen by enemy spells and abilities this turn" (Twilight
    Shroud)."""
    for unit in _resolve_targets(ctx, spec):
        unit.cant_be_chosen_turn = ctx.loop.gs.turn


@effect("opponents_cant_play_spells")
def _opponents_cant_play_spells(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Opponents can't play spells this turn" (Cataclysm)."""
    ctx.loop.gs.cant_play_spells_turn[ctx.opponent_side] = ctx.loop.gs.turn


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
        dst = ctx.loop.choose(_kind("destination", spec), ctx.actor_side, opts,
                              max(opts, key=lambda bf: len(bf._units_for(ctx.opponent_side))), ctx.card)
        ctx.loop._move_unit_by_effect(me, dst)


@effect("ready_or_exhaust_legend")
def _ready_or_exhaust_legend(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Ready or exhaust a legend" (Royal Entourage): ready yours if it is
    exhausted, else exhaust the opponent's (with several legends, the first
    that qualifies)."""
    loop = ctx.loop
    mine = next((lu for lu in loop._legend_units(ctx.actor_side) if not lu.ready), None)
    theirs = next((lu for lu in loop._legend_units(ctx.opponent_side) if lu.ready), None)
    if mine is not None:
        mine.ready = True
        loop._fire_readied(mine, ctx.actor_side)
    elif theirs is not None:
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
        card = ctx.loop.choose(_kind("card", spec), ctx.actor_side, list(hand),
                               max(hand, key=_zone_value), ctx.card)
        hand.remove(card)
        where = ctx.loop.choose("deck_position", ctx.actor_side, ["bottom", "top"], "bottom", ctx.card)
        if where == "top":
            ctx.actor.deck.cards.append(card)
        else:
            ctx.actor.deck.cards.insert(0, card)
            ctx.loop._note_recycled(ctx.actor_side)


def _unit_leaves_to(ctx: "EffectContext", unit, side: str, to: str) -> None:
    """Take a unit off the board to its owner's hand or the top or bottom of
    their Main Deck (`to`: "hand" / "deck_top" / "deck_bottom"); its gear
    stays on the board, in base. A token ceases to exist."""
    loop = ctx.loop
    where = loop._locate_unit(unit)
    if where is None:
        return
    owner = loop.gs.get_player(side)
    if where[1] is None:
        owner.base_units.remove(unit)
    else:
        where[1].remove_unit(side, unit)
    # Its Equipment stays on the board, detached where the unit was, then
    # recalled to base (§436.4.b, §323.6).
    owner.base_gear.extend(unit.gear)
    unit.gear = []
    loop._fire_leaves_board(unit.card, side, where[1] or loop.gs.battlefields[0])
    if to == "hand" and where[1] is not None and where[1].card is not None and \
            loop._has_effect(where[1].card, "rippers_bay") and owner.energy >= 1             and owner.rune_deck.runes:
        # "When a unit here is returned to a player's hand, that player may pay
        # [1] to channel 1 rune exhausted" (Ripper's Bay).
        owner.energy -= 1
        owner.unlock_runes(1, exhausted=True)
        loop._extra_channel("A" if owner is loop.gs.A else "B")
    if unit.is_token:
        return
    owner = loop.gs.get_player(loop._owner_of(unit.card, side))
    unit.card._owner = None
    if to == "hand":
        owner.hand.append(unit.card)
    elif to == "deck_bottom":
        owner.deck.cards.insert(0, unit.card)
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
                if not (dg.is_token or getattr(dg.card, "is_token", False)):
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
        keep = loop.choose(_kind("keep", spec), side, units, max(units, key=lambda u: u.might), ctx.card)
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
        unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, enemies,
                               max(enemies, key=lambda u: u.might), ctx.card)
        ctx.loop._note_chosen(ctx.card, ctx.actor_side, [unit])
        where = ctx.loop.choose(_kind("mode", spec), ctx.opponent_side, ["deck_top", "deck_bottom"],
                                "deck_top", ctx.card)
        _unit_leaves_to(ctx, unit, ctx.opponent_side, where)


@effect("each_player_bounces")
def _each_player_bounces(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Starting with the next player, each player may return a unit to its
    owner's hand" (Whirlwind): each returns the other's mightiest unit."""
    for chooser, victim in ((ctx.opponent_side, ctx.actor_side), (ctx.actor_side, ctx.opponent_side)):
        units = [u for u in _units_at(ctx, victim, "anywhere") if ctx.loop._can_choose(u, chooser, ctx.card)]
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
        if spec.get("banish"):
            ctx.card._flow_banish = True      # "Then banish this" (Forbidden Technique)
        ctx.loop._play_from_zone_now(ctx.actor, ctx.card, ctx.actor_side, "trash")


@effect("sacrifice_for_points")
def _sacrifice_for_points(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "You may kill 3 other friendly units and/or gear to score 1 point"
    (Bottled Constellation). Baseline: only when `count` tokens (units or gear)
    can pay it, so no real card is thrown away."""
    loop = ctx.loop
    me, side = ctx.actor, ctx.actor_side
    count = int(spec.get("count", 3))
    all_units = [u for u in _units_at(ctx, side, "anywhere") if u.card is not ctx.card]
    all_gear = [g for g in me.base_gear if g is not ctx.card]
    if len(all_units) + len(all_gear) < count:
        return
    units = [u for u in all_units if u.is_token]
    gear = [g for g in all_gear if getattr(g, "is_token", False)]
    if not loop.choose(_kind("optional", spec), side, [True, False],
                       len(units) + len(gear) >= count, ctx.card):
        return
    # Which ones (baseline: tokens first, then the weakest units).
    from .combat import UnitInPlay
    order = gear + units + sorted([u for u in all_units if not u.is_token], key=lambda u: u.might) + \
        [g for g in all_gear if not getattr(g, "is_token", False)]
    picked = loop.choose_many("cost_unit:" + str(spec.get("effect")), side, order, order[:count], ctx.card)
    for g in [x for x in picked if not isinstance(x, UnitInPlay)]:
        loop._remove_gear(g, me)
    for u in [x for x in picked if isinstance(x, UnitInPlay)]:
        where = loop._locate_unit(u)
        if where[1] is None:
            me.base_units.remove(u)
        else:
            where[1].remove_unit(side, u)
        loop._route_deaths([(u, side)], where[1] or loop.gs.battlefields[0], in_base=where[1] is None)
    _score_point(ctx, {"amount": int(spec.get("amount", 1))})


@effect("banish_top_playable")
def _banish_top_playable(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Banish the top card of your Main Deck. Until your next Ending Phase,
    you may play that card. (You still pay its costs.)" (Runeblade Anvil,
    Akali Brash): GameLoop offers it as a "banished_play" ability until the
    end of the player's next turn (this turn, if it is theirs and its Ending
    Phase hasn't begun; FAQ: during it, their following turn)."""
    player, side = ctx.actor, ctx.actor_side
    if not player.deck.cards:
        return
    card = player.deck.cards.pop()
    player.banished.append(card)
    ctx.loop._note_banished(side)
    gs = ctx.loop.gs
    card._banish_play_side = side
    if gs.active != side:
        card._banish_play_until = gs.turn + 1
    else:
        card._banish_play_until = gs.turn + 2 if gs.in_ending_phase else gs.turn


@effect("reveal_play_top")
def _reveal_play_top(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Reveal (or look at) cards from the top of a Main Deck, banish one and
    play it (Blind Fury, Drakehound Packmaster, Void Rush, Rek'Sai, Dazzling
    Aurora, Baited Hook, Clocktower Guardian, Wild Claw, Promising Future).
    - `source`: "own" (default) or "opponent" (their deck; you play it).
      `each_player`: every player does it with their own deck, the opponent
      first ("Starting with the next player").
    - `look` (default 1) cards, or `until` a card of that type ("unit");
      `reveal`: they are revealed, not looked at (true: by you; "owner").
    - which can be played: `filter` / `target_filter`; `kill_friendly`: first
      kill your weakest unit, then only cards with Might up to `might_margin`
      more than it (Baited Hook).
    - `pay`: "ignore" (default), "ignore_energy" (still pay its Power),
      "cost" (pay it), or "reduce" by `reduce` Energy.
    - `rest`: "recycle" (default), "draw" (yours), "banish" or "trash".
    - `may`: the play is a "you may"; `zone`: where it is played from
      ("banished" default; "deck": Reinforce); `here`: a unit may be played
      to this battlefield (Rek'Sai Swarm Queen). A card of the opponent's
      stays theirs (Card._owner).
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
        loop._route_deaths([(victim, chooser_side)], where[1] or gs.battlefields[0],
                           in_base=where[1] is None)
    until = spec.get("until")
    match = {"filter": spec.get("filter") or until, "target_filter": spec.get("target_filter") or {}}
    mode = str(spec.get("pay", "ignore")).lower()

    def candidate(card):
        return _zone_effect_card_ok(card, match) and (
            might_cap is None or int(getattr(card, "might", 0) or 0) <= might_cap)

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

    # `reveal`: a reveal, not a look (Void Hatchling): by the chooser, or
    # "owner": the deck's owner (Blind Fury: "Each opponent reveals").
    if spec.get("reveal"):
        revealer = owner_side if spec["reveal"] == "owner" else chooser_side
        loop._before_deck_reveal(revealer, owner_side, mine=revealer == chooser_side,
                                 value=lambda c: _zone_value(c)[0] + 1
                                 if candidate(c) and price(c) is not None else 0)
    deck = owner.deck.cards
    revealed = []
    if until:
        while deck:
            revealed.append(deck.pop())
            if _zone_effect_card_ok(revealed[-1], {"filter": until}):
                break
    else:
        for _ in range(min(int(spec.get("look", 1)), len(deck))):
            revealed.append(deck.pop())
    loop._note_revealed(owner_side, revealed)
    cands = [c for c in revealed if candidate(c)]
    playable = [c for c in cands if price(c) is not None]
    pick = max(playable, key=_zone_value) if playable else None
    if pick is not None and spec.get("may") and not loop.choose(
            "optional:play", chooser_side, [True, False], True, ctx.card):
        pick = None                    # "You may play a unit from among them" (Reinforce)
    if pick is not None:
        pick = loop.choose(_kind("card", spec), chooser_side, playable, pick, ctx.card)
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
        zone = str(spec.get("zone", "banished"))
        if owner is chooser:
            if zone == "banished":
                loop._note_banished(chooser_side)
        else:
            pick._owner = owner_side            # theirs, played by you (Blind Fury)
        here = ctx.extra.get("battlefield") or ctx.battlefield
        if spec.get("here") and isinstance(pick, UnitCard) and here in gs.battlefields and (
                loop.choose("unit_location", chooser_side, [here, None], here, ctx.card) is here):
            # "If it is a unit, you may play it here" (Rek'Sai Swarm Queen)
            prev = here.controller()
            loop._play_unit(pick, chooser_side, bf=here, from_zone=zone)
            loop._arrive_at(here, chooser_side, prev)
        else:
            loop._play_from_zone_now(chooser, pick, chooser_side, zone)
        if spec.get("empower") and loop._locate_unit_or_gear(pick, chooser_side):
            loop._empower(pick, chooser_side)          # Wild Claw: "Empower it."
    rest = str(spec.get("rest", "recycle")).lower()
    if rest == "recycle" and revealed:
        loop._note_recycled(owner_side)
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
    if spec.get("any_side"):
        # "Banish a unit, then its owner plays it" (Temporal Breach): either side.
        units += [u for u in _units_at(ctx, ctx.opponent_side, "anywhere") if not u.is_token]
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
    unit = loop.choose(_kind("target", spec), me, units, unit, ctx.card)
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


@effect("reveal_top")
def _reveal_top(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Reveal the top card of your Main Deck. If it's a unit, draw it.
    Otherwise, put it in your trash and give me +2 [might] this turn" (Pakaa
    Protector). `target_filter`: what is drawn; `otherwise`: "trash", "recycle"
    (to the bottom: Ravenbloom Conservatory) or "top" (stays on top, the
    default); `else`: effects run when it isn't drawn."""
    player = ctx.actor
    tf = spec.get("target_filter") or {}
    ctx.loop._before_deck_reveal(ctx.actor_side, value=lambda c: _zone_card_matches(c, tf))
    if not player.deck.cards:
        return
    top = player.deck.cards[-1]
    ctx.loop._note_revealed(ctx.actor_side, [top])
    if _zone_card_matches(top, tf):
        if spec.get("to_hand"):
            # "put it in your hand": not a draw (Ravenbloom Conservatory)
            player.hand.append(player.deck.cards.pop())
        else:
            ctx.draw_cards(1)
        return
    if spec.get("otherwise") == "trash":
        player.deck.cards.pop()
        player.trash.append(top)
    elif spec.get("otherwise") == "recycle":
        player.deck.cards.pop()
        player.deck.cards.insert(0, top)
    for sub in spec.get("else") or []:
        handler = REGISTRY.get(sub.get("effect"))
        if handler:
            handler(ctx, sub)


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
    domain = ctx.loop.choose(_kind("domain", spec), ctx._side_for_player(player),
                             list(Domain), domain, ctx.card)
    player.add_power(domain, amount)
    if ctx.card.name == "Gold" and ctx.loop._gold_bonus(ctx._side_for_player(player)):
        player.energy += 1     # "your Gold ADD an additional [1]" (Renata Glasc Chem-Baroness)


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
        if spec.get("gear_and_runes"):
            # "... units, gear, and/or runes" (Acceleration Gate): then runes (a
            # readied rune is its Energy back, see ready_runes), then gear.
            exhausted += [r for rs in ctx.actor.rune_pool.values() for r in rs if not r.ready]
            if not ctx.loop._readying_blocked(ctx.actor_side):
                exhausted += [getattr(g, "card", g) for side, _h, g in _gear_entries(ctx, enemy_first=False)
                              if side == ctx.actor_side and getattr(getattr(g, "card", g), "tapped", False)]
        from .cards import Card
        from .player import Rune
        picks = ctx.loop.choose_many(_kind("target", spec), ctx.actor_side, exhausted,
                                     exhausted[:int(spec["amount"])], ctx.card)
        for pick in picks:
            if isinstance(pick, Rune):
                ctx.actor.energy += 1
            elif isinstance(pick, Card):
                pick.tapped = False
            else:
                pick.ready = True
                ctx.loop._fire_readied(pick, ctx.actor_side)
        return
    if target in ("all_friendly_units_anywhere", "your_units", "all_enemy_units_anywhere"):
        # "Ready your units" (On the Hunt, Shurelya's Requiem), "ready all enemy
        # units" (Firebrand Raider): wherever they are.
        side = ctx.opponent_side if target == "all_enemy_units_anywhere" else ctx.actor_side
        units = _friendly_units(ctx) if side == ctx.actor_side else ctx.loop._friendly_units_of(side)
        for unit in units:
            if not unit.ready and ctx.loop._can_ready(unit):
                unit.ready = True
                ctx.loop._fire_readied(unit, side)
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
    """Channel runes from the rune deck into play ('channel N rune(s)[, exhausted]').
    `target: each_player`: "each player channels 1 rune exhausted" (The
    Papertree), the actor first."""
    count = int(spec.get("count", spec.get("amount", 1)))
    target = str(spec.get("target", "actor"))
    players = [ctx.actor, ctx.opponent] if target == "each_player" else [ctx._player_for_target(target)]
    for player in players:
        before = player.total_runes_in_play()
        player.unlock_runes(count, exhausted=_coerce_bool(spec.get("exhausted", False)))
        ctx.loop._extra_channel("A" if player is ctx.loop.gs.A else "B")
        if spec.get("draw_if_short") and player.total_runes_in_play() - before < count:
            # "Channel 2 runes exhausted. If you couldn't channel 2 runes this way,
            # draw 1" (Catalyst of Aeons, Mobilize).
            ctx.draw_cards(int(spec["draw_if_short"]), target="actor")


@effect("grant_temporary_might")
def _grant_temporary_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    amount = _amount(ctx, spec)
    floor = spec.get("minimum", spec.get("min_might"))
    # "Give a unit -2 [might]" (Frigid Touch): an enemy first.
    if amount < 0 and not str(spec.get("target", "")).startswith("all"):
        # "If a spell or ability you control would give -[might] to a unit it
        # chooses, it gives an additional -1 [might]" (Mel Newly Awakened).
        amount -= ctx.loop._extra_might_reduction(ctx.actor_side)
    for unit in _resolve_targets(ctx, spec, bias="enemy" if amount < 0 else "none"):
        if spec.get("amount_if_empowered") and unit.empowered:
            # "If it's EMPOWERED, give it +4 [might] this turn instead" (Guttural Roar)
            unit.temporary_might += int(spec["amount_if_empowered"])
            continue
        if amount < 0 and ctx.loop._gangplank_redirect(unit, spec):
            continue
        if amount < 0:
            ctx.loop._fire_might_reduced(unit, ctx.actor_side)
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
    if not str(spec.get("target", "")).startswith("all"):
        amount += ctx.loop._extra_might_reduction(ctx.actor_side)     # Mel Newly Awakened
    floor = int(spec.get("min_floor", spec.get("minimum", 0)))
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        base = unit.might
        reduction = min(amount, max(0, base - floor))
        unit.temporary_might -= reduction


@effect("double_might")
def _double_might(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    this_combat = str(spec.get("duration", "")).lower() == "this_combat"
    for unit in _resolve_targets(ctx, spec):
        if this_combat:
            unit.combat_might += unit.might   # Fiora Peerless: "double my Might this combat"
        else:
            unit.temporary_might += unit.might  # this-turn doubling


@effect("exhaust_unit")
def _exhaust_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        ctx.loop._exhaust(unit)


@effect("ready_unit")
def _ready_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")},
                                 prefer=lambda u: u.ready or not ctx.loop._can_ready(u)):
        if spec.get("cant_move"):
            unit.cant_move_turn = ctx.loop.gs.turn     # "It can't move this turn" (Hunker Down)
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


def _counterable(card, spec: Mapping[str, Any]) -> bool:
    """A spell `counter_spell` may counter: its printed cost within the limits
    the card prints ("no more than [4] and no more than [rune]": Defy), any
    spell otherwise."""
    power = card.cost_power or 0
    return (card.cost_energy or 0) <= int(spec.get("max_energy", 99)) \
        and int(spec.get("min_power", 0)) <= power <= int(spec.get("max_power", 99))


def _chose_mine(ctx: "EffectContext", item, only_one: bool = False) -> bool:
    """ "Counter an enemy spell or ability that chooses a friendly unit or
    gear" (Not So Fast): an opponent's spell whose declared choices include one
    of our units or gear."""
    if item.player == ctx.actor_side:
        return False
    mine_units = {id(u) for u in _units_at(ctx, ctx.actor_side, "anywhere")}
    mine_gear = {id(getattr(g, "card", g)) for s_, _h, g in _gear_entries(ctx, False) if s_ == ctx.actor_side}
    hits = set()
    for _kind_, _n, got in (item.declared or {}).values():
        for x in (got if isinstance(got, list) else [got]):
            x = x[-1] if isinstance(x, tuple) and x else x
            if id(x) in mine_units or id(getattr(x, "card", x)) in mine_gear:
                hits.add(id(x))
    # Repulse: "that chooses it and no other friendly unit" (only_one).
    return len(hits) == 1 if only_one else bool(hits)


@effect("counter_spell")
def _counter_spell(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    chain = ctx.loop.gs.chain
    if not chain or not _counterable(chain[-1].card, spec) or ctx.loop._uncounterable(chain[-1].player) \
            or ctx.loop._has_effect(chain[-1].card, "cant_be_countered"):
        return
    target_item = chain[-1]
    if spec.get("enemy_choosing_mine") and not _chose_mine(ctx, target_item, bool(spec.get("only_one"))):
        return
    ctx.extra["countered_energy"] = int(target_item.card.cost_energy or 0)   # Riposte
    target_card = target_item.card
    owner = ctx.loop.gs.get_player(target_item.owner or target_item.player)
    controller = ctx.loop.gs.get_player(target_item.player)
    tax = int(spec.get("unless_pays", 0) or 0)
    if tax and controller.energy >= tax:
        controller.energy -= tax     # "unless its controller pays [2]": they do
        return
    chain.pop()
    if spec.get("silence"):
        ctx.loop.gs.cant_play_spells_turn[target_item.player] = ctx.loop.gs.turn
    if spec.get("return_to_hand"):
        owner.hand.append(target_card)
    else:
        ctx.loop._spell_to_trash(owner, target_card)


@effect("grant_temporary_might_per_enemy")
def _grant_temporary_might_per_enemy(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Give a friendly unit at a battlefield +2 [might] this turn for each
    enemy unit there" (Against the Odds): the unit is chosen (baseline: where
    the most enemies are)."""
    base_amount = int(spec.get("amount", 0))
    loop = ctx.loop
    mine = [u for bf in loop.gs.battlefields for u in bf._units_for(ctx.actor_side)]
    if not mine:
        return

    def enemies(u):
        bf = loop._locate_unit(u)[1]
        return len(bf._units_for(ctx.opponent_side)) if bf is not None else 0
    unit = loop.choose(_kind("target", spec), ctx.actor_side, mine, max(mine, key=enemies), ctx.card)
    loop._note_chosen(ctx.card, ctx.actor_side, [unit])
    unit.temporary_might += base_amount * enemies(unit)


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
    instead = int(spec.get("if_buffed_might", 0) or 0)
    for unit in _resolve_targets(ctx, spec, prefer=lambda u: not instead and u.might_counters >= 1):
        if instead and unit.might_counters >= 1:
            # "If it's already buffed, give it +2 [might] this turn instead" (Iridescent Avian)
            unit.temporary_might += instead
            continue
        # BUFF is non-stacking (max 1 per unit), but "I can have any number of
        # buffs" (Lee Sin Ascetic).
        if unit.might_counters < 1 or ctx.loop._has_effect(unit.card, "unlimited_buffs"):
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
        for _ in range(min(count, unit.might_counters)):
            ctx.loop._spend_buff(unit, ctx.actor_side)


@effect("stun_unit")
def _stun_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    stunned_at = []
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "opponent")}, bias="enemy"):
        if ctx.loop._gangplank_redirect(unit, spec):
            continue
        unit.stunned = True
        where = ctx.loop._locate_unit(unit)
        if where is not None and where[0] == ctx.opponent_side:
            stunned_at.append(where[1])
    if stunned_at:
        ctx.extra["stunned_at"] = stunned_at[0]   # "to that enemy unit's battlefield" (Zenith Blade)
        ctx.loop._fire_stun_enemy(ctx.actor_side, stunned_at[0])


@effect("recycle_card")
def _recycle_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    from .cards import RuneCard
    if spec.get("source") == "trash" or spec.get("target") == "self_card":
        _recycle_from_trash(ctx, spec)
        return
    target = str(spec.get("target", "actor"))
    player = ctx._player_for_target(target)
    if player.hand:
        card = player.hand.pop(0)
        # Route card to correct deck by type (Rule 403: RECYCLE)
        if isinstance(card, RuneCard):
            player.rune_deck.cards.append(card)  # Bottom of rune deck
        else:
            player.deck.cards.append(card)  # Bottom of main deck (Units, Spells, Gear)


def _recycle_from_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Recycle 3 from your trash" (Dr. Mundo Expert): `amount` cards of your
    trash to the bottom of your Main Deck, your pick (baseline: the cheapest);
    `target: self_card`: "Recycle me" (Ekko Recurrent's DEATHKNELL)."""
    me = ctx.actor
    if spec.get("target") == "self_card":
        picks = [ctx.card] if any(c is ctx.card for c in me.trash) else []
    else:
        n = min(int(spec.get("amount", spec.get("count", 1))), len(me.trash))
        cheapest = sorted(me.trash, key=_zone_value)[:n]
        picks = ctx.loop.choose_many("recycle:" + str(spec.get("effect")), ctx.actor_side,
                                     list(me.trash), cheapest, ctx.card)
    for card in picks:
        me.trash.remove(card)
        me.deck.cards.insert(0, card)
    if picks:
        ctx.loop._note_recycled(ctx.actor_side)


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
    if "subtype_any" in tf and not set(tf["subtype_any"]) & set(getattr(card, "tags", None) or []):
        return False                    # "a Bird, Cat, Dog, or Poro" (Starhound)
    if tf.get("not_spell") and cat == "SPELL":
        return False                    # "a unit, gear ... with Energy cost [7]" (Nasus Curator)
    if "might_at_least" in tf and int(getattr(card, "might", 0) or 0) < int(tf["might_at_least"]):
        return False                    # "If it's MIGHTY" (Raving Witness)
    return True


def _fury_threatened(ctx: "EffectContext", unit) -> bool:
    """ "a friendly unit that's in combat with an enemy Fury unit or that's being
    chosen by an enemy Fury spell" (Decree of Focus)."""
    loop = ctx.loop

    def fury(card):
        return getattr(getattr(card, "domain", None), "name", "") == "FURY"
    where = loop._locate_unit(unit)
    if where is not None and where[1] is not None and loop._in_combat(unit) and any(
            fury(e.card) for e in where[1]._units_for(loop.gs.other(where[0]))):
        return True
    for item in loop.gs.chain:
        if item.player != ctx.actor_side and fury(item.card):
            for _k, _n, got in (item.declared or {}).values():
                for x in (got if isinstance(got, list) else [got]):
                    if (x[-1] if isinstance(x, tuple) and x else x) is unit:
                        return True
    return False


def _passes_filter(unit, tf: Mapping[str, Any], ctx: "EffectContext") -> bool:
    """Apply a target_filter dict to a single unit (Round 4 Tier 1)."""
    if not tf:
        return True
    card = unit.card
    if tf.get("exclude_self") and card is ctx.card:
        return False
    # The unit's keywords now (granted ones too: Shen's TANK for Kinkou Temple).
    has = unit.has_keyword if hasattr(unit, "has_keyword") else card.has_keyword
    if "has_keyword" in tf and not has(str(tf["has_keyword"])):
        return False
    if "lacks_keyword" in tf and has(str(tf["lacks_keyword"])):
        return False
    cat = _card_category_name(card)
    if tf.get("is_gear") and cat != "GEAR":
        return False
    if tf.get("is_spell") and cat != "SPELL":
        return False
    if tf.get("is_unit") and cat not in ("UNIT", "CHAMPION", "LEGEND"):
        return False
    if tf.get("moved_this_turn") and not getattr(unit, "moves_this_turn", 0):
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
    if "subtype_any" in tf and not set(tf["subtype_any"]) & set(getattr(unit, "tags", None) or card.tags or []):
        return False                     # "Bird, Cat, Dog, Poro, and Ivern units here" (Brush)
    if tf.get("is_buffed") and getattr(unit, "might_counters", 0) <= 0:
        return False
    if tf.get("is_damaged") and getattr(unit, "damage", 0) <= 0:
        return False                     # "all damaged enemy units here" (Warwick Hunter)
    if tf.get("is_attacking") and not ctx.loop._is_attacking(unit):
        return False                     # "Stun an attacking unit" (Thwonk!)
    if tf.get("domain"):
        # "an enemy Calm unit" (the Decrees): the card's domain, not a tag.
        dom = getattr(card, "domain", None)
        if getattr(dom, "name", str(dom)).upper() != str(tf["domain"]).upper():
            return False
    if tf.get("is_empowered") and not unit.empowered:
        return False                     # "Your units that are EMPOWERED" (Aurok General)
    if tf.get("not_subtype") and tf["not_subtype"] in unit.tags:
        return False                     # "a non-Dragon unit" (Ocean Drake)
    if tf.get("fury_threatened") and not _fury_threatened(ctx, unit):
        return False                     # Decree of Focus
    if tf.get("has_named_tag") and getattr(ctx.card, "_named_tag", None) not in unit.tags:
        return False                     # "a unit with the named tag" (The List)
    if tf.get("not_it") and any(unit is u for u in ctx.extra.get("it") or ()):
        return False                     # "... to up to one other unit" (Piercing Light)
    if tf.get("is_exhausted") and getattr(unit, "ready", True):
        return False
    if tf.get("is_ready") and not getattr(unit, "ready", True):
        return False
    if tf.get("is_mighty") and unit.might < 5:
        return False
    if "might_at_most" in tf and unit.might > int(tf["might_at_most"]):
        return False
    if tf.get("at_battlefield"):
        where = ctx.loop._locate_unit(unit)
        if where is None or where[1] is None:
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
# Every unit at the effect's battlefield, both players' ("Deal 1 to each unit
# here": Frozen Fortress; "all units at my battlefield": Kog'Maw Caustic).
_BOTH_SIDES_TARGETS = {"battlefield", "both", "both_players", "everyone", "all_units",
                       "all_units_here"}
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


def _resolve_targets(ctx: "EffectContext", spec: Mapping[str, Any], *, bias: str = "none",
                     prefer=None) -> list:
    """Return the list of units an effect should hit, honoring target + scope + target_filter.

    `bias` ("enemy" | "friendly" | "none") only affects a chooser target ("a unit"):
    it decides which side the deterministic baseline picks first for a single target.
    `prefer`: a sort key for a single pick within that side, lowest first (ready
    an exhausted unit, not one already ready).
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
    if target == "friendly_units_with_it":
        # "If you have exactly two units there, they each get +1 [might]"
        # (Shadow Dash): your units where the unit the previous effect chose
        # is; `only_if_count`: none unless there are exactly that many.
        where = next((w for w in map(ctx.loop._locate_unit, ctx.extra.get("it", [])) if w), None)
        if where is None:
            return []
        units = list(ctx.loop.gs.get_player(ctx.actor_side).base_units) if where[1] is None             else list(where[1]._units_for(ctx.actor_side))
        n = spec.get("only_if_count")
        return [] if n is not None and len(units) != int(n) else units
    if target == "it":
        # "Ready a unit and give it ASSAULT 3": the unit(s) the card's previous
        # effect chose, if still on the board.
        on_board = {id(u) for bf in ctx.loop.gs.battlefields for u in bf.units_A + bf.units_B}
        on_board |= {id(u) for p in (ctx.loop.gs.A, ctx.loop.gs.B) for u in p.base_units}
        return [u for u in ctx.extra.get("it", []) if id(u) in on_board]
    # Where "a unit" may be: `where` "anywhere" (the text names no place:
    # base or any battlefield), "battlefield" (any battlefield) or "base";
    # without it, the units here (a spell's battlefield, the source's).
    where = str(spec.get("where", "")).lower()
    if target in _EVERYWHERE_TARGETS:
        # "Give friendly units +5" / "Deal 3 to all units in bases": not only here.
        who, where = _EVERYWHERE_TARGETS[target]
        sides = {"friendly": [ctx.actor_side], "enemy": [ctx.opponent_side],
                 "both": [ctx.actor_side, ctx.opponent_side]}[who]
        units = [u for s in sides for u in _units_at(ctx, s, where)]
    elif target in _BOTH_SIDES_TARGETS:
        units = list(ctx.battlefield.units_A) + list(ctx.battlefield.units_B)
    elif target in _CHOOSER_TARGETS:
        friendly = _units_where(ctx, ctx.actor_side, where)
        enemy = _units_where(ctx, ctx.opponent_side, where)
        units = enemy + friendly if bias == "enemy" else friendly + enemy
    elif where:
        units = _units_where(ctx, ctx._side_for_player(ctx._player_for_target(target)), where)
    else:
        units = ctx._units_for_target(target)
    hidden = getattr(ctx.card, "_hidden_bf", None)
    if hidden is not None and where != "base" and not target.startswith("all") \
            and target not in _BOTH_SIDES_TARGETS and target not in _EVERYWHERE_TARGETS:
        # Played from facedown: chosen among what is at its battlefield (§811.1.d).
        at = ctx.loop.gs.battlefields[hidden]
        units = [u for u in units if any(u is x for x in at.units_A + at.units_B)]
    tf = spec.get("target_filter")
    if tf:
        units = [u for u in units if _passes_filter(u, tf, ctx)]
    if not units and scope == "single" and not target.startswith("all") and not where \
            and hidden is None and not isinstance(ctx.card, SpellCard) \
            and target not in _BOTH_SIDES_TARGETS:
        # An ability or trigger isn't aimed at one battlefield the way a spell is
        # (a legend's "give a unit ASSAULT 2"): with no candidate here, look at
        # the other battlefields, then base.
        units = _fallback_units(ctx, target, bias)
        if tf:
            units = [u for u in units if _passes_filter(u, tf, ctx)]
    if not units:
        if scope == "single":
            ctx.extra["it"] = []
        return []
    if scope != "single" or target.startswith("all"):
        return list(units)
    # Units picked one by one ("a unit", "up to two units" = count): that's a
    # choice, for "when you choose me" and "you've chosen enemy units twice".
    # Baseline: list order (the bias side first), `prefer` within that side.
    units = _choosable(ctx, units)
    if prefer is not None and units:
        def side(u):
            where = ctx.loop._locate_unit(u)
            return where[0] if where else None
        lead = side(units[0])
        units = sorted(units, key=lambda u: (side(u) != lead, prefer(u)))
    picked = ctx.loop.choose_many(_kind("target", spec), ctx.actor_side, units,
                                  units[:max(1, int(spec.get("count", 1) or 1))], ctx.card)
    ctx.loop._note_chosen(ctx.card, ctx.actor_side, picked)
    ctx.extra["it"] = picked
    return picked


# A spell's targets that are a choice of one unit (§355.5): "a unit", "an enemy unit".
_SINGLE_UNIT_TARGETS = _CHOOSER_TARGETS | {"enemy_unit", "friendly_unit"}


def has_valid_target(ctx: "EffectContext", spec: Mapping[str, Any]) -> Optional[bool]:
    """§355.8 for one instruction of a spell about to be played: whether the
    unit (or spell, for a counter) it chooses has a valid choice now. None: an
    instruction this check doesn't know to target anything."""
    effect = spec.get("effect")
    if effect == "counter_spell":
        chain = ctx.loop.gs.chain
        return (bool(chain) and _counterable(chain[-1].card, spec)
                and not ctx.loop._uncounterable(chain[-1].player)
                and (not spec.get("enemy_choosing_mine")
                     or _chose_mine(ctx, chain[-1], bool(spec.get("only_one")))))
    if effect == "play_token" and spec.get("location") == "enemy_occupied":
        return any(bf._units_for(ctx.opponent_side) for bf in ctx.loop.gs.battlefields)
    target = str(spec.get("target", "")).lower()
    single = str(spec.get("scope", "single")).lower() == "single"
    # A gear to choose (Detonate "Kill a gear", Factory Recall, Turn to Dust).
    if single and (effect in ("return_gear_to_hand", "give_gear_temporary") or
                   (effect == "kill_gear" and target in ("", "none", "chosen_unit", "gear", "enemy_gear",
                                                         "chosen_gear"))):
        entries = _gear_entries(ctx, enemy_first=True, units=effect == "kill_gear")
        if target == "enemy_gear":
            entries = [e for e in entries if e[0] == ctx.opponent_side]
        tf = spec.get("target_filter") or {}
        return any(_gear_matches(g, tf) for _s, _h, g in entries)
    # A card in your trash to choose (Morbid Return "Return a unit from your
    # trash"; Heedless Resurrection "Play a unit from your trash").
    if single and effect in ("return_from_trash", "play_from_trash") and target in ("", "none", "friendly_unit"):
        tf = spec.get("target_filter") or ({"is_unit": True} if target == "friendly_unit" else {})
        return any(_zone_card_matches(c, tf) for c in ctx.actor.trash)
    if str(spec.get("scope", "single")).lower() != "single" or target not in _SINGLE_UNIT_TARGETS:
        return None
    if effect in ("move_unit", "move_units_to_base"):
        return bool(_move_candidates(ctx, spec, effect == "move_units_to_base"))
    return bool(_choosable(ctx, _resolve_targets(ctx, {**spec, "scope": "all"})))


def _units_where(ctx: "EffectContext", side: str, where: str) -> list:
    """`side`'s units a target may pick: here only (no `where`), or every
    battlefield ("battlefield") and the base too ("anywhere"); here first, so
    the baseline's pick is the one it made when only here counted."""
    here = list(ctx._units_for_side(side))
    if not where:
        return here
    gs = ctx.loop.gs
    if where == "base":                    # "a friendly unit in your base" (Showstopper)
        return list(gs.get_player(side).base_units)
    if where == "it_location":
        # "STUN an enemy unit at its location" (Heroic Charge): where "it" is.
        it = next((loop_w for loop_w in map(ctx.loop._locate_unit, ctx.extra.get("it") or []) if loop_w), None)
        if it is None:
            return []
        return list(gs.get_player(side).base_units) if it[1] is None else list(it[1]._units_for(side))
    if where == "moved_bfs":
        # "a unit at a battlefield I moved to or from" (Akali Deadly Weapon)
        ends = [b for b in (ctx.extra.get("moved_from"), ctx.extra.get("moved_to"))
                if isinstance(b, Battlefield)]
        return [u for b in ends for u in b._units_for(side)]
    out = here + [u for bf in gs.battlefields if bf is not ctx.battlefield for u in bf._units_for(side)]
    if where == "anywhere":
        out += list(gs.get_player(side).base_units)
    return out


def _kind(what: str, spec: Mapping[str, Any]) -> str:
    """The name of a choice an effect makes ("target:kill_unit"), for GameLoop.choose."""
    return f"{what}:{spec.get('effect', '?')}"


def _choosable(ctx: "EffectContext", units: list) -> list:
    """The units this effect's controller may choose (GameLoop._can_choose)."""
    return [u for u in units if ctx.loop._can_choose(u, ctx.actor_side, ctx.card)]


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
        # "for each of your MIGHTY units", wherever they are (base too)
        return sum(1 for u in _friendly_units(ctx) if u.might >= 5)
    if src == "highest_might_friendly":
        units = _friendly_units(ctx)
        return max((u.might for u in units), default=0)
    if src == "cards_in_hand":
        return len(ctx.actor.hand)
    if src == "friendly_tokens":
        # "I have +1 [might] for each token unit you control" (Illaoi)
        return sum(1 for u in _friendly_units(ctx) if u.is_token)
    if src == "same_name_here_others":
        # "for each other unit you control here with my name" (Spiderling)
        u = _source_unit(ctx)
        where = ctx.loop._locate_unit(u) if u is not None else None
        if where is None:
            return 0
        here = where[1]._units_for(ctx.actor_side) if where[1] is not None else ctx.actor.base_units
        return sum(1 for x in here if x is not u and x.card.name == u.card.name)
    if src == "battlefields_controlled":
        # "draw 1 for each battlefield you or your allies control" (Right of Conquest)
        return sum(1 for bf in ctx.loop.gs.battlefields if bf.control() == ctx.actor_side)
    if src == "friendly_units":
        # "gain 1 XP for each friendly unit" (Scrutinizing Sergeant)
        return len(_friendly_units(ctx))
    if src == "friendly_temporary_here":
        # "for each of your units with TEMPORARY at my battlefield" (Petal Pixie)
        u = _source_unit(ctx)
        where = ctx.loop._locate_unit(u) if u is not None else None
        if where is None or where[1] is None:
            return 0
        return sum(1 for x in where[1]._units_for(ctx.actor_side) if x.has_keyword("TEMPORARY"))
    if src == "countered_energy":
        # "give that unit +[might] equal to that spell's energy cost" (Riposte)
        return int(ctx.extra.get("countered_energy", 0))
    if src == "killed_might":
        # "If you do, give +[might] equal to its Might" (Deathgrip)
        return int(ctx.extra.get("killed_might", 0))
    if src in ("self_assault", "self_shield"):
        # "deal damage equal to my ASSAULT" (Lucian Gunslinger), "my SHIELD"
        # (Armored Tusker)
        u = _source_unit(ctx)
        return u.keyword_value(src[len("self_"):].upper()) if u else 0
    if src == "discarded_energy":
        # "Discard 1. Deal its Energy cost as damage" (Get Excited!)
        card = ctx.extra.get("discarded")
        return int(getattr(card, "cost_energy", 0) or 0) if card is not None else 0
    if src == "it_might":
        # "Ready a friendly unit. It deals damage equal to its Might" (Last Breath)
        it = [u for u in ctx.extra.get("it") or [] if ctx.loop._locate_unit(u) is not None]
        return it[0].might if it else 0
    if src == "it_shield":
        # "Give a friendly unit SHIELD 2, then deal damage equal to its SHIELD" (Ntofo Strikes)
        it = [u for u in ctx.extra.get("it") or [] if ctx.loop._locate_unit(u) is not None]
        return it[0].keyword_value("SHIELD") if it else 0
    if src == "other_friendly_exhausted_units":
        # "+1 [might] for each other exhausted unit you control" (Seraphine Not Alone)
        me = _source_unit(ctx)
        return sum(1 for u in _friendly_units(ctx) if not u.ready and u is not me)
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
        # `tags`: only these count ("Bird, Cat, Dog, and Poro": Friendship).
        only = set(spec.get("tags") or [])
        return len({t for u in _friendly_units(ctx) for t in u.tags if not only or t in only})
    if src == "excess_damage":
        bf = ctx.extra.get("battlefield") or ctx.battlefield
        turn, n = bf.excess_damage.get(ctx.actor_side, (-1, 0))
        return n if turn == ctx.loop.gs.turn else 0
    if src == "cards_with_my_name_in_trash":
        return sum(1 for c in ctx.actor.trash if c.name == ctx.card.name and c is not ctx.card)
    if src == "battlefields_conquered_this_turn":
        return int(ctx.loop.gs.conquered_this_turn.get(ctx.actor_side, 0))
    if src == "other_battlefields_controlled":
        # "for each other battlefield you or allies control" (Seat of Power)
        here = ctx.extra.get("battlefield") or ctx.battlefield
        return sum(1 for bf in ctx.loop.gs.battlefields
                   if bf is not here and bf.control() == ctx.actor_side)
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
    if src == "chosen_friendly_gear_energy":
        # "Choose a friendly gear. Deal damage equal to its Energy cost"
        # (Improvised Projectile): the costliest one.
        loop = ctx.loop
        gear = list(ctx.actor.base_gear) + loop._controlled_attached_gear(ctx.actor_side) + [
            dg.card for bf in loop.gs.battlefields for dg in bf.gear_for(ctx.actor_side)]
        return max((int(g.cost_energy or 0) for g in gear), default=0)
    if src in ("shown_might", "shown_power_cost", "shown_energy_cost"):
        shown = getattr(ctx.card, "_shown", None) or {}
        return int(shown.get(src[len("shown_"):], 0))
    return int(spec.get("amount", 0))


@effect("kill_unit")
def _kill_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    dead_at: dict = {}   # id(bf or None for a base) -> (bf, [(unit, side)])
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "enemy_unit")}, bias="enemy"):
        # Wherever it is ("Kill a unit": a base too); the owner per unit so
        # both-sides targets route each card to the right trash.
        where = _take_off_board(ctx, unit)
        if where is not None:
            side, bf = where
            ctx.extra["it_controller"] = side      # "Its controller draws 2" (Hidden Blade)
            ctx.extra["killed_might"] = unit.might  # "give +[might] equal to its Might" (Deathgrip)
            dead_at.setdefault(id(bf), (bf, []))[1].append((unit, side))
    # They die together: replacements, DEATHKNELL, "when a friendly unit dies".
    for bf, dead in dead_at.values():
        ctx.loop._route_deaths(dead, bf or ctx.battlefield, in_base=bf is None,
                               killer=(ctx.actor_side, ctx.card))


def _take_off_board(ctx: "EffectContext", unit):
    """Remove `unit` from wherever it is, its battlefield or its base: its
    (side, battlefield or None for a base), or None if it isn't on the board."""
    where = ctx.loop._locate_unit(unit)
    if where is None:
        return None
    side, bf = where
    zone = ctx.loop.gs.get_player(side).base_units if bf is None else bf._units_for(side)
    zone.remove(unit)
    return where


def _gear_entries(ctx: "EffectContext", enemy_first: bool,
                  units: bool = False) -> list[tuple[str, object, object]]:
    """All gear in play as (owner_side, holder_or_None, gear). holder is the
    UnitInPlay wearing it, None for unattached base gear, or the Battlefield a
    DEPLOY gear sits on (gear is then its DeployedGear wrapper). `units`: unit
    gear too (Orianna Lady of Clockwork), as (side, the unit, its card)."""
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
        if units:
            entries.extend((side, u, u.card) for u in in_play if u.gear_unit)
    return entries


def _gear_matches(gear_card, tf: Mapping[str, Any]) -> bool:
    gear_card = getattr(gear_card, "card", gear_card)  # unwrap a DeployedGear
    if "energy_at_most" in tf and int(getattr(gear_card, "cost_energy", 0) or 0) > int(tf["energy_at_most"]):
        return False
    if "energy_at_least" in tf and int(getattr(gear_card, "cost_energy", 0) or 0) < int(tf["energy_at_least"]):
        return False
    if tf.get("domain"):                # "an enemy Chaos unit or gear" (Decree of Unity)
        dom = getattr(gear_card, "domain", None)
        return getattr(dom, "name", str(dom)).upper() == str(tf["domain"]).upper()
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

    entries = _gear_entries(ctx, enemy_first=True, units=True)
    entries = [(s, h, g) for (s, h, g) in entries if _gear_matches(g, tf)]
    if spec.get("_only") is not None:
        entries = [e for e in entries if getattr(e[2], "card", e[2]) is spec["_only"]]
    if spec.get("max_energy_self_might"):
        # "a gear with Energy cost no more than my Might" (Noxian Demolitionist)
        me = _source_unit(ctx)
        cap = me.might if me is not None else 0
        entries = [e for e in entries if int(getattr(getattr(e[2], "card", e[2]), "cost_energy", 0) or 0) <= cap]
    if target in ("self", "this"):
        # "Kill this" (Runeblade Anvil's ability).
        entries = [(s, h, g) for (s, h, g) in entries if getattr(g, "card", g) is ctx.card]
    elif target == "each_player":
        # "Each player kills one of their gear" (Acceptable Losses): each picks.
        picked = []
        for side in (ctx.actor_side, ctx.opponent_side):
            own = [e for e in entries if e[0] == side]
            if own:
                picked.append(ctx.loop.choose("kill_own:kill_gear", side, own,
                                              min(own, key=lambda e: _zone_value(getattr(e[2], "card", e[2]))),
                                              ctx.card))
        entries = picked
    elif single:
        if target in ("friendly_gear", "own_gear"):
            entries = [e for e in entries if e[0] == ctx.actor_side]
        elif target == "enemy_gear":
            entries = [e for e in entries if e[0] == ctx.opponent_side]
        loop = ctx.loop
        entries = [e for e in entries if loop._can_pay_generic_power(
            ctx.actor, loop._gear_deflect_tax(e[0], ctx.actor_side, e[2]))]
        entries = [loop.choose(_kind("target", spec), ctx.actor_side, entries, entries[0],
                               ctx.card)] if entries else []
        tax = loop._gear_deflect_tax(entries[0][0], ctx.actor_side, entries[0][2]) if entries else 0
        if tax and getattr(loop, "_declaring", None) is None:
            loop._pay_generic_power(ctx.actor, tax)     # DEFLECT, paid as it is chosen

    for side, holder, gear in entries:
        player = gs.get_player(side)
        ctx.extra["it_controller"] = side          # "Its controller draws 2" (Detonate)
        if isinstance(holder, Battlefield):
            ctx.loop._kill_deployed_gear(holder, side, [gear])
            continue
        if getattr(holder, "gear_unit", False) and holder.card is gear:
            # A unit gear dies as a unit (DEATHKNELL, "when a friendly unit dies").
            where = _take_off_board(ctx, holder)
            if where is not None:
                ctx.loop._route_deaths([(holder, side)], where[1] or ctx.battlefield,
                                       in_base=where[1] is None, killer=(ctx.actor_side, ctx.card))
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


@effect("clockwork_animate")
def _clockwork_animate(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "At the start of your Main Phase, you may pay [1] to choose a friendly
    gear. It becomes a unit gear with Might equal to its Energy cost until you
    choose another gear with me" (Orianna Lady of Clockwork). The unit gear
    chosen before becomes a gear again. Baseline: pay when a gear would make a
    bigger unit than the one there is, and choose the costliest."""
    loop = ctx.loop
    side = ctx.actor_side
    entries = [e for e in _gear_entries(ctx, enemy_first=False) if e[0] == side]
    if not entries or not loop._can_pay_energy_and_generic(ctx.actor, 1, 0, None):
        return
    current = loop._gear_units(side)

    def energy(e):
        return int(getattr(getattr(e[2], "card", e[2]), "cost_energy", 0) or 0)
    best = max(entries, key=energy)
    have = max((int(u.card.cost_energy or 0) for u in current), default=0)
    if not loop.choose("optional:clockwork_animate", side, [True, False], energy(best) > have, ctx.card):
        return
    loop._pay_energy_and_generic(ctx.actor, 1, 0)
    _side, holder, gear = loop.choose(_kind("target", spec), side, entries, best, ctx.card)
    for unit in current:
        loop._unit_to_gear(unit)
    loop._gear_to_unit(side, holder, gear)


@effect("green_father_brush")
def _green_father_brush(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When you conquer or hold, you may exhaust me to replace that
    battlefield with a Brush battlefield token" (Ivern Green Father). Baseline:
    when the Brush gives a friendly unit there +1 [might]; never a Brush with a
    Brush."""
    loop, bf, side = ctx.loop, ctx.battlefield, ctx.actor_side
    legend = loop._find_unit_by_card(ctx.card)       # Ivern, maybe one Neeko added
    if bf is None or legend is None or not legend.ready:
        return
    if bf.card is not None and bf.card.name == "Brush":
        return
    if not loop.choose("optional:green_father_brush", side, [True, False],
                       loop._brush_helps(bf, side), ctx.card):
        return
    loop._exhaust(legend)
    loop._replace_battlefield(bf, "Brush")


@effect("brush_swap_back")
def _brush_swap_back(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "When you score here, you may replace this with the battlefield it
    replaced" (Brush). Baseline: when the Brush helps no friendly unit here."""
    loop, bf, side = ctx.loop, ctx.battlefield, ctx.actor_side
    if bf is None or bf.replaced is None or bf.card is not ctx.card:
        return
    if loop.choose("optional:brush_swap_back", side, [True, False],
                   not loop._brush_helps(bf, side), ctx.card):
        loop._swap_back_battlefield(bf)


@effect("heal_unit")
def _heal_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")},
                                 prefer=lambda u: u.damage == 0):
        unit.damage = 0


@effect("recall_unit")
def _recall_unit(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Return units to their owner's hand. Every recall_unit card reads
    'return ... to its owner's hand': the card leaves play (tokens cease to
    exist) and attached gear is recovered to the owner's base. "Return a
    unit" (Rebuke, Gust): an enemy first. `to: deck_bottom`: recycled instead
    ("recycle me": Elnuk Herd). `then_play_smaller`: "You may play a unit with
    less Might than that unit had, ignoring its cost" (Transpositionist)."""
    gs = ctx.loop.gs
    for unit in _resolve_targets(ctx, {**spec, "target": spec.get("target", "actor")}, bias="enemy"):
        if ctx.loop._gangplank_redirect(unit, spec):
            continue
        had = unit.might
        where = _take_off_board(ctx, unit)          # a base or any battlefield
        if where is None:
            continue
        if spec.get("then_play_smaller"):
            ctx.extra["recalled_might"] = had
        side, bf = where
        owner = gs.get_player(side)
        owner.base_gear.extend(unit.gear)
        unit.gear = []
        if not getattr(unit, "is_token", False):
            owner_of = gs.get_player(ctx.loop._owner_of(unit.card, side))
            if spec.get("to") == "deck_bottom":
                owner_of.deck.cards.insert(0, unit.card)
            else:
                owner_of.hand.append(unit.card)
            unit.card._owner = None
        # Recall/bounce is a board exit → leaves_board fires (KNOWN_ISSUES #9).
        ctx.loop._fire_leaves_board(unit.card, side, bf or ctx.battlefield)
    if spec.get("then_play_smaller") and "recalled_might" in ctx.extra:
        had = ctx.extra.pop("recalled_might")
        options = [c for c in ctx.actor.hand if _card_category_name(c) in ("UNIT", "CHAMPION")
                   and int(getattr(c, "might", 0) or 0) < had]
        if options and ctx.loop.choose("optional:play_smaller", ctx.actor_side, [True, False], True, ctx.card):
            card = ctx.loop.choose(_kind("card", spec), ctx.actor_side, options,
                                   max(options, key=_zone_value), ctx.card)
            ctx.actor.hand.remove(card)
            ctx.loop._play_unit(card, ctx.actor_side, from_zone="hand")


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
    if not theirs and bf.control() != side:
        return 2
    if bf.control() == side:
        return 1
    return 0


def _move_candidates(ctx: "EffectContext", spec: Mapping[str, Any], to_base_verb: bool) -> list:
    """The (side, unit) pairs a move effect may move: the ones its target names
    that can be chosen and can go somewhere (a chosen unit moves: the move is
    the card's, not a "may", so a pick never falls through to another unit)."""
    loop = ctx.loop
    me, them = ctx.actor_side, ctx.opponent_side
    target = str(spec.get("target", "friendly_unit")).lower()
    if target in ("self", "this", "me"):
        src = _source_unit(ctx)
        candidates = [(me, src)] if src is not None else []
    elif target == "it":
        # "Buff a friendly unit in your base, then move it" (Showstopper).
        candidates = [(w[0], u) for u in ctx.extra.get("it", [])
                      for w in [loop._locate_unit(u)] if w is not None]
    else:
        enemy = any(k in target for k in ("enemy", "opponent"))
        friendly = any(k in target for k in ("friendly", "ally", "actor"))
        default_from = "here" if (to_base_verb or target.endswith("_here")) else "anywhere"
        frm = str(spec.get("from", default_from)).lower()
        sides = [them] if enemy else [me] if friendly else [them, me]
        candidates = [(s, u) for s in sides for u in _units_at(ctx, s, frm)]
    tf = spec.get("target_filter")
    if tf:
        candidates = [(s, u) for s, u in candidates if _passes_filter(u, tf, ctx)]
    candidates = [(s, u) for s, u in candidates if not (u.unmovable_by_enemies and s != me)]
    if not target.startswith("all"):
        chooser = them if str(spec.get("mover", "")) == "opponent" else me
        candidates = [(s, u) for s, u in candidates if loop._can_choose(u, chooser, ctx.card)]
    return [(s, u) for s, u in candidates if _move_destinations(ctx, spec, to_base_verb, s, u)]


def _move_dest_kind(ctx: "EffectContext", spec: Mapping[str, Any], to_base_verb: bool, side: str) -> str:
    # Per unit: the chosen unit's side decides (it went by the first
    # candidate's, so a friendly unit picked after an enemy was "moved" to
    # the base it was in, and the enemy moved instead).
    dest = spec.get("destination")
    if dest is None:
        dest = "base" if to_base_verb or side == ctx.opponent_side else "battlefield"
    return str(dest).lower()


def _move_destinations(ctx: "EffectContext", spec: Mapping[str, Any], to_base_verb: bool,
                       side: str, unit) -> list:
    """Where `unit` may go: a list of battlefields, None standing for base."""
    gs = ctx.loop.gs
    dest = _move_dest_kind(ctx, spec, to_base_verb, side)
    where = ctx.loop._locate_unit(unit)
    cur = where[1] if where else None
    if dest == "base":
        return [None] if cur is not None else []
    if dest in ("here", "this_battlefield"):
        return [ctx.battlefield] if ctx.battlefield in gs.battlefields and cur is not ctx.battlefield else []
    if dest == "same_as_last_move":
        # "They move a unit they control to the same battlefield" (Call to Battle)
        at = ctx.extra.get("last_move_dst")
        return [at] if at is not None and cur is not at else []
    if dest in ("stunned_at", "deployed_at", "defended_at"):
        # "you may move me to that battlefield" (Vex Mocking, Jarvan IV Exemplar),
        # "When you defend at a battlefield, you may move me there" (Loyal Pup)
        at = ctx.extra.get(dest)
        return [at] if at is not None and cur is not at else []
    if dest == "to_or_from_base" and cur is not None:
        return [None]
    others = [bf for bf in gs.battlefields if bf is not cur]
    if dest == "any":
        # "Move a unit" naming no place: any location other than its own, its
        # base included (§355.4.a).
        return ([None] if cur is not None else []) + others
    if dest == "friendly_occupied":
        # "to a battlefield where you have units" (Shadow Dash)
        return [bf for bf in others if bf._units_for(ctx.actor_side)]
    if dest == "controlled_battlefield":
        # "to a battlefield you control" (Call to Battle)
        return [bf for bf in others if bf.control() == ctx.actor_side]
    if dest == "enemy_occupied":
        # "to an occupied enemy battlefield" (Cataclysm)
        return [bf for bf in others if bf._units_for(ctx.opponent_side)]
    if dest == "open":
        # "to an open battlefield": unoccupied and uncontrolled (§170.11.c); the
        # units one effect moves go to the same one.
        last = ctx.extra.get("last_move_dst")
        if last is not None and str(spec.get("scope", "")).lower() == "all":
            return [last] if cur is not last else []
        return [bf for bf in others if not bf.units_A and not bf.units_B and bf.controller() is None]
    return others


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
    candidates = _move_candidates(ctx, spec, to_base_verb)
    if not candidates:
        ctx.extra["it"] = []
        return

    def dest_kind(side):
        return _move_dest_kind(ctx, spec, to_base_verb, side)

    def destinations(side, unit):
        return _move_destinations(ctx, spec, to_base_verb, side, unit)

    def destination_for(side, unit):
        options = destinations(side, unit)
        if len(options) == 1:
            return options[0]
        fields = [bf for bf in options if bf is not None]
        if side == them and None in options or not fields:
            best = None                    # an enemy goes back to its base
        elif side == me:
            best = max(fields, key=lambda bf: _attack_value(ctx, side, unit, bf))
        else:
            # An enemy is moved where it fights worst for them.
            best = min(fields, key=lambda bf: _attack_value(ctx, side, unit, bf))
        return loop.choose(_kind("destination", spec), me, options, best, ctx.card)

    def priority(item):
        side, unit = item
        dest = dest_kind(side)
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

    order = sorted(candidates, key=priority, reverse=True)
    # Who moves (and chooses): the effect's controller, or "Choose an opponent.
    # They must move a unit they control" (Angler Wyrm: `mover` opponent).
    mover = them if str(spec.get("mover", "")) == "opponent" else me
    if not scope_all:
        # Which unit(s): the baseline's priority order, one choice per unit.
        order = loop.choose_many(_kind("target", spec), mover, order, order[:count], ctx.card)
    moved_units, taxed = [], []
    for side, unit in order:
        dst = destination_for(side, unit)
        # Gravity Field: the one instructed to move pays, once per battlefield.
        if dst is not None and not any(dst is t for t in taxed):
            if not loop._pay_move_tax(mover, dst):
                continue
            taxed.append(dst)
        src_where = loop._locate_unit(unit)
        if src_where is not None and src_where[1] is not None:
            ctx.extra["last_move_src"] = src_where[1]       # Isolate
        if loop._move_unit_by_effect(unit, dst):
            if spec.get("ready") and loop._can_ready(unit):
                unit.ready = True
            moved_units.append(unit)
            ctx.extra["last_move_dst"] = dst
            if side != mover:
                # "When you move an enemy unit, you may exhaust this to STUN it" (Blast Cone)
                loop._fire_units_trigger("on_you_move_enemy", mover, triggering_card=unit.card,
                                         extra={"triggering_unit": unit})
    ctx.extra["it"] = moved_units          # "Move a friendly unit and ready it"


@effect("give_keyword")
def _give_keyword(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    keyword = str(spec.get("keyword", "")).strip()
    if not keyword:
        return
    duration = str(spec.get("duration", "")).lower()
    for unit in _resolve_targets(ctx, spec):
        (unit.combat_keywords if duration == "this_combat" else
         unit.turn_keywords if duration == "this_turn" else unit.granted_keywords).append(keyword)


def _give_temp_keyword(ctx: "EffectContext", spec: Mapping[str, Any], kw: str) -> None:
    amount = int(spec.get("amount", 1))
    token = f"{kw} {amount}"
    this_combat = str(spec.get("duration", "")).lower() == "this_combat"
    for unit in _resolve_targets(ctx, spec):
        if spec.get("amount_source") == "target_might":
            token = f"{kw} {unit.might}"     # "ASSAULT equal to its Might" (Brawl)
        # "this turn", or "this combat" (Fortified Position)
        (unit.combat_keywords if this_combat else unit.turn_keywords).append(token)


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
        loop = ctx.loop
        bfs = [bf for bf in gs.battlefields if len(bf.units_A) + len(bf.units_B) >= 2]
        here = loop.choose(_kind("battlefield", spec), side, bfs, loop._locate_unit(u_f)[1], ctx.card)
        there = list(here.units_A) + list(here.units_B)
        if not any(u is u_f for u in there):
            u_f, u_e = there[0], there[1]
        u_f = loop.choose(_kind("target", spec), side, there, u_f, ctx.card)
        others = [u for u in there if u is not u_f]
        u_e = loop.choose(_kind("target", spec) + ":other", side, others,
                          u_e if any(u is u_e for u in others) else others[0], ctx.card)
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
    # `with_name`: only units with that name, tokens too (Zed Without a Sound:
    # "Move me and a Shadow Clone you control to each other's locations").
    named = spec.get("with_name")

    def eligible(u):
        return u is not me and (u.card.name == named if named else not u.is_token)
    candidates = []
    for i, bf in enumerate(gs.battlefields):
        lst = bf.units_A if side == "A" else bf.units_B
        for u in lst:
            if eligible(u) and ("bf", i) != my_loc:
                candidates.append(u)
    for u in ctx.actor.base_units:
        if eligible(u) and my_loc != "base":
            candidates.append(u)
    if not candidates:
        return
    target = ctx.loop.choose(_kind("target", spec), ctx.actor_side, candidates,
                             max(candidates, key=lambda u: u.might), ctx.card)
    tgt_loc, tgt_list = locate(target)
    if named:
        # Real moves: their move triggers fire, a battlefield entered is contested.
        def bf_of(loc):
            return None if loc == "base" else gs.battlefields[loc[1]]
        loop._move_unit_by_effect(me, bf_of(tgt_loc))
        loop._move_unit_by_effect(target, bf_of(my_loc))
        return

    def place(unit, loc):
        if loc == "base":
            ctx.actor.base_units.append(unit)
        else:
            gs.battlefields[loc[1]].add_unit(side, unit)

    if spec.get("take_equipment") and target.gear and loop.choose(
            "optional:take_equipment", side, [True, False], True, ctx.card):
        # "If it's equipped, you may attach one of its Equipment to me" (Azir Ascendant)
        gear = loop.choose("equip", side, list(target.gear), target.gear[0], ctx.card)
        target.gear.remove(gear)
        me.gear.append(gear)
        loop._fire_attached(me, side)
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
    # `scope: all`: "from trashes to their owners' hands" (Shadows of the Past);
    # baseline: your own cards.
    owners = [player, ctx.opponent] if spec.get("scope") == "all" else [player]
    cands = [c for p in owners
             for c in sorted((c for c in p.trash if _zone_effect_card_ok(c, spec)),
                             key=_zone_value, reverse=True)]
    picks = ctx.loop.choose_many(_kind("card", spec), ctx._side_for_player(player), cands,
                                 cands[:count], ctx.card)
    for card in picks:
        owner = next(p for p in owners if card in p.trash)
        owner.trash.remove(card)
        owner.hand.append(card)


@effect("discard_card")
def _discard_card(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    target = str(spec.get("target", "actor"))
    player = ctx._player_for_target(target)
    # `all`: "discards their hand" (Invert Timelines).
    count = len(player.hand) if spec.get("all") else int(spec.get("count", spec.get("amount", 1)))
    side = "A" if player is ctx.loop.gs.A else "B"
    # The discarding player picks the card (baseline: the first one); with
    # `chosen_by: controller`, "They reveal their hand. Choose a card from it,
    # and they discard that card" (Mindsplitter): the effect's controller,
    # baseline the costliest.
    picker = ctx.actor_side if spec.get("chosen_by") == "controller" else side
    with ctx.loop._discard_event():
        for _ in range(count):
            if not player.hand:
                break
            default = max(player.hand, key=_zone_value) if picker != side else player.hand[0]
            card = ctx.loop.choose("discard", picker, list(player.hand), default, ctx.card)
            ctx.loop._discard(player, card)
            ctx.extra["discarded"] = card          # "Deal its Energy cost" (Get Excited!)


@effect("play_token")
def _play_token(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Play `count` tokens (GameLoop._play_token). `location`: "base" (default),
    "here" (this battlefield; base if the source is in base), "moved_from"
    (where the moving unit left, Lillia: "play a Sprite there"), "choose" (the
    text names no place: base or a battlefield its player controls) or
    "enemy_occupied" (a chosen battlefield with enemy units). `might`
    overrides the token's Might ("a 2 [might] Sand Soldier"); `count_if_it_
    friendly`: "If it was a friendly unit, play two" (Blood Money). The units
    played are "it" for the next instruction (Guards!: "ready it")."""
    if spec.get("count_if_it_friendly") and ctx.extra.get("it_controller") == ctx.actor_side:
        spec = {**spec, "count": spec["count_if_it_friendly"]}
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
    if spec.get("target") == "it_controller":
        # "Kill a gear. Its controller plays a Gold" (An Offer You Can't Refuse)
        side = ctx.extra.get("it_controller")
        if side is None:
            return
        player = ctx.loop.gs.get_player(side)
    token_spec = CARD_REGISTRY.get(token_name)
    if token_spec is not None and "DEPLOY" in token_spec.keywords:
        # Gear token with DEPLOY (§830): all `count` go to a single battlefield.
        side = ctx._side_for_player(player)
        bf = _deploy_destination(ctx, spec, side)
        for _ in range(count):
            # A real gear card (the registry spec has no state: a "return all"
            # put it in a hand).
            card = token_spec.instantiate()
            card.is_token = True
            ctx.loop._deploy_gear(side, bf, card, is_token=True)
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
    elif location == "choose":
        # The text says no place: a played unit goes to its player's base or a
        # battlefield they control (§440.2.c, §355.2), their choice when the
        # token is played. Baseline: base.
        options = [None] + [b for b in ctx.loop.gs.battlefields if b.control() == side]
        bf = ctx.loop.choose("token_location", side, options, None, ctx.card) if len(options) > 1 else None
    elif location == "enemy_occupied":
        # "Choose an occupied enemy battlefield. Play three ... there" (Rally for
        # War): a target; the baseline takes the one with the fewest enemies.
        options = [b for b in ctx.loop.gs.battlefields if b._units_for(ctx.opponent_side)]
        if not options:
            return
        bf = ctx.loop.choose(_kind("target", spec), side, options,
                             min(options, key=lambda b: len(b._units_for(ctx.opponent_side))), ctx.card)
    played = [ctx.loop._play_token(token_name, side, bf=bf, ready=ready, might=spec.get("might"))
              for _ in range(count)]
    ctx.extra["it"] = [u for u in played if isinstance(u, UnitInPlay)]


def _deploy_destination(ctx: "EffectContext", spec: Mapping[str, Any], side: str) -> Battlefield:
    """Battlefield a DEPLOY gear goes to. `battlefield: "here"` keeps the effect's
    own battlefield; otherwise (baseline policy) the one with the most enemy units,
    where a Bomb will hit hardest when the opponent holds it."""
    if str(spec.get("battlefield", "")).lower() == "here":
        return ctx.battlefield
    bfs = ctx.loop.gs.battlefields
    enemy = "B" if side == "A" else "A"
    return ctx.loop.choose("deploy", side, list(bfs),
                           max(bfs, key=lambda b: (b.count(enemy), -bfs.index(b))), ctx.card)


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
    src = ctx.loop.choose(_kind("battlefield", spec) + ":from", side, sources, src, ctx.card)
    dests = [b for b in bfs if b is not src]
    if not dests:
        return
    dst = ctx.loop.choose(_kind("battlefield", spec), side, dests,
                          max(dests, key=lambda b: b.count(side)), ctx.card)
    gear = src.gear_for(side)
    dg = ctx.loop.choose(_kind("card", spec), side, list(gear), gear[0], ctx.card)
    gear.remove(dg)
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
            if isinstance(card, UnitCard) and mine:
                unit = ctx.loop.choose(_kind("target", spec), ctx.actor_side, mine,
                                       max(at_bf or mine, key=lambda u: u.might), ctx.card)
                unit.temporary_might += int(card.might or 0)


@effect("banish_hand_and_trash")
def _banish_hand_and_trash(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """"Banish your hand and trash" (Endless Riches)."""
    player = ctx.actor
    cards = list(player.hand) + list(player.trash)
    player.hand.clear()
    player.trash.clear()
    player.banished.extend(cards)
    if cards:
        ctx.loop._note_banished(ctx.actor_side, len(cards))


@effect("empower_self")
def _empower_self(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Vendetta EMPOWER: give the source unit the empowered status. Usually an
    activated ability (`trigger: activated`) whose cost the player pays first, but
    also usable from a trigger ("when ..., empower me"). Idempotent."""
    loop = ctx.loop
    target = str(spec.get("target", "self")).lower()
    tf = spec.get("target_filter") or {}
    if target in ("self", "this", "me"):
        me = _source_unit(ctx)
        if me is not None and me.empowered and max(me.empower_times, 1) < int(spec.get("max_times", 1)):
            me.empower_times = max(me.empower_times, 1) + 1    # once more (Kayle Justified)
            return
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
        u.empowered, u.empower_times = False, 0
        if spec.get("until_end_of_turn"):
            u.empower_flip_at_end = True             # "Empower it at end of turn"


@effect("attach_gear")
def _attach_gear(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Attach it to a unit you control" (Edge of Night): this gear, from your
    base, to a chosen unit (nothing if it is attached already: QUICK-DRAW)."""
    player = ctx.actor
    if not any(g is ctx.card for g in player.base_gear):
        return
    units = _resolve_targets(ctx, {**spec, "target": spec.get("target", "friendly_unit"),
                                   "where": spec.get("where", "anywhere"), "scope": "single"})
    if not units:
        return
    player.base_gear.remove(ctx.card)
    units[0].gear.append(ctx.card)
    ctx.loop._fire_attached(units[0], ctx.actor_side)


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
    # "gain 1 XP for each friendly unit" (Scrutinizing Sergeant): amount_source
    amount = _amount(ctx, spec) if spec.get("amount_source") else int(spec.get("amount", 1))
    side = _target_side(ctx, str(spec.get("target", "actor")))
    ctx.loop.gs.add_xp(side, amount)


@effect("scry")
@effect("predict")
def _predict(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """PREDICT X (§437): look at the top X cards of your deck, recycle any number
    of them (one choice each, top first; baseline: keep, a null action, unless
    the agent's decide_predict_recycle says otherwise), then put the rest back
    on top in any order (baseline: the mightiest drawn first). Top of deck =
    end of the cards list."""
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
    look = [c for c in look if any(c is d for d in deck.cards)]
    if not look:
        return
    agent = getattr(ctx.actor, "agent", None)
    kept, recycled = [], []
    for card in reversed(look):
        recycle = bool(agent is not None and hasattr(agent, "decide_predict_recycle")
                       and agent.decide_predict_recycle(card))
        if ctx.loop.choose("predict_recycle", ctx.actor_side, [False, True], recycle, card):
            recycled.append(card)
        else:
            kept.append(card)
    if len(kept) > 1:
        kept = ctx.loop.choose_many("predict_order", ctx.actor_side, kept,
                                    sorted(kept, key=lambda c: -int(getattr(c, "might", 0) or 0)),
                                    ctx.card)
    rest = deck.cards[:-len(look)]
    # Recycled ones to the bottom (front of the list), each below the one before.
    deck.cards[:] = list(reversed(recycled)) + rest + list(reversed(kept))
    if recycled:
        ctx.loop._note_recycled(ctx.actor_side)


@effect("dig")
@effect("reveal_and_choose")
def _reveal_and_choose(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """Look at the top N cards, you may put one matching the filter into your
    hand ("You may reveal a gear from among them and draw it"; `must`: "Put 1
    into your hand"), the rest go to the bottom (`rest`: "trash" for "Put the
    rest into your trash": Lightning Rush). Baseline: the mightiest. With
    `if_kept_tag` [tags] and `then` an effect: "Then if you revealed a Bird,
    Cat, Dog, or Poro, BUFF a friendly unit" (Ivern Nurturer)."""
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
    tf = spec.get("target_filter") or spec.get("reveal_filter")
    legacy = spec.get("filter")
    zone_spec = {"target_filter": tf if isinstance(tf, Mapping) else
                 (legacy if isinstance(legacy, Mapping) else {}),
                 "filter": legacy if isinstance(legacy, str) else None}
    keepable = [c for c in top if _zone_effect_card_ok(c, zone_spec)]
    kept = None
    if keepable and (spec.get("must") or ctx.loop.choose("optional:keep", ctx.actor_side,
                                                         [True, False], True, ctx.card)):
        best = max(keepable, key=lambda c: int(getattr(c, "might", 0) or 0))
        kept = ctx.loop.choose(_kind("keep", spec), ctx.actor_side, keepable, best, ctx.card)
        top.remove(kept)
        ctx.actor.hand.append(kept)
    if spec.get("rest") == "trash":
        ctx.actor.trash.extend(top)
    else:
        deck.cards[:0] = top  # recycle remainder to the bottom
    tags = set(spec.get("if_kept_tag") or ())
    if kept is not None and tags & set(getattr(kept, "tags", None) or ()) and spec.get("then"):
        handler = REGISTRY.get(spec["then"].get("effect"))
        if handler:
            handler(ctx, spec["then"])


@effect("recycle_from_opponent_hand")
def _recycle_from_opponent_hand(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    """ "Choose an opponent. They reveal their hand and you choose a Mind card
    from it. They recycle that card" (Decree of Strength): `domain`."""
    opp = ctx.opponent
    dom = str(spec.get("domain", "")).upper()
    if spec.get("non_unit"):
        # "Choose a non-unit card from it, and recycle that card" (Sabotage)
        cands = [c for c in opp.hand if _card_category_name(c) not in ("UNIT", "CHAMPION")]
    else:
        cands = [c for c in opp.hand if getattr(getattr(c, "domain", None), "name", "") == dom]
    if not cands:
        return
    card = ctx.loop.choose(_kind("card", spec), ctx.actor_side, cands, max(cands, key=_zone_value), ctx.card)
    opp.hand.remove(card)
    opp.deck.cards.insert(0, card)
    ctx.loop._note_recycled(ctx.opponent_side)


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
    if spec.get("energy_below_points"):
        gs = loop.gs
        pts = gs.points_A if side == "A" else gs.points_B
        picks = [c for c in picks if int(c.cost_energy or 0) < pts]
    if spec.get("cost_at_most_cost_unit"):
        # "costs no more Energy and no more Power than the killed unit": the unit
        # the card's additional cost killed (GameLoop._pay_one_additional_cost).
        victim = getattr(ctx.card, "_cost_unit", None)
        if victim is None:
            return
        picks = [c for c in picks
                 if int(c.cost_energy or 0) <= int(victim.cost_energy or 0)
                 and int(c.cost_power or 0) <= int(victim.cost_power or 0)]
    if picks:
        chosen = loop.choose_many(_kind("card", spec), side, picks, picks[:count], ctx.card)
        picks = chosen + [c for c in picks if not any(c is x for x in chosen)]
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
                loop._note_recycled(side)
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
    if spec.get("target") == "self" and isinstance(ctx.card, SpellCard):
        # "Banish this" on a spell (Time Warp): it is banished as it finishes
        # resolving, not put in the trash (GameLoop._spell_to_trash).
        ctx.card._flow_banish = True
        return
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


@effect("add_battlefield")
def _add_battlefield(ctx: "EffectContext", spec: Mapping[str, Any]) -> None:
    # "As you play me, add the Baron Pit battlefield token to the board ... If
    # you do, I enter there" (Baron Nashor) changes where he enters: applied by
    # GameLoop._play_unit (_add_battlefield_token). A no-op if dispatched.
    return


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