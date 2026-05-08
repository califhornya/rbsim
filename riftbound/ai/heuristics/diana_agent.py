from __future__ import annotations

from riftbound.ai.heuristics.base_agent import Agent
from riftbound.core.cards import UnitCard, SpellCard, GearCard, LegendCard
from riftbound.core.player import Player


class DianaAgent(Agent):
    """Chaos/Mind draw-go spell-control agent built for the Diana deck.

    Strategy: cheap spells + card draw → hand advantage → board control → finishers.
    Key mechanics: Eager Apprentice cost reduction, Ravenbloom spell synergy.
    """

    def decide_action(self, opponent: Player) -> tuple:
        my_side = "A" if self.player.name == "A" else "B"
        bfs = self.player.battlefields
        base_idx = len(bfs)

        candidates = []

        # Score every affordable card in hand
        for idx, card in enumerate(self.player.hand):
            # For spells, use effective cost (accounting for Eager Apprentice discount)
            if isinstance(card, SpellCard):
                effective_cost = self._effective_spell_cost(card, my_side, bfs)
                if not self.player.can_pay_cost(effective_cost, card.cost_power, card.cost_power_domain):
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

    def decide_mulligan(self) -> list[int]:
        """Mulligan away slow and high-power-cost cards. Keep the early engine."""
        indices = []
        for idx, card in enumerate(self.player.hand):
            if card.cost_energy >= 6:
                indices.append(idx)
            elif card.cost_power and card.cost_power >= 1 and card.cost_energy >= 4:
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

    def _effective_spell_cost(self, card: SpellCard, my_side: str, bfs: list) -> int:
        """Reduce spell energy cost by 1 if Eager Apprentice is on the board."""
        has_apprentice = any(
            any(u.card.name == "Eager Apprentice" for u in (bf.units_A if my_side == "A" else bf.units_B))
            for bf in bfs
        )
        return max(1, card.cost_energy - 1) if has_apprentice else card.cost_energy

    def _has_ravenbloom(self, my_side: str, bfs: list) -> bool:
        """Check if Ravenbloom Student is on any friendly battlefield."""
        return any(
            any(u.card.name == "Ravenbloom Student" for u in (bf.units_A if my_side == "A" else bf.units_B))
            for bf in bfs
        )

    def _score_card(self, card, my_side: str, opponent: Player, bfs: list) -> int:
        """Score a card based on its name and board state."""
        name = card.name

        # Ravenbloom bonus: all spells get +2 when Ravenbloom is on board
        ravenbloom_bonus = 2 if isinstance(card, SpellCard) and self._has_ravenbloom(my_side, bfs) else 0

        # Hard-coded card priority table
        if name == "Stupefy":
            return 9 + ravenbloom_bonus
        if name == "Existential Dread":
            opp_units = sum(
                len(bf.units_B if my_side == "A" else bf.units_A)
                for bf in bfs
            )
            return (9 if opp_units > 0 else 5) + ravenbloom_bonus
        if name == "Eager Apprentice":
            return 9
        if name == "Consult the Past":
            return 8 + ravenbloom_bonus
        if name == "Ravenbloom Student":
            return 8
        if name == "Tideturner":
            return 8
        if name == "Eclipse":
            opp_units = sum(
                len(bf.units_B if my_side == "A" else bf.units_A)
                for bf in bfs
            )
            return (8 if opp_units > 0 else 5) + ravenbloom_bonus
        if name == "Stacked Deck":
            return 7 + ravenbloom_bonus
        if name == "Hard Bargain":
            opp_units = sum(
                len(bf.units_B if my_side == "A" else bf.units_A)
                for bf in bfs
            )
            return (7 if opp_units > 0 else 3) + ravenbloom_bonus
        if name == "Moonfall":
            opp_units = sum(
                len(bf.units_B if my_side == "A" else bf.units_A)
                for bf in bfs
            )
            return (7 if opp_units > 0 else 3) + ravenbloom_bonus
        if name == "Ride the Wind":
            has_unit = any(
                len(bf.units_A if my_side == "A" else bf.units_B) > 0
                for bf in bfs
            )
            return (7 if has_unit else 0) + ravenbloom_bonus
        if name == "Gust":
            opp_units_small = any(
                any(u.might <= 3 for u in (bf.units_B if my_side == "A" else bf.units_A))
                for bf in bfs
            )
            return (7 if opp_units_small else 0) + ravenbloom_bonus
        if name == "Traveling Merchant":
            return 6
        if name == "Vex Apathetic":
            return 6
        if name == "Star-Crossed":
            return 5 + ravenbloom_bonus
        if name == "Flash":
            return 5 + ravenbloom_bonus
        if name == "Fizz Trickster":
            score = 5
            has_spell = any(
                c.cost_energy <= 3 and isinstance(c, SpellCard)
                for c in self.player.trash
            )
            return (score + 3 if has_spell else score) + ravenbloom_bonus
        if name == "Hwei Brooding Painter":
            score = 5
            return score - 2 if self.player.energy < 5 else score
        if name == "Thousand-Tailed Watcher":
            score = 5
            return score - 2 if self.player.energy < 7 else score

        # Default low score for unknown cards
        return 1 + ravenbloom_bonus

    def _lane_for_card(self, card, my_side: str, bfs: list) -> int:
        """Choose the best lane for a card based on its type."""
        if isinstance(card, (UnitCard, LegendCard)):
            return self._lane_for_unit(my_side, bfs)
        elif isinstance(card, SpellCard):
            return self._lane_for_spell(my_side, bfs)
        elif isinstance(card, GearCard):
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
        """Deploy Diana Lunari when opponent controls a battlefield and we can afford her."""
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

            # Base score from _score_card
            score = self._score_card(card, my_side, opponent, bfs)

            # Reaction-specific bonuses
            if card.name == "Flash":
                # Flash is good any time; score high
                score = max(score, 7)
            elif card.name == "Hard Bargain":
                # Hard Bargain is a strong counter
                score = max(score, 8)

            if score <= 0:
                continue

            candidates.append((score, idx))

        if not candidates:
            return ("PASS", None, None)

        candidates.sort(key=lambda x: -x[0])
        score, idx = candidates[0]
        # Lane doesn't matter for reactions, but provide 0 as default
        return ("SPELL", idx, 0)
