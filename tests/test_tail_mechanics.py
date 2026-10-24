"""Engine pieces added for hand-authored long-tail cards: new conditions,
per-turn conquer/hold counters, on_friendly_exhaust / on_hide_here triggers,
the return_friendly_unit additional cost, no_combat_damage, counter_spell
min_power, "self" = the source unit, and conditions checked before costs."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import BattlefieldCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import ChainItem, GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec


def _loop(deck_cards=5):
    deck = Deck(cards=[UnitCard(name=f"C{i}") for i in range(deck_cards)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _register(monkeypatch, name, effects, category="Unit"):
    spec = CardSpec.from_dict({"name": name, "category": category, "effects": effects})
    monkeypatch.setitem(CARD_REGISTRY, spec.name, spec)


def _check(loop, ctype, extra=None, **params):
    cond = {"type": ctype, "params": params} if params else {"type": ctype}
    return loop._check_condition(cond, UnitCard(name="Src"), loop.gs.A, loop.gs.B, extra)


def test_hand_runes_and_turn_conditions():
    loop = _loop()
    a = loop.gs.A
    a.hand.extend([UnitCard(name="H1"), UnitCard(name="H2")])
    assert not _check(loop, "cards_in_hand_at_most", n=1)
    a.hand.pop()
    assert _check(loop, "cards_in_hand_at_most", n=1)

    assert _check(loop, "rune_deck_empty")
    for _ in range(5):
        a.add_rune(Domain.FURY)
    assert not _check(loop, "you_have_n_or_fewer_runes", n=4)
    assert _check(loop, "you_have_n_or_fewer_runes", n=5)

    loop.gs.turn = 2
    assert _check(loop, "first_turn_of_player")
    loop.gs.turn = 3
    assert not _check(loop, "first_turn_of_player")


def test_battlefield_shape_conditions():
    loop = _loop()
    bf0, bf1 = loop.gs.battlefields
    extra = {"battlefield": bf0}
    bf0.add_unit("A", UnitInPlay(UnitCard(name="Me")))
    bf0.add_unit("B", UnitInPlay(UnitCard(name="Them")))
    assert _check(loop, "one_on_one_here", extra)
    assert _check(loop, "enemy_alone_here", extra)
    bf0.add_unit("A", UnitInPlay(UnitCard(name="Ally")))
    assert not _check(loop, "one_on_one_here", extra)
    assert _check(loop, "enemy_alone_here", extra)

    assert not _check(loop, "you_control_bf_with_exactly_n_units", n=2)
    bf1.add_unit("A", UnitInPlay(UnitCard(name="X")))
    bf1.add_unit("A", UnitInPlay(UnitCard(name="Y")))
    assert _check(loop, "you_control_bf_with_exactly_n_units", n=2)

    assert not _check(loop, "friendly_deployed_gear_here", {"battlefield": bf1})
    loop._deploy_gear("A", bf1, UnitCard(name="Some Gear"))
    assert _check(loop, "friendly_deployed_gear_here", {"battlefield": bf1})


def test_conquer_and_hold_counters_scale_discounts():
    loop = _loop()
    gs = loop.gs
    loop._fire_scoring_trigger("on_conquer", gs.battlefields[0], "A")
    loop._fire_scoring_trigger("on_hold", gs.battlefields[1], "A")
    ctx = EffectContext(loop, UnitCard(name="Src"), gs.A, gs.B, gs.battlefields[0])
    from riftbound.core.effects import _amount
    assert _amount(ctx, {"amount_source": "battlefields_conquered_this_turn"}) == 1
    assert _amount(ctx, {"amount_source": "hold_points_this_turn"}) == 1


def test_self_target_is_the_source_unit(monkeypatch):
    # "Ready me" on a unit sitting in base must not ready a battlefield ally.
    loop = _loop()
    a = loop.gs.A
    me = UnitInPlay(UnitCard(name="Me"), ready=False)
    ally = UnitInPlay(UnitCard(name="Ally"), ready=False)
    a.base_units.append(me)
    loop.gs.battlefields[0].add_unit("A", ally)
    ctx = EffectContext(loop, me.card, a, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["ready_unit"](ctx, {"target": "self"})
    assert me.ready and not ally.ready


def test_on_friendly_exhaust(monkeypatch):
    _register(monkeypatch, "Test Deserter", [
        {"effect": "grant_temporary_might", "trigger": "on_friendly_exhaust",
         "target": "self", "amount": 1}])
    loop = _loop()
    bf = loop.gs.battlefields[0]
    deserter = UnitInPlay(UnitCard(name="Test Deserter", might=2), ready=True)
    other = UnitInPlay(UnitCard(name="Other", might=2), ready=True)
    bf.add_unit("A", deserter)
    bf.add_unit("A", other)
    loop._exhaust(other)
    assert deserter.temporary_might == 1
    loop._exhaust(deserter)                  # its own exhaust isn't "another"
    assert deserter.temporary_might == 1


def test_on_hide_here(monkeypatch):
    _register(monkeypatch, "Test Academy", [
        {"effect": "draw_cards", "trigger": "on_hide_here", "count": 1}], category="Battlefield")
    loop = _loop()
    a = loop.gs.A
    bf = loop.gs.battlefields[0]
    bf.card = BattlefieldCard(name="Test Academy")
    bf.add_unit("A", UnitInPlay(UnitCard(name="Holder")))
    a.add_rune(Domain.FURY)
    a.power_pool[Domain.FURY] = 1
    a.hand.append(UnitCard(name="Sneaky", keywords=["HIDDEN"]))
    assert loop._hide_card("A", 0, 0)
    assert len(a.hand) == 1                  # hid one, drew one


def test_return_friendly_unit_additional_cost():
    loop = _loop()
    a = loop.gs.A
    unit = UnitInPlay(UnitCard(name="Bounced"))
    loop.gs.battlefields[0].add_unit("A", unit)
    loop.gs.battlefields[1].add_unit("B", UnitInPlay(UnitCard(name="Enemy")))
    assert loop._pay_one_additional_cost(SpellCard(name="Convergence"), a,
                                         {"return_friendly_unit": True})
    assert unit.card in a.hand and not loop.gs.battlefields[0].units_A
    assert loop.gs.battlefields[1].units_B   # the opponent's unit is untouched


def test_exhaust_cost_uses_own_unit():
    # Regression: a shadowed helper made "exhaust a friendly unit" look at the
    # other side's units.
    loop = _loop()
    mine = UnitInPlay(UnitCard(name="Mine"), ready=True)
    theirs = UnitInPlay(UnitCard(name="Theirs"), ready=True)
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.gs.battlefields[0].add_unit("B", theirs)
    assert loop._pay_one_additional_cost(SpellCard(name="Ki Burst"), loop.gs.A,
                                         {"exhaust_friendly_unit": True})
    assert not mine.ready and theirs.ready


def test_no_combat_damage(monkeypatch):
    _register(monkeypatch, "Test Graves", [
        {"effect": "no_combat_damage", "trigger": "passive", "target": "self"}])
    loop = _loop()
    bf = loop.gs.battlefields[0]
    graves = UnitInPlay(UnitCard(name="Test Graves", might=5))
    defender = UnitInPlay(UnitCard(name="Defender", might=3))
    bf.add_unit("A", graves)
    bf.add_unit("B", defender)
    loop._recompute_passives()
    bf.resolve_combat_might(attacker_side="A")
    assert defender in bf.units_B            # took no combat damage from Graves


def test_counter_spell_min_power():
    loop = _loop()
    gs = loop.gs
    ctx = EffectContext(loop, SpellCard(name="Hush"), gs.A, gs.B, gs.battlefields[0])
    cheap = SpellCard(name="Cheap", cost_power=1)
    gs.chain.append(ChainItem(player="B", card=cheap, bf_idx=0))
    REGISTRY["counter_spell"](ctx, {"min_power": 2, "max_power": 99, "max_energy": 99})
    assert gs.chain                          # 1-power spell is not countered
    gs.chain[-1] = ChainItem(player="B", card=SpellCard(name="Big", cost_power=2), bf_idx=0)
    REGISTRY["counter_spell"](ctx, {"min_power": 2, "max_power": 99, "max_energy": 99})
    assert not gs.chain or gs.chain[-1].card.name != "Big"


def test_failed_condition_does_not_spend_cost(monkeypatch):
    _register(monkeypatch, "Test Sands", [
        {"effect": "draw_cards", "trigger": "on_conquer", "count": 1, "cost": {"energy": 1},
         "condition": {"type": "you_have_n_or_fewer_runes", "params": {"n": 0}}}],
        category="Battlefield")
    loop = _loop()
    a = loop.gs.A
    a.add_rune(Domain.FURY)                  # 1 rune > 0 → condition fails
    a.energy = 1
    bf = loop.gs.battlefields[0]
    bf.card = BattlefieldCard(name="Test Sands")
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert a.energy == 1 and not a.hand


def test_annie_legend_readies_up_to_two_runes_at_end_of_turn():
    loop = _loop()
    a = loop.gs.A
    loop.gs.legend_unit_A = UnitInPlay(UnitCard(name="Annie Dark Child"))
    for _ in range(4):
        a.add_rune(Domain.FURY)
    for r in a.rune_pool[Domain.FURY]:
        r.ready = False
    loop._fire_turn_trigger("on_start_of_turn", "A")   # Annie's is an END-of-turn ability
    assert sum(r.ready for r in a.rune_pool[Domain.FURY]) == 0
    loop._fire_turn_trigger("on_end_of_turn", "A")
    assert sum(r.ready for r in a.rune_pool[Domain.FURY]) == 2   # up to 2, not all
