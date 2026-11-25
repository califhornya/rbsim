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
        if pending["type"] == "notice":
            # An opponent's spell or ability the coach can't answer: shown
            # before it resolves.
            assert pending["context"].startswith((f"L'avversario ha lanciato {pending['card']}",
                                                  f"L'avversario ha usato abilità di {pending['card']}",
                                                  f"L'avversario ha innescato abilità di {pending['card']}"))
            return {"ok": True}
        # Every move is described in Italian, the net's ideas point at moves,
        # each idea once (two copies of a card are one idea).
        assert all(a["text"] for a in pending["actions"]) and pending["context"]
        assert all(0 <= s["action"] < len(pending["actions"]) for s in pending["suggestions"])
        texts = [s["text"] for s in pending["suggestions"]]
        assert len(texts) == len(set(texts))
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
        x.N, x.W, x.Q = n, n * q, q
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


def test_a_suggested_move_names_the_unit_it_moves():
    """Twilight Step "Move a unit with 3 [might] or less": the net searches the
    destination; the only unit that qualifies is named in the advice too."""
    import random
    from riftbound.ai.coach import _choice_preview
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.enums import Domain
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    from riftbound.registry.cards_registry import CARD_REGISTRY
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    a.energy = 6
    a.add_power(Domain.CHAOS, 3)
    a.hand = [CARD_REGISTRY["Twilight Step"].instantiate()]
    a.base_units.append(UnitInPlay(card=CARD_REGISTRY["Shadow Order Disciple"].instantiate()))
    b.base_units.append(UnitInPlay(card=CARD_REGISTRY["Kinkou Lifeblade"].instantiate()))
    seen = _choice_preview(gs, "A", ("SPELL", 0, 1), ("destination:move_unit", "Twilight Step", "battlefield 1"), 0)
    assert seen["text"].startswith("bersaglio: Shadow Order Disciple (tua")
    assert seen["text"].endswith("verso: campo 2") and seen["ref"] == "bf:1"


def test_the_advice_names_the_card_of_a_you_may_and_banishes_are_logged():
    """ "Fatto: parte lo showdown" carried Shadow Clone's "you may banish a unit
    from your trash" (searched in the combat it starts) as a bare "Usare questo
    effetto? Sì"; the banished card wasn't in the log either."""
    import random
    from riftbound.ai.coach import _board_events, _choice_preview
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.decisions import Observation
    from riftbound.core.loop import GameLoop
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    from riftbound.registry.cards_registry import CARD_REGISTRY
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    loop = GameLoop(gs)
    a.trash = [CARD_REGISTRY["Punching Poro"].instantiate()]
    gs.battlefields[0].add_unit("B", UnitInPlay(card=UnitCard(name="Wall", might=3)))
    clone = UnitInPlay(card=CARD_REGISTRY["Shadow Clone"].instantiate(), ready=True)
    clone.is_token = True
    a.base_units.append(clone)
    loop._apply_action(a, ("MOVE", 0, 2, 0))                 # held: the showdown waits
    seen = _choice_preview(gs, "A", ("PASS", None, None), ("optional:give_temporary_assault", "Shadow Clone", "yes"), 0)
    assert seen["text"] == "Shadow Clone: Usare questo effetto? Sì"
    before = Observation.from_state(gs, "A").to_dict()
    loop._apply_action(a, ("PASS", None, None))
    lines = [t for _, t in _board_events(before, Observation.from_state(gs, "A").to_dict())]
    assert "Bandita una tua carta: Punching Poro" in lines


def test_an_opponent_discard_then_draw_is_not_a_burn():
    """Traveling Merchant "discard 1 then draw 1" for the opponent read as
    "Dal mazzo avversario al cimitero" (its hand is hidden, the count stays)."""
    import random
    from riftbound.ai.coach import _board_events
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.decisions import Observation
    from riftbound.core.loop import GameLoop
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name="Top")]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    loop = GameLoop(gs)
    b.hand = [UnitCard(name="Twilight Reveler")]
    before = Observation.from_state(gs, "A").to_dict()
    loop._discard(b, b.hand[0])
    b.draw()
    after = Observation.from_state(gs, "A").to_dict()
    lines = [t for _, t in _board_events(before, after, ["Twilight Reveler"])]
    assert lines == ["L'avversario scarta Twilight Reveler", "L'avversario pesca 1 carta"]


