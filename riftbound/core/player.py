from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import random
from .cards import Card

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

    # Rune/Energy system
    energy: int = 0
    max_energy: int = 10
    channel_rate: int = 1  # energy gained each CHANNEL phase, capped by max_energy

    def can_pay(self, cost: int) -> bool:
        return self.energy >= cost

    def pay(self, cost: int) -> bool:
        if self.energy >= cost:
            self.energy -= cost
            return True
        return False

    def channel(self) -> None:
        self.energy = min(self.max_energy, self.energy + self.channel_rate)

    def draw(self) -> Optional[Card]:
        card = self.deck.draw()
        if card:
            self.hand.append(card)
        return card

    def remove_from_hand(self, idx: int) -> None:
        del self.hand[idx]
