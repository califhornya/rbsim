"""The bot of PR #32 against a variant that also plays the opponent's turn.

Reference ("ref"): the search of `handwritten_value.py` (uniform priors,
`table_value`, backup "best"): a leaf of the turn's tree is valued where it
stands, in the middle or at the end of the bot's own turn.

Variant ("reply"): the same search, the same value; every leaf of the turn's
tree is instead valued after the turn is ended there, the opponent has played
its whole turn (simple_trade's moves, on the iteration's determinized hand and
deck) and the bot's next turn has begun (Hold, channel, draw): what the value
sees is what the opponent does to the position, not the position alone. Only
the main turn changes; reactions and showdowns search as in the reference.

Both play to the same CPU time per decision (`budget`, seconds), so the
variant tries fewer lines. A pair of games: one seed, Evelynn in seat A and
Kha'Zix in seat B, the bots swapped between the two games.

  python scripts/diag/opponent_turn.py PAIRS BUDGET [--shadow DIR] [--seed0 N]

--shadow DIR: at each main-turn decision of the variant, the reference
searches the same position too (same budget, not played); where the two
choose different moves the position is saved in DIR (pickle) with both
searches' values, for `opponent_turn_check.py`.
"""
from __future__ import annotations

import math
import os
import pickle
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from handwritten_value import table_value  # noqa: E402  (the reference's value)

from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent  # noqa: E402
from riftbound.ai.net_mcts import NetGuidedMCTSAgent, _Node  # noqa: E402
from riftbound.core.decisions import DecisionPoint, Observation  # noqa: E402
from riftbound.core.legality import legal_actions  # noqa: E402

EVE = Path("riftbound/data/decks/competitive_evelynn.json")
KHA = Path("riftbound/data/decks/competitive_khazix.json")
MAX_TURNS = 40


def _static(clone, side) -> float:
    return table_value(Observation.from_state(clone, side))


class Ref(NetGuidedMCTSAgent):
    """The bot of PR #32, searching for `budget` CPU seconds per decision."""
    name = "ref"

    def __init__(self, player, budget: float, rng: random.Random):
        super().__init__(player, None, iterations=100, rng=rng, backup="best")
        self.budget = budget
        self.main_iters: list = []      # iterations of each main-turn search

    def _evaluate(self, clone, side, legal_ga):
        ts = [a.to_engine() for a in legal_ga]
        u = 1.0 / max(1, len(ts))
        return {t: u for t in ts}, self._leaf(clone, side)

    def _leaf(self, clone, side) -> float:
        return _static(clone, side)

    def _net_value(self, clone, side):
        return _static(clone, side)
    _value_only = _net_value

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        self._ensure_rng()
        side = self.player.name
        root = _Node()
        self._full = True
        t0, n = time.process_time(), 0
        while n < 1 or time.process_time() - t0 < self.budget:
            if point == DecisionPoint.TURN_ACTION:
                self._iterate(root, side, cards_played)
            else:
                self._iterate_now(root, side, point, legal, bf_idx)
            n += 1
        if point == DecisionPoint.TURN_ACTION:
            self.main_iters.append(n)
        return root


