"""F0 (porting Rust): dove va il tempo di una partita di raccolta PPO.

Gioca, in un solo processo e un thread torch, le stesse partite di self-play
EK di `scripts/ppo.py` (stessa `collect.play`, stessi semi di allenamento,
pesi iniziali dal seme come `ppo.py --seme S`, oppure `--init ckpt`) e
attribuisce il tempo, in modo esclusivo (un figlio non conta nel padre), a:
  legali       legality.legal_actions
  osservazione Observation.from_state + encode_observation
  descrittori  features.describe_action / describe_choice / describe_mulligan
  rete         il forward del PPONet (con log_softmax e campionamento: resto)
  gae          collect.gae
  motore       tutto il resto (GameLoop, effetti, euristiche, copie)
Non tocca il motore: avvolge le funzioni nei moduli che le usano.

  python scripts/rust/bench_ppo_split.py --partite 64 --seme 1 [--init ckpt] [--out file.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le verifiche di parità con Python fissano le regole storiche (decisione del 25/11).
os.environ["RBSIM_REGOLE"] = "6427b90"
sys.path.insert(0, str(ROOT))

TRAIN_SEED0 = 1_000_000


class Timer:
    """Exclusive timing by category over nested wrapped calls."""

    def __init__(self):
        self.tot: dict[str, float] = {}
        self.calls: dict[str, int] = {}
        self.stack: list[list] = []        # [category, start, child_time]

    def wrap(self, cat: str, fn):
        def wrapped(*a, **kw):
            t = time.perf_counter()
            self.stack.append([cat, t, 0.0])
            try:
                return fn(*a, **kw)
            finally:
                c, t0, child = self.stack.pop()
                el = time.perf_counter() - t0
                self.tot[c] = self.tot.get(c, 0.0) + el - child
                self.calls[c] = self.calls.get(c, 0) + 1
                if self.stack:
                    self.stack[-1][2] += el
        return wrapped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partite", type=int, default=64)
    ap.add_argument("--seme", type=int, default=1)
    ap.add_argument("--init", default=None)
    ap.add_argument("--primo", type=int, default=0, help="indice della prima partita (seme = 1e6 + seme*1e7 + i)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import torch
    torch.set_num_threads(1)
    from riftbound.ai.ppo import agent as AG
    from riftbound.ai.ppo import collect as C
    from riftbound.ai.ppo import features as F
    from riftbound.ai.ppo.model import PPONet, load
    from riftbound.core import decisions as D

    torch.manual_seed(args.seme)
    net = (load(args.init) if args.init else PPONet()).eval()
    wsha = hashlib.sha256(b"".join(t.detach().cpu().numpy().tobytes() for t in net.state_dict().values())).hexdigest()[:16]

    T = Timer()
    AG.legal_actions = T.wrap("legali", AG.legal_actions)
    AG.encode_observation = T.wrap("osservazione", AG.encode_observation)
    D.Observation.from_state = classmethod(T.wrap("osservazione", D.Observation.from_state.__func__))
    for name in ("describe_action", "describe_choice", "describe_mulligan"):
        setattr(F, name, T.wrap("descrittori", getattr(F, name)))
    C.gae = T.wrap("gae", C.gae)

    class TimedNet(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner
            self.fwd = T.wrap("rete", inner.__call__)

        def __call__(self, *a, **kw):
            return self.fwd(*a, **kw)

    tnet = TimedNet(net)
    turns, decisions, per_game = 0, 0, []
    total0 = time.perf_counter()
    for i in range(args.primo, args.primo + args.partite):
        seed = TRAIN_SEED0 + args.seme * 10_000_000 + i
        starter = "a" if i % 2 == 0 else "b"
        t = time.perf_counter()
        g = T.wrap("partita", C.play)(seed, {"A": tnet, "B": tnet}, {"A": True, "B": True}, sample=True,
                                       starter=starter)
        for s, rs in g["records"].items():
            if rs:
                C.gae(rs, g["z"][s], gamma=1.0, lam=0.98)
                decisions += len(rs)
        per_game.append(time.perf_counter() - t)
        turns += g["turns"]
    total = time.perf_counter() - total0
    T.tot["motore"] = T.tot.pop("partita", 0.0)
    out = {
        "cosa": "bench_ppo_split", "macchina": platform.node(), "cpu": platform.processor() or platform.machine(),
        "python": sys.version.split()[0], "torch": torch.__version__, "thread_torch": torch.get_num_threads(),
        "processi": 1, "mazzi": "EK", "seme": args.seme, "pesi": args.init or f"PPONet() dal seme {args.seme}",
        "pesi_sha256_16": wsha, "partite": args.partite, "primo": args.primo,
        "totale_s": round(total, 3), "ms_a_partita": round(1000 * total / args.partite, 2),
        "partite_ora_un_core": round(3600 * args.partite / total),
        "decisioni_registrate": decisions, "turni_medi": round(turns / args.partite, 2),
        "quote": {k: round(v / total, 4) for k, v in sorted(T.tot.items(), key=lambda kv: -kv[1])},
        "secondi": {k: round(v, 3) for k, v in T.tot.items()},
        "chiamate": T.calls,
    }
    print(json.dumps(out, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
