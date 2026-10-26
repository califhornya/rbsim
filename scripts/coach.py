#!/usr/bin/env python
"""Coach the net in the browser: it plays, you decide.

    uv run python scripts/coach.py                       # opens http://127.0.0.1:8765
    uv run python scripts/coach.py --net runs/precons-2/net.pt --port 8765

A local page (nothing leaves the machine) shows the board from your seat. At
each decision of the net with more than one option you see its top three moves
(how much the search explored each, the win chance it estimates) and accept one
or pick any legal move; for a move you pick, the choices inside it are asked
too. Your decisions are saved when a game ends (runs/coach/coach_*.npz) and
`scripts/train_selfplay.py --coach-dir runs/coach` mixes them into training.
"Segnala un problema" saves the situation and your note (runs/coach/reports.jsonl).
"""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK_DIR = ROOT / "riftbound" / "data" / "decks"
PAGE = ROOT / "riftbound" / "ai" / "coach_page.html"


def main() -> None:
    ap = argparse.ArgumentParser(description="Coach the Riftbound net in the browser")
    ap.add_argument("--net", type=Path, default=ROOT / "runs" / "precons-2" / "net.pt")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "coach")
    ap.add_argument("--iterations", type=int, default=100, help="Search simulations per decision")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    from riftbound.ai.coach import CoachSession
    from riftbound.compute import be_gentle
    be_gentle()
    session = CoachSession(args.net, args.out, iterations=args.iterations)

    def decks() -> list:
        paths = sorted(DECK_DIR.glob("*.json"), key=lambda p: (not p.stem.startswith("precon"), p.stem))
        return [{"path": str(p), "name": p.stem} for p in paths]

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
            if self.path in ("/", "/index.html"):
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json({**session.state(), "decks": decks(), "net": str(args.net)})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/new":
                    session.new_game(Path(body["deck_mine"]), Path(body["deck_opp"]),
                                     seat=body.get("seat", "A"), opponent=body.get("opponent", "net"))
                elif self.path == "/api/answer":
                    session.answer(body)
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
    print(f"Coach: {url}  (net: {args.net}; Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
