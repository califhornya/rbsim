from __future__ import annotations
import copy
import pickle
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import random
from .player import Player
from .battlefield import Battlefield, FacedownCard
from .cards import Card

if TYPE_CHECKING:
    from .combat import UnitInPlay


@dataclass
class ChainItem:
    """Item on the spell chain (LIFO stack)."""
    player: str    # "A" or "B"
    card: Card
    bf_idx: int
    # The choices made as it was put on the chain (§355: targets, modes, move
    # destinations, players), used when it resolves: GameLoop._declare_choices.
    # {(run, instruction, n): (kind, n options, chosen)}; chosen is a list for
    # an "up to N" choice.
    declared: Optional[dict] = None
    # Its choices took effect as it was put on the chain (DEFLECT paid, "when
    # you choose me" fired: GameLoop._put_on_chain); its resolution doesn't redo them.
    choices_noted: bool = False
    # Its owner while another player controls it (Mystic Reversal, Rebuttal):
    # the card still goes to the owner's trash.
    owner: Optional[str] = None
    # An activated ability on the chain (§377.3), `card` its source:
    # {"eff": its EffectSpec (None: EQUIP), "kind": the activatable_abilities
    # entry type, "energy": its base Energy cost, "extra": context extra,
    # "target": EQUIP's unit}. None for a played card.
    ability: Optional[dict] = None


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

    # Legend Zone: identity card, in play from the start. Not a combat unit, but
    # carries activated abilities (some Vendetta legends EMPOWER themselves) and
    # can hold the empowered status — represented by a UnitInPlay so it reuses the
    # activated-ability / passive / empower machinery. Created in GameLoop.start().
    legend_A: Optional[Card] = None
    legend_B: Optional[Card] = None
    legend_unit_A: Optional["UnitInPlay"] = None
    legend_unit_B: Optional["UnitInPlay"] = None
    # Neeko Blending In: the legends each player chose while building the deck
    # (§103.1; side -> cards, outside the game), and the ones she added to the
    # Legend Zone (side -> [(legend UnitInPlay, the Neeko UnitInPlay)]): not
    # Champion Legends, removed when their Neeko leaves the board (§107.4.d.2).
    extra_legends: dict = field(default_factory=lambda: {"A": [], "B": []})
    added_legends: dict = field(default_factory=lambda: {"A": [], "B": []})

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
    # A Standard Move that will start a showdown, held while the player keeps
    # moving units to the same battlefield: those units moved together (Core
    # Rules §144.3) and fight together. (battlefield index, moving side).
    pending_move: Optional[tuple] = None
    # Showdowns staged by units an effect moved into a battlefield they contest
    # (Twilight Step): (battlefield index, moving side), run at the next
    # cleanup with no chain or showdown going on (§462).
    staged_showdowns: list = field(default_factory=list)
    showdown_active: bool = False
    showdown_bf_idx: Optional[int] = None
    showdown_attacker: Optional[str] = None   # who started the showdown (Rengar Pouncing)
    focus_player: Optional[str] = None

    # XP per player (HUNT gains it, LEVEL gates on it). Public, no cap.
    xp_A: int = 0
    xp_B: int = 0

    # Per-turn counters (reset at the start of each player's turn). Used by the
    # condition evaluator for LEGION / "you played N spells this turn" / etc.
    cards_played_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    spells_played_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    # The cards each player played this turn, in order (GameLoop._note_card_played),
    # so "if you've played ANOTHER card" can leave out the card asking.
    played_cards_this_turn: dict = field(default_factory=lambda: {"A": [], "B": []})
    # Times each player chose enemy units/gear with a spell or unit ability this
    # turn (Ezreal Prodigal Explorer).
    enemy_choices_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    # "The next card / spell you play this turn costs ... less" (Astral Heron,
    # Raging Firebrand): per player, a list of {filter, energy, power}.
    next_card_discounts: dict = field(default_factory=lambda: {"A": [], "B": []})
    # "At the end of this turn, ..." effects waiting: (side, source card,
    # battlefield index, effect dict).
    delayed_effects: list = field(default_factory=list)
    # "At the start of your next Main Phase, ..." (Iascylla): the same tuples,
    # run at the start of that side's next Main Phase.
    delayed_main: list = field(default_factory=list)
    # Gear to disempower at end of turn (Tornado Warrior; a unit's is
    # UnitInPlay.empower_at_end).
    disempower_gear_at_end: list = field(default_factory=list)
    # "Once each turn" / "The first time ... each turn" abilities used:
    # (id of the source card, effect index) -> turn number.
    once_per_turn_used: dict = field(default_factory=dict)
    # The last turn each side gained XP (Wily Newtfish).
    xp_gained_turn: dict = field(default_factory=dict)
    # Damage rules for one turn: Unyielding Spirit ("Prevent all spell and
    # ability damage this turn"), Imperial Decree ("When any unit takes damage
    # this turn, kill it"), Ravenborn Tome (side -> turn of "the next spell
    # you play this turn deals 1 Bonus Damage").
    no_spell_damage_turn: int = -1
    decree_turn: int = -1
    next_spell_bonus: dict = field(default_factory=dict)
    # "Choose one that hasn't been chosen this turn": (id of card, turn) -> modes.
    modes_chosen: dict = field(default_factory=dict)
    # Last Caress: side -> the turn "the next unit you play this turn can be
    # played to any battlefield" (and is buffed).
    next_unit_any_bf: dict = field(default_factory=dict)
    # Firelights' Hideout: side -> turn "the next unit you play this turn has ACCELERATE".
    next_unit_accelerate: dict = field(default_factory=dict)
    # Temporal Portal: side -> turn "the next spell you play this turn" has REPEAT.
    next_spell_repeat: dict = field(default_factory=dict)
    # Ashe Focused: (owner side, card) banished from a hand until that player holds.
    held_hostage: list = field(default_factory=list)
    # Consecutive Standard Moves to one place: (turn, side, dst, count) —
    # "when you exhaust three or more friendly units at the same time".
    move_group: Optional[tuple] = None
    # Jhin Virtuoso: side -> spells "banished with me".
    jhin_pile: dict = field(default_factory=dict)
    # "If you've spent [4] or more to play a spell this turn" (Prepared
    # Neophyte, Jhin Meticulous Killer): side -> (turn, most Energy spent on one
    # spell that turn).
    spell_spent: dict = field(default_factory=dict)
    # "Your non-token units cost [1] more to play this turn" (Vaults of Helia):
    # (side, turn, card filter, Energy more).
    turn_cost_changes: list = field(default_factory=list)
    # "Take a turn after this one" (Time Warp): who takes the extra turns.
    extra_turns: list = field(default_factory=list)
    # "You can hide ignoring costs this turn" (Guerilla Warfare): side -> turn.
    free_hide: dict = field(default_factory=dict)
    # "Buffs give an additional +1 [might] to friendly units this turn" (Stand
    # United): side -> turn.
    buff_bonus_turn: dict = field(default_factory=dict)
    # "When a friendly unit is played this turn, buff it" (Rally the Troops):
    # side -> turn.
    rally_turn: dict = field(default_factory=dict)
    # 'This turn, that unit has "When I conquer, you may move me to my base"'
    # (Relentless Pursuit): (unit id, turn).
    conquer_return: list = field(default_factory=list)
    # "Its controller can't play spells this turn" (Lilting Lullaby): side -> turn.
    cant_play_spells_turn: dict = field(default_factory=dict)
    # "When I hold, the next time you play a unit this turn, ready it and BUFF
    # it" (Nami Headstrong): side -> turn.
    next_unit_ready_buff: dict = field(default_factory=dict)
    # A friendly unit died during that side's Beginning Phase (Shadow Watcher):
    # side -> turn.
    died_in_beginning: dict = field(default_factory=dict)
    # True while the active player's Beginning Phase runs (Shard of Undoing).
    in_beginning_phase: bool = False
    # Runes each player controlled as the Beginning Phase started, before the
    # channel (Forsaken Baccai): (turn, {side: runes}).
    runes_at_beginning: tuple = (0, {})
    # True while the active player's Ending Phase runs (Runeblade Anvil).
    in_ending_phase: bool = False
    # Turns each player has started ("their third turn": Forgotten Monument).
    turns_taken: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    # "Opponents can't play cards this turn" (Brynhir): side -> that turn.
    cant_play_cards_turn: dict = field(default_factory=dict)
    # "The next three times you play a unit this turn, draw 1" (Fanfare):
    # side -> [turn, plays left].
    unit_play_draws: dict = field(default_factory=dict)
    # "Units you play this turn enter ready" (Confront): the turn it applies to.
    units_enter_ready_turn: dict = field(default_factory=lambda: {"A": -1, "B": -1})
    # "The next unit you play this turn enters ready" (Sun Disc): how many.
    next_units_enter_ready: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    friendly_unit_died_this_turn: dict = field(default_factory=lambda: {"A": False, "B": False})
    # "If a friendly unit or gear died this turn" (Lingering Animus): the gear.
    friendly_gear_died_this_turn: dict = field(default_factory=lambda: {"A": False, "B": False})
    discarded_this_turn: dict = field(default_factory=lambda: {"A": False, "B": False})
    cards_burned_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    conquered_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    hold_points_this_turn: dict = field(default_factory=lambda: {"A": 0, "B": 0})

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
        if amount > 0:
            self.xp_gained_turn[who] = self.turn     # "if you've gained XP this turn"

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
        # Pickling round-trips the whole graph about 3x faster than deepcopy
        # (search clones the state every simulation), with the agents detached
        # for the copy; deepcopy remains for anything pickle refuses.
        agents = (self.A.agent, self.B.agent)
        self.A.agent = self.B.agent = None
        try:
            return pickle.loads(pickle.dumps(self, protocol=pickle.HIGHEST_PROTOCOL))
        except (pickle.PicklingError, TypeError, AttributeError):
            return copy.deepcopy(self)
        finally:
            self.A.agent, self.B.agent = agents


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
    other = gs.other(observer)

    # The opponent's face-down (Hidden) cards are hidden information too: the
    # observer knows a card is hidden there, but not which. Fold them into the
    # unseen pool and resample, preferring a HIDDEN-keyword identity so the public
    # "a card is hidden here" fact stays consistent.
    opp_facedowns = [(bf, slot) for bf in gs.battlefields
                     for slot, fd in enumerate(bf.facedowns) if fd.owner == other]
    pool = list(opp.hand) + list(opp.deck.cards) + [bf.facedowns[slot].card for bf, slot in opp_facedowns]
    rng.shuffle(pool)
    for bf, slot in opp_facedowns:
        pick = next((c for c in pool if c.has_keyword("HIDDEN")), pool[0] if pool else None)
        if pick is None:
            continue
        pool.remove(pick)
        fd = bf.facedowns[slot]
        bf.facedowns[slot] = FacedownCard(card=pick, owner=fd.owner, turn_hidden=fd.turn_hidden)

    n_hand = len(opp.hand)
    opp.hand = pool[:n_hand]
    opp.deck.cards = pool[n_hand:]

    rng.shuffle(me.deck.cards)
    rng.shuffle(opp.deck.cards)
    return gs
