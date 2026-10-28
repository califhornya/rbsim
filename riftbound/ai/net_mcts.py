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
goes on, which enemy combat damage kills first, a "you may"...; GameLoop.choose)
are searched too: the first time a child action is tried, the player's first
choice of a SEARCH_CHOICES kind it meets splits that child into one child per
option (the action's prior shared out), each later tried with that option
forced. The value of the position each leads to decides, as for actions; the
chosen variant's option is then forced in the real game (_ForcedChoice). The
policy target counts all variants of an action as that action.
"""

from __future__ import annotations

import itertools
import math
import random
from typing import Optional

import numpy as np

from riftbound.ai.encoding import (
    ACTION_DIM,
    action_to_index,
    encode_observation,
    legal_mask,
)
from riftbound.ai.heuristics.base_agent import Action, Agent
from riftbound.ai.net import RiftboundNet, predict
from riftbound.core.decisions import DecisionPoint, Observation, describe_option
from riftbound.core.legality import legal_actions

_PASS: Action = ("PASS", None, None)
_MAX_TURN_ACTIONS = 30

# The GameLoop.choose kinds the search branches on (by prefix): ones the player
# sees, so a determinized copy offers the same options in the same order.
# Hidden ones (dig and predict look at the deck) and the Power domain (six
# options, rarely mattering) keep their baseline.
SEARCH_CHOICES = ("target:", "mode", "equip", "combat_damage_order", "cost_unit:",
                  "destination", "optional:", "deploy", "discard", "player", "token_location",
                  "battlefield:", "tag:")
_MAX_VARIANTS = 6


def _searchable(kind: str, side: str, me: str, n: int) -> bool:
    return side == me and n > 1 and kind.startswith(SEARCH_CHOICES)


def _split_key(key) -> tuple:
    """A child key is an engine action tuple, or (action, (kind, n, option)) for
    one variant of an action's choice. -> (action, force or None)."""
    if key and isinstance(key[0], tuple):
        return key[0], key[1]
    return key, None


class _ChoiceProbe:
    """Chooser for one action applied in the search: records the first choice
    `me` makes of a searched kind, as (kind, n options, baseline index), and
    with `force` = (kind, n, j) takes option j there if it is that choice."""

    def __init__(self, me: str, force=None):
        self.me, self.force, self.first = me, force, None
        self.labels: Optional[list] = None      # the first choice's options, described

    def __call__(self, loop, kind, side, options, default, source):
        if self.first is not None or not _searchable(kind, side, self.me, len(options)):
            return None
        self.first = (kind, len(options), default)
        self.labels = [describe_option(loop, side, o) for o in options]
        if self.force is not None and tuple(self.force[:2]) == (kind, len(options)):
            return self.force[2]
        return None


class _ForcedChoice(_ChoiceProbe):
    """The searched option, forced in the real game for the action just
    returned: fires at the player's first choice of that kind and number of
    options, then puts the loop's previous chooser back; any other choice goes
    to that chooser."""

    def __init__(self, me: str, force, loop, previous):
        super().__init__(me, force)
        self.loop, self.previous = loop, previous

    def __call__(self, loop, kind, side, options, default, source):
        if _searchable(kind, side, self.me, len(options)) and \
                tuple(self.force[:2]) == (kind, len(options)):
            self.release()
            return self.force[2]
        return self.previous(loop, kind, side, options, default, source) if self.previous else None

    def release(self) -> None:
        if self.loop.chooser is self:
            self.loop.chooser = self.previous


class _Node:
    __slots__ = ("N", "W", "P", "children", "expanded", "value", "labels")

    def __init__(self):
        self.N = 0
        self.W = 0.0
        self.P: dict = {}          # action_tuple -> prior
        self.children: dict = {}   # action_tuple -> _Node
        self.expanded = False
        self.value = 0.0
        self.labels: dict = {}     # variant key -> its option, described


class NetGuidedMCTSAgent(Agent):
    name = "net_mcts"

    def __init__(self, player, net: RiftboundNet, iterations: int = 100,
                 c_puct: float = 1.5, rng: Optional[random.Random] = None,
                 mulligan_samples: int = 3, reaction_iterations: Optional[int] = None,
                 explore: bool = False, dirichlet_alpha: float = 0.3,
                 noise_frac: float = 0.25, temperature_moves: int = 10,
                 pass_margin: float = 0.02):
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
        mask = legal_mask(legal_ga)
        probs, value = predict(self.net, vec, mask)
        priors: dict = {}
        total = 0.0
        for a in legal_ga:
            t = a.to_engine()
            idx = action_to_index(a)
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

    def _release_forced(self) -> None:
        """A forced choice the last action never reached doesn't outlive it."""
        chooser = getattr(getattr(self, "loop", None), "chooser", None)
        if isinstance(chooser, _ForcedChoice) and chooser.me == self.player.name:
            chooser.release()

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._ensure_rng()
        self._release_forced()
        side = self.player.name
        root_legal = legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)
        if len(root_legal) <= 1:
            return root_legal[0].to_engine() if root_legal else _PASS
        root = self.search(DecisionPoint.TURN_ACTION, root_legal, cards_played=cards_played)
        return self._conclude(root, side, root_legal)

    def search(self, point: DecisionPoint, legal: list, *, cards_played: int = 0,
               bf_idx: Optional[int] = None) -> _Node:
        """Search a decision with these legal actions (the main turn, or one ply
        in a showdown / on a chain); the root's children (actions and their
        choice variants) carry the visits N and total values W."""
        self._ensure_rng()
        side = self.player.name
        root = _Node()
        if point == DecisionPoint.TURN_ACTION:
            for _ in range(self.iterations):
                self._iterate(root, side, cards_played)
        else:
            for _ in range(self.reaction_iterations):
                self._iterate_now(root, side, point, legal, bf_idx)
        return root

    def _conclude(self, root: _Node, side: str, legal: list) -> Action:
        """Record the visit distribution (and the training example) and play."""
        if not root.children or not any(c.N for c in root.children.values()):
            return _PASS
        total = sum(c.N for c in root.children.values()) or 1
        self.last_visits = {a: c.N / total for a, c in root.children.items()}
        if self.record is not None:
            self._record_example(side, legal)
        return self._play(root, side)

    def _play(self, root: _Node, side: str) -> Action:
        """The root child to play: the most visited (AlphaZero's move choice), or
        early in an exploring game one drawn in proportion to its visits; its
        searched option is forced in the real game."""
        self._decisions += 1
        items = [(k, c) for k, c in root.children.items() if c.N > 0] or list(root.children.items())
        if self.explore and self._decisions <= self.temperature_moves:
            key = self._rng.choices([k for k, _ in items], weights=[max(c.N, 1e-9) for _, c in items])[0]
        else:
            key = self.prefer_pass(root, max(items, key=lambda kv: kv[1].N)[0])
        action, force = _split_key(key)
        if force is not None:
            self.loop.chooser = _ForcedChoice(side, force, self.loop, self.loop.chooser)
        return action

    def prefer_pass(self, root: _Node, key):
        """PASS instead of `key` when `key` isn't clearly better: a free-looking
        move can spend what the opponent's turn needs (Shen's legend tapped for a
        TANK nobody fights with, energy a reaction would want). Not while a move
        is held: PASS then starts its showdown (it isn't "do nothing"). Only
        abilities: a unit, spell or move the search prefers is played (the margin
        made the net skip its 2-drop on turn 2, a noisy Q nudging it to PASS)."""
        p = root.children.get(_PASS)
        best = root.children.get(key)
        if key == _PASS or p is None or best is None or not p.N or not best.N \
                or _split_key(key)[0][0] != "ABILITY" \
                or getattr(self.gs, "pending_move", None) is not None:
            return key
        return _PASS if best.W / best.N - p.W / p.N < self.pass_margin else key

    def _add_noise(self, node: _Node) -> None:
        """Dirichlet noise on a root's priors, so self-play also tries what the
        net doesn't (yet) favour."""
        if not self.explore or len(node.P) < 2:
            return
        noise = [self._rng.gammavariate(self.dirichlet_alpha, 1.0) for _ in node.P]
        total = sum(noise) or 1.0
        f = self.noise_frac
        for key, n in zip(list(node.P), noise):
            node.P[key] = (1 - f) * node.P[key] + f * n / total

    def _record_example(self, side: str, root_legal: list) -> None:
        """Append (state, MCTS visit policy, legal mask, player) for training."""
        obs = Observation.from_state(self.gs, side)
        policy = np.zeros(ACTION_DIM, dtype=np.float32)
        for key, share in self.last_visits.items():
            a_tuple, _force = _split_key(key)
            idx = action_to_index(a_tuple)
            if idx is not None:
                policy[idx] += share
        s = policy.sum()
        if s > 1e-8:
            policy /= s
        self.record.append({
            "state": encode_observation(obs),
            "policy": policy,
            "mask": legal_mask(root_legal),
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
            if key == _PASS and clone.pending_move is None:
                # Stop-here: evaluate the position where we choose to end acting.
                # (PASS during a move ends the move: its showdown, then more turn.)
                path.append(node.children[key])
                value = self._net_value(clone, side)
                break
            action, force = _split_key(key)
            probe = _ChoiceProbe(side, force)
            loop.chooser = probe
            loop._apply_action(clone.get_player(side), action, cards_played_this_turn=cpt)
            loop.chooser = None
            loop._recompute_passives()
            cpt += 1
            if force is None and probe.first is not None:
                key = self._split_child(node, action, probe.first, probe.labels)
            node = node.children[key]
            path.append(node)
        else:
            value = self._net_value(clone, side)

        for n in path:
            n.N += 1
            n.W += value

    @staticmethod
    def _split_child(node: _Node, action, first, labels: Optional[list] = None) -> tuple:
        """The action met a choice: one child per option (at most _MAX_VARIANTS:
        the baseline's and the first others), sharing the action's prior; the
        baseline's keeps the existing child. Returns that child's key."""
        kind, n, default = first
        options = [default] + [j for j in range(n) if j != default][:_MAX_VARIANTS - 1]
        child, prior = node.children.pop(action), node.P.pop(action, 0.0)
        for j in options:
            key = (action, (kind, n, j))
            node.children[key] = child if j == default else _Node()
            node.P[key] = prior / len(options)
            if labels and j < len(labels):
                node.labels[key] = labels[j]
        return (action, (kind, n, default))

    def _puct_select(self, node: _Node, legal: list):
        """PUCT over children that are currently legal (a choice variant when its
        action is):  argmax  Q(a) + c_puct * P(a) * sqrt(sum_b N_b) / (1 + N_a)."""
        legal_set = set(legal)
        candidates = [(a, c) for a, c in node.children.items() if _split_key(a)[0] in legal_set]
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
        PUCT over the legal actions and their choice variants. Each is played on
        a determinized copy until things settle (the chain resolved, then the
        showdown over with its combat, both players passing) and the net's
        value of that position counts. Free when passing is the only option."""
        self._ensure_rng()
        side = self.player.name
        legal = legal_actions(self.loop, point, side)
        if len(legal) <= 1:
            return legal[0].to_engine() if legal else _PASS
        root = self.search(point, legal, bf_idx=bf_idx)
        return self._conclude(root, side, legal)

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
        action, force = _split_key(key)
        probe = _ChoiceProbe(side, force)
        loop.chooser = probe
        if action != _PASS:
            player = clone.get_player(side)
            if point == DecisionPoint.SHOWDOWN_ACTION:
                loop._showdown_step(player, side, action, bf_idx)
            else:
                loop._reaction_step(player, side, action)
        loop.chooser = None
        self._settle(loop)
        value = self._terminal_value(clone, side)
        if value is None:
            value = self._net_value(clone, side)
        if force is None and probe.first is not None:
            key = self._split_child(root, action, probe.first, probe.labels)
        child = root.children[key]
        for n in (root, child):
            n.N += 1
            n.W += value

    @staticmethod
    def _settle(loop) -> None:
        """Resolve the chain, then end the showdown (combat included), as if
        both players passed from here."""
        gs = loop.gs
        if gs.chain:
            loop._resolve_chain()
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
