"""Coach mode: the net searches, a coach decides; coached decisions are saved as
training examples. torch-gated."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.coach import CoachSession, load_coach_examples  # noqa: E402
from riftbound.ai.encoding import ACTION_DIM, OBS_DIM  # noqa: E402
from riftbound.ai.net import RiftboundNet, save_checkpoint  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ZED = REPO / "riftbound" / "data" / "decks" / "precon_zed.json"
SHEN = REPO / "riftbound" / "data" / "decks" / "precon_shen.json"


def _session(tmp_path) -> CoachSession:
    torch.manual_seed(0)
    save_checkpoint(RiftboundNet(), tmp_path / "net.pt")
    return CoachSession(tmp_path / "net.pt", tmp_path / "coach", iterations=4, opponent_pause=0)


def _play(session: CoachSession, pick, timeout: float = 120.0) -> None:
    """Answer every request with pick(pending) until the game is over."""
    end = time.time() + timeout
    while time.time() < end:
        st = session.state()
        if st["status"] == "over":
            return
        if st["status"] == "waiting" and st["pending"] is not None:
            session.answer(pick(st["pending"]))
        time.sleep(0.005)
    raise AssertionError("the coached game didn't end")


def test_a_coached_game_saves_its_decisions(tmp_path):
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="A", opponent="simple_trade", seed=3)
    seen = []

    def pick(pending):
        seen.append(pending["type"])
        if pending["type"] == "mulligan":
            # The opening hand, and the net's best mulligans (keep-all among them).
            assert len(pending["hand"]) == 4 and pending["max"] == 2
            assert 1 <= len(pending["suggestions"]) <= 3
            assert all(len(s["return"]) <= 2 and s["text"] for s in pending["suggestions"])
            return {"return": [0]}
        if pending["type"] == "choice":
            assert all(o["text"] for o in pending["options"])
            return {"option": pending["default"]}
        # Every move is described in Italian, the net's ideas point at moves.
        assert all(a["text"] for a in pending["actions"]) and pending["context"]
        assert all(0 <= s["action"] < len(pending["actions"]) for s in pending["suggestions"])
        # Mostly the net's move; now and then the last legal action instead.
        if len(seen) % 4 == 0:
            return {"action": len(pending["actions"]) - 1}
        return {"suggestion": 0}

    _play(session, pick)
    st = session.state()
    assert st["result"] and "error" not in st["result"], st["result"]
    assert "decision" in seen and seen[0] == "mulligan"
    texts = [e["text"] for e in st["events"]]
    assert any(t.startswith("Mulligan: Rimanda ") for t in texts)
    # The opponent's mulligan is told once the game is over.
    assert texts[-1].startswith("Mulligan dell'avversario: ")
    files = list((tmp_path / "coach").glob("coach_*.npz"))
    assert len(files) == 1
    examples = load_coach_examples(tmp_path / "coach")
    assert len(examples) == st["decisions"] > 0
    for e in examples:
        assert e["state"].shape == (OBS_DIM,) and e["policy"].shape == (ACTION_DIM,)
        assert e["policy"].sum() == 1.0 and e["mask"][e["policy"].argmax()]
        assert e["z"] in (-1.0, 0.0, 1.0)
    assert st["corrections"] > 0
    assert st["observation"]["my_hand"] is not None and st["log"]
    # The Italian log tells both players' moves and what happened.
    moves = {e["who"] for e in st["events"] if e["move"]}
    assert moves == {"me", "opp"} and any(e["who"] == "turn" for e in st["events"])
    assert st["board"]["runes"]["me"] and all(c["img"] for c in st["cards"].values())


def test_an_abandoned_game_saves_nothing_and_a_report_is_kept(tmp_path):
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="B", opponent="simple_trade", seed=5)
    end = time.time() + 60
    while session.state()["status"] != "waiting" and time.time() < end:
        time.sleep(0.005)
    path = session.report("Questo Shen non dovrebbe poter attaccare")
    assert path.exists() and "Shen" in path.read_text(encoding="utf-8")
    session.abandon()
    while session.state()["status"] != "over" and time.time() < end + 60:
        time.sleep(0.01)
    assert session.state()["status"] == "over"
    assert not list((tmp_path / "coach").glob("coach_*.npz"))


def test_training_mixes_in_the_coached_decisions(tmp_path):
    import json
    from riftbound.ai.selfplay import train
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="A", opponent="simple_trade", seed=3)
    _play(session, lambda p: {"option": p["default"]} if p["type"] == "choice" else {"suggestion": 0})
    net = RiftboundNet()
    train(net, [ZED, SHEN], iterations=1, games_per_iter=1, mcts_iters=2, batch_size=8,
          checkpoint=tmp_path / "run" / "net.pt", log_path=tmp_path / "log.jsonl", workers=0,
          eval_every=0, max_turns=8, pause=0, device=torch.device("cpu"),
          coach_dir=tmp_path / "coach", coach_fraction=0.25, log=lambda *a, **k: None)
    record = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[-1])
    assert record["coached"] == session.state()["decisions"] > 0


def test_stopping_keeps_the_coach_decisions_and_the_net_finishes_alone(tmp_path):
    import json
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="A", opponent="simple_trade", seed=3)
    end = time.time() + 120
    while time.time() < end:
        st = session.state()
        if st["status"] == "waiting" and st["pending"] is not None:
            if st["decisions"] >= 3:
                break
            p = st["pending"]
            session.answer({"option": p["default"]} if p["type"] == "choice" else {"suggestion": 0})
        time.sleep(0.005)
    assert session.forget_last()                 # "I misread that card"
    kept = session.state()["decisions"]
    session.finish(save=True)
    while session.state()["status"] != "over" and time.time() < end + 120:
        time.sleep(0.01)
    st = session.state()
    assert st["result"] and "error" not in st["result"] and st["autoplay"]
    # Only the coach's own decisions are saved, not the moves the net made alone.
    assert len(load_coach_examples(tmp_path / "coach")) == kept == 2
    record = json.loads((tmp_path / "coach" / "games.jsonl").read_text().splitlines()[-1])
    assert record["decisions"] == 2 and record["finished_by_net"]


def test_while_moving_units_the_page_says_the_showdown_comes_next():
    import random
    from riftbound.ai.coach import _board_extras, action_info
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    loop = GameLoop(gs)
    gs.battlefields[0].add_unit("B", UnitInPlay(card=UnitCard(name="Wall", might=4), ready=True))
    a.base_units.extend([UnitInPlay(card=UnitCard(name=n, might=2), ready=True) for n in ("Zed", "Poro")])
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    texts = [action_info(loop, "A", "A", DecisionPoint.TURN_ACTION, ga.to_engine())["text"]
             for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")]
    assert texts == ["Fatto: parte lo showdown su campo 1", "Manda anche Poro dalla base a campo 1"]
    assert _board_extras(gs, "A")["moving"] == {"bf": 0, "who": "me"}


def test_a_fight_shows_the_might_with_assault_and_shield():
    """The first coached Shen game: the page said 11 vs 8, the fight was 14 vs
    12 (Shadow Fiend's ASSAULT 3, Shen's SHIELD, Disciple of Shen's SHIELD 3)."""
    import random
    from riftbound.ai.coach import _board_extras
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.loop import GameLoop
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    from riftbound.registry.cards_registry import CARD_REGISTRY
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    loop = GameLoop(gs)
    units = {n: UnitInPlay(card=CARD_REGISTRY[n].instantiate()) for n in (
        "Shadow Fiend", "Shadowblade Lurker", "Blade Twirler",
        "Shen Leader of the Kinkou Order", "Disciple of Shen")}
    units["Shadow Fiend"].empowered = True
    for n, u in units.items():
        gs.battlefields[0].add_unit("B" if "Shen" in n else "A", u)
    loop._recompute_passives()
    assert _board_extras(gs, "A")["fight"] == {"0": {"me": 14, "opp": 12}}


def test_the_log_tells_a_battlefield_discard_and_draw():
    from riftbound.ai.coach import _board_events
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.decisions import Observation
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    gs = next(g for g in (build_game(game_seed=s, deck_a_path=ZED, deck_b_path=SHEN, ai_a=None, ai_b=None)
                          for s in range(1, 40))
              if any(bf.card is not None and bf.card.name == "Zaun Warrens" for bf in g.battlefields))
    i = next(k for k, bf in enumerate(gs.battlefields) if bf.card.name == "Zaun Warrens")
    loop, a = GameLoop(gs), gs.A
    for _ in range(3):
        a.draw()
    a.base_units.append(UnitInPlay(card=UnitCard(name="Probe", might=2), ready=True))
    gs.active = "A"
    before = Observation.from_state(gs, "A").to_dict()
    loop._apply_action(a, ("MOVE", 0, len(gs.battlefields), i))
    loop._apply_action(a, ("PASS", None, None))      # done moving: conquer, discard 1, draw 1
    lines = [t for _, t in _board_events(before, Observation.from_state(gs, "A").to_dict())]
    assert any(t.startswith("Scarti ") for t in lines) and any(t.startswith("Peschi ") for t in lines)
    assert "Ora controlli Zaun Warrens" in lines


def test_the_net_passes_when_its_move_isnt_clearly_better():
    from types import SimpleNamespace
    from riftbound.ai.net_mcts import _PASS, NetGuidedMCTSAgent, _Node
    agent = NetGuidedMCTSAgent(SimpleNamespace(name="A"), RiftboundNet(), iterations=1)
    agent.gs = SimpleNamespace(pending_move=None)

    def node(n, q):
        x = _Node()
        x.N, x.W = n, n * q
        return x
    tank = ("ABILITY", "ACTIVATED", 0)
    root = _Node()
    root.children = {tank: node(70, 0.10), _PASS: node(10, 0.095)}   # a free TANK nobody uses
    assert agent.prefer_pass(root, tank) == _PASS
    root.children[tank] = node(70, 0.20)                             # clearly better: play it
    assert agent.prefer_pass(root, tank) == tank
    root.children[tank] = node(70, 0.10)
    agent.gs.pending_move = (0, "A")                                 # PASS would start a showdown
    assert agent.prefer_pass(root, tank) == tank
    agent.gs.pending_move = None
    fiend = ("UNIT", 2, 0)                                           # a 2-drop on turn 2: play it
    root.children = {fiend: node(64, -0.79), _PASS: node(26, -0.72)}
    assert agent.prefer_pass(root, fiend) == fiend


def test_the_log_says_where_burned_cards_come_from():
    from riftbound.ai.coach import _board_events
    from riftbound.core.decisions import Observation
    from riftbound.core.game_factory import build_game
    gs = build_game(game_seed=1, deck_a_path=ZED, deck_b_path=SHEN, ai_a=None, ai_b=None)
    a = gs.A
    a.draw()
    before = Observation.from_state(gs, "A").to_dict()
    a.burn(2)
    a.draw()
    lines = [t for _, t in _board_events(before, Observation.from_state(gs, "A").to_dict())]
    assert sum(t.startswith("Dal mazzo al cimitero: ") for t in lines) == 2
    assert sum(t.startswith("Peschi ") for t in lines) == 1
