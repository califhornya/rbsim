"""The net and the hand's order (S6), and Evelynn's draw still free (S11a/S11b).

S6: Pyke Returned and Gutter Guardian swapped in the hand, the same
preference for each card, in what the net learns and in how the bot plays.
S11a/S11b: the same position, Evelynn's "once each turn" draw free in S11a and
used in S11b: the encodings differ there, and only there."""
from __future__ import annotations

import random

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.encoding import (  # noqa: E402
    DENSE_DIM,
    action_to_index,
    encode_observation,
    legal_mask,
)
from riftbound.ai.handwritten import NetAgent  # noqa: E402
from riftbound.ai.net import RiftboundNet, masked_log_softmax, predict  # noqa: E402
from riftbound.ai.scenari import (  # noqa: E402
    ScriptedChooser,
    ScriptedSeat,
    _plan,
    build_state,
    get_scenario,
)
from riftbound.core.decisions import Observation  # noqa: E402
from riftbound.core.legality import legal_actions  # noqa: E402
from riftbound.core.loop import GameLoop  # noqa: E402
from riftbound.core.state import determinize  # noqa: E402


class _At(Exception):
    def __init__(self, gs, side, point):
        super().__init__("at")
        self.gs, self.side, self.point = gs, side, point


def _at_decision(sid: str):
    """The game at the human's first decision of the scenario (a copy)."""
    sc = get_scenario(sid)
    gs = build_state(sc)
    plan = _plan(sc)

    def human(agent, point, bf_idx):
        raise _At(agent.gs.clone(), agent.player.name, point)
    for side in ("A", "B"):
        p = gs.get_player(side)
        p.agent = ScriptedSeat(p, sc, plan, human=human if side == sc["human"] else None)
    loop = GameLoop(gs)
    loop.chooser = ScriptedChooser(plan, sc["id"])
    with pytest.raises(_At) as at:
        loop.start()
    return at.value.gs, at.value.side, at.value.point


def _legal(gs, side, point):
    return legal_actions(GameLoop(gs), point, side)


def _swapped(gs, side, a="Pyke Returned", b="Gutter Guardian"):
    g = gs.clone()
    hand = g.get_player(side).hand
    i = next(k for k, c in enumerate(hand) if c.name == a)
    j = next(k for k, c in enumerate(hand) if c.name == b)
    hand[i], hand[j] = hand[j], hand[i]
    return g


def _by_label(net, gs, side, point):
    legal = _legal(gs, side, point)
    n_bf = len(gs.battlefields)
    probs, _ = predict(net, encode_observation(Observation.from_state(gs, side)), legal_mask(legal, n_bf))
    out: dict = {}
    for a in legal:
        i = action_to_index(a, n_bf)
        if i is not None:
            out[a.label] = float(probs[i])
    return out


@pytest.fixture(scope="module")
def s6():
    return _at_decision("S6")


def test_s6_the_swap_moves_the_slots(s6):
    gs, side, point = s6
    sw = _swapped(gs, side)
    n_bf = len(gs.battlefields)
    before = {a.label: action_to_index(a, n_bf) for a in _legal(gs, side, point)}
    after = {a.label: action_to_index(a, n_bf) for a in _legal(sw, side, point)}
    pyke = [k for k in before if k.startswith("Play Pyke Returned")]
    assert pyke and all(before[k] != after[k] for k in pyke)       # a different slot
    assert set(before) == set(after)


def test_s6_same_preference_for_the_same_card(s6):
    gs, side, point = s6
    torch.manual_seed(0)
    net = RiftboundNet().eval()
    before, after = _by_label(net, gs, side, point), _by_label(net, _swapped(gs, side), side, point)
    assert set(before) == set(after)
    for k in before:
        assert before[k] == pytest.approx(after[k], abs=1e-6), k


def test_s6_what_is_learned_goes_with_the_card(s6):
    """A few steps on S6's position with "play Pyke Returned" as the target:
    with the hand swapped the net picks Pyke Returned too."""
    gs, side, point = s6
    legal = _legal(gs, side, point)
    n_bf = len(gs.battlefields)
    target = next(a for a in legal if a.label.startswith("Play Pyke Returned"))
    x = torch.as_tensor(encode_observation(Observation.from_state(gs, side)))[None]
    m = torch.as_tensor(legal_mask(legal, n_bf))[None]
    p = torch.as_tensor([action_to_index(target, n_bf)])
    torch.manual_seed(0)
    net = RiftboundNet()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    for _ in range(30):
        loss = -masked_log_softmax(net(x)[0], m).gather(1, p[:, None]).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.eval()
    for g in (gs, _swapped(gs, side)):
        got = _by_label(net, g, side, point)
        assert max(got, key=got.get) == target.label


def test_s6_the_bot_s_priors_go_with_the_card(s6):
    """The net's search (NetAgent) reads the same priors per card."""
    gs, side, point = s6
    torch.manual_seed(1)
    net = RiftboundNet().eval()
    pri = []
    for g in (gs, _swapped(gs, side)):
        agent = NetAgent(g.get_player(side), net, rng=random.Random(0))
        legal = _legal(g, side, point)
        priors, _ = agent._evaluate(g, side, legal)
        label = {a.to_engine(): a.label for a in legal}
        pri.append({label[t]: v for t, v in priors.items()})
    assert set(pri[0]) == set(pri[1])
    for k in pri[0]:
        assert pri[0][k] == pytest.approx(pri[1][k], abs=1e-6), k


def test_s11_the_net_sees_whether_evelynn_can_still_draw():
    a_gs, a_side, a_point = _at_decision("S11a")
    b_gs, b_side, b_point = _at_decision("S11b")
    assert a_side == b_side == "B" and a_point == b_point
    oa, ob = Observation.from_state(a_gs, "B"), Observation.from_state(b_gs, "B")
    assert oa.my_legend_once_free and not ob.my_legend_once_free
    assert Observation.from_state(a_gs, "A").opp_legend_once_free
    assert not Observation.from_state(b_gs, "A").opp_legend_once_free
    va, vb = encode_observation(oa), encode_observation(ob)
    diff = np.flatnonzero(va != vb)
    assert len(diff) == 1 and diff[0] < DENSE_DIM                  # that feature only
    # The same in the search's copies, the hidden cards drawn again.
    for gs, free in ((a_gs, True), (b_gs, False)):
        c = gs.clone()
        determinize(c, observer="B", rng=random.Random(3))
        assert Observation.from_state(c, "B").my_legend_once_free is free
        assert encode_observation(Observation.from_state(c, "B"))[diff[0]] == float(free)
