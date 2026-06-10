#!/usr/bin/env python
"""Aggregate the human-filled verdicts in scripts/spot_check_results.md.

Reads each card block (the `### name (set, category)` header and its
`**Verdict:** <CODE>` line), tallies verdicts overall and per category, computes
the OK+MINOR acceptance rate, and prints a recommendation:
  - OK+MINOR >= 80%  → PROSEGUI (quality acceptable, continue with B1)
  - otherwise        → RIPARSARE (reinforce the prompt with few-shot examples)

Run this ONLY after a human has replaced the `⬜ TODO` placeholders with verdict
codes. Cards still marked TODO are reported as un-reviewed and excluded from the
rate.

Usage:
  uv run python scripts/spot_check_summary.py
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent / "spot_check_results.md"
GOOD = {"OK", "MINOR"}
# Codes ordered "longest first" so we match e.g. MISSING_CONDITION before MINOR
# inside combined annotations like "Minor, MISSING_TRIGGER ...". The first match
# in the verdict line wins — that's the human's primary judgement.
CODES = [
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
    if not RESULTS_PATH.exists():
        print(f"ERROR: {RESULTS_PATH} not found. Run scripts/spot_check.py first.")
        return 2
    rows = list(parse_results(RESULTS_PATH.read_text(encoding="utf-8")))
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

    print("## Overall verdicts")
    for code, _ in sorted(overall.items(), key=lambda kv: -kv[1]):
        print(f"  {code:<18} {overall[code]}")
    good = sum(overall[c] for c in GOOD)
    rate = 100.0 * good / len(reviewed)
    print(f"\nOK+MINOR: {good}/{len(reviewed)} = {rate:.1f}%\n")

    print("## Per category (OK+MINOR rate)")
    print(f"  {'category':<14} {'OK+MINOR':>8} {'total':>6} {'rate':>7}")
    for cat in sorted(by_cat):
        c = by_cat[cat]
        cgood = sum(c[g] for g in GOOD)
        ctot = sum(c.values())
        crate = 100.0 * cgood / ctot if ctot else 0.0
        print(f"  {cat:<14} {cgood:>8} {ctot:>6} {crate:>6.1f}%")

    print()
    if rate >= 80.0:
        print("RECOMMENDATION: PROSEGUI — quality acceptable (>=80%). Proceed to B1.")
    else:
        print("RECOMMENDATION: RIPARSARE — below 80%. Reinforce the system prompt with "
              "few-shot examples (one per dominant error bucket) before parsing more cards.")
    if todo:
        print(f"\nNote: {todo} card(s) still marked TODO — fill them in for a complete rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
