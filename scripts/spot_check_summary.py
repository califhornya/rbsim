#!/usr/bin/env python
"""Aggregate the human-filled verdicts in scripts/spot_check_results.md.

Reads each card block (the `### name (set, category)` header and its
`**Verdict:** <CODE>` line), tallies verdicts overall and per category, and
prints TWO rates plus a recommendation:
  - Parser accuracy = OK+MINOR+ENGINE_BLOCKED — grades the PARSER. Drives the gate:
      >= 80%  → PROSEGUI (parser quality acceptable, continue with B1)
      otherwise → RIPARSARE (reinforce the prompt with few-shot examples)
  - Sim-ready       = OK+MINOR — how many cards the ENGINE actually executes today.
      The gap between the two is the engine-coverage backlog, not a parser problem.

ENGINE_BLOCKED means the parser's reading is correct/reasonable and the only gap
is a mechanic the engine can't represent — so it counts toward parser accuracy
but NOT toward sim-ready.

Run this ONLY after a human has replaced the `⬜ TODO` placeholders with verdict
codes. Cards still marked TODO are reported as un-reviewed and excluded from the
rate.

Usage:
  uv run python scripts/spot_check_summary.py
  uv run python scripts/spot_check_summary.py --path scripts/spot_check_round2.md
"""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent / "spot_check_results.md"
# Parser did well: correct, mostly-correct, or blocked only by engine coverage.
PARSER_GOOD = {"OK", "MINOR", "ENGINE_BLOCKED"}
# Cards the engine actually runs correctly today.
SIM_READY = {"OK", "MINOR"}
# Codes ordered "longest first" so we match e.g. MISSING_CONDITION before MINOR
# inside combined annotations like "Minor, MISSING_TRIGGER ...". The first match
# in the verdict line wins — that's the human's primary judgement. ENGINE_BLOCKED
# is listed before the WRONG_*/MISSING_* codes so it wins when both appear.
CODES = [
    "ENGINE_BLOCKED",
    "MISSING_CONDITION", "MISSING_EFFECT",
    "PHANTOM_EFFECT", "UNCERTAIN",
    "WRONG_TRIGGER", "WRONG_TARGET", "WRONG_AMOUNT", "WRONG_FILTER",
    "MINOR", "OK", "WRONG",
]
# Aliases the human used in practice but aren't in the canonical taxonomy.
ALIASES = {
    "MISSING_TRIGGER": "WRONG_TRIGGER",
    "MISSING_TIMING": "MISSING_EFFECT",
    "MISSING_KEYWORD": "MISSING_EFFECT",
    "WRONG": "MISSING_EFFECT",
}
HEADER_RE = re.compile(r"^###\s+(.*?)\s+\(([^,]+),\s*([^)]+)\)\s*$")
VERDICT_RE = re.compile(r"^\*\*Verdict:\*\*\s*(.+?)\s*$")
# Treat the literal "TODO" placeholder and the unfilled checkbox glyph as
# not-yet-reviewed.
_TODO_RE = re.compile(r"\bTODO\b|⬜", re.IGNORECASE)


def parse_results(text: str):
    """Yield (name, set, category, verdict) per card block."""
    cur = None
    for line in text.splitlines():
        h = HEADER_RE.match(line)
        if h:
            if cur:
                yield cur
            cur = {"name": h.group(1), "set": h.group(2).strip(),
                   "category": h.group(3).strip(), "verdict": None}
            continue
        if cur and cur["verdict"] is None:
            v = VERDICT_RE.match(line)
            if v:
                token = v.group(1).strip()
                # Blank verdict or TODO placeholder → not reviewed.
                if not token or _TODO_RE.search(token):
                    continue
                up = token.upper()
                # Pick the first canonical code we find. Aliases collapse to a
                # canonical bucket so we still get a usable rate.
                code = next((c for c in CODES if c in up), None)
                if code is None:
                    for alias, canonical in ALIASES.items():
                        if alias in up:
                            code = canonical
                            break
                cur["verdict"] = code  # None if still unrecognized
    if cur:
        yield cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, default=RESULTS_PATH,
                    help="Results markdown to grade (default: scripts/spot_check_results.md)")
    args = ap.parse_args()
    results_path = args.path

    if not results_path.exists():
        print(f"ERROR: {results_path} not found. Run scripts/spot_check.py first.")
        return 2
    rows = list(parse_results(results_path.read_text(encoding="utf-8")))
    total = len(rows)
    reviewed = [r for r in rows if r["verdict"] in CODES]
    todo = total - len(reviewed)

    overall = Counter(r["verdict"] for r in reviewed)
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for r in reviewed:
        by_cat[r["category"]][r["verdict"]] += 1

    print(f"# Spot-check summary\n")
    print(f"Cards in sample: {total}  |  reviewed: {len(reviewed)}  |  still TODO: {todo}\n")

    if not reviewed:
        print("No verdicts filled in yet — nothing to aggregate.")
        return 0

    n = len(reviewed)
    print("## Overall verdicts")
    for code, _ in sorted(overall.items(), key=lambda kv: -kv[1]):
        print(f"  {code:<18} {overall[code]}")

    parser_good = sum(overall[c] for c in PARSER_GOOD)
    sim_good = sum(overall[c] for c in SIM_READY)
    parser_rate = 100.0 * parser_good / n
    sim_rate = 100.0 * sim_good / n
    engine_blocked = overall.get("ENGINE_BLOCKED", 0)
    print(f"\nParser accuracy (OK+MINOR+ENGINE_BLOCKED): {parser_good}/{n} = {parser_rate:.1f}%  <- gate")
    print(f"Sim-ready       (OK+MINOR)               : {sim_good}/{n} = {sim_rate:.1f}%")
    if engine_blocked:
        print(f"  ({engine_blocked} card(s) ENGINE_BLOCKED — parser fine, engine can't run it yet "
              f"= the coverage gap, not a parser failure)")
    print()

    print("## Per category (parser accuracy | sim-ready)")
    print(f"  {'category':<14} {'parser':>9} {'sim':>9} {'total':>6}")
    for cat in sorted(by_cat):
        c = by_cat[cat]
        cpar = sum(c[g] for g in PARSER_GOOD)
        csim = sum(c[g] for g in SIM_READY)
        ctot = sum(c.values())
        prate = 100.0 * cpar / ctot if ctot else 0.0
        srate = 100.0 * csim / ctot if ctot else 0.0
        print(f"  {cat:<14} {prate:>8.1f}% {srate:>8.1f}% {ctot:>6}")

    print()
    if parser_rate >= 80.0:
        print(f"RECOMMENDATION: PROSEGUI — parser accuracy acceptable ({parser_rate:.1f}% >= 80%). "
              "Proceed to B1.")
    else:
        print(f"RECOMMENDATION: RIPARSARE — parser accuracy below 80% ({parser_rate:.1f}%). Reinforce "
              "the system prompt with few-shot examples (one per dominant WRONG_*/MISSING_* bucket) "
              "before parsing more cards. (ENGINE_BLOCKED cards are NOT the parser's fault — don't "
              "re-parse for those.)")
    if todo:
        print(f"\nNote: {todo} card(s) still marked TODO — fill them in for a complete rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
