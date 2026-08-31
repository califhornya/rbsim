from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence
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
class RuneDeck:
    runes: List[Rune]

    def draw(self) -> Optional[Rune]:
        if not self.runes:
            return None
        return self.runes.pop(0)

    def recycle(self, rune: Rune) -> None:
        rune.refresh()
        self.runes.append(rune)


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
    trash: List[Card] = field(default_factory=list)
    banished: List[Card] = field(default_factory=list)
    base_gear: List[Card] = field(default_factory=list)

    energy: int = 0

    rune_deck: RuneDeck = field(default_factory=lambda: RuneDeck([]))
    rune_pool: Dict[Domain, List[Rune]] = field(default_factory=dict)
    power_pool: Dict[Domain, int] = field(default_factory=dict)
    base_units: List[UnitInPlay] = field(default_factory=list)

    @classmethod
    def from_cards_and_runes(
        cls,
        name: str,
        cards: Sequence[Card],
        rune_domains: Sequence[Domain] | None = None,
        agent_class=None
    ) -> "Player":
        """Create a player with properly initialized deck and rune deck for simulation.

        Args:
            name: Player name ("A" or "B")
            cards: List of Card objects for the deck
            rune_domains: List of Domain enums for runes (defaults to 6x FURY, 4x CALM, 4x MIND)
            agent_class: Optional agent class to instantiate
        """
        if rune_domains is None:
            rune_domains = [
                Domain.FURY, Domain.FURY, Domain.FURY, Domain.FURY, Domain.FURY, Domain.FURY,
                Domain.CALM, Domain.CALM, Domain.CALM, Domain.CALM,
                Domain.MIND, Domain.MIND, Domain.MIND, Domain.MIND,
            ]

        runes = [Rune(domain=d) for d in rune_domains]

        # Convert CardSpec objects to Card objects if needed
        instantiated_cards = []
        for card in cards:
            if hasattr(card, 'instantiate'):
                instantiated_cards.append(card.instantiate())
            else:
                instantiated_cards.append(card)

        deck = Deck(cards=instantiated_cards)
        rune_deck = RuneDeck(runes=runes)

        player = cls(
            name=name,
            deck=deck,
            rune_deck=rune_deck
        )

        if agent_class:
            player.agent = agent_class(player)

        return player

    def add_rune(self, domain: Domain, *, ready: bool = True) -> Rune:
        rune = Rune(domain=domain, ready=ready)
        self.rune_pool.setdefault(domain, []).append(rune)
        return rune

    def total_runes_in_play(self) -> int:
        return sum(len(runes) for runes in self.rune_pool.values())

    def unlock_runes(self, n: int = 2, *, exhausted: bool = False) -> None:
        """Bring n runes from the deck into play (max 12 total)."""

        for _ in range(n):
            if self.total_runes_in_play() >= 12:
                break
            rune = self.rune_deck.draw()
            if rune is None:
                break
            rune.ready = not exhausted
            self.rune_pool.setdefault(rune.domain, []).append(rune)

    def recycle_rune(self, domain: Domain) -> bool:
        """Recycle one rune of the given domain (move from play to bottom of deck)."""

        runes = self.rune_pool.get(domain, [])
        if not runes:
            return False
        rune = runes.pop(0)
        if not runes:
            self.rune_pool.pop(domain, None)
        self.rune_deck.recycle(rune)
        return True

    def channel(self) -> None:
        """Tap every ready rune in the pool: each yields +1 energy and +1 power of
        its domain. Per Riftbound RAW each rune has [E]: Add [1] available every
        turn, so every player effectively channels their entire pool each turn."""

        # Refresh all runes at the beginning of the channel step
        for runes in self.rune_pool.values():
            for rune in runes:
                rune.refresh()

        for domain in sorted(self.rune_pool, key=lambda d: d.name):
            for rune in self.rune_pool[domain]:
                if rune.ready:
                    result = rune.activate()
                    if result is not None:
                        self.energy += 1
                        self.power_pool[result] = self.power_pool.get(result, 0) + 1

    def ready_base_units(self) -> None:
        for unit in self.base_units:
            unit.ready = True

    def pop_base_unit(self) -> Optional[UnitInPlay]:
        # Only non-token units may move from base to a battlefield; tokens are
        # skipped so a ready token can't block a movable unit behind it.
        for idx, unit in enumerate(self.base_units):
            if unit.ready and not unit.is_token:
                return self.base_units.pop(idx)
        return None

    def has_movable_base_unit(self) -> bool:
        """True if a ready non-token unit is available to move to a battlefield."""
        return any(u.ready and not u.is_token for u in self.base_units)

    def can_pay_cost(self, cost_energy: int = 0, cost_power: Optional[int] = None, cost_power_domain: Optional[Domain] = None) -> bool:
        if self.energy < cost_energy:
            return False
        if cost_power is None or cost_power_domain is None:
            return True
        if self.power_pool.get(cost_power_domain, 0) < cost_power:
            return False
        runes = self.rune_pool.get(cost_power_domain, [])
        return len(runes) >= cost_power

    def pay_cost(self, cost_energy: int = 0, cost_power: Optional[int] = None, cost_power_domain: Optional[Domain] = None) -> bool:
        if not self.can_pay_cost(cost_energy, cost_power, cost_power_domain):
            return False
        self.energy -= cost_energy
        if cost_power and cost_power_domain:
            current = self.power_pool.get(cost_power_domain, 0) - cost_power
            if current <= 0:
                self.power_pool.pop(cost_power_domain, None)
            else:
                self.power_pool[cost_power_domain] = current
            for _ in range(cost_power):
                if not self.recycle_rune(cost_power_domain):
                    return False
        return True

    def draw(self) -> Optional[Card]:
        card = self.deck.draw()
        if card:
            self.hand.append(card)
        return card

    def burn(self, n: int) -> list:
        """Vendetta BURN X: move the top X cards of the Main Deck to the trash.
        Returns the list of burned cards (may be shorter than n if the deck runs
        out). 'Top' of deck is the end of the list (Deck.draw pops from there)."""
        burned = []
        for _ in range(max(0, int(n))):
            card = self.deck.draw()
            if card is None:
                break
            self.trash.append(card)
            burned.append(card)
        return burned

    def mulligan(self, indices, rng) -> list:
        """Riftbound mulligan (Core Rules §117): set aside up to TWO chosen cards,
        draw that many replacements from the top, THEN Recycle the set-aside cards
        to the BOTTOM of the deck (random order when 2, §416.5). No shuffle.

        `indices` are hand positions to return; anything past the first two, or
        out of range, is ignored (§117.1 caps it at two). Returns the cards that
        were actually set aside (for logging)."""
        chosen = [i for i in dict.fromkeys(indices) if 0 <= i < len(self.hand)][:2]
        if not chosen:
            return []
        set_aside = [self.hand[i] for i in chosen]
        for i in sorted(chosen, reverse=True):
            self.hand.pop(i)
        # 117.2: draw the replacements from the top FIRST (deck.draw pops the end).
        for _ in set_aside:
            c = self.deck.draw()
            if c is not None:
                self.hand.append(c)
        # 117.3: recycle the set-aside cards to the BOTTOM (front of the list, the
        # opposite end from draw), so they are not the ones just drawn.
        recycled = list(set_aside)
        if len(recycled) > 1:
            rng.shuffle(recycled)
        self.deck.cards[:0] = recycled
        return set_aside

    def remove_from_hand(self, idx: int) -> None:
        del self.hand[idx]