def test_an_opponent_spell_the_coach_cant_answer_holds_the_board(tmp_path):
    """Coach note 2026-10-26: the opponent's spells went by too fast. With no
    reaction to play the coach still sees the spell on the chain ("notice"),
    until "Continua"; "quiet" stops it for the rest of the game."""
    import random
    import threading
    from riftbound.ai.coach import CoachAgent
    from riftbound.ai.net_mcts import _PASS
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    from riftbound.core.state import ChainItem
    from riftbound.registry.cards_registry import CARD_REGISTRY
    session = _session(tmp_path)
    gs = build_game(game_seed=1, deck_a_path=ZED, deck_b_path=SHEN, ai_a=None, ai_b=None)
    gs.A.agent = CoachAgent(gs.A, RiftboundNet(), session, iterations=2, rng=random.Random(0))
    session.gs, session.side, session.loop = gs, "A", GameLoop(gs)
    gs.chain.append(ChainItem(player="B", card=CARD_REGISTRY["Charm"].instantiate(), bf_idx=0))
    out = []

    def react():
        out.append(gs.A.agent.decide_reaction(gs.B, gs.chain))
    thread = threading.Thread(target=react)
    thread.start()
    end = time.time() + 30
    while session.state()["pending"] is None and time.time() < end:
        time.sleep(0.005)
    pending = session.state()["pending"]
    assert pending["type"] == "notice" and pending["card"] == "Charm"
    assert pending["context"].startswith("L'avversario ha lanciato Charm")
    session.answer({"ok": True, "quiet": True})
    thread.join(timeout=30)
    assert out == [_PASS] and not session.stop_on_opp_chain
    # Quiet: the next one goes by without stopping.
    assert gs.A.agent.decide_reaction(gs.B, gs.chain) == _PASS


def test_the_log_names_the_opponents_target_and_the_coachs_only_option(tmp_path):
    from types import SimpleNamespace

    from riftbound.core.game_factory import build_game
    from riftbound.core.combat import UnitInPlay
    from riftbound.registry.cards_registry import CARD_REGISTRY
    session = _session(tmp_path)
    gs = build_game(game_seed=1, deck_a_path=ZED, deck_b_path=SHEN, ai_a=None, ai_b=None)
    session.gs, session.side = gs, "A"
    poro = UnitInPlay(card=CARD_REGISTRY["Punching Poro"].instantiate(), ready=True)
    gs.battlefields[0].add_unit("A", poro)
    gs.A.hand.append(CARD_REGISTRY["Twilight Step"].instantiate())
    charm, warrens = SimpleNamespace(name="Charm"), SimpleNamespace(name="Zaun Warrens")
    session._log_choice("target", "B", 1, poro, charm)
    session._log_choice("discard", "A", len(gs.A.hand), gs.A.hand[0], warrens)
    session._log_choice("target", "A", 2, poro, charm)     # asked on the page
    session._log_choice("keep", "B", 1, poro, charm)     # hidden
    texts = [(e["who"], e["text"]) for e in session.state()["events"]]
    assert texts == [
        ("opp", f"Charm: bersaglio → Punching Poro (tua, Might 2, su {gs.battlefields[0].card.name})"),
        ("me", "Zaun Warrens: scarta → Twilight Step (magia, costo 2) (unica scelta)")]


def test_two_battlefields_with_one_name_say_which():
    from riftbound.ai.coach import _view_bf_names
    same = [{"named": "Threshold of the Gray"}, {"named": "Threshold of the Gray"}]
    assert _view_bf_names(same) == ["Threshold of the Gray (sinistra)", "Threshold of the Gray (destra)"]
    assert _view_bf_names([{"named": "Zaun Warrens"}, {"named": None}]) == ["Zaun Warrens", "campo 2"]


def test_a_second_answer_to_one_question_is_refused(tmp_path):
    """An answer sent twice (a double click) isn't kept for the next question."""
    session = _session(tmp_path)
    session.new_game(ZED, SHEN, seat="A", opponent="simple_trade", seed=3)
    end = time.time() + 60
    while session.state()["pending"] is None and time.time() < end:
        time.sleep(0.005)
    assert session.state()["pending"]["type"] == "mulligan"
    session.answer({"return": []})
    assert session.pending is None
    try:
        session.answer({"return": []})
    except RuntimeError:
        pass                      # refused, or the next question was already up
    session.abandon()


