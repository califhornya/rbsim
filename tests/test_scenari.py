"""The scenarios of docs/bot/scenari.json are reached by real moves from turn 1
and are the positions their text describes (riftbound/ai/scenari.py)."""

from __future__ import annotations

import pytest

from riftbound.ai.scenari import load_scenari, reach


def _within(want, got, path="") -> list:
    """Where `got` differs from what `want` states (dicts: only the keys given)."""
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return [f"{path}: {got!r}"]
        return [d for k, v in want.items() for d in _within(v, got.get(k), f"{path}.{k}")]
    return [] if want == got else [f"{path}: want {want!r}, got {got!r}"]


@pytest.mark.parametrize("sc", load_scenari(), ids=lambda sc: sc["id"])
def test_the_scenario_is_the_position_described(sc):
    pos, point = reach(sc)
    expect = dict(sc["expect"])
    assert expect.pop("point") == point.value
    assert expect, "a scenario states its position"
    assert not _within(expect, pos)
