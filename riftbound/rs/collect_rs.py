"""collect.play on the Rust engine (porting, F5): same signature, same
result. The seats with a net play with the PPO agent (Rust asks, Python's
AskPPO answers), the others with Rust's simple_trade or random (seeded as
collect.play seeds them); "bot" (the hand-written bot) is not ported."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

from riftbound.ai.ppo.collect import EVE, KHA, MAX_TURNS


def play(seed: int, nets: dict, learners: dict, sample: bool = True, starter: Optional[str] = None,
         deck_a: Path = EVE, deck_b: Path = KHA, opponent: Optional[str] = None) -> dict:
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.agent_rs import AskPPO
    g = rb.build(seed, deck_a, deck_b, starter or ("a" if seed % 2 == 0 else "b"), MAX_TURNS)
    records = {"A": [], "B": []}
    for seat in ("A", "B"):
        agent_seed = seed * 2 + (seat == "B")
        if nets.get(seat) is None:
            if opponent == "bot":
                raise NotImplementedError("collect_rs: the hand-written bot is not ported to Rust")
            g.set_agent(seat, opponent or "simple_trade", agent_seed)
        else:
            g.set_ppo_agent(seat, AskPPO(nets[seat], seat, sample=sample, seed=agent_seed,
                                         record=records[seat] if learners.get(seat) else None))
    g.set_side_chooser()
    winner, turns = g.start()
    z = {s: (1.0 if winner == s else 0.0 if winner == "DRAW" else -1.0) for s in ("A", "B")}
    counts: Counter = Counter()
    for seat in ("A", "B"):
        counts.update(g.counts(seat))
    return {"winner": winner, "z": z, "records": records, "counts": counts, "turns": g.turn}
