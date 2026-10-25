"""The ten meta-deck cards that did nothing (2026-10-25), each against its text,
plus the engine pieces they needed: cost auras, "the next card costs less",
delayed end-of-turn effects, "if I died alone", choosing / readying triggers,
"when an opponent plays a unit", gear TEMPORARY, blink, "disempower me" costs,
and keywords given "this turn" that now expire."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]),
               rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _unit(name, **kw):
    return UnitInPlay(card=_card(name), **kw)


def test_eager_apprentice_discounts_spells_only_at_a_battlefield():
    loop = _loop()
    a = loop.gs.A
    apprentice = _unit("Eager Apprentice")
    spell = SpellCard(name="S", cost_energy=3)
    cheap = SpellCard(name="Cheap", cost_energy=1)
    a.base_units.append(apprentice)
    assert loop._effective_cost(spell, a, 0)[0] == 3          # in base: no discount
    a.base_units.remove(apprentice)
    loop.gs.battlefields[0].add_unit("A", apprentice)
    assert loop._effective_cost(spell, a, 0)[0] == 2
    assert loop._effective_cost(cheap, a, 0)[0] == 1          # to a minimum of [1]
    assert loop._effective_cost(UnitCard(name="U", cost_energy=3), a)[0] == 3


def test_targons_peak_readies_two_runes_at_the_end_of_the_turn():
    loop = _loop()
    a = loop.gs.A
    for _ in range(3):
        a.add_rune(Domain.FURY, ready=False)
    bf = loop.gs.battlefields[0]
    bf.card = _card("Targon's Peak")
    loop._resolve_triggered_effects(bf.card, "on_conquer", bf, a, loop.gs.B,
                                    context_extra={"battlefield": bf})
    assert a.energy == 0                                     # not yet
    loop._resolve_delayed_effects()
    assert a.energy == 2


def test_lonely_poro_draws_only_if_it_died_alone():
    for with_friend, draws in ((False, 1), (True, 0)):
        loop = _loop()
        a = loop.gs.A
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Lonely Poro"))
        if with_friend:
            bf.add_unit("A", UnitInPlay(card=UnitCard(name="Friend", might=9)))
        bf.add_unit("B", UnitInPlay(card=UnitCard(name="Killer", might=9)))
        ctx = EffectContext(loop, UnitCard(name="Zap"), loop.gs.B, a, bf)
        REGISTRY["kill_unit"](ctx, {"target": "enemy_unit", "target_filter": {"might_at_most": 3}})
        assert len(a.hand) == draws


def test_irelia_fervent_grows_when_chosen_or_readied():
    loop = _loop()
    a = loop.gs.A
    irelia = _unit("Irelia Fervent")
    loop.gs.battlefields[0].add_unit("A", irelia)
    ctx = EffectContext(loop, SpellCard(name="Buff"), a, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["ready_unit"](ctx, {"target": "friendly_unit"})   # chosen (+1) and readied (+1)
    assert irelia.temporary_might == 2
    REGISTRY["ready_unit"](ctx, {"target": "friendly_unit"})   # chosen again, already ready
    assert irelia.temporary_might == 3


def test_ezreal_legend_draws_after_two_enemy_choices():
    loop = _loop()
    a = loop.gs.A
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Ezreal Prodigal Explorer"), ready=True)
    loop.gs.battlefields[0].add_unit("B", UnitInPlay(card=UnitCard(name="E", might=9)))
    ctx = EffectContext(loop, SpellCard(name="Ping"), a, loop.gs.B, loop.gs.battlefields[0])

    def offered():
        return [ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if ga.kind == "ABILITY"]

    REGISTRY["deal_damage"](ctx, {"target": "enemy_unit", "amount": 1})
    assert offered() == []
    REGISTRY["stun_unit"](ctx, {"target": "enemy_unit"})
    assert len(offered()) == 1
    loop._apply_action(a, offered()[0].to_engine())
    assert len(a.hand) == 1


def test_turn_to_dust_kills_their_best_gear_next_beginning_phase():
    loop = _loop()
    b = loop.gs.B
    cheap, pricey = GearCard(name="Cheap", cost_energy=1), GearCard(name="Pricey", cost_energy=5)
    b.base_gear.extend([cheap, pricey])
    loop._resolve_card_effects(_card("Turn to Dust"), loop.gs.battlefields[0], loop.gs.A, b)
    assert pricey in b.base_gear                              # not yet
    loop._phase_beginning("B")
    assert b.base_gear == [cheap] and b.trash == [pricey]


def test_vex_apathetic_stuns_and_pins_a_unit_the_opponent_plays():
    loop = _loop()
    vex = _unit("Vex Apathetic")
    loop.gs.battlefields[0].add_unit("B", vex)
    a = loop.gs.A
    a.hand.append(UnitCard(name="Newcomer", cost_energy=0))
    loop._apply_action(a, ("UNIT", 0, 0, None))
    newcomer = a.base_units[0]
    assert newcomer.stunned and newcomer.cant_move_turn == loop.gs.turn
    newcomer.ready = True
    assert not [ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if ga.kind == "MOVE"]


def test_thrill_of_the_hunt_replays_a_unit_where_it_attacks():
    loop = _loop()
    a = loop.gs.A
    hunter = UnitInPlay(card=UnitCard(name="Hunter", might=4))
    a.base_units.append(hunter)
    loop.gs.battlefields[1].add_unit("B", UnitInPlay(card=UnitCard(name="Prey", might=3)))
    loop._resolve_card_effects(_card("Thrill of the Hunt"), loop.gs.battlefields[0], a, loop.gs.B)
    assert [u.card.name for u in loop.gs.battlefields[1].units_A] == ["Hunter"]
    assert a.base_units == []
    assert loop.gs.cards_played_this_turn["A"] == 1           # it was played again


def test_astral_heron_discounts_the_second_card():
    loop = _loop()
    a = loop.gs.A
    loop.gs.battlefields[0].add_unit("A", _unit("Astral Heron"))
    second = UnitCard(name="Second", cost_energy=5, cost_power=2, domain=Domain.CALM)
    second.cost_power_domain = Domain.CALM
    assert loop._effective_cost(second, a) == (5, 2)
    a.hand.append(SpellCard(name="First", cost_energy=0))
    loop._apply_action(a, ("SPELL", 0, 0, None))
    assert loop._effective_cost(second, a) == (3, 0)          # [2] and two Power less
    a.hand.append(SpellCard(name="Free", cost_energy=0))
    loop._apply_action(a, ("SPELL", 0, 0, None))              # the 2nd card used it up
    assert loop._effective_cost(second, a) == (5, 2)


def test_kennen_legend_empowers_then_disempowers_for_assault():
    loop = _loop()
    a = loop.gs.A
    loop.gs.legend_unit_A = legend = UnitInPlay(card=_card("Kennen Heart of the Tempest"), ready=True)
    fighter = UnitInPlay(card=UnitCard(name="Fighter", might=2))
    loop.gs.battlefields[1].add_unit("A", fighter)

    def offered():
        return [ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if ga.kind == "ABILITY"]

    assert offered() == []                                    # not empowered
    a.trash.append(UnitCard(name="Back", cost_energy=0))
    loop._resolve_card_effects(_card("Spectral Matron"), loop.gs.battlefields[0], a, loop.gs.B)
    assert legend.empowered                                   # a card played from the trash
    loop._apply_action(a, offered()[0].to_engine())
    assert not legend.empowered and not legend.ready
    assert fighter.keyword_value("ASSAULT") == 2


def test_keywords_given_this_turn_expire_and_leave_the_card_alone():
    loop = _loop()
    unit = UnitInPlay(card=UnitCard(name="U", might=1))
    loop.gs.battlefields[0].add_unit("A", unit)
    ctx = EffectContext(loop, SpellCard(name="S"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0])
    REGISTRY["give_temporary_assault"](ctx, {"target": "friendly_unit", "amount": 2})
    REGISTRY["give_temporary_assault"](ctx, {"target": "friendly_unit", "amount": 2})
    assert unit.keyword_value("ASSAULT") == 4                 # instances add up
    assert unit.card.keywords == []
    loop._end_turn()
    assert unit.keyword_value("ASSAULT") == 0


def test_single_target_damage_doesnt_spill_and_groups_hit_each():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    small, big = UnitInPlay(card=UnitCard(name="Small", might=1)), UnitInPlay(card=UnitCard(name="Big", might=3))
    bf.add_unit("B", small)
    bf.add_unit("B", big)
    ctx = EffectContext(loop, SpellCard(name="Bolt"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["deal_damage"](ctx, {"target": "enemy_unit", "amount": 3})
    assert bf.units_B == [small] and small.damage == 0    # Big killed, nothing spilled
    bf.add_unit("B", UnitInPlay(card=UnitCard(name="Other", might=2)))
    REGISTRY["deal_damage"](ctx, {"target": "all_enemy_units_here", "scope": "all", "amount": 2})
    assert bf.units_B == []                               # 2 to each


def test_split_damage_divides_among_enemies():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    for m in (2, 2, 4):
        bf.add_unit("B", UnitInPlay(card=UnitCard(name=f"M{m}", might=m)))
    loop._resolve_card_effects(_card("Scorched Earth"), bf, loop.gs.A, loop.gs.B)
    assert [u.card.name for u in bf.units_B] == ["M4"]     # 2 + 2, then 1 on the 4


def test_hard_bargain_counters_unless_they_pay_and_abandon_returns_it():
    from riftbound.core.state import ChainItem
    for energy, countered in ((2, False), (1, True)):
        loop = _loop()
        loop.gs.A.energy = energy
        target = SpellCard(name="Theirs", cost_energy=1)
        loop.gs.chain.append(ChainItem(player="A", card=target, bf_idx=0))
        loop._resolve_card_effects(_card("Hard Bargain"), loop.gs.battlefields[0], loop.gs.B, loop.gs.A)
        assert (not loop.gs.chain) is countered
    loop = _loop()
    target = SpellCard(name="Theirs", cost_energy=1)
    loop.gs.chain.append(ChainItem(player="A", card=target, bf_idx=0))
    loop._resolve_card_effects(_card("Abandon"), loop.gs.battlefields[0], loop.gs.B, loop.gs.A)
    assert target in loop.gs.A.hand


def test_debuff_floor_and_ready_up_to_n():
    loop = _loop()
    bf = loop.gs.battlefields[0]
    enemy = UnitInPlay(card=UnitCard(name="E", might=2))
    bf.add_unit("B", enemy)
    ctx = EffectContext(loop, UnitCard(name="Src"), loop.gs.A, loop.gs.B, bf)
    REGISTRY["grant_temporary_might"](ctx, {"target": "enemy_unit", "amount": -3, "minimum": 1})
    assert enemy.might == 1
    a = loop.gs.A
    tired = [UnitInPlay(card=UnitCard(name=f"T{i}", might=i + 1)) for i in range(5)]
    a.base_units.extend(tired)
    loop._resolve_card_effects(_card("Acceleration Gate"), bf, a, loop.gs.B)
    assert sum(u.ready for u in tired) == 4 and not tired[0].ready   # the 4 mightiest
