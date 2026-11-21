"""The PPO network (21/11): the state as the current net encodes it (card rows
embedded and pooled by zone, dense features), a question context, and a score
for each option of the menu from its descriptor; a softmax over the menu. The
critic values the state and the question from the decider's side, before the
option is known."""
from __future__ import annotations

import torch
import torch.nn as nn

from riftbound.ai.encoding import (DENSE_DIM, MAX_TOKENS, N_CARD_IDS, N_TOKEN_FEATURES, N_ZONES,
                                   OBS_DIM, TOKEN_WIDTH)
from riftbound.ai.ppo.features import F_CTX, F_OPT, OPTION_TYPES, QUESTIONS

_NEG = -1e9


class PPONet(nn.Module):
    def __init__(self, hidden: int = 256, card_dim: int = 32, opt_dim: int = 128):
        super().__init__()
        self.hidden, self.card_dim, self.opt_dim = hidden, card_dim, opt_dim
        self.card_embed = nn.Embedding(N_CARD_IDS, card_dim, padding_idx=0)
        self.zone_embed = nn.Embedding(N_ZONES, card_dim)
        self.feature_proj = nn.Linear(N_TOKEN_FEATURES, card_dim)
        self.row_mlp = nn.Sequential(nn.ReLU(), nn.Linear(card_dim, card_dim), nn.ReLU())
        self.trunk = nn.Sequential(
            nn.Linear(DENSE_DIM + N_ZONES * card_dim, hidden), nn.LayerNorm(hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.LayerNorm(hidden), nn.ReLU())
        self.q_embed = nn.Embedding(len(QUESTIONS), 32)
        self.ctx = nn.Sequential(nn.Linear(hidden + 32 + card_dim + F_CTX, hidden), nn.ReLU())
        self.t_embed = nn.Embedding(len(OPTION_TYPES), 32)
        self.opt = nn.Sequential(nn.Linear(32 + 3 * card_dim + F_OPT, opt_dim), nn.ReLU(),
                                 nn.Linear(opt_dim, opt_dim), nn.ReLU())
        self.score = nn.Sequential(nn.Linear(hidden + opt_dim, opt_dim), nn.ReLU(), nn.Linear(opt_dim, 1))
        self.value = nn.Sequential(nn.Linear(hidden, 128), nn.ReLU(), nn.Linear(128, 1))

    def state(self, x: torch.Tensor) -> torch.Tensor:
        b = x.shape[0]
        rows = x[:, DENSE_DIM:].reshape(b, MAX_TOKENS, TOKEN_WIDTH)
        zone = rows[..., 0].round().long().clamp(0, N_ZONES - 1)
        card = rows[..., 1].round().long().clamp(0, N_CARD_IDS - 1)
        h = self.card_embed(card) + self.zone_embed(zone) + self.feature_proj(rows[..., 2:])
        h = self.row_mlp(h) * (card > 0).unsqueeze(-1).to(h.dtype)
        pooled = torch.zeros(b, N_ZONES, self.card_dim, device=x.device, dtype=h.dtype)
        pooled.scatter_add_(1, zone.unsqueeze(-1).expand(-1, -1, self.card_dim), h)
        return self.trunk(torch.cat([x[:, :DENSE_DIM], pooled.reshape(b, -1)], dim=1))

    def forward(self, x, q, src, ctx, otype, ocards, ofeats, omask):
        """x [B, OBS_DIM], q [B], src [B], ctx [B, F_CTX]; options padded to M:
        otype [B, M], ocards [B, M, 3], ofeats [B, M, F_OPT], omask [B, M] (True
        = a real option). -> (logits [B, M], value [B])."""
        z = self.state(x)
        h = self.ctx(torch.cat([z, self.q_embed(q), self.card_embed(src), ctx], dim=1))
        b, m = otype.shape
        o = self.opt(torch.cat([self.t_embed(otype), self.card_embed(ocards).reshape(b, m, -1), ofeats], dim=2))
        logits = self.score(torch.cat([h.unsqueeze(1).expand(-1, m, -1), o], dim=2)).squeeze(-1)
        logits = logits.masked_fill(~omask, _NEG)
        return logits, torch.tanh(self.value(h)).squeeze(-1)


def save(net: PPONet, path) -> None:
    torch.save({"state_dict": net.state_dict(), "hidden": net.hidden, "card_dim": net.card_dim,
                "opt_dim": net.opt_dim, "obs_dim": OBS_DIM}, path)


def load(path, device=None) -> PPONet:
    ck = torch.load(path, map_location=device or "cpu")
    if ck.get("obs_dim") != OBS_DIM:
        raise ValueError(f"rete per un'altra codifica dello stato ({ck.get('obs_dim')} != {OBS_DIM})")
    net = PPONet(hidden=ck["hidden"], card_dim=ck["card_dim"], opt_dim=ck["opt_dim"])
    net.load_state_dict(ck["state_dict"])
    return net
