#!/usr/bin/env python
"""Play in the browser against the champion, or coach the net: you decide.

    uv run --extra rl python scripts/coach.py            # opens http://127.0.0.1:8765
    uv run --extra rl python scripts/coach.py --net runs/precons-2/net.pt --port 8765
    uv run --extra rl python scripts/coach.py --motore python        # the frozen Python engine
    uv run --extra rl python scripts/coach.py --regole 6427b90+D72-D76 --iterazioni 60

The engine (25/11): a game between two of the five decks Rust covers (Evelynn, Kha'Zix,
Rengar, Ivern, Sett), against the champion or the simple bot, plays on the Rust engine
with the rules profile --regole (default 6427b90+D72-D82: D72-D82 corrected); the
champion there searches a FIXED number of iterations a move (--iterazioni, default
riftbound.ai.coach_rs.ITERAZIONI_CAMPIONE, the median of the Rust budget 0.03 s; its
--budget is for Python), so that "Annulla l'ultima mossa" replays the same game. Anything
else (another deck, --net's advice, "La rete", --motore python) plays on Python with the
rules 6427b90. The page and games.jsonl say the engine and the rules of each game.

The opponents: the champion (the hand-written search guided by the priors of
--campione, --budget CPU seconds a move; listed when the checkpoint is there),
the net (only with --net) and the simple bot. Without --net you play alone,
with no advice and nothing saved for training (games.jsonl keeps the results).

A local page (nothing leaves the machine) shows the board from your seat, as a
table of card images (scripts/import_card_images.py copies them in; else they
are downloaded from Piltover Archive the first time and kept in
riftbound/data/card_images_piltover, or, when that fails, the browser loads them
from the archive itself; a card without one is drawn). At each of your decisions with more than one option you
pick any legal move by clicking a card (with --net you also see the net's top
three moves, with the win chance it estimates, marked on the table, and can
accept one); for a move you pick, the choices inside it are asked too. With
--net your decisions are saved when a game ends (runs/coach/coach_*.npz) and `scripts/train_selfplay.py --coach-dir runs/coach`
mixes them into training. "Segnala un problema" saves the situation and your
note (runs/coach/reports.jsonl). "Fermati qui e salva" lets the net finish the
game alone and keeps your decisions; "Ho sbagliato l'ultima mossa" drops your
last decision from training. "Annulla l'ultima mossa" (or R) takes your last
decision back, as RiftAtlas's Rewind: the game goes back to it and everything
since is undone (rebuilt from its seed and replayed from its record).
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from riftbound.provenienza import REGOLE, REGOLE_D72_D82

ROOT = Path(__file__).resolve().parents[1]
DECK_DIR = ROOT / "riftbound" / "data" / "decks"
PAGE = ROOT / "riftbound" / "ai" / "coach_page.html"


def main() -> None:
    ap = argparse.ArgumentParser(description="Coach the Riftbound net in the browser")
    ap.add_argument("--net", type=Path, default=None,
                    help="The old AlphaZero net (e.g. runs/precons-2/net.pt): its advice, and the "
                         "\"La rete\" opponent. Without it: no advice")
    ap.add_argument("--campione", type=Path, default=ROOT / "runs" / "sett" / "ekris_s12" / "ckpt_040000.pt",
                    help="The champion's PPO checkpoint (its priors)")
    ap.add_argument("--budget", type=float, default=0.4,
                    help="The champion's CPU seconds a move (on Python; on Rust see --iterazioni)")
    ap.add_argument("--motore", choices=("rust", "python"), default="rust",
                    help="The engine: rust where it covers the game, else python (default rust)")
    ap.add_argument("--regole", choices=REGOLE, default=REGOLE_D72_D82,
                    help="The rules profile of the games on Rust (default %(default)s)")
    ap.add_argument("--iterazioni", type=int, default=None,
                    help="The champion's fixed iterations a move on Rust (default "
                         "riftbound.ai.coach_rs.ITERAZIONI_CAMPIONE)")
    # rimonta from 26/11: arena vs storica on new seeds, EK 0.522, ES 0.533, the other 8 matchups 0.515-0.607
    # (docs/bot/accumulo/risultati/).
    ap.add_argument("--valutazione", choices=("storica", "rimonta"), default="rimonta",
                    help="The evaluation of the champion's search leaves, on Rust (default %(default)s); "
                         "ignored on the Python engine")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "coach")
    ap.add_argument("--iterations", type=int, default=100, help="Search simulations per decision")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pause", type=float, default=0.8,
                    help="Seconds to show the board before each opponent move")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    from riftbound.ai.card_images import image as card_image
    from riftbound.ai.card_images import url as card_url
    from riftbound.ai.coach import CoachSession
    from riftbound.compute import be_gentle
    be_gentle()
    if args.net is not None and not args.net.is_file():
        ap.error(f"--net: {args.net} non esiste")
    session = CoachSession(args.net, args.out, iterations=args.iterations, opponent_pause=args.pause,
                           campione_path=args.campione, budget=args.budget,
                           motore=args.motore, regole=args.regole, iterazioni=args.iterazioni,
                           valutazione=args.valutazione)
    if not args.campione.is_file():
        print(f"Il campione non c'è ({args.campione}): avversari {[o['name'] for o in session.opponents()]}",
              flush=True)

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
            image = re.fullmatch(r"/img/([A-Za-z0-9-]+)\.webp", self.path)
            if self.path in ("/", "/index.html"):
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif image:
                data = card_image(image.group(1))
                if data is None:
                    address = card_url(image.group(1))
                    if address is None:
                        return self._json({"error": "no image"}, 404)
                    # Not downloaded here: the browser loads it from the archive.
                    self.send_response(302)
                    self.send_header("Location", address)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/webp")
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/api/state":
                self._json({**session.state(), "decks": decks(),
                            "net": str(args.net) if args.net else None, "campione": str(args.campione)})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/new":
                    session.new_game(Path(body["deck_mine"]), Path(body["deck_opp"]),
                                     seat=body.get("seat", "A"), opponent=body.get("opponent"),
                                     seed=body.get("seed"), apertura=bool(body.get("apertura", True)))
                elif self.path == "/api/campo":
                    session.scegli_campo(body.get("campo"))
                elif self.path == "/api/inizia":
                    session.inizia(body.get("io"))
                elif self.path == "/api/answer":
                    session.answer(body)
                elif self.path == "/api/report":
                    session.report(str(body.get("note", "")))
                elif self.path == "/api/finish":
                    session.finish(save=bool(body.get("save", True)))
                elif self.path == "/api/abandon":
                    session.abandon()
                elif self.path == "/api/rewind":
                    session.rewind()
                elif self.path == "/api/forget":
                    if not session.forget_last():
                        return self._json({"error": "Nessuna tua decisione da togliere."}, 400)
                else:
                    return self._json({"error": "not found"}, 404)
                self._json({"ok": True})
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Coach: {url}  (avversario di default: {session.opponents()[0]['name']}; "
          f"rete: {args.net or 'nessuna'}; Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