# -- the champion (24/11): Matteo plays a whole game against the strongest bot --

EVELYNN = REPO / "riftbound" / "data" / "decks" / "competitive_evelynn.json"
KHAZIX = REPO / "riftbound" / "data" / "decks" / "competitive_khazix.json"


def _campione(tmp_path) -> Path:
    """A random PPO net standing in for runs/sett/ekris_s12/ckpt_040000.pt
    (runs/ isn't in the repository)."""
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(0)
    path = tmp_path / "campione.pt"
    save(PPONet(), path)
    return path


def _wait(session: CoachSession, status: str, timeout: float = 120.0) -> None:
    end = time.time() + timeout
    while session.state()["status"] != status and time.time() < end:
        time.sleep(0.005)
    assert session.state()["status"] == status


def test_a_whole_game_against_the_champion_without_the_net(tmp_path):
    import json
    import random

    from riftbound.ai.coach import _ppo_net
    from riftbound.ai.ppo.prior_bot import PPOPriorAgent
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0,
                           campione_path=_campione(tmp_path), budget=0.02)
    st = session.state()
    assert [o["id"] for o in st["opponents"]] == ["campione", "simple_trade"] and not st["advice"]
    assert "Sett" in st["opponents"][0]["decks"]
    session.new_game(EVELYNN, KHAZIX, seat="A", seed=3)      # the first opponent: the champion
    assert isinstance(session._opponent, PPOPriorAgent) and session._opponent.budget == 0.02
    assert session._opponent.ppo is _ppo_net(session.campione_path)   # loaded once
    rng, seen = random.Random(0), []

    def pick(pending):
        seen.append(pending["type"])
        assert not pending.get("suggestions")                 # no net, no advice
        if pending["type"] == "choice":
            return {"option": rng.randrange(len(pending["options"]))}
        if pending["type"] == "notice":
            return {"ok": True}
        if pending["type"] == "mulligan":
            return {"return": [0]}
        assert all(a["text"] for a in pending["actions"]) and pending["context"]
        return {"action": rng.randrange(len(pending["actions"]))}

    _play(session, pick, timeout=300)
    st = session.state()
    assert st["result"] and "error" not in st["result"], st["result"]
    assert seen[0] == "mulligan" and "decision" in seen
    assert st["info"]["opponent"] == "campione" and st["info"]["net"] is None
    assert st["info"]["campione"] == str(session.campione_path) and st["info"]["budget"] == 0.02
    moves = {e["who"] for e in st["events"] if e["move"]}
    assert moves == {"me", "opp"}
    assert not any("rete" in e["text"] for e in st["events"])
    # Nothing for training, but the result is kept.
    assert st["decisions"] == 0 and not list((tmp_path / "coach").glob("coach_*.npz"))
    record = json.loads((tmp_path / "coach" / "games.jsonl").read_text().splitlines()[-1])
    assert record["opponent"] == "campione" and record["file"] is None and record["decisions"] == 0
    assert record["regole"] == "6427b90" and st["regole"] == "6427b90"     # the frozen Python engine
    assert record["winner"] == st["result"]["winner"] and record["turns"] == st["result"]["turns"]


def test_abandoning_the_champion_without_the_net_passes_to_the_end(tmp_path):
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0,
                           campione_path=_campione(tmp_path), budget=0.02)
    session.new_game(EVELYNN, KHAZIX, seat="B", opponent="campione", seed=5)
    end = time.time() + 120
    while (session.state()["pending"] or {}).get("type") != "decision" and time.time() < end:
        st = session.state()
        if st["pending"] is not None:
            session.answer({"option": st["pending"].get("default", 0)} if st["pending"]["type"] == "choice"
                           else {"ok": True} if st["pending"]["type"] == "notice" else {"return": []})
        time.sleep(0.005)
    assert session.state()["pending"]["type"] == "decision"
    session.abandon()
    _wait(session, "over", timeout=300)
    st = session.state()
    assert st["result"] and "error" not in st["result"], st["result"]
    assert st["autoplay"] and not st["saving"] and st["activity"].startswith("Partita lasciata")
    assert st["result"]["winner"] != "B"                       # the coach's seat only passed
    assert session._opponent.budget == 0.01                  # nothing counts: it closes quickly
    assert not (tmp_path / "coach" / "games.jsonl").exists()   # abandoned: nothing saved


