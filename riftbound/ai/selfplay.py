"""Self-play game generation + the training step/loop (RL Chunk 4).

Closes the AlphaZero loop: play games with the network-guided MCTS on BOTH seats
(sharing one net), record (state, MCTS visit policy, legal mask, player) at each
searched decision, label each with the game's outcome z from that player's seat,
then train the net to match the search's policy (cross-entropy) and the outcome
(value MSE). Iterate: the net gets stronger, so the search gets stronger, so the
next games are better — the agent improves every iteration.

`train` runs it over a pool of decks with self-play games in parallel worker
processes, kept gentle on the machine (riftbound.compute: a quarter of the cores
by default, below-normal priority, one thread each, a pause between iterations),
and every few iterations measures the net against the simple_trade heuristic.

Requires the `rl` extra (torch). Run headless via `scripts/train_selfplay.py`.
"""

from __future__ import annotations

import json
import random
import tempfile
import time
import warnings
from collections import deque
from pathlib import Path
from statistics import mean
from typing import Optional, Sequence

import numpy as np
import torch
import torch.nn.functional as F

from riftbound.ai.net import RiftboundNet, default_device, masked_log_softmax
from riftbound.ai.net_mcts import NetGuidedMCTSAgent
from riftbound.core.game_factory import build_game, make_agent
from riftbound.core.loop import GameLoop


def play_selfplay_game(net: RiftboundNet, deck_a: Path, deck_b: Path, *,
                       seed: int = 0, iterations: int = 100, c_puct: float = 1.5,
                       max_turns: int = 40, explore: bool = True) -> list[dict]:
    """Play one self-play game; return training examples with value target ``z``
    (+1/-1/0) already filled from the outcome, per each example's seat.
    `explore`: Dirichlet noise and early visit-proportional moves (self-play)."""
    examples: list = []
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b,
                    ai_a=None, ai_b=None, max_turns=max_turns)
    rng = random.Random(seed)
    for side, player in (("A", gs.A), ("B", gs.B)):
        agent = NetGuidedMCTSAgent(player, net, iterations=iterations, c_puct=c_puct,
                                   rng=random.Random(rng.randrange(1 << 30)), explore=explore)
        agent.record = examples
        player.agent = agent
    result = GameLoop(gs).start()
    for ex in examples:
        if result.winner == "DRAW":
            ex["z"] = 0.0
        else:
            ex["z"] = 1.0 if result.winner == ex["player"] else -1.0
    return examples


def play_eval_game(net: RiftboundNet, deck_net: Path, deck_opp: Path, *, seed: int = 0,
                   iterations: int = 100, net_seat: str = "A", opponent: str = "simple_trade",
                   max_turns: int = 40) -> float:
    """The net (searching, no exploration) against a heuristic agent: 1 for a
    net win, 0.5 for a draw, 0 for a loss."""
    deck_a, deck_b = (deck_net, deck_opp) if net_seat == "A" else (deck_opp, deck_net)
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b,
                    ai_a=None, ai_b=None, max_turns=max_turns)
    me = gs.get_player(net_seat)
    them = gs.get_player(gs.other(net_seat))
    me.agent = NetGuidedMCTSAgent(me, net, iterations=iterations, rng=random.Random(seed))
    if opponent == "random":
        from riftbound.ai.search.random_agent import RandomAgent
        them.agent = RandomAgent(them, random.Random(seed))      # seeded: reproducible
    else:
        them.agent = make_agent(opponent, them)
    winner = GameLoop(gs).start().winner
    return 1.0 if winner == net_seat else 0.5 if winner == "DRAW" else 0.0


