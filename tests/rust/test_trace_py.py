"""La traccia Python (riftbound/rs/trace_py.py) non cambia la partita."""
import json

import pytest

torch = pytest.importorskip("torch")


def _net(seed=1):
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(seed)
    return PPONet().eval()


def _agents(net, seed):
    from riftbound.ai.ppo.agent import PPOAgent
    return {s: (lambda p, s=s: PPOAgent(p, net, sample=True, seed=seed * 2 + (s == "B"))) for s in ("A", "B")}


@pytest.mark.parametrize("seed", [1_000_003, 1_000_004])
def test_traced_game_plays_the_same(seed):
    from riftbound.ai.ppo.agent import PPOChooser
    from riftbound.ai.ppo.collect import EVE, KHA
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    from riftbound.rs.canon import canonical_state, first_diff
    from riftbound.rs.trace_py import traced_game

    torch.set_num_threads(1)
    net = _net()
    gs = build_game(game_seed=seed, deck_a_path=EVE, deck_b_path=KHA, ai_a=None, ai_b=None, max_turns=40,
                    first_player="a")
    for s, f in _agents(net, seed).items():
        gs.get_player(s).agent = f(gs.get_player(s))
    loop = GameLoop(gs)
    loop.chooser = PPOChooser(gs)
    res = loop.start()
    plain = canonical_state(gs)

    res2, tr = traced_game(seed, EVE, KHA, _agents(net, seed), starter="a")
    assert (res.winner, res.turns) == (res2.winner, res2.turns)
    traced = canonical_state(tr.gs)        # fresh ids: they depend on the dumps' history
    d = first_diff(plain["root"], traced["root"])
    assert d is None or d[0] == ("$rng",), d     # the recording RNG is a different object, same state
    kinds = {e["k"] for e in tr.events}
    assert {"decision", "choice", "start", "end"} <= kinds
    json.dumps(tr.events)
