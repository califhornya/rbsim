#!/usr/bin/env python
"""Prova B, la prima misura (21/11, docs/PIANO_FORZA.md): quanto è veloce una
rete che gioca senza ricerca, e quante opzioni legali la codifica non sa
indicare.

Due agenti "solo rete" (RiftboundNet con pesi casuali: conta il tempo, non la
forza) giocano Evelynn contro Kha'Zix: nel turno principale, negli showdown e
nelle reazioni scelgono la mossa legale con la probabilità più alta; mulligan,
"you may", modi e scelte interne (bersagli...) restano a simple_trade e al
baseline, e si contano. Un processo, un thread di torch, CPU (o --device).

  uv run --extra rl python scripts/diag/rete_veloce.py --partite 40
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap_net as B  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partite", type=int, default=40)
    ap.add_argument("--hidden", type=int, nargs="+", default=[512, 256])
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    import numpy as np
    import torch
    from riftbound.ai.encoding import action_to_index, encode_observation, legal_mask
    from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
    from riftbound.ai.net import RiftboundNet, masked_log_softmax
    from riftbound.core import loop as L
    from riftbound.core.decisions import DecisionPoint, Observation
    from riftbound.core.game_factory import build_game
    from riftbound.core.legality import legal_actions

    torch.set_num_threads(1)
    torch.manual_seed(0)
    dev = torch.device(args.device)
    net = RiftboundNet(hidden=tuple(args.hidden)).to(dev).eval()
    c: Counter = Counter()
    t_net = [0.0]

    class NetOnly(SimpleTradeAgent):
        def _pick(self, point):
            side = self.player.name
            legal = legal_actions(self.loop, point, side)
            c["decisioni"] += 1
            if len(legal) < 2:
                return legal[0].to_engine() if legal else ("PASS", None, None)
            c["con scelta"] += 1
            n_bf = len(self.gs.battlefields)
            idx = [action_to_index(a, n_bf) for a in legal]
            c["opzioni"] += len(legal)
            c["opzioni senza indice"] += sum(i is None for i in idx)
            t0 = time.process_time()
            vec = encode_observation(Observation.from_state(self.gs, side))
            mask = legal_mask(legal, n_bf)
            with torch.no_grad():
                logits, _ = net(torch.as_tensor(vec[None], device=dev))
                p = masked_log_softmax(logits, torch.as_tensor(mask[None], device=dev)).exp()[0].cpu().numpy()
            t_net[0] += time.process_time() - t0
            best = max(range(len(legal)), key=lambda k: p[idx[k]] if idx[k] is not None else -1.0)
            return legal[best].to_engine()

        def decide_action(self, opponent, cards_played: int = 0):
            return self._pick(DecisionPoint.TURN_ACTION)

        def decide_showdown_action(self, opponent, bf_idx: int):
            return self._pick(DecisionPoint.SHOWDOWN_ACTION)

        def decide_reaction(self, opponent, chain):
            return self._pick(DecisionPoint.REACTION)

    choose = L.GameLoop.choose

    def counted(self, kind, side, options, pick, source=None):
        if len(options) > 1:
            c["scelte interne (al baseline)"] += 1
        return choose(self, kind, side, options, pick, source)
    L.GameLoop.choose = counted

    t0 = time.process_time()
    for s in range(args.partite):
        gs = build_game(game_seed=60_000 + s, deck_a_path=B.EVE, deck_b_path=B.KHA, ai_a=None, ai_b=None,
                        max_turns=B.MAX_TURNS, first_player="a" if s % 2 == 0 else "b")
        for seat in ("A", "B"):
            gs.get_player(seat).agent = NetOnly(gs.get_player(seat))
        L.GameLoop(gs).start()
    tot = time.process_time() - t0
    n = args.partite
    print(f"Rete {tuple(args.hidden)} su {args.device}, {n} partite: {tot:.1f} s di CPU, "
          f"{1000 * tot / n:.0f} ms a partita, {n / tot:.1f} partite/s per core")
    print(f"   decisioni {c['decisioni']} ({c['decisioni'] / n:.0f} a partita), con una scelta vera "
          f"{c['con scelta']}: {c['con scelta'] / tot:.0f} al secondo")
    print(f"   rete (osservazione, codifica, inferenza): {t_net[0]:.1f} s, {100 * t_net[0] / tot:.0f}% del tempo, "
          f"{1000 * t_net[0] / max(1, c['con scelta']):.2f} ms per decisione")
    print(f"   opzioni legali {c['opzioni']}, senza indice nella codifica {c['opzioni senza indice']}; "
          f"scelte interne lasciate al baseline {c['scelte interne (al baseline)']} "
          f"({c['scelte interne (al baseline)'] / n:.1f} a partita)")


if __name__ == "__main__":
    main()
