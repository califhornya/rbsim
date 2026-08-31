"""The game tracer (scripts/trace_game.py): a full decision-by-decision log with
board state at every decision — the tool for eyeballing whether an agent plays
sensibly. Uses simple_trade here to stay fast."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from riftbound.core.game_factory import build_game, make_agent
from riftbound.core.loop import GameLoop
from scripts.trace_game import TracingAgent

REPO = Path(__file__).resolve().parent.parent
AKALI = REPO / "riftbound" / "data" / "decks" / "vendetta_akali.json"
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"


def test_trace_logs_every_decision_with_board_state():
    gs = build_game(game_seed=1, deck_a_path=AKALI, deck_b_path=KENNEN,
                    ai_a=None, ai_b=None, first_player="a", max_turns=40)
    gs.A.agent = TracingAgent(gs.A, make_agent("simple_trade", gs.A))
    gs.B.agent = TracingAgent(gs.B, make_agent("simple_trade", gs.B))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = GameLoop(gs, verbose=True).start()
    text = buf.getvalue()

    # The trace shows decisions, the board, legal options, and the choices.
    assert "DECISION ──" in text
    assert "Legal actions:" in text
    assert "→ CHOSE:" in text
    assert "BF0" in text and "Base A:" in text          # board state is dumped
    assert result.winner in ("A", "B", "DRAW")
    # Many decisions across a full game, not just one.
    assert text.count("DECISION ──") >= 5
