"""Card images for the local pages (the coach's, by card code: OGN-017).

The copy made by scripts/import_card_images.py (riftbound/data/card_images) when
there is one; else Piltover Archive's, downloaded the first time and kept in
riftbound/data/card_images_piltover (the folder scripts/scenari.py fills too).
Both folders are git-ignored: the art is Riot's, it stays on the machine. None
when there is no image or no network: the page draws the card.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request
from pathlib import Path
from typing import Optional

DATA = Path(__file__).resolve().parents[1] / "data"
IMAGES = DATA / "card_images"
CACHE = DATA / "card_images_piltover"
ARCHIVE = DATA / "reference" / "piltover_archive.json"

_URLS: dict = {}
_FAILED: set = set()
_LOCK = threading.Lock()


def image(code: str) -> Optional[bytes]:
    if not re.fullmatch(r"[A-Za-z0-9-]+", code):
        return None
    for path in (IMAGES / f"{code}.webp", CACHE / f"{code}.webp"):
        if path.is_file():
            return path.read_bytes()
    with _LOCK:
        if not _URLS and ARCHIVE.is_file():
            cards = json.loads(ARCHIVE.read_text(encoding="utf-8"))["cards"]
            _URLS.update({k: v["image_url"] for k, v in cards.items() if v.get("image_url")})
        url = _URLS.get(code)
        if not url or code in _FAILED:
            return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rbsim-coach"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
    except Exception:  # noqa: BLE001  (offline, blocked: the page draws the card)
        with _LOCK:
            _FAILED.add(code)
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / f"{code}.webp.part"           # two requests at once: no half file
    tmp.write_bytes(data)
    tmp.replace(CACHE / f"{code}.webp")
    return data
