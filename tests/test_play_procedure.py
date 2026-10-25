"""One play procedure for every zone and timing (GameLoop._play_unit /
_play_gear / _spell_played): the Chosen Champion played from the Champion Zone
gets "when you play me", ACCELERATE and the play counters like a unit from hand;
moving or using an ability is not playing a card; a reaction counts for the
player who plays it and pays the same cost as in the main phase; cards played
from the trash honor their filter and go through the same procedure."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.decisions import DecisionPoint
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop(deck_cards=5):
    deck = Deck(cards=[UnitCard(name=f"C{i}") for i in range(deck_cards)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _register(monkeypatch, name, effects, category="Unit", **raw):
    spec = CardSpec.from_dict({"name": name, "category": category, "effects": effects, **raw})
    monkeypatch.setitem(CARD_REGISTRY, spec.name, spec)
    return spec


def _power(player, domain, n):
    player.power_pool[domain] = player.power_pool.get(domain, 0) + n
    player.rune_pool.setdefault(domain, []).extend(Rune(domain=domain) for _ in range(n))


def test_champion_from_champion_zone_gets_play_effects_and_counts(monkeypatch):
    _register(monkeypatch, "Test Champ", [{"effect": "draw_cards", "count": 1}],
              category="Champion")
    loop = _loop()
    a = loop.gs.A
    loop.gs.champion_A = UnitCard(name="Test Champ", cost_energy=2)
    a.energy = 2
    loop._apply_action(a, ("CHAMPION", None, 0, None))
    assert loop.gs.champion_A_deployed
    assert [u.card.name for u in a.base_units] == ["Test Champ"]
    assert len(a.hand) == 1                     # "when you play me, draw 1"
    assert loop.gs.cards_played_this_turn["A"] == 1


def test_champion_accelerate_enters_ready():
    loop = _loop()
    a = loop.gs.A
    loop.gs.champion_A = UnitCard(name="Fast Champ", cost_energy=2, domain=Domain.FURY,
                                  keywords=["ACCELERATE"])
    a.energy = 3
    _power(a, Domain.FURY, 1)
    loop._apply_action(a, ("CHAMPION", None, 0, None))
    assert a.base_units[0].ready
    assert a.energy == 0


def test_moving_is_not_playing_a_card():
    loop = _loop()
    a = loop.gs.A
    a.base_units.append(UnitInPlay(card=UnitCard(name="Walker"), ready=True))
    loop._apply_action(a, ("MOVE", None, 2, 0))
    assert loop.gs.battlefields[0].units_A
    assert loop.gs.cards_played_this_turn["A"] == 0
    assert not loop._check_condition(
        {"type": "you_already_played_another_card_this_turn"},
        UnitCard(name="Legion Guy"), a, loop.gs.B, None)


def test_legion_card_does_not_count_itself(monkeypatch):
    _register(monkeypatch, "Legion Drawer", [
        {"effect": "draw_cards", "count": 1,
         "condition": {"type": "you_already_played_another_card_this_turn"}}])
    loop = _loop()
    a = loop.gs.A
    a.hand.append(UnitCard(name="Legion Drawer", cost_energy=0))
    loop._apply_action(a, ("UNIT", 0, 0, None))
    assert len(a.hand) == 0                     # first card: no LEGION
    a.hand.append(UnitCard(name="Legion Drawer", cost_energy=0))
    loop._apply_action(a, ("UNIT", 0, 0, None))
    assert len(a.hand) == 1                     # second card: LEGION draws


def test_reaction_counts_for_its_player_and_pays_its_reduction(monkeypatch):
    _register(monkeypatch, "Cheap Trick", [
        {"effect": "reduce_cost", "trigger": "cost_modifier", "amount": 1},
        {"effect": "draw_cards", "trigger": "on_cast", "count": 1}],
        category="Spell")
    loop = _loop()
    b = loop.gs.B
    b.hand.append(SpellCard(name="Cheap Trick", cost_energy=2, keywords=["REACTION"]))
    b.energy = 1

    class _ReactOnce:
        done = False

        def decide_reaction(self, opponent, chain):
            if not self.done:
                self.done = True
                return ("SPELL", 0, 0)
            return ("PASS", None, None)

    b.agent = _ReactOnce()
    legal = legal_actions(loop, DecisionPoint.REACTION, "B")
    assert any(ga.kind == "SPELL" for ga in legal)   # affordable at its reduced cost
    loop.gs.chain.append(__import__("riftbound.core.state", fromlist=["ChainItem"]).ChainItem(
        player="A", card=SpellCard(name="Opening"), bf_idx=0))
    loop._run_chain("A")
    assert b.energy == 0
    assert loop.gs.cards_played_this_turn["B"] == 1
    assert loop.gs.spells_played_this_turn["B"] == 1
    assert len(b.hand) == 1                      # Cheap Trick resolved: drew 1


def test_turn_start_resets_both_players_counters():
    loop = _loop()
    loop._count_card_played(SpellCard(name="X"), "B")
    loop.gs.turn = 3
    loop._begin_turn()
    assert loop.gs.cards_played_this_turn == {"A": 0, "B": 0}
    assert loop.gs.played_cards_this_turn == {"A": [], "B": []}


def test_play_from_trash_honors_its_filter_and_plays_the_card(monkeypatch):
    _register(monkeypatch, "Comes Back", [{"effect": "draw_cards", "count": 1}])
    loop = _loop()
    a = loop.gs.A
    a.trash.extend([UnitCard(name="Big", cost_energy=7), SpellCard(name="Spell", cost_energy=1),
                    UnitCard(name="Comes Back", cost_energy=3)])
    ctx = EffectContext(loop, UnitCard(name="Matron"), a, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY_play = __import__("riftbound.core.effects", fromlist=["REGISTRY"]).REGISTRY["play_from_trash"]
    REGISTRY_play(ctx, {"target_filter": {"energy_at_most": 3, "is_unit": True}})
    assert [u.card.name for u in a.base_units] == ["Comes Back"]
    assert [c.name for c in a.trash] == ["Big", "Spell"]
    assert len(a.hand) == 1                      # its "when you play me" fired
    assert loop.gs.cards_played_this_turn["A"] == 1


def test_return_from_trash_legacy_gear_filter():
    from riftbound.core.effects import REGISTRY
    loop = _loop()
    a = loop.gs.A
    a.trash.extend([UnitCard(name="Unit"), GearCard(name="Hammer")])
    ctx = EffectContext(loop, UnitCard(name="Engineer"), a, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["return_from_trash"](ctx, {"filter": "gear", "destination": "hand"})
    assert [c.name for c in a.hand] == ["Hammer"]


def test_quick_draw_on_opponents_turn_attaches_to_own_unit():
    loop = _loop()
    b = loop.gs.B
    mine = UnitInPlay(card=UnitCard(name="Mine"))
    theirs = UnitInPlay(card=UnitCard(name="Theirs"))
    loop.gs.battlefields[0].add_unit("B", mine)
    loop.gs.battlefields[0].add_unit("A", theirs)
    b.hand.append(GearCard(name="Axe", cost_energy=0, keywords=["QUICK-DRAW", "REACTION"]))
    loop._apply_action(b, ("GEAR", 0, 0, None))
    assert [g.name for g in mine.gear] == ["Axe"]
    assert theirs.gear == []


def test_this_turn_might_ends_for_base_units():
    loop = _loop()
    u = UnitInPlay(card=UnitCard(name="Resting", might=2))
    u.temporary_might = 3
    loop.gs.A.base_units.append(u)
    loop._end_turn()
    assert u.temporary_might == 0


def test_darius_trifarian_fires_on_the_second_card_only():
    loop = _loop()
    a = loop.gs.A
    darius = UnitInPlay(card=CARD_REGISTRY["Darius Trifarian"].instantiate(), ready=False)
    a.base_units.append(darius)
    for i in range(3):
        a.hand.append(SpellCard(name=f"Free{i}", cost_energy=0))
        loop._apply_action(a, ("SPELL", 0, 0, None))
        assert darius.ready is (i >= 1)          # readied by the 2nd card...
        assert darius.temporary_might == (2 if i >= 1 else 0)   # ...+2 once, not per card
    assert loop.gs.cards_played_this_turn["A"] == 3


def test_diana_no_longer_human_gets_two_per_spell():
    loop = _loop()
    a = loop.gs.A
    diana = UnitInPlay(card=CARD_REGISTRY["Diana No Longer Human"].instantiate())
    a.base_units.append(diana)
    for i in range(2):
        a.hand.append(SpellCard(name=f"Free{i}", cost_energy=0))
        loop._apply_action(a, ("SPELL", 0, 0, None))
    assert diana.temporary_might == 4


def test_crumbling_sands_needs_the_opponent_to_have_played_another_spell():
    from riftbound.core.state import ChainItem
    sands = CARD_REGISTRY["Crumbling Sands"].instantiate()
    for opp_spells, countered in ((1, False), (2, True)):
        loop = _loop()
        big = SpellCard(name="Big Spell", cost_energy=9, cost_power=2)
        for _ in range(opp_spells):
            loop._count_card_played(SpellCard(name="S"), "A")
        loop.gs.chain.append(ChainItem(player="A", card=big, bf_idx=0))
        loop._resolve_card_effects(sands, loop.gs.battlefields[0], loop.gs.B, loop.gs.A)
        assert (not loop.gs.chain) is countered


def test_heedless_resurrection_plays_no_bigger_than_the_killed_unit():
    loop = _loop()
    a = loop.gs.A
    victim = UnitInPlay(card=UnitCard(name="Victim", cost_energy=3, cost_power=1))
    loop.gs.battlefields[0].add_unit("A", victim)
    a.trash.extend([UnitCard(name="Huge", cost_energy=8), UnitCard(name="Two", cost_energy=2)])
    heedless = CARD_REGISTRY["Heedless Resurrection"].instantiate()
    a.power_pool[Domain.ORDER] = 0
    loop._try_pay_additional_costs(heedless, a)
    loop._resolve_card_effects(heedless, loop.gs.battlefields[0], a, loop.gs.B)
    names = sorted(u.card.name for u in a.base_units)
    assert names in (["Victim"], ["Two"])        # the killed unit itself qualifies too
    assert "Huge" in [c.name for c in a.trash]


def test_champion_cards_are_units_with_the_champion_category():
    from riftbound.core.effects import _zone_card_matches
    champ = CARD_REGISTRY["Darius Trifarian"].instantiate()
    assert isinstance(champ, UnitCard)
    assert _zone_card_matches(champ, {"is_champion": True})
    assert _zone_card_matches(champ, {"is_unit": True})
