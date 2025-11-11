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
    hp: int = 10
    hand: List[Card] = field(default_factory=list)
    deck: Deck = field(default_factory=lambda: Deck([]))
    agent: object = None  # set by CLI after Player creation

    def draw(self) -> Optional[Card]:
        card = self.deck.draw()
        if card:
            self.hand.append(card)
        return card

    def remove_from_hand(self, idx: int) -> None:
        del self.hand[idx]