def test_the_opponents_that_arent_there_are_refused(tmp_path):
    session = CoachSession(None, tmp_path / "coach", campione_path=tmp_path / "manca.pt")
    assert [o["id"] for o in session.opponents()] == ["simple_trade"]
    for who, says in (("campione", "campione"), ("net", "--net"), ("chiunque", "sconosciuto")):
        with pytest.raises(ValueError, match=says):
            session.new_game(EVELYNN, KHAZIX, opponent=who)
    assert session.state()["status"] == "idle"
    # With the net too: the champion first, then the net; the advice is on.
    torch.manual_seed(0)
    save_checkpoint(RiftboundNet(), tmp_path / "net.pt")
    session = CoachSession(tmp_path / "net.pt", tmp_path / "coach", campione_path=_campione(tmp_path))
    st = session.state()
    assert [o["id"] for o in st["opponents"]] == ["campione", "net", "simple_trade"] and st["advice"]


def _play_trifarian_captain(session: CoachSession, timeout: float = 60.0) -> list:
    """Answer PASS (or the default) until the coach may play Trifarian Captain,
    play it, then collect the questions up to the next turn action."""
    played, shown, end = False, [], time.time() + timeout
    while time.time() < end:
        st = session.state()
        if st["status"] == "over":
            break
        p = st["pending"]
        if st["status"] != "waiting" or not p:
            time.sleep(0.003)
            continue
        if p["type"] == "decision":
            i = next((k for k, a in enumerate(p["actions"]) if "Trifarian Captain" in a["text"]), None)
            if i is not None and not played:
                played = True
                session.answer({"action": i})
                continue
            if played and p["point"] == "turn_action":
                break
            session.answer({"action": next(k for k, a in enumerate(p["actions"]) if a["kind"] == "PASS")})
            continue
        if played:
            shown.append(dict(p, _cards=st["cards"]))      # the page's card metadata then
        session.answer({"option": p["default"]} if p["type"] == "choice"
                       else {"return": []} if p["type"] == "mulligan" else {"ok": True})
    session.abandon()
    assert played
    return shown


def test_the_coach_sees_the_cards_trifarian_captain_looks_at(tmp_path):
    """'Look at the top 4 cards ... you may reveal a unit or gear ... and draw
    it. Recycle the rest.' The page shows the four cards with the choice, and
    alone when none may be taken (seeds of competitive_sett, simple_trade)."""
    sett = REPO / "riftbound" / "data" / "decks" / "competitive_sett.json"
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0)
    session.new_game(sett, sett, seat="A", opponent="simple_trade", seed=2)
    shown = _play_trifarian_captain(session)
    seen = ["Rampage", "Kinkou Initiate", "Pit Rookie", "Showstopper"]
    assert [(p["question"], p.get("seen")) for p in shown[:2]] == [
        ("Prendere una delle carte guardate?", seen), ("Quale carta tenere?", seen)]
    assert "Guardi le prime 4 carte del mazzo: " + ", ".join(seen) in [e["text"] for e in session.state()["events"]]
    # The page has their image code and text, not only the board's cards.
    assert all(shown[0]["_cards"][n]["img"] and shown[0]["_cards"][n]["text"] for n in seen)
    # None of the four may be taken: shown alone, held until seen.
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0)
    session.new_game(sett, sett, seat="A", opponent="simple_trade", seed=20)
    notice = _play_trifarian_captain(session)[0]
    assert notice["type"] == "notice" and notice["own"] and \
        notice["cards"] == ["Fiora Victorious", "Fiora Victorious", "Showstopper", "Rampage"]
    assert all(notice["_cards"][n]["img"] for n in notice["cards"])


