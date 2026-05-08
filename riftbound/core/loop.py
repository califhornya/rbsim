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
from .enums import Domain

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
    
    def _player_for_target(self, target: str) -> Player:
        key = target.lower()
        if key in {"actor", "ally", "self"}:
            return self.actor
        if key in {"opponent", "enemy"}:
            return self.opponent
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

        # Route spell-killed units to trash and gear to base
        owner = self.loop.gs.A if target_side == "A" else self.loop.gs.B
        for dead_unit in dead:
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
        if hasattr(gs.B, "agent") and gs.B.agent:
            gs.B.agent.player.battlefields = gs.battlefields
            gs.B.agent.gs = gs

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

        active_player.unlock_runes(2)
        active_player.channel()
        # Only the Turn Player channels — opponent channels on their own turn

        vps = 0
        for bf in self.gs.battlefields:
            if bf.can_score_hold(active):
                vps += 1
                bf.mark_scored(active)
        return vps

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

        if not effect_specs:
            if isinstance(card, SpellCard):
                context.deal_damage(int(getattr(card, "damage", 0)), target="opponent")
            return

        for effect_spec in effect_specs:
            handler = EFFECT_REGISTRY.get(effect_spec.effect)
            if not handler:
                continue
            handler(context, effect_spec.params)

        # REPEAT (Rule 746): run effects a second time
        # NOTE: REPEAT is optional additional cost in actual rules, but simulator always repeats if keyword present.
        # TODO: Verify REPEAT interacts correctly with all effect types (especially card draw, damage, etc.)
        if card.has_keyword("REPEAT"):
            for effect_spec in effect_specs:
                handler = EFFECT_REGISTRY.get(effect_spec.effect)
                if not handler:
                    continue
                handler(context, effect_spec.params)        

    def _apply_action(self, ap: Player, action: Action, cards_played_this_turn: int = 0) -> None:
        if len(action) == 3:  # type: ignore[arg-type]
            kind, idx, lane = action  # type: ignore[misc]
            dst_lane = None
        else:
            kind, idx, lane, dst_lane = action

        if kind != "MOVE" and lane is not None and not (0 <= lane < len(self.gs.battlefields)):
            lane = 0
        if dst_lane is not None and not (0 <= dst_lane < len(self.gs.battlefields) + 1):
            dst_lane = None

        base_index = len(self.gs.battlefields)

        opponent = self.gs.get_player(self.gs.other(self.gs.active))           

        if kind == "UNIT" and idx is not None and 0 <= idx < len(ap.hand):
            card = ap.hand[idx]
            if isinstance(card, (UnitCard, LegendCard)):
                if not ap.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                    return
                if not ap.pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
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

                # LEGION (Rule 738): trigger effects if another card was played this turn
                # NOTE: Per rules, a card is "played" when fully resolved. Countered spells don't count.
                # BUT LEGION units ARE considered played even if later countered (peculiarity of LEGION).
                # Counter system is deferred; this check works for non-counter context.
                if card.has_keyword("LEGION") and cards_played_this_turn > 0:
                    self._resolve_card_effects(card, self.gs.battlefields[0], ap, opponent)

                # WEAPONMASTER: auto-attach first gear from base if available
                if card.has_keyword("WEAPONMASTER") and ap.base_gear:
                    gear_card = ap.base_gear.pop(0)
                    unit.gear.append(gear_card)

                ap.remove_from_hand(idx)
                self.units_played += 1
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
                if not ap.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                    return
                if not ap.pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                    return
                target_lane = lane if lane is not None else 0
                ap.remove_from_hand(idx)
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
                if not ap.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                    return
                if not ap.pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                    return
                target_bf = self.gs.battlefields[lane if lane is not None else 0]
                friendly_units = target_bf.units_A if self.gs.active == "A" else target_bf.units_B

                if friendly_units:
                    target_unit = friendly_units[0]
                    target_unit.gear.append(card)
                else:
                    ap.base_gear.append(card)

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
                unit.ready = False
                target_bf = self.gs.battlefields[dst]
                target_bf.add_unit(side, unit)

                # Trigger showdown if battlefield becomes contested
                opp_units = target_bf.units_B if side == "A" else target_bf.units_A
                if opp_units:
                    self._run_showdown(dst, attacker=side)

            elif dst == base_index:
                src_bf = self.gs.battlefields[src]
                unit = src_bf.pop_unit_for_movement(side)
                if unit is None:
                    return
                unit.ready = True
                base.append(unit)
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
                dst_bf.add_unit(side, unit)

                # Trigger showdown if battlefield becomes contested
                opp_units = dst_bf.units_B if side == "A" else dst_bf.units_A
                if opp_units:
                    self._run_showdown(dst, attacker=side)

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
        elif bf.units_B and not bf.units_A:
            # B controls
            if bf.can_score_conquer("B"):
                self.gs.points_B += 1
                bf.mark_scored("B")

    def _phase_combat_and_conquer_single(self, bf_idx: int, attacker: str) -> None:
        """Resolve combat for a single battlefield."""
        bf = self.gs.battlefields[bf_idx]
        before_A = list(bf.units_A)
        before_B = list(bf.units_B)

        stats = bf.resolve_combat_might(attacker_side=attacker)

        # Route dead units
        for dead_unit in stats.dead_A:
            self.gs.A.trash.append(dead_unit.card)
            self.gs.A.base_gear.extend(dead_unit.gear)
        for dead_unit in stats.dead_B:
            self.gs.B.trash.append(dead_unit.card)
            self.gs.B.base_gear.extend(dead_unit.gear)

        # Trigger DEATHKNELL effects
        for dead_unit in stats.dead_A + stats.dead_B:
            if dead_unit.card.has_keyword("DEATHKNELL"):
                if dead_unit in stats.dead_A:
                    actor = self.gs.A
                    opponent = self.gs.B
                else:
                    actor = self.gs.B
                    opponent = self.gs.A
                self._resolve_card_effects(dead_unit.card, bf, actor, opponent)

        if self.recorder:
            self._record_combat_deaths(bf, before_A, before_B)

        if bf.can_score_conquer(attacker):
            if attacker == "A":
                self.gs.points_A += 1
            else:
                self.gs.points_B += 1
            bf.mark_scored(attacker)

    def _phase_showdown(self, active: str, opponent: str) -> None:
        pass  # Showdowns now trigger immediately when battlefield contested

    def _phase_combat_and_conquer(self, active: str) -> None:

        for bf in self.gs.battlefields:
            before_A = list(bf.units_A)
            before_B = list(bf.units_B)
            if bf.contested_this_turn:
                stats = bf.resolve_combat_might(attacker_side=active)

                # Route dead units to trash and gear to base
                for dead_unit in stats.dead_A:
                    self.gs.A.trash.append(dead_unit.card)
                    self.gs.A.base_gear.extend(dead_unit.gear)
                for dead_unit in stats.dead_B:
                    self.gs.B.trash.append(dead_unit.card)
                    self.gs.B.base_gear.extend(dead_unit.gear)

                # Trigger DEATHKNELL effects
                for dead_unit in stats.dead_A + stats.dead_B:
                    if dead_unit.card.has_keyword("DEATHKNELL"):
                        if dead_unit in stats.dead_A:
                            actor = self.gs.A
                            opponent = self.gs.B
                        else:
                            actor = self.gs.B
                            opponent = self.gs.A
                        self._resolve_card_effects(dead_unit.card, bf, actor, opponent)

                if self.recorder:
                    self._record_combat_deaths(bf, before_A, before_B)
                if bf.can_score_conquer(active):
                    if active == "A":
                        self.gs.points_A += 1
                    else:
                        self.gs.points_B += 1
                    bf.mark_scored(active)


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

        gs.A.unlock_runes(2)
        gs.B.unlock_runes(3)

        self._phase_mulligan()

        if self.recorder:
            self._snapshot_state(turn_override=0)

        while gs.turn <= gs.max_turns:
            if self.verbose:
                print(f"\n=== TURN {gs.turn} ({gs.active}'s turn) ===")

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


            ap: Player = gs.get_player(gs.active)
            op: Player = gs.get_player(gs.other(gs.active))
            self._phase_draw(ap)

            # Multi-action turn loop
            cards_played_this_turn = 0
            while True:
                if ap.agent is None:
                    act: Action = ("PASS", None, None)
                else:
                    act = ap.agent.decide_action(op)
                if act[0] == "PASS":
                    if self.verbose:
                        print(f"  {ap.name} passes")
                    break
                self._apply_action(ap, act, cards_played_this_turn=cards_played_this_turn)
                cards_played_this_turn += 1

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
