"""RiftboundNet — the AlphaZero-style policy + value network (RL Chunk 2).

A dual-head MLP over the fixed encoding from ``encoding.py``:

    encode_observation(obs)  ->  [OBS_DIM] float32
        |
    trunk (MLP)  ->  policy head [ACTION_DIM] logits   (masked by legal_mask)
                 \-> value head  [1] in (-1, 1)         (expected game result)

Requires PyTorch, which is the optional ``rl`` extra (``uv sync --extra rl``) —
kept out of the core engine so the light install stays torch-free. Import this
module only in the RL/training path. It is **CUDA-aware**: ``default_device()``
picks the GPU when available so the same code runs on a laptop CPU or a rented GPU
box unchanged.

The network reads its input/output sizes from ``encoding.OBS_DIM`` /
``encoding.ACTION_DIM`` so the two stay in lockstep.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from riftbound.ai.encoding import ACTION_DIM, OBS_DIM

_NEG_INF = -1e9  # logit for illegal actions before softmax


def default_device() -> "torch.device":
    """CUDA if available (rented GPU box), else CPU (laptop). No code change needed
    between the two."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


class RiftboundNet(nn.Module):
    """Dual-head MLP: shared trunk → (policy logits, scalar value)."""

    def __init__(self, obs_dim: int = OBS_DIM, action_dim: int = ACTION_DIM,
                 hidden: tuple[int, ...] = (512, 256)):
        super().__init__()
        self.obs_dim = obs_dim
        self.action_dim = action_dim

        layers: list[nn.Module] = []
        prev = obs_dim
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.LayerNorm(h), nn.ReLU()]
            prev = h
        self.trunk = nn.Sequential(*layers)
        self.policy_head = nn.Linear(prev, action_dim)
        self.value_head = nn.Linear(prev, 1)

    def forward(self, x: "torch.Tensor") -> tuple["torch.Tensor", "torch.Tensor"]:
        """x: [B, OBS_DIM] → (policy_logits [B, ACTION_DIM], value [B, 1] in (-1,1))."""
        z = self.trunk(x)
        policy_logits = self.policy_head(z)
        value = torch.tanh(self.value_head(z))
        return policy_logits, value


def masked_log_softmax(logits: "torch.Tensor", mask: "torch.Tensor") -> "torch.Tensor":
    """Log-probabilities over actions with illegal slots driven to ~0 probability.
    ``mask`` is a boolean/0-1 tensor broadcastable to ``logits`` (True = legal)."""
    neg = torch.full_like(logits, _NEG_INF)
    masked = torch.where(mask.bool(), logits, neg)
    return F.log_softmax(masked, dim=-1)


@torch.no_grad()
def predict(net: RiftboundNet, obs_vec: np.ndarray, legal_mask: np.ndarray,
            device: "Optional[torch.device]" = None) -> tuple[np.ndarray, float]:
    """Single-position inference. Returns (probs[ACTION_DIM] with illegal slots at
    0.0 and legal slots summing to 1, value in (-1,1)). Convenience for search/agents;
    handles device placement and eval mode."""
    device = device or next(net.parameters()).device
    net.eval()
    x = torch.as_tensor(np.asarray(obs_vec, dtype=np.float32), device=device).unsqueeze(0)
    m = torch.as_tensor(np.asarray(legal_mask), device=device).unsqueeze(0)
    logits, value = net(x)
    if m.any():
        logp = masked_log_softmax(logits, m)
        probs = logp.exp().squeeze(0).cpu().numpy()
    else:  # no legal action encodable (defensive) → uniform over nothing
        probs = np.zeros(net.action_dim, dtype=np.float32)
    return probs.astype(np.float32), float(value.squeeze().item())


def save_checkpoint(net: RiftboundNet, path) -> None:
    """Persist weights + shape so a training run can resume / a box can reload."""
    torch.save({"state_dict": net.state_dict(),
                "obs_dim": net.obs_dim, "action_dim": net.action_dim}, path)


def load_checkpoint(path, device: "Optional[torch.device]" = None) -> RiftboundNet:
    """Rebuild a net from a checkpoint and move it to ``device`` (default: auto)."""
    device = device or default_device()
    ckpt = torch.load(path, map_location=device)
    net = RiftboundNet(obs_dim=ckpt["obs_dim"], action_dim=ckpt["action_dim"])
    net.load_state_dict(ckpt["state_dict"])
    return net.to(device)
