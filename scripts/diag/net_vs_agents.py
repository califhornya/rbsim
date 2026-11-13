"""Diagnostic: a net (untrained or checkpoint) with search vs an opponent.
Reports W/D/L, turns, final points, the net's turns passed at once, actions per turn.

  uv run python scripts/diag/net_vs_agents.py runs/competitive3/net.pt 40 100 simple_trade,random
  (checkpoint or "-" for an untrained net, games per opponent, MCTS iterations, opponents)

Same seeds every time: two nets, or two settings, play the same games (paired).
Environment: BACKUP=best|mean (the search's backup), CPUCT=1.5, BYQ=1 (with
BACKUP=mean: play the visited move with the best mean). 4 processes."""
import sys, random, json, time
from pathlib import Path
from collections import Counter
from multiprocessing import Pool
import torch
torch.set_num_threads(1)

DECKS = [Path("riftbound/data/decks/competitive_kaisa.json"), Path("riftbound/data/decks/competitive_kennen.json")]

def game(task):
    ckpt, seed, opponent, seat, iters, torch_seed = task
    from riftbound.ai.net import RiftboundNet, load_checkpoint
    from riftbound.ai.net_mcts import NetGuidedMCTSAgent
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.loop import GameLoop
    torch.set_num_threads(1)
    if ckpt:
        net = load_checkpoint(ckpt, device=torch.device("cpu"))
    else:
        torch.manual_seed(torch_seed)
        net = RiftboundNet()
    r = random.Random(seed)
    d_net, d_opp = r.choice(DECKS), r.choice(DECKS)
    da, db = (d_net, d_opp) if seat == "A" else (d_opp, d_net)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None, max_turns=40)
    me = gs.get_player(seat); them = gs.get_player(gs.other(seat))
    import os
    cp = float(os.environ.get("CPUCT", "1.5")); byq = os.environ.get("BYQ") == "1"
    agent = NetGuidedMCTSAgent(me, net, iterations=iters, rng=random.Random(seed), c_puct=cp, backup=os.environ.get('BACKUP', 'best'))
    if byq:
        def _play(root, side, point=None, _a=agent):
            from riftbound.ai.net_mcts import _Plan, _LEVEL
            from riftbound.core.decisions import DecisionPoint
            point = point or DecisionPoint.TURN_ACTION
            items = [(k, c) for k, c in root.children.items() if c.N > 0] or list(root.children.items())
            tot = sum(c.N for _, c in items) or 1
            good = [(k, c) for k, c in items if c.N >= max(2, 0.05 * tot)] or items
            key = max(good, key=lambda kv: kv[1].W / max(1, kv[1].N))[0]
            child = root.children[key]
            if child.choices:
                _a.loop.chooser = _Plan(side, child, _LEVEL[point], _a.loop, _a.loop.chooser)
            return key
        agent._play = _play
    kinds = Counter()
    orig = agent.decide_action
    state = {"turn": None, "acts": 0, "turns": 0, "empty": 0}
    def decide(opponent, cards_played=0):
        act = orig(opponent, cards_played)
        if state["turn"] != gs.turn:
            state["turn"] = gs.turn; state["turns"] += 1; state["first"] = True
        if act[0] == "PASS" and state.get("first") and gs.pending_move is None:
            state["empty"] += 1
        state["first"] = False
        kinds[act[0]] += 1
        return act
    agent.decide_action = decide
    me.agent = agent
    if opponent == "random":
        from riftbound.ai.search.random_agent import RandomAgent
        them.agent = RandomAgent(them, random.Random(seed))
    else:
        them.agent = make_agent(opponent, them)
    res = GameLoop(gs).start()
    mine = gs.points_A if seat == "A" else gs.points_B
    theirs = gs.points_B if seat == "A" else gs.points_A
    out = "W" if res.winner == seat else "D" if res.winner == "DRAW" else "L"
    return dict(out=out, turns=res.turns, mine=mine, theirs=theirs, kinds=dict(kinds), opp=opponent, myturns=state["turns"], empty=state["empty"])

if __name__ == "__main__":
    ckpt = sys.argv[1] if sys.argv[1] != "-" else None
    n = int(sys.argv[2]); iters = int(sys.argv[3])
    opps = sys.argv[4].split(",")
    tasks = [(ckpt, 1000 + g, o, "A" if g % 2 == 0 else "B", iters, 7) for o in opps for g in range(n)]
    t0 = time.time()
    with Pool(4) as p:
        rows = list(p.imap_unordered(game, tasks))
    for o in opps:
        rs = [r for r in rows if r["opp"] == o]
        c = Counter(r["out"] for r in rs)
        k = Counter()
        for r in rs: k.update(r["kinds"])
        tot = sum(k.values()) or 1
        print(f"{o:13s} W{c['W']} D{c['D']} L{c['L']} score={(c['W']+0.5*c['D'])/len(rs):.2f} "
              f"turns={sum(r['turns'] for r in rs)/len(rs):.1f} pts={sum(r['mine'] for r in rs)/len(rs):.1f}-{sum(r['theirs'] for r in rs)/len(rs):.1f} "
              f"emptyturns={sum(r['empty'] for r in rs)/max(1,sum(r['myturns'] for r in rs)):.2f} acts/turn={(tot-k['PASS'])/max(1,sum(r['myturns'] for r in rs)):.2f} kinds={ {a: round(b/tot,2) for a,b in k.most_common(6)} }")
    print(f"{time.time()-t0:.0f}s")
