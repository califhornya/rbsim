from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Tuple, TYPE_CHECKING, Iterable

from .state import GameState, ChainItem
from .cards import Card, GearCard, SpellCard, UnitCard, LegendCard
from .combat import UnitInPlay, kill_order
from .player import Player
from .battlefield import Battlefield, DeployedGear, FacedownCard
from riftbound.registry.cards_registry import CARD_REGISTRY, EffectSpec
from .effects import REGISTRY as EFFECT_REGISTRY
from .effects import _amount as _effect_amount
from .effects import _passes_filter as _effect_passes_filter
from .enums import Domain
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
    "on_exhaust", "on_friendly_exhaust", "on_hide_here", "on_stun_enemy",
    "on_card_played", "on_unit_moves_from_here", "on_enemy_unit_played",
    "on_chosen", "on_readied", "cost_aura", "enter_ready_aura", "on_hide",
    "on_buffed", "on_enemy_unit_moves", "on_stunned_enemy_dies_here",
    "on_friendly_unit_readied", "on_friendly_unit_buffed", "on_friendly_attack",
    "on_friendly_defend", "on_second_draw", "on_opponent_scores",
    "on_enemy_unit_died", "on_discarded", "on_friendly_chosen", "on_gear_ability_used",
    "on_combat_start_here", "on_equipment_attached", "on_friendly_empowered", "on_banish_own",
    "on_become_empowered", "on_you_discard",
    "on_unit_played_here", "on_self_played", "trash_on_card_played", "on_enemy_gear_played",
    "on_enemy_might_reduced", "on_recycle", "on_three_exhausted", "on_friendly_gear_died_at_bf",
    "trash_on_spell_kill", "on_friendly_deploy", "granted_to_legend",
    "on_friendly_moves_from_here", "on_attached",
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
    "friendly_total_might_at_least", "you_control_n_or_more_gear",
    "showed_off", "opponent_controls_a_battlefield", "you_control_no_other_units",
    "card_with_my_name_in_trash", "opponent_controls_stunned_unit",
    "you_control_this_battlefield",
    "cards_in_hand_at_most", "first_turn_of_player", "rune_deck_empty",
    "enemy_alone_here", "one_on_one_here", "you_control_bf_with_exactly_n_units",
    "you_have_n_or_fewer_runes", "friendly_deployed_gear_here",
    "this_is_at_battlefield", "triggering_unit_not_named", "triggering_unit_has_subtype",
    "fewer_runes_than_opponent",
    "cards_played_this_turn_exactly", "opponent_played_n_spells_this_turn",
    "triggering_card_matches", "triggering_card_not_from_hand",
    "moved_to_battlefield", "moved_from_battlefield",
    "all_of", "died_alone", "enemy_choices_this_turn_at_least",
    "not_your_turn", "triggering_card_from_zone", "played_to_controlled_battlefield",
    "units_in_base_at_least", "ready_enemy_here", "moves_this_turn_exactly",
    "moved_to_other_battlefield", "gained_xp_this_turn", "power_spent_this_turn_at_least",
    "triggering_unit_alone", "triggering_unit_buffed", "in_showdown",
    "died_mighty", "units_here_exactly", "triggering_unit_stunned", "died_here",
    "triggering_unit_mightiest", "controller_has_facedown_card",
    "cards_in_hand_exactly", "units_at_battlefields_exactly", "not", "friendly_gear_here",
    "excess_damage_at_least", "facedown_card_here", "played_unit_gear_spell_this_turn",
    "in_beginning_phase", "triggering_unit_here", "has_all_pet_tags", "signpost_possible",
    "holder_didnt_conquer_this_turn", "conquered_uncontrolled", "your_legend_exhausted",
    # safe-False branch (loop.py:612-614)
    "target_was_stunned",
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
    # The trigger's context (triggering_card, moved_from, ...), for handlers.
    extra: dict = field(default_factory=dict)

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
        if key == "chosen_player":
            # "Choose a player. They BURN 1" (Blade Twirler): either one;
            # baseline the opponent.
            return self.loop.choose("player", self.actor_side, [self.opponent, self.actor],
                                    self.opponent, self.card)
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

        # Battlefield that adds bonus damage to units here (e.g. Void Gate). This
        # handler only ever damages units AT self.battlefield, so the bonus never
        # touches player/base-face damage. Covers spells and abilities alike (both
        # route through here).
        amount += self.loop._bf_passive_amount(self.battlefield, "bonus_damage_here")

        _, dead = self.battlefield.apply_spell_damage(
            target_side, amount,
            take=lambda u, a: self.loop._take_damage(u, a, "spell", self.actor_side, self.card))

        # Spell-killed units die like any other (replacements, DEATHKNELL, ...).
        self.loop._route_deaths([(u, target_side) for u in dead], self.battlefield)

        if self.loop.recorder:
            self.loop._record_spell_deaths(self.battlefield, before_a, before_b)

    def damage_units(self, units: list, amount: int) -> None:
        """Deal `amount` to each of these units, wherever they are (plus a
        battlefield's bonus damage there); the ones it kills die together per
        battlefield (replacements, DEATHKNELL, ...)."""
        from .combat import _is_dead
        if amount <= 0:
            return
        dead_at: dict = {}   # id(bf or base marker) -> (bf, [(unit, side)])
        for unit in units:
            where = self.loop._locate_unit(unit)
            if where is None:
                continue
            side, bf = where
            unit.damage += self.loop._take_damage(
                unit, amount + self.loop._bf_passive_amount(bf, "bonus_damage_here"),
                "spell", self.actor_side, self.card)
            if _is_dead(unit):
                if bf is None:
                    self.loop.gs.get_player(side).base_units.remove(unit)
                else:
                    bf.remove_unit(side, unit)
                dead_at.setdefault(id(bf), (bf, []))[1].append((unit, side))
        for bf, dead in dead_at.values():
            self.loop._route_deaths(dead, bf or self.loop.gs.battlefields[0], in_base=bf is None,
                                    killer=(self.actor_side, self.card))

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

        # On the unit in play, not its card (the card's printed Might would
        # otherwise follow it to every zone).
        for unit in iterable:
            unit.aura_might += amount

    def draw_cards(self, count: int, *, target: str = "actor", source: str = "effect") -> None:
        if count <= 0:
            return

        player = self._player_for_target(target)
        for _ in range(count):
            card = self.loop._draw_one(player)   # Burn Out (§418) when deck empties
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

    def reveal_top_draw_if_spell(self, *, target: str = "actor") -> None:
        """Reveal the top card of the target's Main Deck; if it's a Spell, draw it
        (Diana Lunari). Top of deck = end of the cards list."""
        player = self._player_for_target(target)
        if not player.deck.cards:
            return
        top = player.deck.cards[-1]
        if isinstance(top, SpellCard):
            player.draw()

    def add_earmarked_energy(self, amount: int, *, target: str = "actor") -> None:
        """Add energy usable only during showdowns (Diana Scorn, §earmark)."""
        if amount == 0:
            return
        self._player_for_target(target).earmarked_energy_showdown += amount

    def add_earmarked_power(self, amount: int, *, target: str = "actor", use: str = "gear") -> None:
        """Add generic power usable only to play/use gear (Ornn, §earmark), or
        with use="spell" only to play spells (Kai'Sa)."""
        if amount == 0:
            return
        player = self._player_for_target(target)
        if use == "spell":
            player.earmarked_power_spell += amount
        elif use == "unit_or_gear":
            player.earmarked_power_permanent += amount     # Mordekaiser Iron Revenant
        else:
            player.earmarked_power_gear += amount

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
            if self.loop._can_ready(unit):
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

# Bound on priority rounds in one showdown or chain (like the 200 actions of a
# main phase): real ones take a handful.
_PRIORITY_ROUNDS_CAP = 200


