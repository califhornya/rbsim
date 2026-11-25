"""Card images for the local pages (the coach's, by card code: OGN-017).

The copy made by scripts/import_card_images.py (riftbound/data/card_images) when
there is one; else Piltover Archive's, downloaded the first time and kept in
riftbound/data/card_images_piltover (the folder scripts/scenari.py fills too).
Both folders are git-ignored: the art is Riot's, it stays on the machine.
When the download fails (certificates of the Mac's Python, a CDN that turns
away scripts), url() is the image's address for the browser to load itself;
the first failure is told once on the console. No image at all: the page
draws the card.
"""
from __future__ import annotations

import json
import re
import ssl
import sys
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
_told = False


def _context() -> ssl.SSLContext:
    try:                                    # certifi's roots: the Mac's Python may have none
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def url(code: str) -> Optional[str]:
    """The card's image on Piltover Archive (None: there isn't one)."""
    if not re.fullmatch(r"[A-Za-z0-9-]+", code):
        return None
    with _LOCK:
        if not _URLS and ARCHIVE.is_file():
            cards = json.loads(ARCHIVE.read_text(encoding="utf-8"))["cards"]
            _URLS.update({k: v["image_url"] for k, v in cards.items() if v.get("image_url")})
        return _URLS.get(code)


def image(code: str) -> Optional[bytes]:
    """The card's image: the local copy, else downloaded once and kept."""
    global _told
    if not re.fullmatch(r"[A-Za-z0-9-]+", code):
        return None
    for path in (IMAGES / f"{code}.webp", CACHE / f"{code}.webp"):
        if path.is_file():
            return path.read_bytes()
    address = url(code)
    if not address or code in _FAILED:
        return None
    try:
        req = urllib.request.Request(address, headers={"User-Agent": "Mozilla/5.0 (rbsim-coach)"})
        with urllib.request.urlopen(req, timeout=10, context=_context()) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001  (offline, blocked: the browser tries, or draws the card)
        with _LOCK:
            _FAILED.add(code)
            tell, _told = not _told, True
        if tell:
            print(f"Immagini: download da Piltover Archive non riuscito ({exc!r}); "
                  "le carica il browser direttamente.", file=sys.stderr, flush=True)
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / f"{code}.webp.part.{threading.get_ident()}"   # two requests at once: no half file
    tmp.write_bytes(data)
    tmp.replace(CACHE / f"{code}.webp")
    return data