def train_step(net: RiftboundNet, optimizer, batch: list[dict],
               device: Optional[torch.device] = None) -> dict:
    """One gradient step on a batch of examples. Loss = policy cross-entropy
    (visit target vs masked policy) + value MSE. Returns loss components."""
    device = device or next(net.parameters()).device
    states = torch.as_tensor(np.stack([e["state"] for e in batch]), device=device)
    target_p = torch.as_tensor(np.stack([e["policy"] for e in batch]), device=device)
    masks = torch.as_tensor(np.stack([e["mask"] for e in batch]), device=device)
    target_v = torch.as_tensor(np.asarray([e["z"] for e in batch], dtype=np.float32),
                               device=device).unsqueeze(1)

    net.train()
    logits, value = net(states)
    logp = masked_log_softmax(logits, masks)
    policy_loss = -(target_p * logp).sum(dim=1).mean()
    value_loss = F.mse_loss(value, target_v)
    loss = policy_loss + value_loss

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    return {"loss": float(loss.item()),
            "policy_loss": float(policy_loss.item()),
            "value_loss": float(value_loss.item())}


# --- worker processes ----------------------------------------------------------

_WORKER: dict = {"version": None, "net": None}


def _worker_init() -> None:
    from riftbound.compute import be_gentle
    be_gentle()
    torch.set_num_threads(1)
    warnings.filterwarnings("ignore")


def _worker_net(path: str, version: int) -> RiftboundNet:
    """The net of this iteration, read once per iteration per worker."""
    from riftbound.ai.net import load_checkpoint
    if _WORKER["version"] != version:
        _WORKER["net"] = load_checkpoint(path, device=torch.device("cpu"))
        _WORKER["version"] = version
    return _WORKER["net"]


def _selfplay_task(task) -> list[dict]:
    path, version, deck_a, deck_b, seed, iterations, max_turns, rest = task
    net = _worker_net(path, version)
    examples = play_selfplay_game(net, deck_a, deck_b, seed=seed, iterations=iterations,
                                  max_turns=max_turns, explore=True)
    if rest:
        time.sleep(rest)
    return examples


def _eval_task(task) -> tuple[str, float]:
    path, version, deck_net, deck_opp, seed, iterations, net_seat, max_turns, opponent = task
    net = _worker_net(path, version)
    return opponent, play_eval_game(net, deck_net, deck_opp, seed=seed, iterations=iterations,
                                    net_seat=net_seat, opponent=opponent, max_turns=max_turns)


# --- the loop ------------------------------------------------------------------

