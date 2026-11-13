"""Fresh self-play games of a net: outcomes by seat/deck/first player, and the net's value error on
those (held-out) states, by game phase."""
import sys, random
from pathlib import Path
from collections import Counter
from multiprocessing import Pool
import numpy as np, torch
torch.set_num_threads(1)
DECKS = [Path("riftbound/data/decks/competitive_kaisa.json"), Path("riftbound/data/decks/competitive_kennen.json")]

def game(task):
    ckpt, seed, iters = task
    from riftbound.ai.net import load_checkpoint
    from riftbound.ai.net_mcts import NetGuidedMCTSAgent
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    net = load_checkpoint(ckpt, device=torch.device("cpu")); net.eval()
    r = random.Random(seed)
    da, db = r.choice(DECKS), r.choice(DECKS)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None, max_turns=40)
    ex = []
    for side, pl in (("A", gs.A), ("B", gs.B)):
        ag = NetGuidedMCTSAgent(pl, net, iterations=iters, rng=random.Random(r.randrange(1 << 30)), explore=True)
        ag.record = ex; pl.agent = ag
    first = gs.active
    res = GameLoop(gs).start()
    xs = torch.as_tensor(np.stack([e["state"] for e in ex]))
    with torch.no_grad():
        v = net(xs)[1].squeeze(1).numpy()
    z = np.array([0.0 if res.winner == "DRAW" else (1.0 if res.winner == e["player"] else -1.0) for e in ex])
    return dict(winner=res.winner, first=first, turns=res.turns, da=da.stem, db=db.stem, v=v, z=z,
                pa=gs.points_A, pb=gs.points_B)

if __name__ == "__main__":
    ckpt, n, iters = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    with Pool(4) as p:
        gs = list(p.imap_unordered(game, [(ckpt, 5000 + g, iters) for g in range(n)]))
    print("winner", dict(Counter(g["winner"] for g in gs)), "first-player wins", sum(g["winner"] == g["first"] for g in gs), "/", len(gs),
          "turns", round(sum(g["turns"] for g in gs) / len(gs), 1), "ex/game", round(sum(len(g["v"]) for g in gs) / len(gs), 1))
    wd = Counter()
    for g in gs:
        if g["winner"] in "AB" and g["da"] != g["db"]:
            wd[g["da"] if g["winner"] == "A" else g["db"]] += 1
    print("non-mirror wins by deck", dict(wd))
    v = np.concatenate([g["v"] for g in gs]); z = np.concatenate([g["z"] for g in gs])
    print(f"held-out value MSE={np.mean((v - z) ** 2):.3f} (predict 0: {np.mean(z ** 2):.3f})  corr={np.corrcoef(v, z)[0, 1]:.3f}  mean|v|={np.mean(np.abs(v)):.2f} sign-acc={np.mean(np.sign(v) == np.sign(z)):.2f}")
    for lo, hi in ((0, .33), (.33, .66), (.66, 1.01)):
        vv, zz = [], []
        for g in gs:
            m = len(g["v"]); a, b = int(lo * m), int(min(hi, 1) * m)
            vv.append(g["v"][a:b]); zz.append(g["z"][a:b])
        vv, zz = np.concatenate(vv), np.concatenate(zz)
        print(f"  phase {lo:.2f}-{hi:.2f}: MSE={np.mean((vv - zz) ** 2):.3f} corr={np.corrcoef(vv, zz)[0, 1]:.3f}")
