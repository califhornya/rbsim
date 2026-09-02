"""Deck battlefields are placed in play and their own triggered abilities fire.

A single game uses one battlefield per player (chosen from the deck's up to 3).
The in-play Battlefield carries its identity card, so its on_conquer / on_hold /
on_start_of_turn abilities resolve for the scoring/active player.
"""

from __future__ import annotations

import random
from pathlib import Path

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import BattlefieldCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.game_factory import build_game
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY, CardSpec

REPO = Path(__file__).resolve().parent.parent
KENNEN = REPO / "riftbound" / "data" / "decks" / "vendetta_kennen.json"


def test_build_game_places_deck_battlefields():
    gs = build_game(game_seed=3, deck_a_path=KENNEN, deck_b_path=KENNEN,
                    ai_a="simple_trade", ai_b="simple_trade")
    # Both in-play battlefields carry an identity card from the decks.
    assert all(bf.card is not None for bf in gs.battlefields)
    assert all(bf.card.category.name == "BATTLEFIELD" for bf in gs.battlefields)


def test_battlefield_on_conquer_fires():
    spec = CardSpec.from_dict({
        "name": "Test BF Draw", "category": "Battlefield",
        "effects": [{"effect": "draw_cards", "trigger": "on_conquer", "target": "actor", "count": 1}],
    })
    CARD_REGISTRY[spec.name] = spec

    deck = Deck(cards=[UnitCard(name=f"C{i}", might=1) for i in range(5)])
    a = Player(name="A", deck=deck, rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b,
                   battlefields=[Battlefield(card=BattlefieldCard(name="Test BF Draw")), Battlefield()])
    loop = GameLoop(gs)

    hand_before = len(a.hand)
    loop._fire_scoring_trigger("on_conquer", gs.battlefields[0], "A")
    assert len(a.hand) == hand_before + 1  # the battlefield drew for the conqueror


def test_battlefield_without_card_is_noop():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b)  # default: cardless battlefields
    loop = GameLoop(gs)
    loop._fire_scoring_trigger("on_conquer", gs.battlefields[0], "A")  # must not raise


# --- Slice 3: battlefield rule-modifier passives (Void Gate, Heisho Shell) ----

def _bare_loop() -> GameLoop:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    return GameLoop(GameState(rng=random.Random(1), A=a, B=b, active="A"))


def test_bf_passive_amount_reads_authored_markers():
    """The query helper reads the passive marker verbs authored on the real
    Void Gate / Heisho Shell corpus cards; absent/None → default 0."""
    loop = _bare_loop()
    void_gate = Battlefield(card=BattlefieldCard(name="Void Gate"))
    heisho = Battlefield(card=BattlefieldCard(name="Heisho Shell of the World"))
    plain = Battlefield()  # cardless

    assert loop._bf_passive_amount(void_gate, "bonus_damage_here") == 1
    assert loop._bf_passive_amount(void_gate, "ignore_deflect_here") == 0
    assert loop._bf_passive_amount(heisho, "ignore_deflect_here") == 1
    assert loop._bf_passive_amount(plain, "bonus_damage_here") == 0
    assert loop._bf_passive_amount(None, "bonus_damage_here") == 0


def test_void_gate_adds_bonus_damage_to_units_here():
    """A might-3 enemy unit survives 2 spell damage on a plain battlefield but dies
    on Void Gate (2 + 1 bonus = 3 >= 3)."""
    for bf_name, should_die in (("Void Gate", True), (None, False)):
        loop = _bare_loop()
        bf = Battlefield(card=BattlefieldCard(name=bf_name)) if bf_name else Battlefield()
        victim = UnitInPlay(UnitCard(name="Grunt", might=3), ready=True)
        bf.units_B.append(victim)
        ctx = EffectContext(loop=loop, card=SpellCard(name="TST Bolt"),
                            actor=loop.gs.A, opponent=loop.gs.B, battlefield=bf)
        ctx.deal_damage(2, target="opponent")
        died = victim not in bf.units_B
        assert died is should_die, f"{bf_name!r}: died={died}, expected {should_die}"


def test_sandswept_tomb_reduces_power_for_friendly_targeting_spells():
    """Sandswept Tomb: a spell that chooses friendly units here costs 1 power less;
    a spell that doesn't choose friendly units (e.g. plain damage) is unaffected,
    and neither is discounted at a plain battlefield."""
    friendly = CardSpec.from_dict({
        "name": "TST Friendly Buff", "category": "Spell",
        "effects": [{"effect": "grant_might", "target": "ally", "amount": 2}],
    })
    enemy = CardSpec.from_dict({
        "name": "TST Enemy Bolt", "category": "Spell",
        "effects": [{"effect": "deal_damage", "amount": 2}],  # no target → enemy
    })
    CARD_REGISTRY[friendly.name] = friendly
    CARD_REGISTRY[enemy.name] = enemy
    try:
        loop = _bare_loop()
        loop.gs.battlefields[0] = Battlefield(card=BattlefieldCard(name="Sandswept Tomb"))
        buff = SpellCard(name="TST Friendly Buff")
        bolt = SpellCard(name="TST Enemy Bolt")

        # Friendly-targeting spell at the Tomb → 1 power off.
        assert loop._bf_cost_reduction(buff, 0) == (0, 1)
        # Non-friendly spell → no reduction (requires_target: friendly).
        assert loop._bf_cost_reduction(bolt, 0) == (0, 0)
        # Plain battlefield → no reduction for anyone.
        assert loop._bf_cost_reduction(buff, 1) == (0, 0)
    finally:
        CARD_REGISTRY.pop(friendly.name, None)
        CARD_REGISTRY.pop(enemy.name, None)


def test_heisho_shell_waives_deflect_surcharge():
    """DEFLECT normally surcharges an enemy-targeting spell; Heisho Shell waives it."""
    spec = CardSpec.from_dict({
        "name": "TST Deflect Bolt", "category": "Spell",
        "effects": [{"effect": "deal_damage", "amount": 2}],  # no target → enemy
    })
    CARD_REGISTRY[spec.name] = spec
    try:
        bolt = SpellCard(name="TST Deflect Bolt")
        # Plain battlefield with a DEFLECT 2 enemy unit → surcharge 2.
        plain = _bare_loop()
        plain.gs.battlefields[0].units_B.append(
            UnitInPlay(UnitCard(name="Warden", might=1, keywords=["DEFLECT 2"]), ready=True))
        assert plain._deflect_surcharge(bolt, 0) == 2

        # Same unit, but the battlefield waives DEFLECT while paying here → 0.
        heisho = _bare_loop()
        heisho.gs.battlefields[0] = Battlefield(
            card=BattlefieldCard(name="Heisho Shell of the World"))
        heisho.gs.battlefields[0].units_B.append(
            UnitInPlay(UnitCard(name="Warden", might=1, keywords=["DEFLECT 2"]), ready=True))
        assert heisho._deflect_surcharge(bolt, 0) == 0
    finally:
        CARD_REGISTRY.pop(spec.name, None)
