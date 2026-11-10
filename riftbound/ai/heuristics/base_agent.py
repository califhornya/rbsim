from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from riftbound.core.cards import SpellCard
from riftbound.core.legality import _affordable
from riftbound.core.loop import GameLoop, _ADD_VERBS
from riftbound.core.player import Player

# Add abilities used in a row to pay for one thing, at most; ADD sequences tried
# (game copies) to find the shortest that pays for it.
_MAX_ADDS = 8
_ADD_SEARCH = 24
# A player's resources an Add ability changes.
_RESOURCES = ("rune_energy", "pool_energy", "power_pool", "floating_power",
              "earmarked_energy_showdown", "earmarked_power_gear", "earmarked_power_spell",
              "earmarked_power_permanent", "earmarked_energy_spell", "earmarked_energy_unit")


def _entry_key(entry: dict) -> tuple:
    """An activatable_abilities entry, the same on a copy of the game."""
    src = entry.get("unit") or entry.get("gear") or entry.get("card") or entry.get("bf")
    src = getattr(src, "card", src)
    eff = entry.get("eff")
    return (entry["type"], getattr(src, "uuid", None), getattr(eff, "effect", None), entry.get("copy"))


def _find_card(loop: GameLoop, player: Player, uuid: str):
    """`player`'s card with this uuid in hand or the Champion Zone (a copy's)."""
    champ = loop.gs.champion_A if player is loop.gs.A else loop.gs.champion_B
    return next((c for c in list(player.hand) + [champ] if c is not None and c.uuid == uuid), None)

# Action signature supports multiple action types:
# ("SPELL"|"UNIT"|"MOVE"|"PASS"|"ABILITY", ...)
# For UNIT/SPELL: (TYPE, hand_idx, target_lane)
# For MOVE: ("MOVE", None, src_lane, dst_lane)
# For ABILITY: ("ABILITY", ability_id, arg)
Action = tuple

