"""At each searched TURN_ACTION root of a net (vs simple_trade): prior and visit share of PASS,
Q(PASS) vs Q of the other children."""
import sys, random
from pathlib import Path
from multiprocessing import Pool
import torch
torch.set_num_threads(1)
DECKS = [Path("riftbound/data/decks/competitive_kaisa.json"), Path("riftbound/data/decks/competitive_kennen.json")]
PASS = ("PASS", None, None)

def game(task):
    ckpt, seed, seat, iters, explore = task
    from riftbound.ai.net import load_checkpoint
    from riftbound.ai.net_mcts import NetGuidedMCTSAgent
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.loop import GameLoop
    net = load_checkpoint(ckpt, device=torch.device("cpu"))
    r = random.Random(seed)
    da, db = r.choice(DECKS), r.choice(DECKS)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None, max_turns=40)
    me = gs.get_player(seat); them = gs.get_player(gs.other(seat))
    agent = NetGuidedMCTSAgent(me, net, iterations=iters, rng=random.Random(seed), explore=explore)
    rows = []
    orig = agent.search
    def search(point, legal, **kw):
        root = orig(point, legal, **kw)
        if point.name == "TURN_ACTION" and PASS in root.children and len(root.children) > 1 and gs.pending_move is None:
            tot = sum(c.N for c in root.children.values()) or 1
            p = root.children[PASS]
            others = [(k, c) for k, c in root.children.items() if k != PASS and c.N > 0]
            if p.N and others:
                qp = p.W / p.N
                qo = [c.W / c.N for _, c in others]
                wq = sum(c.W for _, c in others) / sum(c.N for _, c in others)
                rows.append(dict(prior=root.P.get(PASS, 0.0), visit=p.N / tot, nlegal=len(root.children),
                                 qpass=qp, qmax=max(qo), qmean=sum(qo) / len(qo), qw=wq,
                                 rootv=root.value if hasattr(root, "value") else 0.0))
        return root
    agent.search = search
    me.agent = agent
    them.agent = make_agent("simple_trade", them)
    GameLoop(gs).start()
    return rows

if __name__ == "__main__":
    ckpt, n, iters = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    explore = len(sys.argv) > 4 and sys.argv[4] == "explore"
    tasks = [(ckpt, 2000 + g, "A" if g % 2 == 0 else "B", iters, explore) for g in range(n)]
    with Pool(4) as p:
        rows = [r for rs in p.imap_unordered(game, tasks) for r in rs]
    m = lambda k: sum(r[k] for r in rows) / len(rows)
    print(f"roots={len(rows)} nlegal={m('nlegal'):.1f} uniform={sum(1/r['nlegal'] for r in rows)/len(rows):.3f} priorPASS={m('prior'):.3f} visitPASS={m('visit'):.3f} "
          f"Qpass={m('qpass'):+.3f} Qmax_other={m('qmax'):+.3f} Qmean_other={m('qmean'):+.3f} "
          f"P(Qmax>Qpass)={sum(r['qmax']>r['qpass'] for r in rows)/len(rows):.2f} P(Qmean>Qpass)={sum(r['qmean']>r['qpass'] for r in rows)/len(rows):.2f} "
          f"PASS most visited={sum(r['visit']>=0.5 for r in rows)/len(rows):.2f}")
