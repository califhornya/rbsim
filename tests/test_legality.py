"""legal_actions() soundness + completeness, plus the Observation info-boundary.

Soundness is defined against the engine's own progress oracle, ``_action_fingerprint``
(the signature its no-op guard uses): a *sound* action, applied to a clone, moves
that fingerprint. Completeness is checked against real heuristic-agent play — every
action an agent actually makes (that makes progress) must be offered.

The heavy lifting is a probe GameLoop that, at each real turn action, enumerates
legal_actions for the acting player and cross-checks them on throwaway clones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop
from riftbound.core.legality import legal_actions
from riftbound.core.decisions import DecisionPoint, Observation, DecisionRequest, GameAction

REPO_ROOT = Path(__file__).resolve().parent.parent
_DECKS = REPO_ROOT / "riftbound" / "data" / "decks"
PYKE = _DECKS / "fury_chaos_pyke.json"
DIANA = _DECKS / "chaos_mind_diana.json"
YASUO = _DECKS / "calm_chaos_yasuo.json"

_GAMES = [
    ("pyke", PYKE, "diana", DIANA, 42),
    ("diana", DIANA, "pyke", PYKE, 7),
    ("simple_trade", YASUO, "pyke", PYKE, 99),
]


def _key(t: tuple) -> tuple:
    """Normalise an engine action tuple to what actually matters for legality,
    collapsing fields the engine ignores (UNIT/CHAMPION target lane; the Gold
    sacrifice's chosen domain)."""
    kind = t[0]
    if kind == "PASS":
        return ("PASS",)
    if kind in ("UNIT", "CHAMPION"):
        return (kind, t[1])
    if kind in ("SPELL", "GEAR"):
        return (kind, t[1], t[2])
    if kind == "MOVE":
        return (kind, t[2], t[3])
    if kind == "ABILITY":
        return (kind, t[1]) if t[1] == "GOLD_SACRIFICE" else (kind, t[1], t[2])
    return tuple(t)


def _apply_on_clone(loop: GameLoop, ap_name: str, engine_action: tuple, cards_played: int):
    """Apply an action to a fresh clone; return (before_fp, after_fp)."""
    clone = loop.gs.clone()
    tmp = GameLoop(clone)  # clone has no agents -> constructing a loop is side-effect free
    cap = clone.get_player(ap_name)
    cop = clone.get_player(clone.other(ap_name))
    before = tmp._action_fingerprint(cap, cop)
    tmp._apply_action(cap, engine_action, cards_played_this_turn=cards_played)
    after = tmp._action_fingerprint(cap, cop)
    return before, after


class _ProbeLoop(GameLoop):
    def __init__(self, gs):
        super().__init__(gs)
        self.sound_violations: list = []
        self.crash_violations: list = []
        self.completeness_violations: list = []

    def _apply_action(self, ap, action, cards_played_this_turn: int = 0):
        acts = legal_actions(self, DecisionPoint.TURN_ACTION, ap.name)

        # PASS is always available.
        assert any(a.kind == "PASS" for a in acts), f"PASS missing at turn {self.gs.turn}"

        legal_keys = {_key(a.to_engine()) for a in acts}

        for a in acts:
            if a.kind == "PASS":
                continue
            try:
                before, after = _apply_on_clone(self, ap.name, a.to_engine(), cards_played_this_turn)
            except Exception as exc:  # noqa: BLE001 - we want to report, not abort
                self.crash_violations.append((self.gs.turn, a.label, repr(exc)))
                continue
            # Card plays / moves / champion must make progress. Activated abilities
            # are handler-dependent (can legitimately fizzle on no target), so they
            # are only required not to crash.
            if a.kind != "ABILITY" and before == after:
                self.sound_violations.append((self.gs.turn, a.label))

        # Completeness: whatever the agent really does, if it makes progress, must
        # be in the legal menu.
        if action[0] != "PASS":
            before, after = _apply_on_clone(self, ap.name, action, cards_played_this_turn)
            if before != after and _key(action) not in legal_keys:
                self.completeness_violations.append((self.gs.turn, action))

        super()._apply_action(ap, action, cards_played_this_turn=cards_played_this_turn)


@pytest.mark.parametrize("ai_a,deck_a,ai_b,deck_b,seed", _GAMES)
def test_legal_actions_sound_and_complete(ai_a, deck_a, ai_b, deck_b, seed):
    gs = build_game(game_seed=seed, deck_a_path=deck_a, deck_b_path=deck_b, ai_a=ai_a, ai_b=ai_b)
    loop = _ProbeLoop(gs)
    loop.start()

    assert not loop.crash_violations, f"legal action crashed on apply: {loop.crash_violations[:5]}"
    assert not loop.sound_violations, f"unsound (no-op) legal actions: {loop.sound_violations[:8]}"
    assert not loop.completeness_violations, (
        f"agent made a move not offered by legal_actions: {loop.completeness_violations[:8]}"
    )


def test_game_action_round_trips():
    for t in [("PASS", None, None), ("UNIT", 3, 0), ("SPELL", 1, 2),
              ("MOVE", None, 2, 1), ("ABILITY", "GOLD_SACRIFICE", "FURY")]:
        assert GameAction.from_engine(t).to_engine() == t


def test_observation_hides_opponent_hand_and_deck_order():
    gs = build_game(game_seed=1, deck_a_path=PYKE, deck_b_path=DIANA, ai_a="pyke", ai_b="diana")
    for _ in range(5):
        gs.A.draw()
        gs.B.draw()

    obs = Observation.from_state(gs, viewer="A")

    # Own hand is visible; opponent's is a count only.
    assert obs.my_hand == tuple(c.name for c in gs.A.hand)
    assert obs.opp_hand_count == len(gs.B.hand)
    # No field anywhere carries the opponent's hand contents or a deck ordering.
    d = obs.to_dict()
    assert "opp_hand" not in d and "opp_deck" not in d
    for key, val in d.items():
        if "deck" in key:
            assert isinstance(val, int), f"{key} leaks deck contents/order: {val!r}"
    # Public facts are present.
    assert d["opp_deck_count"] == len(gs.B.deck.cards)
    assert d["my_deck_count"] == len(gs.A.deck.cards)


def test_decision_request_is_json_serializable():
    import json

    gs = build_game(game_seed=1, deck_a_path=PYKE, deck_b_path=DIANA, ai_a="pyke", ai_b="diana")
    obs = Observation.from_state(gs, "A")
    req = DecisionRequest(DecisionPoint.TURN_ACTION, "A", obs, (GameAction.pass_(),))
    json.dumps(req.to_dict())  # must not raise
