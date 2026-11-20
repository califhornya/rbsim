"""The net sees which of its own facedown cards is hidden on which battlefield
(20/11, external review: swapping Pyke Returned and Switcheroo hidden on our two
battlefields left the observation and the net's input identical).

§128.4: the controller of a facedown card may look at it. The opponent's
facedown cards stay unknown: swapping theirs must not change our input."""
import random
from pathlib import Path

import numpy as np

from riftbound.ai.encoding import encode_observation
from riftbound.core.battlefield import FacedownCard
from riftbound.core.decisions import Observation
from riftbound.core.game_factory import build_game
from riftbound.registry.cards_registry import CARD_REGISTRY

D = Path(__file__).resolve().parents[1] / "riftbound/data/decks"


def _state(first: str, second: str, owner: str):
    gs = build_game(game_seed=3, deck_a_path=D / "competitive_evelynn.json",
                    deck_b_path=D / "competitive_khazix.json", ai_a=None, ai_b=None, max_turns=40)
    gs.rng = random.Random(0)
    for bf, name in zip(gs.battlefields, (first, second)):
        bf.facedowns.append(FacedownCard(card=CARD_REGISTRY[name].instantiate(), owner=owner, turn_hidden=1))
    return gs


def test_own_facedowns_are_seen_where_they_are():
    a = _state("Pyke Returned", "Switcheroo", "A")
    b = _state("Switcheroo", "Pyke Returned", "A")
    oa, ob = Observation.from_state(a, "A"), Observation.from_state(b, "A")
    assert oa.battlefields[0].my_facedown == ("Pyke Returned",)
    assert ob.battlefields[0].my_facedown == ("Switcheroo",)
    assert not np.array_equal(encode_observation(oa), encode_observation(ob))


def test_the_opponents_facedowns_stay_hidden():
    a = _state("Pyke Returned", "Switcheroo", "B")
    b = _state("Switcheroo", "Pyke Returned", "B")
    oa, ob = Observation.from_state(a, "A"), Observation.from_state(b, "A")
    assert oa.battlefields[0].my_facedown == (None,)
    assert np.array_equal(encode_observation(oa), encode_observation(ob))
