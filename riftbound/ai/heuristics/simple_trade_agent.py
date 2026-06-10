from __future__ import annotations

from typing import Optional

from riftbound.ai.heuristics.base_agent import Agent
from riftbound.core.cards import GearCard, LegendCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.player import Player


class SimpleTradeAgent(Agent):
    """Generic trade-focused heuristic.

    Goal: kill enemy units on contested battlefields so the opponent cannot Hold them
    next turn. Plays no card-specific logic — only the four pillars below.

    Decision order in Neutral Open State (`decide_action`):
      1. CHAMPION: deploy when affordable.
      2. MOVE: attack an enemy-controlled or shared BF when the trade math is favorable.
      3. GEAR: equip on a unit at a contested or near-contested BF.
      4. SPELL: cast a might-buff REACTION on a friendly unit at a contested BF.
      5. UNIT: develop a new body to Base for a future Move.
      6. MOVE: claim an empty BF (Non-Combat Showdown -> Conquer).
      7. PASS.

    In Showdown (`decide_showdown_action`) and Closed (`decide_reaction`) states the
    agent restricts itself to spells whose printed timing (ACTION / REACTION) allows
    them — the engine enforces this, the agent just avoids burning energy on illegal
    plays.
    """

    name = "SimpleTrade"

    # ------------------------------------------------------------------
    # Main-phase decision

    def decide_action(self, opponent: Player, cards_played: int = 0) -> tuple:
        my_side = "A" if self.player.name == "A" else "B"
        bfs = self.player.battlefields
        base_idx = len(bfs)

        # 1. Champion deploy — high priority once affordable
        champ_action = self._maybe_deploy_champion(my_side)
        if champ_action is not None:
            return champ_action

        # 2. Trade-finisher MOVE: attack any BF where adding our smallest sufficient
        #    base unit gives us total Might >= opp total Might at that BF.
        trade_move = self._find_trade_move(my_side, bfs, base_idx)
        if trade_move is not None:
            return trade_move

        # 3. Equip a GEAR on a unit at a friendly BF (preferably one with the
        #    strongest unit). Gear auto-attaches to the first friendly unit at the
        #    target lane per the loop's GEAR handler.
        gear_action = self._find_gear_play(my_side, bfs)
        if gear_action is not None:
            return gear_action

        # 4. Cast a might-buff REACTION spell on a friendly unit at a contested BF.
        spell_action = self._find_combat_spell(my_side, bfs)
        if spell_action is not None:
            return spell_action

        # 4b. Use an activated ability (incl. EQUIP of gear waiting at base).
        ability_action = self._find_activated_ability(my_side)
        if ability_action is not None:
            return ability_action

        # 5. Develop a UNIT to Base (engine always routes UNIT plays to base_units).
        unit_action = self._find_unit_to_develop(cards_played)
        if unit_action is not None:
            return unit_action

        # 6. Conquer an empty BF if we have a ready unit waiting.
        empty_bf_move = self._find_empty_bf_move(my_side, bfs, base_idx)
        if empty_bf_move is not None:
            return empty_bf_move

        # 7. Tempo: rather than waste leftover energy, bank an affordable gear at
        #    base now so it can be EQUIPped onto a unit on a later turn.
        stage_gear = self._find_gear_to_stage()
        if stage_gear is not None:
            return stage_gear

        return ("PASS", None, None)

    # ------------------------------------------------------------------
    # Mulligan

    def decide_mulligan(self) -> list[int]:
        """Mulligan expensive cards (cost >= 5). Keep cheap units, gear, reactions."""
        return [
            idx
            for idx, card in enumerate(self.player.hand)
            if card.cost_energy >= 5
        ]

    # ------------------------------------------------------------------
    # Showdown / Reaction

    def decide_showdown_action(self, opponent: Player, bf_idx: int) -> tuple:
        """During a Showdown only [ACTION] / [REACTION] spells are legal."""
        bfs = self.player.battlefields
        my_side = "A" if self.player.name == "A" else "B"

        candidates: list[tuple[int, int]] = []
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, SpellCard):
                continue
            if not (card.has_keyword("ACTION") or card.has_keyword("REACTION")):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue
            score = self._score_combat_spell(card, my_side, bfs, bf_idx)
            if score <= 0:
                continue
            candidates.append((score, idx))

        if not candidates:
            return ("PASS", None, None)

        candidates.sort(key=lambda p: -p[0])
        return ("SPELL", candidates[0][1], bf_idx)

    def decide_reaction(self, opponent: Player, chain: list) -> tuple:
        """Closed State — only [REACTION] spells are legal."""
        bfs = self.player.battlefields
        my_side = "A" if self.player.name == "A" else "B"

        # React to chain items targeting one of our BFs if we have a friendly unit there.
        target_bf = 0
        if chain:
            last = chain[-1]
            bf_idx = getattr(last, "bf_idx", 0)
            if 0 <= bf_idx < len(bfs):
                target_bf = bf_idx

        candidates: list[tuple[int, int]] = []
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, SpellCard):
                continue
            if not card.has_keyword("REACTION"):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue
            score = self._score_combat_spell(card, my_side, bfs, target_bf)
            # Only spend a reaction if the spell genuinely helps a friendly unit there
            if score < 3:
                continue
            candidates.append((score, idx))

        if not candidates:
            return ("PASS", None, None)

        candidates.sort(key=lambda p: -p[0])
        return ("SPELL", candidates[0][1], target_bf)

    # ------------------------------------------------------------------
    # Helpers

    def _opp_side(self, my_side: str) -> str:
        return "B" if my_side == "A" else "A"

    def _trade_math(self, bf, my_side: str) -> tuple[int, int, list, list]:
        """Return (my_might, opp_might, my_units, opp_units) at this battlefield."""
        my_units = bf.units_A if my_side == "A" else bf.units_B
        opp_units = bf.units_B if my_side == "A" else bf.units_A
        my_might = sum(u.might for u in my_units if not u.stunned)
        opp_might = sum(u.might for u in opp_units if not u.stunned)
        return my_might, opp_might, my_units, opp_units

    def _maybe_deploy_champion(self, my_side: str) -> Optional[tuple]:
        gs = getattr(self, "gs", None)
        if gs is None:
            return None
        is_A = my_side == "A"
        champion = gs.champion_A if is_A else gs.champion_B
        if champion is None:
            return None
        already = gs.champion_A_deployed if is_A else gs.champion_B_deployed
        if already:
            return None
        if not self.player.can_pay_cost(champion.cost_energy, champion.cost_power, champion.cost_power_domain):
            return None
        return ("CHAMPION", None, 0)

    def _find_trade_move(self, my_side: str, bfs: list, base_idx: int) -> Optional[tuple]:
        """Pick the smallest sufficient base unit that turns a contested/enemy BF into
        a favorable trade (our total Might >= their total Might after move-in)."""
        ready_base = [
            u for u in self.player.base_units
            if u.ready and not u.is_token and (u.card.might or 0) > 0
        ]
        if not ready_base:
            return None
        # Smallest sufficient unit first — we don't overcommit.
        ready_base.sort(key=lambda u: (u.card.might or 0))

        best: Optional[tuple[int, int]] = None  # (score, bf_idx)
        chosen_action: Optional[tuple] = None

        opp_side = self._opp_side(my_side)
        for bf_idx, bf in enumerate(bfs):
            my_now, opp_now, my_units, opp_units = self._trade_math(bf, my_side)
            if not opp_units:
                continue  # no one to trade with
            for candidate in ready_base:
                projected = my_now + candidate.might
                if projected < opp_now:
                    continue  # losing trade
                # Score: prefer attacks that deny a current opponent Hold.
                score = 10
                if bf.controller() == opp_side:
                    score += 5  # denying their Hold is best
                if projected > opp_now:
                    score += 3  # we likely have survivors -> Conquer
                if best is None or score > best[0]:
                    best = (score, bf_idx)
                    chosen_action = ("MOVE", None, base_idx, bf_idx)
                break  # smallest sufficient unit wins; move on to next BF

        return chosen_action

    def _find_gear_play(self, my_side: str, bfs: list) -> Optional[tuple]:
        """Play a gear targeting a lane that has friendly units (auto-attach).
        Fall back to playing it (it will land in base_gear) if nothing's on a BF."""
        # Find a gear in hand we can afford
        gear_idx: Optional[int] = None
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, GearCard):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue
            gear_idx = idx
            break
        if gear_idx is None:
            return None

        # Target the BF with our strongest unit (best beneficiary of the gear).
        best_lane: Optional[int] = None
        best_might = -1
        for bf_idx, bf in enumerate(bfs):
            my_units = bf.units_A if my_side == "A" else bf.units_B
            if not my_units:
                continue
            top = max(u.might for u in my_units)
            if top > best_might:
                best_might = top
                best_lane = bf_idx

        if best_lane is None:
            # No friendly units on any BF; only worth playing the gear if it's cheap,
            # otherwise we'd rather develop a body first.
            return None
        return ("GEAR", gear_idx, best_lane)

    def _find_combat_spell(self, my_side: str, bfs: list) -> Optional[tuple]:
        """Cast a might-buff spell on a friendly unit at a contested BF."""
        # Pick the target BF: the one where the trade is closest and a buff would flip it.
        target_bf: Optional[int] = None
        best_gap = 999  # smaller is better — we want a swingable trade
        for bf_idx, bf in enumerate(bfs):
            my_might, opp_might, my_units, opp_units = self._trade_math(bf, my_side)
            if not my_units or not opp_units:
                continue
            gap = opp_might - my_might  # positive = we're behind, the spell can save us
            if gap >= 0 and gap < best_gap:
                best_gap = gap
                target_bf = bf_idx
        if target_bf is None:
            return None

        candidates: list[tuple[int, int]] = []
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, SpellCard):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue
            score = self._score_combat_spell(card, my_side, bfs, target_bf)
            if score <= 0:
                continue
            candidates.append((score, idx))

        if not candidates:
            return None
        candidates.sort(key=lambda p: -p[0])
        return ("SPELL", candidates[0][1], target_bf)

    def _score_combat_spell(self, card: SpellCard, my_side: str, bfs: list, bf_idx: int) -> int:
        """Score a spell for a contested-BF context. Generic, name-free."""
        score = 0
        # Real effect data: prefer spells that actually grant might.
        for effect in card.effects or []:
            if not isinstance(effect, dict):
                continue
            eff = effect.get("effect")
            amount = int(effect.get("amount", 0) or 0)
            if eff in {"grant_might", "grant_temporary_might",
                       "grant_temporary_might_per_enemy",
                       "grant_temporary_might_per_friendly"}:
                score += 4 + amount
            elif eff in {"deal_damage", "kill_unit"}:
                score += 4 + amount
            else:
                score += 1
        # If the card has no parsed effects but is a REACTION/ACTION spell, still
        # treat it as marginally useful (counterspell, retreat, filter, etc.).
        if score == 0:
            if card.has_keyword("REACTION") or card.has_keyword("ACTION"):
                score = 2
        return score

    def _find_activated_ability(self, my_side: str) -> Optional[tuple]:
        """Pick the first affordable activated ability whose cost actually consumes
        a resource (taps the source or spends energy/power) — this guards against
        re-triggering a free ability forever in the multi-action loop. EQUIP entries
        (re-attaching base gear) are always finite and included."""
        loop = getattr(self, "loop", None)
        if loop is None:
            return None
        abilities = loop.activatable_abilities(my_side)
        for idx, entry in enumerate(abilities):
            if entry["type"] == "equip":
                gear = entry["gear"]
                if not self.player.can_pay_cost(
                    gear.cost_energy, gear.cost_power, gear.cost_power_domain
                ):
                    continue
                if loop._first_friendly_unit_on_board(my_side) is None:
                    continue
                return ("ABILITY", "ACTIVATED", idx)
            parsed = loop._parse_activated_cost(entry["eff"].cost)
            # Only resource-consuming abilities — never spin on a free/no-op one.
            if not (parsed["tap"] or parsed["energy"] or parsed["power"]):
                continue
            if not loop._activated_affordable(self.player, entry["unit"], parsed):
                continue
            return ("ABILITY", "ACTIVATED", idx)
        return None

    def _find_gear_to_stage(self) -> Optional[tuple]:
        """Last-resort tempo play: deploy an affordable gear when no better action
        exists. With no friendly unit at the lane the engine routes it to base_gear,
        where it waits to be EQUIPped later — strictly better than passing and
        wasting the energy. Energy-bounded, so it can't dump the whole hand at once."""
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, GearCard):
                continue
            if not self.player.can_pay_cost(
                card.cost_energy, card.cost_power, card.cost_power_domain
            ):
                continue
            return ("GEAR", idx, 0)
        return None

    def _find_unit_to_develop(self, cards_played: int) -> Optional[tuple]:
        """Play the highest-Might unit we can afford. UNIT plays always go to base."""
        best: Optional[tuple[int, int]] = None  # (score, hand_idx)
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, (UnitCard, LegendCard)):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue
            might = card.might or 0
            score = might
            # Light keyword bonus (Tank / Shield X / Assault X) without going name-specific.
            for kw in ("TANK", "SHIELD", "ASSAULT"):
                if card.has_keyword(kw):
                    score += 1
            if best is None or score > best[0]:
                best = (score, idx)
        if best is None:
            return None
        return ("UNIT", best[1], 0)

    def _find_empty_bf_move(self, my_side: str, bfs: list, base_idx: int) -> Optional[tuple]:
        """Walk a ready base unit onto an uncontrolled BF to Conquer it."""
        ready = next(
            (u for u in self.player.base_units if u.ready and not u.is_token),
            None,
        )
        if ready is None:
            return None
        for bf_idx, bf in enumerate(bfs):
            if not bf.units_A and not bf.units_B and bf.controller() != my_side:
                return ("MOVE", None, base_idx, bf_idx)
        return None
