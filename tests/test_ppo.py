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


def test_archive_games_balance_seat_and_starter():
    """The pilot's defect (revisione esterna, 22/11): against an archived
    checkpoint the learner always started. Now the four cells are balanced."""
    import importlib.util
    from collections import Counter
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "ppo_script", Path(__file__).resolve().parents[1] / "scripts/ppo.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    class Always:                     # every game against the archive
        def random(self):
            return 0.0

        def choice(self, xs):
            return xs[0]

        def randrange(self, n):
            return 0

    for start in (0, 64, 128):
        new = Counter((seat, starter) for _, starter, _, seat, _ in
                      m.batch_games(start, 64, 1, ["ckpt"], Always(), "bilanciata"))
        assert new == {("A", "a"): 16, ("A", "b"): 16, ("B", "a"): 16, ("B", "b"): 16}
        old = Counter((seat, starter) for _, starter, _, seat, _ in
                      m.batch_games(start, 64, 0, ["ckpt"], Always(), "vecchia"))
        assert set(old) == {("A", "a"), ("B", "b")}


def test_three_deck_mix_balanced_within_matchup():
    """--mazzi ekr (22/11): 50/25/25 over Evelynn-Kha'Zix, Evelynn-Rengar,
    Kha'Zix-Rengar; who starts alternates within each matchup in self-play,
    and against the archive the four cells are balanced within each matchup.
    "ek" keeps the old games exactly."""
    import importlib.util
    import random
    from collections import Counter
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "ppo_script", Path(__file__).resolve().parents[1] / "scripts/ppo.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    class Never:                      # every game against itself
        def random(self):
            return 1.0

        def randrange(self, n):
            return 0

    class Always(Never):              # every game against the archive
        def random(self):
            return 0.0

        def choice(self, xs):
            return xs[0]

    games = [g for start in range(0, 256, 64) for g in m.batch_games(start, 64, 7, [], Never(), mazzi="ekr")]
    assert Counter(g[4] for g in games) == {"EK": 128, "ER": 64, "KR": 64}
    assert Counter((g[4], g[1]) for g in games) == {("EK", "a"): 64, ("EK", "b"): 64, ("ER", "a"): 32,
                                                    ("ER", "b"): 32, ("KR", "a"): 32, ("KR", "b"): 32}
    games = [g for start in range(0, 256, 64) for g in m.batch_games(start, 64, 7, ["c"], Always(), mazzi="ekr")]
    cells = Counter((g[4], g[3], g[1]) for g in games)
    for mu, n in (("EK", 32), ("ER", 16), ("KR", 16)):
        assert all(cells[(mu, seat, stt)] == n for seat in "AB" for stt in "ab")
    # "ekri" (23/11): 6 EK, 3 ER, 3 KR, 4 EI, 4 KI, 4 RI every 24 games.
    games = [g for start in range(0, 768, 64) for g in m.batch_games(start, 64, 9, [], Never(), mazzi="ekri")]
    assert Counter(g[4] for g in games) == {"EK": 192, "ER": 96, "KR": 96, "EI": 128, "KI": 128, "RI": 128}
    assert all(sum(g[1] == "a" for g in games if g[4] == mu) * 2 == n
               for mu, n in Counter(g[4] for g in games).items())
    games = [g for start in range(0, 768, 64) for g in m.batch_games(start, 64, 9, ["c"], Always(), mazzi="ekri")]
    cells = Counter((g[4], g[3], g[1]) for g in games)
    for mu in ("EK", "ER", "KR", "EI", "KI", "RI"):    # 64 is not a multiple of 24: at most 1 per batch off
        xs = [cells[(mu, seat, stt)] for seat in "AB" for stt in "ab"]
        assert max(xs) - min(xs) <= 12
    # "ekris" (23/11): "ekri" on half the games, each Sett matchup an eighth.
    games = [g for start in range(0, 1536, 64) for g in m.batch_games(start, 64, 11, [], Never(), mazzi="ekris")]
    assert Counter(g[4] for g in games) == {"EK": 192, "ER": 96, "KR": 96, "EI": 128, "KI": 128, "RI": 128,
                                            "ES": 192, "KS": 192, "RS": 192, "IS": 192}
    assert all(sum(g[1] == "a" for g in games if g[4] == mu) * 2 == n
               for mu, n in Counter(g[4] for g in games).items())
    # "ek": as before the option, starter by the game's index in self-play.
    a = m.batch_games(64, 64, 1, ["c", "d"], random.Random(3))
    assert all(g[4] == "EK" for g in a)
    assert [g[1] for g in a if g[2] == "self"] == ["a" if (g[0] - 1_000_000) % 2 == 0 else "b"
                                                 for g in a if g[2] == "self"]


@pytest.fixture
def ppo_worker(monkeypatch):
    from scripts import ppo

    monkeypatch.setattr(ppo, "_NETS", {})
    return ppo


@pytest.mark.parametrize("panel_first", [False, True])
def test_archive_and_anchor_with_same_name_keep_their_weights(ppo_worker, monkeypatch, panel_first):
    from riftbound.ai.ppo import collect

    worker = ppo_worker
    model = PPONet(hidden=8, card_dim=4, opt_dim=8)
    with torch.no_grad():
        model.q_embed.weight[0, 0] = 1.0
        archive = worker._blob(model)
        model.q_embed.weight[0, 0] = 2.0
        anchor = worker._blob(model)
    name = "ckpt_030016"
    observed = []

    def capture_opponent(seed, nets, learners, **kwargs):
        observed.append(nets["B"].q_embed.weight[0, 0].item())
        return {"winner": "A", "records": {}, "turns": 0, "counts": {}}

    monkeypatch.setattr(collect, "play", capture_opponent)
    train = ([(42, "a", name, "A", "EI")], ("w1", archive), {name: archive}, 0.98)
    panel = ([(42, "A", "a", "ancora", name, "EI")], ("misura1", archive), {name: anchor})
    calls = [(worker._collect, train), (worker._eval, panel)]
    for call, args in reversed(calls) if panel_first else calls:
        call(args)
    assert observed == ([2.0, 1.0] if panel_first else [1.0, 2.0])


def test_homonymous_external_anchors_both_reach_the_panel(ppo_worker, tmp_path):
    from riftbound.ai.ppo.model import save

    model = PPONet(hidden=8, card_dim=4, opt_dim=8)
    paths = [tmp_path / label / "ckpt_030016.pt" for label in ("ivern", "sett")]
    paths.append(tmp_path / "ckpt_020032.pt")
    for marker, path in enumerate(paths):
        path.parent.mkdir(exist_ok=True)
        with torch.no_grad():
            model.q_embed.weight[0, 0] = marker
        save(model, path)
    anchors = ppo_worker._load_anchors(paths)
    assert list(anchors) == [str(paths[0]), str(paths[1]), "ckpt_020032"]
    for marker, (key, blob) in enumerate(anchors.items()):
        cached = ppo_worker._net(blob, ("anchor", key))
        assert cached.q_embed.weight[0, 0].item() == marker
