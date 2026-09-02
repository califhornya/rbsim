#!/usr/bin/env python
"""Convert a RiftMana-style decklist .txt into the simulator's deck JSON.

Input format (as exported / pasted from RiftMana), sections in any order:

    Legend:
    1 Kennen, Heart of the Tempest
    Champion:
    1 Kennen, Storm of Shuriken
    MainDeck:
    3 Ride the Wind
    ...
    Battlefields:
    1 Minefield
    ...
    Rune Pool:
    3 Order Rune
    9 Chaos Rune
    Sideboard:      # ignored
    ...

Card names in the .txt use a comma ("Kennen, Storm of Shuriken"); the corpus
uses no comma ("Kennen Storm of Shuriken"). Names are canonicalized against
CARD_REGISTRY so the output matches the corpus exactly, and the whole deck is
validated by load_deck_json before writing.

NOTE: the current engine does not yet consume deck-provided `legend` or
`battlefields` (load_deck_json reads only champion/cards/runes). They are written
into the JSON for record and forward-compat; they do not affect the sim yet.

Usage:
  uv run python scripts/deck_from_txt.py path/to/Kennen.txt --out riftbound/data/decks/vendetta_kennen.json
  uv run python scripts/deck_from_txt.py path/to/Kennen.txt          # prints JSON to stdout
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import typer

from riftbound.registry.cards_registry import CARD_REGISTRY, load_deck_json

app = typer.Typer(add_completion=False)

_SECTIONS = {"legend", "champion", "maindeck", "battlefields", "rune pool", "sideboard"}
_RUNE_RE = re.compile(r"^(.*?)\s+Rune$", re.IGNORECASE)


def _norm(name: str) -> str:
    """Decklist name -> corpus lookup key (drop commas, collapse whitespace)."""
    return re.sub(r"\s+", " ", name.replace(",", " ")).strip().lower()


def _canon() -> dict[str, str]:
    return {_norm(k): k for k in CARD_REGISTRY.keys()}


def _resolve(name: str, canon: dict[str, str]) -> str:
    key = _norm(name)
    if key not in canon:
        raise ValueError(f"card not found in corpus: {name!r}")
    return canon[key]


def parse_txt(text: str):
    section = None
    d = {"legend": None, "champion": None, "main": [], "battlefields": [], "runes": []}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower().rstrip(":")
        if low in _SECTIONS:
            section = low
            continue
        m = re.match(r"^(\d+)\s+(.*)$", s)
        if not m:
            continue
        count, name = int(m.group(1)), m.group(2).strip()
        if section == "legend":
            d["legend"] = name
        elif section == "champion":
            d["champion"] = name
        elif section == "maindeck":
            d["main"].append((name, count))
        elif section == "battlefields":
            d["battlefields"].append((name, count))
        elif section == "rune pool":
            d["runes"].append((name, count))
        # sideboard intentionally ignored
    return d


def build_deck(text: str, name: str | None = None) -> dict:
    canon = _canon()
    p = parse_txt(text)
    if not p["champion"]:
        raise ValueError("decklist has no Champion")

    deck: dict = {
        "name": name or (p["champion"] and _resolve(p["champion"], canon)) or "Deck",
        "legend": _resolve(p["legend"], canon) if p["legend"] else None,
        "champion": _resolve(p["champion"], canon),
        "runes": [],
        "battlefields": [{"name": _resolve(n, canon)} for n, _ in p["battlefields"]],
        "cards": [],
    }
    for rune_name, count in p["runes"]:
        m = _RUNE_RE.match(rune_name)
        domain = (m.group(1) if m else rune_name).strip().upper()
        deck["runes"].append({"domain": domain, "count": count})
    for card_name, count in p["main"]:
        deck["cards"].append({"name": _resolve(card_name, canon), "count": count})
    return deck


@app.command()
def main(
    txt: Path = typer.Argument(..., help="RiftMana decklist .txt"),
    out: Path = typer.Option(None, "--out", help="Output deck JSON path (default: stdout)"),
    name: str = typer.Option(None, "--name", help="Deck display name"),
) -> None:
    deck = build_deck(txt.read_text(encoding="utf-8"), name=name)
    blob = json.dumps(deck, ensure_ascii=False, indent=2) + "\n"

    if out:
        out.write_text(blob, encoding="utf-8")
        # Validate the written file through the real loader.
        specs, runes, champ = load_deck_json(out)
        typer.secho(
            f"Wrote {out} — {len(specs)} main cards, "
            f"{sum(c for _, c in runes)} runes, champion={champ.name if champ else None}.",
            fg=typer.colors.GREEN,
        )
    else:
        typer.echo(blob)


if __name__ == "__main__":
    app()
