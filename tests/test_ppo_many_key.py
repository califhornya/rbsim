"""PPOAgent.inner: "choices already made" (`made`, in the question's context)
counts the picks of one choose_many on one loop. Its key held id(loop) and
id(source): a declaration's copy, once freed, can leave its address to the
next copy, which then counted as the same loop (made 1 instead of 0). The
context then depended on the process's memory history (which games ran
before in a worker, how many workers): seen in the PPO cycle on the Mac and
here, one example in 6.232 (porting Rust, 24/11; Rust keys on a unique loop
id). The key now holds the objects themselves."""
import gc

import pytest

pytest.importorskip("torch")

from riftbound.ai.ppo.agent import PPOAgent  # noqa: E402


class _Player:
    name = "A"


class _Loop:
    """What inner reads of a loop with no options to describe."""

    def __init__(self):
        self._in_many = True


def _agent():
    a = PPOAgent(_Player(), net=None)
    a.loop = object()          # the real game: inner asks on a copy (declaring)
    return a


def test_made_counts_on_the_same_loop():
    a = _agent()
    loop = _Loop()
    a.inner(loop, "target:x", [], 0, None)
    a.inner(loop, "target:x", [], 0, None)
    assert a._many[1] == 1


def test_made_restarts_on_a_new_loop_at_a_reused_address():
    a = _agent()
    first = _Loop()
    old = id(first)
    a.inner(first, "target:x", [], 0, None)
    del first
    gc.collect()
    keep, second = [], None
    for _ in range(1000):          # CPython hands the freed block back almost at once
        x = _Loop()
        if id(x) == old:
            second = x
            break
        keep.append(x)
    if second is None:
        pytest.skip("no address reused in 1000 tries: the case can't be built here")
    a.inner(second, "target:x", [], 0, None)
    assert a._many[1] == 0