class Reply(Ref):
    """Ref whose turn-tree leaves are valued after the opponent's turn."""
    name = "reply"

    def __init__(self, player, budget: float, rng: random.Random, shadow_dir=None, tag=""):
        super().__init__(player, budget, rng)
        self._in_turn_tree = False
        self.sim_errors = 0
        self.shadow_dir = shadow_dir
        self.tag = tag
        self.disagreements = 0
        self.compared = 0

    def _iterate(self, root, side, cards_played, *rest):
        self._in_turn_tree = True
        try:
            super()._iterate(root, side, cards_played, *rest)
        finally:
            self._in_turn_tree = False

    def _net_value(self, clone, side):
        return self._leaf(clone, side) if self._in_turn_tree else _static(clone, side)

    def _leaf(self, clone, side) -> float:
        if not self._in_turn_tree:
            return _static(clone, side)
        return reply_value(clone, side, self)

    # -- shadow: what the reference would play here ---------------------------

    def decide_action(self, opponent, cards_played: int = 0):
        if self.shadow_dir is None:
            return super().decide_action(opponent, cards_played)
        side = self.player.name
        legal = legal_actions(self.loop, DecisionPoint.TURN_ACTION, side)
        if len(legal) <= 1:
            return super().decide_action(opponent, cards_played)
        snap = self.gs.clone()
        action = super().decide_action(opponent, cards_played)
        mine = {k: (c.N, c.Q) for k, c in self._last_root.children.items()}
        sh = Ref(self.player, self.budget, random.Random(self._rng.randrange(1 << 30)))
        sh.gs, sh.loop = self.gs, self.loop
        root = sh.search(DecisionPoint.TURN_ACTION, legal, cards_played=cards_played)
        tried = [(k, c) for k, c in root.children.items() if c.N > 0]
        ref_action = max(tried, key=lambda kv: kv[1].Q)[0]
        self.compared += 1
        if ref_action != action:
            self.disagreements += 1
            theirs = {k: (c.N, c.Q) for k, c in root.children.items()}
            name = f"{self.tag}_t{self.gs.turn:02d}_{self.disagreements:02d}.pkl"
            with open(Path(self.shadow_dir) / name, "wb") as f:
                pickle.dump(dict(state=snap, side=side, cards_played=cards_played,
                                 reply=action, ref=ref_action, reply_root=mine, ref_root=theirs,
                                 turn=self.gs.turn, tag=self.tag), f)
        return action

    def search(self, point, legal, *, cards_played: int = 0, bf_idx=None):
        root = super().search(point, legal, cards_played=cards_played, bf_idx=bf_idx)
        self._last_root = root
        return root


def reply_value(clone, side: str, owner=None) -> float:
    """`side`'s value of `clone` (a determinized copy, `side` to act in its
    main phase) after `side` ends its turn here and the opponent plays its
    turn with simple_trade's moves (both players' reactions and showdowns
    too), up to the start of `side`'s next Main Phase."""
    from riftbound.core.loop import GameLoop
    t = NetGuidedMCTSAgent._terminal_value(clone, side)
    if t is not None:
        return t
    if clone.active != side:
        return _static(clone, side)
    clone.A.agent = SimpleTradeAgent(clone.A)
    clone.B.agent = SimpleTradeAgent(clone.B)
    loop = GameLoop(clone)
    try:
        r = loop._end_turn()
        for _ in range(2):          # the opponent's turn, then this player's beginning
            if r is not None or clone.turn > clone.max_turns:
                break
            r = loop._begin_turn()
            if r is None and clone.active != side:
                r = loop._run_main_actions() or loop._end_turn()
            elif r is None:
                break
    except Exception:  # noqa: BLE001 — a simulation never stops the search
        if owner is not None:
            owner.sim_errors += 1
        return _static(clone, side) if clone.active == side else 0.0
    finally:
        clone.A.agent = clone.B.agent = None
    t = NetGuidedMCTSAgent._terminal_value(clone, side)
    if t is not None:
        return t
    if clone.turn > clone.max_turns:
        return 0.0                  # the turn cap: a draw
    return _static(clone, side)


def game(task):
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    seed, reply_seat, budget, shadow_dir = task
    gs = build_game(game_seed=seed, deck_a_path=EVE, deck_b_path=KHA, ai_a=None, ai_b=None,
                    max_turns=MAX_TURNS)
    bots = {}
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        rng = random.Random(seed * 2 + (seat == "B"))
        if seat == reply_seat:
            p.agent = Reply(p, budget, rng, shadow_dir=shadow_dir, tag=f"s{seed}_{seat}")
        else:
            p.agent = Ref(p, budget, rng)
        bots[seat] = p.agent
    t0 = time.process_time()
    res = GameLoop(gs).start()
    rb, fb = bots[reply_seat], bots["B" if reply_seat == "A" else "A"]
    out = "W" if res.winner == reply_seat else "D" if res.winner == "DRAW" else "L"
    return dict(seed=seed, reply_seat=reply_seat, out=out, turns=res.turns,
                first=gs.first_player if hasattr(gs, "first_player") else None,
                pts=(gs.points_A, gs.points_B), cpu=time.process_time() - t0,
                it_reply=rb.main_iters, it_ref=fb.main_iters, sim_errors=rb.sim_errors,
                compared=rb.compared, disagree=rb.disagreements)


