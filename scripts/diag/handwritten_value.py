"""The same search with a hand-written value (points, battlefields, might, cards) and uniform
priors: how far does the search go when the value is crude but sane?"""
import sys, math, random, time
from pathlib import Path
from collections import Counter
from multiprocessing import Pool
# The owner's post-ban decks (Kai'Sa and Kennen until 2026-11-17).
DECKS = [Path("riftbound/data/decks/competitive_evelynn.json"), Path("riftbound/data/decks/competitive_khazix.json")]

# The value, in riftbound/ai/handwritten.py (the bot used elsewhere too).
from riftbound.ai.handwritten import table_value  # noqa: E402

def _value():
    """RBSIM_VALUE=judgment: the value from the user's judgments
    (riftbound/ai/judgment_value.py); default: table_value."""
    import os
    if os.environ.get("RBSIM_VALUE") == "judgment":
        # RBSIM_W='{"hidden": 0, ...}': other weights, to test one judgment at a time.
        import json
        from riftbound.ai import judgment_value as J
        J.W.update(json.loads(os.environ.get("RBSIM_W", "{}")))
        return J.judgment_value
    return table_value

def game(task):
    seed, opponent, seat, iters = task
    from riftbound.ai.net_mcts import NetGuidedMCTSAgent
    from riftbound.core.decisions import Observation
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.loop import GameLoop

    value = _value()

    class Heur(NetGuidedMCTSAgent):
        def _evaluate(self, clone, side, legal_ga):
            ts = [a.to_engine() for a in legal_ga]
            u = 1.0 / max(1, len(ts))
            return {t: u for t in ts}, value(Observation.from_state(clone, side))
        def _net_value(self, clone, side):
            return value(Observation.from_state(clone, side))
        _value_only = _net_value
        def _play(self, root, side, point=None):
            import os
            from riftbound.ai.net_mcts import _Plan, _LEVEL
            from riftbound.core.decisions import DecisionPoint
            if os.environ.get("MAXB") != "1":
                return super()._play(root, side, point or DecisionPoint.TURN_ACTION)
            point = point or DecisionPoint.TURN_ACTION
            def score(node):
                kids = [c for c in list(node.children.values()) + list(node.choices.values()) if c.N > 0]
                return max(score(c) for c in kids) if kids else node.W / node.N
            items = [(k, c) for k, c in root.children.items() if c.N > 0] or list(root.children.items())
            key = max(items, key=lambda kv: score(kv[1]) if kv[1].N else -9)[0]
            child = root.children[key]
            if child.choices:
                self.loop.chooser = _Plan(side, child, _LEVEL[point], self.loop, self.loop.chooser)
            return key

    r = random.Random(seed)
    d_net, d_opp = r.choice(DECKS), r.choice(DECKS)
    da, db = (d_net, d_opp) if seat == "A" else (d_opp, d_net)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None, max_turns=40)
    me = gs.get_player(seat); them = gs.get_player(gs.other(seat))
    import os
    me.agent = Heur(me, None, iterations=iters, rng=random.Random(seed), backup=os.environ.get('BACKUP', 'best'))
    if opponent == "random":
        from riftbound.ai.search.random_agent import RandomAgent
        them.agent = RandomAgent(them, random.Random(seed))
    elif opponent == "table":
        # The same search with table_value: the judgments' value head to head.
        class Table(Heur):
            def _evaluate(self, clone, side, legal_ga):
                ts = [a.to_engine() for a in legal_ga]
                return {t: 1.0 / max(1, len(ts)) for t in ts}, table_value(Observation.from_state(clone, side))
            def _net_value(self, clone, side):
                return table_value(Observation.from_state(clone, side))
            _value_only = _net_value
        them.agent = Table(them, None, iterations=iters, rng=random.Random(seed + 1), backup="best")
    else:
        them.agent = make_agent(opponent, them)
    res = GameLoop(gs).start()
    out = "W" if res.winner == seat else "D" if res.winner == "DRAW" else "L"
    return dict(out=out, opp=opponent, turns=res.turns, t=me.agent.turns, e=me.agent.empty_turns,
                mine=d_net.stem.split("_")[-1], theirs=d_opp.stem.split("_")[-1])

if __name__ == "__main__":
    n, iters = int(sys.argv[1]), int(sys.argv[2])
    opps = sys.argv[3].split(",")
    t0 = time.time()
    with Pool(4) as p:
        rows = list(p.imap_unordered(game, [(1000 + g, o, "A" if g % 2 == 0 else "B", iters) for o in opps for g in range(n)]))
    for o in opps:
        rs = [r for r in rows if r["opp"] == o]; c = Counter(r["out"] for r in rs)
        print(f"{o:13s} W{c['W']} D{c['D']} L{c['L']} score={(c['W'] + 0.5 * c['D']) / len(rs):.2f} turns={sum(r['turns'] for r in rs) / len(rs):.1f} empty={sum(r['e'] for r in rs) / max(1, sum(r['t'] for r in rs)):.2f}")
        for mine in sorted({r["mine"] for r in rs}):
            for theirs in sorted({r["theirs"] for r in rs}):
                sub = [r for r in rs if r["mine"] == mine and r["theirs"] == theirs]
                if sub:
                    w = sum(1 for r in sub if r["out"] == "W") + 0.5 * sum(1 for r in sub if r["out"] == "D")
                    print(f"    search {mine:8s} vs {theirs:8s} {w / len(sub):.2f} ({len(sub)} games)")
    print(f"{time.time() - t0:.0f}s")
