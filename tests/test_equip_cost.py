"""EQUIP cost (§744): equipping charges the gear's EQUIP-ability cost (parsed from
its rules text, e.g. "Equip [fury]" = 1 Fury power), NOT the gear's play cost.
Non-Equipment gear has no Equip ability and cannot be equipped.
"""

from __future__ import annotations

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, Rune, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b))


def _cost(loop, name):
    return loop._equip_cost(CARD_REGISTRY[name].instantiate())


def test_equip_cost_parses_domain_and_energy():
    loop = _loop()
    assert _cost(loop, "Serrated Dirk") == {          # "Equip [fury]"
        "energy": 0, "domain_power": {"fury": 1}, "generic": 0, "complex": False}
    assert _cost(loop, "Skyfall of Areion")["energy"] == 1        # "Equip [1] [fury]"
    assert _cost(loop, "Skyfall of Areion")["domain_power"] == {"fury": 1}
    assert _cost(loop, "Spinning Axe")["generic"] == 1            # "Equip [rune]"
    assert _cost(loop, "Blighted Battleaxe") == {                 # "Equip [1] [fury]"
        "energy": 1, "domain_power": {"fury": 1}, "generic": 0, "complex": False}


def test_non_equipment_gear_has_no_equip_cost():
    loop = _loop()
    assert _cost(loop, "Iron Ballista") is None      # a tap-ability gear, not Equipment


def test_every_equipment_gear_parses():
    # Every GEAR card whose text has an Equip ability must parse to a cost. (Units
    # with WEAPONMASTER mention "Equip" in reminder text but are not equippable gear.)
    loop = _loop()
    unparsed = []
    for name, spec in CARD_REGISTRY.items():
        if (spec.raw or {}).get("category") != "Gear":
            continue
        if "equip" in ((spec.raw or {}).get("effect") or "").lower():
            if loop._equip_cost(spec.instantiate()) is None:
                unparsed.append(name)
    assert unparsed == [], f"Equipment gear with unparseable cost: {unparsed}"


def test_equip_charges_equip_cost_not_play_cost():
    # Serrated Dirk: play cost = 1 energy; EQUIP cost = 1 Fury power. Equipping must
    # spend the Fury (not the energy) and attach to a friendly unit.
    loop = _loop(); ap = loop.gs.A; loop.gs.active = "A"
    dirk = CARD_REGISTRY["Serrated Dirk"].instantiate()
    ap.base_gear.append(dirk)
    unit = UnitInPlay(UnitCard(name="Ally", might=2), ready=True)
    loop.gs.battlefields[0].units_A.append(unit)
    ap.energy = 5
    ap.power_pool[Domain.FURY] = 1
    ap.rune_pool[Domain.FURY] = [Rune(domain=Domain.FURY)]

    # find the equip entry's index and activate it
    abilities = loop.activatable_abilities("A")
    idx = next(i for i, e in enumerate(abilities)
               if e["type"] == "equip" and e["gear"] is dirk)
    loop._apply_activated_ability(ap, loop.gs.B, idx)

    assert dirk in unit.gear                 # attached
    assert dirk not in ap.base_gear
    assert ap.power_pool.get(Domain.FURY, 0) == 0   # Fury spent
    assert ap.energy == 5                     # play-cost energy NOT re-charged
