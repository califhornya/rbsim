"""Diagnostic: two nets head to head, both searching (no exploration).

  uv run python scripts/diag/net_vs_net.py runs/competitive3/net_0060.pt runs/competitive3/net_0010.pt

Games come in pairs: the same deal (seed, decks, seats) played twice, with the
nets swapping places, so seat, deck and the draw cancel out. The pairs cycle
through the four deck pairings (Kai'Sa / Kennen, mirrors included). Same seeds
at every launch. The score is the first net's (1 win, 0.5 draw).

Options: --games (200, rounded to pairs), --iterations (100, the search of
both nets, as in the training's evaluations), --workers (macOS: the fast
cores; elsewhere half the cores), --max-turns (40), --seed (0)."""
import argparse
import math
import os
import random
import subprocess
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch

DECKS = {"kaisa": Path("riftbound/data/decks/competitive_kaisa.json"),
         "kennen": Path("riftbound/data/decks/competitive_kennen.json")}
PAIRINGS = [("kaisa", "kennen"), ("kennen", "kaisa"), ("kaisa", "kaisa"), ("kennen", "kennen")]

_NETS: dict = {}


def _net(path):
    from riftbound.ai.net import load_checkpoint
    if path not in _NETS:
        _NETS[path] = load_checkpoint(path, device=torch.device("cpu"))
    return _NETS[path]


def game(task):
    """One game; returns the first net's result ("W"/"D"/"L") and the details."""
    pair, swap, seed, deck_a, deck_b, path_1, path_2, iters, max_turns = task
    from riftbound.ai.net_mcts import NetGuidedMCTSAgent
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    seat_1 = "B" if swap else "A"
    gs = build_game(game_seed=seed, deck_a_path=DECKS[deck_a], deck_b_path=DECKS[deck_b],
                    ai_a=None, ai_b=None, max_turns=max_turns)
    for seat, path in ((seat_1, path_1), (gs.other(seat_1), path_2)):
        player = gs.get_player(seat)
        player.agent = NetGuidedMCTSAgent(player, _net(path), iterations=iters,
                                          rng=random.Random(seed * 2 + (seat == "B")))
    res = GameLoop(gs).start()
    out = "D" if res.winner == "DRAW" else "W" if res.winner == seat_1 else "L"
    return dict(pair=pair, out=out, seat=seat_1, deck=deck_a if seat_1 == "A" else deck_b,
                turns=res.turns)


def _init():
    from riftbound.compute import be_gentle
    be_gentle()
    torch.set_num_threads(1)
    import warnings
    warnings.filterwarnings("ignore")


def _default_workers() -> int:
    if sys.platform == "darwin":
        try:
            return int(subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                                      capture_output=True, text=True).stdout)
        except ValueError:
            pass
    return max(1, (os.cpu_count() or 4) // 2)


def _score(rows) -> float:
    c = Counter(r["out"] for r in rows)
    return (c["W"] + 0.5 * c["D"]) / max(1, len(rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("net_1")
    ap.add_argument("net_2")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--iterations", type=int, default=100)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    for p in (a.net_1, a.net_2):
        if not Path(p).exists():
            sys.exit(f"missing: {p}")
    pairs = max(1, a.games // 2)
    rng = random.Random(a.seed)
    tasks = []
    for g in range(pairs):
        seed = rng.randrange(1 << 30)
        deck_a, deck_b = PAIRINGS[g % 4]
        for swap in (False, True):
            tasks.append((g, swap, seed, deck_a, deck_b, a.net_1, a.net_2, a.iterations, a.max_turns))
    workers = a.workers or _default_workers()
    name_1, name_2 = Path(a.net_1).stem, Path(a.net_2).stem
    print(f"{name_1} vs {name_2}: {len(tasks)} games, {a.iterations} iterations, {workers} workers")
    t0 = time.time()
    rows = []
    with Pool(workers, initializer=_init) as pool:
        for r in pool.imap_unordered(game, tasks):
            rows.append(r)
            if len(rows) % 20 == 0:
                print(f"  {len(rows)}/{len(tasks)} {name_1} {_score(rows):.2f} "
                      f"({(time.time() - t0) / 60:.0f} min)", flush=True)

    n = len(rows)
    c = Counter(r["out"] for r in rows)
    s = _score(rows)
    # Standard error from the pairs (the two games of a deal are not independent).
    by_pair: dict = {}
    for r in rows:
        by_pair.setdefault(r["pair"], []).append(1.0 if r["out"] == "W" else 0.5 if r["out"] == "D" else 0.0)
    means = [sum(v) / len(v) for v in by_pair.values()]
    sd = math.sqrt(sum((m - s) ** 2 for m in means) / max(1, len(means) - 1))
    se = sd / math.sqrt(len(means))
    print(f"\n{name_1} vs {name_2}: score {s:.3f} ± {1.96 * se:.3f} (95%)  "
          f"W{c['W']} D{c['D']} L{c['L']}  turns {sum(r['turns'] for r in rows) / n:.1f}")
    both = Counter("1" if m == 1 else "2" if m == 0 else "split" for m in means)
    print(f"deals: {name_1} wins both {both['1']}, {name_2} wins both {both['2']}, split {both['split']}")
    for key in ("deck", "seat"):
        parts = "  ".join(f"{v} {_score([r for r in rows if r[key] == v]):.2f}"
                          for v in sorted({r[key] for r in rows}))
        print(f"{name_1} by {key}: {parts}")
    print(f"{(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
