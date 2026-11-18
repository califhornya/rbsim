"""What the scenario page saves (riftbound/ai/scenari.py, save_answer): the
first decision with the options it was chosen from and the hand, the move
considered and discarded, what would change the choice, and the outcome apart
(chat of 17-18/11: judge the move before the draw)."""
from __future__ import annotations

import json
import time

from riftbound.ai.scenari import ScenarioSession


def _wait(session, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        if session.pending is not None or session.status == "over":
            return session.pending
        time.sleep(0.02)
    raise TimeoutError("the scenario never asked")


def test_the_answer_keeps_options_hand_alternative_and_outcome_apart(tmp_path):
    answers = tmp_path / "risposte.jsonl"
    session = ScenarioSession(tmp_path / "out", answers)
    session.new_scenario("S6")
    first = True
    while (pending := _wait(session)) is not None:
        if pending["type"] == "decision":
            texts = [a["text"] for a in pending["actions"]]
            pick = texts.index("Gioca Pyke Returned in base") if first else \
                next(i for i, t in enumerate(texts) if t.startswith("Passa"))
            first = False
            session.answer({"action": pick})
        else:
            session.answer({"option": 0})
    session._thread.join(timeout=30)

    session.save_answer("Pyke in base per nasconderlo dopo", "Gioca Gutter Guardian in base",
                        "se lui avesse una rimozione da 3")
    rec = json.loads(answers.read_text(encoding="utf-8").splitlines()[-1])
    decision = rec["moves"][0]
    assert rec["scenario"] == "S6"
    assert decision["move"] == "Gioca Pyke Returned in base"
    assert "Gioca Gutter Guardian in base" in decision["options"]
    assert "Pyke Returned" in decision["hand"]
    assert rec["note"] == "Pyke in base per nasconderlo dopo"
    assert rec["alternative"] == "Gioca Gutter Guardian in base"
    assert rec["change_if"] == "se lui avesse una rimozione da 3"
    assert set(rec["outcome"]) == {"events", "hand_at_end"}
    assert "Pyke Returned" not in rec["outcome"]["hand_at_end"]
    assert all(not e.get("move") for e in rec["outcome"]["events"])
