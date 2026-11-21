"""Self-play games for PPO (21/11): two agents in the same GameLoop, each
choice to the side that makes it; one trajectory per seat (its own choices,
in order), reward 0 until the end, then +1 / -1 / 0 (a draw, the turn cap
included) on each seat's last choice, even when the other seat ended the
game. GAE per seat, gamma = 1, lambda = 0.98 (revisione esterna)."""
from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
DECKS = ROOT / "riftbound/data/decks"
EVE = DECKS / "competitive_evelynn.json"
KHA = DECKS / "competitive_khazix.json"
MAX_TURNS = 40


def play(seed: int, nets: dict, learners: dict, sample: bool = True, starter: Optional[str] = None,
         deck_a: Path = EVE, deck_b: Path = KHA, opponent: Optional[str] = None) -> dict:
    """One game. nets: {"A": net, "B": net} (a seat with net None plays
    `opponent`, a heuristic agent: "simple_trade", "random"); learners: which
    seats record examples. -> {"winner", "z": {seat: +1/-1/0}, "records":
    {seat: [...]}, "counts": Counter, "turns"}."""
    from riftbound.ai.ppo.agent import PPOAgent, PPOChooser
    from riftbound.core.game_factory import build_game, make_agent
    from riftbound.core.loop import GameLoop
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b, ai_a=None, ai_b=None,
                    max_turns=MAX_TURNS, first_player=starter or ("a" if seed % 2 == 0 else "b"))
    records = {"A": [], "B": []}
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        if nets.get(seat) is None:
            p.agent = make_agent(opponent or "simple_trade", p)
            if hasattr(p.agent, "rng"):
                p.agent.rng = random.Random(seed * 2 + (seat == "B"))
        else:
            p.agent = PPOAgent(p, nets[seat], sample=sample, seed=seed * 2 + (seat == "B"),
                               record=records[seat] if learners.get(seat) else None)
    loop = GameLoop(gs)
    loop.chooser = PPOChooser(gs)
    res = loop.start()
    z = {s: (1.0 if res.winner == s else 0.0 if res.winner == "DRAW" else -1.0) for s in ("A", "B")}
    counts: Counter = Counter()
    for seat in ("A", "B"):
        counts.update(getattr(gs.get_player(seat).agent, "counts", {}))
    return {"winner": res.winner, "z": z, "records": records, "counts": counts, "turns": gs.turn}


def gae(recs: list, z: float, gamma: float = 1.0, lam: float = 0.98) -> None:
    """Advantages and returns of one seat's choices, in place: reward z on the
    last, 0 before; values of the collecting net."""
    nxt = 0.0
    for t in range(len(recs) - 1, -1, -1):
        last = t == len(recs) - 1
        v_next = 0.0 if last else recs[t + 1]["v"]
        delta = (z if last else 0.0) + gamma * v_next - recs[t]["v"]
        nxt = delta + (0.0 if last else gamma * lam * nxt)
        recs[t]["adv"] = nxt
        recs[t]["ret"] = nxt + recs[t]["v"]