def test_the_coach_picks_which_unit_sett_the_boss_saves(tmp_path):
    """Two buffed units of the coach die together: the engine offers Sett The
    Boss's save to each in turn; the page asks once which one to save."""
    import sys
    import threading
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import legend, scripted, setup, unit

    from riftbound.ai.coach import _CoachChooser
    loop, a, b = setup(active="B")
    scripted(loop, a, b)
    boss = legend(loop, "A", "Sett The Boss")
    rookie, fiora = unit("Pit Rookie"), unit("Fiora Victorious")
    for u in (rookie, fiora):
        u.might_counters = 1
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0)
    session.gs, session.side, session.loop = loop.gs, "A", loop
    session._watch(loop)
    loop.chooser = _CoachChooser("A", session, loop, None)
    game = threading.Thread(target=loop._route_deaths,
                            args=([(rookie, "A"), (fiora, "A")], loop.gs.battlefields[0]),
                            kwargs={"in_combat": True})
    game.start()
    end = time.time() + 10
    while session.pending is None and time.time() < end:
        time.sleep(0.005)
    p = session.pending
    assert p["question"] == "Quale unità salvare?" and p["source"] == "Sett The Boss"
    assert [o["text"] for o in p["options"]] == [
        "Salva Pit Rookie (Might 3)", "Salva Fiora Victorious (Might 5)", "Non salvare nessuna"]
    session.answer({"option": 1})                     # the second one the engine meets
    game.join(timeout=10)
    assert [u.card.name for u in a.base_units] == ["Fiora Victorious"] and not boss.ready
    assert [c.name for c in a.trash] == ["Pit Rookie"] and session.pending is None


def test_sett_the_boss_offers_only_the_units_it_can_save(tmp_path):
    """A buffed unit Smite will banish if it dies this turn never reaches the
    save: it isn't offered (choosing it would lose both)."""
    import sys
    import threading
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import legend, scripted, setup, unit

    from riftbound.ai.coach import _CoachChooser
    loop, a, b = setup(active="B")
    scripted(loop, a, b)
    legend(loop, "A", "Sett The Boss")
    rookie, fiora = unit("Pit Rookie"), unit("Fiora Victorious")
    for u in (rookie, fiora):
        u.might_counters = 1
    fiora.banish_if_dies_turn = loop.gs.turn
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0)
    session.gs, session.side, session.loop = loop.gs, "A", loop
    session._watch(loop)
    loop.chooser = _CoachChooser("A", session, loop, None)
    game = threading.Thread(target=loop._route_deaths,
                            args=([(rookie, "A"), (fiora, "A")], loop.gs.battlefields[0]),
                            kwargs={"in_combat": True})
    game.start()
    end = time.time() + 10
    while session.pending is None and time.time() < end:
        time.sleep(0.005)
    assert [o["text"] for o in session.pending["options"]] == ["Salva Pit Rookie (Might 3)", "Non salvare nessuna"]
    session.answer({"option": 0})
    game.join(timeout=10)
    assert [u.card.name for u in a.base_units] == ["Pit Rookie"] and "Fiora Victorious" in [c.name for c in a.banished]


def test_punch_first_is_one_cast_and_its_unit_can_be_in_base(tmp_path):
    """Punch First gives "a unit" +5: any unit, the base's too. The menu
    offered one cast per battlefield ("campo: ..."), as if the spell were
    aimed there (Matteo, 25/11): one cast now, the unit is the next question."""
    import sys
    import threading
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import card, scripted, setup, unit

    from riftbound.ai.coach import _CoachChooser, action_info
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    loop, a, b = setup(active="A")
    scripted(loop, a, b)
    a.base_units.append(unit("Reckless Innovator"))
    bf = loop.gs.battlefields[1]
    bf.units_B.extend([unit("Pit Rookie"), unit("Sett Kingpin")])
    bf._note_control()
    a.hand.append(card("Punch First"))
    casts = [g.to_engine() for g in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if g.kind == "SPELL"]
    infos = [action_info(loop, "A", "A", DecisionPoint.TURN_ACTION, t) for t in casts]
    assert len(casts) == 2 and {(i["text"], i["dst"]) for i in infos} == {("Lancia Punch First", None)}
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0)
    session.gs, session.side, session.loop = loop.gs, "A", loop
    session._watch(loop)
    loop.chooser = _CoachChooser("A", session, loop, None)
    game = threading.Thread(target=loop._apply_action, args=(a, casts[1]))
    game.start()
    end = time.time() + 10
    while session.pending is None and time.time() < end:
        time.sleep(0.005)
    p = session.pending
    assert [o["text"] for o in p["options"]] == [
        "Reckless Innovator (tua, Might 3, in base)", "Pit Rookie (avversaria, Might 2, su campo 2)",
        "Sett Kingpin (avversaria, Might 5, su campo 2)"]
    session.answer({"option": 0})
    game.join(timeout=10)
    assert a.base_units[0].might == 8 and [u.might for u in bf.units_B] == [2, 5]


