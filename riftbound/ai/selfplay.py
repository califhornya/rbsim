"""Self-play game generation + the training step/loop (RL Chunk 4).

Closes the AlphaZero loop: play games with the network-guided MCTS on BOTH seats
(sharing one net), record (state, MCTS visit policy, legal mask, player) at each
searched decision, label each with the game's outcome z from that player's seat,
then train the net to match the search's policy (cross-entropy) and the outcome
(value MSE). Iterate: the net gets stronger, so the search gets stronger, so the
next games are better — the agent improves every iteration.

Requires the `rl` extra (torch). Run headless on a rented GPU box via
`scripts/train_selfplay.py`.
"""

from __future__ import annotations

import random
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from riftbound.ai.net import RiftboundNet, default_device, masked_log_softmax
from riftbound.ai.net_mcts import NetGuidedMCTSAgent
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop


def play_selfplay_game(net: RiftboundNet, deck_a: Path, deck_b: Path, *,
                       seed: int = 0, iterations: int = 100, c_puct: float = 1.5,
                       max_turns: int = 40) -> list[dict]:
    """Play one self-play game; return training examples with value target ``z``
    (+1/-1/0) already filled from the outcome, per each example's seat."""
    examples: list = []
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b,
                    ai_a=None, ai_b=None, max_turns=max_turns)
    rng = random.Random(seed)
    for side, player in (("A", gs.A), ("B", gs.B)):
        agent = NetGuidedMCTSAgent(player, net, iterations=iterations, c_puct=c_puct,
                                   rng=random.Random(rng.randrange(1 << 30)))
        agent.record = examples
        player.agent = agent
    result = GameLoop(gs).start()
    for ex in examples:
        if result.winner == "DRAW":
            ex["z"] = 0.0
        else:
            ex["z"] = 1.0 if result.winner == ex["player"] else -1.0
    return examples


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


def run_training(net: RiftboundNet, deck_a: Path, deck_b: Path, *,
                 iterations: int = 5, games_per_iter: int = 4, mcts_iters: int = 100,
                 train_steps: int = 32, batch_size: int = 64, lr: float = 1e-3,
                 buffer_size: int = 20000, checkpoint: Optional[Path] = None,
                 seed: int = 0, device: Optional[torch.device] = None,
                 log=print) -> RiftboundNet:
    """Full self-play → train loop. Runs headless; CUDA-aware. Saves a checkpoint
    after each iteration when ``checkpoint`` is given."""
    from riftbound.ai.net import save_checkpoint
    device = device or default_device()
    net.to(device)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    buffer: deque = deque(maxlen=buffer_size)
    rng = random.Random(seed)

    for it in range(iterations):
        new = 0
        for _ in range(games_per_iter):
            ex = play_selfplay_game(net, deck_a, deck_b, seed=rng.randrange(1 << 30),
                                    iterations=mcts_iters)
            buffer.extend(ex)
            new += len(ex)
        stats = {"loss": float("nan")}
        if len(buffer) >= batch_size:
            for _ in range(train_steps):
                batch = random.sample(buffer, batch_size)
                stats = train_step(net, opt, batch, device=device)
        log(f"[iter {it + 1}/{iterations}] examples+={new} buffer={len(buffer)} "
            f"loss={stats['loss']:.4f}")
        if checkpoint is not None:
            save_checkpoint(net, checkpoint)
    return net
