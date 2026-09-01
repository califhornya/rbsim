"""RiftboundEnv (Stage 1): gym-style single-agent RL environment over the real
engine. Drive a full game with a trivial policy and check the reset/step/reward
contract."""

from __future__ import annotations

from pathlib import Path

from riftbound.ai.env import RiftboundEnv
from riftbound.core.decisions import DecisionPoint, Observation

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"

_PASS = ("PASS", None, None)


def _trivial_policy(info):
    """Keep the whole hand at mulligan; otherwise PASS if legal, else first legal."""
    if info["decision_point"] == DecisionPoint.MULLIGAN.value:
        return []
    legal = info["legal_actions"]
    for a in legal:
        if a.to_engine() == _PASS:
            return a
    return legal[0] if legal else _PASS


def _play_to_end(env):
    obs, info = env.reset(seed=5)
    assert isinstance(obs, Observation)
    steps = 0
    while not info["done"]:
        obs, reward, done, info = env.step(_trivial_policy(info))
        steps += 1
        assert steps < 2000            # must terminate
    return obs, info


def test_env_runs_a_full_game_and_reports_reward():
    env = RiftboundEnv(deck_a_path=KENNEN, deck_b_path=ORNN,
                       agent_side="A", opponent="simple_trade", seed=5)
    obs, info = _play_to_end(env)
    assert info["done"] is True
    assert info["reward"] in (-1.0, 0.0, 1.0)
    assert env.result is not None and env.result.winner in ("A", "B", "DRAW")
    # Reward sign matches the outcome from the learner's seat.
    if env.result.winner == "A":
        assert info["reward"] == 1.0
    elif env.result.winner == "B":
        assert info["reward"] == -1.0
    else:
        assert info["reward"] == 0.0


def test_env_reset_gives_observation_and_legal_actions():
    env = RiftboundEnv(deck_a_path=KENNEN, deck_b_path=ORNN, agent_side="A", seed=1)
    obs, info = env.reset()
    assert obs.viewer == "A"
    assert info["decision_point"] in {p.value for p in DecisionPoint}
    # legal_actions is a list (possibly empty at a mulligan point).
    assert isinstance(info["legal_actions"], list)
    assert info["done"] is False


def test_env_agent_side_b_reward_perspective():
    env = RiftboundEnv(deck_a_path=KENNEN, deck_b_path=ORNN,
                       agent_side="B", opponent="simple_trade", seed=5)
    _obs, info = _play_to_end(env)
    if env.result.winner == "B":
        assert info["reward"] == 1.0
    elif env.result.winner == "A":
        assert info["reward"] == -1.0
