"""Does the variant play this position better than the reference?

A position saved by `opponent_turn.py --shadow` (the variant and the reference
chose different moves) is played on in K worlds the mover can't tell apart
(the opponent's hand and both decks redealt from its view, `determinize`),
the same K worlds for both arms. Arm "reply": the mover plays the rest of this
turn as the variant; arm "ref": as the reference; at the same time per move
(ITERS for the reference, ITERS * RATIO for the variant, RATIO the variants'
iterations per decision over the reference's in the match). From the next
turn on both players are the reference (ITERS, fixed: a world then plays the
same way in both arms unless this turn differed).

  python scripts/diag/opponent_turn_check.py FILE.pkl [K] [ITERS] [RATIO]
  (WORLD0=N: worlds N..N+K-1 instead of 0..K-1)
  python scripts/diag/opponent_turn_check.py --show FILE.pkl
"""
from __future__ import annotations

import os
import pickle
import random
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import opponent_turn as O  # noqa: E402

from riftbound.ai.net_mcts import NetGuidedMCTSAgent  # noqa: E402
from riftbound.core.decisions import DecisionPoint, Observation  # noqa: E402
from riftbound.core.legality import legal_actions  # noqa: E402


class Fixed(O.Ref):
    """The reference with a fixed number of iterations (deterministic)."""

    def __init__(self, player, iters: int, rng):
        super().__init__(player, 0.0, rng)
        self.iterations = self.reaction_iterations = iters

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        return NetGuidedMCTSAgent.search(self, point, legal, cards_played=cards_played, bf_idx=bf_idx)


class TurnArm(Fixed):
    """The mover: this turn as the variant (`variant`) or the reference, at
    equal time per move; from the next turn on the reference."""

    def __init__(self, player, iters, rng, variant: bool, ratio: float, turn0: int):
        super().__init__(player, iters, rng)
        self.variant, self.turn0, self.base = variant, turn0, iters
        self.v_iters = max(1, round(iters * ratio))
        self._in_turn_tree = False
        self.sim_errors = 0
        self.first = None           # the first move of the turn

    def _now(self) -> bool:
        return self.variant and self.gs.turn == self.turn0

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        self.iterations = self.reaction_iterations = self.v_iters if self._now() else self.base
        return super().search(point, legal, cards_played=cards_played, bf_idx=bf_idx)

    def _iterate(self, root, side, cards_played):
        self._in_turn_tree = self._now()
        try:
            super()._iterate(root, side, cards_played)
        finally:
            self._in_turn_tree = False

    def _leaf(self, clone, side):
        return O.reply_value(clone, side, self) if self._in_turn_tree else O._static(clone, side)

    def _net_value(self, clone, side):
        return self._leaf(clone, side)

    def decide_action(self, opponent, cards_played: int = 0):
        a = super().decide_action(opponent, cards_played)
        if self.first is None:
            self.first = a
        return a


def play_on(task):
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import determinize
    path, arm, k, iters, ratio = task
    w = k + int(os.environ.get("WORLD0", "0"))  # another set of worlds
    d = pickle.load(open(path, "rb"))
    side = d["side"]
    gs = d["state"].clone()
    gs.rng = random.Random(10_000 + w)
    determinize(gs, observer=side, rng=gs.rng)
    other = gs.other(side)
    mover = TurnArm(gs.get_player(side), iters, random.Random(20_000 + w), arm == "reply", ratio, gs.turn)
    gs.get_player(side).agent = mover
    gs.get_player(other).agent = Fixed(gs.get_player(other), iters, random.Random(30_000 + w))
    res = GameLoop(gs).resume_to_completion()
    return arm, k, 1.0 if res.winner == side else 0.5 if res.winner == "DRAW" else 0.0, mover.first


def labels(d) -> dict:
    from riftbound.core.loop import GameLoop
    gs = d["state"].clone()
    loop = GameLoop(gs)
    return {a.to_engine(): a.label for a in legal_actions(loop, DecisionPoint.TURN_ACTION, d["side"])}


