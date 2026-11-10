"""F part 2: the engine's own choices when nobody chooses (BACKLOG F).

Each is a GameLoop.choose call with a baseline: a player (the search, the
coach, a test) may answer it; nobody answering, the baseline holds.
"""

from __future__ import annotations

from riftbound.registry.cards_registry import CARD_REGISTRY

from tests.test_hidden import _control, _hidden_unit, _loop


def _picks(*names):
    """A chooser answering each choice whose options include one of `names`
    (by card name, in order); None for the rest."""
    left = list(names)

    def chooser(loop, kind, side, options, default, source):
        for i, o in enumerate(options):
            card = getattr(o, "card", o)
            if left and getattr(card, "name", None) == left[0]:
                left.pop(0)
                return i
        return None
    return chooser


# --- a facedown card trashed for lack of room (§107.3.b.2) -------------------

def _two_hidden_then_trap_dies(chooser=None):
    loop = _loop(power=2)
    loop.gs.A.hand.extend([_hidden_unit("One"), _hidden_unit("Two")])
    _control(loop, "A", 0)
    bf = loop.gs.battlefields[0]
    loop._deploy_gear("A", bf, CARD_REGISTRY["Bushwhack Trap"].instantiate())
    assert loop._hide_card("A", 0, 0) and loop._hide_card("A", 0, 0)
    seen = []

    def record(loop_, kind, side, options, default, source):
        seen.append((kind, side, [getattr(o, "name", o) for o in options]))
        return chooser(loop_, kind, side, options, default, source) if chooser else None
    loop.chooser = record
    loop._kill_deployed_gear(bf, "A", list(bf.gear_A))
    return loop, bf, seen


def test_the_zone_controller_chooses_which_facedown_card_to_trash():
    loop, bf, seen = _two_hidden_then_trap_dies(_picks("One"))
    assert ("facedown_trash", "A", ["One", "Two"]) in seen
    assert [fd.card.name for fd in bf.facedowns] == ["Two"]
    assert "One" in [c.name for c in loop.gs.A.trash]


def test_facedown_trash_baseline_is_the_newest():
    loop, bf, _seen = _two_hidden_then_trap_dies()
    assert [fd.card.name for fd in bf.facedowns] == ["One"]
    assert "Two" in [c.name for c in loop.gs.A.trash]


def test_the_coach_asks_which_facedown_card_to_trash():
    from riftbound.ai.coach import _SHORT, question
    assert "coperta" in question("facedown_trash")
    assert "facedown_trash" in _SHORT


# --- discards ----------------------------------------------------------------

def _hand_loop():
    from riftbound.core.cards import SpellCard
    from tests.test_corpus_cards import _setup
    loop, a, b = _setup()
    big = SpellCard(name="Big", cost_energy=6)
    small = SpellCard(name="Small", cost_energy=1)
    mid = SpellCard(name="Mid", cost_energy=3)
    return loop, a, b, big, small, mid


def test_discard_baseline_is_the_cheapest_own_card():
    loop, a, _b, big, small, mid = _hand_loop()
    a.hand.extend([big, mid, small])
    assert loop._discard_choice("A", a, list(a.hand)) is small


def test_discard_baseline_takes_a_card_that_wants_to_be_discarded_first():
    loop, a, _b, big, small, _mid = _hand_loop()
    chompers = CARD_REGISTRY["Flame Chompers"].instantiate()
    a.hand.extend([big, chompers, small])
    assert loop._discard_choice("A", a, list(a.hand)) is chompers


def test_choosing_an_opponents_discard_takes_their_costliest():
    loop, _a, b, big, small, mid = _hand_loop()
    b.hand.extend([small, big, mid])
    assert loop._discard_choice("A", b, list(b.hand)) is big


def test_discard_card_effect_asks_the_discarding_player():
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    loop, a, b, big, small, mid = _hand_loop()
    a.hand.extend([big, mid, small])
    seen = []

    def chooser(loop_, kind, side, options, default, source):
        seen.append((kind, side, options[default].name))
        return None
    loop.chooser = chooser
    REGISTRY["discard_card"](EffectContext(loop, None, a, b, loop.gs.battlefields[0], {}),
                             {"effect": "discard_card", "count": 1})
    assert seen == [("discard", "A", "Small")]
    assert [c.name for c in a.trash] == ["Small"]


