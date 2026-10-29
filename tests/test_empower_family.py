"""EMPOWER on units, legends and gear: gear abilities that empower or need
"Disempower this" (Questionable Tome, Hextech Disc, Platewyrm Egg, Tools of
Empire, Glowstone), "When you empower something else, empower me" (Mel,
Ambessa), "When you banish a card you own" (Zed), Lacerate, Sanction,
Hextech Formula, Profiteer, Helm of Suppression."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import REGISTRY
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[UnitCard(name=f"C{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[UnitCard(name=f"D{i}") for i in range(5)]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _abilities(loop, card, side="A"):
    return [(i, e) for i, e in enumerate(loop.activatable_abilities(side))
            if e.get("gear") is card or (e.get("unit") is not None and e["unit"].card is card)]


def _use(loop, idx, side="A"):
    loop._apply_action(loop.gs.get_player(side), ("ABILITY", "ACTIVATED", idx, None))


def test_questionable_tome_empowers_then_disempowers_to_draw():
    loop = _loop()
    ap = loop.gs.A
    tome = _card("Questionable Tome")
    ap.base_gear.append(tome)
    (idx, _), = [(i, e) for i, e in _abilities(loop, tome) if loop._ability_usable(ap, e)]
    _use(loop, idx)
    assert tome.empowered and tome.tapped
    tome.tapped = False
    ap.energy = 1
    usable = [(i, e) for i, e in _abilities(loop, tome) if loop._ability_usable(ap, e)]
    assert [e["eff"].effect for _, e in usable] == ["draw_cards"]     # empower is hidden
    _use(loop, usable[0][0])
    assert not tome.empowered and len(ap.hand) == 1


def test_platewyrm_egg_adds_more_when_empowered():
    loop = _loop()
    ap = loop.gs.A
    egg = _card("Platewyrm Egg")
    ap.base_gear.append(egg)
    loop.gs.active = "B"                                   # reaction window
    usable = [e["eff"].params.get("amount") for _, e in _abilities(loop, egg) if loop._ability_usable(ap, e)]
    assert usable == [1]
    egg.empowered = True
    usable = [e["eff"].params.get("amount") for _, e in _abilities(loop, egg) if loop._ability_usable(ap, e)]
    assert usable == [2]


def test_mel_and_ambessa_follow_an_empower_without_looping():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Mel Soul's Reflection"))
    ambessa = UnitInPlay(card=_card("Ambessa Matriarch of War"))
    loop.gs.A.base_units.append(ambessa)
    unit = UnitInPlay(card=UnitCard(name="U", might=2))
    loop.gs.battlefields[0].add_unit("A", unit)
    loop._empower(unit.card, "A")
    assert unit.empowered and loop.gs.legend_unit_A.empowered and ambessa.empowered


def test_zed_empowers_when_you_banish_your_card():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Zed Master of Shadows"))
    loop.gs.A.trash = [UnitCard(name="Old")]
    ctx = EffectContext(loop, SpellCard(name="S"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["banish_card"](ctx, {"from": "trash"})
    assert loop.gs.legend_unit_A.empowered


def test_lacerate_disempowers_then_kills_what_drops_to_three():
    loop = _loop()
    witness = UnitInPlay(card=_card("Mournful Witness"))   # EMPOWERED: +2
    witness.empowered = True
    big = UnitInPlay(card=UnitCard(name="Big", might=6))
    loop.gs.battlefields[0].add_unit("B", witness)
    loop.gs.battlefields[0].add_unit("B", big)
    loop._recompute_passives()
    assert witness.might > 3
    loop._resolve_card_effects(_card("Lacerate"), loop.gs.battlefields[0], loop.gs.A, loop.gs.B)
    assert witness not in loop.gs.battlefields[0].units_B and big in loop.gs.battlefields[0].units_B


def test_sanction_empowers_until_end_of_turn():
    loop = _loop()
    unit = UnitInPlay(card=UnitCard(name="U", might=2))
    loop.gs.battlefields[0].add_unit("A", unit)
    loop._resolve_card_effects(_card("Sanction"), loop.gs.battlefields[0], loop.gs.A, loop.gs.B)
    assert unit.empowered
    loop._resolve_delayed_effects()
    assert not unit.empowered


def test_hextech_formula_empowers_another_gear():
    loop = _loop()
    formula, tools = _card("Hextech Formula"), _card("Tools of Empire")
    loop.gs.A.base_gear += [formula, tools]
    ctx = EffectContext(loop, formula, loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["empower_self"](ctx, CARD_REGISTRY["Hextech Formula"].effects[0].merged_params())
    assert tools.empowered and not getattr(formula, "empowered", False)


def test_glowstone_given_away_hurts_its_new_controller():
    loop = _loop()
    ap = loop.gs.A
    glow = _card("Glowstone")
    ap.base_gear.append(glow)
    glow.empowered = True
    (idx, _), = [(i, e) for i, e in _abilities(loop, glow)
                 if e["eff"].effect == "give_this_to_opponent" and loop._ability_usable(ap, e)]
    _use(loop, idx)
    assert glow in loop.gs.B.base_gear
    victim = UnitInPlay(card=UnitCard(name="V", might=4))
    loop.gs.battlefields[0].add_unit("B", victim)
    loop._fire_turn_trigger("on_end_of_turn", "B")
    assert victim not in loop.gs.battlefields[0].units_B and glow not in loop.gs.B.base_gear


def test_helm_of_suppression_taxes_opponents_spells():
    loop = _loop()
    helm = _card("Helm of Suppression")
    loop.gs.A.base_gear.append(helm)
    spell = SpellCard(name="S", cost_energy=2)
    assert loop._effective_cost(spell, loop.gs.B)[0] == 3
    assert loop._effective_cost(spell, loop.gs.A)[0] == 2
    assert loop._effective_cost(helm, loop.gs.A)[0] == int(helm.cost_energy)
    helm.empowered = True
    assert loop._effective_cost(spell, loop.gs.B)[0] == 4


def test_profiteer_moves_an_unused_empower_to_a_card_that_uses_it():
    loop = _loop()
    plain = UnitInPlay(card=UnitCard(name="Plain", might=2))
    plain.empowered = True
    witness = UnitInPlay(card=_card("Mournful Witness"))
    loop.gs.battlefields[0].add_unit("A", plain)
    loop.gs.battlefields[0].add_unit("A", witness)
    ctx = EffectContext(loop, _card("Profiteer"), loop.gs.A, loop.gs.B, loop.gs.battlefields[0], {})
    REGISTRY["move_empowerment"](ctx, {})
    assert witness.empowered and not plain.empowered


def test_a_cards_target_filter_reaches_its_handler():
    # Twilight Step: "Move a unit with 3 [might] or less" (the filter used to be dropped).
    loop = _loop()
    big, small = UnitInPlay(card=UnitCard(name="Big", might=6)), UnitInPlay(card=UnitCard(name="Small", might=2))
    loop.gs.battlefields[0].add_unit("B", big)
    loop.gs.battlefields[0].add_unit("B", small)
    loop._resolve_card_effects(_card("Twilight Step"), loop.gs.battlefields[0], loop.gs.A, loop.gs.B)
    assert big in loop.gs.battlefields[0].units_B and small not in loop.gs.battlefields[0].units_B


def test_hall_of_legends_readies_your_legend_and_factory_recall_bounces_gear():
    loop = _loop()
    legend = UnitInPlay(card=_card("Jax Grandmaster at Arms"), ready=False)
    loop.gs.legend_unit_A = legend
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Hall of Legends")
    loop.gs.A.energy = 1
    loop._fire_scoring_trigger("on_conquer", bf0, "A")
    assert legend.ready and loop.gs.A.energy == 0
    relic = _card("Long Sword")
    loop.gs.B.base_gear.append(relic)
    loop._resolve_card_effects(_card("Factory Recall"), bf0, loop.gs.A, loop.gs.B)
    assert relic in loop.gs.B.hand and not loop.gs.B.base_gear
