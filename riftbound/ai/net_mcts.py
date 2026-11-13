"""NetGuidedMCTSAgent — AlphaZero-style, network-guided MCTS (RL Chunk 3).

Where `ISMCTSAgent` explores with random/heuristic rollouts, this agent uses the
policy+value network (`net.py`) instead:
- **priors** P(a) from the network's policy steer selection (PUCT), and
- a **leaf is evaluated by the network's value** — no random playout.

Per decision it runs N simulations over the active player's turn on a determinized
clone (hidden opponent info resampled per iteration, as in ISMCTS), then plays the
**most-visited** root action. This is the search half of AlphaZero; the self-play
training loop (next chunk) will feed the visit distributions back as policy targets.

Requires the optional `rl` extra (torch), via `net.py`. The main turn is searched
over the player's actions until the turn passes; a decision in a showdown or on an
open chain gets a one-ply search (`_search_now`: each option played until the chain
and the showdown settle, both players then passing); the mulligan compares the
net's value of each keep.

**Choices inside an action** (a spell's target, a mode, the unit an Equipment
goes on, which enemy combat damage kills first, a "you may", a card looked at
on the deck...; GameLoop.choose) are searched too, every one the player makes
while the action plays out (its chain and showdown included): the tree goes on
below an action through one node per option chosen, keyed by the choice and
the option's description (_choice_key), so a determinized copy that shows
other cards (dig, predict) only adds options. A choice node's options have
equal priors, the baseline's tried first. The real game then follows the
most visited options (_Plan) until the player's next decision of that kind.

**Choices while the other player acts** (combat damage as the defender, a
spell of theirs that makes this player choose, the resolution of this player's
own spell after they passed) come after a showdown or chain decision of this
player: that one-ply search plays on until things settle, so it searches them
too, and runs even when passing is the only option if a probe sees such a
choice ahead (_choices_ahead).
"""

from __future__ import annotations

import itertools
import math
import random
from typing import TYPE_CHECKING, Optional

import numpy as np

from riftbound.ai.encoding import (
    ACTION_DIM,
    action_to_index,
    encode_observation,
    legal_mask,
)
from riftbound.ai.heuristics.base_agent import Action, Agent
from riftbound.core.decisions import DecisionPoint, Observation, describe_option
from riftbound.core.legality import legal_actions

if TYPE_CHECKING:
    from riftbound.ai.net import RiftboundNet


def predict(net, vec, mask):
    """riftbound.ai.net.predict, imported when the net first runs: torch is an
    optional extra, and the coach's text helpers (which import this module) are
    used by engine tests that run without it."""
    from riftbound.ai.net import predict as _predict
    return _predict(net, vec, mask)


_PASS: Action = ("PASS", None, None)
_MAX_TURN_ACTIONS = 30

# Choices the search leaves to the baseline (GameLoop.choose kinds, by prefix).
UNSEARCHED_CHOICES: tuple = ()


def _searchable(kind: str, side: str, me: str, n: int) -> bool:
    return side == me and n > 1 and not (UNSEARCHED_CHOICES and kind.startswith(UNSEARCHED_CHOICES))


def _label(loop, side: str, option, i: int) -> str:
    """An option's description, the same on every copy of the game (an object
    without one is named by its place among the options)."""
    text = describe_option(loop, side, option)
    return f"{type(option).__name__} #{i}" if " at 0x" in text else text


def _choice_keys(loop, kind: str, side: str, options: list, source) -> list:
    """One key per option: (kind, the card making the choice, the option's
    description). Two options with one key are the same choice."""
    src = getattr(source, "name", None) or ""
    return [(kind, src, _label(loop, side, o, i)) for i, o in enumerate(options)]


def _split_key(key) -> tuple:
    """A suggestion's key is an engine action tuple, or (action, choice key)
    for one option of the action's first choice. -> (action, choice key or None)."""
    if key and isinstance(key[0], tuple):
        return key[0], key[1]
    return key, None


def _unlink(loop, chooser) -> None:
    """Take `chooser` out of the loop's chain of choosers (each one passes what
    isn't its own to `previous`), wherever it is in it."""
    if loop.chooser is chooser:
        loop.chooser = chooser.previous
        return
    c = loop.chooser
    while c is not None:
        prev = getattr(c, "previous", None)
        if prev is chooser:
            c.previous = chooser.previous
            return
        c = prev


