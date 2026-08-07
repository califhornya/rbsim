"""Audit parsed EQUIP costs against the printed rules text (RECAP §6d).

For every card whose keywords contain EQUIP, re-derive the attach cost from the
printed `effect` text and compare with the parsed keyword:
- `EQUIP [N] ...`      → N (a bracketed number is the cost)
- `EQUIP [fury]` etc.  → count of bracketed domain/resource symbols (1 per symbol)
- bare `EQUIP` keyword → treated as 1 (engine default, like bare REPEAT)

Prints mismatches; exits 1 if any are found so it can run in CI.
Use --fix to rewrite the keywords in all_cards.json to the derived values.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CARDS_PATH = Path(__file__).resolve().parent.parent / "riftbound" / "data" / "cards" / "all_cards.json"

_EQUIP_TEXT = re.compile(r"\bEQUIP((?:\s*\[[^\]]+\])+)", re.IGNORECASE)
_BRACKET = re.compile(r"\[([^\]]+)\]")


def derive_cost(effect_text: str) -> int | None:
    """Cost implied by the printed text, or None if the text has no EQUIP clause."""
    m = _EQUIP_TEXT.search(effect_text or "")
    if not m:
        return None
    cost = 0
    for sym in _BRACKET.findall(m.group(1)):
        sym = sym.strip()
        cost += int(sym) if sym.isdigit() else 1
    return cost


def parsed_cost(keywords: list[str]) -> int | None:
    """Cost recorded in the parsed keywords, or None if EQUIP isn't present."""
    for kw in keywords or []:
        parts = kw.split()
        if parts and parts[0].upper() == "EQUIP":
            return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="Rewrite mismatched keywords in all_cards.json")
    args = ap.parse_args()

    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    mismatches = []
    for card in cards:
        kws = card.get("keywords") or []
        have = parsed_cost(kws)
        if have is None:
            continue
        want = derive_cost(card.get("effect", ""))
        if want is None:
            # QUICK-DRAW gear etc. — keyword present but no EQUIP clause in text.
            continue
        if have != want:
            mismatches.append((card["name"], have, want))
            if args.fix:
                card["keywords"] = [
                    f"EQUIP {want}" if k.split()[0].upper() == "EQUIP" else k
                    for k in kws
                ]

    if args.fix and mismatches:
        CARDS_PATH.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if mismatches:
        action = "FIXED" if args.fix else "MISMATCH"
        for name, have, want in mismatches:
            print(f"{action}: {name}: parsed EQUIP {have} vs printed {want}")
        print(f"{len(mismatches)} EQUIP mismatch(es).")
        return 0 if args.fix else 1
    print("EQUIP audit clean: all parsed costs match the printed text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
