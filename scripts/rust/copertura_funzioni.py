"""Copertura per funzione (da un coverage.json): per ogni funzione dei moduli
del motore, istruzioni eseguite / totali, per guidare il porting.

  python scripts/rust/copertura_funzioni.py runs/rust_f3/coverage.json [--min 1] [--md out.md]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES = ["riftbound/core/loop.py", "riftbound/core/effects.py", "riftbound/core/legality.py",
           "riftbound/core/decisions.py", "riftbound/core/combat.py", "riftbound/core/battlefield.py",
           "riftbound/core/player.py", "riftbound/core/state.py", "riftbound/core/cards.py",
           "riftbound/core/game_factory.py", "riftbound/ai/encoding.py", "riftbound/ai/ppo/features.py",
           "riftbound/ai/heuristics/base_agent.py", "riftbound/ai/heuristics/simple_trade_agent.py",
           "riftbound/registry/cards_registry.py"]


def functions(path: Path):
    tree = ast.parse(path.read_text())
    out = []

    def visit(node, prefix=""):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((prefix + ch.name, ch.lineno, ch.end_lineno))
                visit(ch, prefix + ch.name + ".")
            elif isinstance(ch, ast.ClassDef):
                visit(ch, prefix + ch.name + ".")
    visit(tree)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cov")
    ap.add_argument("--min", type=int, default=1)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()
    cov = json.loads(Path(args.cov).read_text())["files"]
    lines = []
    tot_exec = tot_fun = 0
    for mod in MODULES:
        f = cov.get(mod)
        if f is None:
            continue
        executed = set(f["executed_lines"])
        missing = set(f["missing_lines"])
        rows = []
        for name, a, b in functions(ROOT / mod):
            ex = sum(1 for ln in executed if a < ln <= b)
            ms = sum(1 for ln in missing if a < ln <= b)
            if ex >= args.min:
                rows.append((name, a, b, ex, ms))
        # inner functions are counted in their parents too: report leaves only once (by span)
        tot_exec += len(executed)
        tot_fun += len(rows)
        lines.append(f"\n## {mod}: {len(executed)} istruzioni eseguite, {len(missing)} no; {len(rows)} funzioni toccate\n")
        lines.append("| funzione | righe | eseguite | non eseguite |\n|---|---|---|---|")
        for name, a, b, ex, ms in rows:
            lines.append(f"| `{name}` | {a}-{b} | {ex} | {ms} |")
    text = "\n".join(lines)
    if args.md:
        Path(args.md).write_text(text + "\n")
    print(f"funzioni toccate {tot_fun}, istruzioni eseguite {tot_exec}")


if __name__ == "__main__":
    main()