class _ForcedChoice:
    """One option forced in the real game (the coach's suggestion taken): fires
    at the player's first choice that offers it, then leaves the loop's chain
    of choosers; any other choice goes to the previous chooser."""

    def __init__(self, me: str, force, loop, previous):
        self.me, self.force, self.loop, self.previous = me, force, loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if _searchable(kind, side, self.me, len(options)):
            keys = _choice_keys(loop, kind, side, options, source)
            if self.force in keys:
                self.release()
                return keys.index(self.force)
        return self.previous(loop, kind, side, options, default, source) if self.previous else None

    def release(self) -> None:
        _unlink(self.loop, self)


# How long a plan lasts: a decision of the player releases its plans of that
# level and the ones below it (a turn action all of them).
_LEVEL = {DecisionPoint.TURN_ACTION: 0, DecisionPoint.SHOWDOWN_ACTION: 1, DecisionPoint.REACTION: 2}


class _Plan:
    """The search's choices for the action just played, followed in the real
    game: at each choice of the player, the most visited option the tree has
    for it (its node then goes one step down); a choice the tree hasn't seen
    goes to the previous chooser (or the baseline). Only during the turn it was
    made in."""

    def __init__(self, me: str, node: "_Node", level: int, loop, previous):
        self.me, self.node, self.level = me, node, level
        self.loop, self.previous = loop, previous
        self.turn = loop.gs.turn

    def __call__(self, loop, kind, side, options, default, source):
        if self.node is None or loop.gs.turn != self.turn or \
                not _searchable(kind, side, self.me, len(options)):
            return self.previous(loop, kind, side, options, default, source) if self.previous else None
        keys = _choice_keys(loop, kind, side, options, source)
        seen = [(c.N, -i) for i, k in enumerate(keys)
                if (c := self.node.choices.get(k)) is not None and c.N > 0]
        # The tree saw other options for this kind of choice: it depends on
        # hidden cards (dig, predict); the previous chooser (_Fallback) sees
        # the real ones.
        hidden = any(k[0] == kind and k not in keys for k in self.node.choices)
        if seen and not hidden:
            i = -max(seen)[1]
        else:
            i = self.previous(loop, kind, side, options, default, source) if self.previous else None
        got = default if i is None else i
        self.node = self.node.choices.get(keys[got], self.node)
        return i

    def release(self) -> None:
        _unlink(self.loop, self)


class _Stop(BaseException):
    """A replayed segment reached a decision the journal doesn't have yet."""


class _Diverged(BaseException):
    """A replayed segment left the journal's path."""


class _Cursor:
    """Replays a loop's journal on a copy of its segment: the decisions (for
    _ReplayAgent) and the choices, in order; then the choice being weighed
    gets `force` (its randomness from here on is new, `seed`), any later one
    the baseline, and the next decision stops the replay (_Stop)."""

    def __init__(self, journal: list, target: tuple, force: int, seed: int, gs):
        self.journal, self.target, self.force, self.seed, self.gs = journal, target, force, seed, gs
        self.k = 0
        self.done = False

    def decision(self, side: str, point: str):
        if self.k >= len(self.journal):
            raise _Stop()
        e = self.journal[self.k]
        if e[0] != "decision" or e[1] != side or e[2] != point:
            raise _Diverged()
        self.k += 1
        return e[3]

    def __call__(self, loop, kind, side, options, default, source):
        if self.k < len(self.journal):
            e = self.journal[self.k]
            if e[0] != "choice" or e[1:4] != (side, kind, len(options)):
                raise _Diverged()
            self.k += 1
            return e[4]
        if self.done:
            return None
        if (side, kind, len(options)) != self.target:
            raise _Diverged()
        self.done = True
        self.k += 1
        self.gs.rng = random.Random(self.seed)
        return self.force