def test_a_spell_that_counts_its_battlefield_still_says_which():
    """En Garde's "+1 more if it is the only unit you control there": the
    battlefield matters, one cast for each."""
    import sys
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import card, setup, unit

    from riftbound.ai.coach import action_info
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    loop, a, _ = setup(active="A")
    loop.gs.battlefields[0].units_A.append(unit("Pit Rookie"))
    loop.gs.battlefields[1].units_A.extend([unit("Fiora Victorious"), unit("First Mate")])
    a.hand.append(card("En Garde"))
    texts = [action_info(loop, "A", "A", DecisionPoint.TURN_ACTION, g.to_engine())["text"]
             for g in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if g.kind == "SPELL"]
    assert texts == ["Lancia En Garde (campo: campo 1)", "Lancia En Garde (campo: campo 2)"]


def test_the_gold_reckless_innovator_plays_is_drawn_exhausted():
    """Reckless Innovator's Gold enters exhausted (the engine has it so); the
    page drew every gear upright, as if ready (Matteo, 25/11)."""
    import sys
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import act, choices, scripted, setup, unit

    from riftbound.ai.coach import _board_extras
    loop, a, b = setup(active="A")
    scripted(loop, a, b)
    a.base_units.append(unit("Reckless Innovator"))
    choices(loop, {"mode": lambda _loop, options: 0})          # the Gold
    act(loop, "A", "Move Reckless Innovator base→BF1")
    assert [g.name for g in a.base_gear] == ["Gold"]
    extras = _board_extras(loop.gs, "A")
    assert extras["gear_exhausted"]["me"] == {"base": [True], "0": [], "1": []}
    assert _board_extras(loop.gs, "B")["gear_exhausted"]["opp"]["base"] == [True]


def _gold_table(tmp_path, body_runes: int):
    """The coach (A, no net) with `body_runes` Body runes channeled, a ready
    Gold, Punch First in hand and Reckless Innovator in base."""
    import sys
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import card, scripted, setup, unit

    from riftbound.ai.coach import CoachAgent, CoachLoop
    from riftbound.core.player import Domain, Rune
    _, a, b = setup(active="A", rich=())
    loop = CoachLoop(_.gs)
    scripted(loop, a, b)
    a.rune_pool[Domain.BODY] = [Rune(Domain.BODY) for _ in range(body_runes)]
    a.channel()
    gold = card("Gold")
    gold.tapped = False
    a.base_gear.append(gold)
    a.base_units.append(unit("Reckless Innovator"))
    a.hand.append(card("Punch First"))
    session = CoachSession(None, tmp_path / "coach", opponent_pause=0)
    session.gs, session.side, session.loop = loop.gs, "A", loop
    session._watch(loop)
    agent = CoachAgent(a, None, session)
    a.agent, agent.gs, agent.loop = agent, loop.gs, loop
    return loop, a, b, session, agent


def _next_pending(session, end):
    while session.pending is None and time.time() < end:
        time.sleep(0.005)
    return session.pending


def test_a_card_played_with_a_gold_ready_asks_how_to_pay(tmp_path):
    """Matteo (25/11): players keep their runes and pay with Gold when they
    have one. Played straight from the hand, the card asks how to pay; the
    Gold is used first (its Power in the card's domain), then the card."""
    import threading

    from riftbound.core.player import Domain
    loop, a, b, session, agent = _gold_table(tmp_path, 3)
    game = threading.Thread(target=lambda: [loop._apply_action(a, agent.decide_action(b)) for _ in range(2)])
    game.start()
    end = time.time() + 20
    p = _next_pending(session, end)
    texts = [x["text"] for x in p["actions"]]
    session.answer({"action": texts.index("Lancia Punch First")})
    p = _next_pending(session, end)
    assert p["question"] == "Come paghi?" and p["source"] == "Punch First"
    assert [o["text"] for o in p["options"]] == ["Ricicli 2 rune Body", "Col Gold, ricicli 1 runa Body"]
    session.answer({"option": 1})
    game.join(timeout=20)
    assert not a.base_gear and len(a.rune_pool[Domain.BODY]) == 2 and a.base_units[0].might == 8
    log = [e["text"] for e in session.events if e["who"] == "me"]
    assert log[:3] == ["Punch First: Come paghi? → Col Gold, ricicli 1 runa Body",
                       "Usa Gold: Power Body per pagare Punch First", "Lancia Punch First"]


