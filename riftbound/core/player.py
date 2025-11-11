from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random

from .cards import Card
from .combat import UnitInPlay
from .enums import Domain


@dataclass
class Rune:
    domain: Domain
    ready: bool = True

    def activate(self) -> Optional[Domain]:
        if not self.ready:
            return None
        self.ready = False
        return self.domain

    def refresh(self) -> None:
        self.ready = True

@dataclass
class Deck:
    cards: List[Card]

    def shuffle(self, rng: random.Random) -> None:
        rng.shuffle(self.cards)

    def draw(self) -> Optional[Card]:
        if not self.cards:
            return None
        return self.cards.pop()


@dataclass
class Player:
    name: str
    hp: int = 10  # legacy; not used in VP rules but kept for compatibility
    hand: List[Card] = field(default_factory=list)
    deck: Deck = field(default_factory=lambda: Deck([]))
    agent: object = None  # set by CLI after Player creation

    energy: int = 0

    rune_pool: Dict[Domain, List[Rune]] = field(default_factory=dict)
    power_pool: Dict[Domain, int] = field(default_factory=dict)
    base_units: List[UnitInPlay] = field(default_factory=list)

    def add_rune(self, domain: Domain, *, ready: bool = True) -> None:
        self.rune_pool.setdefault(domain, []).append(Rune(domain=domain, ready=ready))

    def channel(self) -> None:
        """Channel up to two ready runes, producing energy and power tokens."""

        # Refresh all runes at the beginning of the channel step
        for runes in self.rune_pool.values():
            for rune in runes:
                rune.refresh()

        channels_remaining = 2
        for domain in sorted(self.rune_pool, key=lambda d: d.name):
            runes = self.rune_pool[domain]
            for rune in runes:
                if channels_remaining <= 0:
                    break
                if rune.ready:
                    result = rune.activate()
                    if result is not None:
                        self.energy += 1
                        self.power_pool[result] = self.power_pool.get(result, 0) + 1
                        channels_remaining -= 1
            if channels_remaining <= 0:
                break

    def ready_base_units(self) -> None:
        for unit in self.base_units:
            unit.ready = True

    def pop_base_unit(self) -> Optional[UnitInPlay]:
        for idx, unit in enumerate(self.base_units):
            if unit.ready:
                return self.base_units.pop(idx)
        return None

    def can_pay(self, cost: int) -> bool:
        return self.energy >= cost

    def pay(self, cost: int) -> bool:
        if self.energy >= cost:
            self.energy -= cost
            return True
        return False

    def can_pay_cost(self, cost_energy: int = 0, cost_power: Optional[Domain] = None) -> bool:
        if self.energy < cost_energy:
            return False
        if cost_power is None:
            return True
        return self.power_pool.get(cost_power, 0) > 0

    def pay_cost(self, cost_energy: int = 0, cost_power: Optional[Domain] = None) -> bool:
        if not self.can_pay_cost(cost_energy, cost_power):
            return False
        self.energy -= cost_energy
        if cost_power is not None:
            self.power_pool[cost_power] = self.power_pool.get(cost_power, 0) - 1
            if self.power_pool[cost_power] <= 0:
                del self.power_pool[cost_power]
        return True

    def draw(self) -> Optional[Card]:
        card = self.deck.draw()
        if card:
            self.hand.append(card)
        return card

    def remove_from_hand(self, idx: int) -> None:
        del self.hand[idx]
