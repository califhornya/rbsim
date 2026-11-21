"""The PPO update (21/11): clipped objective on the menus saved at collection
time, value loss on the GAE returns, an entropy bonus. Menus are padded to the
longest of the minibatch and masked."""
from __future__ import annotations

import numpy as np
import torch

from riftbound.ai.ppo.features import F_OPT


def tensors(recs: list, device="cpu") -> dict:
    n = len(recs)
    m = max(len(r["otype"]) for r in recs)
    otype = np.zeros((n, m), dtype=np.int64)
    ocards = np.zeros((n, m, 3), dtype=np.int64)
    ofeats = np.zeros((n, m, F_OPT), dtype=np.float32)
    omask = np.zeros((n, m), dtype=bool)
    for i, r in enumerate(recs):
        k = len(r["otype"])
        otype[i, :k], ocards[i, :k], ofeats[i, :k], omask[i, :k] = r["otype"], r["ocards"], r["ofeats"], True
    t = {
        "x": torch.as_tensor(np.stack([r["x"] for r in recs]).astype(np.float32)),
        "q": torch.as_tensor(np.array([r["q"] for r in recs], dtype=np.int64)),
        "src": torch.as_tensor(np.array([r["src"] for r in recs], dtype=np.int64)),
        "ctx": torch.as_tensor(np.stack([r["ctx"] for r in recs]).astype(np.float32)),
        "otype": torch.as_tensor(otype), "ocards": torch.as_tensor(ocards),
        "ofeats": torch.as_tensor(ofeats), "omask": torch.as_tensor(omask),
        "a": torch.as_tensor(np.array([r["a"] for r in recs], dtype=np.int64)),
        "logp": torch.as_tensor(np.array([r["logp"] for r in recs], dtype=np.float32)),
    }
    if "adv" in recs[0]:
        t["adv"] = torch.as_tensor(np.array([r["adv"] for r in recs], dtype=np.float32))
        t["ret"] = torch.as_tensor(np.array([r["ret"] for r in recs], dtype=np.float32))
    return {k: v.to(device) for k, v in t.items()}


def evaluate(net, t: dict, idx=None):
    """(log-probability of the action taken, value, entropy) for the rows idx."""
    sel = (lambda v: v) if idx is None else (lambda v: v[idx])
    logits, v = net(sel(t["x"]), sel(t["q"]), sel(t["src"]), sel(t["ctx"]), sel(t["otype"]),
                    sel(t["ocards"]), sel(t["ofeats"]), sel(t["omask"]))
    logp_all = torch.log_softmax(logits, dim=1)
    logp = logp_all.gather(1, sel(t["a"]).unsqueeze(1)).squeeze(1)
    p = logp_all.exp() * sel(t["omask"])
    ent = -(p * logp_all.masked_fill(~sel(t["omask"]), 0.0)).sum(1)
    return logp, v, ent


def update(net, opt, recs: list, epochs: int = 4, minibatch: int = 512, clip: float = 0.2,
           vf_coef: float = 0.5, ent_coef: float = 0.01, max_grad: float = 0.5, device="cpu") -> dict:
    t = tensors(recs, device)
    adv = t["adv"]
    t["adv"] = (adv - adv.mean()) / (adv.std() + 1e-8)
    n = len(recs)
    stats = {"kl": 0.0, "clipfrac": 0.0, "entropia": 0.0, "errore valore": 0.0, "passi": 0}
    net.train()
    for _ in range(epochs):
        perm = torch.randperm(n)
        for b in range(0, n, minibatch):
            idx = perm[b:b + minibatch].to(device)
            logp, v, ent = evaluate(net, t, idx)
            ratio = torch.exp(logp - t["logp"][idx])
            a = t["adv"][idx]
            pg = -torch.min(ratio * a, torch.clamp(ratio, 1 - clip, 1 + clip) * a).mean()
            vl = ((v - t["ret"][idx]) ** 2).mean()
            loss = pg + vf_coef * vl - ent_coef * ent.mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), max_grad)
            opt.step()
            with torch.no_grad():
                stats["kl"] += float((t["logp"][idx] - logp).mean())
                stats["clipfrac"] += float(((ratio - 1).abs() > clip).float().mean())
                stats["entropia"] += float(ent.mean())
                stats["errore valore"] += float(vl)
                stats["passi"] += 1
    net.eval()
    k = max(1, stats.pop("passi"))
    return {key: val / k for key, val in stats.items()}
