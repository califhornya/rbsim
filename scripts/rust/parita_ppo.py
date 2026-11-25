"""Parità della raccolta PPO Python / Rust (porting, F5): la stessa partita
(seme, rete, posti) giocata da collect.play (motore Python) e da
collect_rs.play (motore Rust, rete in Python) deve dare gli stessi esempi
bit per bit: x, q, src, ctx, otype, ocards, ofeats, a, logp, v, seat, turn;
e lo stesso esito, gli stessi turni, gli stessi conteggi. Si ferma al primo
esempio diverso e dice quale campo.

  python scripts/rust/parita_ppo.py --semi 1-20 [--avversario simple_trade] [--init ckpt.pt]
  python scripts/rust/parita_ppo.py --semi 1-20 --matchup ER --posti
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
import os  # noqa: E402
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))

FIELDS = ("x", "q", "src", "ctx", "otype", "ocards", "ofeats", "a", "logp", "v", "seat", "turn")


def _same(a, b) -> bool:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a), np.asarray(b)
        return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
    return a == b


def first_record_difference(py: dict, rs: dict):
    for seat in ("A", "B"):
        ra, rb = py["records"][seat], rs["records"][seat]
        for i, (x, y) in enumerate(zip(ra, rb)):
            for f in FIELDS:
                if not _same(x[f], y[f]):
                    detail = None
                    if isinstance(x[f], np.ndarray) and np.asarray(x[f]).shape == np.asarray(y[f]).shape:
                        diff = np.argwhere(np.asarray(x[f]) != np.asarray(y[f]))
                        detail = {"posizioni": diff[:8].tolist(),
                                  "python": np.asarray(x[f])[tuple(diff[:8].T)].tolist(),
                                  "rust": np.asarray(y[f])[tuple(diff[:8].T)].tolist()}
                    return {"posto": seat, "esempio": i, "campo": f, "q": x["q"], "turno": x["turn"],
                            "dettaglio": detail if detail else (str(x[f])[:200], str(y[f])[:200])}
        if len(ra) != len(rb):
            return {"posto": seat, "esempi": [len(ra), len(rb)]}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", nargs="+", required=True)
    ap.add_argument("--avversario", default=None, help="simple_trade | random: rete solo in A")
    ap.add_argument("--seme-rete", type=int, default=1)
    ap.add_argument("--init", default=None, help="checkpoint .pt (pesi della rete)")
    ap.add_argument("--greedy", action="store_true")
    ap.add_argument("--matchup", default="EK", help="lettere di riftbound/rs/mazzi.py: il primo mazzo in A (EK, ER, KR; minuscola = con la sideboard: Er)")
    ap.add_argument("--posti", action="store_true", help="anche col matchup rovesciato (i mazzi ai due posti)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo import collect
    from riftbound.rs.mazzi import decks
    from riftbound.ai.ppo.model import PPONet
    from riftbound.rs import collect_rs
    torch.manual_seed(args.seme_rete)
    net = PPONet().eval()
    if args.init:
        from riftbound.ai.ppo.model import load
        net = load(args.init).eval()
    seeds = []
    for s in args.semi:
        a, _, b = s.partition("-")
        seeds += list(range(int(a), int(b or a) + 1))
    nets = {"A": net, "B": None if args.avversario else net}
    learners = {"A": True, "B": not args.avversario}
    rows, ok = [], 0
    mus = [args.matchup] + ([args.matchup[::-1]] if args.posti and args.matchup[0] != args.matchup[1] else [])
    for seed, mu in [(s, m) for s in seeds for m in mus]:
        mazzi = dict(zip(("deck_a", "deck_b"), decks(mu)))
        t0 = time.perf_counter()
        py = collect.play(seed, nets, learners, sample=not args.greedy, opponent=args.avversario, **mazzi)
        t1 = time.perf_counter()
        try:
            rs = collect_rs.play(seed, nets, learners, sample=not args.greedy, opponent=args.avversario, **mazzi)
            err = None
        except RuntimeError as e:
            rs, err = None, str(e)
        t2 = time.perf_counter()
        row = {"seme": seed, "matchup": mu, "python": [py["winner"], py["turns"], sum(map(len, py["records"].values()))],
               "t_py": round(t1 - t0, 3), "t_rs": round(t2 - t1, 3)}
        if err:
            row["errore_rust"] = err
        else:
            row["rust"] = [rs["winner"], rs["turns"], sum(map(len, rs["records"].values()))]
            d = first_record_difference(py, rs)
            if d is None and dict(py["counts"]) != dict(rs["counts"]):
                d = {"conteggi": [dict(py["counts"]), dict(rs["counts"])]}
            if d is None and (py["winner"], py["turns"]) != (rs["winner"], rs["turns"]):
                d = {"esito": [py["winner"], py["turns"], rs["winner"], rs["turns"]]}
            if d is not None:
                row["prima_differenza"] = d
        same = "prima_differenza" not in row and "errore_rust" not in row
        ok += same
        print(json.dumps(row, default=str)[:1500])
        rows.append(row)
    print(f"\n{ok}/{len(rows)} partite con esempi identici")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
