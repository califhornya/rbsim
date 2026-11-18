"""S11a/S11b (docs/bot/scenari.json): G3, turn 7, against Sett (18/11). The
same position, Rampage on the chain; in S11b Evelynn's "once each turn" draw
is already used (`legend_used`). Flipping Bedeviling Stranger draws a card
(Star-Crossed, as in the game) in S11a, none in S11b."""
from __future__ import annotations

import pytest

from riftbound.ai.scenari import (
    ScenarioOver,
    ScriptedChooser,
    ScriptedSeat,
    _plan,
    build_state,
    get_scenario,
    stop_after_turn,
)
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop


def _flip_stranger(sid: str) -> dict:
    """The user flips the Stranger at the first decision, then passes to the
    end of the turn: what the deck and the hand became."""
    sc = get_scenario(sid)
    gs = build_state(sc)
    plan = _plan(sc)
    seen: dict = {}

    def human(agent, point, bf_idx):
        if "deck" in seen:
            return ("PASS", None, None)
        me = agent.player
        seen["deck"], seen["point"] = len(me.deck.cards), point.value
        legal = legal_actions(agent.loop, point, me.name)
        hit = [g for g in legal if g.label.startswith("Play Bedeviling Stranger from Hidden")]
        assert hit, [g.label for g in legal]
        return hit[0].to_engine()

    for side in ("A", "B"):
        p = gs.get_player(side)
        p.agent = ScriptedSeat(p, sc, plan, human=human if side == sc["human"] else None)
    loop = GameLoop(gs)
    loop.chooser = ScriptedChooser(plan, sc["id"])
    stop_after_turn(loop, int(sc["turn"]))
    with pytest.raises(ScenarioOver):
        loop.start()
    me = gs.get_player(sc["human"])
    seen["deck_after"] = len(me.deck.cards)
    seen["seen"] = {c.name for c in me.hand} | {c.name for c in me.trash}
    return seen


def test_flipping_the_stranger_draws_only_with_the_trigger_free():
    a, b = _flip_stranger("S11a"), _flip_stranger("S11b")
    assert a["point"] == b["point"] == "reaction"
    assert a["deck"] == b["deck"]
    assert a["deck"] - a["deck_after"] == 1 and "Star-Crossed" in a["seen"]
    assert b["deck"] - b["deck_after"] == 0 and "Star-Crossed" not in b["seen"]
