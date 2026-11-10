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

    # Energy (`energy` = the two). The engine exhausts every rune for its Energy
    # as the turn begins, so `rune_energy` stands for runes still ready (kept
    # through the opponent's turn); `pool_energy` is what an ADD put in the Rune
    # Pool: spent first, lost when the pool empties (§167).
    rune_energy: int = 0
    pool_energy: int = 0
    # Earmarked resources (§ restricted-use): in the pool, lost when it empties.
    earmarked_energy_showdown: int = 0  # Diana Scorn: energy spendable only in showdowns
    earmarked_power_gear: int = 0       # Ornn: generic power spendable only for gear
    earmarked_power_spell: int = 0      # Kai'Sa: generic power spendable only for spells
    earmarked_power_permanent: int = 0  # Mordekaiser: generic power only for units or gear
    earmarked_energy_spell: int = 0     # Lux Crownguard: energy spendable only for spells
    earmarked_energy_unit: int = 0      # Renekton Butcher: only for units or units' abilities

    rune_deck: RuneDeck = field(default_factory=lambda: RuneDeck([]))
    rune_pool: Dict[Domain, List[Rune]] = field(default_factory=dict)
    power_pool: Dict[Domain, int] = field(default_factory=dict)
    # The part of power_pool added by effects ("ADD [fury]": Seals, Gold) rather
    # than backed by a rune: spent first, without recycling a rune; lost when
    # the pool empties.
    floating_power: Dict[Domain, int] = field(default_factory=dict)
    # Power paid this turn ("If you've spent at least [rune] [rune] this turn").
    power_spent_this_turn: int = 0
    # Cards drawn this turn ("When you draw your second card each turn").
    draws_this_turn: int = 0
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

    @property
    def energy(self) -> int:
        return self.rune_energy + self.pool_energy

    @energy.setter
    def energy(self, value: int) -> None:
        """Spending takes the pool's Energy first (it would be lost anyway); a
        gain set this way (a refund) is a rune's. An ADD is `add_energy`."""
        delta = value - self.energy
        if delta < 0:
            from_pool = min(-delta, max(self.pool_energy, 0))
            self.pool_energy -= from_pool
            self.rune_energy += delta + from_pool
        else:
            self.rune_energy += delta

    def add_energy(self, amount: int) -> None:
        """ADD Energy (§430): into the Rune Pool, lost when it empties."""
        self.pool_energy += amount

    def ready_runes(self, n: int) -> None:
        """Ready n runes, each exhausted again at once for its Energy. With
        fewer exhausted runes (their Energy unused), the player exhausts a ready
        one first (its Energy to the pool), then readies it."""
        exhausted = max(0, self.total_runes_in_play() - self.rune_energy)
        k = min(n, exhausted)
        self.rune_energy += k
        self.pool_energy += n - k

    def runes_left_play(self) -> None:
        """Runes left play: a ready one goes only when none is exhausted, and
        the player exhausts it first (its Energy to the pool)."""
        over = self.rune_energy - self.total_runes_in_play()
        if over > 0:
            self.rune_energy -= over
            self.pool_energy += over

    def empty_rune_pool(self) -> None:
        """The Rune Pool empties (§167): unspent Energy and Power an ADD put
        there are lost; ready runes keep theirs."""
        self.pool_energy = 0
        for domain, n in self.floating_power.items():
            left = self.power_pool.get(domain, 0) - n
            if left > 0:
                self.power_pool[domain] = left
            else:
                self.power_pool.pop(domain, None)
        self.floating_power.clear()
        self.earmarked_energy_showdown = 0
        self.earmarked_power_gear = 0
        self.earmarked_power_spell = 0
        self.earmarked_power_permanent = 0
        self.earmarked_energy_spell = 0
        self.earmarked_energy_unit = 0

    def add_rune(self, domain: Domain, *, ready: bool = True) -> Rune:
        rune = Rune(domain=domain, ready=ready)
        self.rune_pool.setdefault(domain, []).append(rune)
        return rune

    def total_runes_in_play(self) -> int:
        return sum(len(runes) for runes in self.rune_pool.values())

    def unlock_runes(self, n: int = 2, *, exhausted: bool = False) -> None:
        """Bring n runes from the deck into play (max 12 total). Each can be
        recycled for its Power at once (§164.2.b); a ready one is exhausted for
        its Energy at once, as `channel` does."""

        for _ in range(n):
            if self.total_runes_in_play() >= 12:
                break
            rune = self.rune_deck.draw()
            if rune is None:
                break
            rune.ready = False
            self.rune_pool.setdefault(rune.domain, []).append(rune)
            self.power_pool[rune.domain] = self.power_pool.get(rune.domain, 0) + 1
            if not exhausted:
                self.rune_energy += 1

    def recycle_rune(self, domain: Domain) -> bool:
        """Recycle one rune of the given domain (move from play to bottom of deck)."""

        runes = self.rune_pool.get(domain, [])
        if not runes:
            return False
        rune = runes.pop(0)
        if not runes:
            self.rune_pool.pop(domain, None)
        self.rune_deck.recycle(rune)
        self.runes_left_play()
        # "When you recycle a rune" (Sivir Battle Mistress): GameLoop drains it.
        self.runes_recycled = getattr(self, "runes_recycled", 0) + 1
        return True

    def awaken_runes(self) -> None:
        """Awaken (§315.1): every rune readies."""
        for runes in self.rune_pool.values():
            for rune in runes:
                rune.refresh()

    def channel(self) -> None:
        """Tap every ready rune in the pool: each yields +1 energy and +1 power of
        its domain. Per Riftbound RAW each rune has [E]: Add [1] available every
        turn, so every player effectively channels their entire pool each turn
        (the turn's own channeled runes were tapped as they came, an exhausted
        one gives no Energy)."""

        for domain in sorted(self.rune_pool, key=lambda d: d.name):
            for rune in self.rune_pool[domain]:
                if rune.ready:
                    result = rune.activate()
                    if result is not None:
                        self.rune_energy += 1
                        self.power_pool[result] = self.power_pool.get(result, 0) + 1
        # Generic Power is paid in this dict's order: by domain name.
        order = sorted(self.power_pool.items(), key=lambda kv: kv[0].name)
        self.power_pool.clear()
        self.power_pool.update(order)

    def ready_base_units(self) -> None:
        for unit in self.base_units:
            unit.ready = True

    def pop_base_unit(self) -> Optional[UnitInPlay]:
        # Token units take the Standard Move like any unit (§185.2.d).
        for idx, unit in enumerate(self.base_units):
            if unit.ready:
                return self.base_units.pop(idx)
        return None

    def has_movable_base_unit(self) -> bool:
        """True if a ready unit is available to move to a battlefield."""
        return any(u.ready for u in self.base_units)

    def can_pay_cost(self, cost_energy: int = 0, cost_power: Optional[int] = None, cost_power_domain: Optional[Domain] = None) -> bool:
        if self.energy < cost_energy:
            return False
        if not cost_power:
            return True
        if cost_power_domain is None:
            # A card with no single power domain: [A], power of any domain
            # (§135.2.e.6.b; the loop narrows a multi-domain card to its own).
            return self.can_pay_power_of(cost_power, list(Domain))
        return self._power_left(cost_power_domain) >= cost_power

    def _power_left(self, domain: Domain) -> int:
        """Power of `domain` this player can pay now."""
        return min(self.power_pool.get(domain, 0),
                   len(self.rune_pool.get(domain, [])) + self.floating_power.get(domain, 0))

    def can_pay_power_of(self, n: int, domains) -> bool:
        """Whether n power can be paid from any mix of `domains`."""
        return sum(self._power_left(d) for d in domains) >= n

    def pay_power_of(self, n: int, domains) -> bool:
        """Pay n power from any mix of `domains`, each from the one with the most left."""
        domains = list(domains)
        for _ in range(n):
            d = max(domains, key=self._power_left)
            if not self._power_left(d) or not self.pay_cost(0, 1, d):
                return False
        return True

    def pay_cost(self, cost_energy: int = 0, cost_power: Optional[int] = None, cost_power_domain: Optional[Domain] = None) -> bool:
        if not self.can_pay_cost(cost_energy, cost_power, cost_power_domain):
            return False
        self.energy -= cost_energy
        if cost_power and cost_power_domain is None:
            return self.pay_power_of(cost_power, list(Domain))
        if cost_power and cost_power_domain:
            self.power_spent_this_turn += cost_power
            current = self.power_pool.get(cost_power_domain, 0) - cost_power
            if current <= 0:
                self.power_pool.pop(cost_power_domain, None)
            else:
                self.power_pool[cost_power_domain] = current
            floating = min(cost_power, self.floating_power.get(cost_power_domain, 0))
            if floating:
                self.floating_power[cost_power_domain] -= floating
            for _ in range(cost_power - floating):
                if not self.recycle_rune(cost_power_domain):
                    return False
        return True

    def add_power(self, domain: Domain, amount: int = 1) -> None:
        """ADD Power of a domain from an effect (not a rune): spendable this turn."""
        self.power_pool[domain] = self.power_pool.get(domain, 0) + amount
        self.floating_power[domain] = self.floating_power.get(domain, 0) + amount

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
