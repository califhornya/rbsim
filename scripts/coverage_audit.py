#!/usr/bin/env python
"""Engine coverage audit — the Stage-0 map.

For every card in the meta decks (and the whole corpus), classify whether the
engine actually models its printed ability, and if not, *why*. This turns the
vague "~40% of cards are inert" into a concrete, prioritized punch-list.

It reuses the existing single-source-of-truth vocabulary and handler table — no
new judgement of what "handled" means lives here:
- effects.REGISTRY + engine_vocab.NON_HANDLER_VERBS  → verbs the engine dispatches
- engine_vocab.KNOWN_TRIGGERS / KNOWN_CONDITIONS / SAFE_FALSE_CONDITIONS
- registry.load_deck_json / CARD_REGISTRY             → the cards to classify

Verdicts per card:
- LIVE    — has ≥1 effect and every effect's verb/trigger/condition is handled
            (or: a spell with no effects[] that still deals its printed damage).
- PARTIAL — has ≥1 handled effect AND ≥1 that the engine drops.
- INERT   — every effect is dropped, OR effects[] is empty but the card has
            printed ability text the parser never turned into effects.
- VANILLA — effects[] empty and no printed ability (pure stats/keywords). Fine.

Usage:
  uv run python scripts/coverage_audit.py            # writes COVERAGE_REPORT.md
  uv run python scripts/coverage_audit.py --decks-only
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import typer

from riftbound.core.effects import REGISTRY as EFFECT_REGISTRY
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec, load_deck_json
from riftbound.registry.engine_vocab import (
    KNOWN_CONDITIONS,
    KNOWN_TRIGGERS,
    NON_HANDLER_VERBS,
    SAFE_FALSE_CONDITIONS,
)

REPO = Path(__file__).resolve().parent.parent
DECK_DIR = REPO / "riftbound" / "data" / "decks"
REVIEW_FILE = REPO / "scripts" / "review_needed.txt"
OUT_FILE = REPO / "COVERAGE_REPORT.md"

_HANDLED_VERBS = set(EFFECT_REGISTRY) | set(NON_HANDLER_VERBS)
_PARENS = re.compile(r"\([^)]*\)")
_LOWER_PROSE = re.compile(r"[a-z]{3,}")

LIVE, PARTIAL, INERT, VANILLA = "LIVE", "PARTIAL", "INERT", "VANILLA"


def _printed_ability_text(spec: CardSpec) -> str:
    """Rules text with parenthetical reminders and the card's own keyword tokens
    removed. If lowercase prose survives, the card has an ability the parser was
    supposed to express."""
    text = str(spec.raw.get("effect") or spec.raw.get("rules_text") or "")
    text = _PARENS.sub(" ", text)
    for kw in spec.keywords:
        text = re.sub(rf"\b{re.escape(kw)}\b", " ", text, flags=re.IGNORECASE)
    return text


def _effect_problems(eff) -> list[str]:
    """Reasons this single effect is dropped by the engine (empty = handled)."""
    problems: list[str] = []
    if eff.effect not in _HANDLED_VERBS:
        problems.append(f"unhandled verb '{eff.effect}'")
    if eff.trigger not in KNOWN_TRIGGERS:
        problems.append(f"unknown trigger '{eff.trigger}'")
    cond = eff.condition
    if isinstance(cond, dict):
        ct = cond.get("type")
        if ct in SAFE_FALSE_CONDITIONS:
            problems.append(f"safe-false condition '{ct}' (never fires)")
        elif ct is not None and ct not in KNOWN_CONDITIONS:
            problems.append(f"unknown condition '{ct}'")
    return problems


def classify(spec: CardSpec) -> tuple[str, str]:
    """Return (verdict, reason)."""
    if not spec.effects:
        category = str(spec.raw.get("category") or "").strip().lower()
        if category == "spell" and spec.damage:
            return LIVE, "printed damage, no effects[]"
        if _LOWER_PROSE.search(_printed_ability_text(spec)):
            return INERT, "empty effects[] but has printed ability text"
        return VANILLA, "no printed ability (stats/keywords only)"

    dropped = 0
    reasons: list[str] = []
    for eff in spec.effects:
        probs = _effect_problems(eff)
        if probs:
            dropped += 1
            reasons.extend(probs)
    if dropped == 0:
        return LIVE, "all effects handled"
    dedup = "; ".join(dict.fromkeys(reasons))
    if dropped == len(spec.effects):
        return INERT, dedup
    return PARTIAL, f"{dropped}/{len(spec.effects)} effects dropped — {dedup}"


def _load_review_reasons() -> dict[str, str]:
    reasons: dict[str, str] = {}
    if REVIEW_FILE.exists():
        for line in REVIEW_FILE.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                name, reason = line.split("\t", 1)
                reasons[name.strip()] = reason.strip()
    return reasons


def _deck_cards(path: Path):
    """Yield (name, copies, zone, spec) for a deck: main deck (collapsed by name),
    plus champion / legend / battlefields."""
    specs, _runes, champion, legend, battlefields = load_deck_json(path)
    counts = Counter(s.name for s in specs)
    by_name = {s.name: s for s in specs}
    for name, copies in sorted(counts.items()):
        yield name, copies, "deck", by_name[name]
    if champion is not None:
        yield champion.name, 1, "champion", champion
    if legend is not None:
        yield legend.name, 1, "legend", legend
    for bf in battlefields:
        yield bf.name, 1, "battlefield", bf


def _fmt_table(rows: list[tuple]) -> list[str]:
    out = ["| card | copies | zone | verdict | reason |",
           "|------|:------:|------|---------|--------|"]
    for name, copies, zone, verdict, reason in rows:
        reason = reason.replace("|", "\\|")
        out.append(f"| {name} | {copies} | {zone} | {verdict} | {reason} |")
    return out


def main(decks_only: bool = typer.Option(False, "--decks-only",
         help="Skip the corpus-wide summary; only audit the deck files.")):
    review = _load_review_reasons()
    lines: list[str] = ["# Engine Coverage Audit", "",
                        "_Generated by `scripts/coverage_audit.py`. Reuses "
                        "`effects.REGISTRY` + `engine_vocab` as the source of truth "
                        "for what the engine handles._", ""]

    # --- Corpus-wide summary ---
    if not decks_only:
        corpus = Counter(classify(s)[0] for s in CARD_REGISTRY.values())
        total = sum(corpus.values())
        lines += [f"## Corpus-wide ({total} cards)", ""]
        for v in (LIVE, PARTIAL, INERT, VANILLA):
            n = corpus.get(v, 0)
            lines.append(f"- **{v}**: {n} ({100 * n / total:.0f}%)")
        modeled = corpus.get(LIVE, 0) + corpus.get(VANILLA, 0)
        lines += ["",
                  f"_LIVE + VANILLA = {modeled} ({100 * modeled / total:.0f}%) of "
                  f"cards are faithfully modeled; INERT + PARTIAL = "
                  f"{corpus.get(INERT, 0) + corpus.get(PARTIAL, 0)} miss all or part "
                  f"of their printed ability._", ""]

    # --- Per-deck detail ---
    lines += ["## Meta decks", "",
              "The cards that actually matter for win-rate. `verdict` other than "
              "LIVE/VANILLA means the engine misrepresents that card.", ""]
    deck_paths = sorted(DECK_DIR.glob("*.json"))
    summary_rows: list[str] = ["| deck | LIVE | VANILLA | PARTIAL | INERT |",
                               "|------|:----:|:-------:|:-------:|:-----:|"]
    detail_sections: list[str] = []
    for path in deck_paths:
        rows = []
        counts = Counter()
        for name, copies, zone, spec in _deck_cards(path):
            verdict, reason = classify(spec)
            counts[verdict] += 1
            if name in review and verdict in (INERT, PARTIAL):
                reason = f"{reason} [parser: {review[name]}]"
            rows.append((name, copies, zone, verdict, reason))
        summary_rows.append(
            f"| {path.stem} | {counts.get(LIVE, 0)} | {counts.get(VANILLA, 0)} | "
            f"{counts.get(PARTIAL, 0)} | {counts.get(INERT, 0)} |")
        # Sort problems first, then by zone/name, for a scannable worklist.
        order = {INERT: 0, PARTIAL: 1, VANILLA: 2, LIVE: 3}
        rows.sort(key=lambda r: (order[r[3]], r[2], r[0]))
        detail_sections += [f"### {path.stem}", ""] + _fmt_table(rows) + [""]

    lines += summary_rows + [""] + detail_sections
    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Console recap.
    print(f"Wrote {OUT_FILE.relative_to(REPO)}")
    if not decks_only:
        for v in (LIVE, PARTIAL, INERT, VANILLA):
            print(f"  corpus {v:8s}: {corpus.get(v, 0)}")


if __name__ == "__main__":
    typer.run(main)