class GameLoop:
    """Core turn structure, extended with Might combat, rune channeling and movement."""

    def __init__(self, gs: GameState, recorder: Optional["GameRecorder"] = None, verbose: bool = False):
        self.gs = gs
        self.units_played = 0
        self.spells_cast = 0
        self.recorder = recorder
        self.verbose = verbose
        # Sees (and may replace) every choice the engine makes for a player:
        # see `choose`. None: the baseline policies decide.
        self.chooser = None

        if hasattr(gs.A, "agent") and gs.A.agent:
            gs.A.agent.player.battlefields = gs.battlefields
            gs.A.agent.gs = gs
            gs.A.agent.loop = self
        if hasattr(gs.B, "agent") and gs.B.agent:
            gs.B.agent.player.battlefields = gs.battlefields
            gs.B.agent.gs = gs
            gs.B.agent.loop = self

    def choose(self, kind: str, side: str, options: list, pick, source=None):
        """`side` makes a choice the rules give a player (a target, a mode, a "you
        may", which unit an Equipment goes on...) that the engine makes with a
        fixed baseline policy. `options` are the legal choices and `pick` the
        baseline's (one of them, by identity). Returns `pick`, or the option a
        `chooser` returns the index of: chooser(loop, kind, side, options,
        default_index, source) -> int | None (None keeps the baseline's)."""
        if self.chooser is None or not options:
            return pick
        default = next((i for i, o in enumerate(options) if o is pick), 0)
        i = self.chooser(self, kind, side, options, default, source)
        return pick if i is None else options[i]

    def choose_many(self, kind: str, side: str, options: list, picks: list, source=None) -> list:
        """`choose` for "up to N" picks: one choice per pick, in the baseline's
        order, each among the options not taken yet."""
        if self.chooser is None:
            return picks
        order = list(picks) + [o for o in options if not any(o is p for p in picks)]
        out: list = []
        for _ in picks:
            left = [o for o in order if not any(o is t for t in out)]
            out.append(self.choose(kind, side, left, left[0], source))
        return out

    # ====== PHASE HELPERS ======

    def _phase_mulligan(self) -> None:
        for player in [self.gs.A, self.gs.B]:
            if player.agent is None:
                continue
            indices_to_return = player.agent.decide_mulligan()
            # Mulligan resolution lives on Player (Core Rules §117: up to two cards,
            # draw replacements from the top, then recycle the set-aside cards to
            # the bottom). Shared with the search agent's mulligan rollouts.
            player.mulligan(indices_to_return or [], self.gs.rng)

    def _ready_active_units(self, active: str) -> None:
        player = self.gs.get_player(active)
        exhausted = [u for u in player.base_units if not u.ready]
        exhausted += [u for bf in self.gs.battlefields for u in bf._units_for(active) if not u.ready]
        player.ready_base_units()
        for bf in self.gs.battlefields:
            bf.ready_side(active)
        for unit in exhausted:
            if unit.cant_ready:
                unit.ready = False       # "I can't be readied" (Maduli)
                continue
            self._fire_readied(unit, active)
        legend_unit = self._legend_unit(active)
        if legend_unit is not None:
            legend_unit.ready = True
        # Untap the player's gear (base + attached) so its [tap] abilities recharge.
        for g in player.base_gear:
            g.tapped = False
        for u in player.base_units:
            for g in u.gear:
                g.tapped = False
        for bf in self.gs.battlefields:
            for u in (bf.units_A if active == "A" else bf.units_B):
                for g in u.gear:
                    g.tapped = False

    def _phase_beginning(self, active: str) -> int:
        self.gs.in_beginning_phase = True
        try:
            return self._phase_beginning_steps(active)
        finally:
            self.gs.in_beginning_phase = False

    def _phase_beginning_steps(self, active: str) -> int:
        for bf in self.gs.battlefields:
            bf.begin_turn_reset()

        # TEMPORARY units die at the start of their controller's Beginning Phase
        # (at battlefields and in base): DEATHKNELL, "when a friendly unit dies".
        player = self.gs.get_player(active)
        for bf in self.gs.battlefields:
            units = bf.units_A if active == "A" else bf.units_B
            if any(self._has_effect(u.card, "no_temporary_here") for u in units):
                continue     # "Your TEMPORARY effects at my battlefield don't trigger"
            dead = [u for u in units if u.has_keyword("TEMPORARY")]
            for u in dead:
                units.remove(u)
            if dead:
                self._route_deaths([(u, active) for u in dead], bf)
        dead = [u for u in player.base_units if u.has_keyword("TEMPORARY")]
        for u in dead:
            player.base_units.remove(u)
        if dead:
            self._route_deaths([(u, active) for u in dead], self.gs.battlefields[0])

        # Remove unattached TEMPORARY gear at base (§742.1.b; e.g. Spinning Axe:
        # "if unattached, kill it at the start of its controller's Beginning
        # Phase"). Attached gear rides its host unit and is left alone.
        actor = self.gs.get_player(active)
        temp_gear = [g for g in actor.base_gear if g.has_keyword("TEMPORARY")]
        for g in temp_gear:
            self._remove_gear(g, actor)       # killed: its DEATHKNELL (Sprite Fountain)
        # Gear an effect gave TEMPORARY (Turn to Dust: "Kill it at the start of
        # its controller's Beginning Phase"), attached or not.
        for g in [g for g in actor.base_gear + self._controlled_attached_gear(active)
                  if getattr(g, "_temporary", False)]:
            g._temporary = False
            self._remove_gear(g, actor)

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
        active_player.floating_power.clear()
        active_player.earmarked_energy_showdown = 0
        active_player.earmarked_power_gear = 0
        active_player.earmarked_power_spell = 0
        active_player.earmarked_power_permanent = 0
        active_player.earmarked_energy_spell = 0

        # Channel Phase (§430): channel 2 runes from the rune deck. The player who
        # goes second channels one extra rune on their first turn. Turn 2 is always
        # the second player's first turn (turn 1 = starter, active flips each turn),
        # so this works regardless of which side starts the game.
        channel_count = 2
        if self.gs.turn == 2:
            channel_count = 3
        if any(self._units_at_battlefields_with(s, "channel_only_one") for s in ("A", "B")):
            channel_count = 1     # Sandstone Chimera
        active_player.unlock_runes(channel_count)
        self._extra_channel(active)
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
                vps += self._points_allowed(active, 1, "hold", bf)
                bf.mark_scored(active)
                if self.verbose:
                    bf_idx = self.gs.battlefields.index(bf)
                    print(f"  [HOLD] {active} holds BF{bf_idx} -> +1 VP")
                # DEPLOY (§830): "When an opponent holds here, kill this."
                other = self.gs.other(active)
                self._kill_deployed_gear(bf, other, list(bf.gear_for(other)))
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
                # Its Equipment ("At the end of your turn, ... deal 4 to me").
                for g in list(unit.gear):
                    self._resolve_triggered_effects(g, trigger, bf, actor, opponent,
                                                    context_extra={"battlefield": bf,
                                                                   "triggering_unit": unit})
        # Base units (use battlefield[0] as a neutral context anchor).
        anchor = self.gs.battlefields[0]
        for unit in list(actor.base_units):
            self._resolve_triggered_effects(unit.card, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor})
        # The player's Legend (e.g. Jinx Loose Cannon: draw at the start of turn).
        legend_unit = self._legend_unit(side)
        if legend_unit is not None:
            self._resolve_triggered_effects(legend_unit.card, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor})
        # Unattached gear ("At the end of your turn, ...": Dazzling Aurora).
        for g in list(actor.base_gear):
            self._resolve_triggered_effects(g, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor})
        # Deployed gear's turn triggers ("at the end of your turn, if you control
        # this battlefield ..."), with their battlefield as "here".
        for bf in self.gs.battlefields:
            self._fire_deployed_gear_trigger(trigger, bf, side)
        # Battlefields' own turn triggers (e.g. Frozen Fortress: deal 1 to all
        # units here at start of turn). Fire once per battlefield, on the active
        # player's start/end of turn.
        for bf in self.gs.battlefields:
            if bf.card is not None:
                self._resolve_triggered_effects(bf.card, trigger, bf, actor, opponent,
                                                context_extra={"battlefield": bf})

    def _fire_scoring_trigger(self, trigger: str, bf: Battlefield, side: str) -> None:
        """Fire on_conquer / on_hold for the scoring player's units at this BF
        (plus their deployed champion). Also grants HUNT XP."""
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        if trigger == "on_conquer":
            self.gs.conquered_this_turn[side] = self.gs.conquered_this_turn.get(side, 0) + 1
            bf.conquered_turn[side] = self.gs.turn
        elif trigger == "on_hold":
            self.gs.hold_points_this_turn[side] = self.gs.hold_points_this_turn.get(side, 0) + 1
        units = list(bf.units_A if side == "A" else bf.units_B)
        for unit in units:
            # HUNT keyword grants XP on Conquer or Hold.
            if unit.has_keyword("HUNT"):
                amount = unit.keyword_value("HUNT") or 1
                self.gs.add_xp(side, amount)
                if self.verbose:
                    print(f"  [HUNT] {side} gains {amount} XP (now {self.gs.get_xp(side)})")
            if trigger == "on_conquer":
                unit.conquered_turn = self.gs.turn
            triggers = [trigger]
            if any(self._has_effect(g, "hold_conquer_swap") for g in unit.gear):
                # "My hold effects are also conquer effects, and vice versa"
                # (Skyfall of Areion).
                triggers.append("on_hold" if trigger == "on_conquer" else "on_conquer")
            for trig in triggers:
                for card in [unit.card] + list(unit.gear):
                    self._resolve_triggered_effects(
                        card, trig, bf, actor, opponent,
                        context_extra={"battlefield": bf},
                    )
        if trigger == "on_hold":
            # Ashe Focused: "When they hold, return it to their hand".
            back = [c for s, c in self.gs.held_hostage if s == side]
            self.gs.held_hostage = [(s, c) for s, c in self.gs.held_hostage if s != side]
            for c in back:
                if c in actor.banished:
                    actor.banished.remove(c)
                    actor.hand.append(c)
        # The scoring player's Legend ("When you conquer, ready me": Sett).
        legend_unit = self._legend_unit(side)
        if legend_unit is not None:
            self._resolve_triggered_effects(legend_unit.card, trigger, bf, actor, opponent,
                                            context_extra={"battlefield": bf})
        # "When an opponent scores, ..." (Sumpworks Map).
        self._fire_units_trigger("on_opponent_scores", self.gs.other(side))
        # The scoring player's deployed gear here ("when you hold here ...").
        self._fire_deployed_gear_trigger(trigger, bf, side)
        # The battlefield's OWN triggered ability (e.g. "when you conquer here,
        # draw 1") fires for the scoring player.
        if bf.card is not None:
            self._resolve_triggered_effects(
                bf.card, trigger, bf, actor, opponent,
                context_extra={"battlefield": bf},
            )

    def _exhaust(self, unit) -> None:
        """Exhaust a unit. A ready → exhausted change fires its "when I become
        exhausted" (on_exhaust) abilities for its controller."""
        if not unit.ready:
            return
        unit.ready = False
        for side in ("A", "B"):
            actor = self.gs.get_player(side)
            bf = next((b for b in self.gs.battlefields
                       if unit in (b.units_A if side == "A" else b.units_B)), None)
            if bf is None and unit not in actor.base_units and unit is not self._legend_unit(side):
                continue
            bf = bf or self.gs.battlefields[0]
            self._resolve_triggered_effects(unit.card, "on_exhaust", bf, actor,
                                            self.gs.get_player(self.gs.other(side)),
                                            context_extra={"battlefield": bf})
            self._fire_units_trigger("on_friendly_exhaust", side, exclude_card=unit.card)
            return

    def _fire_stun_enemy(self, side: str, at=None) -> None:
        """`side` stunned one or more enemy units: fire on_stun_enemy for its units
        and its Legend; `at` is where (a battlefield, or None for base)."""
        self._fire_units_trigger("on_stun_enemy", side, extra={"stunned_at": at})

    def _exhaust_gear(self, gear, actor: Player) -> None:
        """Tap a gear for its [tap] ability; fires its on_exhaust abilities."""
        if getattr(gear, "tapped", False):
            return
        gear.tapped = True
        side = "A" if actor is self.gs.A else "B"
        anchor = self.gs.battlefields[0]
        self._resolve_triggered_effects(gear, "on_exhaust", anchor, actor,
                                        self.gs.get_player(self.gs.other(side)),
                                        context_extra={"battlefield": anchor})

    @staticmethod
    def _disarm_value(unit) -> int:
        """Total DISARM X on a unit (§831): a bare keyword counts 1 and every
        instance adds up (printed + granted). Granted copies live in a set, so two
        identical grants ("Your Mechs have DISARM" twice) still count once."""
        total = unit.card.keyword_value("DISARM")
        for k in unit.passive_keywords:
            ku = k.upper()
            if ku == "DISARM":
                total += 1
            elif ku.startswith("DISARM "):
                try:
                    total += int(ku[len("DISARM"):].strip())
                except ValueError:
                    total += 1
        return total

    def _apply_disarm(self, unit, bf: Battlefield, defender: str) -> None:
        """DISARM X (§831): when this unit attacks, give an enemy unit here -X Might
        this turn. Baseline policy: the enemy with the highest Might."""
        x = self._disarm_value(unit)
        enemies = bf.units_A if defender == "A" else bf.units_B
        if x <= 0 or not enemies:
            return
        target = self.choose("disarm", self.gs.other(defender), list(enemies),
                             max(enemies, key=lambda u: u.might), unit.card)
        target.temporary_might -= x
        self._fire_might_reduced(target, self.gs.other(defender))
        if self.verbose:
            print(f"  [DISARM] {unit.card.name} gives {target.card.name} -{x} might")

    def _return_borrowed_units(self) -> None:
        """Hostile Takeover: "Lose control of that unit and recall it at end of
        turn" — to its owner's base."""
        for side in ("A", "B"):
            for unit in self._friendly_units_of(side):
                if unit.borrowed is None or unit.borrowed[1] != self.gs.turn:
                    continue
                owner = unit.borrowed[0]
                unit.borrowed = None
                where = self._locate_unit(unit)
                if where[1] is None:
                    self.gs.get_player(side).base_units.remove(unit)
                else:
                    where[1].remove_unit(side, unit)
                self.gs.get_player(owner).base_units.append(unit)

    def _take_control(self, unit: UnitInPlay, new_side: str) -> Optional[Battlefield]:
        """`new_side` takes control of `unit` where it is; returns its battlefield."""
        where = self._locate_unit(unit)
        if where is None:
            return None
        old, bf = where
        if bf is None:
            self.gs.get_player(old).base_units.remove(unit)
            self.gs.get_player(new_side).base_units.append(unit)
        else:
            bf.remove_unit(old, unit)
            bf.add_unit(new_side, unit)
        return bf

    def _extra_channel(self, side: str) -> None:
        """ "If you would channel runes, channel that many runes plus 1 exhausted
        rune instead" (Seraphic Wyvern), per Wyvern."""
        n = sum(1 for src, _ in self._sources_in_play(side) if self._has_effect(src, "channel_plus_one"))
        if n:
            self.gs.get_player(side).unlock_runes(n, exhausted=True)

    def _fire_might_reduced(self, unit: UnitInPlay, by_side: str) -> None:
        """`by_side` reduced an enemy unit's Might: "When you reduce the Might of
        an enemy unit here" (Ahri Confident)."""
        where = self._locate_unit(unit)
        if where is None or where[0] == by_side:
            return
        self._fire_units_trigger("on_enemy_might_reduced", by_side, triggering_card=unit.card,
                                 extra={"triggering_unit": unit, "died_at": where[1]})

    def _show_off(self, card, actor: Player) -> None:
        """SHOW OFF [Object] (§832): as the card is played, the player may reveal a
        matching card from hand or pick another matching friendly object on the
        board. Records `card._showed_off` and snapshots the object's info in
        `card._shown` (§832.1.c), read by the `showed_off` condition and the
        shown_* amount sources. The object comes from the card's `show_off`
        marker spec (its target_filter); without one, any card qualifies.
        Baseline policy: show off whenever possible, picking the object with the
        highest Might, then Power cost, then Energy cost."""
        card._showed_off = False
        card._shown = None
        if not card.has_keyword("SHOW OFF"):
            return
        spec = CARD_REGISTRY.get(card.name)
        marker = next((es for es in (spec.effects if spec else ()) if es.effect == "show_off"), None)
        tf = (marker.target_filter if marker else None) or {}

        side = "A" if actor is self.gs.A else "B"
        candidates = []  # (object card, current Might)
        for c in actor.hand:
            if c is not card:
                candidates.append((c, int(getattr(c, "might", 0) or 0)))
        units = [u for bf in self.gs.battlefields
                 for u in (bf.units_A if side == "A" else bf.units_B)]
        units += actor.base_units
        for u in units:
            if u.card is not card:
                candidates.append((u.card, u.might))
            candidates.extend((g, 0) for g in u.gear)
        candidates.extend((g, 0) for g in actor.base_gear if g is not card)
        for bf in self.gs.battlefields:
            candidates.extend((dg.card, 0) for dg in bf.gear_for(side) if dg.card is not card)
        candidates = [(c, m) for (c, m) in candidates if self._show_off_matches(c, tf)]
        if not candidates or not self._wants_optional_keyword(actor, card, "SHOW OFF"):
            return
        obj, might = self.choose("show_off", side, candidates, max(candidates, key=lambda cm: (
            cm[1], int(getattr(cm[0], "cost_power", 0) or 0),
            int(getattr(cm[0], "cost_energy", 0) or 0))), card)
        card._showed_off = True
        card._shown = {
            "might": might,
            "power_cost": int(getattr(obj, "cost_power", 0) or 0),
            "energy_cost": int(getattr(obj, "cost_energy", 0) or 0),
        }
        if self.verbose:
            print(f"  [SHOW OFF] {card.name} shows off {obj.name}")

    @staticmethod
    def _show_off_matches(obj, tf) -> bool:
        from .effects import _zone_card_matches
        if not _zone_card_matches(obj, tf):
            return False
        if "has_keyword" in tf:
            # Token units carry a CardSpec (no has_keyword), so read keywords directly.
            kw = str(tf["has_keyword"]).upper()
            kws = [k.upper() for k in getattr(obj, "keywords", ())]
            if not any(k == kw or k.startswith(kw + " ") for k in kws):
                return False
        energy = int(getattr(obj, "cost_energy", 0) or 0)
        if "energy_at_least" in tf and energy < int(tf["energy_at_least"]):
            return False
        if "energy_at_most" in tf and energy > int(tf["energy_at_most"]):
            return False
        return True

    # --- DEPLOY gear (§830) -------------------------------------------------

    def _deploy_gear(self, side: str, bf: Battlefield, card, *, is_token: bool = False) -> None:
        """Put a gear onto a battlefield under `side`'s control (DEPLOY §830.1.a).
        Deployed gear stay there through cleanup (§830.1.b) until killed or moved."""
        bf.gear_for(side).append(DeployedGear(card=card, is_token=is_token))
        if self.verbose:
            bf_idx = self.gs.battlefields.index(bf)
            print(f"  [DEPLOY] {side} deploys {card.name} at BF{bf_idx}")
        self._recompute_passives()

    def _kill_deployed_gear(self, bf: Battlefield, side: str, dead: list) -> None:
        """Kill some of `side`'s deployed gear at `bf` simultaneously, then fire each
        one's DEATHKNELL (on_death) with this battlefield as "here". Non-token gear
        go to the trash; tokens (Bombs) cease to exist."""
        gear = bf.gear_for(side)
        dead = [dg for dg in dead if dg in gear]
        if not dead:
            return
        owner = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        for dg in dead:
            gear.remove(dg)
            if not dg.is_token:
                owner.trash.append(dg.card)
            if self.verbose:
                bf_idx = self.gs.battlefields.index(bf)
                print(f"  [DEPLOY] {side}'s {dg.card.name} at BF{bf_idx} dies")
        for dg in dead:
            self._resolve_triggered_effects(dg.card, "on_death", bf, owner, opponent,
                                            context_extra={"battlefield": bf})
            if not dg.is_token:
                self._fire_units_trigger("on_friendly_gear_died_at_bf", side, triggering_card=dg.card)
        self._recompute_passives()

    def _fire_deployed_gear_trigger(self, trigger: str, bf: Battlefield, side: str) -> None:
        """Fire a trigger for `side`'s deployed gear at `bf`."""
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        for dg in list(bf.gear_for(side)):
            self._resolve_triggered_effects(dg.card, trigger, bf, actor, opponent,
                                            context_extra={"battlefield": bf})

    def _draw_one(self, player: Player):
        """Draw one card, applying Burn Out (§418) when the Main Deck is empty:
        draw what's possible, recycle the trash into the deck (randomized), an
        opponent gains 1 point, then complete the draw. Returns the card, or None
        only when both deck AND trash are empty (a fully decked-out player still
        hands the opponent a point — the deck-out loss vector)."""
        card = player.draw()
        if card is None:
            self._burn_out(player)
            card = player.draw()
        if card is not None:
            self._zero_point_overflow(player)
            player.draws_this_turn += 1
            if player.draws_this_turn == 2:
                # "When you draw your second card each turn" (Frigid Jewel).
                self._fire_units_trigger("on_second_draw", "A" if player is self.gs.A else "B")
        return card

    def _zero_point_overflow(self, player: Player) -> None:
        """ "When you draw 1 or more cards with 9 or more other cards in your hand,
        discard your hand, kill this, and choose an opponent. They score 1
        point." (Zero Point Inflection)"""
        zpi = next((g for g in player.base_gear if self._has_effect(g, "zero_point_overflow")), None)
        if zpi is None or len(player.hand) - 1 < 9:
            return
        for c in list(player.hand):
            self._discard(player, c)
        self._remove_gear(zpi, player)
        side = "A" if player is self.gs.A else "B"
        self._gain_points(self.gs.other(side), 1, "effect")

    def _burn_out(self, player: Player) -> None:
        # §418.2.b: recycle trash into the Main Deck, randomizing (reminder note).
        if player.trash:
            player.deck.cards.extend(player.trash)
            player.trash.clear()
            self.gs.rng.shuffle(player.deck.cards)
        # §418.2.c: an opponent gains 1 point (2-player: the other player).
        side = "A" if player is self.gs.A else "B"
        self._gain_points(self.gs.other(side), 1, "burn_out")
        if self.verbose:
            print(f"  {player.name} BURNS OUT (§418): opponent +1 point, trash recycled")

    def _phase_draw(self, ap: Player) -> None:
        card = self._draw_one(ap)
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
        if (card.has_keyword("REPEAT") or getattr(card, "_granted_repeat", False)) \
                and getattr(card, "_repeat_paid", False):
            runs = 2

        try:
            for _ in range(runs):
                for effect_spec in play_specs:
                    # Asked once the condition holds: a "you may" that can't
                    # happen is no choice.
                    if not self._check_condition(effect_spec.condition, card, actor, opponent, None):
                        continue
                    if not self._wants_optional(actor, card, effect_spec):
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
            card._showed_off = False
            card._shown = None

    def _wants_optional(self, actor: Player, card: Card, es: "EffectSpec") -> bool:
        """Gate an optional ("you may ...") effect through the actor's agent. A
        non-optional effect always runs. When the actor has no agent (rollouts,
        tests) or the agent doesn't implement decide_optional, default to yes,
        preserving the engine's historical always-resolve behavior."""
        if not getattr(es, "optional", False):
            return True
        agent = getattr(actor, "agent", None)
        yes = True
        if agent is not None and hasattr(agent, "decide_optional"):
            yes = bool(agent.decide_optional(card, es.effect))
        side = "A" if actor is self.gs.A else "B"
        return self.choose(f"optional:{es.effect}", side, [True, False], yes, card)

    def _wants_optional_keyword(self, actor: Player, card: Card, name: str) -> bool:
        """Gate an optional KEYWORD choice (e.g. Accelerate §731.2 "you may pay")
        through the actor's agent. Same default-yes semantics as `_wants_optional`
        (no agent / no `decide_optional` → yes), so heuristic and rollout play is
        unchanged while a learning agent gets the decision."""
        agent = getattr(actor, "agent", None)
        yes = True
        if agent is not None and hasattr(agent, "decide_optional"):
            yes = bool(agent.decide_optional(card, name))
        side = "A" if actor is self.gs.A else "B"
        return self.choose(f"optional:{name}", side, [True, False], yes, card)

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
        context = EffectContext(self, card, actor, opponent, battlefield, dict(context_extra or {}))
        for es_index, es in enumerate(effect_specs):
            if es.trigger != trigger:
                continue
            once_key = (id(card), es_index)
            if es.params.get("once_per_turn") and self.gs.once_per_turn_used.get(once_key) == self.gs.turn:
                continue    # "Once each turn" / "The first time ... each turn": used
            # A condition that doesn't depend on the payment is checked first, so
            # a failed "if ..." never wastes the cost ("if you control 4 or fewer
            # runes, you may pay [1] to draw 1").
            kicker_gate = (es.condition or {}).get("type") == "kicker_paid"
            if not kicker_gate and not self._check_condition(
                    es.condition, card, actor, opponent, context_extra):
                continue
            # Optional ("you may ...") effects: let the actor decline BEFORE paying
            # any cost. Default (no agent / heuristic agents) is yes.
            if not self._wants_optional(actor, card, es):
                continue
            # Pay any cost / additional_cost the triggered ability carries BEFORE
            # a kicker_paid check (so the gate sees the payment). If a cost exists
            # but is unaffordable, the ability simply doesn't fire (KNOWN_ISSUES #12).
            if not self._pay_triggered_cost(card, actor, es):
                continue
            if kicker_gate and not self._check_condition(
                    es.condition, card, actor, opponent, context_extra):
                continue
            handler = EFFECT_REGISTRY.get(es.effect)
            if not handler:
                continue
            if es.params.get("once_per_turn"):
                self.gs.once_per_turn_used[once_key] = self.gs.turn
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
            gear = card if unit is None and isinstance(card, GearCard) else None
            if parsed["tap"] and gear is not None and getattr(gear, "tapped", False):
                return False      # "exhaust this" on an exhausted gear
            if not self._pay_energy_and_generic(actor, parsed["energy"], parsed["power"], parsed["domain"]):
                return False
            if parsed["tap"] and unit is not None:
                self._exhaust(unit)
            if parsed["tap"] and gear is not None:
                self._exhaust_gear(gear, actor)
            self._recycle_from_trash(actor, parsed["recycle"])
            self._pay_discard_and_banish(actor, parsed, unit)
            if parsed["spend_xp"]:
                self.gs.add_xp(side, -parsed["spend_xp"])
            if parsed["sacrifice"] and unit is not None:
                self._remove_unit_from_play(unit, side)
                self._to_trash(actor, unit.card)
            card._kicker_paid = True

        return True

    def _fire_units_trigger(self, trigger: str, side: str, exclude_card=None,
                            triggering_card=None, extra: Optional[dict] = None) -> None:
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
                                                               "triggering_card": trig,
                                                               **(extra or {})})
        anchor = self.gs.battlefields[0]
        for u in list(actor.base_units):
            if u.card is exclude_card:
                continue
            self._resolve_triggered_effects(u.card, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor,
                                                           "triggering_card": trig,
                                                           **(extra or {})})
        # Unattached gear ("When you play a unit, ...": Blood Rose, Fresh Beans)
        # and the Legend ("When you win a combat, draw 1": Draven).
        legend_unit = self._legend_unit(side)
        listeners = list(actor.base_gear) + ([legend_unit.card] if legend_unit is not None else [])
        for g in listeners:
            if g is exclude_card:
                continue
            self._resolve_triggered_effects(g, trigger, anchor, actor, opponent,
                                            context_extra={"battlefield": anchor,
                                                           "triggering_card": trig,
                                                           **(extra or {})})

    def _fire_readied(self, unit: UnitInPlay, side: str) -> None:
        """`unit` went from exhausted to ready: its "when you ready me" abilities
        (on_readied, Irelia Fervent)."""
        where = self._locate_unit(unit)
        bf = where[1] if where and where[1] is not None else self.gs.battlefields[0]
        self._resolve_triggered_effects(unit.card, "on_readied", bf, self.gs.get_player(side),
                                        self.gs.get_player(self.gs.other(side)),
                                        context_extra={"battlefield": bf})
        # "When you ready a friendly unit, ..." (Pirate's Haven).
        self._fire_units_trigger("on_friendly_unit_readied", side, triggering_card=unit.card,
                                 extra={"triggering_unit": unit})

    def _note_chosen(self, source: Card, chooser: str, units: list) -> None:
        """A spell or ability of `chooser` chose these units (a choice, not "all
        units"): count a choice of enemies (Ezreal Prodigal Explorer: "with spells
        or unit abilities") and fire "when you choose me" (on_chosen) on the
        chooser's units chosen, with the source as triggering_card."""
        gs = self.gs
        enemy = gs.other(chooser)
        located = [(u, self._locate_unit(u)) for u in units]
        from_spell_or_unit = isinstance(source, (SpellCard, UnitCard))
        if from_spell_or_unit and any(w is not None and w[0] == enemy for _, w in located):
            gs.enemy_choices_this_turn[chooser] = gs.enemy_choices_this_turn.get(chooser, 0) + 1
        for unit, where in located:
            if where is None or where[0] != chooser or unit.card is source:
                continue
            self._fire_units_trigger("on_friendly_chosen", chooser, triggering_card=source,
                                     extra={"triggering_unit": unit})
            bf = where[1] or gs.battlefields[0]
            self._resolve_triggered_effects(unit.card, "on_chosen", bf, gs.get_player(chooser),
                                            gs.get_player(enemy),
                                            context_extra={"battlefield": bf,
                                                           "triggering_card": source})

    def _resolve_delayed_effects(self) -> None:
        """Run the "at the end of this turn, ..." effects scheduled this turn."""
        waiting, self.gs.delayed_effects = self.gs.delayed_effects, []
        for side, card, bf_idx, sub in waiting:
            handler = EFFECT_REGISTRY.get(sub.get("effect"))
            if handler is None:
                continue
            ctx = EffectContext(self, card, self.gs.get_player(side),
                                self.gs.get_player(self.gs.other(side)),
                                self.gs.battlefields[bf_idx])
            handler(ctx, sub)

    def _legend_unit(self, side: str):
        """The in-play UnitInPlay for a side's Legend, or None."""
        return self.gs.legend_unit_A if side == "A" else self.gs.legend_unit_B

    def _all_units_in_play(self):
        """Every UnitInPlay across battlefields and both bases, plus legends."""
        units = []
        for bf in self.gs.battlefields:
            units.extend(bf.units_A)
            units.extend(bf.units_B)
        units.extend(self.gs.A.base_units)
        units.extend(self.gs.B.base_units)
        for lu in (self.gs.legend_unit_A, self.gs.legend_unit_B):
            if lu is not None:
                units.append(lu)
        return units

    def _recompute_passives(self) -> None:
        """Re-evaluate all continuous (trigger: passive) abilities and fold their
        grants into the passive_might / passive_keywords overlays. Called whenever
        board state changes so `UnitInPlay.might` stays correct (Round 4 Tier 2)."""
        for u in self._all_units_in_play():
            if u.copied_from is not None and not any(self._has_effect(g, "copy_friendly_unit") for g in u.gear):
                u.card, u.copied_from = u.copied_from, None     # Shady Spectacles came off
            u.passive_might = 0
            u.passive_keywords = set()
            u.no_combat_damage = False
            u.equip_bonus_mult = 1
            u.unchoosable = u.no_move_to_base = u.cant_ready = u.spell_immune = False

        for bf in self.gs.battlefields:
            for side in ("A", "B"):
                actor = self.gs.get_player(side)
                opponent = self.gs.get_player(self.gs.other(side))
                for unit in list(bf.units_A if side == "A" else bf.units_B):
                    self._apply_unit_passives(unit, side, bf, actor, opponent)
                # Deployed gear ("friendly units here have ASSAULT").
                for dg in bf.gear_for(side):
                    self._apply_gear_passives(dg.card, side, bf, actor, opponent)
        anchor = self.gs.battlefields[0]
        for side in ("A", "B"):
            actor = self.gs.get_player(side)
            opponent = self.gs.get_player(self.gs.other(side))
            for unit in list(actor.base_units):
                self._apply_unit_passives(unit, side, anchor, actor, opponent)
            legend_unit = self._legend_unit(side)
            if legend_unit is not None:
                self._apply_unit_passives(legend_unit, side, anchor, actor, opponent)
            # Unattached non-Equipment gear ("Your units have +2 [might]":
            # Ephemeral Ward). An Equipment's passives are for its unit.
            for g in list(actor.base_gear):
                if self._equip_cost(g) is None:
                    self._apply_gear_passives(g, side, anchor, actor, opponent)

    def _apply_unit_passives(self, unit, side, bf, actor, opponent) -> None:
        spec = CARD_REGISTRY.get(unit.card.name)
        if not (spec and spec.effects):
            self._apply_equipment_conditions(unit, actor, opponent, bf)
            return
        context = EffectContext(self, unit.card, actor, opponent, bf)
        for es in spec.effects:
            if es.trigger != "passive":
                continue
            if not self._check_condition(es.condition, unit.card, actor, opponent,
                                         {"battlefield": bf}):
                continue
            self._apply_passive_grant(unit, context, es)
        self._apply_equipment_conditions(unit, actor, opponent, bf)

    def _apply_equipment_conditions(self, unit, actor, opponent, bf) -> None:
        """An Equipment's conditional Might for its unit ("I have +2 [might]
        while I'm at a battlefield with exactly one other unit you control":
        Hand Hammer), checked as the unit."""
        for g in unit.gear:
            gspec = CARD_REGISTRY.get(g.name)
            for es in (gspec.effects if gspec else ()):
                if es.effect == "equip_conditional_might" and self._check_condition(
                        es.condition, unit.card, actor, opponent, {"battlefield": bf}):
                    unit.passive_might += int(es.params.get("amount", 0))

    def _apply_gear_passives(self, card, side, bf, actor, opponent) -> None:
        spec = CARD_REGISTRY.get(card.name)
        if not (spec and spec.effects):
            return
        context = EffectContext(self, card, actor, opponent, bf)
        for es in spec.effects:
            if es.trigger != "passive":
                continue
            if not self._check_condition(es.condition, card, actor, opponent,
                                         {"battlefield": bf}):
                continue
            self._apply_passive_grant(None, context, es)

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

        if es.effect == "no_combat_damage":
            for u in targets:
                u.no_combat_damage = True
            return

        if es.effect == "double_equipment_might":
            for u in targets:
                u.equip_bonus_mult = 2
            return

        if es.effect in ("cant_be_chosen", "cant_move_to_base", "cant_be_readied",
                         "prevent_enemy_spell_damage"):
            flag = {"cant_be_chosen": "unchoosable", "cant_move_to_base": "no_move_to_base",
                    "cant_be_readied": "cant_ready",
                    "prevent_enemy_spell_damage": "spell_immune"}[es.effect]
            for u in targets:
                setattr(u, flag, True)
            return

        if es.effect == "give_keyword":
            keyword = str(params.get("keyword", "")).strip()
            if not keyword:
                return
            src = params.get("amount_source")
            for u in targets:
                if src == "own_equipment":
                    # "Your Equipment each give ASSAULT" (Lucian Purifier).
                    n = sum(1 for g in u.gear if self._equip_cost(g) is not None)
                elif src:
                    # "I have ASSAULT equal to the number of ..." (Ancient Warmonger).
                    n = _effect_amount(context, params)
                else:
                    u.passive_keywords.add(keyword)
                    continue
                if n > 0:
                    u.passive_keywords.add(f"{keyword.split()[0]} {n}")
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

    def _bf_passive_amount(self, bf, verb: str, default: int = 0) -> int:
        """Amount of a battlefield-scoped passive rule-modifier (e.g.
        ``bonus_damage_here``) carried by this battlefield's card, or ``default``
        if absent. These marker verbs are NON_HANDLER_VERBS consumed by the
        relevant subsystem here rather than dispatched via effects.REGISTRY (same
        pattern as ``reduce_cost``). A flag marker with no ``amount`` reports 1
        when present. Preserves the ``bf.card is None`` no-op."""
        if bf is None or bf.card is None:
            return default
        spec = CARD_REGISTRY.get(bf.card.name)
        if not spec:
            return default
        for es in spec.effects:
            if es.trigger == "passive" and es.effect == verb:
                amt = es.params.get("amount")
                if isinstance(amt, (int, float)) and not isinstance(amt, bool):
                    return int(amt)
                return 1
        return default

    def _deflect_surcharge(self, card: Card, target_lane: int,
                           caster: Optional[str] = None) -> int:
        """Extra energy a spell costs because the caster's opponent has DEFLECT
        units at the target battlefield (§809). Applies only when the spell targets
        the opponent. Returns the max DEFLECT value among eligible enemy units.
        `caster` defaults to the active player (a reaction's caster may not be)."""
        # Battlefield that waives DEFLECT while paying here (e.g. Heisho Shell of
        # the World) → no surcharge regardless of who the spell targets.
        if 0 <= target_lane < len(self.gs.battlefields):
            if self._bf_passive_amount(self.gs.battlefields[target_lane], "ignore_deflect_here"):
                return 0
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
        opp_side = self.gs.other(caster or self.gs.active)
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

        def _friendly_units():
            """Units the actor controls: their battlefield units, base units, and
            legend unit (mirrors the you_control_subtype walk below)."""
            us = []
            for bf in self.gs.battlefields:
                us.extend(bf.units_A if side == "A" else bf.units_B)
            us.extend(actor.base_units)
            lu = self.gs.legend_unit_A if side == "A" else self.gs.legend_unit_B
            if lu is not None:
                us.append(lu)
            return us

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
        if ctype == "showed_off":
            return bool(getattr(card, "_showed_off", False))
        if ctype == "friendly_unit_died_this_turn":
            return bool(self.gs.friendly_unit_died_this_turn.get(side, False))
        if ctype == "you_played_n_spells_this_turn":
            return self.gs.spells_played_this_turn.get(side, 0) >= _threshold()
        if ctype == "your_legend_exhausted":
            legend = self._legend_unit(side)
            return legend is not None and not legend.ready
        if ctype == "holder_didnt_conquer_this_turn":
            unit = extra.get("triggering_unit")
            return unit is not None and unit.conquered_turn != self.gs.turn
        if ctype == "conquered_uncontrolled":
            # "When I conquer a battlefield that was uncontrolled" (Yone).
            bf = extra.get("battlefield")
            return bf is not None and getattr(bf, "prev_controller", "?") is None
        if ctype == "not":
            return not self._check_condition(params.get("condition"), card, actor, opponent, extra)
        if ctype == "friendly_gear_here":
            # "unless there's a friendly gear here" (Orianna Exquisite).
            unit = self._find_unit_by_card(card)
            where = self._locate_unit(unit) if unit is not None else None
            here = where[1] if where else None
            return here is not None and (bool(here.gear_for(side)) or
                                         any(u.gear for u in here._units_for(side)))
        if ctype == "cards_in_hand_exactly":
            return len(actor.hand) == _threshold()
        if ctype == "units_at_battlefields_exactly":
            # Gutter Palace: "exactly 4 units at battlefields".
            return sum(len(bf._units_for(side)) for bf in self.gs.battlefields) == _threshold()
        if ctype == "died_mighty":
            # DEATHKNELL "If I was MIGHTY" (Unsung Hero).
            return int(extra.get("died_might", 0) or 0) >= 5
        if ctype == "units_here_exactly":
            # "if there is exactly one other unit you control here": n counts me.
            unit = self._find_unit_by_card(card)
            where = self._locate_unit(unit) if unit is not None else None
            here = where[1] if where else extra.get("battlefield")
            return here is not None and len(here._units_for(side)) == _threshold(1)
        if ctype == "triggering_unit_stunned":
            unit = extra.get("triggering_unit")
            return unit is not None and unit.stunned
        if ctype == "died_here":
            # "when an enemy unit here dies": where it died is where I am.
            unit = self._find_unit_by_card(card)
            where = self._locate_unit(unit) if unit is not None else None
            return where is not None and where[1] is not None and extra.get("died_at") is where[1]
        if ctype == "triggering_unit_mightiest":
            # "a unit with Might greater than each other unit on the board".
            unit = extra.get("triggering_unit")
            if unit is None:
                trig = extra.get("triggering_card")
                unit = self._find_unit_by_card(trig) if trig is not None else None
            others = [u for u in self._all_units_in_play() if u is not unit]
            return unit is not None and all(unit.might > u.might for u in others)
        if ctype == "triggering_unit_alone":
            # "When a friendly unit attacks or defends alone".
            return bool(extra.get("alone"))
        if ctype == "triggering_unit_buffed":
            # "When a buffed friendly unit dies".
            unit = extra.get("triggering_unit")
            return unit is not None and unit.might_counters > 0
        if ctype == "in_showdown":
            return self.gs.showdown_active
        if ctype == "gained_xp_this_turn":
            return self.gs.xp_gained_turn.get(side) == self.gs.turn
        if ctype == "power_spent_this_turn_at_least":
            # "If you've spent at least [rune] [rune] this turn".
            return actor.power_spent_this_turn >= _threshold(1)
        if ctype == "ready_enemy_here":
            bf = extra.get("battlefield")
            return bf is not None and any(u.ready for u in bf._units_for(self.gs.other(side)))
        if ctype == "moves_this_turn_exactly":
            # "The first / third time I move in a turn" (on_move).
            unit = extra.get("triggering_unit") or self._find_unit_by_card(card)
            return unit is not None and unit.moves_this_turn == _threshold(1)
        if ctype == "moved_to_other_battlefield":
            # "When an opponent moves to a battlefield other than mine".
            to = extra.get("moved_to")
            me = self._locate_unit(self._find_unit_by_card(card)) if self._find_unit_by_card(card) else None
            return to is not None and to != "base" and (me is None or me[1] is not to)
        if ctype == "not_your_turn":
            return side != self.gs.active
        if ctype == "triggering_card_from_zone":
            # "When you play a card from face down" (zone "facedown").
            return extra.get("triggering_card") is not None and \
                extra.get("from_zone", "hand") == params.get("zone")
        if ctype == "played_to_controlled_battlefield":
            bf = extra.get("played_to")
            return bf is not None and bf.controller() == side
        if ctype == "units_in_base_at_least":
            # "if you have two or more other units in your base"
            return sum(1 for u in actor.base_units if u.card is not card) >= _threshold(1)
        if ctype == "all_of":
            # Several conditions that must all hold ("your first card each turn,
            # if I'm at a battlefield").
            return all(self._check_condition(c, card, actor, opponent, extra)
                       for c in params.get("conditions") or [])
        if ctype == "died_alone":
            # DEATHKNELL "if I died alone": no other friendly unit here, alive or
            # dying with it (set by _route_deaths).
            return bool(extra.get("died_alone"))
        if ctype == "enemy_choices_this_turn_at_least":
            return self.gs.enemy_choices_this_turn.get(side, 0) >= _threshold(1)
        if ctype in ("moved_to_battlefield", "moved_from_battlefield"):
            # "When I move to a battlefield" / "from a battlefield" (on_move).
            where = extra.get("moved_to" if ctype == "moved_to_battlefield" else "moved_from")
            return where is not None and where != "base"
        if ctype == "cards_played_this_turn_exactly":
            # "When you play your second card in a turn": the triggering card is
            # already counted when on_card_played fires.
            return self.gs.cards_played_this_turn.get(side, 0) == _threshold(1)
        if ctype == "opponent_played_n_spells_this_turn":
            return self.gs.spells_played_this_turn.get(self.gs.other(side), 0) >= _threshold(1)
        if ctype == "triggering_card_matches":
            # "When you play a spell / a gear / a card with Energy cost [7] or more".
            from .effects import _zone_effect_card_ok
            trig = extra.get("triggering_card")
            return trig is not None and _zone_effect_card_ok(trig, {"target_filter": params.get("filter") or {}})
        if ctype == "triggering_card_not_from_hand":
            # "When you play a card from anywhere other than your hand".
            return extra.get("triggering_card") is not None and extra.get("from_zone", "hand") != "hand"
        if ctype == "you_already_played_another_card_this_turn":
            # Another card than this one: a LEGION card's own play is already
            # counted while its "when you play me" resolves.
            return any(c is not card for c in self.gs.played_cards_this_turn.get(side, ()))
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
            # (unit, legend or gear) carries the empowered status.
            return self._is_empowered(card)
        if ctype == "you_control_subtype":
            # The corpus writes the tag as "subtype" (older specs as "tag").
            tag = str(params.get("tag") or params.get("subtype") or "")
            if not tag:
                return False
            # other: true = "another Dragon" (not this card).
            other = bool(params.get("other"))
            return any(tag in u.tags and not (other and u.card is card)
                       for u in _friendly_units())
        if ctype == "score_within_n_of_victory":
            pts = self.gs.points_A if side == "A" else self.gs.points_B
            return pts >= self.gs.victory_score - _threshold()
        if ctype == "you_discarded_card_this_turn":
            return bool(self.gs.discarded_this_turn.get(side, False))
        if ctype == "cards_burned_this_turn_at_least":
            return self.gs.cards_burned_this_turn.get(side, 0) >= _threshold()
        if ctype == "friendly_total_might_at_least":
            # Combined might of the actor's OTHER units (exclude the source card),
            # e.g. Kinkou Initiate "draw 1 if your other units have total Might 5+".
            total = sum(int(getattr(u, "might", 0) or 0)
                        for u in _friendly_units() if u.card is not card)
            return total >= _threshold()
        if ctype == "you_control_n_or_more_gear":
            # Gear the actor controls: attached to their units + loose in base,
            # e.g. Patched Porobot "if you control 3 or more other gear, draw 1".
            # The source is a unit, not gear, so nothing to exclude.
            count = (sum(len(u.gear) for u in _friendly_units()) + len(actor.base_gear)
                     + sum(len(bf.gear_for(side)) for bf in self.gs.battlefields))
            return count >= _threshold()
        if ctype == "opponent_controls_a_battlefield":
            other = self.gs.other(side)
            return any(bf.controller() == other for bf in self.gs.battlefields)
        if ctype == "you_control_no_other_units":
            return not [u for u in _friendly_units()
                        if u.card is not card and u is not self._legend_unit(side)]
        if ctype == "card_with_my_name_in_trash":
            return any(c.name == card.name and c is not card for c in actor.trash)
        if ctype == "cards_in_hand_at_most":
            return len(actor.hand) <= _threshold()
        if ctype == "first_turn_of_player":
            return self.gs.turn <= 2
        if ctype == "rune_deck_empty":
            return not actor.rune_deck.runes
        if ctype in ("enemy_alone_here", "one_on_one_here"):
            bf = extra.get("battlefield")
            if bf is None:
                return False
            other = self.gs.other(side)
            enemies = bf.units_A if other == "A" else bf.units_B
            if ctype == "enemy_alone_here":
                return len(enemies) == 1
            friends = bf.units_A if side == "A" else bf.units_B
            return len(enemies) == 1 and len(friends) == 1
        if ctype == "you_control_bf_with_exactly_n_units":
            n = _threshold(2)
            return any(bf.controller() == side and len(bf.units_A) + len(bf.units_B) == n
                       for bf in self.gs.battlefields)
        if ctype == "you_have_n_or_fewer_runes":
            return actor.total_runes_in_play() <= _threshold()
        if ctype == "this_is_at_battlefield":
            return any(u.card is card for bf in self.gs.battlefields
                       for u in (bf.units_A if side == "A" else bf.units_B))
        if ctype == "fewer_runes_than_opponent":
            return actor.total_runes_in_play() < opponent.total_runes_in_play()
        if ctype == "triggering_unit_has_subtype":
            trig = extra.get("triggering_card")
            tag = str(params.get("subtype") or params.get("tag") or "")
            return trig is not None and bool(tag) and tag in (getattr(trig, "tags", None) or [])
        if ctype == "triggering_unit_not_named":
            trig = extra.get("triggering_card")
            return trig is None or getattr(trig, "name", None) != params.get("name")
        if ctype == "friendly_deployed_gear_here":
            bf = extra.get("battlefield")
            return bf is not None and bool(bf.gear_for(side))
        if ctype == "you_control_this_battlefield":
            bf = extra.get("battlefield")
            return bf is not None and bf.controller() == side
        if ctype == "opponent_controls_stunned_unit":
            other = self.gs.other(side)
            return any(u.stunned for bf in self.gs.battlefields
                       for u in (bf.units_A if other == "A" else bf.units_B))
        if ctype == "has_all_pet_tags":
            # "if your units have all of the following tags among them - Bird,
            # Cat, Dog, and Poro" (Ivern Friend to All).
            tags = {t for u in self._friendly_units_of(side) for t in u.tags}
            return {"Bird", "Cat", "Dog", "Poro"} <= tags
        if ctype == "signpost_possible":
            return self._signpost_pair(side) is not None
        if ctype == "in_beginning_phase":
            return self.gs.in_beginning_phase and self.gs.active == side
        if ctype == "triggering_unit_here":
            # "an enemy unit here": where it is (or died) is where I am.
            unit = self._find_unit_by_card(card)
            where = self._locate_unit(unit) if unit is not None else None
            return where is not None and where[1] is not None and extra.get("died_at") is where[1]
        if ctype == "excess_damage_at_least":
            # "if you assigned 3 or more excess damage" in this battlefield's combat.
            bf = extra.get("battlefield")
            turn, amount = (bf.excess_damage.get(side, (-1, 0)) if bf is not None else (-1, 0))
            return turn == self.gs.turn and amount >= _threshold(1)
        if ctype == "facedown_card_here":
            # "if you control a facedown card here" (Evelynn in Control).
            bf = extra.get("battlefield")
            return bf is not None and bf.facedown is not None and bf.facedown.owner == side
        if ctype == "played_unit_gear_spell_this_turn":
            # "if you've played a non-token unit, a non-token gear, and a spell
            # this turn" (Swain Visionary).
            played = self.gs.played_cards_this_turn.get(side, ())
            return (any(isinstance(c, UnitCard) for c in played)
                    and any(isinstance(c, GearCard) for c in played)
                    and any(isinstance(c, SpellCard) for c in played))
        if ctype == "controller_has_facedown_card":
            # "if you control a facedown card at a battlefield" (Mushroom Pouch).
            return any(bf.facedown is not None and bf.facedown.owner == side
                       for bf in self.gs.battlefields)
        # Conditions needing context the engine doesn't track yet → safe False
        # (effects gated on them simply don't fire): excess_damage_at_least,
        # target_was_stunned.
        return False

    def _cost_reduction(self, card: Card, actor: Player) -> int:
        """Static / conditional flat energy cost reduction (Round 4 Tier 2).
        Sums every `reduce_cost` effect (trigger `cost_modifier`) on the card whose
        optional condition currently holds. Dynamic (amount_source) reductions are
        A reduction with an `amount_source` scales: "I cost [1] less for each card
        you've played this turn" → amount_source cards_played_this_turn (times
        `amount`, default 1). Returns a non-negative energy amount to subtract."""
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
            if es.params.get("amount_source"):
                ctx = EffectContext(self, card, actor, opponent, self.gs.battlefields[0])
                per = int(es.params.get("amount", 1) or 1)
                total += per * _effect_amount(ctx, {"amount_source": es.params["amount_source"]})
            else:
                total += int(es.params.get("amount", 0))
        return max(0, total)

    _EQUIP_DOMAINS = ("fury", "calm", "mind", "body", "chaos", "order")

    def _equip_cost(self, gear: Card) -> Optional[dict]:
        """Parse a gear's EQUIP-ability cost from its rules text (§744), e.g.
        "Equip [fury]" → 1 Fury power; "Equip [1] [fury]" → 1 energy + 1 Fury;
        "Equip [rune]" → 1 generic power. Returns None if the gear has no Equip
        ability (i.e. it is not Equipment and cannot be equipped). `complex` flags
        an additional non-resource cost (recycle / kill / spend XP) we don't yet
        charge — a documented undercharge for those few cards."""
        import re
        spec = CARD_REGISTRY.get(gear.name)
        text = (spec.raw.get("effect") if spec and getattr(spec, "raw", None) else None)
        if not text:
            text = getattr(gear, "equip_text", "") or ""
        m = re.search(r"(?i)\bequip\b(.*?)\(", text)   # cost = between 'equip' and reminder '('
        if not m:
            return None
        clause = m.group(1)
        energy = 0
        domain_power: dict[str, int] = {}
        generic = 0
        for tok in re.findall(r"\[([^\]]+)\]", clause):
            t = tok.strip().lower()
            if t.isdigit():
                energy += int(t)
            elif t in self._EQUIP_DOMAINS:
                domain_power[t] = domain_power.get(t, 0) + 1
            elif t == "rune":
                generic += 1
        # Additional non-resource Equip costs (Last Rites / Blade of the Ruined
        # King / Shepherd's Heirloom): recycle N from trash, kill a friendly unit,
        # spend N XP.
        rec = re.search(r"(?i)recycle\s+(\d+)", clause)
        recycle = int(rec.group(1)) if rec else 0
        kill_friendly = bool(re.search(r"(?i)kill a friendly", clause))
        xp = re.search(r"(?i)spend\s+(\d+)\s*xp", clause)
        spend_xp = int(xp.group(1)) if xp else 0
        # `complex` now means an extra cost we still can't model (none currently).
        return {"energy": energy, "domain_power": domain_power, "generic": generic,
                "recycle": recycle, "kill_friendly": kill_friendly,
                "spend_xp": spend_xp, "complex": False}

    @staticmethod
    def _equip_cost_minus_A(cost: dict) -> dict:
        """An Equip cost reduced by [A] (1 Power of any domain) — Weaponmaster's
        discount. Drops one power position: generic first, else one domain unit."""
        c = dict(cost)
        c["domain_power"] = dict(cost["domain_power"])
        if c["generic"] > 0:
            c["generic"] -= 1
        else:
            for d in list(c["domain_power"]):
                c["domain_power"][d] -= 1
                if c["domain_power"][d] == 0:
                    del c["domain_power"][d]
                break
        return c

    def _can_pay_equip(self, ap: Player, cost: dict) -> bool:
        # Ornn's earmarked gear-power (generic) may cover any power position.
        earmark = ap.earmarked_power_gear
        if ap.energy < cost["energy"]:
            return False
        gen = max(0, cost["generic"] - earmark)
        earmark = max(0, earmark - cost["generic"])
        if not self._can_pay_generic_power(ap, gen):
            return False
        for d, n in cost["domain_power"].items():
            need = max(0, n - earmark)
            earmark = max(0, earmark - n)
            if need and not ap.can_pay_cost(0, need, Domain[d.upper()]):
                return False
        # Additional Equip costs.
        side = "A" if ap is self.gs.A else "B"
        if cost.get("recycle", 0) and len(ap.trash) < cost["recycle"]:
            return False
        if cost.get("kill_friendly") and self._first_friendly_unit_on_board(side) is None:
            return False
        if cost.get("spend_xp", 0) and self.gs.get_xp(side) < cost["spend_xp"]:
            return False
        return True

    def _pay_equip(self, ap: Player, cost: dict) -> bool:
        if not self._can_pay_equip(ap, cost):
            return False
        side = "A" if ap is self.gs.A else "B"
        ap.energy -= cost["energy"]
        # Spend earmarked gear-power first (generic portion, then domain portions).
        gen = cost["generic"]
        use = min(gen, ap.earmarked_power_gear)
        ap.earmarked_power_gear -= use
        self._pay_generic_power(ap, gen - use)
        for d, n in cost["domain_power"].items():
            use = min(n, ap.earmarked_power_gear)
            ap.earmarked_power_gear -= use
            if n - use:
                ap.pay_cost(0, n - use, Domain[d.upper()])
        # Additional Equip costs.
        self._recycle_from_trash(ap, cost.get("recycle", 0))
        if cost.get("kill_friendly"):
            victim = self._first_friendly_unit_on_board(side)
            if victim is not None:
                self._remove_unit_from_play(victim, side)
                self._to_trash(ap, victim.card)
        if cost.get("spend_xp", 0):
            self.gs.add_xp(side, -cost["spend_xp"])
        return True

    def _can_pay_showdown(self, p: Player, energy: int, power, domain) -> bool:
        """Affordability during a showdown: Diana Scorn's earmarked energy adds to
        available energy (spendable only here)."""
        if p.energy + p.earmarked_energy_showdown < energy:
            return False
        if power and domain is not None:
            return p.can_pay_cost(0, power, domain)
        return True

    def _pay_showdown(self, p: Player, energy: int, power, domain) -> bool:
        if not self._can_pay_showdown(p, energy, power, domain):
            return False
        from_earmark = min(energy, p.earmarked_energy_showdown)
        p.earmarked_energy_showdown -= from_earmark
        return p.pay_cost(energy - from_earmark, power, domain)

    def _can_pay_gear(self, ap: Player, energy: int, power, domain) -> bool:
        """Affordability of a gear cost: Ornn's earmarked gear-power (generic) may
        cover the power portion."""
        if ap.energy < energy:
            return False
        if not power:
            return True
        remaining = max(0, power - ap.earmarked_power_gear)
        if remaining == 0:
            return True
        if domain is None:
            return self._can_pay_generic_power(ap, remaining)
        return ap.can_pay_cost(0, remaining, domain)

    def _pay_gear(self, ap: Player, energy: int, power, domain) -> bool:
        if not self._can_pay_gear(ap, energy, power, domain):
            return False
        ap.energy -= energy
        if power:
            from_earmark = min(power, ap.earmarked_power_gear)
            ap.earmarked_power_gear -= from_earmark
            remaining = power - from_earmark
            if remaining:
                if domain is None:
                    self._pay_generic_power(ap, remaining)
                else:
                    ap.pay_cost(0, remaining, domain)
        return True

    def _spell_chooses_friendly(self, card: Card) -> bool:
        """True if the spell EXPLICITLY targets a friendly unit — used by
        battlefield cost auras like Sandswept Tomb ("spells that choose friendly
        units here"). Only explicit friendly targets count; we never assume a
        handler's default target, so the discount under-applies rather than
        misfiring on, say, a self-defaulting buff."""
        spec = CARD_REGISTRY.get(card.name)
        if not (spec and spec.effects):
            return False
        return any((es.target or "").lower() in self._PASSIVE_FRIENDLY_TARGETS
                   for es in spec.effects)

    def _bf_cost_reduction(self, card: Card, target_lane: int) -> tuple[int, int]:
        """(energy, power) cost reduction the TARGET battlefield grants this spell,
        e.g. Sandswept Tomb: a spell choosing friendly units here costs 1 power
        ([rune]) less. Data-driven marker `reduce_cost_here` {amount, resource:
        'power'|'energy' (default energy), requires_target: 'friendly'|None}."""
        if not (0 <= target_lane < len(self.gs.battlefields)):
            return 0, 0
        bf = self.gs.battlefields[target_lane]
        if bf is None or bf.card is None:
            return 0, 0
        spec = CARD_REGISTRY.get(bf.card.name)
        if not spec:
            return 0, 0
        e_red = p_red = 0
        for es in spec.effects:
            if es.trigger != "passive" or es.effect != "reduce_cost_here":
                continue
            if es.params.get("requires_target") == "friendly" and not self._spell_chooses_friendly(card):
                continue
            amt = int(es.params.get("amount", 1))
            if es.params.get("resource") == "power":
                p_red += amt
            else:
                e_red += amt
        return e_red, p_red

    def _can_pay_generic_power(self, actor: Player, n: int) -> bool:
        """Whether the actor can pay n generic ([rune]) power from a single domain.
        The engine's power pool is domain-keyed; generic power is modeled as 'any one
        domain you have enough of' (a documented simplification)."""
        if n <= 0:
            return True
        return any(actor.can_pay_cost(0, n, d) for d in list(actor.power_pool))

    def _can_pay_energy_and_generic(self, actor: Player, energy: int, power: int,
                                    domain: Optional[Domain] = None) -> bool:
        """Affordability of an ability / additional cost: Energy plus power of
        `domain` ("[2] [fury]"), or generic power ([rune]) when it is None.
        (Player.can_pay_cost with no domain ignores power entirely — that made
        every such power cost free.)"""
        if actor.energy < (energy or 0):
            return False
        if domain is not None and power:
            return actor.can_pay_cost(0, power, domain)
        return self._can_pay_generic_power(actor, power or 0)

    def _pay_energy_and_generic(self, actor: Player, energy: int, power: int,
                                domain: Optional[Domain] = None) -> bool:
        if not self._can_pay_energy_and_generic(actor, energy, power, domain):
            return False
        actor.energy -= energy or 0
        if domain is not None and power:
            return actor.pay_cost(0, power, domain)
        return self._pay_generic_power(actor, power or 0)

    def _pay_repeat(self, card: Card, ap: Player) -> bool:
        """Pay a spell's REPEAT cost if affordable: its printed cost
        (SpellCard.repeat_cost: Energy, Power of a domain or of any, or a
        discard), else an explicit "REPEAT N" keyword, else the spell's Energy
        cost (a bare REPEAT)."""
        cost = getattr(card, "repeat_cost", None)
        if not card.has_keyword("REPEAT") and getattr(card, "_granted_repeat", False):
            # "REPEAT equal to its cost"
            dom = card.cost_power_domain
            cost = {"energy": card.cost_energy or 0, "power": card.cost_power or 0,
                    "domain": dom.name if isinstance(dom, Domain) else None}
        if not cost:
            bare = any(k.strip().upper() == "REPEAT" for k in card.keywords)
            cost = {"energy": (card.cost_energy or 0) if bare else card.keyword_value("REPEAT")}
        energy = int(cost.get("energy", 0) or 0)
        power = int(cost.get("power", 0) or 0)
        domain = Domain[cost["domain"]] if cost.get("domain") else None
        discard = int(cost.get("discard_cards", 0) or 0)
        others = [c for c in ap.hand if c is not card]
        if not (energy or power or discard) or ap.energy < energy or len(others) < discard:
            return False
        if power and not (ap.can_pay_cost(0, power, domain) if domain
                          else self._can_pay_generic_power(ap, power)):
            return False
        ap.energy -= energy
        if power:
            if domain:
                ap.pay_cost(0, power, domain)
            else:
                self._pay_generic_power(ap, power)
        for victim in others[:discard]:
            self._discard(ap, victim)
        return True

    def _pay_generic_power(self, actor: Player, n: int) -> bool:
        """Pay n generic ([rune]) power from the first domain that can cover it."""
        if n <= 0:
            return True
        for d in list(actor.power_pool):
            if actor.can_pay_cost(0, n, d):
                return actor.pay_cost(0, n, d)
        return False

    def _offer_reveal_from_top(self, actor: Player, cards: list) -> list:
        """When cards are looked at / revealed from the TOP of `actor`'s deck (dig /
        predict / scry), offer each card carrying an `on_reveal_from_top` ability the
        chance to banish itself and play for its alternate cost (Nocturne: banish,
        then play for [rune]). Optional — routed through decide_optional. Accepted
        cards are removed from `cards` (and the deck) and put into play as a unit
        (enters exhausted, like a normal play). Returns the cards taken.

        Simplifications (documented): the card's two nested "may"s collapse into one
        decision (you only banish in order to play); on-play triggers of the played
        card are not re-fired here; [rune] is charged as 1 power of any one domain."""
        taken: list = []
        for card in list(cards):
            spec = CARD_REGISTRY.get(card.name)
            if not spec:
                continue
            es = next((e for e in spec.effects if e.trigger == "on_reveal_from_top"), None)
            if es is None:
                continue
            if not self._wants_optional(actor, card, es):
                continue
            cost = es.cost or {}
            energy = int(cost.get("energy", 0))
            power = int(cost.get("power", 0))
            if actor.energy < energy or not self._can_pay_generic_power(actor, power):
                continue
            actor.energy -= energy
            self._pay_generic_power(actor, power)
            if card in actor.deck.cards:
                actor.deck.cards.remove(card)
            if card in cards:
                cards.remove(card)
            # Banished, then played from banishment.
            self._play_unit(card, "A" if actor is self.gs.A else "B", from_zone="banished")
            taken.append(card)
            if self.verbose:
                print(f"  {actor.name} reveals {card.name} from top → banish + play for [rune]")
        return taken

    def _ambush_legal_lanes(self, side: str) -> list:
        """Battlefield indices where this side's champion may be AMBUSH-deployed
        (played at reaction speed). Empty unless the champion exists, is undeployed,
        and has the AMBUSH keyword. A lane qualifies if the friendly side has units
        there, or — for the extended 'even without your own units' variant (Rengar,
        marked `enemy_ok` on its `ambush` effect) — if the enemy has units there."""
        champ = self.gs.champion_A if side == "A" else self.gs.champion_B
        deployed = self.gs.champion_A_deployed if side == "A" else self.gs.champion_B_deployed
        if champ is None or deployed or not champ.has_keyword("AMBUSH"):
            return []
        spec = CARD_REGISTRY.get(champ.name)
        enemy_ok = bool(spec and any(
            e.trigger == "passive" and e.effect == "ambush" and e.params.get("enemy_ok")
            for e in spec.effects))
        lanes = []
        for i, bf in enumerate(self.gs.battlefields):
            friendly = bf.units_A if side == "A" else bf.units_B
            enemy = bf.units_B if side == "A" else bf.units_A
            if friendly or (enemy_ok and enemy):
                lanes.append(i)
        return lanes

    def _deploy_ambush_champion(self, side: str, lane: int) -> bool:
        """Deploy the AMBUSH champion directly onto a battlefield lane at reaction
        speed. Validates the lane, pays the champion's cost, places it (exhausted),
        and marks the champion deployed. Returns True on success."""
        if lane not in self._ambush_legal_lanes(side):
            return False
        ap = self.gs.get_player(side)
        champ = self.gs.champion_A if side == "A" else self.gs.champion_B
        energy, power = self._effective_cost(champ, ap)
        if not self._pay_card(ap, champ, energy, power):
            return False
        bf = self.gs.battlefields[lane]
        if side == "A":
            self.gs.champion_A_deployed = True
        else:
            self.gs.champion_B_deployed = True
        if self.verbose:
            print(f"  {side} AMBUSH-deploys CHAMPION {champ.name} @BF{lane}")
        self._play_unit(champ, side, bf=bf, from_zone="champion")
        if self.recorder:
            self.recorder.record_play(side, self.gs.turn, champ, action="UNIT",
                                      battlefield_index=lane)
        # If the AMBUSH deploy contests the lane, spawn a showdown (#22) — mirrors
        # the move-into-contested path. _run_showdown self-guards on showdown_active,
        # so a deploy made DURING a showdown does NOT nest: the champion simply joins
        # the current combat, which resolves at end of turn (contested_this_turn).
        if bf.units_A and bf.units_B:
            bf.contested_this_turn = True
            self._run_showdown(lane, attacker=side)
        return True

    def _fire_first_unit_here(self, side: str, bf: Battlefield, just_moved) -> None:
        """Battlefield 'first non-token unit played here each turn' trigger (Star
        Spring: 'they may move another unit they control here to its base'). Fires
        once per side per turn. Optional (decide_optional). Deterministic stand-in:
        retreat the lowest-might OTHER friendly unit here to base."""
        if just_moved is None or just_moved.is_token:
            return
        already = bf.first_unit_here_A if side == "A" else bf.first_unit_here_B
        if already:
            return
        if side == "A":
            bf.first_unit_here_A = True
        else:
            bf.first_unit_here_B = True
        spec = CARD_REGISTRY.get(bf.card.name) if bf.card is not None else None
        if spec is None:
            return
        es = next((e for e in spec.effects
                   if e.trigger == "on_first_unit_here" and e.effect == "move_ally_here_to_base"), None)
        if es is None:
            return
        if not self._wants_optional(self.gs.get_player(side), bf.card, es):
            return
        here = bf.units_A if side == "A" else bf.units_B
        others = [u for u in here if u is not just_moved and not u.is_token]
        if not others:
            return
        victim = self.choose("first_unit_here", side, others, min(others, key=lambda u: u.might), bf.card)
        bf.remove_unit(side, victim)
        self.gs.get_player(side).base_units.append(victim)
        if self.verbose:
            print(f"  Star Spring: {side} retreats {victim.card.name} to base")

    # ------------------------------------------------------------------
    # HIDDEN keyword (Core Rules §737 / §408 / §106.4)

    def _hide_lanes(self, side: str) -> list:
        """Battlefields where `side` may Hide a card: it must control the
        battlefield (§106.4.c) and the Facedown Zone must be empty (§106.4.b)."""
        return [i for i, bf in enumerate(self.gs.battlefields)
                if bf.controller() == side and bf.facedown is None]

    def _hide_card(self, side: str, idx: int, lane: int) -> bool:
        """Hide the hand card at `idx` facedown at battlefield `lane` for the cost
        of 1 generic power (§737.1.b). Hiding is not a Play and opens no chain
        (§737.1.c.2). Returns True on success."""
        ap = self.gs.get_player(side)
        if not (0 <= idx < len(ap.hand)):
            return False
        card = ap.hand[idx]
        if not card.has_keyword("HIDDEN"):
            return False
        if lane not in self._hide_lanes(side):
            return False
        if not self._can_hide_pay(ap, side):
            return False
        if self._can_pay_generic_power(ap, 1):
            self._pay_generic_power(ap, 1)
        else:
            ap.energy -= 1           # Teemo Swift Scout: "pay [1] ... instead of [rune]"
        ap.remove_from_hand(idx)
        bf = self.gs.battlefields[lane]
        bf.facedown = FacedownCard(card=card, owner=side, turn_hidden=self.gs.turn)
        if self.verbose:
            print(f"  {side} HIDEs {card.name} facedown @BF{lane}")
        if bf.card is not None:
            self._resolve_triggered_effects(bf.card, "on_hide_here", bf, ap,
                                            self.gs.get_player(self.gs.other(side)),
                                            context_extra={"battlefield": bf})
        # "When you hide a card" on the hider's units (Katarina Reckless).
        self._fire_units_trigger("on_hide", side)
        return True

    def _can_hide_pay(self, ap: Player, side: str) -> bool:
        legend = self._legend_unit(side)
        teemo = legend is not None and self._has_effect(legend.card, "hide_for_energy")
        return self._can_pay_generic_power(ap, 1) or (teemo and ap.energy >= 1)

    def _cleanup_hidden_cards(self) -> None:
        """§106.4.d / §322.8: a face-down card whose owner no longer controls its
        battlefield is removed to its owner's trash. Called during end-of-turn
        cleanup."""
        for bf in self.gs.battlefields:
            fd = bf.facedown
            if fd is not None and bf.controller() != fd.owner:
                self.gs.get_player(fd.owner).trash.append(fd.card)
                bf.facedown = None

    def _hidden_playable_lanes(self, side: str) -> list:
        """Battlefields where `side` has a face-down card it may now play for [0]:
        it owns the facedown card and at least one turn has passed since hiding
        (§737.1.b 'beginning on the next turn'). Current control is NOT required —
        the facedown persists until the next Cleanup even if control is lost
        (§106.4.d), and playing a hidden card into a now-contested lane is the
        keyword's whole point. Loss-of-control removal is handled at cleanup."""
        lanes = []
        for i, bf in enumerate(self.gs.battlefields):
            fd = bf.facedown
            if fd is not None and fd.owner == side and self.gs.turn > fd.turn_hidden:
                # "Your opponents' HIDDEN cards can't be revealed here" (Noxus Saboteur).
                if any(self._has_effect(u.card, "no_enemy_reveals_here")
                       for u in bf._units_for(self.gs.other(side))):
                    continue
                lanes.append(i)
        return lanes

    def _play_from_hidden(self, side: str, lane: int) -> bool:
        """Play a face-down card from its Facedown Zone for [0] (§737.1.b). A unit
        enters at that battlefield; a spell resolves on a fresh chain aimed at that
        battlefield (§737.1.c.3 / §737.1.d). Returns True on success."""
        if lane not in self._hidden_playable_lanes(side):
            return False
        bf = self.gs.battlefields[lane]
        fd = bf.facedown
        card = fd.card
        bf.facedown = None
        ap = self.gs.get_player(side)
        if isinstance(card, SpellCard):
            self._spell_played(card, ap, from_zone="facedown")
            self.gs.chain.append(ChainItem(player=side, card=card, bf_idx=lane))
            self._run_chain(side)
        else:  # unit / champion / gear-as-unit → enters at that battlefield
            self._play_unit(card, side, bf=bf, from_zone="facedown")
        if self.verbose:
            print(f"  {side} plays {card.name} from Hidden @BF{lane} for [0]")
        return True

    # ------------------------------------------------------------------
    # Additional costs / kicker at play time (B1)

    def _cost_objects(self, card: Card, ap: Player, ac: dict) -> tuple[str, list, object]:
        """What an additional cost takes from the board: (verb, the legal
        objects, the baseline's pick), or ("", [], None) when it takes nothing.
        `kill_friendly_unit` (with `or_gear`: "a friendly unit or gear"; with
        `unit_filter` {"is_mighty": true}: Sacrifice), `kill_friendly_gear`
        (Zaun Punk), `exhaust_friendly_unit` (a ready one), `exhaust_legend`
        (Bard Mercurial), `return_friendly_unit`. Baseline: what the player
        misses least — a token, then a unit in base (not fighting), then the
        weakest unit or the cheapest gear."""
        side = "A" if ap is self.gs.A else "B"
        units = [u for u in self._friendly_units_of(side) if u.card is not card]
        gear = [g for g in list(ap.base_gear) + self._controlled_attached_gear(side) if g is not card]
        if ac.get("unit_filter", {}).get("is_mighty"):
            units = [u for u in units if u.might >= 5]
        if ac.get("kill_friendly_unit"):
            verb, objs = "kill", units + (gear if ac.get("or_gear") else [])
        elif ac.get("kill_friendly_gear"):
            verb, objs = "kill", gear
        elif ac.get("exhaust_friendly_unit"):
            verb, objs = "exhaust", [u for u in units if u.ready]
        elif ac.get("exhaust_legend"):
            legend = self._legend_unit(side)
            verb, objs = "exhaust", [legend] if legend is not None and legend.ready else []
        elif ac.get("return_friendly_unit"):
            verb, objs = "return", units
        else:
            return "", [], None
        if not objs:
            return verb, [], None

        def spare(o):
            if isinstance(o, UnitInPlay):
                in_base = self._locate_unit(o) is not None and self._locate_unit(o)[1] is None
                return (not o.is_token, not in_base, o.might)
            return (not getattr(o, "is_token", False), False, int(o.cost_energy or 0))
        return verb, objs, min(objs, key=spare)

    @staticmethod
    def _additional_cost_optional(card: Card) -> bool:
        """ "You may ... as an additional cost" (Zed, Dune Devourer, Meditation),
        not "As an additional cost to play this, kill a friendly unit". A kicker
        phrased otherwise ("you may kill another friendly unit or gear to draw
        1") is optional."""
        spec = CARD_REGISTRY.get(card.name)
        text = ((spec.raw or {}).get("effect") or "") if spec else ""
        sentences = [s for s in re.split(r"(?<=[.)])\s+", text) if "additional cost" in s.lower()]
        return not sentences or any("you may" in s.lower() for s in sentences)

    def _try_pay_additional_costs(self, card: Card, ap: Player) -> bool:
        """If the card has an effect carrying an `additional_cost` (kicker), try to
        pay the first affordable one; a "you may" one is the player's choice
        (baseline: pay). Sets `card._kicker_paid = True` when paid. One kicker per
        card. Returns whether anything was paid."""
        spec = CARD_REGISTRY.get(card.name)
        if not (spec and spec.effects):
            return False
        for es in spec.effects:
            ac = getattr(es, "additional_cost", None)
            if not ac:
                continue
            side = "A" if ap is self.gs.A else "B"
            if self._additional_cost_optional(card) and \
                    self._pay_one_additional_cost(card, ap, ac, check_only=True) and \
                    not self.choose("optional:additional_cost", side, [True, False], True, card):
                return False
            if self._pay_one_additional_cost(card, ap, ac):
                card._kicker_paid = True
                if self.verbose:
                    print(f"  {ap.name} pays kicker for {card.name}: {ac}")
                return True
            break  # only the first additional_cost is considered (one kicker/card)
        return False

    def _pay_one_additional_cost(self, card: Card, ap: Player, ac: dict,
                                 check_only: bool = False) -> bool:
        """Check an additional_cost dict is affordable, then pay it atomically.
        Returns True iff fully paid (no partial payment); `check_only`: whether
        it could be."""
        energy = int(ac.get("energy", 0) or 0)
        power = int(ac.get("power", 0) or 0)
        domain = Domain[ac["domain"]] if ac.get("domain") else None
        discard_n = int(ac.get("discard_cards", 0) or 0)

        # --- affordability check (no mutation yet) ---
        if not self._can_pay_energy_and_generic(ap, energy, power, domain):
            return False
        # Never discard the very card being played (it may still be in hand).
        in_hand = any(c is card for c in ap.hand)
        if discard_n and len(ap.hand) < discard_n + (1 if in_hand else 0):
            return False
        verb, objs, target = self._cost_objects(card, ap, ac)
        if verb and target is None:
            return False
        if check_only:
            return True
        side = "A" if ap is self.gs.A else "B"
        if target is not None:
            target = self.choose(f"cost_unit:{verb}", side, objs, target, card)

        # --- payment ---
        if not self._pay_energy_and_generic(ap, energy, power, domain):
            return False
        for _ in range(discard_n):
            idx = next((i for i, c in enumerate(ap.hand) if c is not card), None)
            if idx is None:
                return False
            hand = [c for c in ap.hand if c is not card]
            self._discard(ap, self.choose("discard", side, hand, ap.hand[idx], card))
        if isinstance(target, UnitInPlay):
            where = self._locate_unit(target)
            if verb == "exhaust":
                self._exhaust(target)
            elif where is not None:
                if where[1] is None:
                    ap.base_units.remove(target)
                else:
                    where[1].remove_unit(side, target)
                if verb == "kill":
                    # It dies (DEATHKNELL, "when a friendly unit dies"); a token
                    # ceases to exist.
                    self._route_deaths([(target, side)], where[1] or self.gs.battlefields[0],
                                       in_base=where[1] is None)
                else:
                    ap.base_gear.extend(target.gear)
                    target.gear = []
                    if not target.is_token:
                        ap.hand.append(target.card)
                    self._fire_leaves_board(target.card, side, where[1] or self.gs.battlefields[0])
            # "... no more Energy and no more Power than the killed unit"
            # (Heedless Resurrection) reads the unit this cost took.
            card._cost_unit = target.card
        elif target is not None:
            self._remove_gear(target, ap)
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
        for lu in (self.gs.legend_unit_A, self.gs.legend_unit_B):
            if lu is not None and lu.card is card:
                return lu
        return None

    def _action_fingerprint(self, ap: Player, op: Player):
        """Cheap signature of everything a turn action can change. Used by the
        action loop to detect a no-op (an action the engine silently refuses) so
        the agent can't spin on it forever."""
        gs = self.gs

        def player_sig(p: Player):
            side = "A" if p is gs.A else "B"
            legend = self._legend_unit(side)
            return (
                len(p.hand), len(p.deck.cards), len(p.trash), len(p.banished),
                len(p.base_units), len(p.base_gear), p.energy,
                tuple(sorted((d.name, n) for d, n in p.power_pool.items())),
                p.total_runes_in_play(),
                tuple(sorted(u.card.name for u in p.base_units if u.ready)),
                sum(u.might for u in p.base_units),
                sum(1 for g in p.base_gear if getattr(g, "tapped", False)),
                legend is not None and legend.ready,
                p.earmarked_energy_showdown, p.earmarked_power_gear,
            )

        board = tuple(
            (len(bf.units_A), len(bf.units_B),
             sum(u.might for u in bf.units_A), sum(u.might for u in bf.units_B),
             sum(u.ready for u in bf.units_A + bf.units_B))
            for bf in gs.battlefields
        )
        return (
            player_sig(ap), player_sig(op), board,
            gs.points_A, gs.points_B, len(gs.chain),
            gs.get_xp("A"), gs.get_xp("B"),
        )

    # ------------------------------------------------------------------
    # Playing a card: one procedure for every zone (hand, Champion Zone, face
    # down, trash, banishment, top of deck) and every timing (main phase, chain,
    # showdown). Callers pay the card's own cost (or ignore it) and take the card
    # out of its zone; everything that happens AS a card is played lives here.

    def _effective_cost(self, card: Card, actor: Player,
                        lane: Optional[int] = None, from_zone: str = "hand") -> tuple[int, Optional[int]]:
        """(energy, power) `actor` pays to play `card`: the printed cost minus the
        card's own reductions. A spell aimed at battlefield `lane` also pays the
        DEFLECT surcharge there and gets that battlefield's discount."""
        printed = int(card.cost_energy or 0)
        energy = printed - self._cost_reduction(card, actor)
        power = card.cost_power
        side = "A" if actor is self.gs.A else "B"
        if from_zone != "hand" and self._has_effect(card, "reduce_cost_not_from_hand"):
            energy -= 2                                    # Void Drone
        extras = self._cost_extras(card, side) if from_zone == "hand" else {}
        energy -= extras.get("energy", 0)
        if power:
            power = max(0, power - extras.get("power", 0))
        if isinstance(card, GearCard) and self._orianna_discount_ready(side):
            energy -= 1                                    # Orianna Mechanical Marvel
            if power:
                power = max(0, power - 1)
        if isinstance(card, SpellCard):
            energy += self._vex_cheerless_delta(side, energy)
        if isinstance(card, SpellCard) and lane is not None:
            energy += self._deflect_surcharge(card, lane, side)
            e_red, p_red = self._bf_cost_reduction(card, lane)
            energy -= e_red
            if power is not None and p_red:
                power = max(0, power - p_red)
        aura, floor = self._aura_reduction(card, actor)
        if aura:
            # "reduced by [1], to a minimum of [1]": never below the floor, and
            # never raises a card that already costs less than it.
            energy = max(min(energy, floor), energy - aura)
        if isinstance(card, SpellCard):
            energy += self._enemy_spell_tax(side)
        if card.has_keyword("REACTION") and self.gs.showdown_active and self.gs.showdown_bf_idx is not None:
            sbf = self.gs.battlefields[self.gs.showdown_bf_idx]
            if sbf.card is not None and self._has_effect(sbf.card, "reaction_tax_in_showdown"):
                energy += 1     # Mystic Vortex: [rune] more, paid as Energy
        if power:
            power = max(0, power - self._aura_power_reduction(card, actor))
        discount = self._next_card_discount(card, side)
        if discount is not None:
            energy -= int(discount.get("energy", 0))
            if power:
                power = max(0, power - int(discount.get("power", 0)))
        return max(0, energy), power

    def _cost_extras(self, card: Card, side: str) -> dict:
        """What a card lets you spend as you play it to cost less (baseline:
        all of it): Kraken Hunter's buffs ([body] each), Commander Ledros's
        friendly units ([order] each; tokens only), Poppy Defender's 3 XP ([3])."""
        spec = CARD_REGISTRY.get(card.name)
        out: dict = {}
        for es in (spec.effects if spec else ()):
            kind = es.effect
            if kind == "spend_buffs_for_power":
                n = min(int(card.cost_power or 0),
                        sum(1 for u in self._friendly_units_of(side) if u.might_counters > 0))
                if n:
                    out.update(power=n, buffs=n)
            elif kind == "kill_tokens_for_power":
                n = min(int(card.cost_power or 0),
                        sum(1 for u in self._friendly_units_of(side) if u.is_token))
                if n:
                    out.update(power=n, tokens=n)
            elif kind == "spend_xp_for_energy":
                xp = int(es.params.get("xp", 3))
                if self.gs.get_xp(side) >= xp:
                    out.update(energy=int(es.params.get("amount", 3)), xp=xp)
        return out

    def _choose_cost_extras(self, card: Card, ap: Player, extras: dict, energy: int, power):
        """How much of `extras` the player spends (GameLoop.choose; baseline: all
        of it). Each buff or token not spent is one Power back on the cost, unspent
        XP its Energy; only affordable amounts are offered. Returns (extras,
        energy, power)."""
        if not extras or self.chooser is None:
            return extras, energy, power
        side = "A" if ap is self.gs.A else "B"
        options = [(extras, energy, power)]
        key = "buffs" if "buffs" in extras else "tokens" if "tokens" in extras else None
        if key:
            for k in range(extras[key] - 1, -1, -1):
                back = extras[key] - k
                less = {**extras, key: k, "power": k} if k else {x: v for x, v in extras.items()
                                                                if x not in (key, "power")}
                options.append((less, energy, (power or 0) + back))
        if "xp" in extras:
            less = {x: v for x, v in extras.items() if x not in ("xp", "energy")}
            options.append((less, energy + extras.get("energy", 0), power))
        options = [o for o in options if o is options[0] or self._can_pay_card(ap, card, o[1], o[2])]
        return self.choose("cost_extras", side, options, options[0], card)

    def _spend_cost_extras(self, extras: dict, side: str) -> None:
        """Pay what _cost_extras said the play spends."""
        for _ in range(extras.get("buffs", 0)):
            holder = self._buff_to_spend(side, None, "any")
            if holder is not None:
                holder.might_counters -= 1
        for _ in range(extras.get("tokens", 0)):
            tokens = [u for u in self._friendly_units_of(side) if u.is_token]
            if tokens:
                victim = min(tokens, key=lambda u: u.might)
                where = self._locate_unit(victim)
                if where[1] is None:
                    self.gs.get_player(side).base_units.remove(victim)
                else:
                    where[1].remove_unit(side, victim)
                self._route_deaths([(victim, side)], where[1] or self.gs.battlefields[0],
                                   in_base=where[1] is None)
        if extras.get("xp"):
            self.gs.add_xp(side, -extras["xp"])

    def _adjust_ability_cost(self, unit, eff, parsed: dict, side: str) -> dict:
        """ "EMPOWER costs of your units here cost [1] or [Rune] less" (Risen
        Altar): Energy first, else Power."""
        if eff.effect != "empower_self" or unit is None:
            return parsed
        where = self._locate_unit(unit)
        bf = where[1] if where else None
        if bf is None or bf.card is None or bf.controller() != side or \
                not self._has_effect(bf.card, "empower_discount_here"):
            return parsed
        parsed = dict(parsed)
        if parsed["energy"]:
            parsed["energy"] -= 1
        elif parsed["power"]:
            parsed["power"] -= 1
        return parsed

    def _orianna_discount_ready(self, side: str) -> bool:
        """ "Once each turn, while I'm at a battlefield, you may pay [1] [rune]
        less to play a gear" (Orianna Mechanical Marvel), not used yet this turn."""
        return any(self.gs.once_per_turn_used.get((id(u.card), "orianna")) != self.gs.turn
                   for u in self._units_at_battlefields_with(side, "gear_discount_once"))

    def _vex_cheerless_delta(self, side: str, energy: int) -> int:
        """ "While I'm in combat, friendly spells cost [1][rune] less to a minimum
        of [1], and enemy spells cost [1][rune] more" (Vex Cheerless): during a
        showdown at Vex's battlefield; [1][rune] counted as 2 Energy."""
        gs = self.gs
        if not gs.showdown_active or gs.showdown_bf_idx is None:
            return 0
        bf = gs.battlefields[gs.showdown_bf_idx]
        delta = 0
        for s in ("A", "B"):
            if any(self._has_effect(u.card, "vex_cheerless") for u in bf._units_for(s)):
                delta += -min(2, max(0, energy - 1)) if s == side else 2
        return delta

    def _destination_surcharge(self, card: Card, dst, side: str) -> int:
        """Extra generic Power `side` pays to play `card` to battlefield `dst`:
        Dragon Roost ("Any player may pay [rune] [rune] as an additional cost to
        play a Dragon. If they do, they play it to this battlefield") — unless
        they control it, where the unit could go anyway."""
        if dst is None:
            return 0
        bf = self.gs.battlefields[dst]
        if bf.card is not None and self._has_effect(bf.card, "dragon_roost") and                 "Dragon" in (card.tags or []) and bf.controller() != side:
            return 2
        return 0

    def _enemy_spell_tax(self, side: str) -> int:
        """ "Opponents' spells cost [1] more. If this is EMPOWERED, they cost
        [1] [rune] more instead" (Helm of Suppression): what `side`'s spells
        cost extra ([rune] paid as Energy, as DEFLECT's surcharge is)."""
        total = 0
        for src, _bf in self._sources_in_play(self.gs.other(side)):
            spec = CARD_REGISTRY.get(src.name)
            for es in (spec.effects if spec else ()):
                if es.effect == "enemy_spell_tax":
                    total += int(es.params.get("amount", 1))
                    if self._is_empowered(src):
                        total += int(es.params.get("empowered_extra", 0))
        return total

    def _aura_reduction(self, card: Card, actor: Player, flow: bool = False) -> tuple[int, int]:
        """Energy that `actor`'s in-play sources take off `card`'s cost ("While
        I'm at a battlefield, spells you play cost [1] less, to a minimum of
        [1]"): `cost_aura` effects (verb reduce_cost) whose condition holds for
        their source and whose `filter` matches the card. Returns (total, the
        highest `min_cost` floor among them). `flow`: the card is played from
        the trash for its FLOW cost, which `flow_only` auras also reduce
        (Stargazer)."""
        from .effects import _zone_effect_card_ok
        side = "A" if actor is self.gs.A else "B"
        opponent = self.gs.get_player(self.gs.other(side))
        total, floor = 0, 0
        for src, bf in self._sources_in_play(side):
            if src is card:
                continue
            spec = CARD_REGISTRY.get(src.name)
            for es in (spec.effects if spec else ()):
                if es.trigger != "cost_aura" or es.effect != "reduce_cost":
                    continue
                if es.params.get("flow_only") and not flow:
                    continue
                if not _zone_effect_card_ok(card, {"target_filter": es.params.get("filter") or {}}):
                    continue
                if not self._check_condition(es.condition, src, actor, opponent,
                                             {"battlefield": bf, "triggering_card": card}):
                    continue
                total += int(es.params.get("amount", 1))
                floor = max(floor, int(es.params.get("min_cost", 0)))
        return total, floor

    def _aura_power_reduction(self, card: Card, actor: Player) -> int:
        """Power that `cost_aura` effects take off `card` ("cost [1] [rune] less")."""
        from .effects import _zone_effect_card_ok
        side = "A" if actor is self.gs.A else "B"
        opponent = self.gs.get_player(self.gs.other(side))
        total = 0
        for src, bf in self._sources_in_play(side):
            spec = CARD_REGISTRY.get(src.name) if src is not card else None
            for es in (spec.effects if spec else ()):
                if es.trigger == "cost_aura" and es.effect == "reduce_cost" and es.params.get("power") \
                        and _zone_effect_card_ok(card, {"target_filter": es.params.get("filter") or {}}) \
                        and self._check_condition(es.condition, src, actor, opponent,
                                                  {"battlefield": bf, "triggering_card": card}):
                    total += int(es.params["power"])
        return total

    def _sources_in_play(self, side: str) -> list:
        """(card, battlefield) for everything `side` has in play that can carry an
        ability: units (and their gear) at battlefields and in base, base gear,
        deployed gear and the legend. Base sources report battlefields[0]."""
        ap = self.gs.get_player(side)
        anchor = self.gs.battlefields[0]
        out = []
        for bf in self.gs.battlefields:
            for u in bf._units_for(side):
                out.append((u.card, bf))
                out.extend((g, bf) for g in u.gear)
            out.extend((dg.card, bf) for dg in bf.gear_for(side))
        for u in ap.base_units:
            out.append((u.card, anchor))
            out.extend((g, anchor) for g in u.gear)
        out.extend((g, anchor) for g in ap.base_gear)
        legend = self._legend_unit(side)
        if legend is not None:
            out.append((legend.card, anchor))
        return out

    def _next_card_discount(self, card: Card, side: str):
        """The first waiting "next card you play costs less" discount that applies
        to `card`, or None."""
        from .effects import _zone_effect_card_ok
        for d in self.gs.next_card_discounts.get(side, ()):
            if _zone_effect_card_ok(card, {"target_filter": d.get("filter") or {}}):
                return d
        return None

    def _can_pay_card(self, actor: Player, card: Card, energy: int, power) -> bool:
        """Whether `actor` can pay this cost for `card` now. Gear may use Ornn's
        earmarked gear power, spells Kai'Sa's earmarked spell power; during a
        showdown Diana's showdown energy counts. Units and gear may use
        Mordekaiser's earmarked power."""
        if self._play_forbidden(actor, card):
            return False
        if isinstance(card, (UnitCard, GearCard)) and power:
            power = max(0, power - actor.earmarked_power_permanent)
        if isinstance(card, GearCard):
            return self._can_pay_gear(actor, energy, power, card.cost_power_domain)
        if isinstance(card, SpellCard):
            power = max(0, (power or 0) - actor.earmarked_power_spell) if power else power
            energy = max(0, energy - actor.earmarked_energy_spell)
        if self.gs.showdown_active:
            return self._can_pay_showdown(actor, energy, power, card.cost_power_domain)
        return actor.can_pay_cost(energy, power, card.cost_power_domain)

    def _pay_card(self, actor: Player, card: Card, energy: int, power) -> bool:
        if not self._can_pay_card(actor, card, energy, power):
            return False
        if isinstance(card, (UnitCard, GearCard)) and power:
            from_earmark = min(power, actor.earmarked_power_permanent)
            actor.earmarked_power_permanent -= from_earmark
            power -= from_earmark
        if isinstance(card, GearCard):
            return self._pay_gear(actor, energy, power, card.cost_power_domain)
        if isinstance(card, SpellCard):
            if power:
                from_earmark = min(power, actor.earmarked_power_spell)
                actor.earmarked_power_spell -= from_earmark
                power -= from_earmark
            from_earmark = min(energy, actor.earmarked_energy_spell)
            actor.earmarked_energy_spell -= from_earmark
            energy -= from_earmark
        if self.gs.showdown_active:
            return self._pay_showdown(actor, energy, power, card.cost_power_domain)
        return actor.pay_cost(energy, power, card.cost_power_domain)

    def _count_card_played(self, card: Card, side: str) -> None:
        """Count a played card for the "this turn" counters (LEGION, "your second
        card", "for each card you've played"). Tokens are not cards and don't count."""
        gs = self.gs
        discount = self._next_card_discount(card, side)
        if discount is not None:
            gs.next_card_discounts[side].remove(discount)   # "the next card": used up
        gs.played_cards_this_turn[side].append(card)
        gs.cards_played_this_turn[side] = gs.cards_played_this_turn.get(side, 0) + 1
        if isinstance(card, SpellCard):
            gs.spells_played_this_turn[side] = gs.spells_played_this_turn.get(side, 0) + 1

    def _note_card_played(self, card: Card, side: str, from_zone: str = "hand") -> None:
        """Count a played card and fire its owner's "when you play a card" abilities."""
        self._count_card_played(card, side)
        self._fire_card_played(side, card, from_zone)

    def _fire_card_played(self, side: str, card: Card, from_zone: str) -> None:
        """on_card_played for `side`'s units, legend and gear (not the card itself).
        Conditions see the played card as triggering_card and its origin zone."""
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        anchor = self.gs.battlefields[0]
        sources = []  # (card, battlefield it is at)
        for bf in self.gs.battlefields:
            for u in (bf.units_A if side == "A" else bf.units_B):
                sources.append((u.card, bf))
                sources.extend((g, bf) for g in u.gear)
            sources.extend((dg.card, bf) for dg in bf.gear_for(side))
        for u in actor.base_units:
            sources.append((u.card, anchor))
            sources.extend((g, anchor) for g in u.gear)
        sources.extend((g, anchor) for g in actor.base_gear)
        legend_unit = self._legend_unit(side)
        if legend_unit is not None:
            sources.append((legend_unit.card, anchor))
        # Its own "When you play me from face down" (Tornado Warrior).
        own = self._find_unit_by_card(card)
        own_bf = (self._locate_unit(own)[1] if own is not None else None) or anchor
        self._resolve_triggered_effects(card, "on_self_played", own_bf, actor, opponent,
                                        context_extra={"battlefield": own_bf,
                                                       "triggering_card": card,
                                                       "from_zone": from_zone})
        # Cards in the trash that answer it (Meticulous Restorationist).
        for src in list(actor.trash):
            self._resolve_triggered_effects(src, "trash_on_card_played", anchor, actor, opponent,
                                            context_extra={"battlefield": anchor,
                                                           "triggering_card": card,
                                                           "from_zone": from_zone})
        for src, bf in sources:
            if src is card:
                continue
            self._resolve_triggered_effects(src, "on_card_played", bf, actor, opponent,
                                            context_extra={"battlefield": bf,
                                                           "triggering_card": card,
                                                           "from_zone": from_zone})

    def _pay_accelerate(self, card: Card, ap: Player, granted: bool = False) -> bool:
        """ACCELERATE (§731): optional additional cost of [1] + 1 Power of the
        unit's domain ([A] if no/multi domain) to enter ready. Routed through the
        agent (default yes). Returns whether it was paid. `granted`: an effect
        gives it ACCELERATE."""
        if not (card.has_keyword("ACCELERATE") or granted):
            return False
        domain = card.domain
        if domain is not None:
            can = ap.can_pay_cost(1, 1, domain)
        else:
            can = ap.energy >= 1 and self._can_pay_generic_power(ap, 1)
        if not (can and self._wants_optional_keyword(ap, card, "accelerate")):
            return False
        if domain is not None:
            ap.pay_cost(1, 1, domain)
        else:
            ap.energy -= 1
            self._pay_generic_power(ap, 1)
        return True

    def _play_unit(self, card: Card, side: str, *, bf: Optional[Battlefield] = None,
                   ready: bool = False, from_zone: str = "hand",
                   accelerate: bool = True) -> UnitInPlay:
        """A unit card is played from any zone: ACCELERATE, it enters (its base,
        or `bf`), additional costs, SHOW OFF, the play counters, "when you play
        me", WEAPONMASTER, then its controller's "when you play a unit"
        abilities. The caller paid (or ignored) its cost and took it out of its
        zone. Contesting a battlefield is the caller's business."""
        ap = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        # "Friendly units played from anywhere other than a player's hand have
        # ACCELERATE" (Rek'Sai Breacher).
        granted = from_zone != "hand" and self._side_has_passive(side, "accelerate_non_hand")
        if self.gs.next_unit_accelerate.get(side) == self.gs.turn:
            del self.gs.next_unit_accelerate[side]       # Firelights' Hideout: used up
            granted = True
        if accelerate and self._pay_accelerate(card, ap, granted=granted):
            ready = True
        last_caress = self.gs.next_unit_any_bf.get(side) == self.gs.turn
        if last_caress:
            del self.gs.next_unit_any_bf[side]       # "the next unit you play": used up
        if self._enters_ready(card, side, bf):
            ready = True
        if self.gs.next_units_enter_ready.get(side, 0) > 0:
            self.gs.next_units_enter_ready[side] -= 1    # "the next unit": used up
            ready = True
        unit = UnitInPlay(card=card, ready=ready)
        if last_caress:
            unit.might_counters = max(unit.might_counters, 1)   # "When you play it, BUFF it"
        if bf is None:
            ap.base_units.append(unit)
        else:
            bf.add_unit(side, unit)
        self.units_played += 1
        # B1: optional additional cost (kicker), paid before resolution.
        self._try_pay_additional_costs(card, ap)
        self._show_off(card, ap)
        self._count_card_played(card, side)
        self._resolve_card_effects(card, bf or self.gs.battlefields[0], ap, opponent)

        # WEAPONMASTER (§747): choose an Equipment you control, pay its real
        # Equip cost reduced by [A] (1 Power of any domain), and attach it to
        # this unit. First affordable Equipment among base gear.
        if card.has_keyword("WEAPONMASTER"):
            for gear_card in list(ap.base_gear):
                base_cost = self._equip_cost(gear_card)
                if base_cost is None:
                    continue
                reduced = self._equip_cost_minus_A(base_cost)
                if self._can_pay_equip(ap, reduced) and self._pay_equip(ap, reduced):
                    ap.base_gear.remove(gear_card)
                    unit.gear.append(gear_card)
                    if self.verbose:
                        print(f"  {ap.name} WEAPONMASTER attaches {gear_card.name} to {card.name}")
                    self._fire_attached(unit, side)
                    break

        self._fire_units_trigger("on_friendly_unit_played", side, exclude_card=card)
        self._fire_enemy_unit_played(unit, side)
        self._fire_card_played(side, card, from_zone)
        self._unit_play_draw(side)
        self._vision(card, side)
        return unit

    def _vision(self, card: Card, side: str) -> None:
        """VISION (migrated to PREDICT 1): "When you play me, look at the top card
        of your Main Deck. You may recycle it." Unless the card's spec already
        predicts when played."""
        n = card.keyword_value("PREDICT") if card.has_keyword("PREDICT") else 0
        spec = CARD_REGISTRY.get(card.name)
        if not n or (spec and any(es.effect == "predict" and es.trigger == "on_play"
                                  for es in spec.effects)):
            return
        ctx = EffectContext(self, card, self.gs.get_player(side),
                            self.gs.get_player(self.gs.other(side)), self.gs.battlefields[0])
        EFFECT_REGISTRY["predict"](ctx, {"amount": n})

    def _fire_enemy_unit_played(self, unit: UnitInPlay, side: str) -> None:
        """`side` played `unit` (a card or a token): the opponent's "when an
        opponent plays a unit" (on_enemy_unit_played) abilities, with the unit as
        triggering_unit (Vex Apathetic stuns it)."""
        self._fire_units_trigger("on_enemy_unit_played", self.gs.other(side),
                                 triggering_card=unit.card,
                                 extra={"triggering_unit": unit})

    def _play_gear(self, card: Card, side: str, lane: int = 0, from_zone: str = "hand") -> None:
        """A gear card is played from any zone (cost already handled, card out of
        its zone). §146.1.a.1: gear goes to the controller's BASE, unattached;
        Equipment attaches later via its Equip ability, never for free on play.
        Exceptions: QUICK-DRAW (§745.1.d) attaches to a unit you control as it is
        played; DEPLOY (§830.1.a) gear go to a battlefield."""
        ap = self.gs.get_player(side)
        if from_zone == "hand":
            for u in self._units_at_battlefields_with(side, "gear_discount_once"):
                key = (id(u.card), "orianna")
                if self.gs.once_per_turn_used.get(key) != self.gs.turn:
                    self.gs.once_per_turn_used[key] = self.gs.turn     # used up
                    break
        attached_to = None
        deployed_bf = None
        if card.has_keyword("DEPLOY"):
            deployed_bf = self.gs.battlefields[lane]
        elif card.has_keyword("QUICK-DRAW"):
            target_bf = self.gs.battlefields[lane]
            friendly_units = target_bf.units_A if side == "A" else target_bf.units_B
            if friendly_units:
                attached_to = self.choose("equip", side, list(friendly_units), friendly_units[0], card)
                attached_to.gear.append(card)
                self._fire_attached(attached_to, side)
        if deployed_bf is not None:
            self._deploy_gear(side, deployed_bf, card)
        elif attached_to is None:
            ap.base_gear.append(card)
        # "This enters exhausted" gear cannot use its [tap] ability the turn
        # it is played (§ enters exhausted) — it untaps on the next turn.
        _gspec = CARD_REGISTRY.get(card.name)
        if _gspec and "enters exhausted" in ((_gspec.raw or {}).get("effect") or "").lower():
            card.tapped = True
        if self.verbose:
            if attached_to is not None:
                print(f"  {side} plays GEAR (QUICK-DRAW): {card.name} -> {attached_to.card.name}")
            elif deployed_bf is None:
                print(f"  {side} plays GEAR: {card.name} (to base)")

        # "When you play this" gear effects. A deployed gear's "here" is
        # its battlefield.
        play_bf = deployed_bf or self.gs.battlefields[lane]
        opponent = self.gs.get_player(self.gs.other(side))
        self._show_off(card, ap)
        self._count_card_played(card, side)
        self._resolve_card_effects(card, play_bf, ap, opponent)
        self._fire_card_played(side, card, from_zone)
        self._vision(card, side)
        self._fire_units_trigger("on_enemy_gear_played", self.gs.other(side), triggering_card=card)
        if deployed_bf is not None:
            # "When you play a gear with DEPLOY, ..." (Jarvan IV Exemplar).
            self._fire_units_trigger("on_friendly_deploy", side, triggering_card=card,
                                     extra={"deployed_at": deployed_bf})

    def _cast_spell_now(self, card: Card, side: str, lane: int = 0,
                        from_zone: str = "hand") -> None:
        """Play a spell from a zone other than hand as part of an effect ("play a
        spell from your trash"): it is played, goes on a chain and resolves (the
        opponent may react). Cost already handled, card out of its zone."""
        ap = self.gs.get_player(side)
        self._spell_played(card, ap, from_zone=from_zone)
        self.gs.chain.append(ChainItem(player=side, card=card, bf_idx=lane))
        self._run_chain(side)

    def _spell_played(self, card: Card, ap: Player, from_zone: str = "hand") -> None:
        """A spell is played from any zone, after its cost is paid and it left
        that zone, before it goes on the chain: additional costs (kicker),
        REPEAT, SHOW OFF, and the play counters."""
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
        side_ = "A" if ap is self.gs.A else "B"
        card._granted_repeat = False
        if self.gs.next_spell_repeat.get(side_) == self.gs.turn:
            del self.gs.next_spell_repeat[side_]          # Temporal Portal: used up
            card._granted_repeat = True
        if self.gs.showdown_active and self.gs.showdown_bf_idx is not None and any(
                self._has_effect(u.card, "spells_repeat_in_showdown")
                for u in self.gs.battlefields[self.gs.showdown_bf_idx]._units_for(side_)):
            card._granted_repeat = True                   # Syndra Transcendent
        if card.has_keyword("REPEAT") or card._granted_repeat:
            card._repeat_paid = self._pay_repeat(card, ap)
        self._show_off(card, ap)
        side = "A" if ap is self.gs.A else "B"
        if self.gs.next_spell_bonus.get(side) == self.gs.turn:
            card._bonus_damage_turn = self.gs.turn      # Ravenborn Tome
            del self.gs.next_spell_bonus[side]
        self._note_card_played(card, side, from_zone)

    def _play_token(self, name: str, side: str, *, bf: Optional[Battlefield] = None,
                    ready: bool = False, might: Optional[int] = None):
        """Play a token (§179). Tokens are not cards (§185): they don't count as a
        card played and cease to exist off the board (§186.1, see _to_trash). A
        unit token enters its controller's base or `bf` (exhausted unless
        `ready`) and is a unit played ("when you play a unit"); a gear token goes
        to base. Returns the UnitInPlay or the gear card (None if unknown)."""
        spec = CARD_REGISTRY.get(name)
        if spec is None:
            return None
        card = spec.instantiate()
        card.is_token = True
        if might is not None:
            card.might = int(might)
        ap = self.gs.get_player(side)
        if not isinstance(card, GearCard):
            # "If you would play a unit token ... you may play a 3 [might] Mech
            # unit token ... instead" (Heimerdinger Academy Instructor), when bigger.
            if name != "Mech" and int(card.might or 0) < 3 and \
                    self._units_at_battlefields_with(side, "mech_instead_of_tokens"):
                return self._play_token("Mech", side, bf=bf, ready=ready, might=3)
            # "Once each turn ... play that token and an additional copy of it"
            # (Zilean Time Mage).
            for z in self._units_at_battlefields_with(side, "double_tokens_once"):
                key = (id(z.card), "double_tokens_once")
                if self.gs.once_per_turn_used.get(key) != self.gs.turn:
                    self.gs.once_per_turn_used[key] = self.gs.turn
                    self._play_token(name, side, bf=bf, ready=ready, might=might)
                    break
        if isinstance(card, GearCard):
            card.tapped = not ready
            if card.has_keyword("DEPLOY"):
                # "Play this only to a battlefield" (a Bomb): `bf`, else where
                # the opponent has the most units.
                from .battlefield import DeployedGear
                enemy = self.gs.other(side)
                where = bf or max(self.gs.battlefields, key=lambda b: (b.count(enemy), -self.gs.battlefields.index(b)))
                where.gear_for(side).append(DeployedGear(card=card, is_token=True))
                return card
            ap.base_gear.append(card)
            return card
        unit = UnitInPlay(card=card, ready=ready or self._enters_ready(card, side, bf),
                          is_token=True)
        if bf is None:
            ap.base_units.append(unit)
        else:
            bf.add_unit(side, unit)
        self._fire_units_trigger("on_friendly_unit_played", side, exclude_card=card)
        self._fire_enemy_unit_played(unit, side)
        self._unit_play_draw(side)
        return unit

    def _unit_played_here(self, bf: Battlefield, side: str, unit: UnitInPlay) -> None:
        """ "When a player plays a unit here" (Valley of Idols)."""
        if bf.card is not None:
            self._resolve_triggered_effects(bf.card, "on_unit_played_here", bf,
                                            self.gs.get_player(side),
                                            self.gs.get_player(self.gs.other(side)),
                                            context_extra={"battlefield": bf, "triggering_unit": unit})

    def _unit_play_draw(self, side: str) -> None:
        """ "The next three times you play a unit this turn, draw 1" (Fanfare)."""
        entry = self.gs.unit_play_draws.get(side)
        if entry and entry[0] == self.gs.turn and entry[1] > 0:
            entry[1] -= 1
            player = self.gs.get_player(side)
            self._draw_one(player)

    def _play_permissions(self, card: Card, side: str) -> set:
        """Where else than base or a battlefield it controls `side` may play
        unit `card`: "open" (Sai Scout, and Miss Fortune Buccaneer's friendly
        units), "occupied_enemy" (Dauntless Vanguard), "enemy_alone" (Arachnoid
        Horror), "any" (Last Caress's next unit), or "conquered_this_turn_only"
        (Perched Grimwyrm)."""
        perms = set()
        spec = CARD_REGISTRY.get(card.name)
        for es in (spec.effects if spec else ()):
            if es.effect == "play_location":
                perms.add(str(es.params.get("where")))
        for src, _bf in self._sources_in_play(side):
            sspec = CARD_REGISTRY.get(src.name)
            for es in (sspec.effects if sspec else ()):
                if es.effect == "play_location_aura":
                    perms.add(str(es.params.get("where")))
        if self.gs.next_unit_any_bf.get(side) == self.gs.turn:
            perms.add("any")
        return perms

    def _unit_play_destinations(self, card: Card, side: str) -> list:
        """Where `side` may play unit `card` now (§ a unit is played to its
        controller's base or a battlefield they control): None for base, and
        battlefield indices. Rockfall Path ("Units can't be played here") and
        an opponent's Mageseeker Warden at a battlefield ("opponents can only
        play units to their base") restrict it."""
        gs = self.gs
        opp = gs.other(side)
        perms = self._play_permissions(card, side)
        only_conquered = "conquered_this_turn_only" in perms
        out = [] if only_conquered else [None]
        if self._units_at_battlefields_with(opp, "warden_only_base"):
            return out
        for i, bf in enumerate(gs.battlefields):
            if bf.card is not None and self._has_effect(bf.card, "no_unit_plays_here"):
                continue
            mine, theirs = bf._units_for(side), bf._units_for(opp)
            if only_conquered:
                ok = bf.conquered_turn.get(side) == gs.turn
            else:
                pets = ("Bird", "Cat", "Dog", "Poro")
                ok = (bf.controller() == side or "any" in perms
                      or (bf.card is not None and self._has_effect(bf.card, "dragon_roost")
                          and "Dragon" in (card.tags or []))
                      or ("pet_battlefield" in perms and any(t in u.tags for u in mine for t in pets))
                      or ("open" in perms and not mine and not theirs and bf.controller() is None)
                      or ("occupied_enemy" in perms and bool(theirs))
                      or ("enemy_alone" in perms and len(theirs) == 1))
            if ok:
                out.append(i)
        return out

    def _arrive_at(self, bf: Battlefield, side: str, prev_controller) -> None:
        """A unit was played to `bf`: it contests the battlefield if `side`
        didn't control it (§190.3.a.1); the showdown follows like a move's."""
        dst = self.gs.battlefields.index(bf)
        bf.prev_controller = prev_controller
        gained = prev_controller != side and bf.controller() == side
        if gained or (bf.units_A and bf.units_B):
            bf.contested_this_turn = True
            if self.gs.pending_move is None and not self.gs.showdown_active and not self.gs.chain:
                self.gs.pending_move = (dst, side)

    def _ambush_unit_lanes(self, card: Card, side: str) -> list:
        """The battlefields a unit card in hand may be played to at reaction
        speed: AMBUSH ("as a REACTION to a battlefield where you have units"), a
        REACTION unit to a battlefield you control, Rengar Pouncing also to a
        battlefield you're attacking."""
        gs = self.gs
        lanes = set()
        if card.has_keyword("AMBUSH"):
            lanes |= {i for i, bf in enumerate(gs.battlefields) if bf._units_for(side)}
        if card.has_keyword("REACTION"):
            lanes |= {i for i, bf in enumerate(gs.battlefields) if bf.controller() == side}
            if "attacking" in self._play_permissions(card, side) and gs.showdown_active                     and gs.showdown_attacker == side and gs.showdown_bf_idx is not None:
                lanes.add(gs.showdown_bf_idx)
        if self._units_at_battlefields_with(gs.other(side), "warden_only_base"):
            return []
        return sorted(i for i in lanes if not (gs.battlefields[i].card is not None and
                                               self._has_effect(gs.battlefields[i].card, "no_unit_plays_here")))

    def _play_ambush_unit(self, ap: Player, idx: int, lane) -> bool:
        """Play an AMBUSH unit from hand to `lane` at reaction speed."""
        side = "A" if ap is self.gs.A else "B"
        if not (0 <= idx < len(ap.hand)) or lane not in self._ambush_unit_lanes(ap.hand[idx], side):
            return False
        card = ap.hand[idx]
        energy, power = self._effective_cost(card, ap)
        if not self._pay_card(ap, card, energy, power):
            return False
        ap.remove_from_hand(idx)
        bf = self.gs.battlefields[lane]
        if self.verbose:
            print(f"  {side} AMBUSH-plays {card.name} @BF{lane}")
        self._play_unit(card, side, bf=bf)
        if bf.units_A and bf.units_B:
            bf.contested_this_turn = True
            self._run_showdown(lane, attacker=side)
        return True

    def _enters_ready(self, card: Card, side: str, bf: Optional[Battlefield]) -> bool:
        """Whether a unit `side` plays (a card or token, to `bf` or base) enters
        ready by an effect: "Units you play this turn enter ready" (Confront), or
        an `enter_ready_aura` of something `side` has in play whose filter
        matches it and whose condition holds ("Other friendly units enter ready",
        "Your tokens enter ready", "Units you play to battlefields you control")."""
        from .effects import _zone_effect_card_ok
        if self.gs.units_enter_ready_turn.get(side) == self.gs.turn:
            return True
        actor = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        for src, src_bf in self._sources_in_play(side):
            if src is card:
                continue
            spec = CARD_REGISTRY.get(src.name)
            for es in (spec.effects if spec else ()):
                if es.trigger != "enter_ready_aura":
                    continue
                if not _zone_effect_card_ok(card, {"target_filter": es.params.get("filter") or {}}):
                    continue
                if self._check_condition(es.condition, src, actor, opponent,
                                         {"battlefield": src_bf, "triggering_card": card,
                                          "played_to": bf}):
                    return True
        return False

    @staticmethod
    def _to_trash(owner: Player, card: Card) -> None:
        """Put a card that left the board into its owner's trash; a token ceases
        to exist instead (§186.1)."""
        if getattr(card, "empowered", False):
            card.empowered = False
        if not getattr(card, "is_token", False):
            owner.trash.append(card)

    def _standard_move(self, unit: UnitInPlay, side: str, src: int, dst: int) -> None:
        """A unit's Standard Move (§144) from location `src` to `dst` (battlefield
        index, or len(battlefields) for base): exhaust it (the cost, §144.2), move
        it, fire its "when I move" (on_move) abilities with where it came from and
        went, then start a showdown if it contests or claims the battlefield (the
        move's triggers resolve first: Corina's Recruits join the fight)."""
        ap = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        base_index = len(self.gs.battlefields)
        src_bf = None if src == base_index else self.gs.battlefields[src]
        dst_bf = None if dst == base_index else self.gs.battlefields[dst]
        self._exhaust(unit)
        g = self.gs.move_group
        count = g[3] + 1 if g is not None and g[:3] == (self.gs.turn, side, dst) else 1
        self.gs.move_group = (self.gs.turn, side, dst, count)
        if count == 3:
            # "when you exhaust three or more friendly units at the same time"
            self._fire_units_trigger("on_three_exhausted", side)
        if self.verbose:
            print(f"  {side} moves UNIT: {unit.card.name} to {'base' if dst_bf is None else f'BF{dst}'}")
        prev_controller = dst_bf.controller() if dst_bf is not None else None
        if dst_bf is not None and self.gs.pending_move != (dst, side):
            dst_bf.prev_controller = prev_controller     # "a battlefield that was uncontrolled"
        if dst_bf is None:
            ap.base_units.append(unit)
        else:
            dst_bf.add_unit(side, unit)
        self._fire_move_triggers(unit, side, src_bf, dst_bf)
        if dst_bf is None:
            return
        if src_bf is None:
            # Battlefield "first non-token unit played here this turn" trigger
            # (Star Spring). Fires once per side per turn at this battlefield.
            self._fire_first_unit_here(side, dst_bf, unit)
        # Contested if: gaining control from empty/opponent, OR both sides now have
        # units. The showdown waits while the player moves more units here
        # (_flush_pending_move): they moved together (§144.3).
        gained_control = prev_controller != side and dst_bf.controller() == side
        if gained_control or (dst_bf.units_A and dst_bf.units_B):
            dst_bf.contested_this_turn = True
            if self.gs.pending_move is None:
                self.gs.pending_move = (dst, side)

    def _fire_move_triggers(self, unit: UnitInPlay, side: str,
                            src_bf: Optional[Battlefield], dst_bf: Optional[Battlefield]) -> None:
        """After a unit moved (Standard Move or an effect; None = base): its "when
        I move" (on_move) abilities with where it came from and went, its
        Equipment's (Eye of the Herald), and "when a unit moves from here"
        (Back-Alley Bar) on the battlefield it left."""
        ap = self.gs.get_player(side)
        opponent = self.gs.get_player(self.gs.other(side))
        unit.moves_this_turn += 1
        here = dst_bf or self.gs.battlefields[0]
        extra = {"battlefield": here, "moved_from": src_bf or "base",
                 "moved_to": dst_bf or "base", "triggering_unit": unit}
        # "When an opponent moves to a battlefield ..." (Volibear Imposing): once
        # per move, not per unit of a group move (§144.3) already held here.
        dst_index = self.gs.battlefields.index(dst_bf) if dst_bf is not None else None
        if self.gs.pending_move != (dst_index, side):
            self._fire_units_trigger("on_enemy_unit_moves", self.gs.other(side),
                                     triggering_card=unit.card, extra=extra)
        for card in [unit.card] + list(unit.gear):
            self._resolve_triggered_effects(card, "on_move", here, ap, opponent,
                                            context_extra=extra)
        # "When a friendly unit moves from my location, I may be moved with it"
        # (Stealthy Pursuer): the friends it left behind.
        left = src_bf._units_for(side) if src_bf is not None else ap.base_units
        for friend in list(left):
            if friend is not unit and self._has_effect(friend.card, "follow_move"):
                self._resolve_triggered_effects(friend.card, "on_friendly_moves_from_here", here,
                                                ap, opponent, context_extra=extra)
        if src_bf is not None and src_bf.card is not None:
            self._resolve_triggered_effects(src_bf.card, "on_unit_moves_from_here", src_bf,
                                            ap, opponent, context_extra=extra)

    def _locate_unit(self, unit: UnitInPlay):
        """(side, battlefield or None for base) of a unit on the board, or None."""
        for side in ("A", "B"):
            for bf in self.gs.battlefields:
                if any(u is unit for u in bf._units_for(side)):
                    return side, bf
            if any(u is unit for u in self.gs.get_player(side).base_units):
                return side, None
        return None

    def _move_unit_by_effect(self, unit: UnitInPlay, dst_bf: Optional[Battlefield]) -> bool:
        """Move a unit as an effect says ("Move an enemy unit to its base"): no
        exhaust (that is the Standard Move's cost), its move triggers fire. A
        battlefield it contests fights at the end of the turn. Returns whether
        it moved (it may already be there or off the board)."""
        where = self._locate_unit(unit)
        if where is None:
            return False
        side, src_bf = where
        if src_bf is dst_bf:
            return False
        if dst_bf is None and not self._can_move_to_base(unit, src_bf):
            return False
        if src_bf is None:
            self.gs.get_player(side).base_units.remove(unit)
        else:
            src_bf.remove_unit(side, unit)
        if dst_bf is None:
            self.gs.get_player(side).base_units.append(unit)
        else:
            dst_bf.add_unit(side, unit)
        if self.verbose:
            to = "base" if dst_bf is None else f"BF{self.gs.battlefields.index(dst_bf)}"
            print(f"  {unit.card.name} ({side}) is moved to {to}")
        self._fire_move_triggers(unit, side, src_bf, dst_bf)
        return True

    def _flush_pending_move(self) -> None:
        """Start the showdown a held Standard Move owes (see GameState.pending_move):
        called before any action other than another move to the same battlefield,
        and when the player's actions end."""
        pending = self.gs.pending_move
        if pending is None:
            return
        self.gs.pending_move = None
        dst, side = pending
        self._run_showdown(dst, attacker=side)

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

        # A Standard Move is declared one unit at a time: units moved to the same
        # battlefield in a row move together (§144.3). Anything else ends the
        # move, and its showdown happens first (§323.11): the action chosen
        # before it isn't taken, the player decides again on the board the
        # showdown left (legal_actions offers only PASS or joining the move).
        pending = self.gs.pending_move
        if pending is not None and not (kind == "MOVE" and dst_lane == pending[0]):
            self._flush_pending_move()
            return
        if kind != "MOVE":
            self.gs.move_group = None       # the units moved together are done

        opponent = self.gs.get_player(self.gs.other(self.gs.active))           

        if kind == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, (UnitCard, LegendCard)):
                # Where it goes: base (dst None) or a battlefield it may be played to.
                dst = None if dst_lane is None or dst_lane == base_index else dst_lane
                if dst not in self._unit_play_destinations(card, ap.name):
                    return
                bf = None if dst is None else self.gs.battlefields[dst]
                prev_controller = bf.controller() if bf is not None else None
                # LEGION cost reductions are handled generically by _cost_reduction
                # (the reduce_cost effect gated on you_already_played_another_card_
                # this_turn).
                extras = self._cost_extras(card, ap.name)
                surcharge = self._destination_surcharge(card, dst, ap.name)
                energy, power = self._effective_cost(card, ap)
                extras, energy, power = self._choose_cost_extras(card, ap, extras, energy, power)
                if surcharge and not self._can_pay_generic_power(ap, surcharge + int(power or 0)):
                    return
                if not self._pay_card(ap, card, energy, power):
                    return
                if surcharge:
                    self._pay_generic_power(ap, surcharge)
                self._spend_cost_extras(extras, ap.name)
                if self.verbose:
                    print(f"  {ap.name} plays UNIT: {card.name}" + (f" to BF{dst}" if bf else ""))
                ap.remove_from_hand(idx)
                unit = self._play_unit(card, ap.name, bf=bf)
                if bf is not None:
                    self._arrive_at(bf, ap.name, prev_controller)
                    self._unit_played_here(bf, ap.name, unit)
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
                energy, power = self._effective_cost(card, ap, target_lane)
                if not self._pay_card(ap, card, energy, power):
                    return
                ap.remove_from_hand(idx)
                self._spell_played(card, ap)
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
                # Ornn's earmarked gear-power may cover the power portion.
                energy, power = self._effective_cost(card, ap)
                if not self._pay_card(ap, card, energy, power):
                    return
                ap.remove_from_hand(idx)
                # The player playing it (QUICK-DRAW can be played on the opponent's
                # turn), not necessarily the active player.
                self._play_gear(card, ap.name, lane if lane is not None else 0)
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
            # The Chosen Champion is played from the Champion Zone like any unit
            # from hand: its own reductions, ACCELERATE, "when you play me", ...
            energy, power = self._effective_cost(champion, ap)
            if not self._pay_card(ap, champion, energy, power):
                return
            if is_A:
                self.gs.champion_A_deployed = True
            else:
                self.gs.champion_B_deployed = True
            if self.verbose:
                print(f"  {ap.name} deploys CHAMPION: {champion.name}")
            self._play_unit(champion, ap.name, from_zone="champion")
            if self.recorder:
                self.recorder.record_play(
                    ap.name,
                    self.gs.turn,
                    champion,
                    action="UNIT",
                    battlefield_index=lane if lane is not None else 0,
                )

        elif kind == "HIDE" and idx is not None and isinstance(lane, int):
            # HIDDEN keyword: place a hand card facedown at a controlled battlefield.
            side = "A" if ap is self.gs.A else "B"
            self._hide_card(side, idx, lane)

        elif kind == "HIDDEN_PLAY" and isinstance(lane, int):
            # Play a previously-hidden card for [0] during your own main phase.
            side = "A" if ap is self.gs.A else "B"
            self._play_from_hidden(side, lane)

        elif kind == "MOVE":
            # Illegal during Showdown or Closed State (active chain), §144.1.
            if self.gs.showdown_active or self.gs.chain:
                return
            src, dst = lane, dst_lane
            n_loc = len(self.gs.battlefields) + 1
            if src is None or dst is None or src == dst or src not in range(n_loc)                     or dst not in range(n_loc):
                return
            side = self.gs.active
            src_bf = None if src == base_index else self.gs.battlefields[src]
            units = ap.base_units if src_bf is None else src_bf._units_for(side)
            if idx is None:   # legacy: the first ready unit there
                unit = next((u for u in units if u.ready), None)
            else:
                unit = units[idx] if isinstance(idx, int) and 0 <= idx < len(units) else None
            if unit is None or not unit.ready or unit.cant_move_turn == self.gs.turn:
                return
            if src_bf is not None and dst != base_index and not unit.has_keyword("GANKING"):
                return    # bf -> bf needs GANKING (§144.4.c)
            if dst == base_index and not self._can_move_to_base(unit, src_bf):
                return
            toll = self._group_move_toll(side, dst)
            if toll:
                if ap.energy < toll:
                    return
                ap.energy -= toll
            if src_bf is None:
                units.remove(unit)
            else:
                src_bf.remove_unit(side, unit)
            self._standard_move(unit, side, src, dst)

        elif kind == "ABILITY":
            ability_id = idx  # idx actually contains the ability_id
            arg = lane  # lane actually contains the argument
            if ability_id == "ACTIVATED":
                self._apply_activated_ability(ap, opponent, arg)

        # A unit played to a battlefield it contests: its showdown starts as
        # soon as the play is done (§323.11); nothing joins it.
        if kind != "MOVE" and self.gs.pending_move is not None:
            self._flush_pending_move()

    # ------------------------------------------------------------------
    # Generic activated abilities (Round 4 Tier 2 / D3)

    # Which ability timings each window allows: in your own Open State any
    # ability; in a showdown ACTION and REACTION ones; with a chain open only
    # REACTION ones (Core Rules: ACTION = your turn or showdowns, REACTION =
    # any time).
    _WINDOW_TIMINGS = {
        "main": (None, "action", "reaction"),
        "showdown": ("action", "reaction"),
        "reaction": ("reaction",),
    }

    def _ability_window(self, side: str) -> str:
        """The timing window `side` is acting in right now."""
        if self.gs.chain:
            return "reaction"
        if self.gs.showdown_active:
            return "showdown"
        return "main" if side == self.gs.active else "reaction"

    def activatable_abilities(self, side: str) -> list:
        """Deterministic list of activated abilities `side` may use in the current
        window (_ability_window): unit/legend/gear abilities tagged `trigger:
        activated` whose timing the window allows, plus EQUIP entries for gear
        waiting at base (Open State only). The list order is stable for a given
        board and window, so an agent can pick by index and the engine
        re-resolves the same entry. Affordability and conditions are NOT filtered
        here (so indices stay stable): see _ability_usable.

        A spec tagged `activated` with no cost is never offered: every printed
        activated ability has a cost, so a cost-less one is a misparsed trigger
        ("When you stun an enemy unit, ready me" read as a button) that would
        otherwise be usable for free, without limit."""
        ap = self.gs.get_player(side)
        window = self._ability_window(side)
        allowed = self._WINDOW_TIMINGS[window]
        out: list = []

        def _abilities(card):
            spec = CARD_REGISTRY.get(card.name)
            for eff in (spec.effects if spec else ()):
                if eff.trigger != "activated" or not eff.cost:
                    continue  # cost-less "activated" = misparsed trigger (see docstring)
                if ((eff.timing or "").lower() or None) not in allowed:
                    continue
                yield eff

        def _add_unit_abilities(unit, bf_idx):
            for eff in _abilities(unit.card):
                # EMPOWER can only be activated while NOT already empowered.
                if eff.effect == "empower_self" and getattr(unit, "empowered", False):
                    continue
                out.append({"type": "ability", "unit": unit, "bf_idx": bf_idx, "eff": eff})
            if self._has_effect(unit.card, "copy_tap_abilities"):
                # "I have all [tap] abilities of all friendly legends, units, and
                # gears" (Heimerdinger Inventor): used by me, tapping me.
                for src, _bf in self._sources_in_play(side):
                    if src is unit.card:
                        continue
                    for eff in _abilities(src):
                        if self._parse_activated_cost(eff.cost)["tap"] and \
                                EFFECT_REGISTRY.get(eff.effect) is not None:
                            out.append({"type": "ability", "unit": unit, "bf_idx": bf_idx, "eff": eff})

        def _add_gear_abilities(gear):
            # Gear's own activated [tap] abilities (Seals, Gold, Iron Ballista, …).
            for eff in _abilities(gear):
                if eff.effect == "empower_self" and getattr(gear, "empowered", False):
                    continue      # EMPOWER: "Use only if not Empowered"
                if EFFECT_REGISTRY.get(eff.effect) is not None:
                    out.append({"type": "gear_ability", "gear": gear, "eff": eff})

        for bf_idx, bf in enumerate(self.gs.battlefields):
            for unit in (bf.units_A if side == "A" else bf.units_B):
                _add_unit_abilities(unit, bf_idx)
        for unit in ap.base_units:
            _add_unit_abilities(unit, None)
        legend_unit = self._legend_unit(side)
        if legend_unit is not None:
            _add_unit_abilities(legend_unit, None)
            # "While you control this battlefield, friendly legends have '[tap]:
            # Attach an Equipment ...'" (Forge of the Fluft).
            for bf in self.gs.battlefields:
                if bf.card is not None and bf.controller() == side:
                    bspec = CARD_REGISTRY.get(bf.card.name)
                    for eff in (bspec.effects if bspec else ()):
                        if eff.trigger == "granted_to_legend" and \
                                ((eff.timing or "").lower() or None) in allowed:
                            out.append({"type": "ability", "unit": legend_unit, "bf_idx": None, "eff": eff})
        for gear in list(ap.base_gear):
            # Only Equipment (gear with an Equip ability) can be equipped.
            if window == "main" and self._equip_cost(gear) is not None:
                out.append({"type": "equip", "gear": gear})
            _add_gear_abilities(gear)
        # Attached gear (on controlled units) can also use its [tap] abilities.
        for gear in self._controlled_attached_gear(side):
            _add_gear_abilities(gear)
        # FLOW (§ "You may play this from your trash for its Flow cost. Then
        # banish it."): a spell in the trash, at its own timing.
        for card in ap.trash:
            if isinstance(card, SpellCard) and self._flow_cost(card, side) is not None:
                timing = "reaction" if card.has_keyword("REACTION") else \
                    "action" if card.has_keyword("ACTION") else None
                if timing in allowed:
                    out.append({"type": "flow", "card": card})
        # "Banish the top card of your Main Deck. Until your next Ending Phase,
        # you may play that card." (Runeblade Anvil, Akali Brash)
        for card in ap.banished:
            if self._banished_playable(card, side) and self._card_timing(card) in allowed:
                out.append({"type": "banished_play", "card": card})
        return out

    @staticmethod
    def _card_timing(card: Card):
        """The timing a card can be played at: "reaction" (REACTION spells,
        QUICK-DRAW gear), "action" (ACTION spells and units), else None (your
        own Open State)."""
        if card.has_keyword("REACTION") or (isinstance(card, GearCard) and card.has_keyword("QUICK-DRAW")):
            return "reaction"
        return "action" if card.has_keyword("ACTION") else None

    def _banished_playable(self, card: Card, side: str) -> bool:
        return (getattr(card, "_banish_play_side", None) == side
                and self.gs.turn <= getattr(card, "_banish_play_until", -1))

    def _play_banished(self, ap: Player, card: Card, side: str) -> None:
        """Play a card a "you may play that card" effect left in banishment,
        paying its costs."""
        if card not in ap.banished or not self._banished_playable(card, side):
            return
        energy, power = self._effective_cost(card, ap, from_zone="banished")
        if not self._pay_card(ap, card, energy, power):
            return
        ap.banished.remove(card)
        card._banish_play_side = None
        if self.verbose:
            print(f"  {ap.name} plays {card.name} from banishment")
        self._play_from_zone_now(ap, card, side, "banished")

    def _play_from_zone_now(self, ap: Player, card: Card, side: str, zone: str) -> None:
        """Put a card taken from `zone` (cost handled) into play: a unit to base,
        a gear to base, a spell onto the open chain or as a new chain (aimed at
        the showdown's battlefield, else the first)."""
        if isinstance(card, UnitCard):
            self._play_unit(card, side, from_zone=zone)
        elif isinstance(card, GearCard):
            self._play_gear(card, side, 0, from_zone=zone)
        elif isinstance(card, SpellCard):
            lane = self.gs.showdown_bf_idx if self.gs.showdown_active and \
                self.gs.showdown_bf_idx is not None else 0
            if self.gs.chain:
                self._spell_played(card, ap, from_zone=zone)
                self.gs.chain.append(ChainItem(player=side, card=card, bf_idx=lane))
            else:
                self._cast_spell_now(card, side, lane, from_zone=zone)

    def _flow_cost(self, card: Card, side: str):
        """(Energy, Power, domain or None) to play `card` from the trash with
        FLOW: its printed FLOW cost, or its own cost when an effect gave it FLOW
        this turn (Kennen), less cost auras (Stargazer: FLOW spells cost [2]
        less, to a minimum of [1]). None if it has no FLOW now."""
        cost = getattr(card, "flow_cost", None)
        if getattr(card, "_flow_granted_turn", None) == self.gs.turn:
            dom = getattr(card, "cost_power_domain", None)
            cost = {"energy": card.cost_energy or 0, "power": card.cost_power or 0,
                    "domain": dom.name if isinstance(dom, Domain) else None}
        if not cost:
            return None
        aura, floor = self._aura_reduction(card, self.gs.get_player(side), flow=True)
        energy = int(cost.get("energy", 0) or 0)
        if aura:
            energy = max(min(energy, floor), energy - aura)
        domain = Domain[cost["domain"]] if cost.get("domain") else None
        return energy, int(cost.get("power", 0) or 0), domain

    def _can_pay_flow(self, ap: Player, card: Card, side: str) -> bool:
        cost = self._flow_cost(card, side)
        if cost is None or card not in ap.trash or self._play_forbidden(ap, card):
            return False
        energy, power, domain = cost
        if ap.energy < energy:
            return False
        if not power:
            return True
        return ap.can_pay_cost(0, power, domain) if domain else self._can_pay_generic_power(ap, power)

    def _play_with_flow(self, ap: Player, card: Card, side: str) -> None:
        """Pay a spell's FLOW cost, take it from the trash and play it: on the
        open chain if there is one, else as a new chain. It is banished when it
        resolves or is countered. The battlefield it is aimed at is the
        showdown's, else the first."""
        if not self._can_pay_flow(ap, card, side):
            return
        energy, power, domain = self._flow_cost(card, side)
        ap.energy -= energy
        if power:
            if domain:
                ap.pay_cost(0, power, domain)
            else:
                self._pay_generic_power(ap, power)
        ap.trash.remove(card)
        card._flow_banish = True
        if self.verbose:
            print(f"  {ap.name} plays {card.name} from the trash (FLOW)")
        self._play_from_zone_now(ap, card, side, "trash")

    def _spell_to_trash(self, owner: Player, card: Card) -> None:
        """A spell that resolved or was countered goes to the trash, or is
        banished if it was played with FLOW."""
        side = "A" if owner is self.gs.A else "B"
        legend = self._legend_unit(side)
        if getattr(card, "_flow_banish", False):
            card._flow_banish = False
            owner.banished.append(card)
            self._note_banished(side)
        elif legend is not None and self._has_effect(legend.card, "jhin_pile") \
                and int(card.cost_energy or 0) >= 4:
            # "if you spent [4] or more, you may banish it. Then, if there are four
            # spells banished with me, put each in its trash, channel 4 runes, and
            # draw 1." (Jhin Virtuoso)
            owner.banished.append(card)
            self._note_banished(side)
            pile = self.gs.jhin_pile.setdefault(side, [])
            pile.append(card)
            if len(pile) >= 4:
                for c in pile:
                    if c in owner.banished:
                        owner.banished.remove(c)
                        owner.trash.append(c)
                self.gs.jhin_pile[side] = []
                owner.unlock_runes(4)
                self._draw_one(owner)
        else:
            owner.trash.append(card)

    def _ability_usable(self, ap: Player, entry: dict) -> bool:
        """Whether `ap` can use this activatable_abilities entry now: it can pay
        the cost and the ability's condition ("LEGION", "while I'm at a
        battlefield") holds."""
        side = "A" if ap is self.gs.A else "B"
        if entry["type"] == "equip":
            gear = entry["gear"]
            cost = self._equip_cost(gear)
            return (gear in ap.base_gear and cost is not None and self._can_pay_equip(ap, cost)
                    and self._first_friendly_unit_on_board(side) is not None)
        if entry["type"] == "flow":
            return self._can_pay_flow(ap, entry["card"], side)
        if entry["type"] == "banished_play":
            card = entry["card"]
            if card not in ap.banished or not self._banished_playable(card, side):
                return False
            energy, power = self._effective_cost(card, ap, from_zone="banished")
            return self._can_pay_card(ap, card, energy, power)
        eff = entry["eff"]
        if EFFECT_REGISTRY.get(eff.effect) is None:
            return False
        if eff.params.get("once_per_turn"):
            src = entry["gear"] if entry["type"] == "gear_ability" else entry["unit"].card
            if self.gs.once_per_turn_used.get((id(src), "activated", eff.effect)) == self.gs.turn:
                return False        # "Use only once each turn"
        parsed = self._parse_activated_cost(eff.cost)
        if entry["type"] == "gear_ability":
            gear = entry["gear"]
            source = gear
            if not self._controls_gear(ap, gear):
                return False
            if parsed["tap"] and getattr(gear, "tapped", False):
                return False
            if parsed["disempower"] and not getattr(gear, "empowered", False):
                return False      # "Disempower this, ...": needs it empowered
            # Gear ability power is generic; Ornn's earmarked gear-power may cover it.
            if not self._can_pay_gear(ap, parsed["energy"], parsed["power"], parsed["domain"]):
                return False
            if parsed["recycle"] and len(ap.trash) < parsed["recycle"]:
                return False
            if parsed["banish_from_trash"] and self._trash_card_to_banish(ap, parsed) is None:
                return False
            if parsed["discard"] and len(self._discardable(ap, parsed)) < parsed["discard"]:
                return False
            if parsed["spend_buff"] and self._buff_to_spend(side, None, parsed["spend_buff"]) is None:
                return False
            if parsed["spend_xp"] and self.gs.get_xp(side) < parsed["spend_xp"]:
                return False
        else:
            source = entry["unit"].card
            parsed = self._adjust_ability_cost(entry["unit"], eff, parsed, side)
            if not self._activated_affordable(ap, entry["unit"], parsed):
                return False
        bf = self.gs.battlefields[entry["bf_idx"]] if entry.get("bf_idx") is not None             else self.gs.battlefields[0]
        return self._check_condition(eff.condition, source, ap,
                                     self.gs.get_player(self.gs.other(side)),
                                     {"battlefield": bf})

    def _gear_left_board(self, gear, side: str) -> None:
        """A gear was killed (or sacrificed): its DEATHKNELL (Sprite Fountain)
        and "When this leaves the board" (Runeblade Anvil, Treasure Trove)."""
        card = getattr(gear, "card", gear)
        bf = self.gs.battlefields[0]
        self._resolve_triggered_effects(card, "on_death", bf, self.gs.get_player(side),
                                        self.gs.get_player(self.gs.other(side)),
                                        context_extra={"battlefield": bf})
        self._fire_leaves_board(card, side, bf)

    def _remove_gear(self, gear, ap: Player) -> None:
        """A gear `ap` controls (in base or attached) is killed: it goes to the
        trash, or ceases to exist if it is a token."""
        if gear in ap.base_gear:
            ap.base_gear.remove(gear)
        else:
            side = "A" if ap is self.gs.A else "B"
            for u in [u for b in self.gs.battlefields for u in (b.units_A if side == "A" else b.units_B)] + ap.base_units:
                if gear in u.gear:
                    u.gear.remove(gear)
                    break
        self._to_trash(ap, gear)
        self._gear_left_board(gear, "A" if ap is self.gs.A else "B")

    def _controlled_attached_gear(self, side: str) -> list:
        ap = self.gs.get_player(side)
        gears = [g for u in ap.base_units for g in u.gear]
        for bf in self.gs.battlefields:
            for u in (bf.units_A if side == "A" else bf.units_B):
                gears.extend(u.gear)
        return gears

    def _controls_gear(self, ap: Player, gear) -> bool:
        side = "A" if ap is self.gs.A else "B"
        return gear in ap.base_gear or gear in self._controlled_attached_gear(side)

    @staticmethod
    def _parse_activated_cost(cost) -> dict:
        """Normalize the mixed string/dict/None cost forms the generator emits."""
        import re
        parsed = {"energy": 0, "power": 0, "domain": None, "tap": False, "recycle": 0,
                  "sacrifice": False, "spend_xp": 0, "disempower": False,
                  "banish_from_trash": None, "discard": 0, "discard_type": None,
                  "spend_buff": None, "kill_other_token": False, "kill_other_friendly": False}
        if cost is None:
            return parsed
        if isinstance(cost, dict):
            parsed["energy"] = int(cost.get("energy", 0) or 0)
            parsed["power"] = int(cost.get("power", 0) or 0)
            # "[2] [fury]": the power's domain; None is generic ([rune]).
            parsed["domain"] = Domain[cost["domain"]] if cost.get("domain") else None
            parsed["tap"] = bool(cost.get("tap") or cost.get("exhaust_self")
                                 or cost.get("exhaust"))
            parsed["recycle"] = int(cost.get("recycle_from_trash",
                                             cost.get("recycle", 0)) or 0)
            parsed["sacrifice"] = bool(cost.get("sacrifice_self")
                                       or cost.get("kill_friendly"))
            parsed["spend_xp"] = int(cost.get("spend_xp", 0) or 0)
            parsed["disempower"] = bool(cost.get("disempower_self"))
            # "Banish a unit from your trash": the card type(s), e.g. "unit".
            parsed["banish_from_trash"] = cost.get("banish_from_trash")
            parsed["discard"] = int(cost.get("discard", 0) or 0)     # "Discard 1, [tap]: ..."
            parsed["discard_type"] = cost.get("discard_type")         # "Discard a gear"
            parsed["spend_buff"] = cost.get("spend_buff")             # "self" / "other" / "any"
            parsed["kill_other_token"] = bool(cost.get("kill_other_token"))
            parsed["kill_other_friendly"] = bool(cost.get("kill_other_friendly"))  # "Kill a friendly unit"
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

    @staticmethod
    def _trash_card_to_banish(ap: Player, parsed: dict):
        """The card a "banish a <type> from your trash" cost takes: the cheapest
        matching one (the least likely to be played back)."""
        from .effects import _zone_effect_card_ok
        kind = parsed.get("banish_from_trash")
        if not kind:
            return None
        spec = {"filter": kind} if isinstance(kind, str) else {"target_filter": kind}
        cands = [c for c in ap.trash if _zone_effect_card_ok(c, spec)]
        return min(cands, key=lambda c: c.cost_energy or 0) if cands else None

    def _pay_discard_and_banish(self, ap: Player, parsed: dict, unit=None) -> None:
        """Pay a cost's "banish a <type> from your trash", "Discard N" (the
        cheapest cards), "spend a buff" and "kill a friendly token"."""
        side = "A" if ap is self.gs.A else "B"
        if parsed.get("banish_from_trash"):
            card = self._trash_card_to_banish(ap, parsed)
            if card is not None:
                from .effects import _zone_effect_card_ok
                kind = parsed["banish_from_trash"]
                spec = {"filter": kind} if isinstance(kind, str) else {"target_filter": kind}
                card = self.choose("cost_banish", side,
                                   [c for c in ap.trash if _zone_effect_card_ok(c, spec)], card)
            self._banish_from_trash(ap, card)
        for _ in range(parsed.get("discard", 0)):
            cands = self._discardable(ap, parsed)
            if cands:
                self._discard(ap, self.choose("discard", side, cands,
                                              min(cands, key=lambda c: c.cost_energy or 0)))
        if parsed.get("spend_buff"):
            holder = self._buff_to_spend(side, unit, parsed["spend_buff"])
            if holder is not None:
                holder.might_counters -= 1
        if parsed.get("kill_other_token") or parsed.get("kill_other_friendly"):
            others = [u for u in self._friendly_units_of(side) if u is not unit]
            if parsed.get("kill_other_token"):
                victim = self._token_to_kill(side, unit)
                if victim is not None:
                    # "Kill a friendly unit or gear" (Malzahar Fanatic): any of them.
                    victim = self.choose("cost_unit:kill", side, others + list(ap.base_gear), victim)
            else:
                victim = self._friendly_to_kill(side, unit)
                if victim is not None:
                    victim = self.choose("cost_unit:kill", side, others, victim)
            if isinstance(victim, UnitInPlay):
                where = self._locate_unit(victim)
                if where[1] is None:
                    ap.base_units.remove(victim)
                else:
                    where[1].remove_unit(side, victim)
                self._route_deaths([(victim, side)], where[1] or self.gs.battlefields[0],
                                   in_base=where[1] is None)
            elif victim is not None:
                self._remove_gear(victim, ap)

    @staticmethod
    def _discardable(ap: Player, parsed: dict) -> list:
        kind = parsed.get("discard_type")
        if kind == "gear":
            return [c for c in ap.hand if isinstance(c, GearCard)]
        if kind == "spell":                 # "Discard a spell" (Mel Defiant Soul)
            return [c for c in ap.hand if isinstance(c, SpellCard)]
        return list(ap.hand)

    def _buff_to_spend(self, side: str, unit, who: str):
        """The unit whose buff a "spend a buff" cost takes: "self" (Udyr: "Spend
        my buff"), "other" (not the source), "any": a buffed friendly unit,
        one in base first (it isn't fighting), the weakest."""
        if who == "self":
            return unit if unit is not None and unit.might_counters > 0 else None
        cands = [u for u in self._friendly_units_of(side) if u.might_counters > 0
                 and not (who == "other" and u is unit)]
        if not cands:
            return None
        return self.choose("spend_buff", side, cands,
                           min(cands, key=lambda u: (self._locate_unit(u)[1] is not None, u.might)))

    def _friendly_units_of(self, side: str) -> list:
        return [u for bf in self.gs.battlefields for u in bf._units_for(side)] + \
            list(self.gs.get_player(side).base_units)

    def _friendly_to_kill(self, side: str, unit):
        """ "Kill a friendly unit" as a cost (Escaped Grayback): baseline, a token
        first, else the weakest other friendly unit."""
        others = [u for u in self._friendly_units_of(side) if u is not unit]
        if not others:
            return None
        return min(others, key=lambda u: (not u.is_token, u.might))

    def _token_to_kill(self, side: str, unit):
        """ "Kill a friendly unit or gear" as a cost (Malzahar Fanatic): baseline,
        only a token (unit or gear) is given up."""
        tokens = [u for u in self._friendly_units_of(side) if u.is_token and u is not unit]
        if tokens:
            return min(tokens, key=lambda u: u.might)
        gear = [g for g in self.gs.get_player(side).base_gear if getattr(g, "is_token", False)]
        return gear[0] if gear else None

    def _banish_from_trash(self, ap: Player, card) -> None:
        if card is not None and card in ap.trash:
            ap.trash.remove(card)
            ap.banished.append(card)
            self._note_banished("A" if ap is self.gs.A else "B")

    def _activated_affordable(self, ap: Player, unit, parsed: dict) -> bool:
        side = "A" if ap is self.gs.A else "B"
        if parsed["tap"] and unit is not None and not unit.ready:
            return False
        if parsed["disempower"] and not (unit is not None and unit.empowered):
            return False   # "Disempower me" needs me empowered
        if not self._can_pay_energy_and_generic(ap, parsed["energy"], parsed["power"], parsed["domain"]):
            return False
        if parsed["recycle"] and len(ap.trash) < parsed["recycle"]:
            return False
        if parsed["banish_from_trash"] and self._trash_card_to_banish(ap, parsed) is None:
            return False
        if parsed["discard"] and len(self._discardable(ap, parsed)) < parsed["discard"]:
            return False
        if parsed["spend_buff"] and self._buff_to_spend(side, unit, parsed["spend_buff"]) is None:
            return False
        if parsed["kill_other_token"] and self._token_to_kill(side, unit) is None:
            return False
        if parsed["kill_other_friendly"] and self._friendly_to_kill(side, unit) is None:
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
        if not self._ability_usable(ap, entry):
            return

        if entry["type"] == "equip":
            gear = entry["gear"]
            cost = self._equip_cost(gear)              # the EQUIP-ability cost (§744)
            target_unit = self._first_friendly_unit_on_board(side)
            if not self._pay_equip(ap, cost):
                return
            # A cost that kills a friendly unit may have taken that one.
            if self._locate_unit(target_unit) is None:
                target_unit = self._first_friendly_unit_on_board(side)
                if target_unit is None:
                    return
            target_unit = self.choose("equip", side, self._friendly_units_of(side),
                                      target_unit, gear)
            ap.base_gear.remove(gear)
            target_unit.gear.append(gear)
            if self.verbose:
                print(f"  {ap.name} EQUIP: {gear.name} -> {target_unit.card.name}")
            self._fire_attached(target_unit, side)
            return

        if entry["type"] == "flow":
            self._play_with_flow(ap, entry["card"], side)
            return
        if entry["type"] == "banished_play":
            self._play_banished(ap, entry["card"], side)
            return

        if entry["type"] == "gear_ability":
            gear = entry["gear"]
            eff = entry["eff"]
            parsed = self._parse_activated_cost(eff.cost)
            if not self._pay_gear(ap, parsed["energy"], parsed["power"], parsed["domain"]):
                return
            if parsed["tap"]:
                self._exhaust_gear(gear, ap)
            if parsed["disempower"]:
                gear.empowered = False
            self._recycle_from_trash(ap, parsed["recycle"])
            self._pay_discard_and_banish(ap, parsed)
            if parsed["spend_xp"]:
                self.gs.add_xp(side, -parsed["spend_xp"])
            if parsed["sacrifice"]:
                # "Kill this" (a Gold token): off the board before the effect.
                self._remove_gear(gear, ap)
            handler = EFFECT_REGISTRY.get(eff.effect)
            if handler is None:
                return
            context = EffectContext(self, gear, ap, opponent, self.gs.battlefields[0])
            handler(context, eff.merged_params())
            if self.verbose:
                print(f"  {ap.name} GEAR ABILITY: {eff.effect} ({gear.name})")
            self._fire_units_trigger("on_gear_ability_used", side, triggering_card=gear)
            return

        # Unit/legend activated ability.
        unit = entry["unit"]
        eff = entry["eff"]
        if eff.params.get("once_per_turn"):
            self.gs.once_per_turn_used[(id(unit.card), "activated", eff.effect)] = self.gs.turn
        parsed = self._adjust_ability_cost(unit, eff, self._parse_activated_cost(eff.cost), side)
        # Pay.
        if not self._pay_energy_and_generic(ap, parsed["energy"], parsed["power"], parsed["domain"]):
            return
        if parsed["tap"] and unit is not None:
            self._exhaust(unit)
        if parsed["disempower"] and unit is not None:
            unit.empowered = False
        self._recycle_from_trash(ap, parsed["recycle"])
        self._pay_discard_and_banish(ap, parsed, unit)
        if parsed["spend_xp"]:
            self.gs.add_xp(side, -parsed["spend_xp"])
        if parsed["sacrifice"] and unit is not None:
            self._remove_unit_from_play(unit, side)
            self._to_trash(ap, unit.card)

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

    def _use_ability_now(self, player: Player, ability_id, arg) -> bool:
        """Use an activated ability inside a chain or showdown window. Returns
        whether it changed the game (an unusable pick does nothing)."""
        opponent = self.gs.get_player(self.gs.other(player.name))
        before = self._action_fingerprint(player, opponent)
        self._apply_action(player, ("ABILITY", ability_id, arg, None))
        self._recompute_passives()
        return self._action_fingerprint(player, opponent) != before

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
        if self._sacrifice_instead_of_dying(dead_unit, owner_side):
            return True
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
            self._to_trash(owner, gear)    # the gear is destroyed instead of the unit
        owner.base_units.append(dead_unit)  # recall (not a move)
        if self.verbose:
            print(f"  {owner.name} DEATH REPLACEMENT: {dead_unit.card.name} recalled instead of dying")
        return True

    def _sacrifice_instead_of_dying(self, dead_unit: UnitInPlay, side: str) -> bool:
        """ "Once each turn, if I would die, you may kill a friendly unit to heal
        me, exhaust me, and recall me instead" (Mordekaiser Twice Slain): a token
        or the weakest other friendly unit is killed."""
        if not self._has_effect(dead_unit.card, "sacrifice_instead_of_dying"):
            return False
        key = (id(dead_unit.card), "sacrifice_instead_of_dying")
        if self.gs.once_per_turn_used.get(key) == self.gs.turn:
            return False
        others = [u for u in self._friendly_units_of(side) if u is not dead_unit]
        if not others:
            return False
        victim = min(others, key=lambda u: (not u.is_token, u.might))
        self.gs.once_per_turn_used[key] = self.gs.turn
        where = self._locate_unit(victim)
        if where[1] is None:
            self.gs.get_player(side).base_units.remove(victim)
        else:
            where[1].remove_unit(side, victim)
        self._route_deaths([(victim, side)], where[1] or self.gs.battlefields[0], in_base=where[1] is None)
        dead_unit.reset_damage()
        dead_unit.ready = False
        self.gs.get_player(side).base_units.append(dead_unit)
        return True

    def _route_combat_deaths(self, stats, bf) -> None:
        self._route_deaths([(u, "A") for u in stats.dead_A] + [(u, "B") for u in stats.dead_B], bf)

    def _route_deaths(self, ordered, bf, in_base: bool = False, killer=None) -> None:
        """Units that just died (already off the board), as (unit, owner side)
        pairs, from combat, spell damage or a kill effect: apply death
        replacements, then trash the truly-dead (tokens cease to exist), route
        their gear to base, set the friendly-died flag, and fire on_death /
        leaves_board / on_friendly_unit_death."""
        truly_dead = []
        if killer is not None and isinstance(killer[1], SpellCard) and ordered:
            # "When you kill a unit with a spell, you may pay ... to play me from
            # your trash" (Immortal Phoenix).
            ksi, kcard = killer
            kp = self.gs.get_player(ksi)
            for src in list(kp.trash):
                self._resolve_triggered_effects(src, "trash_on_spell_kill", bf, kp,
                                                self.gs.get_player(self.gs.other(ksi)),
                                                context_extra={"battlefield": bf})
        for dead_unit, owner_side in ordered:
            if self._try_replace_death(dead_unit, owner_side):
                continue
            owner = self.gs.get_player(owner_side)
            self._to_trash(owner, dead_unit.card)
            owner.base_gear.extend(dead_unit.gear)
            self.gs.friendly_unit_died_this_turn[owner_side] = True
            truly_dead.append((dead_unit, owner_side))
        for dead_unit, owner_side in truly_dead:
            actor = self.gs.get_player(owner_side)
            opponent = self.gs.get_player(self.gs.other(owner_side))
            alone = not bf._units_for(owner_side) and \
                sum(1 for _, s in truly_dead if s == owner_side) == 1
            # The unit's DEATHKNELL, then its Equipment's ("When I die" on gear;
            # the gear itself is back in base by now).
            # "Your DEATHKNELL effects trigger an additional time" (Karthus).
            times = 2 if self._side_has_passive(owner_side, "double_deathknell") else 1
            for _ in range(times):
                for card in [dead_unit.card] + list(dead_unit.gear):
                    self._resolve_triggered_effects(
                        card, "on_death", bf, actor, opponent,
                        context_extra={"battlefield": bf, "died_alone": alone,
                                       "died_might": dead_unit.might},
                    )
            dead_unit.gear = []
            # "When this leaves the board" fires on death too (KNOWN_ISSUES #9).
            self._fire_leaves_board(dead_unit.card, owner_side, bf)
            self._fire_units_trigger("on_friendly_unit_death", owner_side,
                                     exclude_card=dead_unit.card,
                                     extra={"triggering_unit": dead_unit})
            # "When an enemy unit dies (here)" (Nasus, Solari Shrine, Sivir).
            self._fire_units_trigger("on_enemy_unit_died", self.gs.other(owner_side),
                                     triggering_card=dead_unit.card,
                                     extra={"triggering_unit": dead_unit,
                                            "died_at": None if in_base else bf})
            if dead_unit.stunned:
                # "When a stunned enemy unit dies here" (Storm Raptor).
                enemy = self.gs.other(owner_side)
                for u in list(bf._units_for(enemy)):
                    self._resolve_triggered_effects(u.card, "on_stunned_enemy_dies_here", bf,
                                                    self.gs.get_player(enemy), actor,
                                                    context_extra={"battlefield": bf})

    def _take_damage(self, unit: UnitInPlay, amount: int, kind: str = "spell",
                     source_side: Optional[str] = None, source: Optional[Card] = None) -> int:
        """The damage `unit` actually takes from `amount` dealt to it (kind
        "spell" = a spell or ability, or "combat"): Bonus Damage (Annie Fiery,
        Ravenborn Tome's next spell), prevention (Unyielding Spirit, Esteemed
        Hierophant, Kayn after two moves, Ki Barrier's shield), doubling (Lotus
        Trap); with Imperial Decree a unit that takes damage dies."""
        gs = self.gs
        if amount <= 0:
            return 0
        where = self._locate_unit(unit)
        owner = where[0] if where else None
        if kind == "spell":
            if gs.no_spell_damage_turn == gs.turn:
                return 0
            if source_side is not None:
                amount += self._spell_bonus(source_side)
                if getattr(source, "_bonus_damage_turn", None) == gs.turn:
                    amount += 1
                if unit.spell_immune and owner is not None and source_side != owner:
                    return 0
        if self._has_effect(unit.card, "no_damage_if_moved_twice") and unit.moves_this_turn >= 2:
            return 0
        if unit.double_damage_turn == gs.turn:
            amount *= 2
        if unit.damage_shield:
            absorbed = min(unit.damage_shield, amount)
            unit.damage_shield -= absorbed
            amount -= absorbed
        if amount > 0 and gs.decree_turn == gs.turn:
            # Imperial Decree: dealt damage kills it.
            return max(amount, unit.might - unit.damage, 1)
        return amount

    def _spell_bonus(self, side: str) -> int:
        """ "Your spells and abilities deal N Bonus Damage" (Annie Fiery; Rabadon's
        Deathcrown only while attached)."""
        ap = self.gs.get_player(side)
        total = 0
        for src, _bf in self._sources_in_play(side):
            if src in ap.base_gear and self._equip_cost(src) is not None:
                continue
            spec = CARD_REGISTRY.get(src.name)
            total += sum(int(es.params.get("amount", 1)) for es in (spec.effects if spec else ())
                         if es.trigger == "passive" and es.effect == "spell_bonus_damage")
        return total

    def _is_empowered(self, card: Card) -> bool:
        """EMPOWERED status of a unit / legend (on its UnitInPlay) or a gear (on
        the card)."""
        unit = self._find_unit_by_card(card)
        return bool(unit.empowered) if unit is not None else bool(getattr(card, "empowered", False))

    def _empower(self, card: Card, side: str) -> None:
        """Empower a unit, legend or gear `side` controls; if it wasn't already,
        its own "When I become EMPOWERED" (Apprentice Mage, Kharox) and "When
        you empower something else, empower me" (Mel, Ambessa)."""
        unit = self._find_unit_by_card(card)
        if self._is_empowered(card):
            return
        if unit is not None:
            unit.empowered = True
        else:
            card.empowered = True
        where = self._locate_unit(unit) if unit is not None else None
        bf = (where[1] if where else None) or self.gs.battlefields[0]
        self._resolve_triggered_effects(card, "on_become_empowered", bf, self.gs.get_player(side),
                                        self.gs.get_player(self.gs.other(side)),
                                        context_extra={"battlefield": bf})
        self._fire_units_trigger("on_friendly_empowered", side, exclude_card=card,
                                 triggering_card=card)

    def _disempower(self, card: Card) -> None:
        unit = self._find_unit_by_card(card)
        if unit is not None:
            unit.empowered = False
        else:
            card.empowered = False

    def _locate_unit_or_gear(self, card: Card, side: str) -> bool:
        """Whether `card` is in play for `side` (a unit, or a gear in base or
        attached)."""
        if self._find_unit_by_card(card) is not None:
            return True
        ap = self.gs.get_player(side)
        return card in ap.base_gear or card in self._controlled_attached_gear(side)

    def _recycle_from_trash(self, player: Player, n: int) -> None:
        """Recycle n cards from the trash: to the bottom of the Main Deck."""
        moved = 0
        for _ in range(n):
            if player.trash:
                player.deck.cards.insert(0, player.trash.pop(0))
                moved += 1
        if moved:
            self._note_recycled("A" if player is self.gs.A else "B")

    def _note_recycled(self, side: str) -> None:
        """`side` recycled one or more cards to its Main Deck: "When you recycle
        one or more cards to your Main Deck" (Karma Channeler)."""
        self._fire_units_trigger("on_recycle", side)

    def _note_banished(self, side: str, count: int = 1) -> None:
        """`side` banished card(s) it owns: "When you banish a card you own,
        empower me" (Zed Master of Shadows)."""
        for _ in range(count):
            self._fire_units_trigger("on_banish_own", side)

    def _fire_attached(self, unit: UnitInPlay, side: str) -> None:
        """An Equipment was attached to `unit`: its "When you attach an
        Equipment to me" (Aphelios Exalted, Jax Unrelenting)."""
        where = self._locate_unit(unit)
        bf = where[1] if where and where[1] is not None else self.gs.battlefields[0]
        self._resolve_triggered_effects(unit.card, "on_equipment_attached", bf,
                                        self.gs.get_player(side),
                                        self.gs.get_player(self.gs.other(side)),
                                        context_extra={"battlefield": bf})
        # "As this is attached to a unit, ..." (Shady Spectacles).
        for g in list(unit.gear):
            self._resolve_triggered_effects(g, "on_attached", bf, self.gs.get_player(side),
                                            self.gs.get_player(self.gs.other(side)),
                                            context_extra={"battlefield": bf, "triggering_unit": unit})

    def _signpost_pair(self, side: str):
        """Forgotten Signpost: (a ready friendly unit at a battlefield to exhaust,
        a different friendly unit in base to move there), the mightiest."""
        ready = [u for bf in self.gs.battlefields for u in bf._units_for(side) if u.ready]
        movers = list(self.gs.get_player(side).base_units)
        if not ready or not movers:
            return None
        return max(ready, key=lambda u: u.might), max(movers, key=lambda u: u.might)

    def _group_move_toll(self, side: str, dst: int) -> int:
        """ "Opponents must pay 1 for each unit beyond the first to move multiple
        units to my battlefield at the same time" (Mageseeker Investigator)."""
        if dst >= len(self.gs.battlefields):
            return 0
        g = self.gs.move_group
        if g is None or g[:3] != (self.gs.turn, side, dst):
            return 0
        bf = self.gs.battlefields[dst]
        return sum(1 for u in bf._units_for(self.gs.other(side))
                   if self._has_effect(u.card, "group_move_toll"))

    def _can_choose(self, unit: UnitInPlay, chooser: str) -> bool:
        """Whether a spell or ability of `chooser` can choose `unit`: not an
        enemy unit that "can't be chosen by enemy spells and abilities" (Ruin
        Runner, Alpha Wildclaw; Twilight Shroud this turn)."""
        where = self._locate_unit(unit)
        if where is None or where[0] == chooser:
            return True
        return not (unit.unchoosable or unit.cant_be_chosen_turn == self.gs.turn)

    def _can_move_to_base(self, unit: UnitInPlay, src_bf: Optional[Battlefield]) -> bool:
        """ "I can't move to base" / "Units can't move to base" (Determined
        Sentry, Minotaur Reckoner), "Units can't move from here to base"
        (Vilemaw's Lair)."""
        if unit.no_move_to_base:
            return False
        if src_bf is not None and src_bf.card is not None:
            spec = CARD_REGISTRY.get(src_bf.card.name)
            if spec and any(es.effect == "no_moves_to_base_from_here" for es in spec.effects):
                return False
        return True

    def _can_ready(self, unit: UnitInPlay) -> bool:
        """Whether a spell or ability can ready `unit`: not "I can't be readied"
        (Maduli), not while its opponent has a Mageseeker Warden at a
        battlefield ("spells and abilities can't ready enemy units")."""
        if unit.cant_ready:
            return False
        where = self._locate_unit(unit)
        if where is None:
            return True
        other = self.gs.other(where[0])
        return not any(self._has_effect(u.card, "warden_no_ready")
                       for bf in self.gs.battlefields for u in bf._units_for(other))

    @staticmethod
    def _has_effect(card: Card, verb: str) -> bool:
        spec = CARD_REGISTRY.get(card.name)
        return bool(spec) and any(es.effect == verb for es in spec.effects)

    def _units_at_battlefields_with(self, side: str, verb: str) -> list:
        return [u for bf in self.gs.battlefields for u in bf._units_for(side)
                if self._has_effect(u.card, verb)]

    def _play_forbidden(self, actor: Player, card: Card) -> bool:
        """Restrictions on playing `card` now: "opponents can't play cards this
        turn" (Brynhir), "I can't be played on your first, second, or third
        turns" (Ol' Poro), a spell an opponent's Fallen Feline named."""
        side = "A" if actor is self.gs.A else "B"
        if self.gs.cant_play_cards_turn.get(side) == self.gs.turn:
            return True
        if self._has_effect(card, "requires_friendly_gear") and not (
                actor.base_gear or self._controlled_attached_gear(side)):
            return True      # "As an additional cost to play me, return a friendly gear"
        if self._has_effect(card, "requires_pet") and not any(
                t in u.tags for u in self._friendly_units_of(side) for t in ("Bird", "Cat", "Dog", "Poro")):
            return True      # "kill a Bird, Cat, Dog, or Poro you control"
        spec = CARD_REGISTRY.get(card.name)
        for es in (spec.effects if spec else ()):
            # "As an additional cost to play this, kill a friendly [Mighty]
            # unit" (Sacrifice): not without one.
            if es.additional_cost and not self._additional_cost_optional(card) and \
                    not self._pay_one_additional_cost(card, actor, es.additional_cost, check_only=True):
                return True
            if es.effect == "play_restriction" and \
                    self.gs.turns_taken.get(side, 0) < int(es.params.get("min_turn", 0)):
                return True
        if isinstance(card, SpellCard):
            for u in self._units_at_battlefields_with(self.gs.other(side), "name_spell"):
                if getattr(u.card, "_named_spell", None) == card.name:
                    return True
        return False

    def _points_allowed(self, side: str, n: int, how: str, bf: Optional[Battlefield] = None) -> int:
        """Points `side` actually gains from `n` it would score by `how`
        ("conquer", "hold", "effect", "burn_out"): none while an opponent's
        Tianna Crownguard is at a battlefield; none at Forgotten Monument
        before the player's third turn; a draw instead during their first two
        turns while Otterpus is in play (conquer / hold, 1 point)."""
        gs = self.gs
        if self._units_at_battlefields_with(gs.other(side), "opponents_cant_gain_points"):
            return 0
        if how in ("conquer", "hold") and bf is not None and bf.card is not None:
            spec = CARD_REGISTRY.get(bf.card.name)
            for es in (spec.effects if spec else ()):
                if es.effect == "no_score_before_turn" and \
                        gs.turns_taken.get(side, 0) < int(es.params.get("turn", 3)):
                    return 0
        if how in ("conquer", "hold") and n == 1 and gs.turns_taken.get(side, 0) <= 2 and \
                any(self._has_effect(u.card, "early_score_draws") for u in self._all_units_in_play()):
            self._draw_one(gs.get_player(side))
            return 0
        points = gs.points_A if side == "A" else gs.points_B
        if how == "conquer" and points + n >= gs.victory_score and any(
                other is not bf and not (other.scored_this_turn_A if side == "A"
                                         else other.scored_this_turn_B)
                for other in gs.battlefields):
            # The Final Point (§473.1.b): through a Conquer only after scoring
            # every battlefield this turn; otherwise draw a card instead.
            self._draw_one(gs.get_player(side))
            return 0
        return n

    def _gain_points(self, side: str, n: int, how: str, bf: Optional[Battlefield] = None) -> int:
        n = self._points_allowed(side, n, how, bf)
        if side == "A":
            self.gs.points_A += n
        else:
            self.gs.points_B += n
        return n

    def _side_has_passive(self, side: str, verb: str) -> bool:
        """Whether something `side` has in play has a passive `verb` effect
        (Karthus Eternal's double_deathknell)."""
        for src, _bf in self._sources_in_play(side):
            spec = CARD_REGISTRY.get(src.name)
            if spec and any(es.trigger == "passive" and es.effect == verb for es in spec.effects):
                return True
        return False

    def _discard(self, player: Player, card: Card) -> None:
        """`player` discards `card` from their hand: to the trash, then its
        "When you discard me" (Flame Chompers, Mask Mother)."""
        if card not in player.hand:
            return
        player.hand.remove(card)
        player.trash.append(card)
        side = "A" if player is self.gs.A else "B"
        self.gs.discarded_this_turn[side] = True
        anchor = self.gs.battlefields[0]
        self._resolve_triggered_effects(card, "on_discarded", anchor, player,
                                        self.gs.get_player(self.gs.other(side)),
                                        context_extra={"battlefield": anchor})
        # "When you discard one or more cards" (Jinx Rebel). Approximation: once
        # per card discarded, not once per discard event.
        self._fire_units_trigger("on_you_discard", side, triggering_card=card)

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
        rounds = 0

        while passes < 2 and self.gs.chain and rounds < _PRIORITY_ROUNDS_CAP:
            rounds += 1
            player = self.gs.get_player(active)
            if player.agent is None:
                passes += 1
                active = self.gs.other(active)
                continue

            action = player.agent.decide_reaction(self.gs.get_player(self.gs.other(active)), self.gs.chain)
            step = "pass" if action[0] == "PASS" else self._reaction_step(player, active, action)
            if step == "kept":
                continue          # a resolved ability: its player keeps priority
            # An action that does nothing (a spell it can't pay for once taxes
            # are added) counts as a pass: two players proposing one each never
            # stopped.
            passes = 0 if step == "acted" else passes + 1
            active = self.gs.other(active)

        self._resolve_chain()

    def _reaction_step(self, player: Player, side: str, action) -> str:
        """`side` takes `action` with priority on an open chain: "acted" (it put
        something on the chain or into play; priority passes), "kept" (a
        REACTION ability resolved; its player keeps priority) or "noop"."""
        kind, idx, lane = action[0], action[1], action[2] if len(action) > 2 else None
        if kind == "SPELL" and idx is not None and 0 <= idx < len(player.hand):
            card = player.hand[idx]
            if isinstance(card, SpellCard) and card.has_keyword("REACTION"):
                if lane is None or not (0 <= lane < len(self.gs.battlefields)):
                    lane = 0
                energy, power = self._effective_cost(card, player, lane)
                if self._pay_card(player, card, energy, power):
                    player.remove_from_hand(idx)
                    self._spell_played(card, player)
                    self.gs.chain.append(ChainItem(player=side, card=card, bf_idx=lane))
                    return "acted"
        elif kind == "GEAR" and idx is not None and 0 <= idx < len(player.hand):
            # QUICK-DRAW gear (§745): played at reaction speed.
            card = player.hand[idx]
            if isinstance(card, GearCard) and card.has_keyword("QUICK-DRAW"):
                before = len(player.hand)
                self._apply_action(player, ("GEAR", idx, lane if lane is not None else 0, None))
                if len(player.hand) < before:
                    return "acted"
        elif kind == "CHAMPION":
            # AMBUSH: deploy the champion to a lane at reaction speed. Not a
            # spell → resolves immediately (no chain), then priority reopens.
            if self._deploy_ambush_champion(side, lane if lane is not None else 0):
                return "acted"
        elif kind == "UNIT" and len(action) > 3:
            # An AMBUSH unit from hand, at reaction speed.
            if self._play_ambush_unit(player, idx, action[3]):
                return "acted"
        elif kind == "HIDDEN_PLAY":
            # Play a facedown card for [0] at reaction speed (§737.1.b).
            if self._play_from_hidden(side, lane if lane is not None else 0):
                return "acted"
        elif kind == "ABILITY":
            # A REACTION ability resolves at once (resource abilities can't be
            # reacted to) and its player keeps priority. One that put a spell on
            # the chain (FLOW) passes priority like a played spell.
            depth = len(self.gs.chain)
            if self._use_ability_now(player, idx, lane):
                return "kept" if len(self.gs.chain) == depth else "acted"
        return "noop"

    def _resolve_chain(self) -> None:
        """Resolve the chain LIFO, each spell to its caster's trash."""
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
                # A resolved spell goes to its caster's trash (KNOWN_ISSUES #19a).
                # Previously cast spells vanished, starving trash-based mechanics
                # (FLOW / recycle / return-from-trash) of any targets. Countered
                # spells are popped + trashed by counter_spell before this loop, so
                # they never reach here — no double-trash.
                self._spell_to_trash(actor, item.card)

    def _run_showdown(self, bf_idx: int, attacker: str) -> None:
        """Execute a showdown at the given battlefield (§337–345)."""
        if self.gs.showdown_active:
            return  # Already in a showdown

        if self.verbose:
            print(f"  [SHOWDOWN triggered at BF{bf_idx}] {attacker} has focus")

        self.gs.showdown_active = True
        self.gs.showdown_attacker = attacker
        self.gs.showdown_bf_idx = bf_idx
        self.gs.focus_player = attacker

        # on_showdown_begin (§Diana Lunari): fire for units at the showdown lane,
        # each routed to its controller (attacker first, mirroring focus order).
        sd_bf = self.gs.battlefields[bf_idx]
        for side in (attacker, self.gs.other(attacker)):
            actor = self.gs.get_player(side)
            opponent = self.gs.get_player(self.gs.other(side))
            for u in list(sd_bf.units_A if side == "A" else sd_bf.units_B):
                self._resolve_triggered_effects(u.card, "on_showdown_begin", sd_bf,
                                                actor, opponent,
                                                context_extra={"battlefield": sd_bf})
        # A contested battlefield: this is the combat showdown, its attack /
        # defend triggers come first (§466.2), then both players act.
        self._open_combat(sd_bf, attacker)

        passes = 0
        rounds = 0
        while passes < 2 and rounds < _PRIORITY_ROUNDS_CAP:
            rounds += 1
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
                step = self._showdown_step(focus_player, self.gs.focus_player, action, bf_idx)
                # A unit that arrived (AMBUSH) becomes an Attacker / Defender now.
                self._open_combat(sd_bf, attacker)
                if step == "kept":
                    passes = 0
                    continue      # an ability resolved: focus stays
                # An action that does nothing counts as a pass (see _run_chain).
                passes = 0 if step == "acted" else passes + 1

            self.gs.focus_player = self.gs.other(self.gs.focus_player)

        self._finish_showdown(bf_idx, attacker)

    def _showdown_step(self, player: Player, side: str, action, bf_idx: int) -> str:
        """`side` (with focus) takes `action` in the showdown at `bf_idx`: "acted"
        (focus passes), "kept" (an ACTION / REACTION ability resolved; focus
        stays) or "noop"."""
        kind, idx, lane = action[0], action[1], action[2] if len(action) > 2 else None
        if kind == "SPELL" and idx is not None and 0 <= idx < len(player.hand):
            card = player.hand[idx]
            if isinstance(card, SpellCard):
                has_action_or_reaction = card.has_keyword("ACTION") or card.has_keyword("REACTION")
                energy, power = self._effective_cost(card, player, bf_idx)
                if has_action_or_reaction and self._pay_card(player, card, energy, power):
                    player.remove_from_hand(idx)
                    self._spell_played(card, player)
                    if self.verbose:
                        print(f"    {side} plays SPELL in showdown: {card.name}")
                    self.gs.chain.append(ChainItem(player=side, card=card, bf_idx=bf_idx))
                    self._run_chain(side)
                    return "acted"
        elif kind == "UNIT" and len(action) > 3 and action[3] is not None:
            # An AMBUSH unit into the showdown's battlefield.
            if self._play_ambush_unit(player, idx, action[3]):
                return "acted"
        elif kind == "UNIT" and idx is not None and 0 <= idx < len(player.hand):
            # ACTION unit (§732.1.c.1): played during a showdown (to base).
            card = player.hand[idx]
            if isinstance(card, UnitCard) and card.has_keyword("ACTION"):
                before = len(player.base_units)
                self._apply_action(player, ("UNIT", idx, bf_idx, None))
                if len(player.base_units) > before:
                    return "acted"
        elif kind == "GEAR" and idx is not None and 0 <= idx < len(player.hand):
            # QUICK-DRAW gear (§745): played during a showdown.
            card = player.hand[idx]
            if isinstance(card, GearCard) and card.has_keyword("QUICK-DRAW"):
                before = len(player.hand)
                self._apply_action(player, ("GEAR", idx, bf_idx, None))
                if len(player.hand) < before:
                    return "acted"
        elif kind == "CHAMPION":
            # AMBUSH: deploy the champion into the showdown lane at reaction speed.
            if self._deploy_ambush_champion(side, bf_idx):
                return "acted"
        elif kind == "HIDDEN_PLAY":
            # Play a facedown card for [0] into the showdown lane (§737.1.b).
            if self._play_from_hidden(side, bf_idx):
                return "acted"
        elif kind == "ABILITY":
            # ACTION / REACTION ability: resolves at once, focus stays.
            if self._use_ability_now(player, idx, lane):
                return "kept"
        return "noop"

    def _finish_showdown(self, bf_idx: int, attacker: str) -> None:
        """Both players passed: the showdown ends, then combat if the battlefield
        is contested, else a conquer."""
        self.gs.showdown_active = False
        self.gs.showdown_bf_idx = None
        self.gs.showdown_attacker = None
        self.gs.focus_player = None

        # Resolve showdown outcome
        bf = self.gs.battlefields[bf_idx]
        if bf.units_A and bf.units_B:
            # Contested: run combat
            self._phase_combat_and_conquer_single(bf_idx, attacker)
            return
        bf.combat_designated, bf.combat_started = set(), False   # no combat after all
        if bf.units_A and not bf.units_B:
            # A controls
            if bf.can_score_conquer("A"):
                self._gain_points("A", 1, "conquer", bf)
                bf.mark_scored("A")
                if self.verbose:
                    print(f"  [CONQUER] A conquers BF{bf_idx} (uncontested showdown) -> +1 VP")
                self._fire_scoring_trigger("on_conquer", bf, "A")
        elif bf.units_B and not bf.units_A:
            # B controls
            if bf.can_score_conquer("B"):
                self._gain_points("B", 1, "conquer", bf)
                bf.mark_scored("B")
                if self.verbose:
                    print(f"  [CONQUER] B conquers BF{bf_idx} (uncontested showdown) -> +1 VP")
                self._fire_scoring_trigger("on_conquer", bf, "B")

    def _open_combat(self, bf: Battlefield, attacker: str) -> None:
        """The combat at `bf` opens (§466.2): start of combat effects, then the
        units there become Attackers / Defenders and their attack / defend
        triggers fire, attacker's first. It opens with the combat showdown, so
        both players can still act before damage (a unit banished for Shadow
        Clone empowers Zed's legend, whose ACTION is then usable). A unit that
        arrives later gets its designation and triggers when this runs again."""
        defender = self.gs.other(attacker)
        if not (bf.units_A and bf.units_B):
            return
        atk_actor, atk_opp = self.gs.get_player(attacker), self.gs.get_player(defender)
        if not bf.combat_started:
            bf.combat_started = True
            # "When combat starts here, the attacker and defender each ADD [1]"
            # (Threshold of the Gray).
            if bf.card is not None:
                for side in (attacker, defender):
                    self._resolve_triggered_effects(bf.card, "on_combat_start_here", bf,
                                                    self.gs.get_player(side),
                                                    self.gs.get_player(self.gs.other(side)),
                                                    context_extra={"battlefield": bf})
        new = {side: [u for u in bf._units_for(side) if id(u) not in bf.combat_designated]
               for side in (attacker, defender)}
        for side in new:
            bf.combat_designated.update(id(u) for u in new[side])
        for unit in new[attacker]:
            for card in [unit.card] + list(unit.gear):
                self._resolve_triggered_effects(card, "on_attack", bf, atk_actor, atk_opp,
                                                context_extra={"battlefield": bf})
            self._apply_disarm(unit, bf, defender)
        # "When a friendly unit attacks / defends (alone), ..." (Mask of Foresight).
        for side, trig in ((attacker, "on_friendly_attack"), (defender, "on_friendly_defend")):
            fighters = list(bf._units_for(side))
            for unit in new[side]:
                self._fire_units_trigger(trig, side, triggering_card=unit.card,
                                         extra={"battlefield": bf, "triggering_unit": unit,
                                                "alone": len(fighters) == 1})
        for unit in new[defender]:
            for card in [unit.card] + list(unit.gear):
                self._resolve_triggered_effects(card, "on_defend", bf, atk_opp, atk_actor,
                                                context_extra={"battlefield": bf})

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

        # Units that fight without having been designated in the showdown (a
        # combat with no showdown, a unit arriving late) get their triggers now.
        defender = self.gs.other(attacker)
        self._open_combat(bf, attacker)
        bf.combat_designated, bf.combat_started = set(), False
        stats = bf.resolve_combat_might(attacker_side=attacker, **self._combat_mods(bf, attacker))
        bf.excess_damage = {"A": (self.gs.turn, stats.excess_by_A), "B": (self.gs.turn, stats.excess_by_B)}

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

        # Combat cleanup (§468.1.a.2): attackers still here with defenders are
        # recalled to their base (not a move).
        if bf.units_A and bf.units_B:
            # "If a combat where you are the attacker ends in a tie, recall ALL
            # units instead" (Symbol of the Solari).
            tie_all = any(self._has_effect(src, "tie_recall_all")
                          for src, _ in self._sources_in_play(attacker))
            for side in ((attacker, defender) if tie_all else (attacker,)):
                for unit in list(bf._units_for(side)):
                    bf.remove_unit(side, unit)
                    self.gs.get_player(side).base_units.append(unit)
            if self.verbose:
                print(f"  [RECALL] {attacker}'s attackers at BF{bf_idx} return to base")

        # on_win_combat: a side won if it still has units and the other doesn't.
        if bf.units_A and not bf.units_B:
            self._fire_units_trigger("on_win_combat", "A")
        elif bf.units_B and not bf.units_A:
            self._fire_units_trigger("on_win_combat", "B")

        if bf.can_score_conquer(attacker):
            self._gain_points(attacker, 1, "conquer", bf)
            bf.mark_scored(attacker)
            if self.verbose:
                print(f"  [CONQUER] {attacker} conquers BF{bf_idx} -> +1 VP")
            self._fire_scoring_trigger("on_conquer", bf, attacker)

    def _combat_mods(self, bf: Battlefield, attacker: str) -> dict:
        """Combat-only rules at `bf`: the damage hook (_take_damage), a side
        that ignores TANK while assigning damage here (Dune Surfer), and Might
        changes while fighting (Forbidding Waste: a lone defender -2; Crimson
        Pigeons: +2 attacking with another unit)."""
        defender = self.gs.other(attacker)
        mods: dict = {}
        if bf.card is not None and self._has_effect(bf.card, "lone_defender_minus") \
                and len(bf._units_for(defender)) == 1:
            mods[id(bf._units_for(defender)[0])] = -2
        attackers = bf._units_for(attacker)
        if len(attackers) >= 2:
            for u in attackers:
                if self._has_effect(u.card, "attacking_with_another_bonus"):
                    mods[id(u)] = mods.get(id(u), 0) + 2

        def surfer(side):
            return any(self._has_effect(u.card, "ignore_tank_here") for u in bf._units_for(side))

        def first(assigner):
            # Which enemy unit `assigner`'s damage kills first. Baseline: the
            # order that kills the most Might (combat.kill_order).
            return lambda units, damage: self.choose("combat_damage_order", assigner, units,
                                                     kill_order(units, damage)[0])
        return {"take": lambda u, a: self._take_damage(u, a, "combat"),
                "ignore_tank_a": surfer("B"), "ignore_tank_b": surfer("A"),
                "might_mods": mods, "first_a": first("B"), "first_b": first("A")}

    def _phase_showdown(self, active: str, opponent: str) -> None:
        pass  # Showdowns now trigger immediately when battlefield contested

    def _phase_combat_and_conquer(self, active: str) -> None:
        self._recompute_passives()

        for bf_idx, bf in enumerate(self.gs.battlefields):
            if not bf.contested_this_turn:
                continue
            if bf.units_A and bf.units_B:
                # Contested by an effect (a unit moved or played there) without
                # a showdown yet: it fights now, the turn player attacking.
                self._phase_combat_and_conquer_single(bf_idx, active)
                continue
            if bf.can_score_conquer(active):
                self._gain_points(active, 1, "conquer", bf)
                bf.mark_scored(active)
                if self.verbose:
                    print(f"  [CONQUER] {active} conquers BF{bf_idx} -> +1 VP")
                self._fire_scoring_trigger("on_conquer", bf, active)

    # ====== MAIN LOOP ======

    def start(self) -> Result:
        """Run a fresh game start-to-finish. Byte-identical to the historical
        control flow — the golden fixture (tests/test_golden_games.py) pins this.
        It is now a thin composition of the resumable pieces below."""
        self._setup()
        return self._play_all_turns()

    def resume_to_completion(self) -> Result:
        """Continue a game from *inside the active player's main action phase* —
        the point at which an agent's ``decide_action`` fires — to the end. Used
        by rollout/search agents on a clone: the clone's beginning phase already
        ran for the current turn, so finish this turn's actions + end, then loop
        the remaining turns. (Step 1 of the search-agent roadmap.)"""
        result = self._run_main_actions() or self._end_turn()
        if result is not None:
            return result
        return self._play_all_turns()

    def _setup(self) -> None:
        """Pre-game setup: place legends, draw opening hands, mulligan. Runs once."""
        gs = self.gs

        # Legends start in play (Legend Zone). Represented as UnitInPlay so they
        # reuse the activated-ability / passive / empower machinery, but kept out
        # of base_units/battlefields so combat and movement never touch them.
        if gs.legend_A is not None and gs.legend_unit_A is None:
            gs.legend_unit_A = UnitInPlay(card=gs.legend_A, ready=True)
        if gs.legend_B is not None and gs.legend_unit_B is None:
            gs.legend_unit_B = UnitInPlay(card=gs.legend_B, ready=True)

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

    def _play_all_turns(self) -> Result:
        """The turn loop: begin → main actions → end, until victory or turn cap."""
        gs = self.gs
        while gs.turn <= gs.max_turns:
            result = self._begin_turn()
            if result is not None:
                return result
            result = self._run_main_actions() or self._end_turn()
            if result is not None:
                return result
        return self._final_result()

    def _begin_turn(self) -> Optional[Result]:
        """Turn header + counter reset + beginning phase (channel/ready/hold-score)
        + start-of-turn triggers + passive recompute + draw. Returns a Result if
        the beginning phase's Hold scoring wins the game, else None."""
        gs = self.gs
        if self.verbose:
            print(f"\n=== TURN {gs.turn} ({gs.active}'s turn) ===")

        # Reset per-turn counters for the condition evaluator. Both players: the
        # non-active one can play reactions this turn too.
        gs.cards_played_this_turn["A"] = gs.cards_played_this_turn["B"] = 0
        gs.spells_played_this_turn["A"] = gs.spells_played_this_turn["B"] = 0
        gs.played_cards_this_turn["A"] = []
        gs.played_cards_this_turn["B"] = []
        gs.A.power_spent_this_turn = gs.B.power_spent_this_turn = 0
        gs.turns_taken[gs.active] = gs.turns_taken.get(gs.active, 0) + 1
        gs.A.draws_this_turn = gs.B.draws_this_turn = 0
        gs.enemy_choices_this_turn["A"] = gs.enemy_choices_this_turn["B"] = 0
        gs.next_card_discounts["A"] = []
        gs.next_card_discounts["B"] = []
        gs.next_units_enter_ready["A"] = gs.next_units_enter_ready["B"] = 0
        gs.friendly_unit_died_this_turn["A"] = False
        gs.friendly_unit_died_this_turn["B"] = False
        gs.discarded_this_turn["A"] = False
        gs.discarded_this_turn["B"] = False
        gs.cards_burned_this_turn["A"] = 0
        gs.cards_burned_this_turn["B"] = 0
        gs.conquered_this_turn["A"] = gs.conquered_this_turn["B"] = 0
        gs.hold_points_this_turn["A"] = gs.hold_points_this_turn["B"] = 0

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
        self._phase_draw(gs.get_player(gs.active))
        return None

    def _run_main_actions(self) -> Optional[Result]:
        """The active player's multi-action main phase (decide_action → apply until
        PASS / no-op / cap). Returns None — kept Optional so callers can chain it
        with `or self._end_turn()`. The cards-played counters live in GameState and
        are kept by the play procedure (_note_card_played), so a mid-turn clone
        continues LEGION counting correctly."""
        gs = self.gs
        ap: Player = gs.get_player(gs.active)
        op: Player = gs.get_player(gs.other(gs.active))

        actions_this_turn = 0
        while True:
            cards_played_this_turn = gs.cards_played_this_turn.get(gs.active, 0)
            if ap.agent is None:
                act: Action = ("PASS", None, None)
            else:
                act = ap.agent.decide_action(op, cards_played=cards_played_this_turn)
            if act[0] == "PASS":
                if gs.pending_move is not None:
                    # Done declaring a move: its showdown, then the turn goes on.
                    self._flush_pending_move()
                    self._recompute_passives()
                    actions_this_turn += 1
                    continue
                if self.verbose:
                    print(f"  {ap.name} passes")
                break
            # No-op guard: if an action leaves the game state unchanged it can
            # never be "used up", so an agent that keeps proposing it (e.g. a
            # MOVE the engine silently refuses) would loop forever. Treat an
            # action that makes no progress as an implicit PASS. The absolute
            # cap is a belt-and-suspenders bound; real turns play far fewer.
            # (An action that ended a move ran its showdown instead: progress.)
            before = self._action_fingerprint(ap, op)
            held = gs.pending_move
            self._apply_action(ap, act, cards_played_this_turn=cards_played_this_turn)
            self._recompute_passives()
            actions_this_turn += 1
            ended_move = held is not None and gs.pending_move is None
            if self._action_fingerprint(ap, op) == before and not ended_move:
                if self.verbose:
                    print(f"  {ap.name} no-op action {act} — ending action phase")
                break
            if actions_this_turn > 200:
                if self.verbose:
                    print(f"  {ap.name} hit action cap — ending action phase")
                break
        self._flush_pending_move()
        return None

    def _end_turn(self) -> Optional[Result]:
        """Showdown + combat/conquer (+victory) + end-of-turn triggers + cleanup +
        advance to the next player/turn. Returns a Result on a combat victory."""
        gs = self.gs
        self._flush_pending_move()   # search agents end turns without a PASS
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
        self._resolve_delayed_effects()
        self._return_borrowed_units()

        # Expiration step (§317.2): heal all units, and "this turn" Might bonuses
        # (REACTION spells like Discipline) end, wherever the unit is.
        for unit in self._all_units_in_play():
            unit.damage = 0
            unit.clear_turn_end_bonuses()

        # Cleanup: a facedown card whose owner no longer controls its battlefield is
        # removed to its owner's trash (§106.4.d / §322.8).
        self._cleanup_hidden_cards()

        if self.verbose:
            bf0 = gs.battlefields[0]
            bf1 = gs.battlefields[1]
            print(f"  [END TURN] Board: BF0={len(bf0.units_A)}A vs {len(bf0.units_B)}B ({bf0.controller() or '?'}) | BF1={len(bf1.units_A)}A vs {len(bf1.units_B)}B ({bf1.controller() or '?'}) | Points: A={gs.points_A} B={gs.points_B}")

        gs.active = gs.other(gs.active)
        gs.turn += 1
        if self.recorder:
            self._snapshot_state()
        return None

    def _final_result(self) -> Result:
        """Decide the winner by points once the turn cap is reached."""
        gs = self.gs
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