class _ReplayAgent:
    """A player's agent on a replayed segment: decides as the journal says."""

    def __init__(self, player, cursor: _Cursor):
        self.player, self.cursor = player, cursor

    def decide_action(self, opponent, cards_played: int = 0):
        return self.cursor.decision(self.player.name, DecisionPoint.TURN_ACTION.value)

    def decide_reaction(self, opponent, chain):
        return self.cursor.decision(self.player.name, DecisionPoint.REACTION.value)

    def decide_showdown_action(self, opponent, bf_idx: int):
        return self.cursor.decision(self.player.name, DecisionPoint.SHOWDOWN_ACTION.value)

    def decide_mulligan(self) -> list:
        return []

    def decide_optional(self, card, effect_name: str) -> bool:
        return True

    def decide_predict_recycle(self, card) -> bool:
        return False

    def decide_mode(self, card, n_modes: int):
        return None


class _Fallback:
    """At the bottom of the real loop's choosers: a choice of the agent's
    player no plan answers (one the search didn't meet, or one on hidden
    cards: the ones looked at are real now) is weighed by replaying the loop's
    segment once per option (NetGuidedMCTSAgent.replay_values)."""

    def __init__(self, agent: "NetGuidedMCTSAgent", previous):
        self.agent, self.previous = agent, previous
        self.me = agent.player.name

    def __call__(self, loop, kind, side, options, default, source):
        if _searchable(kind, side, self.me, len(options)):
            values = self.agent.replay_values(kind, side, options, source)
            if values:
                best = max(range(len(values)), key=lambda i: (values[i], i == default))
                if values[best] > values[default] + 1e-6:
                    return best
            return None
        return self.previous(loop, kind, side, options, default, source) if self.previous else None


class _TreeChooser:
    """Chooser for one action applied in the search: at each choice of `me`,
    PUCT over the node's options (created as the choice is met, with equal
    priors), one step down the tree; `path` collects the nodes."""

    def __init__(self, agent: "NetGuidedMCTSAgent", me: str, node: "_Node", path: list):
        self.agent, self.me, self.node, self.path = agent, me, node, path
        self.met = False

    def __call__(self, loop, kind, side, options, default, source):
        if not _searchable(kind, side, self.me, len(options)):
            return None
        self.met = True
        keys = _choice_keys(loop, kind, side, options, source)
        node, n = self.node, len(options)
        for i, k in enumerate(keys):
            if k not in node.choices:
                node.choices[k] = _Node()
                node.cprior[k] = 1.0 / n
        i = self.agent._select_option(node, keys, default)
        self.node = node.choices[keys[i]]
        self.path.append(self.node)
        return i


class _Node:
    __slots__ = ("N", "W", "P", "children", "expanded", "value", "choices", "cprior")

    def __init__(self):
        self.N = 0
        self.W = 0.0
        self.P: dict = {}          # action_tuple -> prior
        self.children: dict = {}   # action_tuple -> _Node
        self.expanded = False
        self.value = 0.0
        # The choices met right after this node, as an action plays out:
        # choice key (_choice_keys) -> _Node, and its prior.
        self.choices: dict = {}
        self.cprior: dict = {}


