"""The search's choice keys are the same on every copy of the game: a
trigger's label holds its battlefield's repr, whose `combat_designated` set
printed in memory-address order made one option a different key on each copy
(found by the mixed arena, seed 70113, 24/11)."""
from riftbound.ai.net_mcts import _label
from riftbound.ai.ppo.collect import EVE, KHA
from riftbound.core.combat import UnitInPlay
from riftbound.core.game_factory import build_game
from riftbound.core.loop import GameLoop
from riftbound.core.state import PendingTrigger


def _game_with_combat():
    gs = build_game(game_seed=1, deck_a_path=EVE, deck_b_path=KHA, ai_a=None, ai_b=None, max_turns=40,
                    first_player="a")
    bf = gs.battlefields[0]
    units = [UnitInPlay(card=gs.A.deck.cards[i]) for i in range(3)] + [UnitInPlay(card=gs.B.deck.cards[0])]
    bf.units_A.extend(units[:3])
    bf.units_B.append(units[3])
    bf.combat_designated = set(units)
    gs.pending_trigger_probe = PendingTrigger(card=units[0].card, trigger="on_attack", side="A", bf=bf, specs=[])
    return gs


def test_trigger_label_same_on_every_copy():
    gs = _game_with_combat()
    labels = set()
    for _ in range(30):
        c = gs.clone()
        labels.add(_label(GameLoop(c), "A", c.pending_trigger_probe, 0))
    assert len(labels) == 1


def test_stable_repr_is_repr_without_sets():
    from riftbound.ai.net_mcts import _stable_repr
    gs = _game_with_combat()
    c = gs.A.deck.cards[5]
    for o in (gs.battlefields[1], c, (c, 2), {"k": gs.battlefields[1]}):
        assert _stable_repr(o) == repr(o)