def train(net: RiftboundNet, decks: Sequence[Path], *, iterations: int = 20,
          games_per_iter: int = 16, mcts_iters: int = 100, train_steps: int = 0,
          batch_size: int = 128, lr: float = 1e-3, buffer_size: int = 50000,
          checkpoint: Optional[Path] = None, log_path: Optional[Path] = None,
          start_iteration: int = 0, seed: int = 0, workers: Optional[int] = None,
          eval_every: int = 5, eval_games: int = 20,
          eval_vs: Sequence[str] = ("simple_trade", "random"), max_turns: int = 40,
          pause: float = 10.0, rest: float = 0.0, device: Optional[torch.device] = None,
          log=print) -> RiftboundNet:
    """Self-play → train, `iterations` times, over a pool of decks (each game
    two decks drawn from `decks`, mirrors included). `workers`: processes for
    the games (None: riftbound.compute.default_workers(); 0: in this process).
    `train_steps` gradient steps per iteration (0: enough for each new example
    to be seen about twice). Every `eval_every` iterations the net plays
    `eval_games` games against each agent of `eval_vs` (simple_trade, and
    random as a sanity check), seats alternating. `pause`
    seconds between iterations and `rest` after each game let the machine
    breathe. Saves `checkpoint` and appends a JSON line per iteration to
    `log_path`."""
    from multiprocessing import Pool

    from riftbound.ai.net import save_checkpoint
    from riftbound.compute import be_gentle, default_workers

    decks = [Path(d) for d in decks]
    workers = default_workers() if workers is None else workers
    device = device or (torch.device("cpu") if workers else default_device())
    if workers:
        be_gentle()                   # the trainer too: low priority, one thread
    net.to(device)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    buffer: deque = deque(maxlen=buffer_size)
    rng = random.Random(seed)
    tmp = None
    if checkpoint is None:
        tmp = tempfile.TemporaryDirectory(prefix="rbsim_train_")
    weights = Path(checkpoint) if checkpoint is not None else Path(tmp.name) / "net.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    pool = Pool(workers, initializer=_worker_init) if workers else None

    def run(fn, tasks):
        if pool is None:
            return [fn(t) for t in tasks]
        return list(pool.imap_unordered(fn, tasks))

    try:
        for it in range(start_iteration, start_iteration + iterations):
            t0 = time.time()
            save_checkpoint(net.to("cpu"), weights)
            net.to(device)
            tasks = []
            for _ in range(games_per_iter):
                tasks.append((str(weights), it, rng.choice(decks), rng.choice(decks),
                              rng.randrange(1 << 30), mcts_iters, max_turns, rest))
            new = 0
            for examples in run(_selfplay_task, tasks):
                buffer.extend(examples)
                new += len(examples)
            stats = {"loss": float("nan"), "policy_loss": float("nan"), "value_loss": float("nan")}
            if len(buffer) >= batch_size:
                # 0 = auto: each new example is seen about twice.
                n_steps = train_steps or max(1, 2 * new // batch_size)
                steps = [train_step(net, opt, random.sample(buffer, batch_size), device=device)
                         for _ in range(n_steps)]
                stats = {k: mean(s[k] for s in steps) for k in stats}
            record = {"iteration": it + 1, "games": games_per_iter, "examples": new,
                      "buffer": len(buffer), **stats}
            if eval_every and (it + 1) % eval_every == 0 and eval_games:
                save_checkpoint(net.to("cpu"), weights)
                net.to(device)
                etasks = [(str(weights), it + 0.5, rng.choice(decks), rng.choice(decks),
                           rng.randrange(1 << 30), mcts_iters, "A" if g % 2 == 0 else "B",
                           max_turns, opponent)
                          for opponent in eval_vs for g in range(eval_games)]
                scores: dict = {}
                for opponent, score in run(_eval_task, etasks):
                    scores.setdefault(opponent, []).append(score)
                for opponent, xs in scores.items():
                    record[f"vs_{opponent}"] = mean(xs)
            record["seconds"] = round(time.time() - t0, 1)
            if checkpoint is not None:
                save_checkpoint(net.to("cpu"), checkpoint)
                net.to(device)
            if log_path is not None:
                with open(log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
            vs = "".join(f" {k}={v:.2f}" for k, v in record.items() if k.startswith("vs_"))
            log(f"[iter {it + 1}] examples+={new} buffer={len(buffer)} loss={stats['loss']:.4f} "
                f"(policy {stats['policy_loss']:.3f}, value {stats['value_loss']:.3f}){vs} "
                f"{record['seconds']}s")
            # A file named STOP next to the checkpoint ends the run here, saved.
            if checkpoint is not None and (Path(checkpoint).parent / "STOP").exists():
                log(f"STOP file found: stopping after iteration {it + 1}")
                break
            if pool is not None and pause:
                time.sleep(pause)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
        if tmp is not None:
            tmp.cleanup()
    return net


def run_training(net: RiftboundNet, deck_a: Path, deck_b: Path, *,
                 iterations: int = 5, games_per_iter: int = 4, mcts_iters: int = 100,
                 train_steps: int = 32, batch_size: int = 64, lr: float = 1e-3,
                 buffer_size: int = 20000, checkpoint: Optional[Path] = None,
                 seed: int = 0, device: Optional[torch.device] = None,
                 log=print) -> RiftboundNet:
    """`train` in this process over two decks, without the evaluation games
    (the original small loop; tests and quick checks)."""
    return train(net, [deck_a, deck_b], iterations=iterations, games_per_iter=games_per_iter,
                 mcts_iters=mcts_iters, train_steps=train_steps, batch_size=batch_size, lr=lr,
                 buffer_size=buffer_size, checkpoint=checkpoint, seed=seed, workers=0,
                 eval_every=0, pause=0.0, device=device, log=log)
