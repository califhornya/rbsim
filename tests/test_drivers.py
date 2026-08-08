"""SyncDriver / SessionDriver — completion parity and pausable human play."""

from __future__ import annotations

from pathlib import Path

from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop
from riftbound.core.drivers import SyncDriver, SessionDriver

REPO_ROOT = Path(__file__).resolve().parent.parent
_DECKS = REPO_ROOT / "riftbound" / "data" / "decks"
PYKE = _DECKS / "fury_chaos_pyke.json"
DIANA = _DECKS / "chaos_mind_diana.json"


def _game(seed=42, ai_a="pyke", ai_b="diana"):
    return build_game(game_seed=seed, deck_a_path=PYKE, deck_b_path=DIANA, ai_a=ai_a, ai_b=ai_b)


def test_sync_driver_is_identical_to_direct_loop():
    # Two identically-seeded games: one via the raw loop, one via SyncDriver.
    # SyncDriver must add no behavioural change (the golden fixture pins the loop,
    # so this transitively pins the driver).
    for seed in (1, 42, 99, 256):
        direct = GameLoop(_game(seed)).start()
        driven = SyncDriver(_game(seed)).run()
        assert (direct.winner, direct.turns, direct.units_played, direct.spells_cast) == (
            driven.winner, driven.turns, driven.units_played, driven.spells_cast
        )


def _drive_human_passes(driver: SessionDriver, max_steps: int = 5000):
    """Play a full game where the remote seat mulligans nothing and always PASSes.
    Returns the number of decisions surfaced to the human."""
    decisions = 0
    for _ in range(max_steps):
        if driver.is_over():
            break
        st = driver.state()
        if st["done"]:
            break
        decisions += 1
        if st["pending_decision"] == "mulligan":
            driver.submit([])
        else:
            driver.submit(("PASS", None, None))
    return decisions


def test_session_driver_runs_a_full_human_game():
    driver = SessionDriver(_game())
    driver.make_remote("A")  # A is the human; B keeps its Diana heuristic
    driver.start()

    decisions = _drive_human_passes(driver)
    driver.join(timeout=5)

    assert driver.is_over()
    assert decisions >= 1  # the human was actually asked to act
    assert driver.result is not None
    assert driver.result.winner in ("A", "B", "DRAW")


def test_session_driver_first_decision_and_info_boundary():
    driver = SessionDriver(_game())
    driver.make_remote("A")
    driver.start()

    req = driver.pending()
    assert req is not None
    assert req.player == "A"
    assert req.observation.viewer == "A"

    # The observation the web receives never carries the opponent's hand contents.
    st = driver.state()
    obs = st["observation"]
    assert "opp_hand" not in obs
    assert isinstance(obs["opp_hand_count"], int)
    assert "my_hand" in obs

    # Resuming works and the game can be driven to completion afterwards.
    _drive_human_passes(driver)
    driver.join(timeout=5)
    assert driver.is_over()


def test_session_driver_submit_after_over_raises():
    driver = SessionDriver(_game())
    driver.make_remote("A")
    driver.start()
    _drive_human_passes(driver)
    driver.join(timeout=5)

    assert driver.is_over()
    try:
        driver.submit(("PASS", None, None))
    except RuntimeError:
        pass
    else:
        raise AssertionError("submitting after game over should raise")
