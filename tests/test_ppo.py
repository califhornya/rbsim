"""The PPO pilot's first checks (21/11, revisione esterna): every menu met is
described (all five sparring decks), the PPO ratio is 1 before the first
update (the saved menus re-evaluated), returns have the right sign for both
seats (gamma = lambda = 1: advantage = the seat's result - value), and the
state a decision sees doesn't depend on the order of what is hidden."""
import random

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.encoding import encode_observation  # noqa: E402
from riftbound.ai.ppo.collect import DECKS, gae, play  # noqa: E402
from riftbound.ai.ppo.model import PPONet  # noqa: E402
from riftbound.ai.ppo.train import evaluate, tensors  # noqa: E402
from riftbound.core.decisions import Observation  # noqa: E402

FIVE = ["competitive_evelynn", "competitive_khazix", "competitive_ivern", "competitive_sett",
        "competitive_rengar"]


@pytest.fixture(scope="module")
def net():
    torch.manual_seed(0)
    return PPONet().eval()


def test_every_option_of_the_five_decks_is_described(net):
    for i, a in enumerate(FIVE):
        b = FIVE[(i + 1) % len(FIVE)]
        g = play(500 + i, {"A": net, "B": net}, {}, deck_a=DECKS / f"{a}.json", deck_b=DECKS / f"{b}.json")
        assert g["counts"]["decisioni"] > 20
        assert g["counts"]["opzioni sconosciute"] == 0, (a, b)


def test_ratio_is_one_before_the_first_update(net):
    g = play(11, {"A": net, "B": net}, {"A": True, "B": True})
    recs = g["records"]["A"] + g["records"]["B"]
    assert len(recs) > 20
    with torch.no_grad():
        logp, _, _ = evaluate(net, tensors(recs))
    old = torch.as_tensor(np.array([r["logp"] for r in recs], dtype=np.float32))
    assert torch.allclose(torch.exp(logp - old), torch.ones_like(old), atol=1e-3)


def test_returns_have_the_sign_of_each_seats_result(net):
    g = play(12, {"A": net, "B": net}, {"A": True, "B": True})
    assert g["winner"] in ("A", "B", "DRAW")
    for seat in ("A", "B"):
        recs = g["records"][seat]
        gae(recs, g["z"][seat], gamma=1.0, lam=1.0)
        for r in recs:
            assert r["adv"] == pytest.approx(g["z"][seat] - r["v"], abs=1e-6)
            assert r["ret"] == pytest.approx(g["z"][seat], abs=1e-6)
    if g["winner"] != "DRAW":
        loser = "B" if g["winner"] == "A" else "A"
        assert g["records"][g["winner"]][-1]["ret"] == 1.0
        assert g["records"][loser][-1]["ret"] == -1.0


def test_the_state_doesnt_see_the_order_of_hidden_cards():
    from riftbound.core.game_factory import build_game
    gs = build_game(game_seed=3, deck_a_path=DECKS / "competitive_evelynn.json",
                    deck_b_path=DECKS / "competitive_khazix.json", ai_a=None, ai_b=None, max_turns=40)
    other = gs.clone()
    random.Random(1).shuffle(other.A.deck.cards)
    random.Random(2).shuffle(other.B.deck.cards)
    random.Random(3).shuffle(other.A.rune_deck.runes)
    assert np.array_equal(encode_observation(Observation.from_state(gs, "A")),
                          encode_observation(Observation.from_state(other, "A")))
