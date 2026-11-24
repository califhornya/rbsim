"""L'arena su Rust (porting, tappa A): una partita del bot a mano
(HandwrittenAgent) o del bot coi prior PPO (PPOPriorAgent) sul motore Rust,
con la firma e il ritorno di scripts/diag/arena_bot._game.

La ricerca gira in Rust (rust/rbsim-core/src/search.rs); per il prior Rust
costruisce osservazione, descrittori del menu e contesto e Python fa solo il
forward e il softmax (`make_probs`), come PPOPriorAgent._evaluate. Perimetro:
i matchup che il motore Rust copre (oggi Evelynn-Kha'Zix, `COPERTI`).
"""
from __future__ import annotations

from pathlib import Path

REF_BUDGET = 0.4        # scripts/diag/arena_bot.REF_BUDGET
MAX_TURNS = 40          # scripts/bootstrap_net.MAX_TURNS
COPERTI = ("EK",)
_NETS: dict = {}


def make_probs(net):
    """PPOPriorAgent._evaluate's forward and softmax, on the arrays Rust builds."""
    import torch

    def probs(x, q, ctx, otype, ocards, ofeats):
        n = len(otype)
        with torch.no_grad():
            logits, _ = net(torch.as_tensor(x[None]), torch.tensor([q]), torch.tensor([0]),
                            torch.as_tensor(ctx[None]), torch.as_tensor(otype[None]), torch.as_tensor(ocards[None]),
                            torch.as_tensor(ofeats[None]), torch.ones(1, n, dtype=torch.bool))
            return torch.softmax(logits[0], dim=0).numpy()
    return probs


def _probs_for(path: str):
    if path not in _NETS:
        import torch
        from riftbound.ai.ppo.model import load
        torch.set_num_threads(1)
        _NETS[path] = make_probs(load(path).eval())
    return _NETS[path]


def coperto(mu: str) -> bool:
    """Whether the Rust engine plays this matchup (by the lists' content)."""
    from riftbound.ai.ppo.collect import DECK_OF, EVE, KHA
    from riftbound.provenienza import lista_sha
    ek = {lista_sha(EVE), lista_sha(KHA)}
    return {lista_sha(DECK_OF[mu[0]]), lista_sha(DECK_OF[mu[1]])} <= ek


def game(task):
    """arena_bot._game on Rust: task (seed, starter, cand_seat, name, ckpt,
    opp, opp_ckpt[, mu[, budget_cand, budget_opp]]); name/opp "prior_ppo"
    (the hand-written bot with that checkpoint's priors) or "mano"."""
    from riftbound.ai.ppo.collect import DECK_OF
    from riftbound.rs import rust_bridge as rb
    seed, starter, cand_seat, name, ckpt, opp, opp_ckpt = task[:7]
    mu = task[7] if len(task) > 7 else "EK"
    b_cand, b_opp = (task[8], task[9]) if len(task) > 9 else (None, None)
    if not coperto(mu):
        raise ValueError(f"matchup {mu}: non coperto dal motore Rust ({', '.join(COPERTI)})")
    g = rb.build(seed, Path(DECK_OF[mu[0]]), Path(DECK_OF[mu[1]]), starter, MAX_TURNS)
    for seat in ("A", "B"):
        kind, path, b = (name, ckpt, b_cand) if seat == cand_seat else (opp, opp_ckpt, b_opp)
        if kind not in ("prior_ppo", "mano"):
            raise ValueError(f"bot {kind}: su Rust solo prior_ppo e mano")
        probs = _probs_for(str(path)) if kind == "prior_ppo" else None
        g.set_search_agent(seat, 100, seed * 2 + (seat == "B"), b or REF_BUDGET, probs, False)
    g.set_side_chooser()
    winner, _turns = g.start()
    other = "B" if cand_seat == "A" else "A"
    s = 1.0 if winner == cand_seat else 0.5 if winner == "DRAW" else 0.0
    ci, ce, ct = g.search_stats(cand_seat)
    oi, oe, ot = g.search_stats(other)
    return (seed, starter, cand_seat, s, list(ci), list(oi), (ce, ct), (oe, ot), {})
