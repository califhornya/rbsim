"""The same search with a hand-written value (points, battlefields, might, cards) and uniform
priors: how far does the search go when the value is crude but sane?"""
import sys, math, random, time
from pathlib import Path
from collections import Counter
from multiprocessing import Pool
DECKS = [Path("riftbound/data/decks/competitive_kaisa.json"), Path("riftbound/data/decks/competitive_kennen.json")]

def table_value(obs) -> float:
    me = obs.viewer
    s = 0.45 * (obs.my_points - obs.opp_points)
    for bf in obs.battlefields:
        mine = sum(u.might for u in getattr(bf, me)); theirs = sum(u.might for u in getattr(bf, 'B' if me == 'A' else 'A'))
        if bf.controller == me: s += 0.30
        elif bf.controller is not None: s -= 0.30
        s += 0.05 * (mine - theirs)
    s += 0.03 * (sum(u.might for u in obs.my_base_units) - sum(u.might for u in obs.opp_base_units))
    s += 0.03 * (len(obs.my_hand) - obs.opp_hand_count)
    return math.tanh(s)

def game(task):
    seed, opponent, seat, iters = task
    from riftbound.ai.net_mcts import NetGuidedMCTSAgent
    from riftbound.core.decisions import Observation
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.loop import GameLoop

    class Heur(NetGuidedMCTSAgent):
        def _evaluate(self, clone, side, legal_ga):
            ts = [a.to_engine() for a in legal_ga]
            u = 1.0 / max(1, len(ts))
            return {t: u for t in ts}, table_value(Observation.from_state(clone, side))
        def _net_value(self, clone, side):
            return table_value(Observation.from_state(clone, side))
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
    else:
        them.agent = make_agent(opponent, them)
    res = GameLoop(gs).start()
    out = "W" if res.winner == seat else "D" if res.winner == "DRAW" else "L"
    return dict(out=out, opp=opponent, turns=res.turns, t=me.agent.turns, e=me.agent.empty_turns)

if __name__ == "__main__":
    n, iters = int(sys.argv[1]), int(sys.argv[2])
    opps = sys.argv[3].split(",")
    t0 = time.time()
    with Pool(4) as p:
        rows = list(p.imap_unordered(game, [(1000 + g, o, "A" if g % 2 == 0 else "B", iters) for o in opps for g in range(n)]))
    for o in opps:
        rs = [r for r in rows if r["opp"] == o]; c = Counter(r["out"] for r in rs)
        print(f"{o:13s} W{c['W']} D{c['D']} L{c['L']} score={(c['W'] + 0.5 * c['D']) / len(rs):.2f} turns={sum(r['turns'] for r in rs) / len(rs):.1f} empty={sum(r['e'] for r in rs) / max(1, sum(r['t'] for r in rs)):.2f}")
    print(f"{time.time() - t0:.0f}s")