def test_a_card_only_the_gold_pays_for_is_offered_with_it(tmp_path):
    """One Body rune and a Gold: Punch First (two Body Power) is played only
    with the Gold; the engine has none of it until the Gold is used. The page
    offers it "col Gold", and plays the Gold first."""
    import threading

    from riftbound.core.player import Domain
    loop, a, b, session, agent = _gold_table(tmp_path, 1)
    game = threading.Thread(target=lambda: [loop._apply_action(a, agent.decide_action(b)) for _ in range(2)])
    game.start()
    end = time.time() + 20
    p = _next_pending(session, end)
    texts = [x["text"] for x in p["actions"]]
    assert "Lancia Punch First" not in texts
    session.answer({"action": texts.index("Lancia Punch First (col Gold)")})
    game.join(timeout=20)
    assert session.pending is None
    assert not a.base_gear and not a.rune_pool.get(Domain.BODY) and a.base_units[0].might == 8


def test_hiding_a_card_asks_which_rune_to_recycle(tmp_path):
    """Matteo (25/11): hiding costs [rune], a Power of any domain; the engine
    recycled the first domain's rune (Body before Chaos). The page asks."""
    import threading

    from riftbound.core.player import Domain, Rune
    from riftbound.registry.cards_registry import CARD_REGISTRY
    loop, a, b, session, agent = _gold_table(tmp_path, 2)
    a.base_gear.clear()                                     # no Gold here
    a.rune_pool[Domain.CHAOS] = [Rune(Domain.CHAOS) for _ in range(2)]
    a.channel()
    a.hand.append(CARD_REGISTRY["Back Off"].instantiate())
    bf = loop.gs.battlefields[0]
    bf.units_A.append(a.base_units.pop())
    bf._note_control()
    game = threading.Thread(target=lambda: loop._apply_action(a, agent.decide_action(b)))
    game.start()
    end = time.time() + 20
    p = _next_pending(session, end)
    texts = [x["text"] for x in p["actions"]]
    session.answer({"action": next(i for i, t in enumerate(texts) if t.startswith("Nascondi Back Off"))})
    p = _next_pending(session, end)
    assert p["question"] == "Come paghi?" and p["source"] == "Back Off"
    assert [o["text"] for o in p["options"]] == ["Ricicli 1 runa Body", "Ricicli 1 runa Chaos"]
    session.answer({"option": 1})
    game.join(timeout=20)
    assert len(a.rune_pool[Domain.BODY]) == 2 and len(a.rune_pool[Domain.CHAOS]) == 1
    assert [fd.card.name for fd in bf.facedowns] == ["Back Off"]


def test_the_runes_whose_energy_is_spent_are_drawn_exhausted():
    """The engine keeps the Energy not spent (`rune_energy`), not which rune
    gave it: as many runes are drawn ready, the rest exhausted."""
    import sys
    sys.path.insert(0, str(REPO / "tests" / "audit"))
    from audit_helpers import setup

    from riftbound.ai.coach import _board_extras
    from riftbound.core.player import Domain, Rune
    loop, a, _ = setup(active="A", rich=())
    a.rune_pool[Domain.BODY] = [Rune(Domain.BODY) for _ in range(3)]
    a.rune_pool[Domain.CHAOS] = [Rune(Domain.CHAOS) for _ in range(2)]
    a.channel()
    a.energy -= 2
    runes = _board_extras(loop.gs, "A")["runes"]["me"]
    assert [(r["domain"], r["ready"]) for r in runes] == [
        ("BODY", True), ("BODY", True), ("BODY", True), ("CHAOS", False), ("CHAOS", False)]
