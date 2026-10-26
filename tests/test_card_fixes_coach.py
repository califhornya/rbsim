"""Cards fixed after the first coached games (2026-10-26), each checked against
its card image: EMPOWER costs (Steel Paws is [7], the source text said [1]),
EMPOWER abilities that were missing or never offered, "When I become
EMPOWERED" (a trigger the engine didn't have), and activated abilities whose
cost was missing so the engine never offered them."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup(*names, energy=0):
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    loop = GameLoop(gs)
    units = [UnitInPlay(card=CARD_REGISTRY[n].instantiate(), ready=True) for n in names]
    a.base_units.extend(units)
    a.energy = energy
    loop._recompute_passives()
    return loop, a, units


def _use(loop, name) -> bool:
    """Use `name`'s first offered ability; False if none is offered."""
    for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A"):
        if ga.kind == "ABILITY" and ga.label.endswith(f"({name})"):
            loop._apply_action(loop.gs.A, ga.to_engine())
            loop._recompute_passives()
            return True
    return False


def test_steel_paws_empowers_for_seven():
    loop, a, (paws,) = _setup("Steel Paws", energy=6)
    assert not _use(loop, "Steel Paws")
    a.energy = 7
    assert _use(loop, "Steel Paws")
    assert a.energy == 0 and paws.empowered and paws.might == 7


def test_apprentice_mage_predicts_when_it_becomes_empowered():
    loop, a, (mage,) = _setup("Apprentice Mage", energy=2)
    # Top of the deck = end of the list; PREDICT's baseline puts the mightiest on top.
    a.deck.cards = [UnitCard(name=n, might=m) for n, m in (("Z", 1), ("Big", 3), ("Top", 1))]
    assert _use(loop, "Apprentice Mage")
    assert mage.empowered and [c.name for c in a.deck.cards] == ["Z", "Top", "Big"]


def test_mel_defiant_soul_discards_a_spell_and_banishes_a_small_enemy_at_a_battlefield():
    loop, a, (mel,) = _setup("Mel Defiant Soul")
    a.hand = [UnitCard(name="Keep", might=1), SpellCard(name="Spare", cost_energy=1)]
    small = UnitInPlay(card=UnitCard(name="Small", might=3), ready=True)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.gs.B.base_units.append(UnitInPlay(card=UnitCard(name="AtHome", might=1), ready=True))
    assert _use(loop, "Mel Defiant Soul")
    assert [c.name for c in a.hand] == ["Keep"] and mel.empowered
    assert not loop.gs.battlefields[0].units_B and [c.name for c in loop.gs.B.banished] == ["Small"]
    assert [u.card.name for u in loop.gs.B.base_units] == ["AtHome"]       # not at a battlefield


def test_escaped_grayback_kills_another_friendly_unit_to_empower():
    loop, a, (grayback,) = _setup("Escaped Grayback")
    assert not _use(loop, "Escaped Grayback")                 # nothing else to kill
    a.base_units.append(UnitInPlay(card=UnitCard(name="Friend", might=1), ready=True))
    assert _use(loop, "Escaped Grayback")
    assert grayback.empowered and [u.card.name for u in a.base_units] == ["Escaped Grayback"]


def test_punching_poro_empowers_by_discarding():
    loop, a, (poro,) = _setup("Punching Poro")
    assert not _use(loop, "Punching Poro")                    # empty hand
    a.hand = [UnitCard(name="Card", might=1)]
    assert _use(loop, "Punching Poro")
    assert not a.hand and poro.empowered


def test_jinx_rebel_readies_when_you_discard():
    loop, a, (jinx,) = _setup("Jinx Rebel")
    jinx.ready = False
    might = jinx.might
    a.hand = [UnitCard(name="Card", might=1)]
    loop._discard(a, a.hand[0])
    loop._recompute_passives()
    assert jinx.ready and jinx.might == might + 1


def test_fretful_feline_grows_when_it_becomes_ready():
    loop, a, (cat,) = _setup("Fretful Feline")
    cat.ready = False
    might = cat.might
    loop._ready_active_units("A")
    loop._recompute_passives()
    assert cat.ready and cat.might == might + 2


def test_sett_brawler_spends_its_buff_for_four():
    loop, a, (sett,) = _setup("Sett Brawler")
    assert not _use(loop, "Sett Brawler")                     # no buff yet
    sett.might_counters = 1
    loop._recompute_passives()
    might = sett.might
    assert _use(loop, "Sett Brawler")
    assert sett.might_counters == 0 and sett.might == might - 1 + 4


def test_lux_crownguard_exhausts_for_two_energy_for_spells():
    loop, a, (lux,) = _setup("Lux Crownguard")
    assert _use(loop, "Lux Crownguard")
    assert not lux.ready and a.earmarked_energy_spell == 2