class Agent(ABC):
    name: str = "Agent"

    def __init__(self, player: Player):
        self.player = player
        # GameLoop will inject: self.player.battlefields = list[Battlefield]
        self._begin_decision()

    # ------------------------------------------------------------------
    # Paying: what a card costs now, and the Add abilities that pay for it.
    # An Add ability (Seals, Gold, Lux's Energy, ...) resolves at once and what
    # it adds is lost as the turn ends, so it is used while paying (§430.3):
    # right before the play it pays for, never on its own.

    def _begin_decision(self) -> None:
        """Called as each decide_* starts: the game may have changed."""
        self._adds_now = None

    def _card_check(self, card, lane: Optional[int] = None, dst=None):
        """A check (loop, player) -> bool: whether `card` (in hand or the
        Champion Zone) can be paid, aimed at battlefield `lane` (a spell) or
        played to battlefield `dst` (a unit, DEPLOY gear): what it costs now
        (_effective_cost: every reduction and tax), its Power from any of its
        domains, the discounts it may take (Seraphine Starry-Eyed Songstress,
        Irelia Graceful, an alternate cost, ...); a spell, if it has its
        targets there (§355.8). Without a loop: its printed cost."""
        uuid = card.uuid

        def check(loop, player) -> bool:
            if loop is None:
                return player.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain)
            c = card if loop is getattr(self, "loop", None) else _find_card(loop, player, uuid)
            if c is None or not _affordable(loop, player, c, lane, dst):
                return False
            return not (isinstance(c, SpellCard) and lane is not None) or \
                loop._spell_has_targets(c, player.name, lane)
        return check

    def _entry_check(self, entry: dict):
        """A check (loop, player) -> bool: whether this activatable_abilities
        entry (an ability, an EQUIP, a play from the trash) can be used."""
        key = _entry_key(entry)

        def check(loop, player) -> bool:
            if loop is getattr(self, "loop", None):
                found = entry
            else:
                found = next((e for e in loop.activatable_abilities(player.name)
                              if _entry_key(e) == key), None)
            return found is not None and loop._ability_usable(player, found)
        return check

    def _can_pay(self, check) -> bool:
        """Whether `check` holds now, or once Add abilities are used."""
        return check(getattr(self, "loop", None), self.player) or self._adds_may_pay(check)

    def _paying(self, action: tuple, check) -> Optional[tuple]:
        """`action`, if `check` holds now; else, when Add abilities pay for
        it, the one to use first of the shortest sequence that does (the next
        decision plays it); else None."""
        if check(getattr(self, "loop", None), self.player):
            return action
        if not self._adds_may_pay(check):
            return None
        first = self._first_add(check)
        return ("ABILITY", "ACTIVATED", first) if first is not None else None

    def _best_payable(self, candidates: list) -> Optional[tuple]:
        """Of `candidates` (score, action, check, or None for nothing to pay),
        best score first (ties: in order), the first that can be paid:
        _paying's action for it. None if none can."""
        for _score, action, check in sorted(candidates, key=lambda c: -c[0]):
            paid = action if check is None else self._paying(action, check)
            if paid is not None:
                return paid
        return None

    def _adds_may_pay(self, check) -> bool:
        """Whether `check`, false now, holds once Add abilities are used: with
        what every Add ability would add (_all_adds), then, when that isn't
        conclusive, by trying sequences of them (_first_add)."""
        loop = getattr(self, "loop", None)
        if loop is None:
            return False
        if getattr(self, "_adds_now", None) is None:
            entries = loop.activatable_abilities(self.player.name)
            self._adds_now = (id(loop.gs), loop.gs.turn,
                              tuple(_entry_key(entries[i]) for i in self._add_entries(loop, self.player)))
        if not self._adds_now[2]:
            return False
        gains, conclusive = self._all_adds(loop)
        player = self.player
        saved = {k: getattr(player, k) for k in _RESOURCES}
        try:
            for k, gain in gains.items():
                if isinstance(gain, dict):
                    pool = dict(saved[k])
                    for d, n in gain.items():
                        pool[d] = max(0, pool.get(d, 0) + n)
                    setattr(player, k, pool)
                else:
                    setattr(player, k, max(0, saved[k] + gain))
            if check(loop, player):
                return True
        finally:
            for k, v in saved.items():
                setattr(player, k, v)
        return not conclusive and self._first_add(check) is not None

    @staticmethod
    def _add_entries(loop: GameLoop, player: Player) -> list:
        """Indices of the Add abilities `player` can use now: those that only
        exhaust first, then those that cost Energy or Power or convert it,
        then those that give something up (Gold, Malzahar Fanatic's token)."""
        out = []
        for i, entry in enumerate(loop.activatable_abilities(player.name)):
            eff = entry.get("eff")
            if entry["type"] not in ("ability", "gear_ability") or eff is None or \
                    eff.effect not in _ADD_VERBS or not loop._ability_usable(player, entry):
                continue
            parsed = loop._parse_activated_cost(eff.cost)
            if parsed["kill_other_token"] and loop._token_to_kill(player.name, entry.get("unit")) is None:
                continue        # only a token is given up for it (simple_trade)
            gives_up = any(parsed[k] for k in ("sacrifice", "kill_other_token", "kill_other_friendly",
                                               "kill_friendly_gear", "banish_from_trash", "banish_self",
                                               "discard", "recycle", "spend_xp", "spend_buff"))
            pays = bool(parsed["energy"] or parsed["power"]) or eff.effect == "convert_x"
            out.append((2 if gives_up else 1 if pays else 0, i))
        return [i for _rank, i in sorted(out)]

    def _all_adds(self, loop: GameLoop):
        """(what using every Add ability the player can use changes in its
        resources, _RESOURCES, on a copy of the game; whether that is
        conclusive: no ability that converts or pays was among them, so what
        can't be paid with that, no sequence pays). Kept while the same Add
        abilities can be used, this turn."""
        cached = getattr(self, "_adds_cache", None)
        if cached is not None and cached[0] == self._adds_now:
            return cached[1]
        gs = loop.gs.clone()
        tmp = GameLoop(gs)
        cap = gs.get_player(self.player.name)
        before = {k: (dict(v) if isinstance(v, dict) else v)
                  for k, v in ((k, getattr(cap, k)) for k in _RESOURCES)}
        conclusive = True
        for _ in range(_MAX_ADDS):
            adds = self._add_entries(tmp, cap)
            if not adds:
                break
            eff = tmp.activatable_abilities(cap.name)[adds[0]]["eff"]
            parsed = tmp._parse_activated_cost(eff.cost)
            if parsed["energy"] or parsed["power"] or eff.effect == "convert_x":
                conclusive = False
            if not tmp._use_ability_now(cap, "ACTIVATED", adds[0]):
                break
        gains = {}
        for k in _RESOURCES:
            was, now = before[k], getattr(cap, k)
            gains[k] = {d: now.get(d, 0) - was.get(d, 0) for d in set(now) | set(was)} \
                if isinstance(now, dict) else now - was
        result = (gains, conclusive)
        self._adds_cache = (self._adds_now, result)
        return result

    def _first_add(self, check) -> Optional[int]:
        """The first Add ability of the shortest sequence after which `check`
        holds (each tried on a copy of the game), or None."""
        loop = self.loop
        frontier = [(loop, self.player, None, frozenset())]
        seen, tried = set(), 0
        for _depth in range(_MAX_ADDS):
            nxt = []
            for node_loop, node_player, first, used in frontier:
                entries = node_loop.activatable_abilities(node_player.name)
                for idx in self._add_entries(node_loop, node_player):
                    done = used | {_entry_key(entries[idx])}
                    if done in seen:
                        continue
                    seen.add(done)
                    if tried >= _ADD_SEARCH:
                        return None
                    tried += 1
                    gs = node_loop.gs.clone()
                    tmp = GameLoop(gs)
                    cap = gs.get_player(self.player.name)
                    if not tmp._use_ability_now(cap, "ACTIVATED", idx):
                        continue
                    lead = idx if first is None else first
                    if check(tmp, cap):
                        return lead
                    nxt.append((tmp, cap, lead, done))
            if not nxt:
                return None
            frontier = nxt
        return None

    @abstractmethod
    def decide_action(self, opponent: Player, cards_played: int = 0) -> Action:
        """Return a chosen action. cards_played is the number of cards played this turn (for LEGION cost reduction)."""
        ...

    @abstractmethod
    def decide_mulligan(self) -> list[int]:
        """Return indices of hand cards to send back. Empty list = keep all."""
        ...

    def decide_showdown_action(self, opponent: Player, bf_idx: int) -> Action:
        """Return ACTION or REACTION spell to play during showdown, or PASS."""
        return ("PASS", None, None)

    def decide_reaction(self, opponent: Player, chain: list) -> Action:
        """Return REACTION spell to play in response to chain, or PASS."""
        return ("PASS", None, None)

    def decide_optional(self, card, effect_name: str) -> bool:
        """Whether to take an optional ("you may ...") effect. Default: yes — this
        preserves the engine's historical "optional effects always resolve"
        behavior. Agents (esp. search) may override to decline or branch."""
        return True

    def decide_predict_recycle(self, card) -> bool:
        """VISION / PREDICT 1: whether to recycle the revealed top card to the
        bottom of the deck. Default: no (keep it, the neutral null action). Search
        / learning agents may override to recycle a bad top card."""
        return False

    def decide_mode(self, card, n_modes: int):
        """Modal "choose one": which mode (0..n_modes-1) to resolve, or None for
        no preference (the engine's baseline tries each mode and takes the best).
        Search / learning agents may override to branch."""
        return None