def report(rows):
    c = Counter(r["out"] for r in rows)
    n = len(rows)
    score = (c["W"] + 0.5 * c["D"]) / n
    print(f"reply vs ref: {n} games  W{c['W']} D{c['D']} L{c['L']}  score {score:.3f}")
    pairs = {}
    for r in rows:
        pairs.setdefault(r["seed"], []).append(r)
    ps = [sum({"W": 1, "D": 0.5, "L": 0}[r["out"]] for r in v) / 2 for v in pairs.values() if len(v) == 2]
    if ps:
        m = sum(ps) / len(ps)
        sd = math.sqrt(sum((x - m) ** 2 for x in ps) / max(1, len(ps) - 1))
        dist = Counter(ps)
        print(f"  pairs {len(ps)}: mean {m:.3f} ± {1.96 * sd / math.sqrt(len(ps)):.3f} (95%)  "
              f"both won {dist[1.0]}, split {dist[0.5]}, both lost {dist[0.0]}, other {len(ps) - dist[1.0] - dist[0.5] - dist[0.0]}")
    for seat, deck in (("A", "Evelynn"), ("B", "Kha'Zix")):
        sub = [r for r in rows if r["reply_seat"] == seat]
        if sub:
            s = sum({"W": 1, "D": 0.5, "L": 0}[r["out"]] for r in sub) / len(sub)
            print(f"  reply with {deck:8s}: {s:.3f} ({len(sub)} games)")
    a_wins = sum(1 for r in rows if (r["out"] == "W") == (r["reply_seat"] == "A") and r["out"] != "D")
    print(f"  Evelynn (seat A) won {a_wins}/{n}")
    ir = [x for r in rows for x in r["it_reply"]]
    jf = [x for r in rows for x in r["it_ref"]]
    print(f"  iterations per main decision: reply {sum(ir) / max(1, len(ir)):.0f}, ref {sum(jf) / max(1, len(jf)):.0f}")
    print(f"  turns {sum(r['turns'] for r in rows) / n:.1f}, cpu per game {sum(r['cpu'] for r in rows) / n:.0f}s, "
          f"simulation errors {sum(r['sim_errors'] for r in rows)}")
    cmp_ = sum(r["compared"] for r in rows)
    if cmp_:
        print(f"  shadow: reference disagrees on {sum(r['disagree'] for r in rows)}/{cmp_} main decisions")


if __name__ == "__main__":
    pairs, budget = int(sys.argv[1]), float(sys.argv[2])
    shadow = sys.argv[sys.argv.index("--shadow") + 1] if "--shadow" in sys.argv else None
    seed0 = int(sys.argv[sys.argv.index("--seed0") + 1]) if "--seed0" in sys.argv else 3000
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    if shadow:
        os.makedirs(shadow, exist_ok=True)
    tasks = [(seed0 + i, seat, budget, shadow) for i in range(pairs) for seat in ("A", "B")]
    t0 = time.time()
    rows = []
    with Pool(int(os.environ.get("PROCS", "4"))) as p:
        for r in p.imap_unordered(game, tasks):
            rows.append(r)
            if out:
                with open(out, "a") as f:
                    f.write(repr(r) + "\n")
    report(sorted(rows, key=lambda r: (r["seed"], r["reply_seat"])))
    print(f"{time.time() - t0:.0f}s")