def test_insightful_investigator_chooses_the_discard_from_their_hand():
    from riftbound.core.effects import REGISTRY
    from riftbound.core.loop import EffectContext
    loop, a, b, big, small, mid = _hand_loop()
    from riftbound.core.cards import SpellCard
    b.hand.extend([small, big, mid])
    b.deck.cards.append(SpellCard(name="Drawn"))
    loop.gs.add_xp("A", 2)
    loop.chooser = _picks("Mid")
    REGISTRY["force_discard_redraw"](EffectContext(loop, None, a, b, loop.gs.battlefields[0], {}),
                                     {"effect": "force_discard_redraw", "xp": 2})
    assert [c.name for c in b.trash] == ["Mid"]


# --- "you may" additional costs ------------------------------------------------

def test_kicker_is_not_paid_when_what_it_unlocks_has_no_target():
    """Masa Crashing Thunder: 'You may pay [order] as an additional cost ... if
    you paid the additional cost, STUN an enemy unit at a battlefield.' No enemy
    at a battlefield: the [order] stays in the pool."""
    from tests.test_corpus_cards import _setup
    from riftbound.core.enums import Domain
    loop, a, _b = _setup()
    masa = CARD_REGISTRY["Masa Crashing Thunder"].instantiate()
    before = a.power_pool.get(Domain.ORDER, 0)
    assert loop._kicker_worth(masa, a) is False
    assert loop._try_pay_additional_costs(masa, a) is False
    assert a.power_pool.get(Domain.ORDER, 0) == before


def test_kicker_is_paid_when_what_it_unlocks_has_a_target():
    from tests.test_corpus_cards import _setup, _unit
    from riftbound.core.enums import Domain
    loop, a, b = _setup()
    loop.gs.battlefields[1].units_B.append(_unit("Foe", 3))
    masa = CARD_REGISTRY["Masa Crashing Thunder"].instantiate()
    before = a.power_pool.get(Domain.ORDER, 0)
    assert loop._kicker_worth(masa, a) is True
    assert loop._try_pay_additional_costs(masa, a) is True
    assert a.power_pool.get(Domain.ORDER, 0) == before - 1


def test_kicker_is_still_the_players_choice():
    from tests.test_corpus_cards import _setup
    loop, a, _b = _setup()
    masa = CARD_REGISTRY["Masa Crashing Thunder"].instantiate()
    seen = []

    def chooser(loop_, kind, side, options, default, source):
        seen.append((kind, options[default]))
        return options.index(True)
    loop.chooser = chooser
    assert loop._try_pay_additional_costs(masa, a) is True
    assert seen == [("optional:additional_cost", False)]


# --- the unit an Equipment goes on --------------------------------------------

def test_equip_baseline_is_the_weakest_ready_non_token_unit():
    from riftbound.core.loop import GameLoop
    from tests.test_corpus_cards import _unit
    big, small, tiny_token, stunned = _unit("Big", 5), _unit("Small", 2), _unit("Recruit", 1), _unit("Dazed", 1)
    tiny_token.is_token = True
    stunned.stunned = True
    assert GameLoop._equip_baseline([big, tiny_token, stunned, small]) is small
    assert GameLoop._equip_baseline([big, tiny_token]) is big
    assert GameLoop._equip_baseline([tiny_token]) is tiny_token


def test_equip_ability_attaches_to_the_baseline_unit():
    from tests.test_corpus_cards import _setup, _unit
    loop, a, _b = _setup()
    big, small = _unit("Big", 5), _unit("Small", 2)
    loop.gs.battlefields[0].units_A.append(big)
    a.base_units.append(small)
    sword = CARD_REGISTRY["Long Sword"].instantiate()
    a.base_gear.append(sword)
    entries = loop.activatable_abilities("A")
    idx = next(i for i, e in enumerate(entries) if e["type"] == "equip" and e["gear"] is sword)
    seen = []

    def chooser(loop_, kind, side, options, default, source):
        if kind == "equip":
            seen.append(options[default].card.name)
        return None
    loop.chooser = chooser
    loop._apply_activated_ability(a, loop.gs.B, idx)
    assert seen == ["Small"]
    assert sword in small.gear
