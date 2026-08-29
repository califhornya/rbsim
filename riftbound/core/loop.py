from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, TYPE_CHECKING, Iterable

from .state import GameState, ChainItem
from .cards import Card, GearCard, SpellCard, UnitCard, LegendCard
from .combat import UnitInPlay
from .player import Player
from .battlefield import Battlefield
from riftbound.registry.cards_registry import CARD_REGISTRY, EffectSpec
from .effects import REGISTRY as EFFECT_REGISTRY
from .effects import _amount as _effect_amount
from .effects import _passes_filter as _effect_passes_filter
from .enums import Domain
from .legion_effects import get_legion_cost_reduction
from .movement_effects import MOVEMENT_REGISTRY
from riftbound.registry.engine_vocab import (
    KNOWN_TRIGGERS,
    KNOWN_CONDITIONS,
    SAFE_FALSE_CONDITIONS,
)

# --- engine_vocab drift guard --------------------------------------------------
# These mirror the dispatch tables in this module. If you teach the engine a new
# trigger (dispatch path) or condition (_check_condition branch), update both the
# relevant set below AND engine_vocab.py — the asserts fail the import otherwise,
# which is the whole point: it keeps the parser's vocabulary honest.
_DISPATCHED_TRIGGERS: frozenset[str] = frozenset({
    "on_play", "on_cast", "on_conquer", "on_hold", "on_attack", "on_defend",
    "on_death", "leaves_board", "on_move", "on_start_of_turn", "on_end_of_turn",
    "on_friendly_unit_played", "on_friendly_unit_death", "on_play_spell",
    "on_win_combat", "passive", "activated", "cost_modifier", "death_replacement",
})
_HANDLED_CONDITIONS: frozenset[str] = frozenset({
    "you_have_n_or_more_runes", "you_have_n_or_more_units_here",
    "spell_cost_at_least", "this_is_alone", "this_is_mighty",
    "triggering_unit_is_mighty", "kicker_paid",
    "friendly_unit_died_this_turn", "you_played_n_spells_this_turn",
    "you_already_played_another_card_this_turn", "controller_has_xp_at_least",
    "card_in_trash_count_at_least", "this_is_buffed", "this_is_empowered",
    "you_control_subtype",
    "score_within_n_of_victory", "you_discarded_card_this_turn",
    "cards_burned_this_turn_at_least",
    # safe-False branch (loop.py:612-614)
    "excess_damage_at_least", "controller_has_facedown_card", "target_was_stunned",
})
assert _DISPATCHED_TRIGGERS <= KNOWN_TRIGGERS, (
    "loop.py dispatches triggers missing from engine_vocab.KNOWN_TRIGGERS: "
    f"{sorted(_DISPATCHED_TRIGGERS - KNOWN_TRIGGERS)}"
)
assert _HANDLED_CONDITIONS == (KNOWN_CONDITIONS | SAFE_FALSE_CONDITIONS), (
    "loop.py condition handling is out of sync with engine_vocab; "
    f"only in loop: {sorted(_HANDLED_CONDITIONS - (KNOWN_CONDITIONS | SAFE_FALSE_CONDITIONS))}; "
    f"only in vocab: {sorted((KNOWN_CONDITIONS | SAFE_FALSE_CONDITIONS) - _HANDLED_CONDITIONS)}"
)
# -------------------------------------------------------------------------------

if TYPE_CHECKING:
    from riftbound.data.writer import GameRecorder


@dataclass
class Result:
    winner: str  # "A" | "B" | "DRAW"
    turns: int
    units_played: int
    spells_cast: int

@dataclass
class EffectContext:
    loop: "GameLoop"
    card: Card
    actor: Player
    opponent: Player
    battlefield: Battlefield

    def _side_for_player(self, player: Player) -> str:
        return "A" if player is self.loop.gs.A else "B"

    @property
    def actor_side(self) -> str:
        return self._side_for_player(self.actor)

    @property
    def opponent_side(self) -> str:
        return self._side_for_player(self.opponent)
    
    _FRIENDLY_TARGET_ALIASES = {
        "actor", "ally", "allies", "self", "this", "friendly", "friendly_unit",
        "all_friendly_units_here", "all_units_here",
    }
    _ENEMY_TARGET_ALIASES = {
        "opponent", "enemy", "enemy_unit", "all_enemy_units_here", "chosen_enemy",
    }
    # "Player picks a unit" — unrestricted, may hit EITHER side (KNOWN_ISSUES #16).
    # Unit-targeting resolves these to a both-sides pool in effects._resolve_targets;
    # this fallback keeps non-unit direct callers (draw/recycle/etc.) from raising.
    _CHOOSER_TARGET_ALIASES = {"chosen_unit", "chosen", "any_unit", "a_unit", "unit"}

    def _player_for_target(self, target: str) -> Player:
        key = target.lower()
        if key in self._FRIENDLY_TARGET_ALIASES:
            return self.actor
        if key in self._ENEMY_TARGET_ALIASES:
            return self.opponent
        if key in self._CHOOSER_TARGET_ALIASES:
            return self.actor  # safe fallback; real pick happens in _resolve_targets
        raise ValueError(f"Unknown player target '{target}'")

    def _units_for_side(self, side: str) -> list[UnitInPlay]:
        return self.battlefield.units_A if side == "A" else self.battlefield.units_B

    def _units_for_target(self, target: str) -> list[UnitInPlay]:
        player = self._player_for_target(target)
        return self._units_for_side(self._side_for_player(player))

    def deal_damage(self, amount: int, *, target: str = "opponent") -> None:
        if amount <= 0:
            return

        before_a = list(self.battlefield.units_A)
        before_b = list(self.battlefield.units_B)

        target_key = target.lower()
        if target_key in {"actor", "ally", "self"}:
            target_side = self.actor_side
        else:
            target_side = self.opponent_side

        _, dead = self.battlefield.apply_spell_damage(target_side, amount)

        # Route spell-killed units (death replacements applied first) to trash + gear.
        owner = self.loop.gs.A if target_side == "A" else self.loop.gs.B
        for dead_unit in dead:
            if self.loop._try_replace_death(dead_unit, target_side):
                continue
            owner.trash.append(dead_unit.card)
            owner.base_gear.extend(dead_unit.gear)

        if self.loop.recorder:
            self.loop._record_spell_deaths(self.battlefield, before_a, before_b)

    def grant_might(self, amount: int, *, target: str = "actor", scope: str = "all") -> None:
        if amount == 0:
            return

        target_key = target.lower()
        if target_key in {"actor", "ally", "self"}:
            side = self.actor_side
        else:
            side = self.opponent_side

        units = self.battlefield.units_A if side == "A" else self.battlefield.units_B
        if not units:
            return

        scope_key = scope.lower()
        if scope_key == "single":
            iterable = units[:1]
        else:
            iterable = units

        for unit in iterable:
            current = int(unit.card.might or 0)
            unit.card.might = current + amount

    def draw_cards(self, count: int, *, target: str = "actor", source: str = "effect") -> None:
        if count <= 0:
            return

        player = self._player_for_target(target)
        for _ in range(count):
            card = player.draw()
            if not card:
                break
            if self.loop.recorder:
                self.loop.recorder.record_draw(
                    player.name,
                    self.loop.gs.turn,
                    card,
                    source=source,
                )

    def gain_energy(self, amount: int, *, target: str = "actor") -> None:
        if amount == 0:
            return

        player = self._player_for_target(target)
        player.energy += amount

    def ready_units(self, *, target: str = "actor", scope: str = "all") -> None:
        units = self._units_for_target(target)
        if not units:
            return

        scope_key = scope.lower()
        if scope_key == "single":
            iterable: Iterable[UnitInPlay] = units[:1]
        else:
            iterable = units

        for unit in iterable:
            unit.ready = True

    def add_rune(self, domain: object, *, target: str = "actor", ready: bool = True) -> None:
        domain_obj = self._coerce_domain(domain)
        player = self._player_for_target(target)
        player.add_rune(domain_obj, ready=ready)

    def _coerce_domain(self, value: object) -> Domain:
        if isinstance(value, Domain):
            return value
        if isinstance(value, str):
            key = value.strip().upper()
            if not key:
                raise ValueError("Domain value cannot be empty")
            try:
                return Domain[key]
            except KeyError:
                for domain in Domain:
                    if domain.value.upper() == key:
                        return domain
        raise ValueError(f"Unknown domain '{value}'")      


# Legacy action signature retained for agents:
# ("SPELL"|"UNIT"|"MOVE"|"PASS", hand_index_or_None, battlefield_index_or_src, optional_dst)
# Agents implemented before MOVE support still emit 3-tuples; the loop normalises them.
Action = Tuple[str, Optional[int], Optional[int], Optional[int]]


