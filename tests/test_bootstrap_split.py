"""The three groups of scripts/bootstrap_net.py: disjoint, 1,600/200/200 of
2,000 games, Evelynn half the times in A and half in B in each."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "bootstrap_net", Path(__file__).resolve().parents[1] / "scripts/bootstrap_net.py")
bn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bn)


def _games(n):
    # As data() plays them: seeds SEED0.., Evelynn in A in the even seeds.
    return [dict(seed=bn.SEED0 + i, eve="A" if (bn.SEED0 + i) % 2 == 0 else "B") for i in range(n)]


def test_2000_games():
    seeds = np.arange(bn.SEED0, bn.SEED0 + 2000)
    g = bn.group_of(seeds)
    for gr, n in ((bn.TRAIN, 1600), (bn.VAL, 200), (bn.TEST, 200)):
        s = seeds[g == gr]
        assert len(s) == n
        assert (s % 2 == 0).sum() == n // 2            # Evelynn in A
        assert (s % 2 == 1).sum() == n // 2            # Evelynn in B
    assert len(set(seeds[g == bn.VAL]) | set(seeds[g == bn.TEST]) | set(seeds[g == bn.TRAIN])) == 2000
    lines = bn.check_split(_games(2000), seeds)
    assert "1600 partite (Evelynn 800 in A, 800 in B)" in lines[0]
    assert "200 partite (Evelynn 100 in A, 100 in B)" in lines[1]
    assert "200 partite (Evelynn 100 in A, 100 in B)" in lines[2]


def test_every_chunk_is_balanced():
    # A run stopped early keeps whole chunks: each one already balanced.
    for c in range(50):
        seeds = np.arange(bn.SEED0 + c * bn.CHUNK, bn.SEED0 + (c + 1) * bn.CHUNK)
        g = bn.group_of(seeds)
        for gr in (bn.VAL, bn.TEST):
            assert (seeds[g == gr] % 2 == 0).sum() == (seeds[g == gr] % 2 == 1).sum() > 0


def test_check_split_refuses():
    games = _games(40)
    games[3]["eve"] = "A"                               # an odd seed with Evelynn in A
    with pytest.raises(RuntimeError):
        bn.check_split(games)
    with pytest.raises(RuntimeError):
        bn.check_split(_games(40) + _games(1))          # the same seed twice
    with pytest.raises(RuntimeError):
        bn.check_split(_games(39))                      # a test pair cut in half
    with pytest.raises(RuntimeError):
        bn.check_split(_games(40), np.array([bn.SEED0 + 99]))
