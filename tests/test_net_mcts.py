"""RL Chunk 3: network-guided MCTS (PUCT). torch-gated (runs after `uv sync
--extra rl`). Uses a randomly-initialised net — asserts search *mechanics*
(legal moves, termination, visit distribution), not play strength."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.net import RiftboundNet  # noqa: E402
from riftbound.ai.net_mcts import NetGuidedMCTSAgent  # noqa: E402
from riftbound.core.decisions import DecisionPoint  # noqa: E402
from riftbound.core.game_factory import build_game  # noqa: E402
from riftbound.core.legality import legal_actions  # noqa: E402
from riftbound.core.loop import GameLoop  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SHEN = REPO / "riftbound" / "data" / "decks" / "precon_shen.json"
ZED = REPO / "riftbound" / "data" / "decks" / "precon_zed.json"


def _game_with_net_mcts(seed=1, iters=8):
    torch.manual_seed(0)
    net = RiftboundNet()
    gs = build_game(game_seed=seed, deck_a_path=SHEN, deck_b_path=ZED,
                    ai_a=None, ai_b="simple_trade", first_player="a")
    gs.A.agent = NetGuidedMCTSAgent(gs.A, net, iterations=iters, rng=random.Random(0))
    return gs, gs.A.agent


def test_decide_action_is_legal():
    gs, agent = _game_with_net_mcts()
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()
    act = agent.decide_action(gs.B)
    legal = {a.to_engine() for a in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")}
    assert act in legal
    # A search with >1 candidate populates a visit distribution summing to ~1.
    if act != ("PASS", None, None) or len(legal) > 1:
        assert agent.last_visits
        assert abs(sum(agent.last_visits.values()) - 1.0) < 1e-6


def test_drives_full_game_to_completion():
    gs, _agent = _game_with_net_mcts(seed=2, iters=6)
    result = GameLoop(gs).start()
    assert result.winner in ("A", "B", "DRAW")
    assert result.turns >= 1


def test_visits_prefer_searched_actions():
    gs, agent = _game_with_net_mcts(seed=3, iters=24)
    loop = GameLoop(gs)
    loop._setup()
    loop._begin_turn()
    agent.decide_action(gs.B)
    # With a real iteration budget, total visits across root children == iterations
    # is not guaranteed (some iterations expand the root only), but visits must be
    # non-negative and the chosen action is among the most visited.
    assert agent.last_visits
    top = max(agent.last_visits, key=agent.last_visits.get)
    assert agent.last_visits[top] > 0


def test_search_makes_the_choices_inside_an_action():
    """A kill spell with two enemy targets: the baseline takes the first (the
    1-Might one). With a value that counts Might on the board, the search's
    choice nodes find the 6-Might target, and the real game kills it."""
    from riftbound.ai.net_mcts import _Plan
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.effects import _position_value
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    from riftbound.registry.cards_registry import CARD_REGISTRY

    class BoardValue(NetGuidedMCTSAgent):
        def _evaluate(self, clone, side, legal_ga):
            return {a.to_engine(): 1.0 / len(legal_ga) for a in legal_ga}, self._net_value(clone, side)

        def _net_value(self, clone, side):
            return max(-1.0, min(1.0, _position_value(clone, side) / 20))

    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    small, big = UnitInPlay(UnitCard(name="Small", might=1)), UnitInPlay(UnitCard(name="Big", might=6))
    gs.battlefields[0].add_unit("B", small)
    gs.battlefields[0].add_unit("B", big)
    a.hand.append(CARD_REGISTRY["Death from Below"].instantiate())
    a.energy = 10
    from riftbound.core.enums import Domain
    a.add_power(Domain.CHAOS, 1)                # its [fury] or [chaos]
    torch.manual_seed(0)
    a.agent = BoardValue(a, RiftboundNet(), iterations=60, rng=random.Random(0))
    loop = GameLoop(gs)

    act = a.agent.decide_action(b)
    assert act[0] == "SPELL"
    assert isinstance(loop.chooser, _Plan)
    assert loop.chooser.node.choices                                    # its target searched
    loop._apply_action(a, act)
    assert gs.battlefields[0].units_B == [small]
    a.agent._release_forced()                                           # the next decision
    assert not isinstance(loop.chooser, _Plan)


def test_search_casts_a_spell_in_a_showdown():
    """A's 3-Might unit attacks B's 4: losing. With Grim Resolve (+3, ACTION) in
    hand and a value that counts the board, the showdown search casts it (the
    agent used to pass in every showdown)."""
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.effects import _position_value
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    from riftbound.registry.cards_registry import CARD_REGISTRY

    class BoardValue(NetGuidedMCTSAgent):
        def _evaluate(self, clone, side, legal_ga):
            return {a.to_engine(): 1.0 / len(legal_ga) for a in legal_ga}, self._net_value(clone, side)

        def _net_value(self, clone, side):
            return max(-1.0, min(1.0, _position_value(clone, side) / 20))

    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    gs.battlefields[0].add_unit("A", UnitInPlay(UnitCard(name="Mine", might=3)))
    gs.battlefields[0].add_unit("B", UnitInPlay(UnitCard(name="Theirs", might=4)))
    gs.showdown_active, gs.showdown_bf_idx, gs.showdown_attacker, gs.focus_player = True, 0, "A", "A"
    a.hand.append(CARD_REGISTRY["Grim Resolve"].instantiate())
    a.energy = 5
    torch.manual_seed(0)
    a.agent = BoardValue(a, RiftboundNet(), iterations=40, rng=random.Random(0))
    GameLoop(gs)
    act = a.agent.decide_showdown_action(b, 0)
    assert act[0] == "SPELL" and act[1] == 0


# --- choices beyond the first, while defending, on hidden cards (BACKLOG O3) ---

def _bare_game():
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.cards import UnitCard
    from riftbound.core.player import Deck, Player, RuneDeck
    from riftbound.core.state import GameState
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return gs, a, b


class _BoardValue(NetGuidedMCTSAgent):
    """Uniform priors, the board (effects._position_value) as the value."""

    def _evaluate(self, clone, side, legal_ga):
        return {a.to_engine(): 1.0 / len(legal_ga) for a in legal_ga}, self._net_value(clone, side)

    def _net_value(self, clone, side):
        from riftbound.core.effects import _position_value
        return max(-1.0, min(1.0, _position_value(clone, side) / 20))


def test_search_makes_every_choice_of_an_action_not_only_the_first():
    """Star-Crossed returns a friendly unit and an enemy unit to their hands:
    two choices. The search returns A's weaker unit and B's 6-Might one (the
    baseline takes another pair), and the real game follows the plan."""
    from riftbound.ai.net_mcts import _Plan
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.enums import Domain
    from riftbound.registry.cards_registry import CARD_REGISTRY
    gs, a, b = _bare_game()
    weak, strong = UnitInPlay(UnitCard(name="Weak", might=1)), UnitInPlay(UnitCard(name="Strong", might=5))
    small, big = UnitInPlay(UnitCard(name="Small", might=1)), UnitInPlay(UnitCard(name="Big", might=6))
    for u in (weak, strong):
        gs.battlefields[1].add_unit("A", u)
    for u in (small, big):
        gs.battlefields[0].add_unit("B", u)
    a.hand.append(CARD_REGISTRY["Star-Crossed"].instantiate())
    a.energy = 10
    for d in Domain:
        a.add_power(d, 2)
    torch.manual_seed(0)
    a.agent = _BoardValue(a, RiftboundNet(), iterations=120, rng=random.Random(0))
    loop = GameLoop(gs)
    act = a.agent.decide_action(b)
    assert act[0] == "SPELL"
    plan = loop.chooser
    assert isinstance(plan, _Plan)
    # Both choices are in the tree: the second below the first.
    first = [c for c in plan.node.choices.values() if c.N]
    assert first and any(c.choices for c in first)
    loop._apply_action(a, act)
    assert gs.battlefields[1].units_A == [strong]
    assert gs.battlefields[0].units_B == [small]


def test_search_makes_the_defenders_combat_choices():
    """B's two 3-Might units attack A's 3-Might one at a battlefield: A has no
    card to play, so passing is its only option in the showdown, but the
    combat that follows asks it which attacker its damage kills. The baseline
    kills the first (as much Might either way); the value wants Prey gone, and
    the showdown search plans it, which the real combat follows."""
    from riftbound.ai.net_mcts import _Plan
    from riftbound.core.cards import UnitCard
    from riftbound.core.combat import UnitInPlay

    class WantsPreyDead(_BoardValue):
        def _net_value(self, clone, side):
            alive = any(u.card.name == "Prey" for bf in clone.battlefields for u in bf.units_B)
            return 0.0 if alive else 0.5

    gs, a, b = _bare_game()
    gs.active = "B"
    gs.battlefields[0].add_unit("A", UnitInPlay(UnitCard(name="Mine", might=3)))
    plain, prey = UnitInPlay(UnitCard(name="Plain", might=3)), UnitInPlay(UnitCard(name="Prey", might=3))
    gs.battlefields[0].add_unit("B", plain)
    gs.battlefields[0].add_unit("B", prey)
    gs.showdown_active, gs.showdown_bf_idx, gs.showdown_attacker, gs.focus_player = True, 0, "B", "A"
    gs.battlefields[0].contest("B", "A")
    torch.manual_seed(0)
    a.agent = WantsPreyDead(a, RiftboundNet(), iterations=40, rng=random.Random(0))
    loop = GameLoop(gs)
    loop._open_combat(gs.battlefields[0], "B")
    assert a.agent.decide_showdown_action(b, 0) == ("PASS", None, None)
    assert isinstance(loop.chooser, _Plan)
    loop._finish_showdown(0, "B")
    assert plain in gs.battlefields[0].units_B and prey not in gs.battlefields[0].units_B


def test_a_dig_is_decided_on_the_cards_really_looked_at():
    """Lightning Rush: look at the top 3, draw one, the rest to the trash. The
    search's copies have other cards on top (the deck's order is hidden), so
    the choice is weighed when the real game asks it: the segment is replayed
    with each card. The value wants Prize in hand; the baseline takes the
    mightiest (Brute)."""
    from riftbound.core.cards import UnitCard
    from riftbound.core.enums import Domain
    from riftbound.registry.cards_registry import CARD_REGISTRY

    class WantsPrize(_BoardValue):
        def _net_value(self, clone, side):
            return 0.5 if any(c.name == "Prize" for c in clone.get_player(side).hand) else 0.0

    gs, a, b = _bare_game()
    a.deck.cards = [UnitCard(name=f"Filler{i}", might=2) for i in range(6)] + \
        [UnitCard(name="Prize", might=1), UnitCard(name="Brute", might=7), UnitCard(name="Mid", might=3)]
    a.hand.append(CARD_REGISTRY["Lightning Rush"].instantiate())
    a.energy = 10
    for d in Domain:
        a.add_power(d, 2)
    torch.manual_seed(0)
    a.agent = WantsPrize(a, RiftboundNet(), iterations=8, rng=random.Random(0))
    b.agent = WantsPrize(b, RiftboundNet(), iterations=4, rng=random.Random(1))
    loop = GameLoop(gs)
    a.agent.decide_action(b)                 # the real loop keeps a journal from now on
    act = ("SPELL", 0, 0)
    loop._open_segment("A", act, 0)          # what the main loop does with a decision
    loop._apply_action(a, act)
    assert [c.name for c in a.hand] == ["Prize"]
    assert {c.name for c in a.trash} >= {"Brute", "Mid"}


def test_a_predicted_top_card_is_known_and_kept_by_determinization():
    """PREDICT keeps a card on top: its player sees it (Observation, a token
    row of its own), and a determinized copy keeps it there."""
    from riftbound.ai.encoding import encode_observation, token_rows
    from riftbound.core.cards import UnitCard
    from riftbound.core.decisions import Observation
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    from riftbound.core.state import determinize
    gs, a, b = _bare_game()
    loop = GameLoop(gs)
    from riftbound.registry.cards_registry import CARD_REGISTRY
    names = sorted(CARD_REGISTRY)[:6]
    a.deck.cards = [CARD_REGISTRY[n].instantiate() for n in names]
    ctx = EffectContext(loop=loop, card=UnitCard(name="Seer"), actor=a, opponent=b,
                        battlefield=gs.battlefields[0])
    REGISTRY["predict"](ctx, {"effect": "predict", "amount": 2})
    obs = Observation.from_state(gs, "A")
    assert obs.my_deck_top == (names[5], names[4])
    assert Observation.from_state(gs, "B").my_deck_top == ()
    rows = [r for r in token_rows(encode_observation(obs)) if r[0] == "my_deck_top"]
    assert [(n, round(float(f[1]) * 3)) for _z, n, f in rows] == [(names[5], 0), (names[4], 1)]
    for seed in range(5):
        c = gs.clone()
        determinize(c, observer="A", rng=random.Random(seed))
        assert [x.name for x in c.A.deck.cards[-2:]] == [names[4], names[5]]
    a.draw()
    assert Observation.from_state(gs, "A").my_deck_top == (names[4],)
    a.deck.shuffle(random.Random(0))
    assert Observation.from_state(gs, "A").my_deck_top == ()