class GameLoop:
    """Core turn structure, extended with Might combat, rune channeling and movement."""

    def __init__(self, gs: GameState, recorder: Optional["GameRecorder"] = None, verbose: bool = False):
        self.gs = gs
        self.units_played = 0
        self.spells_cast = 0
        self.recorder = recorder
        self.verbose = verbose

        if hasattr(gs.A, "agent") and gs.A.agent:
            gs.A.agent.player.battlefields = gs.battlefields
            gs.A.agent.gs = gs
            gs.A.agent.loop = self
        if hasattr(gs.B, "agent") and gs.B.agent:
            gs.B.agent.player.battlefields = gs.battlefields
            gs.B.agent.gs = gs
            gs.B.agent.loop = self

    # ====== PHASE HELPERS ======

    def _phase_mulligan(self) -> None:
        for player in [self.gs.A, self.gs.B]:
            if player.agent is None:
                continue
            indices_to_return = player.agent.decide_mulligan()
            if not indices_to_return:
                continue
            indices_to_return.sort(reverse=True)
            returned_cards = []
            for idx in indices_to_return:
                if 0 <= idx < len(player.hand):
                    returned_cards.append(player.hand.pop(idx))
            player.deck.cards.extend(returned_cards)
            for _ in returned_cards:
                card = player.draw()
                if not card:
                    break

    def _ready_active_units(self, active: str) -> None:
        player = self.gs.get_player(active)
        player.ready_base_units()
        for bf in self.gs.battlefields:
            bf.ready_side(active)

    def _phase_beginning(self, active: str) -> int:
        for bf in self.gs.battlefields:
            bf.begin_turn_reset()

        # Remove TEMPORARY units at the start of the active player's turn
        for bf in self.gs.battlefields:
            player = self.gs.get_player(active)
            units = bf.units_A if active == "A" else bf.units_B
            dead = [u for u in units if u.card.has_keyword("TEMPORARY")]
            for u in dead:
                units.remove(u)
                player.trash.append(u.card)
                player.base_gear.extend(u.gear)

        # Clear STUN status at the start of the active player's turn
        for bf in self.gs.battlefields:
            for unit in bf.units_A + bf.units_B:
                unit.stunned = False

        for bf in self.gs.battlefields:
            bf.last_controller = bf.controller()
        for bf in self.gs.battlefields:
            if bf.units_A and bf.units_B:
                bf.contested_this_turn = True
                if bf.controller() is None:
                    bf.showdown_pending = True

        self._ready_active_units(active)

        active_player = self.gs.get_player(active)
        # Clear leftover resources from last turn before channeling
        active_player.energy = 0
        active_player.power_pool.clear()

        # Channel Phase (§430): channel 2 runes from the rune deck. The player who
        # goes second channels one extra rune on their first turn. Turn 2 is always
        # the second player's first turn (turn 1 = starter, active flips each turn),
        # so this works regardless of which side starts the game.
        channel_count = 2
        if self.gs.turn == 2:
            channel_count = 3
        active_player.unlock_runes(channel_count)
        active_player.channel()
        # Only the Turn Player channels — opponent channels on their own turn

        if self.verbose:
            power_summary = ", ".join(
                f"{d.name}:{v}" for d, v in active_player.power_pool.items()
            ) or "none"
            print(
                f"  [CHANNEL] {active} energy={active_player.energy} "
                f"power={{{power_summary}}}"
            )

        vps = 0
        for bf in self.gs.battlefields:
            if bf.can_score_hold(active):
                vps += 1
                bf.mark_scored(active)
                if self.verbose:
                    bf_idx = self.gs.battlefields.index(bf)
                    print(f"  [HOLD] {active} holds BF{bf_idx} -> +1 VP")
                self._fire_scoring_trigger("on_hold", bf, active)
        return vps

    def _fire_turn_trigger(self, trigger: str, side: str) -> None:
        """Fire on_start_of_turn / on_end_of_turn for all of a player's units on
        board (across battlefields and base)."""
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        for bf in self.gs.battlefields:
            units = list(bf.units_A if side == "A" else bf.units_B)
            for unit in units:
                self._resolve_triggered_effects(unit.card, trigger, bf, actor, opponent,
                                                context_extra={"battlefield": bf})
        # Base units (use battlefield[0] as a neutral context anchor).
        anchor = self.gs.battlefields[0]
        for unit in list(actor.base_units):
            self._resolve_triggered_effects(unit.card, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor})

    def _fire_scoring_trigger(self, trigger: str, bf: Battlefield, side: str) -> None:
        """Fire on_conquer / on_hold for the scoring player's units at this BF
        (plus their deployed champion). Also grants HUNT XP."""
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        units = list(bf.units_A if side == "A" else bf.units_B)
        for unit in units:
            # HUNT keyword grants XP on Conquer or Hold.
            if unit.has_keyword("HUNT"):
                amount = unit.keyword_value("HUNT") or 1
                self.gs.add_xp(side, amount)
                if self.verbose:
                    print(f"  [HUNT] {side} gains {amount} XP (now {self.gs.get_xp(side)})")
            self._resolve_triggered_effects(
                unit.card, trigger, bf, actor, opponent,
                context_extra={"battlefield": bf},
            )

    def _phase_draw(self, ap: Player) -> None:
        card = ap.draw()
        if card and self.recorder:
            self.recorder.record_draw(ap.name, self.gs.turn, card)

    def _resolve_card_effects(
        self,
        card: Card,
        battlefield: Battlefield,
        actor: Player,
        opponent: Player,
    ) -> None:
        spec = CARD_REGISTRY.get(card.name)
        effect_specs: list[EffectSpec] = []
        if spec and spec.effects:
            effect_specs = list(spec.effects)
        elif getattr(card, "effects", None):
            try:
                effect_specs = [EffectSpec.from_dict(e) for e in card.effects]  # type: ignore[arg-type]
            except Exception:
                effect_specs = []

        context = EffectContext(self, card, actor, opponent, battlefield)

        # on_play / on_cast effects only (other triggers fire via
        # _resolve_triggered_effects). Old flat effects default trigger=on_play.
        play_specs = [es for es in effect_specs if es.trigger in ("on_play", "on_cast")]

        if not play_specs:
            # Fallback: an effect-less spell deals its printed damage to opponent.
            if not effect_specs and isinstance(card, SpellCard):
                context.deal_damage(int(getattr(card, "damage", 0)), target="opponent")
            return

        runs = 1
        # REPEAT: only repeat if the player actually paid the additional cost.
        # The play path tags the card instance with `_repeat_paid` when paid.
        if card.has_keyword("REPEAT") and getattr(card, "_repeat_paid", False):
            runs = 2

        try:
            for _ in range(runs):
                for effect_spec in play_specs:
                    if not self._check_condition(effect_spec.condition, card, actor, opponent, None):
                        continue
                    handler = EFFECT_REGISTRY.get(effect_spec.effect)
                    if not handler:
                        continue
                    # Resilience: a single malformed spec (e.g. a parser-emitted
                    # target/param the handler can't satisfy) must not abort the
                    # whole match. Skip + log instead. See KNOWN_ISSUES for the
                    # known offenders to fix at the spec/handler level.
                    try:
                        handler(context, effect_spec.merged_params())
                    except Exception as exc:  # noqa: BLE001
                        if self.verbose:
                            print(f"  [EFFECT-SKIP] {card.name}: "
                                  f"{effect_spec.effect} failed: {exc}")
        finally:
            # Kicker is consumed by this resolution; reset so a replayed instance
            # (return_from_trash, Yorick, ...) doesn't inherit a stale flag.
            if getattr(card, "_kicker_paid", False):
                card._kicker_paid = False

    def _resolve_triggered_effects(
        self,
        card: Card,
        trigger: str,
        battlefield: Battlefield,
        actor: Player,
        opponent: Player,
        context_extra: Optional[dict] = None,
    ) -> None:
        """Fire a card's effects whose `trigger` matches (e.g. on_conquer,
        on_hold, on_attack, on_defend, on_death, on_start_of_turn, on_end_of_turn)."""
        spec = CARD_REGISTRY.get(card.name)
        effect_specs: list[EffectSpec] = list(spec.effects) if spec and spec.effects else []
        if not effect_specs:
            return
        context = EffectContext(self, card, actor, opponent, battlefield)
        for es in effect_specs:
            if es.trigger != trigger:
                continue
            # Pay any cost / additional_cost the triggered ability carries BEFORE
            # the condition check (so a kicker_paid gate sees the payment). If a
            # cost exists but is unaffordable, the ability simply doesn't fire
            # (KNOWN_ISSUES #12).
            if not self._pay_triggered_cost(card, actor, es):
                continue
            if not self._check_condition(es.condition, card, actor, opponent, context_extra):
                continue
            handler = EFFECT_REGISTRY.get(es.effect)
            if not handler:
                continue
            # Resilience: mirror the guard in _resolve_card_effects — a single
            # malformed triggered spec must not abort the whole match. Skip + log.
            try:
                handler(context, es.merged_params())
            except Exception as exc:  # noqa: BLE001
                if self.verbose:
                    print(f"  [EFFECT-SKIP] {card.name}: "
                          f"{es.effect} ({trigger}) failed: {exc}")

    def _pay_triggered_cost(self, card: Card, actor: Player, es: EffectSpec) -> bool:
        """Pay a triggered effect's `cost` (activated-style: tap/energy/power/
        spend_xp/recycle/sacrifice) and/or `additional_cost` (kicker-style).
        Baseline policy: pay when affordable. Returns True when there was nothing
        to pay or it was fully paid; False when a cost existed but was
        unaffordable (the ability then doesn't fire). Sets card._kicker_paid on a
        successful payment so a `kicker_paid` condition passes. KNOWN_ISSUES #12."""
        cost = getattr(es, "cost", None)
        ac = getattr(es, "additional_cost", None)
        if not cost and not ac:
            return True
        side = "A" if actor is self.gs.A else "B"
        unit = self._find_unit_by_card(card)

        if ac:
            if not self._pay_one_additional_cost(card, actor, ac):
                return False
            card._kicker_paid = True

        if cost:
            parsed = self._parse_activated_cost(cost)
            if not self._activated_affordable(actor, unit, parsed):
                return False
            if (parsed["energy"] or parsed["power"]) and not actor.pay_cost(
                parsed["energy"], parsed["power"] or None, None
            ):
                return False
            if parsed["tap"] and unit is not None:
                unit.ready = False
            for _ in range(parsed["recycle"]):
                if actor.trash:
                    actor.deck.cards.append(actor.trash.pop(0))
            if parsed["spend_xp"]:
                self.gs.add_xp(side, -parsed["spend_xp"])
            if parsed["sacrifice"] and unit is not None:
                self._remove_unit_from_play(unit, side)
                actor.trash.append(unit.card)
            card._kicker_paid = True

        return True

    def _fire_units_trigger(self, trigger: str, side: str, exclude_card=None,
                            triggering_card=None) -> None:
        """Fire a trigger for every unit a side controls on board + base (and skip
        an optional excluded card so 'when another friendly unit ...' works).

        `triggering_card` (the card whose play/death caused this fan-out) is
        exposed to conditions via extra['triggering_card'] — e.g.
        triggering_unit_is_mighty. Defaults to exclude_card, which for
        on_friendly_unit_played IS the just-played unit."""
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        trig = triggering_card if triggering_card is not None else exclude_card
        for bf in self.gs.battlefields:
            for u in list(bf.units_A if side == "A" else bf.units_B):
                if u.card is exclude_card:
                    continue
                self._resolve_triggered_effects(u.card, trigger, bf, actor, opponent,
                                                context_extra={"battlefield": bf,
                                                               "triggering_card": trig})
        anchor = self.gs.battlefields[0]
        for u in list(actor.base_units):
            if u.card is exclude_card:
                continue
            self._resolve_triggered_effects(u.card, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor,
                                                           "triggering_card": trig})

    def _all_units_in_play(self):
        """Every UnitInPlay across battlefields and both bases."""
        units = []
        for bf in self.gs.battlefields:
            units.extend(bf.units_A)
            units.extend(bf.units_B)
        units.extend(self.gs.A.base_units)
        units.extend(self.gs.B.base_units)
        return units

    def _recompute_passives(self) -> None:
        """Re-evaluate all continuous (trigger: passive) abilities and fold their
        grants into the passive_might / passive_keywords overlays. Called whenever
        board state changes so `UnitInPlay.might` stays correct (Round 4 Tier 2)."""
        for u in self._all_units_in_play():
            u.passive_might = 0
            u.passive_keywords = set()

        for bf in self.gs.battlefields:
            for side in ("A", "B"):
                actor = self.gs.get_player(side)
                opponent = self.gs.get_player(self.gs.other(side))
                for unit in list(bf.units_A if side == "A" else bf.units_B):
                    self._apply_unit_passives(unit, side, bf, actor, opponent)
        anchor = self.gs.battlefields[0]
        for side in ("A", "B"):
            actor = self.gs.get_player(side)
            opponent = self.gs.get_player(self.gs.other(side))
            for unit in list(actor.base_units):
                self._apply_unit_passives(unit, side, anchor, actor, opponent)

    def _apply_unit_passives(self, unit, side, bf, actor, opponent) -> None:
        spec = CARD_REGISTRY.get(unit.card.name)
        if not (spec and spec.effects):
            return
        context = EffectContext(self, unit.card, actor, opponent, bf)
        for es in spec.effects:
            if es.trigger != "passive":
                continue
            if not self._check_condition(es.condition, unit.card, actor, opponent,
                                         {"battlefield": bf}):
                continue
            self._apply_passive_grant(unit, context, es)

    _PASSIVE_FRIENDLY_TARGETS = {
        "self", "this", "actor", "ally", "allies", "friendly", "friendly_unit",
        "all_friendly_units_here",
    }
    _PASSIVE_ENEMY_TARGETS = {
        "opponent", "enemy", "enemy_unit", "all_enemy_units_here",
    }

    _PASSIVE_BOARD_WIDE_SCOPES = {"board", "all_battlefields", "everywhere", "global", "all"}

    def _passive_targets(self, source_unit, bf, side, target, scope=None):
        """Resolve the units a passive ability applies to, honoring the corpus's
        target vocabulary. Self-targets hit only the source; group targets hit the
        relevant side(s) at the source's battlefield. A board-wide scope (anthems
        that read 'your <X> units' with no 'here') spans every battlefield + base."""
        key = (target or "self").lower()
        if key in ("self", "this"):
            return [source_unit]

        board_wide = str(scope or "").lower() in self._PASSIVE_BOARD_WIDE_SCOPES
        if board_wide:
            friendly = [u for b in self.gs.battlefields
                        for u in (b.units_A if side == "A" else b.units_B)]
            friendly += self.gs.get_player(side).base_units
            enemy = [u for b in self.gs.battlefields
                     for u in (b.units_B if side == "A" else b.units_A)]
            enemy += self.gs.get_player("B" if side == "A" else "A").base_units
        else:
            friendly = list(bf.units_A if side == "A" else bf.units_B)
            enemy = list(bf.units_B if side == "A" else bf.units_A)

        if key == "all_units_here":
            return list(friendly) + list(enemy)
        if key in self._PASSIVE_ENEMY_TARGETS:
            return list(enemy)
        # Default (incl. _PASSIVE_FRIENDLY_TARGETS and anything unknown) → friendlies.
        return list(friendly)

    def _apply_passive_grant(self, source_unit, context, es) -> None:
        """Fold a single passive (continuous) effect into the recompute overlays.
        Might-granting verbs become passive_might; give_keyword becomes a passive
        keyword. Unsupported passive verbs are safely ignored."""
        params = es.merged_params()
        side = context.actor_side
        bf = context.battlefield
        targets = self._passive_targets(source_unit, bf, side, es.target, es.scope)

        # Anthems/"while" buffs restricted to a subset ("your TOKEN units ...")
        # must honor the target_filter, not blanket every friendly (KNOWN_ISSUES #18).
        tf = es.target_filter
        if tf:
            targets = [u for u in targets if _effect_passes_filter(u, tf, context)]

        if es.effect == "give_keyword":
            keyword = str(params.get("keyword", "")).strip()
            if keyword:
                for u in targets:
                    u.passive_keywords.add(keyword)
            return

        # Might-granting passives (anthems, "while" buffs). buff_unit tagged as a
        # passive is an anthem (+N might), folded into the overlay rather than a
        # permanent counter so it clears when the source leaves.
        if es.effect in ("grant_might", "grant_temporary_might", "buff_unit",
                         "grant_temporary_might_if_alone"):
            amount = _effect_amount(context, params)
            if es.effect == "buff_unit" and not params.get("amount"):
                amount = 1
            if es.effect == "grant_temporary_might_if_alone" and len(
                bf.units_A if side == "A" else bf.units_B
            ) > 1:
                return  # not alone
            for u in targets:
                u.passive_might += amount

    _ENEMY_TARGETS = {"opponent", "enemy", "enemy_unit", "all_enemy_units_here"}

    def _deflect_surcharge(self, card: Card, target_lane: int) -> int:
        """Extra energy a spell costs because the opponent has DEFLECT units at
        the target battlefield (§809). Applies only when the spell targets the
        opponent. Returns the max DEFLECT value among eligible enemy units."""
        spec = CARD_REGISTRY.get(card.name)
        effects = list(spec.effects) if spec and spec.effects else []
        # Determine whether the spell targets enemy units.
        targets_enemy = False
        for es in effects:
            tgt = (es.target or "").lower()
            if tgt in self._ENEMY_TARGETS:
                targets_enemy = True
                break
            # deal_damage with no explicit target defaults to opponent.
            if es.effect == "deal_damage" and es.target is None:
                targets_enemy = True
                break
        if not targets_enemy:
            return 0
        if not (0 <= target_lane < len(self.gs.battlefields)):
            return 0
        bf = self.gs.battlefields[target_lane]
        opp_side = self.gs.other(self.gs.active)
        enemy_units = bf.units_A if opp_side == "A" else bf.units_B
        return max((u.keyword_value("DEFLECT") for u in enemy_units), default=0)

    def _check_condition(
        self,
        cond: Optional[dict],
        card: Card,
        actor: Player,
        opponent: Player,
        extra: Optional[dict],
    ) -> bool:
        """Evaluate an effect's optional condition. None = always true."""
        if not cond:
            return True
        ctype = cond.get("type")
        params = cond.get("params", {})
        side = "A" if actor is self.gs.A else "B"
        extra = extra or {}

        def _threshold(default: int = 0) -> int:
            """Read the condition's numeric threshold. The loader canonicalizes
            this to `n`, but read through the alias list defensively so a spec
            built outside the loader (or future data drift) can't silently
            reintroduce the always-true bug (see cards_registry._normalize_condition)."""
            for key in ("n", "amount", "count", "value", "threshold"):
                v = params.get(key)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return int(v)
            return default

        if ctype == "you_have_n_or_more_runes":
            return actor.total_runes_in_play() >= _threshold()
        if ctype == "you_have_n_or_more_units_here":
            bf = extra.get("battlefield")
            if bf is None:
                return False
            units = bf.units_A if side == "A" else bf.units_B
            return len(units) >= _threshold()
        if ctype == "spell_cost_at_least":
            return int(extra.get("triggering_spell_cost", 0)) >= _threshold()
        if ctype == "this_is_alone":
            bf = extra.get("battlefield")
            if bf is None:
                return False
            units = bf.units_A if side == "A" else bf.units_B
            return len(units) <= 1
        if ctype == "this_is_mighty":
            return int(getattr(card, "might", 0) or 0) >= 5
        if ctype == "triggering_unit_is_mighty":
            # Gate on the UNIT THAT JUST TRIGGERED this ability (e.g. the mighty
            # unit you just played), not the source card (KNOWN_ISSUES #15).
            trig = extra.get("triggering_card")
            return int(getattr(trig, "might", 0) or 0) >= 5
        if ctype == "kicker_paid":
            return bool(getattr(card, "_kicker_paid", False))
        if ctype == "friendly_unit_died_this_turn":
            return bool(self.gs.friendly_unit_died_this_turn.get(side, False))
        if ctype == "you_played_n_spells_this_turn":
            return self.gs.spells_played_this_turn.get(side, 0) >= _threshold()
        if ctype == "you_already_played_another_card_this_turn":
            return self.gs.cards_played_this_turn.get(side, 0) >= 1
        if ctype == "controller_has_xp_at_least":
            return self.gs.get_xp(side) >= _threshold()
        if ctype == "card_in_trash_count_at_least":
            return len(actor.trash) >= _threshold()
        # Round 4 Tier 1 conditions
        if ctype == "this_is_buffed":
            unit = self._find_unit_by_card(card)
            return bool(unit and unit.might_counters > 0)
        if ctype == "this_is_empowered":
            # Vendetta EMPOWERED dependent ability: fires only while the source
            # unit carries the empowered status (see UnitInPlay.empowered).
            unit = self._find_unit_by_card(card)
            return bool(unit and getattr(unit, "empowered", False))
        if ctype == "you_control_subtype":
            tag = str(params.get("tag", ""))
            for bf in self.gs.battlefields:
                for u in (bf.units_A if side == "A" else bf.units_B):
                    if tag in (u.card.tags or []):
                        return True
            return any(tag in (u.card.tags or []) for u in actor.base_units)
        if ctype == "score_within_n_of_victory":
            pts = self.gs.points_A if side == "A" else self.gs.points_B
            return pts >= self.gs.victory_score - _threshold()
        if ctype == "you_discarded_card_this_turn":
            return bool(self.gs.discarded_this_turn.get(side, False))
        if ctype == "cards_burned_this_turn_at_least":
            return self.gs.cards_burned_this_turn.get(side, 0) >= _threshold()
        # Conditions needing context the engine doesn't track yet → safe False
        # (effects gated on them simply don't fire): excess_damage_at_least,
        # controller_has_facedown_card, target_was_stunned.
        return False

    def _cost_reduction(self, card: Card, actor: Player) -> int:
        """Static / conditional flat energy cost reduction (Round 4 Tier 2).
        Sums every `reduce_cost` effect (trigger `cost_modifier`) on the card whose
        optional condition currently holds. Dynamic (amount_source) reductions are
        out of scope. Returns a non-negative energy amount to subtract."""
        spec = CARD_REGISTRY.get(card.name)
        if not (spec and spec.effects):
            return 0
        side = "A" if actor is self.gs.A else "B"
        opponent = self.gs.get_player(self.gs.other(side))
        total = 0
        for es in spec.effects:
            if es.trigger != "cost_modifier" or es.effect != "reduce_cost":
                continue
            if not self._check_condition(es.condition, card, actor, opponent, None):
                continue
            total += int(es.params.get("amount", 0))
        return max(0, total)

    # ------------------------------------------------------------------
    # Additional costs / kicker at play time (B1)

    def _first_friendly_unit_on_board(self, ap: Player):
        """First friendly UnitInPlay on any battlefield, else a base unit, else None."""
        side = "A" if ap is self.gs.A else "B"
        for bf in self.gs.battlefields:
            units = bf.units_A if side == "A" else bf.units_B
            if units:
                return units[0]
        return ap.base_units[0] if ap.base_units else None

    def _try_pay_additional_costs(self, card: Card, ap: Player) -> bool:
        """If the card has an effect carrying an `additional_cost` (kicker), try to
        pay the first affordable one. Policy: always pay when affordable (the
        baseline agents are not kicker-aware). Sets `card._kicker_paid = True` when
        paid. One kicker per card. Returns whether anything was paid."""
        spec = CARD_REGISTRY.get(card.name)
        if not (spec and spec.effects):
            return False
        for es in spec.effects:
            ac = getattr(es, "additional_cost", None)
            if not ac:
                continue
            if self._pay_one_additional_cost(card, ap, ac):
                card._kicker_paid = True
                if self.verbose:
                    print(f"  {ap.name} pays kicker for {card.name}: {ac}")
                return True
            break  # only the first additional_cost is considered (one kicker/card)
        return False

    def _pay_one_additional_cost(self, card: Card, ap: Player, ac: dict) -> bool:
        """Check an additional_cost dict is affordable, then pay it atomically.
        Returns True iff fully paid (no partial payment)."""
        energy = int(ac.get("energy", 0) or 0)
        power = int(ac.get("power", 0) or 0)
        discard_n = int(ac.get("discard_cards", 0) or 0)
        kill = bool(ac.get("kill_friendly_unit"))
        exhaust = bool(ac.get("exhaust_friendly_unit"))

        # --- affordability check (no mutation yet) ---
        if (energy or power) and not ap.can_pay_cost(energy, power or None, None):
            return False
        # +1: never discard the very card being played.
        if discard_n and len(ap.hand) < discard_n + 1:
            return False
        target_unit = self._first_friendly_unit_on_board(ap) if (kill or exhaust) else None
        if (kill or exhaust) and target_unit is None:
            return False

        # --- payment ---
        if (energy or power) and not ap.pay_cost(energy, power or None, None):
            return False
        for _ in range(discard_n):
            idx = next((i for i, c in enumerate(ap.hand) if c is not card), None)
            if idx is None:
                return False
            ap.trash.append(ap.hand.pop(idx))
        if target_unit is not None:
            if exhaust:
                target_unit.ready = False
            if kill:
                side = "A" if ap is self.gs.A else "B"
                self._remove_unit_from_play(target_unit, side)
                ap.trash.append(target_unit.card)
        return True

    def _find_unit_by_card(self, card: Card):
        """Locate the UnitInPlay whose card is this one (board or base)."""
        for bf in self.gs.battlefields:
            for u in bf.units_A + bf.units_B:
                if u.card is card:
                    return u
        for p in (self.gs.A, self.gs.B):
            for u in p.base_units:
                if u.card is card:
                    return u
        return None

    def _action_fingerprint(self, ap: Player, op: Player):
        """Cheap signature of everything a turn action can change. Used by the
        action loop to detect a no-op (an action the engine silently refuses) so
        the agent can't spin on it forever."""
        gs = self.gs

        def player_sig(p: Player):
            return (
                len(p.hand), len(p.deck.cards), len(p.trash), len(p.banished),
                len(p.base_units), len(p.base_gear), p.energy,
                tuple(sorted((d.name, n) for d, n in p.power_pool.items())),
                p.total_runes_in_play(),
                tuple(sorted(u.card.name for u in p.base_units if u.ready)),
            )

        board = tuple(
            (len(bf.units_A), len(bf.units_B),
             sum(u.might for u in bf.units_A), sum(u.might for u in bf.units_B))
            for bf in gs.battlefields
        )
        return (
            player_sig(ap), player_sig(op), board,
            gs.points_A, gs.points_B, len(gs.chain),
            gs.get_xp("A"), gs.get_xp("B"),
        )

    def _apply_action(self, ap: Player, action: Action, cards_played_this_turn: int = 0) -> None:
        if len(action) == 3:  # type: ignore[arg-type]
            kind, idx, lane = action  # type: ignore[misc]
            dst_lane = None
        else:
            kind, idx, lane, dst_lane = action

        # Validate lanes only for actions that use them as integers
        if kind not in ("MOVE", "ABILITY") and lane is not None and isinstance(lane, int) and not (0 <= lane < len(self.gs.battlefields)):
            lane = 0
        if dst_lane is not None and isinstance(dst_lane, int) and not (0 <= dst_lane < len(self.gs.battlefields) + 1):
            dst_lane = None

        base_index = len(self.gs.battlefields)

        opponent = self.gs.get_player(self.gs.other(self.gs.active))           

        if kind == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, (UnitCard, LegendCard)):
                effective_energy = card.cost_energy
                if card.has_keyword("LEGION") and cards_played_this_turn > 0:
                    legion_reduction = get_legion_cost_reduction(card.name)
                    if legion_reduction is not None:
                        effective_energy = max(0, card.cost_energy - legion_reduction)
                effective_energy = max(0, effective_energy - self._cost_reduction(card, ap))
                if not ap.can_pay_cost(effective_energy, card.cost_power, card.cost_power_domain):
                    return
                if not ap.pay_cost(effective_energy, card.cost_power, card.cost_power_domain):
                    return
                if self.verbose:
                    print(f"  {ap.name} plays UNIT: {card.name}")
                # ACCELERATE: optional additional cost of 1 energy + 1 power of the unit's domain
                enters_ready = False
                if card.has_keyword("ACCELERATE"):
                    accel_domain = card.domain
                    if ap.can_pay_cost(1, 1, accel_domain):
                        ap.pay_cost(1, 1, accel_domain)
                        enters_ready = True
                unit = UnitInPlay(card=card, ready=enters_ready)
                ap.base_units.append(unit)

                # B1: optional additional cost (kicker), paid before resolution.
                self._try_pay_additional_costs(card, ap)

                # Resolve on_play effects for EVERY unit. (Previously this was
                # gated on `LEGION and cards_played>0`, so normal "When you play
                # me" effects never fired — see KNOWN_ISSUES. LEGION's mechanical
                # benefit is the cost reduction applied above, not effect gating.)
                self._resolve_card_effects(card, self.gs.battlefields[0], ap, opponent)

                # WEAPONMASTER: choose an Equipment you control and pay its Equip
                # cost reduced by 1 Power of any domain to attach it to this unit.
                # We approximate the reduced cost as max(0, gear.cost_energy - 1)
                # and only attach when affordable (no free auto-attach).
                if card.has_keyword("WEAPONMASTER") and ap.base_gear:
                    gear_card = ap.base_gear[0]
                    reduced = max(0, int(getattr(gear_card, "cost_energy", 0)) - 1)
                    if ap.can_pay_cost(reduced, None, None) and ap.pay_cost(reduced, None, None):
                        ap.base_gear.pop(0)
                        unit.gear.append(gear_card)
                        if self.verbose:
                            print(f"  {ap.name} WEAPONMASTER attaches {gear_card.name} to {card.name}")

                # Recompute by identity: a kicker `discard_cards` cost may have
                # popped another hand card, shifting the original index.
                cur_idx = next((i for i, c in enumerate(ap.hand) if c is card), idx)
                ap.remove_from_hand(cur_idx)
                self.units_played += 1
                # on_friendly_unit_played: notify the player's OTHER units.
                self._fire_units_trigger("on_friendly_unit_played", ap.name, exclude_card=card)
                if self.recorder:
                    self.recorder.record_play(
                        ap.name,
                        self.gs.turn,
                        card,
                        action="UNIT",
                        battlefield_index=0,
                    )


        elif kind == "SPELL" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, SpellCard):
                target_lane = lane if lane is not None else 0
                # DEFLECT: if this spell targets enemy units and the opponent
                # controls DEFLECT units at the target battlefield, the spell
                # costs that much more energy (additional cost, §809).
                deflect_surcharge = self._deflect_surcharge(card, target_lane)
                base_energy = max(0, card.cost_energy + deflect_surcharge
                                  - self._cost_reduction(card, ap))
                if not ap.can_pay_cost(base_energy, card.cost_power, card.cost_power_domain):
                    return
                if not ap.pay_cost(base_energy, card.cost_power, card.cost_power_domain):
                    return
                # B1: optional additional cost (kicker), paid before chain resolution.
                self._try_pay_additional_costs(card, ap)
                # REPEAT [Cost]: optional additional cost. Pay it (once) if we can
                # afford it, which flags the effect to execute a second time.
                # Per the rules the REPEAT cost equals the spell's printed cost,
                # so a bare "REPEAT" keyword (no explicit value) defaults to
                # card.cost_energy. An explicit "REPEAT N" overrides for the rare
                # exceptions. (Note: card.keyword_value returns 1 for bare
                # keywords, so we detect bare-vs-parameterized by inspecting the
                # raw keyword list rather than relying on the integer value.)
                card._repeat_paid = False
                if card.has_keyword("REPEAT"):
                    bare = any(k.strip().upper() == "REPEAT" for k in card.keywords)
                    if bare:
                        repeat_cost = card.cost_energy
                        if self.verbose:
                            print(f"  REPEAT defaults to spell cost ({repeat_cost}) for {card.name}")
                    else:
                        repeat_cost = card.keyword_value("REPEAT")
                    if repeat_cost and ap.can_pay_cost(repeat_cost, None, None):
                        if ap.pay_cost(repeat_cost, None, None):
                            card._repeat_paid = True
                # Recompute by identity: a kicker `discard_cards` cost may have
                # popped another hand card, shifting the original index.
                cur_idx = next((i for i, c in enumerate(ap.hand) if c is card), idx)
                ap.remove_from_hand(cur_idx)
                self.gs.spells_played_this_turn[ap.name] = self.gs.spells_played_this_turn.get(ap.name, 0) + 1
                if self.verbose:
                    print(f"  {ap.name} plays SPELL: {card.name} at BF{target_lane}")
                self.gs.chain.append(ChainItem(player=ap.name, card=card, bf_idx=target_lane))
                self._run_chain(ap.name)
                if self.recorder:
                    self.recorder.record_play(
                        ap.name,
                        self.gs.turn,
                        card,
                        action="SPELL",
                        battlefield_index=target_lane,
                    )
        elif kind == "GEAR" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, GearCard):
                gear_energy = max(0, card.cost_energy - self._cost_reduction(card, ap))
                if not ap.can_pay_cost(gear_energy, card.cost_power, card.cost_power_domain):
                    return
                if not ap.pay_cost(gear_energy, card.cost_power, card.cost_power_domain):
                    return
                target_bf = self.gs.battlefields[lane if lane is not None else 0]
                friendly_units = target_bf.units_A if self.gs.active == "A" else target_bf.units_B

                if friendly_units:
                    target_unit = friendly_units[0]
                    target_unit.gear.append(card)
                    if self.verbose:
                        print(f"  {ap.name} plays GEAR: {card.name} -> {target_unit.card.name}")
                else:
                    ap.base_gear.append(card)
                    if self.verbose:
                        print(f"  {ap.name} plays GEAR: {card.name} (staged at base)")

                ap.remove_from_hand(idx)
                if self.recorder:
                    self.recorder.record_play(
                        ap.name,
                        self.gs.turn,
                        card,
                        action="GEAR",
                        battlefield_index=lane if lane is not None else 0,
                    )

        elif kind == "CHAMPION":
            is_A = (self.gs.active == "A")
            champion = self.gs.champion_A if is_A else self.gs.champion_B
            already_deployed = self.gs.champion_A_deployed if is_A else self.gs.champion_B_deployed
            if champion is None or already_deployed:
                return
            if not ap.can_pay_cost(champion.cost_energy, champion.cost_power, champion.cost_power_domain):
                return
            if not ap.pay_cost(champion.cost_energy, champion.cost_power, champion.cost_power_domain):
                return
            unit = UnitInPlay(card=champion, ready=False)
            ap.base_units.append(unit)
            if is_A:
                self.gs.champion_A_deployed = True
            else:
                self.gs.champion_B_deployed = True
            if self.verbose:
                print(f"  {ap.name} deploys CHAMPION: {champion.name}")
            self.units_played += 1
            if self.recorder:
                self.recorder.record_play(
                    ap.name,
                    self.gs.turn,
                    champion,
                    action="UNIT",
                    battlefield_index=lane if lane is not None else 0,
                )

        elif kind == "MOVE":
            # Illegal during Showdown or Closed State (active chain)
            if self.gs.showdown_active or self.gs.chain:
                return

            src = lane
            dst = dst_lane
            if src is None or dst is None or src == dst:
                return
            if src not in range(len(self.gs.battlefields) + 1):
                return
            if dst not in range(len(self.gs.battlefields) + 1):
                return

            side = self.gs.active
            base = ap.base_units

            if src == base_index:
                if dst == base_index:
                    return
                unit = ap.pop_base_unit()
                if unit is None:
                    return
                if unit.is_token:
                    ap.base_units.insert(0, unit)
                    return
                if self.verbose:
                    print(f"  {ap.name} moves UNIT: {unit.card.name} to BF{dst}")
                unit.ready = False
                target_bf = self.gs.battlefields[dst]

                # Check if this move establishes contested status (moving to a BF the player doesn't control)
                prev_controller = target_bf.controller()
                target_bf.add_unit(side, unit)
                new_controller = target_bf.controller()

                # Contested if: gaining control from empty/opponent, OR both sides now have units
                gained_control = prev_controller != side and new_controller == side
                both_sides = target_bf.units_A and target_bf.units_B

                if gained_control or both_sides:
                    target_bf.contested_this_turn = True
                    self._run_showdown(dst, attacker=side)

                # Dispatch movement effects
                handler = MOVEMENT_REGISTRY.get(unit.card.name)
                if handler:
                    handler(ap, opponent, self.gs, unit, "base", "bf", target_bf)
                self._resolve_triggered_effects(unit.card, "on_move", target_bf, ap, opponent,
                                                context_extra={"battlefield": target_bf})

            elif dst == base_index:
                src_bf = self.gs.battlefields[src]
                unit = src_bf.pop_unit_for_movement(side)
                if unit is None:
                    return
                unit.ready = True
                base.append(unit)

                # Dispatch movement effects
                handler = MOVEMENT_REGISTRY.get(unit.card.name)
                if handler:
                    handler(ap, opponent, self.gs, unit, "bf", "base", None)
                self._resolve_triggered_effects(unit.card, "on_move", self.gs.battlefields[0],
                                                ap, opponent,
                                                context_extra={"battlefield": self.gs.battlefields[0]})
            else:
                src_bf = self.gs.battlefields[src]
                dst_bf = self.gs.battlefields[dst]
                unit = src_bf.pop_unit_for_movement(side)
                if unit is None:
                    return
                if not unit.has_keyword("GANKING"):
                    src_bf.add_unit(side, unit)
                    unit.ready = True
                    return
                unit.ready = False

                # Check if this move establishes contested status (moving to a BF the player doesn't control)
                prev_controller = dst_bf.controller()
                dst_bf.add_unit(side, unit)
                new_controller = dst_bf.controller()

                # Contested if: gaining control from empty/opponent, OR both sides now have units
                gained_control = prev_controller != side and new_controller == side
                both_sides = dst_bf.units_A and dst_bf.units_B

                if gained_control or both_sides:
                    dst_bf.contested_this_turn = True
                    self._run_showdown(dst, attacker=side)

                # Dispatch movement effects
                handler = MOVEMENT_REGISTRY.get(unit.card.name)
                if handler:
                    handler(ap, opponent, self.gs, unit, "bf", "bf", dst_bf)
                self._resolve_triggered_effects(unit.card, "on_move", dst_bf, ap, opponent,
                                                context_extra={"battlefield": dst_bf})

        elif kind == "ABILITY":
            ability_id = idx  # idx actually contains the ability_id
            arg = lane  # lane actually contains the argument
            if ability_id == "PYKE_LEGEND":
                self._apply_pyke_ability(ap, opponent)
            elif ability_id == "GOLD_SACRIFICE":
                self._apply_gold_sacrifice(ap, str(arg) if arg is not None else "FURY")
            elif ability_id == "ACTIVATED":
                self._apply_activated_ability(ap, opponent, arg)

    def _apply_pyke_ability(self, ap: Player, op: Player) -> None:
        """[1],[tap]: Return a friendly unit at a battlefield to hand. Play Gold token."""
        side = "A" if ap is self.gs.A else "B"

        # Find Pyke legend on any friendly battlefield, must be ready
        pyke_unit = None
        for bf in self.gs.battlefields:
            units = bf.units_A if side == "A" else bf.units_B
            for u in units:
                if u.card.name == "Pyke Bloodharbor Ripper" and u.ready:
                    pyke_unit = u
                    break
            if pyke_unit:
                break

        if pyke_unit is None:
            return
        if not ap.can_pay_cost(1, None, None):
            return
        ap.pay_cost(1, None, None)
        pyke_unit.ready = False

        # Return a friendly unit from a battlefield to hand (prefer non-Pyke units)
        for bf in self.gs.battlefields:
            units = bf.units_A if side == "A" else bf.units_B
            candidates = [u for u in units if u is not pyke_unit and not u.is_token]
            if candidates:
                target_unit = candidates[0]
                units.remove(target_unit)
                ap.hand.append(target_unit.card)
                if self.verbose:
                    print(f"  {ap.name} PYKE ABILITY: returned {target_unit.card.name} to hand")
                break

        # Spawn Gold token to base
        from .movement_effects import _spawn_token_to_base
        _spawn_token_to_base(ap, "Gold", ready=False)
        if self.verbose:
            print(f"  {ap.name} spawned Gold token")

    def _apply_gold_sacrifice(self, ap: Player, domain_str: str) -> None:
        """Kill a Gold token, add a rune of chosen domain."""
        gold = next((u for u in ap.base_units if u.card.name == "Gold" and u.is_token), None)
        if gold is None:
            return
        ap.base_units.remove(gold)
        ap.trash.append(gold.card)
        try:
            domain = Domain[domain_str.upper()]
            ap.add_rune(domain, ready=True)
            if self.verbose:
                print(f"  {ap.name} GOLD SACRIFICE: gained {domain_str} rune")
        except (KeyError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Generic activated abilities (Round 4 Tier 2 / D3)

    def activatable_abilities(self, side: str) -> list:
        """Deterministic list of activated abilities a side can use in its Open
        State (main phase, non-reaction): unit/legend abilities tagged
        `trigger: activated`, plus EQUIP entries for gear waiting at base. The
        list order is stable for a given board, so an agent can pick by index and
        the engine re-resolves the same entry. Affordability is NOT filtered here
        (so indices stay stable) — payment fails gracefully if unaffordable."""
        ap = self.gs.get_player(side)
        out: list = []
        for bf_idx, bf in enumerate(self.gs.battlefields):
            for unit in (bf.units_A if side == "A" else bf.units_B):
                spec = CARD_REGISTRY.get(unit.card.name)
                if not (spec and spec.effects):
                    continue
                for eff in spec.effects:
                    if eff.trigger != "activated":
                        continue
                    if (eff.timing or "").lower() == "reaction":
                        continue
                    # EMPOWER can only be activated while NOT already empowered.
                    if eff.effect == "empower_self" and getattr(unit, "empowered", False):
                        continue
                    out.append({"type": "ability", "unit": unit, "bf_idx": bf_idx, "eff": eff})
        for unit in ap.base_units:
            spec = CARD_REGISTRY.get(unit.card.name)
            if not (spec and spec.effects):
                continue
            for eff in spec.effects:
                if eff.trigger != "activated":
                    continue
                if (eff.timing or "").lower() == "reaction":
                    continue
                if eff.effect == "empower_self" and getattr(unit, "empowered", False):
                    continue
                out.append({"type": "ability", "unit": unit, "bf_idx": None, "eff": eff})
        for gear in list(ap.base_gear):
            out.append({"type": "equip", "gear": gear})
        return out

    @staticmethod
    def _parse_activated_cost(cost) -> dict:
        """Normalize the mixed string/dict/None cost forms the generator emits."""
        import re
        parsed = {"energy": 0, "power": 0, "tap": False, "recycle": 0,
                  "sacrifice": False, "spend_xp": 0}
        if cost is None:
            return parsed
        if isinstance(cost, dict):
            parsed["energy"] = int(cost.get("energy", 0) or 0)
            parsed["power"] = int(cost.get("power", 0) or 0)
            parsed["tap"] = bool(cost.get("tap") or cost.get("exhaust_self")
                                 or cost.get("exhaust"))
            parsed["recycle"] = int(cost.get("recycle_from_trash",
                                             cost.get("recycle", 0)) or 0)
            parsed["sacrifice"] = bool(cost.get("sacrifice_self")
                                       or cost.get("kill_friendly"))
            parsed["spend_xp"] = int(cost.get("spend_xp", 0) or 0)
        elif isinstance(cost, str):
            for tok in cost.split(","):
                t = tok.strip().lower()
                if t in ("tap", "exhaust", "exhaust_self"):
                    parsed["tap"] = True
                elif t.startswith("recycle"):
                    m = re.search(r"\d+", t)
                    parsed["recycle"] = int(m.group()) if m else 1
                elif t.isdigit():
                    parsed["energy"] = int(t)
        return parsed

    def _activated_affordable(self, ap: Player, unit, parsed: dict) -> bool:
        side = "A" if ap is self.gs.A else "B"
        if parsed["tap"] and unit is not None and not unit.ready:
            return False
        if (parsed["energy"] or parsed["power"]) and not ap.can_pay_cost(
            parsed["energy"], parsed["power"] or None, None
        ):
            return False
        if parsed["recycle"] and len(ap.trash) < parsed["recycle"]:
            return False
        if parsed["spend_xp"] and self.gs.get_xp(side) < parsed["spend_xp"]:
            return False
        return True

    def _apply_activated_ability(self, ap: Player, opponent: Player, arg) -> None:
        try:
            index = int(arg)
        except (TypeError, ValueError):
            return
        side = "A" if ap is self.gs.A else "B"
        abilities = self.activatable_abilities(side)
        if not (0 <= index < len(abilities)):
            return
        entry = abilities[index]

        if entry["type"] == "equip":
            gear = entry["gear"]
            if gear not in ap.base_gear:
                return
            if not ap.can_pay_cost(gear.cost_energy, gear.cost_power, gear.cost_power_domain):
                return
            target_unit = self._first_friendly_unit_on_board(side)
            if target_unit is None:
                return
            if not ap.pay_cost(gear.cost_energy, gear.cost_power, gear.cost_power_domain):
                return
            ap.base_gear.remove(gear)
            target_unit.gear.append(gear)
            if self.verbose:
                print(f"  {ap.name} EQUIP: {gear.name} -> {target_unit.card.name}")
            return

        # Unit/legend activated ability.
        unit = entry["unit"]
        eff = entry["eff"]
        parsed = self._parse_activated_cost(eff.cost)
        if not self._activated_affordable(ap, unit, parsed):
            return
        # Pay.
        if parsed["energy"] or parsed["power"]:
            if not ap.pay_cost(parsed["energy"], parsed["power"] or None, None):
                return
        if parsed["tap"] and unit is not None:
            unit.ready = False
        for _ in range(parsed["recycle"]):
            if ap.trash:
                ap.deck.cards.append(ap.trash.pop(0))
        if parsed["spend_xp"]:
            self.gs.add_xp(side, -parsed["spend_xp"])
        if parsed["sacrifice"] and unit is not None:
            self._remove_unit_from_play(unit, side)
            ap.trash.append(unit.card)

        bf = self.gs.battlefields[entry["bf_idx"]] if entry["bf_idx"] is not None \
            else self.gs.battlefields[0]
        handler = EFFECT_REGISTRY.get(eff.effect)
        if handler is None:
            return
        context = EffectContext(self, unit.card if unit else ap.base_units[0].card,
                                ap, opponent, bf)
        handler(context, eff.merged_params())
        if self.verbose:
            print(f"  {ap.name} ACTIVATED: {eff.effect}")

    def _first_friendly_unit_on_board(self, side: str):
        for bf in self.gs.battlefields:
            units = bf.units_A if side == "A" else bf.units_B
            non_token = [u for u in units if not u.is_token]
            if non_token:
                return non_token[0]
        return None

    def _remove_unit_from_play(self, unit, side: str) -> None:
        for bf in self.gs.battlefields:
            units = bf.units_A if side == "A" else bf.units_B
            if unit in units:
                units.remove(unit)
                return
        ap = self.gs.get_player(side)
        if unit in ap.base_units:
            ap.base_units.remove(unit)

    # ------------------------------------------------------------------
    # Death replacement (Round 4 Tier 2) — Guardian Angel / Zhonya's family

    _DEATH_REPLACEMENT_EFFECTS = ("replace_death_with_recall", "prevent_death")

    def _unit_death_replacement(self, unit):
        """Return ('unit', None, spec) or ('gear', gear_card, spec) if this dying
        unit has a death-replacement available — from its own card effects or an
        attached gear's effects (trigger `death_replacement`). Else None."""
        spec = CARD_REGISTRY.get(unit.card.name)
        if spec and spec.effects:
            for es in spec.effects:
                if es.trigger == "death_replacement" and es.effect in self._DEATH_REPLACEMENT_EFFECTS:
                    return ("unit", None, es)
        for gear in list(unit.gear):
            gspec = CARD_REGISTRY.get(gear.name)
            if gspec and gspec.effects:
                for es in gspec.effects:
                    if es.trigger == "death_replacement" and es.effect in self._DEATH_REPLACEMENT_EFFECTS:
                        return ("gear", gear, es)
        return None

    def _try_replace_death(self, dead_unit, owner_side: str) -> bool:
        """If the dying unit has a death replacement, perform it — heal, exhaust,
        recall to base, and destroy the source gear (if any) — and return True.
        The unit is assumed already removed from its battlefield by the kill path.
        Returns False if there is no replacement (caller routes the death normally)."""
        repl = self._unit_death_replacement(dead_unit)
        if repl is None:
            return False
        owner = self.gs.get_player(owner_side)
        kind, gear, _es = repl
        dead_unit.reset_damage()        # heal
        dead_unit.ready = False         # exhaust
        if kind == "gear" and gear is not None:
            if gear in dead_unit.gear:
                dead_unit.gear.remove(gear)
            owner.trash.append(gear)    # the gear is destroyed instead of the unit
        owner.base_units.append(dead_unit)  # recall (not a move)
        if self.verbose:
            print(f"  {owner.name} DEATH REPLACEMENT: {dead_unit.card.name} recalled instead of dying")
        return True

    def _route_combat_deaths(self, stats, bf) -> None:
        """Apply death replacements, then trash the truly-dead, route their gear to
        base, set the friendly-died flag, and fire on_death / on_friendly_unit_death."""
        ordered = [(u, "A") for u in stats.dead_A] + [(u, "B") for u in stats.dead_B]
        truly_dead = []
        for dead_unit, owner_side in ordered:
            if self._try_replace_death(dead_unit, owner_side):
                continue
            owner = self.gs.get_player(owner_side)
            owner.trash.append(dead_unit.card)
            owner.base_gear.extend(dead_unit.gear)
            self.gs.friendly_unit_died_this_turn[owner_side] = True
            truly_dead.append((dead_unit, owner_side))
        for dead_unit, owner_side in truly_dead:
            actor = self.gs.get_player(owner_side)
            opponent = self.gs.get_player(self.gs.other(owner_side))
            self._resolve_triggered_effects(
                dead_unit.card, "on_death", bf, actor, opponent,
                context_extra={"battlefield": bf},
            )
            # "When this leaves the board" fires on death too (KNOWN_ISSUES #9).
            self._fire_leaves_board(dead_unit.card, owner_side, bf)
            self._fire_units_trigger("on_friendly_unit_death", owner_side,
                                     exclude_card=dead_unit.card)

    def _fire_leaves_board(self, card: Card, owner_side: str, bf: Battlefield) -> None:
        """Fire a card's `leaves_board` triggered effects. 'Leaving the board'
        covers ANY board exit — death, recall, bounce-to-hand, banish — not just
        death (KNOWN_ISSUES #9). Callers invoke this at each exit path."""
        actor = self.gs.get_player(owner_side)
        opponent = self.gs.get_player(self.gs.other(owner_side))
        self._resolve_triggered_effects(
            card, "leaves_board", bf, actor, opponent,
            context_extra={"battlefield": bf},
        )

    def _run_chain(self, caster: str) -> None:
        """Execute the spell chain (LIFO stack) with two-player priority loop (§331–336)."""
        active = self.gs.other(caster)
        passes = 0

        while passes < 2 and self.gs.chain:
            player = self.gs.get_player(active)
            if player.agent is None:
                passes += 1
                active = self.gs.other(active)
                continue

            action = player.agent.decide_reaction(self.gs.get_player(self.gs.other(active)), self.gs.chain)

            if action[0] == "PASS":
                passes += 1
            else:
                kind, idx, lane = action[0], action[1], action[2] if len(action) > 2 else None
                if kind == "SPELL" and idx is not None and 0 <= idx < len(player.hand):
                    card = player.hand[idx]
                    if isinstance(card, SpellCard) and card.has_keyword("REACTION"):
                        if player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                            if player.pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                                if lane is None or not (0 <= lane < len(self.gs.battlefields)):
                                    lane = 0
                                player.remove_from_hand(idx)
                                self.gs.chain.append(ChainItem(player=active, card=card, bf_idx=lane))
                                passes = 0

            active = self.gs.other(active)

        # Resolve chain LIFO
        while self.gs.chain:
            item = self.gs.chain.pop()
            actor = self.gs.get_player(item.player)
            opponent = self.gs.get_player(self.gs.other(item.player))
            battlefield = self.gs.battlefields[item.bf_idx]
            self._resolve_card_effects(item.card, battlefield, actor, opponent)

            if self.recorder:
                before_a = list(battlefield.units_A)
                before_b = list(battlefield.units_B)
                self._record_spell_deaths(battlefield, before_a, before_b)

            self.spells_cast += 1
            # on_play_spell: notify the caster's units (e.g. Ravenbloom Student).
            if isinstance(item.card, SpellCard):
                self._fire_units_trigger("on_play_spell", item.player, exclude_card=item.card)

    def _run_showdown(self, bf_idx: int, attacker: str) -> None:
        """Execute a showdown at the given battlefield (§337–345)."""
        if self.gs.showdown_active:
            return  # Already in a showdown

        if self.verbose:
            print(f"  [SHOWDOWN triggered at BF{bf_idx}] {attacker} has focus")

        self.gs.showdown_active = True
        self.gs.showdown_bf_idx = bf_idx
        self.gs.focus_player = attacker

        passes = 0
        while passes < 2:
            focus_player = self.gs.get_player(self.gs.focus_player)
            opponent_player = self.gs.get_player(self.gs.other(self.gs.focus_player))

            if focus_player.agent is None:
                passes += 1
                self.gs.focus_player = self.gs.other(self.gs.focus_player)
                continue

            action = focus_player.agent.decide_showdown_action(opponent_player, bf_idx)

            if action[0] == "PASS":
                passes += 1
                if self.verbose:
                    print(f"    {self.gs.focus_player} passes (passes={passes}/2)")
            else:
                kind, idx, lane = action[0], action[1], action[2] if len(action) > 2 else None
                if kind == "SPELL" and idx is not None and 0 <= idx < len(focus_player.hand):
                    card = focus_player.hand[idx]
                    if isinstance(card, SpellCard):
                        has_action_or_reaction = card.has_keyword("ACTION") or card.has_keyword("REACTION")
                        if has_action_or_reaction and focus_player.can_pay_cost(
                            card.cost_energy, card.cost_power, card.cost_power_domain
                        ):
                            if focus_player.pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                                focus_player.remove_from_hand(idx)
                                if self.verbose:
                                    print(f"    {self.gs.focus_player} plays SPELL in showdown: {card.name}")
                                self.gs.chain.append(ChainItem(player=self.gs.focus_player, card=card, bf_idx=bf_idx))
                                self._run_chain(self.gs.focus_player)
                                passes = 0

            self.gs.focus_player = self.gs.other(self.gs.focus_player)

        self.gs.showdown_active = False
        self.gs.showdown_bf_idx = None
        self.gs.focus_player = None

        # Resolve showdown outcome
        bf = self.gs.battlefields[bf_idx]
        if bf.units_A and bf.units_B:
            # Contested: run combat
            self._phase_combat_and_conquer_single(bf_idx, attacker)
        elif bf.units_A and not bf.units_B:
            # A controls
            if bf.can_score_conquer("A"):
                self.gs.points_A += 1
                bf.mark_scored("A")
                if self.verbose:
                    print(f"  [CONQUER] A conquers BF{bf_idx} (uncontested showdown) -> +1 VP")
                self._fire_scoring_trigger("on_conquer", bf, "A")
        elif bf.units_B and not bf.units_A:
            # B controls
            if bf.can_score_conquer("B"):
                self.gs.points_B += 1
                bf.mark_scored("B")
                if self.verbose:
                    print(f"  [CONQUER] B conquers BF{bf_idx} (uncontested showdown) -> +1 VP")
                self._fire_scoring_trigger("on_conquer", bf, "B")

    def _phase_combat_and_conquer_single(self, bf_idx: int, attacker: str) -> None:
        """Resolve combat for a single battlefield."""
        self._recompute_passives()
        bf = self.gs.battlefields[bf_idx]
        before_A = list(bf.units_A)
        before_B = list(bf.units_B)

        if self.verbose:
            mightA = sum(u.might for u in before_A if not u.stunned)
            mightB = sum(u.might for u in before_B if not u.stunned)
            namesA = ",".join(f"{u.card.name}({u.might})" for u in before_A) or "-"
            namesB = ",".join(f"{u.card.name}({u.might})" for u in before_B) or "-"
            print(
                f"  [COMBAT BF{bf_idx}] attacker={attacker} "
                f"A_might={mightA} [{namesA}] vs B_might={mightB} [{namesB}]"
            )

        # Attack/Defend triggers fire once, before damage, as designations are set.
        defender = self.gs.other(attacker)
        atk_actor, atk_opp = self.gs.get_player(attacker), self.gs.get_player(defender)
        for unit in list(bf.units_A if attacker == "A" else bf.units_B):
            self._resolve_triggered_effects(unit.card, "on_attack", bf, atk_actor, atk_opp,
                                            context_extra={"battlefield": bf})
        for unit in list(bf.units_A if defender == "A" else bf.units_B):
            self._resolve_triggered_effects(unit.card, "on_defend", bf, atk_opp, atk_actor,
                                            context_extra={"battlefield": bf})

        stats = bf.resolve_combat_might(attacker_side=attacker)

        if self.verbose:
            dead_A_names = ",".join(u.card.name for u in stats.dead_A) or "-"
            dead_B_names = ",".join(u.card.name for u in stats.dead_B) or "-"
            print(
                f"  [COMBAT RESULT BF{bf_idx}] "
                f"deaths A=[{dead_A_names}] B=[{dead_B_names}] "
                f"survivors A={len(bf.units_A)} B={len(bf.units_B)}"
            )

        # Route dead units (death replacements applied first), fire on_death etc.
        self._route_combat_deaths(stats, bf)

        if self.recorder:
            self._record_combat_deaths(bf, before_A, before_B)

        # on_win_combat: a side won if it still has units and the other doesn't.
        if bf.units_A and not bf.units_B:
            self._fire_units_trigger("on_win_combat", "A")
        elif bf.units_B and not bf.units_A:
            self._fire_units_trigger("on_win_combat", "B")

        if bf.can_score_conquer(attacker):
            if attacker == "A":
                self.gs.points_A += 1
            else:
                self.gs.points_B += 1
            bf.mark_scored(attacker)
            if self.verbose:
                print(f"  [CONQUER] {attacker} conquers BF{bf_idx} -> +1 VP")
            self._fire_scoring_trigger("on_conquer", bf, attacker)

    def _phase_showdown(self, active: str, opponent: str) -> None:
        pass  # Showdowns now trigger immediately when battlefield contested

    def _phase_combat_and_conquer(self, active: str) -> None:
        self._recompute_passives()

        for bf in self.gs.battlefields:
            before_A = list(bf.units_A)
            before_B = list(bf.units_B)
            if bf.contested_this_turn:
                bf_idx = self.gs.battlefields.index(bf)
                # Only log "real" combats — when both sides have units that can fight.
                real_combat = bool(before_A) and bool(before_B)
                if self.verbose and real_combat:
                    mightA = sum(u.might for u in before_A if not u.stunned)
                    mightB = sum(u.might for u in before_B if not u.stunned)
                    namesA = ",".join(f"{u.card.name}({u.might})" for u in before_A) or "-"
                    namesB = ",".join(f"{u.card.name}({u.might})" for u in before_B) or "-"
                    print(
                        f"  [COMBAT BF{bf_idx} end-of-turn] attacker={active} "
                        f"A_might={mightA} [{namesA}] vs B_might={mightB} [{namesB}]"
                    )
                stats = bf.resolve_combat_might(attacker_side=active)
                if self.verbose and real_combat:
                    dead_A_names = ",".join(u.card.name for u in stats.dead_A) or "-"
                    dead_B_names = ",".join(u.card.name for u in stats.dead_B) or "-"
                    print(
                        f"  [COMBAT RESULT BF{bf_idx}] "
                        f"deaths A=[{dead_A_names}] B=[{dead_B_names}] "
                        f"survivors A={len(bf.units_A)} B={len(bf.units_B)}"
                    )

                # Route dead units (death replacements applied first), fire on_death.
                self._route_combat_deaths(stats, bf)

                if self.recorder:
                    self._record_combat_deaths(bf, before_A, before_B)
                if bf.can_score_conquer(active):
                    if active == "A":
                        self.gs.points_A += 1
                    else:
                        self.gs.points_B += 1
                    bf.mark_scored(active)
                    if self.verbose:
                        print(f"  [CONQUER] {active} conquers BF{bf_idx} -> +1 VP")
                    self._fire_scoring_trigger("on_conquer", bf, active)


    # ====== MAIN LOOP ======

    def start(self) -> Result:
        gs = self.gs

        for _ in range(4):
            card_a = gs.A.draw()
            card_b = gs.B.draw()
            if self.recorder:
                if card_a:
                    self.recorder.record_draw("A", 0, card_a)
                if card_b:
                    self.recorder.record_draw("B", 0, card_b)

        # Per RAW: runes are channeled during each player's Beginning Phase Channel
        # Phase, not before turn 1. No initial-pool unlock. The "+1 extra on B's
        # first turn" rule (Channeling §430) is handled below in _phase_beginning.

        self._phase_mulligan()

        if self.recorder:
            self._snapshot_state(turn_override=0)

        while gs.turn <= gs.max_turns:
            if self.verbose:
                print(f"\n=== TURN {gs.turn} ({gs.active}'s turn) ===")

            # Reset per-turn counters for the condition evaluator.
            gs.cards_played_this_turn[gs.active] = 0
            gs.spells_played_this_turn[gs.active] = 0
            gs.friendly_unit_died_this_turn["A"] = False
            gs.friendly_unit_died_this_turn["B"] = False
            gs.discarded_this_turn["A"] = False
            gs.discarded_this_turn["B"] = False
            gs.cards_burned_this_turn["A"] = 0
            gs.cards_burned_this_turn["B"] = 0

            gained = self._phase_beginning(gs.active)
            if gained:
                if gs.active == "A":
                    gs.points_A += gained
                else:
                    gs.points_B += gained
                if gs.points_A >= gs.victory_score:
                    if self.recorder:
                        self._snapshot_state()
                    return Result("A", gs.turn, self.units_played, self.spells_cast)
                if gs.points_B >= gs.victory_score:
                    if self.recorder:
                        self._snapshot_state()
                    return Result("B", gs.turn, self.units_played, self.spells_cast)


            self._fire_turn_trigger("on_start_of_turn", gs.active)
            self._recompute_passives()

            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))
            self._phase_draw(ap)

            # Multi-action turn loop
            cards_played_this_turn = 0
            actions_this_turn = 0
            while True:
                if ap.agent is None:
                    act: Action = ("PASS", None, None)
                else:
                    act = ap.agent.decide_action(op, cards_played=cards_played_this_turn)
                if act[0] == "PASS":
                    if self.verbose:
                        print(f"  {ap.name} passes")
                    break
                # No-op guard: if an action leaves the game state unchanged it can
                # never be "used up", so an agent that keeps proposing it (e.g. a
                # MOVE the engine silently refuses) would loop forever. Treat an
                # action that makes no progress as an implicit PASS. The absolute
                # cap is a belt-and-suspenders bound; real turns play far fewer.
                before = self._action_fingerprint(ap, op)
                self._apply_action(ap, act, cards_played_this_turn=cards_played_this_turn)
                self._recompute_passives()
                actions_this_turn += 1
                if self._action_fingerprint(ap, op) == before:
                    if self.verbose:
                        print(f"  {ap.name} no-op action {act} — ending action phase")
                    break
                if actions_this_turn > 200:
                    if self.verbose:
                        print(f"  {ap.name} hit action cap — ending action phase")
                    break
                cards_played_this_turn += 1
                gs.cards_played_this_turn[gs.active] = cards_played_this_turn

            self._phase_showdown(gs.active, gs.other(gs.active))

            self._phase_combat_and_conquer(gs.active)
            if gs.points_A >= gs.victory_score:
                if self.recorder:
                    self._snapshot_state()
                return Result("A", gs.turn, self.units_played, self.spells_cast)
            if gs.points_B >= gs.victory_score:
                if self.recorder:
                    self._snapshot_state()
                return Result("B", gs.turn, self.units_played, self.spells_cast)


            self._fire_turn_trigger("on_end_of_turn", gs.active)

            # Clear temporary might bonuses (REACTION spells like Discipline)
            for bf in self.gs.battlefields:
                for unit in bf.units_A + bf.units_B:
                    unit.clear_turn_end_bonuses()

            if self.verbose:
                bf0 = gs.battlefields[0]
                bf1 = gs.battlefields[1]
                print(f"  [END TURN] Board: BF0={len(bf0.units_A)}A vs {len(bf0.units_B)}B ({bf0.controller() or '?'}) | BF1={len(bf1.units_A)}A vs {len(bf1.units_B)}B ({bf1.controller() or '?'}) | Points: A={gs.points_A} B={gs.points_B}")

            gs.active = gs.other(gs.active)
            gs.turn += 1
            if self.recorder:
                self._snapshot_state()

        if gs.points_A > gs.points_B:
            winner = "A"
        elif gs.points_B > gs.points_A:
            winner = "B"
        else:
            winner = "DRAW"
        if self.recorder:
            self._snapshot_state()
        return Result(winner, gs.turn - 1, self.units_played, self.spells_cast)

    def _snapshot_state(self, *, turn_override: Optional[int] = None) -> None:
        if not self.recorder:
            return

        turn_number = turn_override if turn_override is not None else self.gs.turn
        for idx, bf in enumerate(self.gs.battlefields):
            self.recorder.record_board(
                turn_number,
                idx,
                bf.units_A,
                bf.units_B,
                controller=bf.controller(),
                contested=bf.contested_this_turn,
                points_a=self.gs.points_A,
                points_b=self.gs.points_B,
            )

        self.recorder.record_hand("A", turn_number, self.gs.A.hand)
        self.recorder.record_hand("B", turn_number, self.gs.B.hand)

    def _record_spell_deaths(
        self,
        battlefield: Battlefield,
        before_a: list[UnitInPlay],
        before_b: list[UnitInPlay],
    ) -> None:
        if not self.recorder:
            return

        self._record_unit_diffs(
            before_a,
            battlefield.units_A,
            owner="A",
            battlefield_index=self.gs.battlefields.index(battlefield),
            cause="spell",
        )
        self._record_unit_diffs(
            before_b,
            battlefield.units_B,
            owner="B",
            battlefield_index=self.gs.battlefields.index(battlefield),
            cause="spell",
        )

    def _record_combat_deaths(
        self,
        battlefield: Battlefield,
        before_a: list[UnitInPlay],
        before_b: list[UnitInPlay],
    ) -> None:
        if not self.recorder:
            return

        index = self.gs.battlefields.index(battlefield)
        self._record_unit_diffs(
            before_a,
            battlefield.units_A,
            owner="A",
            battlefield_index=index,
            cause="combat",
        )
        self._record_unit_diffs(
            before_b,
            battlefield.units_B,
            owner="B",
            battlefield_index=index,
            cause="combat",
        )

    def _record_unit_diffs(
        self,
        before: list[UnitInPlay],
        after: list[UnitInPlay],
        *,
        owner: str,
        battlefield_index: int,
        cause: str,
    ) -> None:
        if not self.recorder:
            return

        remaining = {getattr(unit.card, "uuid", None) for unit in after}
        for unit in before:
            uuid = getattr(unit.card, "uuid", None)
            if uuid not in remaining:
                self.recorder.record_play(
                    owner,
                    self.gs.turn,
                    unit.card,
                    action="DEATH",
                    battlefield_index=battlefield_index,
                    result=cause,
                )
