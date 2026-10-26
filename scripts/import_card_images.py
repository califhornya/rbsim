#!/usr/bin/env python
"""Copy card images from a saved RiftMana card-list page into the project.

    uv run python scripts/import_card_images.py "C:\\Users\\me\\Downloads\\tutte le carte_files"

Save the card list in the browser with Ctrl+S, "Web page, complete" (scrolled
to the bottom, so every image has loaded): the page's `_files` folder holds
each card's image named by its code (OGN-017.webp; battlefields
OGN-275-horizontal.webp) and the card back (rift_backup.webp). This copies the
ones for the cards in all_cards.json to riftbound/data/card_images/<code>.webp
(battlefields stay horizontal), plus back.webp. The folder is git-ignored: the
art is Riot's, it stays on this machine. Run it again after saving a new set.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "riftbound" / "data" / "cards" / "all_cards.json"
OUT = ROOT / "riftbound" / "data" / "card_images"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path, help="the saved page's _files folder")
    args = ap.parse_args()
    src = args.folder
    if not src.is_dir():
        raise SystemExit(f"not a folder: {src}")
    OUT.mkdir(parents=True, exist_ok=True)
    copied, missing = 0, []
    for card in json.loads(CARDS.read_text(encoding="utf-8")):
        cid = card["card_id"]
        names = [f"{cid}-horizontal.webp", f"{cid}.webp"] if card["category"] == "Battlefield" \
            else [f"{cid}.webp"]
        names += [f"{v['variant_id']}.webp" for v in card.get("variants") or []]
        found = next((src / n for n in names if (src / n).is_file()), None)
        if found is None:
            missing.append(f"{cid} {card['name']}")
            continue
        shutil.copyfile(found, OUT / f"{cid}.webp")
        copied += 1
    if (src / "rift_backup.webp").is_file():
        shutil.copyfile(src / "rift_backup.webp", OUT / "back.webp")
    print(f"copied {copied} card images to {OUT}")
    if missing:
        print(f"no image for {len(missing)}: " + ", ".join(missing))


if __name__ == "__main__":
    main()
