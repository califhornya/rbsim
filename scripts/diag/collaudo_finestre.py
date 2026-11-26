#!/usr/bin/env python
"""Collaudo di --finestre-candidato (arena_mazzi.py): una coppia a posti scambiati (candidato in A e poi in B) con
poche iterazioni; dalle diagnosi di ricerca (`search_finestre_diag`) verifica che le finestre simulate seguano il
candidato in entrambi i posti e mai l'altro lato. Esce con 1 se non è così.

  python scripts/diag/collaudo_finestre.py --ckpt CK [--mu ES] [--seed 109000] [--iterazioni 12] [--regole PROFILO]
(--ckpt omesso: una rete a pesi casuali, per il collaudo locale)."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def collauda(ckpt: str, mu: str = "ES", seed: int = 109_000, iterazioni: int = 12, regole: str | None = None) -> list[str]:
    """-> i problemi trovati (lista vuota = collaudo superato)."""
    from riftbound.rs import arena_rs
    if regole:
        os.environ["RBSIM_REGOLE"] = regole
    opz = {"iter_cand": iterazioni, "iter_opp": iterazioni, "probe_cand": True, "probe_opp": True,
           "val_cand": ["rimonta", 3.0, 0.2], "val_opp": ["rimonta", 3.0, 0.2], "fin_cand": True, "diag_finestre": True}
    problemi = []
    for seat in ("A", "B"):
        task = (seed, "a" if seed % 2 == 0 else "b", seat, "prior_ppo", ckpt, "prior_ppo", ckpt, mu, None, None, opz)
        d = arena_rs.game(task)[8]["finestre_diag"]
        cand, opp = d["cand"], d["opp"]
        print(f"candidato in {seat}: ricerche con finestre del candidato {len(cand)} "
              f"(giocate dei piloti {sum(t[3] for x in cand for c in x['children'] for t in c['tally'])}), "
              f"dell'avversario {len(opp)}")
        if not cand:
            problemi.append(f"candidato in {seat}: nessuna ricerca con finestre")
        if not all(x.get("finestre") for x in cand):
            problemi.append(f"candidato in {seat}: ricerche senza finestre")
        if opp:
            problemi.append(f"candidato in {seat}: l'avversario ha {len(opp)} ricerche con finestre")
        if not any(c["tally"] for x in cand for c in x["children"]):
            problemi.append(f"candidato in {seat}: nessuna giocata dei piloti registrata")
    return problemi


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--mu", default="ES")
    ap.add_argument("--seed", type=int, default=109_000)
    ap.add_argument("--iterazioni", type=int, default=12)
    ap.add_argument("--regole", default=None)
    a = ap.parse_args()
    ckpt = a.ckpt
    if ckpt is None:
        import torch
        from riftbound.ai.ppo.model import PPONet, save
        torch.manual_seed(1)
        ckpt = str(Path(tempfile.mkdtemp()) / "casuale.pt")
        save(PPONet(), ckpt)
    problemi = collauda(ckpt, a.mu, a.seed, a.iterazioni, a.regole)
    for p in problemi:
        print("PROBLEMA:", p)
    print("collaudo finestre: " + ("SUPERATO" if not problemi else "FALLITO"))
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
