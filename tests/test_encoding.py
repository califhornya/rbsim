"""RL Chunk 1: state & action encoding. The network's I/O contract — fixed-size
observation vector + canonical action slots + legal mask."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from riftbound.ai.encoding import (
    ACTION_DIM,
    OBS_DIM,
    action_to_index,
    encode_observation,
    index_to_legal_action,
    legal_mask,
)
from riftbound.ai.env import RiftboundEnv
from riftbound.core.decisions import DecisionPoint, GameAction, Observation

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"
ORNN = REPO / "riftbound" / "data" / "decks" / "vendetta_ornn.json"


def _env():
    return RiftboundEnv(deck_a_path=KENNEN, deck_b_path=ORNN, agent_side="A",
                        opponent="simple_trade", seed=5)


def test_encode_observation_shape_and_determinism():
    env = _env()
    obs, _info = env.reset()
    v1 = encode_observation(obs)
    v2 = encode_observation(obs)
    assert v1.dtype == np.float32
    assert v1.shape == (OBS_DIM,)
    assert np.array_equal(v1, v2)                 # deterministic
    assert np.all(np.isfinite(v1))                # no NaN/inf


def test_legal_mask_matches_legal_actions_and_round_trips():
    env = _env()
    _obs, info = env.reset()
    # Advance to a turn-action decision (skip a mulligan point, which has no mask).
    while info["decision_point"] == DecisionPoint.MULLIGAN.value:
        _obs, _r, done, info = env.step([])
        assert not done
    legal = info["legal_actions"]
    mask = legal_mask(legal)
    assert mask.shape == (ACTION_DIM,)
    # Every encodable legal action sets its slot; each True slot round-trips back
    # to a legal action whose index is that slot.
    encodable = [a for a in legal if action_to_index(a) is not None]
    assert mask.sum() == len({action_to_index(a) for a in encodable})
    for i in np.nonzero(mask)[0]:
        a = index_to_legal_action(int(i), legal)
        assert a is not None and action_to_index(a) == int(i)


def test_action_to_index_stable_across_kinds():
    # Representative actions map to distinct, stable slots.
    samples = [
        GameAction.pass_(),
        GameAction.play("SPELL", 3, 1, ""),
        GameAction.play("UNIT", 0, 0, ""),
        GameAction.move(2, 0, ""),                 # base(=2) -> BF0
        GameAction.hidden_play(1, ""),
        GameAction.ability("ACTIVATED", 0, ""),
        GameAction.ability("ACTIVATED", 2, ""),
    ]
    idxs = [action_to_index(a) for a in samples]
    assert all(i is not None for i in idxs)
    assert len(set(idxs)) == len(idxs)             # injective
    assert all(0 <= i < ACTION_DIM for i in idxs)
    # Stable: recomputing gives the same slots.
    assert idxs == [action_to_index(a) for a in samples]


def test_full_game_encodes_every_step():
    env = _env()
    obs, info = env.reset()
    steps = 0
    while not info["done"]:
        vec = encode_observation(obs)
        assert vec.shape == (OBS_DIM,)
        if info["decision_point"] == DecisionPoint.MULLIGAN.value:
            action = []
        else:
            mask = legal_mask(info["legal_actions"])
            assert mask.shape == (ACTION_DIM,)
            # Pick any legal, encodable slot; fall back to first legal action.
            hot = np.nonzero(mask)[0]
            action = (index_to_legal_action(int(hot[0]), info["legal_actions"])
                      if len(hot) else (info["legal_actions"][0] if info["legal_actions"] else ("PASS", None, None)))
        obs, _r, done, info = env.step(action)
        steps += 1
        assert steps < 2000
    assert info["done"]


def test_encoding_sees_turn_player_showdown_and_chain():
    import random
    from riftbound.ai.encoding import token_rows
    from riftbound.core.cards import SpellCard
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import ChainItem, GameState

    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, active="A")
    gs.showdown_active, gs.showdown_bf_idx = True, 1
    gs.chain.append(ChainItem(player="B", card=SpellCard(name="Rebuke"), bf_idx=1))
    va = encode_observation(Observation.from_state(gs, "A"))
    vb = encode_observation(Observation.from_state(gs, "B"))
    assert not np.array_equal(va, vb)
    assert ("opp_chain", "Rebuke") in [(z, c) for z, c, _ in token_rows(va)]   # B's spell, seen by A
    assert ("my_chain", "Rebuke") in [(z, c) for z, c, _ in token_rows(vb)]


def test_encoding_sees_each_units_state_and_the_public_zones():
    import random
    from riftbound.ai.encoding import token_rows
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState

    a = Player(name="A", deck=Deck(cards=[UnitCard(name="Gust Monk")]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name="Hidden One")]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, active="A", battlefields=[Battlefield(), Battlefield()])
    tired = UnitInPlay(UnitCard(name="Blade Twirler", might=3), ready=False, damage=2)
    gs.battlefields[1].add_unit("A", tired)
    b.trash.append(UnitCard(name="Shadow Assassin"))
    rows = token_rows(encode_observation(Observation.from_state(gs, "A")))
    unit = next(f for z, c, f in rows if (z, c) == ("my_units_bf1", "Blade Twirler"))
    assert unit[0] == 0.3 and unit[1] == 0.2 and unit[2] == 0.0          # Might 3, damage 2, exhausted
    assert ("opp_trash", "Shadow Assassin") in [(z, c) for z, c, _ in rows]
    assert ("my_deck", "Gust Monk") in [(z, c) for z, c, _ in rows]      # my deck's cards, not theirs
    assert not any(z.startswith("opp_deck") or c == "Hidden One" for z, c, _ in rows)