class NetGuidedMCTSAgent(Agent):
    name = "net_mcts"

    def __init__(self, player, net: RiftboundNet, iterations: int = 100,
                 c_puct: float = 1.5, rng: Optional[random.Random] = None,
                 mulligan_samples: int = 3, reaction_iterations: Optional[int] = None,
                 explore: bool = False, dirichlet_alpha: float = 0.3,
                 noise_frac: float = 0.25, temperature_moves: int = 10,
                 pass_margin: float = 0.02, fast_iterations: Optional[int] = None,
                 full_fraction: float = 1.0):
        super().__init__(player)
        # A move whose searched value isn't at least this much above passing's
        # (values in [-1, 1]: 0.02 = 1 point of win chance) isn't played.
        self.pass_margin = pass_margin
        self.net = net
        self.iterations = iterations
        # Showdown / reaction decisions search one ply: a quarter of the budget.
        self.reaction_iterations = reaction_iterations or max(8, iterations // 4)
        self.c_puct = c_puct
        self.mulligan_samples = mulligan_samples
        self._rng = rng
        # Self-play exploration (AlphaZero): Dirichlet noise on the root priors,
        # and for the first `temperature_moves` searched decisions an action
        # drawn in proportion to its visits instead of the most visited.
        self.explore = explore
        self.dirichlet_alpha = dirichlet_alpha
        self.noise_frac = noise_frac
        self.temperature_moves = temperature_moves
        self._decisions = 0
        # Self-play with two budgets (KataGo's playout cap randomization): a
        # decision is searched in full (noise, recorded for training) with
        # probability `full_fraction`, otherwise with `fast_iterations`, no
        # noise, not recorded. More games for the same time, and fewer examples
        # of one game sharing its outcome (the value memorized games: 16 games
        # an iteration, 90 examples each, made it sure of itself and wrong).
        self.fast_iterations = fast_iterations
        self.full_fraction = full_fraction
        self._full = True
        # Turns where this player had something else to do and passed at once.
        self.turns = 0
        self.empty_turns = 0
        self._turn_seen = None
        # Last root visit distribution (action_tuple -> visit share), for the
        # self-play trainer's policy target and for debugging.
        self.last_visits: dict = {}
        # When set to a list, decide_action appends a training example per searched
        # decision: {"state","policy","mask","player"} (value target z filled later
        # by the self-play driver from the game outcome).
        self.record: Optional[list] = None

    def _ensure_rng(self) -> None:
        if self._rng is None:
            base = getattr(self, "gs", None)
            seed = base.rng.randrange(1 << 30) if base is not None else random.randrange(1 << 30)
            self._rng = random.Random(seed)

    # -- network evaluation of a determinized state --------------------------

    def _evaluate(self, clone, side: str, legal_ga: list) -> tuple[dict, float]:
        """Run the net on ``clone`` from ``side``'s view. Returns (priors over the
        legal engine-tuples, value in [-1,1]). Uniform priors if the net puts no
        mass on any legal slot."""
        obs = Observation.from_state(clone, side)
        vec = encode_observation(obs)
        n_bf = len(clone.battlefields)
        mask = legal_mask(legal_ga, n_bf)
        probs, value = predict(self.net, vec, mask)
        priors: dict = {}
        total = 0.0
        for a in legal_ga:
            t = a.to_engine()
            idx = action_to_index(a, n_bf)
            p = float(probs[idx]) if idx is not None else 0.0
            priors[t] = p
            total += p
        if total > 1e-8:
            for t in priors:
                priors[t] /= total
        else:
            u = 1.0 / max(1, len(priors))
            priors = {t: u for t in priors}
        return priors, value

    def _net_value(self, clone, side: str) -> float:
        # The value doesn't depend on the legal mask: no legal-action list (it
        # was a third of a search's time).
        return self._value_only(clone, side)

    def _value_only(self, clone, side: str) -> float:
        """Net value of a state, mask-independent — used for pre-turn (mulligan)
        choices where turn-action legality isn't meaningful yet."""
        vec = encode_observation(Observation.from_state(clone, side))
        _probs, value = predict(self.net, vec, np.ones(ACTION_DIM, dtype=bool))
        return value

    @staticmethod
    def _loop_for(clone):
        from riftbound.core.loop import GameLoop
        return GameLoop(clone)

    # -- search --------------------------------------------------------------

    def _ensure_fallback(self) -> None:
        """The real loop records its journal, and this player's choices no plan
        answers go to a _Fallback (once per loop)."""
        loop = getattr(self, "loop", None)
        if loop is None or getattr(self, "_fallback_loop", None) is loop:
            return
        self._fallback_loop = loop
        if loop.journal is None:
            loop.journal = []
        loop.chooser = _Fallback(self, loop.chooser)

    def replay_values(self, kind: str, side: str, options: list, source) -> Optional[list]:
        """The value, for this player, of each option of the choice the real
        loop is asking now: its segment replayed on a copy with that option,
        up to the next decision. None when it can't be replayed (no segment
        yet, or the copy took another path)."""
        from riftbound.core.loop import GameLoop
        loop = self.loop
        if loop.segment is None or loop.journal is None:
            return None
        self._ensure_rng()
        journal = list(loop.journal)
        snap = loop.segment[0]
        keys = _choice_keys(loop, kind, side, options, source)
        seed = self._rng.randrange(1 << 30)
        values: list = []
        for j, key in enumerate(keys):
            if key in keys[:j]:
                values.append(values[keys.index(key)])
                continue
            clone = snap.clone()
            cursor = _Cursor(journal, (side, kind, len(options)), j, seed, clone)
            clone.A.agent = _ReplayAgent(clone.A, cursor)
            clone.B.agent = _ReplayAgent(clone.B, cursor)
            rl = GameLoop(clone)
            rl.chooser, rl.segment = cursor, loop.segment
            try:
                rl.replay_segment()
            except _Stop:
                pass
            except (_Diverged, Exception):  # noqa: BLE001 — a replay never stops the game
                return None
            if not cursor.done:
                return None
            clone.A.agent = clone.B.agent = None
            v = self._terminal_value(clone, self.player.name)
            values.append(self._net_value(clone, self.player.name) if v is None else v)
        return values

    def _release_forced(self, level: int = 0) -> None:
        """The plans (and forced choices) of this player's earlier decisions
        don't outlive the next one of their level: a turn action releases
        all of them, a showdown decision the showdown and chain ones, a chain
        decision the chain ones (the one-ply search plans what comes next)."""
        loop = getattr(self, "loop", None)
        c = getattr(loop, "chooser", None)
        while c is not None:
            prev = getattr(c, "previous", None)
            if getattr(c, "me", None) == self.player.name and (
                    isinstance(c, _ForcedChoice) and level == 0
                    or isinstance(c, _Plan) and (c.level >= level or c.turn != loop.gs.turn)):
                c.release()
            c = prev

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._ensure_rng()
        self._ensure_fallback()
        self._release_forced()
        side = self.player.name
        root_legal = legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)
        if len(root_legal) <= 1:
            return root_legal[0].to_engine() if root_legal else _PASS
        root = self.search(DecisionPoint.TURN_ACTION, root_legal, cards_played=cards_played)
        action = self._conclude(root, side, root_legal)
        if self._turn_seen != self.gs.turn:
            self._turn_seen = self.gs.turn
            self.turns += 1
            if action == _PASS and self.gs.pending_move is None:
                self.empty_turns += 1
        return action

    def search(self, point: DecisionPoint, legal: list, *, cards_played: int = 0,
               bf_idx: Optional[int] = None) -> _Node:
        """Search a decision with these legal actions (the main turn, or one ply
        in a showdown / on a chain); the root's children (actions and their
        choice variants) carry the visits N and total values W."""
        self._ensure_rng()
        side = self.player.name
        root = _Node()
        self._full = not (self.explore and self.fast_iterations
                          and self._rng.random() >= self.full_fraction)
        if point == DecisionPoint.TURN_ACTION:
            for _ in range(self.iterations if self._full else self.fast_iterations):
                self._iterate(root, side, cards_played)
        else:
            n = self.reaction_iterations if self._full else max(4, self.fast_iterations // 4)
            for _ in range(n):
                self._iterate_now(root, side, point, legal, bf_idx)
        return root

    def _conclude(self, root: _Node, side: str, legal: list,
                  point: DecisionPoint = DecisionPoint.TURN_ACTION) -> Action:
        """Record the visit distribution (and the training example) and play."""
        if not root.children or not any(c.N for c in root.children.values()):
            return _PASS
        total = sum(c.N for c in root.children.values()) or 1
        self.last_visits = {a: c.N / total for a, c in root.children.items()}
        if self.record is not None and len(legal) > 1 and self._full:
            self._record_example(side, legal)
        return self._play(root, side, point)

    def _play(self, root: _Node, side: str, point: DecisionPoint = DecisionPoint.TURN_ACTION) -> Action:
        """The root child to play: the most visited (AlphaZero's move choice), or
        early in an exploring game one drawn in proportion to its visits; the
        real game then follows its searched choices (_Plan)."""
        items = [(k, c) for k, c in root.children.items() if c.N > 0] or list(root.children.items())
        if len(items) > 1:
            self._decisions += 1
        if self.explore and len(items) > 1 and self._decisions <= self.temperature_moves:
            key = self._rng.choices([k for k, _ in items], weights=[max(c.N, 1e-9) for _, c in items])[0]
        else:
            key = self.prefer_pass(root, max(items, key=lambda kv: kv[1].N)[0])
        child = root.children[key]
        if child.choices:
            self.loop.chooser = _Plan(side, child, _LEVEL[point], self.loop, self.loop.chooser)
        return key

    def variants(self, root: _Node) -> list:
        """The root's moves as suggestions: (key, visits, total value) for each
        action, or for each option of its first choice the search tried
        (key = (action, choice key)), most visited first."""
        out = []
        for action, child in root.children.items():
            tried = [(k, c) for k, c in child.choices.items() if c.N > 0]
            if not tried:
                out.append((action, child.N, child.W))
            out += [((action, k), c.N, c.W) for k, c in tried]
        return sorted(out, key=lambda v: -v[1])

    def prefer_pass(self, root: _Node, key):
        """PASS instead of `key` when `key` isn't clearly better: a free-looking
        move can spend what the opponent's turn needs (Shen's legend tapped for a
        TANK nobody fights with, energy a reaction would want). Not while a move
        is held: PASS then starts its showdown (it isn't "do nothing"). Only
        abilities: a unit, spell or move the search prefers is played (the margin
        made the net skip its 2-drop on turn 2, a noisy Q nudging it to PASS)."""
        p = root.children.get(_PASS)
        best = root.children.get(_split_key(key)[0])
        if key == _PASS or p is None or best is None or not p.N or not best.N \
                or _split_key(key)[0][0] != "ABILITY" \
                or getattr(self.gs, "pending_move", None) is not None:
            return key
        return _PASS if best.W / best.N - p.W / p.N < self.pass_margin else key

    def _add_noise(self, node: _Node) -> None:
        """Dirichlet noise on a root's priors, so self-play also tries what the
        net doesn't (yet) favour."""
        if not self.explore or not self._full or len(node.P) < 2:
            return
        noise = [self._rng.gammavariate(self.dirichlet_alpha, 1.0) for _ in node.P]
        total = sum(noise) or 1.0
        f = self.noise_frac
        for key, n in zip(list(node.P), noise):
            node.P[key] = (1 - f) * node.P[key] + f * n / total

    def _record_example(self, side: str, root_legal: list) -> None:
        """Append (state, MCTS visit policy, legal mask, player) for training."""
        obs = Observation.from_state(self.gs, side)
        n_bf = len(self.gs.battlefields)
        policy = np.zeros(ACTION_DIM, dtype=np.float32)
        for a_tuple, share in self.last_visits.items():
            idx = action_to_index(a_tuple, n_bf)
            if idx is not None:
                policy[idx] += share
        s = policy.sum()
        if s > 1e-8:
            policy /= s
        self.record.append({
            "state": encode_observation(obs),
            "policy": policy,
            "mask": legal_mask(root_legal, n_bf),
            "player": side,
        })

    def _iterate(self, root: _Node, side: str, cards_played: int) -> None:
        from riftbound.core.loop import GameLoop
        from riftbound.core.state import determinize
        clone = self.gs.clone()
        clone.rng = random.Random(self._rng.randrange(1 << 30))
        determinize(clone, observer=side, rng=clone.rng)
        loop = GameLoop(clone)

        node = root
        path = [root]
        cpt = cards_played
        value = 0.0
        vs = clone.victory_score

        for _ in range(_MAX_TURN_ACTIONS):
            # Decided game → exact terminal value from `side`'s perspective.
            if clone.points_A >= vs or clone.points_B >= vs:
                pa, pb = clone.points_A, clone.points_B
                win = (pa > pb) if side == "A" else (pb > pa)
                value = 1.0 if win else (-1.0 if pa != pb else 0.0)
                break
            if clone.active != side:
                value = self._net_value(clone, side)   # opponent to move → net estimate
                break

            legal_ga = legal_actions(loop, DecisionPoint.TURN_ACTION, side)
            if not legal_ga:
                value = self._net_value(clone, side)
                break

            if not node.expanded:
                priors, v = self._evaluate(clone, side, legal_ga)
                node.P = priors
                node.children = {t: _Node() for t in priors}
                node.expanded = True
                node.value = v
                if node is root:
                    self._add_noise(node)
                value = v
                break

            key = self._puct_select(node, [a.to_engine() for a in legal_ga])
            if key is None:
                value = self._net_value(clone, side)
                break
            node = node.children[key]
            path.append(node)
            if key == _PASS and clone.pending_move is None:
                # Stop-here: evaluate the position where we choose to end acting.
                # (PASS during a move ends the move: its showdown, then more turn.)
                value = self._net_value(clone, side)
                break
            tree = _TreeChooser(self, side, node, path)
            loop.chooser = tree
            loop._apply_action(clone.get_player(side), key, cards_played_this_turn=cpt)
            loop.chooser = None
            loop._recompute_passives()
            cpt += 1
            node = tree.node          # below the options chosen
        else:
            value = self._net_value(clone, side)

        for n in path:
            n.N += 1
            n.W += value

    def _select_option(self, node: _Node, keys: list, default: int = 0) -> int:
        """PUCT over a choice's options (by key; the first of two with one key):
        an option not tried yet is worth the node's own mean so far; on a tie
        the baseline's option goes first."""
        sqrt_total = math.sqrt(max(1, node.N))
        fpu = node.W / node.N if node.N else 0.0
        best, best_val, seen = default, -1e30, set()
        order = [default] + [i for i in range(len(keys)) if i != default]
        for i in order:
            k = keys[i]
            if k in seen:
                continue
            seen.add(k)
            child = node.choices[k]
            q = child.W / child.N if child.N else fpu
            val = q + self.c_puct * node.cprior.get(k, 0.0) * sqrt_total / (1 + child.N)
            if val > best_val:
                best, best_val = i, val
        return best

    def _puct_select(self, node: _Node, legal: list):
        """PUCT over children that are currently legal:
        argmax  Q(a) + c_puct * P(a) * sqrt(sum_b N_b) / (1 + N_a)."""
        legal_set = set(legal)
        candidates = [(a, c) for a, c in node.children.items() if a in legal_set]
        if not candidates:
            return None
        sqrt_total = math.sqrt(max(1, node.N))
        best, best_val = None, -1e30
        for a, child in candidates:
            q = (child.W / child.N) if child.N > 0 else 0.0
            u = self.c_puct * node.P.get(a, 0.0) * sqrt_total / (1 + child.N)
            val = q + u
            if val > best_val:
                best_val, best = val, a
        return best

    # -- other decision points (simple in v1; documented deferral) -----------

    def decide_mulligan(self) -> list:
        """Learned mulligan: for every keep/return combination (§117: up to two
        cards), apply it on a determinized clone and score the resulting opening by
        the net's VALUE; keep the best. No hand-crafted rule — as the value net
        learns that a dead card in hand loses, it learns to mulligan it (e.g.
        Nocturne). Averaged over a few determinized draws to cut variance."""
        best_combo, best_v = [], -1e30
        for combo, v in self.mulligan_values():
            if v > best_v:
                best_v, best_combo = v, combo
        return best_combo

    def mulligan_values(self) -> list:
        """(hand indices to send back, the net's value of the opening after it)
        for every mulligan (§117: up to two cards), keep-all first."""
        self._ensure_rng()
        self._release_forced()
        side = self.player.name
        n = len(self.player.hand)
        if n == 0:
            return []
        from riftbound.core.state import determinize
        out = []
        for combo in (list(c) for r in range(3) for c in itertools.combinations(range(n), r)):
            vals = []
            for _ in range(max(1, self.mulligan_samples)):
                clone = self.gs.clone()
                clone.rng = random.Random(self._rng.randrange(1 << 30))
                clone.get_player(side).mulligan(combo, clone.rng)
                determinize(clone, observer=side, rng=clone.rng)
                vals.append(self._value_only(clone, side))
            out.append((combo, sum(vals) / len(vals)))
        return out

    # -- showdown / reaction decisions -----------------------------------------

    def decide_showdown_action(self, opponent, bf_idx: int) -> Action:
        return self._search_now(DecisionPoint.SHOWDOWN_ACTION, bf_idx)

    def decide_reaction(self, opponent, chain) -> Action:
        return self._search_now(DecisionPoint.REACTION, None)

    def _search_now(self, point: DecisionPoint, bf_idx: Optional[int]) -> Action:
        """A decision in a showdown (with focus) or on an open chain: one-ply
        PUCT over the legal actions and the choices each meets. Each is played
        on a determinized copy until things settle (the chain resolved, then
        the showdown over with its combat, both players passing) and the net's
        value of that position counts. When passing is the only option, only
        if this player has a choice to make before things settle."""
        self._ensure_rng()
        self._ensure_fallback()
        self._release_forced(_LEVEL[point])
        side = self.player.name
        legal = legal_actions(self.loop, point, side)
        if len(legal) <= 1 and not (legal and self._choices_ahead(legal[0].to_engine(), point, bf_idx)):
            return legal[0].to_engine() if legal else _PASS
        root = self.search(point, legal, bf_idx=bf_idx)
        return self._conclude(root, side, legal, point)

    def _choices_ahead(self, action, point: DecisionPoint, bf_idx: Optional[int]) -> bool:
        """Whether this player makes a choice (more than one option) on a
        determinized copy where `action` is taken and things settle."""
        from riftbound.core.state import determinize
        clone = self.gs.clone()
        clone.rng = random.Random(self._rng.randrange(1 << 30))
        determinize(clone, observer=self.player.name, rng=clone.rng)
        loop = self._loop_for(clone)
        met = []

        def probe(_loop, kind, side, options, default, source):
            if _searchable(kind, side, self.player.name, len(options)):
                met.append(kind)
            return None
        loop.chooser = probe
        try:
            self._step(loop, point, action, bf_idx)
            self._settle(loop)
        except Exception:  # noqa: BLE001 — a probe never stops the game
            return False
        return bool(met)

    def _step(self, loop, point: DecisionPoint, action, bf_idx: Optional[int]) -> None:
        """Take `action` at a showdown or chain decision on `loop` (a copy)."""
        if action == _PASS:
            return
        player = loop.gs.get_player(self.player.name)
        if point == DecisionPoint.SHOWDOWN_ACTION:
            loop._showdown_step(player, self.player.name, action, bf_idx)
        else:
            loop._reaction_step(player, self.player.name, action)

    def _iterate_now(self, root: _Node, side: str, point: DecisionPoint, legal: list,
                     bf_idx: Optional[int]) -> None:
        from riftbound.core.loop import GameLoop
        from riftbound.core.state import determinize
        clone = self.gs.clone()
        clone.rng = random.Random(self._rng.randrange(1 << 30))
        determinize(clone, observer=side, rng=clone.rng)
        loop = GameLoop(clone)
        if not root.expanded:
            priors, value = self._evaluate(clone, side, legal)
            root.P = priors
            root.children = {t: _Node() for t in priors}
            root.expanded = True
            self._add_noise(root)
            root.N += 1
            root.W += value
            return
        key = self._puct_select(root, [a.to_engine() for a in legal])
        if key is None:
            return
        child = root.children[key]
        path = [root, child]
        loop.chooser = _TreeChooser(self, side, child, path)
        self._step(loop, point, key, bf_idx)
        self._settle(loop)
        loop.chooser = None
        value = self._terminal_value(clone, side)
        if value is None:
            value = self._net_value(clone, side)
        for n in path:
            n.N += 1
            n.W += value

    @staticmethod
    def _settle(loop) -> None:
        """Resolve the chain, then end the showdown (combat included), as if
        both players passed from here."""
        gs = loop.gs
        if gs.chain:
            loop._resolve_chain_passing()
        if gs.showdown_active and gs.showdown_bf_idx is not None:
            loop._finish_showdown(gs.showdown_bf_idx, gs.showdown_attacker)

    @staticmethod
    def _terminal_value(clone, side: str) -> Optional[float]:
        vs = clone.victory_score
        if clone.points_A >= vs or clone.points_B >= vs:
            pa, pb = clone.points_A, clone.points_B
            win = (pa > pb) if side == "A" else (pb > pa)
            return 1.0 if win else (-1.0 if pa != pb else 0.0)
        return None
