from __future__ import annotations

from riftbound.ai.heuristics.base_agent import Agent
from riftbound.core.cards import UnitCard, SpellCard, GearCard, LegendCard
from riftbound.core.player import Player
from riftbound.core.legion_effects import get_legion_cost_reduction


class PykeAgent(Agent):
    """Fury/Chaos tempo-control agent built for the Pyke deck.

    Strategy: cheap filtering + hand disruption early, bounce removal mid, big threats late.
    """

    def decide_action(self, opponent: Player, cards_played: int = 0) -> tuple:
        my_side = "A" if self.player.name == "A" else "B"
        bfs = self.player.battlefields
        base_idx = len(bfs)

        candidates = []

        # Score every affordable card in hand
        for idx, card in enumerate(self.player.hand):
            # For units, check affordability with LEGION discount
            if isinstance(card, (UnitCard, LegendCard)):
                effective_energy = self._effective_unit_cost(card, cards_played)
                if not self.player.can_pay_cost(effective_energy, card.cost_power, card.cost_power_domain):
                    continue
            else:
                if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                    continue

            score = self._score_card(card, my_side, opponent, bfs)
            if score <= 0:
                continue

            lane = self._lane_for_card(card, my_side, bfs)

            if isinstance(card, (UnitCard, LegendCard)):
                action = "UNIT"
            elif isinstance(card, SpellCard):
                action = "SPELL"
            elif isinstance(card, GearCard):
                action = "GEAR"
            else:
                continue

            candidates.append((score, (action, idx, lane)))

        # Score MOVE opportunity
        move_score = self._score_move(my_side, bfs)
        if move_score > 0:
            best_bf = self._lane_for_unit(my_side, bfs)
            candidates.append((move_score, ("MOVE", None, base_idx, best_bf)))

        # Champion deploy check (highest priority)
        if self._should_deploy_champion(my_side, opponent, bfs):
            lane = self._lane_for_unit(my_side, bfs)
            return ("CHAMPION", None, lane)

        if not candidates:
            return ("PASS", None, None)

        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    def _effective_unit_cost(self, card, cards_played: int) -> int:
        """Compute effective energy cost for units, accounting for LEGION discount."""
        energy = card.cost_energy
        if card.has_keyword("LEGION") and cards_played > 0:
            legion_reduction = get_legion_cost_reduction(card.name)
            if legion_reduction is not None:
                energy = max(0, energy - legion_reduction)
        return energy

    def decide_mulligan(self) -> list[int]:
        """Mulligan away slow cards (cost >= 5) and high-power-cost cards."""
        indices = []
        for idx, card in enumerate(self.player.hand):
            if card.cost_energy >= 5:
                indices.append(idx)
            elif card.cost_power and card.cost_power >= 2 and card.cost_energy >= 3:
                indices.append(idx)
        return indices

    def _score_move(self, my_side: str, bfs: list) -> int:
        """Score the value of moving a ready base unit to a battlefield."""
        ready_unit = next((u for u in self.player.base_units if u.ready), None)
        if ready_unit is None:
            return 0
        # High value: opponent controls a bf we don't
        opp_side = "B" if my_side == "A" else "A"
        for bf in bfs:
            if bf.controller() == opp_side:
                return 8
        # Medium: contested (no one controls, both have units)
        for bf in bfs:
            if bf.units_A and bf.units_B:
                return 7
        # Baseline: just getting presence on the board
        return 5

    def _score_card(self, card, my_side: str, opponent: Player, bfs: list) -> int:
        """Score a card based on its name and board state."""
        name = card.name

        # Hard-coded card priority table
        if name == "Stacked Deck":
            return 9
        if name == "Tideturner":
            return 8
        if name == "Bewitching Spirit":
            return 8
        if name == "Treasure Trove":
            # Only play if we have a unit to attach to
            has_unit = any(
                len(bf.units_A if my_side == "A" else bf.units_B) > 0
                for bf in bfs
            )
            return 8 if has_unit else 0
        if name == "Gust":
            # Check if opponent has a unit with might <= 3
            opp_side = "B" if my_side == "A" else "A"
            has_target = any(
                any(u.might <= 3 for u in (bf.units_B if my_side == "A" else bf.units_A))
                for bf in bfs
            )
            return 8 if has_target else 0
        if name == "Death from Below":
            opp_side = "B" if my_side == "A" else "A"
            has_target = any(
                any(u.might <= 3 for u in (bf.units_B if my_side == "A" else bf.units_A))
                for bf in bfs
            )
            return 8 if has_target else 5
        if name == "Fizz Trickster":
            # +2 if we have a playable spell in trash
            score = 7
            has_spell = any(
                c.cost_energy <= 3 and isinstance(c, SpellCard)
                for c in self.player.trash
            )
            return score + 2 if has_spell else score
        if name == "Treasure Hunter":
            return 7
        if name == "Sharkling":
            return 7
        if name == "Falling Star":
            opp_units = sum(
                len(bf.units_B if my_side == "A" else bf.units_A)
                for bf in bfs
            )
            return 7 if opp_units > 0 else 5
        if name == "Detonate":
            # Check if opponent has gear
            has_gear = any(
                any(len(u.gear) > 0 for u in (bf.units_B if my_side == "A" else bf.units_A))
                for bf in bfs
            )
            return 7 if has_gear else 0
        if name == "Noxus Hopeful":
            return 6
        if name == "Rebuke":
            opp_units = sum(
                len(bf.units_B if my_side == "A" else bf.units_A)
                for bf in bfs
            )
            return 6 if opp_units > 0 else 3
        if name == "Pack of Wonders":
            has_unit = any(
                len(bf.units_A if my_side == "A" else bf.units_B) > 0
                for bf in bfs
            )
            return 5 if has_unit else 2
        if name == "Star-Crossed":
            return 4
        if name == "Mindsplitter":
            score = 5
            return score - 2 if self.player.energy < 9 else score
        if name == "Baron Nashor":
            score = 4
            return score - 2 if self.player.energy < 9 else score

        # Default low score for unknown cards
        return 1

    def _lane_for_card(self, card, my_side: str, bfs: list) -> int:
        """Choose the best lane for a card based on its type."""
        if isinstance(card, (UnitCard, LegendCard)):
            # Units/Legends go to the most threatened lane (lowest differential)
            return self._lane_for_unit(my_side, bfs)
        elif isinstance(card, SpellCard):
            # Spells go to the lane with the most enemy units
            return self._lane_for_spell(my_side, bfs)
        elif isinstance(card, GearCard):
            # Gear goes to the lane with friendly units
            return self._lane_for_unit(my_side, bfs)
        return 0

    def _lane_for_unit(self, my_side: str, bfs: list) -> int:
        """Find the lane where we're most behind (or tied)."""
        best_lane = 0
        best_diff = float("inf")

        for i, bf in enumerate(bfs):
            my_units = len(bf.units_A if my_side == "A" else bf.units_B)
            opp_units = len(bf.units_B if my_side == "A" else bf.units_A)
            diff = my_units - opp_units
            if diff < best_diff:
                best_diff = diff
                best_lane = i

        return best_lane

    def _lane_for_spell(self, my_side: str, bfs: list) -> int:
        """Find the lane with the most enemy units (best removal target)."""
        best_lane = 0
        best_count = 0

        for i, bf in enumerate(bfs):
            opp_count = len(bf.units_B if my_side == "A" else bf.units_A)
            if opp_count > best_count:
                best_count = opp_count
                best_lane = i

        return best_lane

    def _should_deploy_champion(self, my_side: str, opponent: Player, bfs: list) -> bool:
        """Deploy champion when affordable and opponent controls at least one battlefield."""
        if not hasattr(self, "gs") or self.gs is None:
            return False

        champion = self.gs.champion_A if my_side == "A" else self.gs.champion_B
        if champion is None:
            return False

        is_A = my_side == "A"
        already_deployed = (
            self.gs.champion_A_deployed if is_A else self.gs.champion_B_deployed
        )
        if already_deployed:
            return False

        if not self.player.can_pay_cost(
            champion.cost_energy, champion.cost_power, champion.cost_power_domain
        ):
            return False

        # Deploy if opponent controls any battlefield
        opp_side = "B" if my_side == "A" else "A"
        for bf in bfs:
            if bf.controller() == opp_side:
                return True

        return False

    def decide_showdown_action(self, opponent: Player, bf_idx: int) -> tuple:
        """Play best ACTION or REACTION spell during showdown."""
        my_side = "A" if self.player.name == "A" else "B"
        bfs = self.player.battlefields

        candidates = []
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, SpellCard):
                continue
            if not (card.has_keyword("ACTION") or card.has_keyword("REACTION")):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue

            score = self._score_card(card, my_side, opponent, bfs)
            if score <= 0:
                continue

            candidates.append((score, idx))

        if not candidates:
            return ("PASS", None, None)

        candidates.sort(key=lambda x: -x[0])
        score, idx = candidates[0]
        return ("SPELL", idx, bf_idx)

    def decide_reaction(self, opponent: Player, chain: list) -> tuple:
        """Play REACTION spell in response to chain."""
        my_side = "A" if self.player.name == "A" else "B"
        bfs = self.player.battlefields

        candidates = []
        for idx, card in enumerate(self.player.hand):
            if not isinstance(card, SpellCard):
                continue
            if not card.has_keyword("REACTION"):
                continue
            if not self.player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                continue

            score = self._score_card(card, my_side, opponent, bfs)

            # PykeAgent mostly passes reactions, but plays high-value ones
            if score < 5:
                continue

            candidates.append((score, idx))

        if not candidates:
            return ("PASS", None, None)

        candidates.sort(key=lambda x: -x[0])
        score, idx = candidates[0]
        return ("SPELL", idx, 0)

