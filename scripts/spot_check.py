#!/usr/bin/env python
"""Generate a stratified sample of parsed cards for MANUAL semantic review.

Picks 30 cards (fixed RNG seed for reproducibility) from those that already have
structured `effects[]`, stratified by set (proportional), category (>=3 per
category where available), and text complexity (>=10 with len(effect) > 120).
Writes one markdown block per card to scripts/spot_check_results.md with a blank
Verdict/Notes for a human to fill in.

This script makes NO API calls — the spot-check is explicitly manual. After a
human fills the verdicts, run scripts/spot_check_summary.py to aggregate.

Usage:
  uv run python scripts/spot_check.py
  uv run python scripts/spot_check.py --n 30 --seed 42
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import random

CARDS_PATH = Path(__file__).resolve().parent.parent / "riftbound" / "data" / "cards" / "all_cards.json"
OUT_PATH = Path(__file__).resolve().parent / "spot_check_results.md"
COMPLEX_LEN = 120
COMPLEX_QUOTA = 10
PER_CATEGORY = 3

TAXONOMY = [
    ("OK", "interpretazione corretta"),
    ("MINOR", "verb principale giusto ma manca una clausola secondaria"),
    ("ENGINE_BLOCKED", "la lettura del parser è corretta/ragionevole; l'unico buco "
                       "è una meccanica che il MOTORE non sa rappresentare (non è "
                       "colpa del parser). Conta come promosso per l'accuratezza del parser."),
    ("WRONG_TRIGGER", "verb giusto, trigger sbagliato"),
    ("WRONG_TARGET", "target sbagliato"),
    ("WRONG_AMOUNT", "quantità sbagliata / mancato amount_source"),
    ("WRONG_FILTER", "filtro mancante o sbagliato"),
    ("MISSING_EFFECT", "clausole intere ignorate (meccanica SUPPORTATA dal motore)"),
    ("PHANTOM_EFFECT", "effetto inventato non presente nel testo"),
    ("MISSING_CONDITION", "condition non riconosciuta (meccanica SUPPORTATA dal motore)"),
    ("UNCERTAIN", "il testo è genuinamente ambiguo"),
]


def _cid(card: dict) -> str:
    return card.get("card_id") or card.get("name") or ""


def _is_complex(card: dict) -> bool:
    return len(card.get("effect") or "") > COMPLEX_LEN


def select_sample(cards: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    pool = [c for c in cards if c.get("effects")]
    selected: list[dict] = []
    chosen: set[str] = set()

    def take(card: dict) -> None:
        cid = _cid(card)
        if cid not in chosen:
            selected.append(card)
            chosen.add(cid)

    # 1. Category coverage: up to PER_CATEGORY per category.
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in pool:
        by_cat[str(c.get("category"))].append(c)
    for cat in sorted(by_cat):
        lst = by_cat[cat][:]
        rng.shuffle(lst)
        for c in lst[:PER_CATEGORY]:
            if len(selected) < n:
                take(c)

    # 2. Complexity quota: ensure >= COMPLEX_QUOTA complex cards.
    complex_pool = [c for c in pool if _is_complex(c) and _cid(c) not in chosen]
    rng.shuffle(complex_pool)
    while sum(_is_complex(c) for c in selected) < COMPLEX_QUOTA and complex_pool:
        cand = complex_pool.pop()
        if len(selected) < n:
            take(cand)
        else:
            # Full but short on complex: swap out a non-complex pick.
            for i, s in enumerate(selected):
                if not _is_complex(s):
                    chosen.discard(_cid(s))
                    selected[i] = cand
                    chosen.add(_cid(cand))
                    break
            else:
                break

    # 3. Fill remaining slots; shuffling the whole pool keeps set mix proportional.
    remaining = [c for c in pool if _cid(c) not in chosen]
    rng.shuffle(remaining)
    while len(selected) < n and remaining:
        take(remaining.pop())

    return selected[:n]


def render(cards: list[dict]) -> str:
    out: list[str] = []
    out.append("# Spot-check — revisione semantica manuale\n")
    out.append(f"Campione di {len(cards)} carte (RNG seed fisso) dalle carte con "
               "`effects[]`. Compila **Verdict** per ciascuna con uno dei codici "
               "qui sotto, poi esegui `scripts/spot_check_summary.py`.\n")
    out.append("**Tassonomia verdict:**\n")
    for code, desc in TAXONOMY:
        out.append(f"- `{code}` — {desc}")
    out.append("\nDue tassi vengono calcolati da `spot_check_summary.py`:\n"
               "- **Parser accuracy** = OK+MINOR+ENGINE_BLOCKED (misura il parser). "
               "Soglia gate: ≥ 80% → PROSEGUI; altrimenti RIPARSARE.\n"
               "- **Sim-ready** = OK+MINOR (quante carte il motore esegue davvero oggi). "
               "Il divario con parser accuracy è il backlog di copertura del MOTORE, non un problema del parser.\n")
    out.append("---\n")

    for c in sorted(cards, key=lambda x: (str(x.get("category")), str(x.get("name")))):
        name = c.get("name")
        cset = c.get("set")
        cat = c.get("category")
        out.append(f"### {name} ({cset}, {cat})\n")
        out.append(f"**Raw effect:** {c.get('effect') or '(none)'}")
        if c.get("effect_equipped"):
            out.append(f"\n**Raw effect (equipped):** {c.get('effect_equipped')}")
        out.append("\n**Parsed effects:**\n")
        out.append("```json")
        out.append(json.dumps(c.get("effects") or [], ensure_ascii=False, indent=2))
        out.append("```\n")
        out.append(f"**Parsed keywords:** {c.get('keywords') or []}\n")
        out.append("**Verdict:** ⬜ TODO")
        out.append("**Notes:** \n")
        out.append("---\n")
    return "\n".join(out)


def _has_filled_verdicts(path: Path) -> bool:
    """True if the file already contains a non-TODO Verdict line — i.e. a human
    has spent time on it. We refuse to overwrite in that case so verdicts
    aren't lost; pass --force to override."""
    if not path.exists():
        return False
    import re as _re
    pat = _re.compile(r"^\*\*Verdict:\*\*\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if not m:
            continue
        token = m.group(1).strip()
        if token and "TODO" not in token.upper() and "⬜" not in token:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="Sample size")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (reproducibility)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite spot_check_results.md even if it already contains filled verdicts")
    args = ap.parse_args()

    if _has_filled_verdicts(OUT_PATH) and not args.force:
        print(f"REFUSING to overwrite {OUT_PATH} — it contains filled verdicts.",
              "Pass --force to overwrite, or move/rename the existing file first.",
              sep="\n")
        return 2

    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    parsed = [c for c in cards if c.get("effects")]
    sample = select_sample(cards, args.n, args.seed)

    OUT_PATH.write_text(render(sample), encoding="utf-8")
    complex_n = sum(_is_complex(c) for c in sample)
    cats = sorted({str(c.get("category")) for c in sample})
    print(f"Pool: {len(parsed)} cards with effects. Sampled {len(sample)}.")
    print(f"Categories covered: {', '.join(cats)}")
    print(f"Complex (>{COMPLEX_LEN} chars): {complex_n} (quota {COMPLEX_QUOTA}).")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
