#!/usr/bin/env python
"""Gli scenari dei giudizi nel browser: la posizione, giocata con mosse vere,
sul tavolo con le immagini delle carte; giochi tu il turno e scrivi il perché.

    uv run python scripts/scenari.py                 # apre http://127.0.0.1:8766
    uv run python scripts/scenari.py --port 8766 --no-browser

Una pagina locale (niente esce dal computer), separata dal coach
(`scripts/coach.py`, che resta com'è e usa la porta 8765). Gli scenari sono in
`docs/bot/scenari.json` (come si costruiscono: `riftbound/ai/scenari.py`). Le
risposte (le mosse e il perché) vanno in `docs/bot/risposte_scenari.jsonl`;
"Segnala un problema" in `runs/scenari/reports.jsonl`. Non serve la rete.

Le immagini delle carte: quelle del coach (`riftbound/data/card_images`, da
`scripts/import_card_images.py`) se ci sono; le altre scaricate da Piltover
Archive la prima volta e tenute in `riftbound/data/card_images_piltover`
(fuori da git, come le altre: l'arte è di Riot). Senza rete, la carta è disegnata.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "riftbound" / "ai" / "scenari_page.html"
IMAGES = ROOT / "riftbound" / "data" / "card_images"
CACHE = ROOT / "riftbound" / "data" / "card_images_piltover"
ARCHIVE = ROOT / "riftbound" / "data" / "reference" / "piltover_archive.json"
_URLS: dict = {}
_FAILED: set = set()


def _image(code: str) -> bytes | None:
    """The card's image: the coach's copy, or Piltover Archive's (downloaded
    once, then kept in CACHE). None when there is none or no network."""
    for path in (IMAGES / f"{code}.webp", CACHE / f"{code}.webp"):
        if path.is_file():
            return path.read_bytes()
    if not _URLS:
        cards = json.loads(ARCHIVE.read_text(encoding="utf-8"))["cards"]
        _URLS.update({k: v["image_url"] for k, v in cards.items() if v.get("image_url")})
    url = _URLS.get(code)
    if not url or code in _FAILED:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rbsim-scenari"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
    except Exception:  # noqa: BLE001  (offline, blocked: the page draws the card)
        _FAILED.add(code)
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{code}.webp").write_bytes(data)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Gli scenari dei giudizi nel browser")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "scenari")
    ap.add_argument("--answers", type=Path, default=None,
                    help="Dove salvare le risposte (default docs/bot/risposte_scenari.jsonl)")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    from riftbound.ai.scenari import RISPOSTE_PATH, ScenarioSession
    session = ScenarioSession(args.out, args.answers or RISPOSTE_PATH)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:      # keep the console quiet
            pass

        def _send(self, body: bytes, kind: str = "application/json", code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(json.dumps(obj, default=str).encode("utf-8"), code=code)

        def do_GET(self) -> None:
            image = re.fullmatch(r"/img/([A-Za-z0-9-]+)\.webp", self.path)
            if self.path in ("/", "/index.html"):
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif image:
                data = _image(image.group(1))
                if data is None:
                    return self._json({"error": "no image"}, 404)
                self.send_response(200)
                self.send_header("Content-Type", "image/webp")
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/api/state":
                self._json(session.state())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/scenario":
                    session.new_scenario(str(body["id"]))
                elif self.path == "/api/answer":
                    session.answer(body)
                elif self.path == "/api/save":
                    session.save_answer(str(body.get("note", "")))
                elif self.path == "/api/report":
                    session.report(str(body.get("note", "")))
                elif self.path == "/api/abandon":
                    session.abandon()
                else:
                    return self._json({"error": "not found"}, 404)
                self._json({"ok": True})
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Scenari: {url}  (Ctrl+C per fermare)", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