def show(path) -> None:
    d = pickle.load(open(path, "rb"))
    gs, side = d["state"], d["side"]
    other = gs.other(side)
    lab = labels(d)
    obs = Observation.from_state(gs, side)
    o = obs
    print(f"{Path(path).name}: turn {gs.turn}, {side} to act ({o.my_legend}), cards played this turn {d['cards_played']}"
          f"  points {side} {o.my_points} - {other} {o.opp_points}")
    me, them = gs.get_player(side), gs.get_player(other)
    print(f"  {side}: runes {o.my_runes} ({o.my_runes_ready} ready) {o.my_rune_domains}, energy {o.my_energy}, "
          f"legend ready {o.my_legend_ready}, champion zone {o.my_champion}, deck {o.my_deck_count}")
    print(f"  {other}: runes {o.opp_runes} ({o.opp_runes_ready} ready) {o.opp_rune_domains}, energy {o.opp_energy}, "
          f"legend {o.opp_legend} ready {o.opp_legend_ready}, champion zone {o.opp_champion}, deck {o.opp_deck_count}")
    print(f"  hand {side}: {[c.name for c in me.hand]}")
    print(f"  hand {other} (hidden, {len(them.hand)}): {[c.name for c in them.hand]}")
    print(f"  trash {side}: {list(o.my_trash)}; trash {other}: {list(o.opp_trash)}")
    def us(units):
        return [(u.card.name, u.might, '' if u.ready else 'exh') for u in units]
    for name, p in ((side, me), (other, them)):
        print(f"  {name} base: {us(p.base_units)}")
    for i, bf in enumerate(gs.battlefields):
        print(f"  BF{i} {bf.card.name if getattr(bf, 'card', None) else ''} controller {bf.controller()}: "
              f"A {us(bf.units_A)}  B {us(bf.units_B)}")
    print(f"  table value now {O.table_value(obs):+.2f}")
    for who in ("reply", "ref"):
        root = d[who + "_root"]
        print(f"  {who} plays: {lab.get(d[who], d[who])}")
        for k, (n, q) in sorted(root.items(), key=lambda kv: -kv[1][1] if kv[1][0] else 9)[:6]:
            if n:
                print(f"      {lab.get(k, k)!s:60.60s} N={n:3d} Q={q:+.2f}")


if __name__ == "__main__":
    if sys.argv[1] == "--show":
        for p in sys.argv[2:]:
            show(p)
        sys.exit()
    path = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    ratio = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    import math
    from collections import Counter
    tasks = [(path, m, i, iters, ratio) for i in range(k) for m in ("reply", "ref")]
    with Pool(int(os.environ.get("PROCS", "4"))) as p:
        rows = p.map(play_on, tasks)
    lab = labels(pickle.load(open(path, "rb")))
    by = {m: {i: s for mm, i, s, _ in rows if mm == m} for m in ("reply", "ref")}
    diff = [by["reply"][i] - by["ref"][i] for i in range(k)]
    m = sum(diff) / k
    sd = math.sqrt(sum((x - m) ** 2 for x in diff) / max(1, k - 1))
    print(f"{Path(path).name}: variant's turn {sum(by['reply'].values()) / k:.2f}, reference's turn {sum(by['ref'].values()) / k:.2f}"
          f"  (paired diff {m:+.2f} ± {1.96 * sd / math.sqrt(k):.2f}; variant better in {sum(1 for x in diff if x > 0)}, worse in {sum(1 for x in diff if x < 0)} of {k} worlds)")
    for arm in ("reply", "ref"):
        c = Counter(lab.get(f, f) for mm, _, _, f in rows if mm == arm)
        print(f"  {arm} first move: " + "; ".join(f"{n}× {a}" for a, n in c.most_common(4)))
