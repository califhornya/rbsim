"""Cost rules: resources spent as you play (Kraken Hunter's buffs, Commander
Ledros's tokens, Poppy Defender's XP), Void Drone off-hand, Orianna Mechanical
Marvel's once-a-turn gear discount, Vex Cheerless in combat, Risen Altar's
EMPOWER discount, Dragon Roost, mandatory additional costs (Legion
Quartermaster, Stalking Wolf), Spirit of the Forge, Jayce Man of Progress,
Teemo Swift Scout's hide, Noxus Saboteur."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield, FacedownCard
from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs)


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _u(name, might=2, tags=None, **kw):
    return UnitInPlay(card=UnitCard(name=name, might=might, tags=list(tags or [])), **kw)


def test_kraken_hunter_spends_buffs_for_its_body_pips():
    loop = _loop()
    ap = loop.gs.A
    for i in range(2):
        u = _u(f"B{i}")
        u.might_counters = 1
        ap.base_units.append(u)
    kraken = _card("Kraken Hunter")
    assert loop._effective_cost(kraken, ap) == (3, 0)
    ap.hand = [kraken]
    ap.energy = 3
    loop._apply_action(ap, ("UNIT", 0, 0, None))
    assert any(u.card is kraken for u in ap.base_units)
    assert sum(u.might_counters for u in ap.base_units if u.card is not kraken) == 0


def test_commander_ledros_eats_tokens_and_poppy_spends_xp():
    loop = _loop()
    ap = loop.gs.A
    loop._play_token("Recruit", "A")
    ledros = _card("Commander Ledros")
    assert loop._effective_cost(ledros, ap)[1] == 3
    loop.gs.add_xp("A", 3)
    assert loop._effective_cost(_card("Poppy Defender of the Meek"), ap)[0] == 3


def test_void_drone_is_cheaper_from_banishment():
    loop = _loop()
    drone = _card("Void Drone")
    assert loop._effective_cost(drone, loop.gs.A)[0] == 3
    assert loop._effective_cost(drone, loop.gs.A, from_zone="banished")[0] == 1


def test_orianna_discounts_one_gear_a_turn():
    loop = _loop()
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=_card("Orianna Mechanical Marvel")))
    gear = GearCard(name="G", cost_energy=3)
    assert loop._effective_cost(gear, loop.gs.A)[0] == 2
    loop._play_gear(gear, "A", 0)
    assert loop._effective_cost(GearCard(name="H", cost_energy=3), loop.gs.A)[0] == 3


def test_vex_cheerless_in_a_showdown():
    loop = _loop()
    loop.gs.battlefields[0].add_unit("A", UnitInPlay(card=_card("Vex Cheerless")))
    spell = SpellCard(name="S", cost_energy=4)
    loop.gs.showdown_active, loop.gs.showdown_bf_idx = True, 0
    assert loop._effective_cost(spell, loop.gs.A)[0] == 2
    assert loop._effective_cost(spell, loop.gs.B)[0] == 6
    cheap = SpellCard(name="C", cost_energy=1)
    assert loop._effective_cost(cheap, loop.gs.A)[0] == 1


def test_risen_altar_cuts_empower_costs_here():
    loop = _loop()
    bf0 = loop.gs.battlefields[0]
    bf0.card = _card("Risen Altar")
    hunter = UnitInPlay(card=_card("Brutal Hunter"), ready=True)      # EMPOWER [3]
    bf0.add_unit("A", hunter)
    loop.gs.A.energy = 2
    (idx, entry), = [(i, e) for i, e in enumerate(loop.activatable_abilities("A")) if e.get("unit") is hunter]
    assert loop._ability_usable(loop.gs.A, entry)
    loop._apply_action(loop.gs.A, ("ABILITY", "ACTIVATED", idx, None))
    assert hunter.empowered and loop.gs.A.energy == 0


def test_dragon_roost_lets_a_dragon_in_for_two_power():
    loop = _loop()
    bf1 = loop.gs.battlefields[1]
    bf1.card = _card("Dragon Roost")
    dragon = UnitCard(name="Wyrm", might=4, cost_energy=0, tags=["Dragon"])
    assert loop._unit_play_destinations(dragon, "A") == [None, 1]
    loop.gs.A.hand = [dragon]
    loop.gs.A.add_power(Domain.FURY, 2)
    loop._apply_action(loop.gs.A, ("UNIT", 0, 0, 1))
    assert any(u.card is dragon for u in bf1.units_A) and not loop.gs.A.power_pool


def test_legion_quartermaster_needs_and_returns_a_gear():
    loop = _loop()
    qm = _card("Legion Quartermaster")
    assert not loop._can_pay_card(loop.gs.A, qm, 0, 0)
    gear = GearCard(name="Spare", cost_energy=1)
    loop.gs.A.base_gear.append(gear)
    loop._play_unit(qm, "A")
    assert gear in loop.gs.A.hand


def test_stalking_wolf_kills_a_pet():
    loop = _loop()
    wolf = _card("Stalking Wolf")
    assert not loop._can_pay_card(loop.gs.A, wolf, 0, 0)
    bf1 = loop.gs.battlefields[1]
    poro = _u("Poro", 1, ["Poro"])
    bf1.add_unit("A", poro)
    loop.gs.battlefields[1].add_unit("B", _u("Enemy"))
    assert 1 in loop._unit_play_destinations(wolf, "A")
    loop._play_unit(wolf, "A", bf=bf1)
    assert poro not in bf1.units_A and any(u.card is wolf for u in bf1.units_A)


def test_spirit_of_the_forge_and_jayce_trade_gear():
    loop = _loop()
    ap = loop.gs.A
    gear = GearCard(name="Anvil", cost_energy=4)
    ap.base_gear.append(gear)
    spirit = loop._play_unit(_card("Spirit of the Forge"), "A")
    assert gear in ap.hand and spirit.ready and spirit.might == int(spirit.card.might) + 4
    loop = _loop()
    ap = loop.gs.A
    ap.base_gear.append(GearCard(name="Junk", cost_energy=1))
    big = GearCard(name="Big", cost_energy=7)
    ap.hand = [big]
    loop._play_unit(_card("Jayce Man of Progress"), "A")
    assert big in ap.base_gear and [c.name for c in ap.trash] == ["Junk"]


def test_teemo_hides_for_energy_and_saboteur_blocks_reveals():
    loop = _loop()
    loop.gs.legend_unit_A = UnitInPlay(card=_card("Teemo Swift Scout"))
    assert loop._can_hide_pay(loop.gs.A, "A") is False
    loop.gs.A.energy = 1
    assert loop._can_hide_pay(loop.gs.A, "A")
    bf0 = loop.gs.battlefields[0]
    bf0.facedown = FacedownCard(card=SpellCard(name="Trap"), owner="A", turn_hidden=0)
    loop.gs.turn = 2
    assert loop._hidden_playable_lanes("A") == [0]
    bf0.add_unit("B", UnitInPlay(card=_card("Noxus Saboteur")))
    assert loop._hidden_playable_lanes("A") == []
