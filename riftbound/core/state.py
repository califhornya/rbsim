from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import random
from .player import Player
from .battlefield import Battlefield
from .cards import Card


@dataclass
class ChainItem:
    """Item on the spell chain (LIFO stack)."""
    player: str    # "A" or "B"
    card: Card
    bf_idx: int


@dataclass
class GameState:
    rng: random.Random
    A: Player
    B: Player

    turn: int = 1
    max_turns: int = 40
    active: str = "A"

    # Champion Zone: the Chosen Champion card for each player (not in main deck)
    champion_A: Optional[Card] = None
    champion_B: Optional[Card] = None

    # Victory points via Hold/Conquer
    points_A: int = 0
    points_B: int = 0
    victory_score: int = 8  # Duel Mode default

    # Exactly two battlefields total in 1v1
    battlefields: list[Battlefield] = field(default_factory=lambda: [Battlefield(), Battlefield()])

    # Champion deployment state
    champion_A_deployed: bool = False
    champion_B_deployed: bool = False

    # Chain and Showdown state
    chain: list[ChainItem] = field(default_factory=list)
    showdown_active: bool = False
    showdown_bf_idx: Optional[int] = None
    focus_player: Optional[str] = None

    # XP per player (HUNT gains it, LEVEL gates on it). Public, no cap.
    xp_A: int = 0
    xp_B: int = 0

    # Per-turn counters (reset at the start of each player's turn). Used by the
    # condition evaluator for LEGION / "you played N spells this turn" / etc.
    cards_played_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    spells_played_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    friendly_unit_died_this_turn: dict = field(default_factory=lambda: {"A": False, "B": False})
    discarded_this_turn: dict = field(default_factory=lambda: {"A": False, "B": False})

    def other(self, who: str) -> str:
        return "B" if who == "A" else "A"

    def get_player(self, who: str) -> Player:
        return self.A if who == "A" else self.B

    def get_xp(self, who: str) -> int:
        return self.xp_A if who == "A" else self.xp_B

    def add_xp(self, who: str, amount: int) -> None:
        if who == "A":
            self.xp_A += amount
        else:
            self.xp_B += amount

    def clone(self) -> "GameState":
        """A deep, independent copy of the game state — the primitive search
        (MCTS) and speculative "what if I play this?" evaluation build on.

        Agents are deliberately dropped (the clone's players have ``agent=None``):
        an agent back-references its ``GameLoop`` and, through it, the DB recorder
        / SQLAlchemy session, none of which are copyable or meaningful on a clone.
        Everything else — cards, units, runes, battlefields, chain, counters, and
        the RNG (copied with its current state) — is duplicated, so mutating the
        clone never touches the original.
        """
        memo: dict[int, object] = {}
        # Pre-seed the memo so deepcopy substitutes None for each agent instead of
        # recursing into the loop/recorder graph hanging off it.
        for player in (self.A, self.B):
            if player.agent is not None:
                memo[id(player.agent)] = None
        return copy.deepcopy(self, memo)


def determinize(gs: "GameState", observer: str, rng: random.Random) -> "GameState":
    """Randomise the information hidden from ``observer``, in place, for ISMCTS.

    From the observer's seat the opponent's hand *contents* and both players' deck
    *orders* are unknown. We keep counts and every public fact (board, trash,
    points, energy, the observer's own hand) fixed, and resample the hidden parts:

    * the opponent's hand is redealt from their unseen pool (their current hand +
      deck), so it stays the right size but its identities are randomised;
    * both decks are shuffled (the observer knows neither order).

    Mutates and returns ``gs`` (normally a :meth:`GameState.clone`). Card objects
    are only moved between the opponent's own zones, so conservation is preserved.
    """
    me = gs.get_player(observer)
    opp = gs.get_player(gs.other(observer))

    pool = list(opp.hand) + list(opp.deck.cards)
    rng.shuffle(pool)
    n_hand = len(opp.hand)
    opp.hand = pool[:n_hand]
    opp.deck.cards = pool[n_hand:]

    rng.shuffle(me.deck.cards)
    rng.shuffle(opp.deck.cards)
    return gs
