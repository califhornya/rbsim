"""
Parse the RiftMana card list HTML page into a staged JSON file
compatible with `import_cards.py merge`.

Usage:
    uv run python scripts/parse_html_cards.py \
        "/path/to/Card List - ....html" \
        --out staged_parsed.json \
        [--sets "Unleashed,Spiritforged"]   # comma-separated; omit to get all sets
"""

from __future__ import annotations

import html as html_lib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(help="Parse RiftMana HTML card list into staged JSON")

_MASTER_DATA = (
    Path(__file__).resolve().parent.parent
    / "riftbound" / "core" / "master_data_cards.json"
)

# Matches one card-item div (including showcase variants with extra classes)
_CARD_DIV = re.compile(r'<div class="card-item[^"]*"(.*?)</div>', re.DOTALL)
# Matches a single data-* attribute
_ATTR = re.compile(r'\bdata-([\w-]+)="([^"]*)"', re.DOTALL)


def _parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): html_lib.unescape(m.group(2)) for m in _ATTR.finditer(raw)}


_VARIANT_SUFFIX = re.compile(r'^([A-Z]+-\d+)[a-z]$')


def _base_card_id(card_id: str) -> str:
    """Strip trailing letter suffix from showcase variants: 'UNL-022a' → 'UNL-022'."""
    m = _VARIANT_SUFFIX.match(card_id)
    return m.group(1) if m else card_id


def _to_entry(attrs: dict[str, str]) -> dict[str, Any]:
    raw_card_id = attrs.get("card-id", "").strip()
    card_id = _base_card_id(raw_card_id)
    energy_raw = attrs.get("cost", "")
    might_raw = attrs.get("might", "")
    power_domain = attrs.get("power", "").strip()

    return {
        "card_id": card_id,
        "name": attrs.get("name", "").strip(),
        "type": attrs.get("type", "").strip(),
        "domain": attrs.get("color", "").strip(),
        "cost": {
            "energy": int(energy_raw) if energy_raw.isdigit() else None,
            "power": 1 if power_domain else None,
        },
        "might": int(might_raw) if might_raw.isdigit() else None,
        "rules_text": attrs.get("effect", "").strip(),
        "set": attrs.get("set", "").strip(),
        "_variant": {
            "variant_id": attrs.get("alt-code", "").strip(),
            "rarity": attrs.get("rarity", "").strip(),
        },
    }


@app.command()
def main(
    html_file: Path = typer.Argument(..., help="Path to the saved RiftMana HTML file"),
    out: Path = typer.Option(Path("staged_parsed.json"), "--out", help="Output staging file"),
    sets: str = typer.Option("", "--sets", help='Comma-separated set names to include, e.g. "Unleashed,Spiritforged". Empty = all sets.'),
    skip_existing: bool = typer.Option(True, "--skip-existing/--no-skip-existing", help="Skip cards already in master_data_cards.json"),
) -> None:
    """Parse a saved RiftMana card-list HTML into a staged JSON file."""

    if not html_file.exists():
        typer.secho(f"Error: file not found: {html_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    filter_sets: set[str] = set()
    if sets.strip():
        filter_sets = {s.strip() for s in sets.split(",") if s.strip()}

    existing_ids: set[str] = set()
    if skip_existing and _MASTER_DATA.exists():
        with _MASTER_DATA.open("r", encoding="utf-8") as fh:
            existing_ids = {c.get("card_id", "") for c in json.load(fh)}

    raw_html = html_file.read_text(encoding="utf-8", errors="replace")

    # Group by card_id so multi-variant cards merge into one entry
    by_id: dict[str, dict[str, Any]] = {}
    variants_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)

    for m in _CARD_DIV.finditer(raw_html):
        attrs = _parse_attrs(m.group(1))
        if not attrs.get("name"):
            continue
        entry = _to_entry(attrs)
        card_id = entry["card_id"]
        if not card_id:
            continue
        if filter_sets and entry["set"] not in filter_sets:
            continue

        variant = entry.pop("_variant")
        variants_by_id[card_id].append(variant)

        if card_id not in by_id:
            by_id[card_id] = entry

    # Attach collected variants
    results: list[dict[str, Any]] = []
    skipped_existing = 0
    for card_id, entry in sorted(by_id.items()):
        if card_id in existing_ids:
            skipped_existing += 1
            continue
        entry["variants"] = variants_by_id[card_id]
        results.append(entry)

    with out.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    sets_found = sorted({e["set"] for e in results})
    typer.secho(f"\nParsed {len(results)} new card(s) into {out}", fg=typer.colors.GREEN)
    if skipped_existing:
        typer.echo(f"Skipped {skipped_existing} card(s) already in registry.")
    typer.echo(f"Sets: {', '.join(sets_found) if sets_found else '(none)'}")
    typer.echo(f"\nReview {out}, then run:\n\n  uv run python scripts/import_cards.py merge {out}\n")


if __name__ == "__main__":
    app()
