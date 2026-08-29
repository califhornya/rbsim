#!/usr/bin/env python
"""Merge a saved RiftMana card-list HTML directly into the card corpus.

This restores the corpus-merge step (the old scripts/import_cards.py referenced by
parse_html_cards.py is not in the repo). It reads the `card-item` divs from a saved
RiftMana HTML page, maps each card to the all_cards.json schema, and appends the
NEW cards to the corpus.

Design decisions:
- Cards whose NAME already exists in the corpus are SKIPPED. Cross-set reprints
  (e.g. Viktor Innovator, the basic Runes/Gold/Mech/Recruit tokens) are identical
  to the existing entry, which is already parsed — keeping one canonical entry per
  name avoids ambiguous duplicates when resolving decklists by name.
- effects[] starts EMPTY; the LLM parser (scripts/generate_effects.py) fills it
  in a later step (needs an API key).
- POWER COST: RiftMana encodes the pip COUNT by repeating the domain token in
  data-power, space-separated. "Order" = 1 Order pip; "Order Order" = 2 Order
  pips; "Body Body Body" = 3 Body; "Fury/Calm" = a single hybrid pip payable by
  Fury or Calm. So cost_power = number of space-separated tokens, and
  cost_power_domain is the (deduplicated) domain string — matching the convention
  the rest of the corpus already uses (cost_power ranges 0-4).

Usage:
  uv run python scripts/import_cards.py merge-html path/to/vendetta.html
  uv run python scripts/import_cards.py merge-html path/to/vendetta.html --sets Vendetta --dry-run
"""
from __future__ import annotations

import html as html_lib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(help="Merge RiftMana HTML card data into the corpus")


@app.callback()
def _root() -> None:
    """Card corpus import tools."""

CORPUS = Path(__file__).resolve().parent.parent / "riftbound" / "data" / "cards" / "all_cards.json"

_CARD_DIV = re.compile(r'<div class="card-item[^"]*"(.*?)</div>', re.DOTALL)
_ATTR = re.compile(r'\bdata-([\w-]+)="([^"]*)"', re.DOTALL)
_VARIANT_SUFFIX = re.compile(r'^([A-Z]+-\d+)[a-z]$')


def _parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): html_lib.unescape(m.group(2)) for m in _ATTR.finditer(raw)}


def _base_card_id(card_id: str) -> str:
    m = _VARIANT_SUFFIX.match(card_id)
    return m.group(1) if m else card_id


def _entry_from_attrs(attrs: dict[str, str]) -> dict[str, Any]:
    """Map one RiftMana card's data-* attributes to the all_cards.json schema."""
    cost_raw = attrs.get("cost", "").strip()
    might_raw = attrs.get("might", "").strip()
    # data-power repeats the domain token once per pip, space-separated:
    # "" | "Fury" | "Order Order" (=2) | "Fury/Calm" (=1 hybrid pip).
    power_raw = attrs.get("power", "").strip()
    power_tokens = power_raw.split()
    cost_power = len(power_tokens)
    if power_tokens:
        uniq = list(dict.fromkeys(power_tokens))  # dedup, preserve order
        cost_power_domain: str | None = uniq[0] if len(uniq) == 1 else "/".join(uniq)
    else:
        cost_power_domain = None
    color = attrs.get("color", "").strip()          # "" | "Fury" | "Fury Calm"

    # Energy: an integer when present; a card with a power cost but no energy
    # number costs 0 energy; costless cards (Legends/Runes/Tokens/Battlefields)
    # get None to match the corpus convention.
    if cost_raw.isdigit():
        cost_energy: int | None = int(cost_raw)
    elif cost_power:
        cost_energy = 0
    else:
        cost_energy = None

    effect = attrs.get("effect", "").strip()
    equipped = attrs.get("e-effect", "").strip()

    return {
        "card_id": _base_card_id(attrs.get("card-id", "").strip()),
        "name": attrs.get("name", "").strip(),
        "domain": color or None,
        "category": attrs.get("type", "").strip(),
        "sub_type": attrs.get("sub-type", "").strip() or None,
        "might": int(might_raw) if might_raw.isdigit() else None,
        "cost_energy": cost_energy,
        "cost_power": cost_power,
        "cost_power_domain": cost_power_domain,
        "effect": effect,
        "effect_equipped": equipped or None,
        "set": attrs.get("set", "").strip(),
        "keywords": [],   # populated by the loader/parser from rules text
        "effects": [],    # filled later by scripts/generate_effects.py
    }


@app.command("merge-html")
def merge_html(
    html_file: Path = typer.Argument(..., help="Saved RiftMana card-list HTML"),
    sets: str = typer.Option("", "--sets", help='Comma-separated set names to include (e.g. "Vendetta"). Empty = all.'),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be added; do not write."),
) -> None:
    if not html_file.exists():
        typer.secho(f"Error: file not found: {html_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    filter_sets = {s.strip() for s in sets.split(",") if s.strip()}

    corpus: list[dict[str, Any]] = json.loads(CORPUS.read_text(encoding="utf-8"))
    existing_names = {c.get("name", "") for c in corpus}
    existing_ids = {c.get("card_id", "") for c in corpus}

    raw = html_file.read_text(encoding="utf-8", errors="replace")

    by_id: dict[str, dict[str, Any]] = {}
    variants_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for m in _CARD_DIV.finditer(raw):
        attrs = _parse_attrs(m.group(1))
        if not attrs.get("name"):
            continue
        entry = _entry_from_attrs(attrs)
        base_id = entry["card_id"]
        if not base_id:
            continue
        if filter_sets and entry["set"] not in filter_sets:
            continue
        variants_by_id[base_id].append({
            "variant_id": attrs.get("card-id", "").strip(),
            "rarity": attrs.get("rarity", "").strip(),
        })
        by_id.setdefault(base_id, entry)

    new_entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    skipped_name: list[str] = []
    skipped_id = 0
    for base_id, entry in sorted(by_id.items()):
        name = entry["name"]
        if base_id in existing_ids:
            skipped_id += 1
            continue
        if name in existing_names or name in seen_names:
            skipped_name.append(name)
            continue
        entry["variants"] = variants_by_id[base_id]
        new_entries.append(entry)
        seen_names.add(name)

    sets_found = sorted({e["set"] for e in new_entries})
    typer.secho(f"New cards to add: {len(new_entries)}  (sets: {', '.join(sets_found) or '(none)'})",
                fg=typer.colors.GREEN)
    typer.echo(f"Skipped {len(set(skipped_name))} name-collision(s) (reprints/tokens already in corpus)"
               f"{' + %d id-collision(s)' % skipped_id if skipped_id else ''}.")
    by_cat: dict[str, int] = defaultdict(int)
    for e in new_entries:
        by_cat[e["category"]] += 1
    typer.echo("By category: " + ", ".join(f"{k}={v}" for k, v in sorted(by_cat.items())))

    if dry_run:
        typer.secho("\n--dry-run: no files written.", fg=typer.colors.YELLOW)
        return

    backup = CORPUS.with_suffix(".json.preimport.bak")
    shutil.copy2(CORPUS, backup)
    corpus.extend(new_entries)
    CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.secho(f"\nWrote {len(corpus)} cards to {CORPUS} (backup: {backup.name}).", fg=typer.colors.GREEN)
    typer.echo("Next: run scripts/generate_effects.py on the new set to fill effects[] (needs API key).")


if __name__ == "__main__":
    app()
