"""Inventario EK per il porting (F3): le carte reali di Evelynn e Kha'Zix
(mazzo, sideboard, leggenda, campione, campi, token che creano), i loro
effetti (verbo, trigger, condizione, bersaglio, costo, parole chiave) e,
per ogni verbo, lo stato in Rust: un handler in rbsim-core/src/effects.rs,
un marcatore che il motore legge senza handler, o NON PORTATO (darebbe
NotPorted). Le esecuzioni di ogni handler si contano su un campione di
partite Python EK (simple_trade, random, PPO a pesi dal seme 1; i due
posti): le stesse partite che Rust gioca identiche.

  python scripts/rust/inventario.py [--partite 40] [--out docs/rust/INVENTARIO_EK.md]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def deck_cards(path: Path) -> dict:
    d = json.loads(path.read_text())
    out = {"leggenda": [d["legend"]], "campione": [d["champion"]],
           "campi": [b["name"] for b in d["battlefields"]],
           "mazzo": [c["name"] for c in d["cards"]], "sideboard": [c["name"] for c in d.get("sideboard", [])]}
    return out


def rust_verbs() -> set:
    """The verbs of the match arms of rbsim-core's run_effect."""
    src = (ROOT / "rust/rbsim-core/src/effects.rs").read_text()
    body = src[src.index("pub fn run_effect"):]
    body = body[:body.index("other =>")]
    arms = re.findall(r'^\s*((?:"[a-z_]+"\s*\|?\s*)+)=>', body, re.M)
    return {v for arm in arms for v in re.findall(r'"([a-z_]+)"', arm)}


def count_executions(n: int) -> Counter:
    """Handler calls over n games of each kind (both seats)."""
    import torch
    from riftbound.ai.ppo import collect
    from riftbound.ai.ppo.model import PPONet
    from riftbound.core import effects as E
    calls: Counter = Counter()
    for verb, fn in list(E.REGISTRY.items()):
        def wrapped(ctx, spec, _fn=fn, _v=verb):
            calls[_v] += 1
            return _fn(ctx, spec)
        E.REGISTRY[verb] = wrapped
    torch.manual_seed(1)
    torch.set_num_threads(1)
    net = PPONet().eval()
    for seed in range(1, n + 1):
        collect.play(seed, {"A": net, "B": net}, {})
        collect.play(seed, {"A": net, "B": None}, {}, opponent="simple_trade")
        collect.play(seed, {"A": None, "B": net}, {}, opponent="random")
    return calls


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partite", type=int, default=40, help="partite per tipo (self-play, contro simple_trade, contro random)")
    ap.add_argument("--out", default=str(ROOT / "docs/rust/INVENTARIO_EK.md"))
    args = ap.parse_args()
    from riftbound.ai.ppo.collect import EVE, KHA
    from riftbound.core import effects as E
    from riftbound.registry.cards_registry import CARD_REGISTRY
    decks = {"Evelynn": deck_cards(EVE), "Kha'Zix": deck_cards(KHA)}
    names: dict = {}
    for who, parts in decks.items():
        for part, cs in parts.items():
            for c in cs:
                names.setdefault(c, set()).add(f"{who} {part}")
    # Tokens and other cards the EK cards name in their effects.
    for c in list(names):
        for es in CARD_REGISTRY[c].effects:
            for v in (es.params or {}).values():
                if isinstance(v, str) and v in CARD_REGISTRY and v not in names:
                    names[v] = {f"creata da {c}"}
    rv = rust_verbs()
    calls = count_executions(args.partite)
    rows, verbs = [], {}
    for c in sorted(names):
        spec = CARD_REGISTRY[c]
        for es in spec.effects:
            cond = (es.condition or {}).get("type") if isinstance(es.condition, dict) else es.condition
            cost = ",".join(sorted(k for k, v in (es.cost or {}).items() if v)) if isinstance(es.cost, dict) else ""
            verbs.setdefault(es.effect, set()).add(c)
            rows.append((c, es.effect, es.trigger, es.timing or "", cond or "", es.target or "", cost))
    lines = ["# Inventario EK (porting Rust, F3)", "",
             f"Generato da `python scripts/rust/inventario.py --partite {args.partite}`. Esecuzioni: chiamate "
             f"degli handler Python su {3 * args.partite} partite EK (self-play PPO a pesi dal seme 1, PPO contro "
             "simple_trade, random contro PPO), le stesse che il motore Rust gioca identiche.", "",
             "## Carte", "", "| Carta | Dove | Tipo | Parole chiave |", "|---|---|---|---|"]
    for c in sorted(names):
        s = CARD_REGISTRY[c]
        lines.append(f"| {c} | {', '.join(sorted(names[c]))} | {getattr(s.category, 'name', s.category)} | "
                     f"{', '.join(s.keywords) or '—'} |")
    lines += ["", "## Verbi", "",
              "Stato in Rust: **handler** (rbsim-core `run_effect`), **marcatore** (nessun handler in Python: "
              "il motore lo legge dove serve, porting con la funzione che lo legge), **NON PORTATO** "
              "(handler Python senza traduzione: in Rust darebbe `NotPorted`).", "",
              "| Verbo | Stato Rust | Esecuzioni | Carte |", "|---|---|---|---|"]
    missing = []
    for v in sorted(verbs):
        if v in rv:
            state = "handler"
        elif v not in E.REGISTRY:
            state = "marcatore"
        else:
            state = "NON PORTATO"
            missing.append(v)
        lines.append(f"| {v} | {state} | {calls.get(v, 0)} | {', '.join(sorted(verbs[v]))} |")
    lines += ["", "## Effetti per carta", "",
              "| Carta | Verbo | Trigger | Tempo | Condizione | Bersaglio | Costo |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {' | '.join(str(x) for x in r)} |" for r in rows]
    lines += ["", "## Sintesi", "",
              f"- Carte: {len(names)}; effetti: {len(rows)}; verbi: {len(verbs)} "
              f"(handler Rust {sum(1 for v in verbs if v in rv)}, marcatori {sum(1 for v in verbs if v not in E.REGISTRY)}, "
              f"non portati {len(missing)}{': ' + ', '.join(missing) if missing else ''}).",
              f"- Verbi mai eseguiti nel campione: {', '.join(v for v in sorted(verbs) if v in E.REGISTRY and not calls.get(v)) or 'nessuno'}."]
    Path(args.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-3:]))


if __name__ == "__main__":
    main()
