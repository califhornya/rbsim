"""BACKLOG F3, the net's encoding (riftbound/ai/encoding.py): the Baron Pit is a
third battlefield it sees and moves to and from (the engine's base index is then
3, not 2), each facedown card at Bandle Tree has its own HIDDEN_PLAY slot,
hiding the champion from the Champion Zone has its own HIDE slot (it raised a
TypeError), the legends Neeko Blending In adds are seen, and so is a Standard
Move being declared (GameState.pending_move)."""
from __future__ import annotations

from riftbound.ai.encoding import (
    DENSE_DIM,
    N_BF,
    action_to_index,
    encode_observation,
    index_to_legal_action,
    legal_mask,
    token_rows,
)
from riftbound.core.cards import UnitCard
from riftbound.core.decisions import DecisionPoint, GameAction, Observation
from riftbound.core.legality import legal_actions
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_baron_nashor import _play_baron
from test_corpus_cards import _setup, _unit
from test_hidden import _control, _hidden_unit, _loop, _named_bf
from test_neeko_blending_in import _champion_legend, _play_neeko, _pool


def _rows(gs, side):
    return [(z, c) for z, c, _ in token_rows(encode_observation(Observation.from_state(gs, side)))]


def _round_trips(legal, n_bf):
    """Each legal action has its own slot, and each slot gives it back."""
    slots = [action_to_index(a, n_bf) for a in legal]
    assert None not in slots
    assert len(set(slots)) == len(slots)
    mask = legal_mask(legal, n_bf)
    assert mask.sum() == len(slots)
    for a, i in zip(legal, slots):
        assert index_to_legal_action(i, legal, n_bf) == a


def _with_the_pit():
    loop, a, b = _setup()
    _play_baron(loop, a)
    loop._flush_pending_move()                 # he conquers the Pit
    assert len(loop.gs.battlefields) == 3
    return loop, a, b


def test_moves_to_and_from_the_baron_pit_have_their_own_slots():
    loop, a, b = _with_the_pit()
    pit = loop.gs.battlefields[2]
    pit.units_A[0].ready = True
    a.base_units.append(_unit("Runner", 2))
    loop.gs.battlefields[0].add_unit("A", _unit("Scout", 1))
    legal = legal_actions(loop, DecisionPoint.TURN_ACTION, "A")
    moves = {(m.lane, m.dst_lane) for m in legal if m.kind == "MOVE"}
    assert {(3, 2), (2, 3), (0, 2), (0, 3), (3, 0)} <= moves     # base is 3 now
    _round_trips(legal, 3)


def test_a_location_means_the_same_with_two_or_three_battlefields():
    base_to_bf0 = action_to_index(GameAction.move(2, 0, ""), 2)
    assert action_to_index(GameAction.move(3, 0, ""), 3) == base_to_bf0
    # bf0 -> the Pit was bf0 -> base's slot (N_BF was 2); base -> Pit had none.
    assert action_to_index(GameAction.move(0, 2, ""), 3) != action_to_index(GameAction.move(0, 3, ""), 3)
    assert action_to_index(GameAction.move(0, 2, ""), 2) == action_to_index(GameAction.move(0, 3, ""), 3)
    assert action_to_index(GameAction.move(3, 2, ""), 3) is not None
    assert action_to_index(GameAction("UNIT", 0, 0, 2, ""), 3) != action_to_index(GameAction.play("UNIT", 0, 0, ""), 3)


def test_the_net_sees_the_pit_and_who_is_there():
    loop, a, b = _with_the_pit()
    assert ("battlefield_2", "Baron Pit") in _rows(loop.gs, "A")
    assert ("my_units_bf2", "Baron Nashor") in _rows(loop.gs, "A")
    assert ("opp_units_bf2", "Baron Nashor") in _rows(loop.gs, "B")


def test_each_facedown_card_at_bandle_tree_has_its_own_slot():
    loop = _loop(power=2, turn=3)
    _named_bf(loop, 0, "Bandle Tree")
    loop.gs.A.hand.extend([_hidden_unit("One"), _hidden_unit("Two")])
    _control(loop, "A", 0)
    loop._hide_card("A", 0, 0)
    loop._hide_card("A", 0, 0)
    loop.gs.turn = 4
    react = legal_actions(loop, DecisionPoint.REACTION, "A")
    hidden = [a for a in react if a.kind == "HIDDEN_PLAY"]
    assert len(hidden) == 2
    _round_trips(react, 2)


def test_hiding_the_champion_has_its_own_slot():
    loop, a, b = _setup()
    loop.gs.champion_A = CARD_REGISTRY["Kennen Keeper of Balance"].instantiate()
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    a.hand.append(UnitCard(name="Sneaky", might=3, keywords=["HIDDEN"]))
    legal = legal_actions(loop, DecisionPoint.TURN_ACTION, "A")
    hides = {a.to_engine()[1] for a in legal if a.kind == "HIDE"}
    assert {"champion", 0} <= hides
    _round_trips(legal, 2)


def test_the_net_sees_the_legends_neeko_added():
    loop, a, b = _setup()
    _champion_legend(loop, "A", "Sett The Boss")
    _pool(loop, "A", "Diana Scorn of the Moon", "Jinx Loose Cannon")
    _play_neeko(loop, a)
    rows = token_rows(encode_observation(Observation.from_state(loop.gs, "A")))
    legends = {c: f[0] for z, c, f in rows if z == "my_legend"}
    assert legends == {"Sett The Boss": 1.0, "Diana Scorn of the Moon": 1.0}    # ready
    assert ("opp_legend", "Diana Scorn of the Moon") in _rows(loop.gs, "B")


def test_the_net_sees_a_move_being_declared():
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Guard", 1))
    a.base_units.append(_unit("Runner", 2))
    held = DENSE_DIM - 2 * N_BF               # the viewer's, then the opponent's
    before = encode_observation(Observation.from_state(loop.gs, "A"))
    assert before[held:DENSE_DIM].sum() == 0
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    assert loop.gs.pending_move == (0, "A")    # more units may join: no showdown yet
    obs_a, obs_b = Observation.from_state(loop.gs, "A"), Observation.from_state(loop.gs, "B")
    assert (obs_a.my_held_move, obs_a.opp_held_move) == (0, None)
    assert (obs_b.my_held_move, obs_b.opp_held_move) == (None, 0)
    assert encode_observation(obs_a)[held] == 1.0
    assert encode_observation(obs_b)[held + N_BF] == 1.0
