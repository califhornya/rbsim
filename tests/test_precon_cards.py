"""The precon decks (precon_zed, precon_shen), card by card: each sentence of
the printed text played through the engine (BACKLOG.md section A)."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    a.energy = 20
    for d in Domain:
        a.add_power(d, 5)
    return GameLoop(gs), a, b


def _unit(name, might=None, **kw):
    card = CARD_REGISTRY[name].instantiate() if name in CARD_REGISTRY else UnitCard(name=name, might=might)
    return UnitInPlay(card=card, ready=True, **kw)


def _choose(loop, name, asked=None):
    """The player picks the unit called `name` at any target choice."""
    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target"):
            if asked is not None:
                asked.append([getattr(getattr(o, "card", None), "name", o) for o in options])
            return next((i for i, o in enumerate(options)
                         if getattr(getattr(o, "card", None), "name", None) == name), None)
        return None
    loop.chooser = chooser


def _cast(loop, a, name, lane=0):
    a.hand.append(CARD_REGISTRY[name].instantiate())
    loop._apply_action(a, ("SPELL", len(a.hand) - 1, lane))
    loop._recompute_passives()


def _castable(loop, a, name) -> bool:
    a.hand.append(CARD_REGISTRY[name].instantiate())
    try:
        return any(ga.kind == "SPELL" and a.hand[ga.to_engine()[1]].name == name
                   for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A"))
    finally:
        a.hand.pop()


def _on_board(loop, unit) -> bool:
    return loop._locate_unit(unit) is not None


# -- Lacerate: "Choose a unit. If it's EMPOWERED, disempower it. Then kill it if
# it has 3 [might] or less." -------------------------------------------------------

def test_lacerate_chooses_any_unit_disempowers_then_kills_at_three_or_less():
    loop, a, b = _setup()
    witness = _unit("Mournful Witness", empowered=True)     # EMPOWERED: +2 [might]
    big = _unit("Big", 5)
    a.base_units.append(witness)                             # mine, in base
    loop.gs.battlefields[1].add_unit("B", big)
    loop._recompute_passives()
    assert witness.might == witness.card.might + 2
    asked = []
    _choose(loop, "Mournful Witness", asked)
    _cast(loop, a, "Lacerate")
    assert sorted(asked[0]) == ["Big", "Mournful Witness"]  # both sides, base too
    assert not witness.empowered and not _on_board(loop, witness)
    assert witness.card in a.trash


def test_lacerate_disempowers_but_spares_a_unit_still_above_three():
    loop, a, b = _setup()
    big = _unit("Big", 5)
    loop.gs.battlefields[0].add_unit("B", big)
    _choose(loop, "Big")
    _cast(loop, a, "Lacerate")
    assert _on_board(loop, big)


def test_lacerate_needs_a_unit():
    loop, a, b = _setup()
    assert not _castable(loop, a, "Lacerate")


# -- Pakaa Protector: "When I move, reveal the top card of your Main Deck. If it's
# a unit, draw it. Otherwise, put it in your trash and give me +2 [might] this
# turn." --------------------------------------------------------------------------

def _move_pakaa(top):
    loop, a, b = _setup()
    pakaa = _unit("Pakaa Protector")
    a.base_units.append(pakaa)
    a.deck.cards = [UnitCard(name="Bottom", might=1), top]
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()
    return loop, a, pakaa


def test_pakaa_protector_draws_a_revealed_unit():
    loop, a, pakaa = _move_pakaa(UnitCard(name="Top", might=1))
    assert [c.name for c in a.hand] == ["Top"] and not a.trash
    assert pakaa.might == pakaa.card.might


def test_pakaa_protector_trashes_anything_else_and_gets_two():
    loop, a, pakaa = _move_pakaa(SpellCard(name="Top Spell"))
    assert not a.hand and [c.name for c in a.trash] == ["Top Spell"]
    assert [c.name for c in a.deck.cards] == ["Bottom"]
    assert pakaa.might == pakaa.card.might + 2


# -- Shadow Dash: "Move an enemy unit to a battlefield where you have units. If
# you have exactly two units there, they each get +1 [might] this turn." -------

def test_shadow_dash_moves_an_enemy_where_you_have_two_units_and_they_get_one():
    loop, a, b = _setup()
    mine = [_unit("M1", 2), _unit("M2", 2)]
    for u in mine:
        loop.gs.battlefields[1].add_unit("A", u)
    enemy = _unit("Enemy", 3)
    b.base_units.append(enemy)
    _choose(loop, "Enemy")
    _cast(loop, a, "Shadow Dash", lane=0)
    # Moved in, it fights at once (§462): 3 against 3 + 3, the units with +1.
    assert enemy not in b.base_units and enemy.card in b.trash
    survivors = loop.gs.battlefields[1].units_A
    assert len(survivors) == 1 and survivors[0].might == 3


def test_shadow_dash_gives_nothing_without_exactly_two_units_there():
    loop, a, b = _setup()
    mine = [_unit(f"M{i}", 2) for i in range(3)]
    for u in mine:
        loop.gs.battlefields[1].add_unit("A", u)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    _cast(loop, a, "Shadow Dash", lane=0)
    # Moved in, it fights at once (§462); no +1 with three units there.
    assert not loop.gs.battlefields[0].units_B and not loop.gs.battlefields[1].units_B
    assert [u.might for u in loop.gs.battlefields[1].units_A] == [2, 2]


def test_shadow_dash_needs_a_battlefield_with_your_units():
    loop, a, b = _setup()
    a.base_units.append(_unit("Home", 2))
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 3))
    assert not _castable(loop, a, "Shadow Dash")


# -- Dragon Form: "Choose a unit. Its base Might becomes 5 this turn." ---------

def test_dragon_form_chooses_any_unit_even_in_base():
    loop, a, b = _setup()
    small = _unit("Small", 1)
    a.base_units.append(small)
    _choose(loop, "Small")
    _cast(loop, a, "Dragon Form", lane=0)
    assert small.might == 5


# -- Ki Barrier: "Choose a unit. Prevent the next 7 damage that would be dealt to
# it this turn." -------------------------------------------------------------------

def test_ki_barrier_may_choose_any_unit():
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 3), _unit("Theirs", 3)
    loop.gs.battlefields[0].add_unit("A", mine)
    b.base_units.append(theirs)
    asked = []
    _choose(loop, "Theirs", asked)
    _cast(loop, a, "Ki Barrier")
    assert sorted(asked[0]) == ["Mine", "Theirs"]
    assert theirs.damage_shield == 7 and mine.damage_shield == 0


def _chooser(loop, picks):
    """A chooser answering by kind prefix: picks = {kind prefix: f(options) -> index};
    records (kind, option names) of every choice."""
    seen = []

    def chooser(_loop, kind, side, options, default, source):
        seen.append((kind, [getattr(getattr(o, "card", None), "name", None) or getattr(o, "name", o)
                            for o in options]))
        for prefix, f in picks.items():
            if kind.startswith(prefix):
                return f(_loop, options)
        return None
    loop.chooser = chooser
    return seen


# -- Moves name no place: any location but its own, its base included (§355.4) --

def test_charm_may_move_an_enemy_to_a_battlefield_or_its_base():
    loop, a, b = _setup()
    enemy = _unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    seen = _chooser(loop, {"destination": lambda l, o: next(i for i, x in enumerate(o) if x is l.gs.battlefields[1])})
    _cast(loop, a, "Charm")
    dest = [opts for kind, opts in seen if kind.startswith("destination")][0]
    assert len(dest) == 2 and None in dest                    # its base or the other battlefield
    assert enemy in loop.gs.battlefields[1].units_B


def test_charm_pulls_an_enemy_out_of_its_base():
    loop, a, b = _setup()
    enemy = _unit("Enemy", 2)
    b.base_units.append(enemy)
    assert _castable(loop, a, "Charm")
    _chooser(loop, {"destination": lambda l, o: 0})
    _cast(loop, a, "Charm")
    assert enemy in loop.gs.battlefields[0].units_B


def test_twilight_step_may_send_your_unit_home():
    loop, a, b = _setup()
    mine = _unit("Mine", 3)
    loop.gs.battlefields[0].add_unit("A", mine)
    _chooser(loop, {"destination": lambda l, o: o.index(None)})
    _cast(loop, a, "Twilight Step")
    assert mine in a.base_units


# -- Tokens: "play a token" naming no place goes to base or a battlefield you
# control, the player's choice (§440.2.c, §355.2); "here" is where the card is --

def test_death_mark_plays_its_shadow_clone_where_you_choose():
    loop, a, b = _setup()
    loop.gs.battlefields[1].add_unit("A", _unit("Holder", 2))   # I control battlefield 2
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    seen = _chooser(loop, {"token_location": lambda l, o: 1})
    _cast(loop, a, "Death Mark")
    where = [opts for kind, opts in seen if kind == "token_location"][0]
    assert len(where) == 2                                      # base, battlefield 2
    assert [u.card.name for u in loop.gs.battlefields[1].units_A] == ["Holder", "Shadow Clone"]
    assert len(a.trash) == 3 + 1                                # BURN 3, the spell


def test_a_token_played_here_goes_where_the_card_is():
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 2))
    a.hand = [CARD_REGISTRY["Faithful Manufactor"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0, 0))                   # to battlefield 1, which I control
    names = [u.card.name for u in loop.gs.battlefields[0].units_A]
    assert names.count("Recruit") == 1 and "Faithful Manufactor" in names


# -- Gust Monk: "You may pay [1] as an additional cost to play me. When you play
# me, if you paid the additional cost, banish a card from any trash to give a
# unit ASSAULT 2 this turn." -------------------------------------------------------

def test_gust_monk_banishes_from_any_trash_to_give_assault_two():
    loop, a, b = _setup()
    target = _unit("Target", 2)
    loop.gs.battlefields[0].add_unit("A", target)
    b.trash.append(UnitCard(name="Theirs", might=1))
    a.hand = [CARD_REGISTRY["Gust Monk"].instantiate()]
    energy = a.energy
    _choose(loop, "Target")
    loop._apply_action(a, ("UNIT", 0, 0))
    assert a.energy == energy - 2 - 1                           # its cost and the [1]
    assert [c.name for c in b.banished] == ["Theirs"] and not b.trash
    assert target.keyword_value("ASSAULT") == 2


def test_gust_monk_gives_nothing_with_every_trash_empty():
    loop, a, b = _setup()
    target = _unit("Target", 2)
    loop.gs.battlefields[0].add_unit("A", target)
    a.hand = [CARD_REGISTRY["Gust Monk"].instantiate()]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert target.keyword_value("ASSAULT") == 0


# -- Shadow Order Disciple: "When I move, you may BURN 1 to give me +1 [might]
# this turn." One choice: no burn, no +1. ------------------------------------------

def test_shadow_order_disciple_burns_to_get_one_in_a_single_choice():
    for take in (True, False):
        loop, a, b = _setup()
        sod = _unit("Shadow Order Disciple")
        a.base_units.append(sod)
        a.deck.cards = [UnitCard(name="Top", might=1)]
        seen = _chooser(loop, {"optional:": lambda l, o: o.index(take)})
        loop._apply_action(a, ("MOVE", 0, 2, 0))
        loop._flush_pending_move()
        assert sum(k.startswith("optional:") for k, _ in seen) == 1
        assert (sod.might, len(a.trash)) == ((sod.card.might + 1, 1) if take else (sod.card.might, 0))


# -- Ravenbloom Prefect: "When an opponent plays a gear, you may banish me to
# banish it." Any gear (there was an invented "costs 3 or more"). -------------------

def test_ravenbloom_prefect_answers_any_gear():
    loop, a, b = _setup()
    prefect = _unit("Ravenbloom Prefect")
    b.base_units.append(prefect)
    a.hand = [CARD_REGISTRY["Hand Hammer"].instantiate()]       # costs 1
    loop._apply_action(a, ("GEAR", 0, 0))
    assert prefect not in b.base_units and prefect.card in b.banished
    assert any(c.name == "Hand Hammer" for c in a.banished)


# -- Kinkou Temple: "Units here with TANK have +1 [might]." Both players'. ---------

def test_kinkou_temple_gives_one_to_every_tank_here():
    loop, a, b = _setup()
    temple = CARD_REGISTRY["Kinkou Temple"].instantiate()
    loop.gs.battlefields[0].card = temple
    mine, theirs, plain = _unit("Mine", 2), _unit("Theirs", 2), _unit("Plain", 2)
    for u in (mine, theirs):
        u.turn_keywords.append("TANK")
    loop.gs.battlefields[0].add_unit("A", mine)
    loop.gs.battlefields[0].add_unit("A", plain)
    loop.gs.battlefields[0].add_unit("B", theirs)
    loop._recompute_passives()
    assert (mine.might, theirs.might, plain.might) == (3, 3, 2)


def test_battlefield_passives_reach_the_units_on_it():
    """They were never applied: Trifarian War Camp, Windswept Hillock."""
    loop, a, b = _setup()
    loop.gs.battlefields[0].card = CARD_REGISTRY["Trifarian War Camp"].instantiate()
    loop.gs.battlefields[1].card = CARD_REGISTRY["Windswept Hillock"].instantiate()
    here, there, home = _unit("Here", 2), _unit("There", 2), _unit("Home", 2)
    loop.gs.battlefields[0].add_unit("B", here)
    loop.gs.battlefields[1].add_unit("A", there)
    a.base_units.append(home)
    loop._recompute_passives()
    assert (here.might, there.might, home.might) == (3, 2, 2)
    assert there.has_keyword("GANKING") and not here.has_keyword("GANKING")


# -- The rest of the Zed deck ----------------------------------------------------

def _abilities(loop, side="A"):
    return [ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, side) if ga.kind == "ABILITY"]


def _use(loop, a, name) -> bool:
    for ga in _abilities(loop):
        if ga.label.endswith(f"({name})"):
            loop._apply_action(a, ga.to_engine())
            loop._recompute_passives()
            return True
    return False


def _zed_legend(loop):
    gs = loop.gs
    gs.legend_A = CARD_REGISTRY["Zed Master of Shadows"].instantiate()
    gs.legend_unit_A = UnitInPlay(card=gs.legend_A, ready=True)
    return gs.legend_unit_A


def test_zed_master_of_shadows_empowers_on_banishing_your_card_then_loots():
    """'When you banish a card you own, empower me. ACTION Disempower me,
    [tap]: Discard 1, then draw 1.'"""
    loop, a, b = _setup()
    legend = _zed_legend(loop)
    assert not _use(loop, a, "Zed Master of Shadows")        # needs EMPOWERED
    b.trash.append(UnitCard(name="Theirs", might=1))
    a.trash.append(UnitCard(name="Mine", might=1))
    loop._banish_from_trash(b, b.trash[0])                    # not mine: nothing
    assert not legend.empowered
    loop._banish_from_trash(a, a.trash[0])
    assert legend.empowered
    a.hand = [UnitCard(name="Old", might=1)]
    a.deck.cards = [UnitCard(name="New", might=1)]
    assert _use(loop, a, "Zed Master of Shadows")
    assert not legend.empowered and not legend.ready
    assert [c.name for c in a.hand] == ["New"] and "Old" in [c.name for c in a.trash]


def test_zed_from_the_shadows_discards_for_a_shadow_clone():
    """'You may discard 1 as an additional cost to play me. When you play me, if
    you paid the additional cost, play a 0 [might] Shadow Clone unit token.'"""
    for pay in (True, False):
        loop, a, b = _setup()
        champ = CARD_REGISTRY["Zed From the Shadows"].instantiate()
        a.hand = [champ, UnitCard(name="Spare", might=1)]
        _chooser(loop, {"optional:additional_cost": lambda l, o: o.index(pay)})
        loop._apply_action(a, ("UNIT", 0, 0))
        names = [u.card.name for u in a.base_units]
        assert ("Shadow Clone" in names) == pay and (len(a.hand) == 0) == pay


def test_zed_without_a_sound_conquers_for_a_clone_and_swaps_with_it():
    """'When I conquer, play a 0 [might] Shadow Clone unit token to your base.
    ACTION [1] [Chaos]: Move me and a Shadow Clone you control to each
    other's locations.'"""
    loop, a, b = _setup()
    zed = _unit("Zed Without a Sound")
    a.base_units.append(zed)
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()                                # conquers the open battlefield
    clone = next(u for u in a.base_units if u.card.name == "Shadow Clone")
    zed.ready = True
    energy = a.energy
    assert _use(loop, a, "Zed Without a Sound")
    assert zed in a.base_units and clone in loop.gs.battlefields[0].units_A
    assert a.energy == energy - 1


def test_shadow_assassin_enters_ready_with_its_name_in_your_trash():
    """'I enter ready if you have a card with my name in your trash.'"""
    for in_trash in (True, False):
        loop, a, b = _setup()
        if in_trash:
            a.trash.append(CARD_REGISTRY["Shadow Assassin"].instantiate())
        a.hand = [CARD_REGISTRY["Shadow Assassin"].instantiate()]
        loop._apply_action(a, ("UNIT", 0, 0))
        assert a.base_units[0].ready == in_trash


def test_kinkou_lifeblade_empowered_has_one_more_and_ganking():
    """'EMPOWER [2]. EMPOWERED: I have +1 [might] and GANKING.'"""
    loop, a, b = _setup()
    blade = _unit("Kinkou Lifeblade")
    a.base_units.append(blade)
    energy = a.energy
    assert _use(loop, a, "Kinkou Lifeblade")
    assert a.energy == energy - 2 and blade.empowered
    assert blade.might == blade.card.might + 1 and blade.has_keyword("GANKING")


def test_shadowblade_lurker_costs_two_less_per_copy_in_your_trash():
    """'I cost [2] less for each card with my name in your trash.'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Shadowblade Lurker"].instantiate()
    assert loop._effective_cost(card, a)[0] == 5
    a.trash += [CARD_REGISTRY["Shadowblade Lurker"].instantiate() for _ in range(2)]
    assert loop._effective_cost(card, a)[0] == 1


def test_traveling_merchant_loots_when_it_moves():
    """'When I move, discard 1, then draw 1.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Traveling Merchant"))
    a.hand = [UnitCard(name="Old", might=1)]
    a.deck.cards = [UnitCard(name="New", might=1)]
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()
    assert [c.name for c in a.hand] == ["New"] and [c.name for c in a.trash] == ["Old"]


def test_perfect_execution_readies_and_gives_assault_three_and_flows():
    """'Ready a unit and give it ASSAULT 3 this turn. FLOW [3] [Fury].'"""
    loop, a, b = _setup()
    tired = _unit("Tired", 2)
    tired.ready = False
    a.base_units.append(tired)
    _choose(loop, "Tired")
    _cast(loop, a, "Perfect Execution")
    assert tired.ready and tired.keyword_value("ASSAULT") == 3
    assert loop._flow_cost(a.trash[-1], "A") == (3, 1, Domain.FURY)


def test_death_mark_flows_for_one_and_two_runes():
    """'FLOW [1] [Rune] [Rune].'"""
    loop, a, b = _setup()
    assert loop._flow_cost(CARD_REGISTRY["Death Mark"].instantiate(), "A") == (1, 2, None)


def test_twilight_reveler_readies_another_friendly_unit_when_it_attacks():
    """'When I attack, ready another friendly unit.'"""
    loop, a, b = _setup()
    reveler = _unit("Twilight Reveler")
    home = _unit("Home", 2)
    home.ready = False
    a.base_units += [reveler, home]
    loop.gs.battlefields[0].add_unit("B", _unit("Wall", 9))
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()                                # the combat at battlefield 1
    assert home.ready and not reveler.ready


def _battlefield(loop, i, name):
    loop.gs.battlefields[i].card = CARD_REGISTRY[name].instantiate()


def test_zaun_warrens_loots_when_you_conquer_it():
    """'When you conquer here, discard 1, then draw 1.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Zaun Warrens")
    a.base_units.append(_unit("Mover", 2))
    a.hand = [UnitCard(name="Old", might=1)]
    a.deck.cards = [UnitCard(name="New", might=1)]
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()
    assert [c.name for c in a.hand] == ["New"] and [c.name for c in a.trash] == ["Old"]


def test_shadow_temple_burns_three_when_you_hold_it():
    """'When you hold here, BURN 3.'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Shadow Temple")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 2))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(5)]
    loop._score_holds("A") if hasattr(loop, "_score_holds") else loop._phase_beginning("A")
    assert len(a.trash) == 3


def test_threshold_of_the_gray_gives_attacker_and_defender_one_energy():
    """'When combat starts here, the attacker and defender each ADD [1].'"""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Threshold of the Gray")
    a.base_units.append(_unit("Attacker", 2))
    loop.gs.battlefields[0].add_unit("B", _unit("Defender", 5))
    a.energy, b.energy = 0, 0
    seen = []

    class Agent:
        def __init__(self, p):
            self.p = p

        def decide_showdown_action(self, opponent, bf_idx):
            seen.append((self.p.name, self.p.energy))
            return ("PASS", None, None)
    a.agent, b.agent = Agent(a), Agent(b)
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()
    assert ("A", 1) in seen and ("B", 1) in seen


def test_blade_twirler_burns_only_on_its_first_move_each_turn():
    """'The first time I move each turn, choose a player. They BURN 1.'"""
    loop, a, b = _setup()
    twirler = _unit("Blade Twirler")
    a.base_units.append(twirler)
    b.deck.cards = [UnitCard(name=f"B{i}", might=1) for i in range(3)]
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._flush_pending_move()
    assert len(b.trash) == 1
    twirler.ready = True
    loop._apply_action(a, ("MOVE", 0, 0, 2))                # back to base: a second move
    assert len(b.trash) == 1


def test_punching_poro_empowered_has_one_more():
    """'EMPOWER — Discard 1. EMPOWERED I have +1 [might].'"""
    loop, a, b = _setup()
    poro = _unit("Punching Poro")
    a.base_units.append(poro)
    a.hand = [UnitCard(name="Spare", might=1)]
    assert poro.might == 2
    assert _use(loop, a, "Punching Poro")
    assert poro.empowered and poro.might == 3


def test_shadow_fiend_empowered_has_assault_three_attacking():
    """'EMPOWER [2] [fury]. EMPOWERED I have ASSAULT 3.'"""
    loop, a, b = _setup()
    fiend = _unit("Shadow Fiend")
    a.base_units.append(fiend)
    assert fiend.keyword_value("ASSAULT") == 0
    assert _use(loop, a, "Shadow Fiend")
    assert fiend.keyword_value("ASSAULT") == 3 and fiend.might == 2   # +3 only while attacking


def test_ruthless_strike_hits_only_a_unit_at_a_battlefield():
    """'Deal 3 to a unit at a battlefield.' A unit in a base isn't offered."""
    loop, a, b = _setup()
    home = _unit("Home", 2)
    b.base_units.append(home)
    there = _unit("There", 2)
    loop.gs.battlefields[1].add_unit("B", there)
    asked = []
    _choose(loop, "There", asked)
    _cast(loop, a, "Ruthless Strike", lane=0)
    assert all("Home" not in names for names in asked)
    assert not _on_board(loop, there) and _on_board(loop, home)


def test_morgana_vindictive_ambushes_only_where_you_have_units():
    """'AMBUSH (You may play me as a REACTION to a battlefield where you have
    units.)'"""
    loop, a, b = _setup()
    morgana = CARD_REGISTRY["Morgana Vindictive"].instantiate()
    assert loop._ambush_unit_lanes(morgana, "A") == []
    loop.gs.battlefields[1].add_unit("A", _unit("Mine", 2))
    assert loop._ambush_unit_lanes(morgana, "A") == [1]


# -- The Shen deck ---------------------------------------------------------------

def _fight(loop, bf_idx=0, attacker="A"):
    loop.gs.battlefields[bf_idx].contested_this_turn = True
    loop._phase_combat_and_conquer_single(bf_idx, attacker)


def test_shen_kinkou_reacts_to_a_battlefield_you_control_with_shield_two_and_tank():
    """'REACTION (... including to a battlefield you control.) SHIELD 2 TANK'"""
    loop, a, b = _setup()
    card = CARD_REGISTRY["Shen Kinkou"].instantiate()
    assert loop._ambush_unit_lanes(card, "A") == []
    loop.gs.battlefields[1].add_unit("A", _unit("Mine", 1))
    assert loop._ambush_unit_lanes(card, "A") == [1]
    shen = _unit("Shen Kinkou")
    assert shen.keyword_value("SHIELD") == 2 and shen.has_keyword("TANK")


def test_shen_scourge_of_shadows_draws_holding_with_exactly_one_other_unit():
    """'When I hold, if there is exactly one other unit you control here, draw 1.'"""
    for others, drawn in ((1, 1), (0, 0), (2, 0)):
        loop, a, b = _setup()
        a.deck.cards = [UnitCard(name="Top", might=1)]
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Shen Scourge of Shadows"))
        for i in range(others):
            bf.add_unit("A", _unit(f"Pal{i}", 1))
        loop._fire_scoring_trigger("on_hold", bf, "A")
        assert len(a.hand) == drawn


def test_shen_leader_has_shield_one():
    assert _unit("Shen Leader of the Kinkou Order").keyword_value("SHIELD") == 1


def test_steel_paws_deflect_taxes_an_opponent_choosing_it():
    """'DEFLECT (Opponents must pay [rune] to choose me with a spell or ability.)'"""
    loop, a, b = _setup()
    for d in Domain:
        a.power_pool.pop(d, None)
        a.floating_power.pop(d, None)
    paws = _unit("Steel Paws")
    loop.gs.battlefields[0].add_unit("B", paws)
    _choose(loop, "Steel Paws")
    assert not _castable(loop, a, "Ruthless Strike")       # no [rune] for the tax
    a.add_power(Domain.FURY, 1)
    _cast(loop, a, "Ruthless Strike", lane=0)
    assert not _on_board(loop, paws) and not a.power_pool.get(Domain.FURY)
    decree = CARD_REGISTRY["Decree of Insight"].instantiate()
    assert loop._deflect_tax(paws, "A", decree) == 0        # "Ignore DEFLECT while paying"


def test_keeper_of_law_costs_two_order_less_with_a_two_unit_battlefield():
    """'I cost [2] [order] less if you control a battlefield with exactly two
    units there.' (printed [5] [order])"""
    loop, a, b = _setup()
    keeper = CARD_REGISTRY["Keeper of Law"].instantiate()
    assert tuple(loop._effective_cost(keeper, a)) == (5, 1)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("One", 1))
    bf.add_unit("A", _unit("Two", 1))
    assert tuple(loop._effective_cost(keeper, a)) == (3, 0)
    bf.add_unit("A", _unit("Three", 1))
    assert tuple(loop._effective_cost(keeper, a)) == (5, 1)


def test_soulspinner_ambushes_where_you_have_units():
    loop, a, b = _setup()
    card = CARD_REGISTRY["Soulspinner"].instantiate()
    assert loop._ambush_unit_lanes(card, "A") == []
    loop.gs.battlefields[0].add_unit("A", _unit("Mine", 1))
    assert loop._ambush_unit_lanes(card, "A") == [0]


def test_noxian_emissary_empowered_deathknell_plays_two_recruits():
    """'EMPOWER [1] [Order]. EMPOWERED DEATHKNELL Play two 1 [Might] Recruit unit
    tokens to your base.'"""
    for empower in (True, False):
        loop, a, b = _setup()
        emissary = _unit("Noxian Emissary")
        loop.gs.battlefields[0].add_unit("A", emissary)
        if empower:
            assert _use(loop, a, "Noxian Emissary") and emissary.empowered
        loop.gs.battlefields[0].add_unit("B", _unit("Big", 9))
        _fight(loop, 0, "B")
        recruits = [u for u in a.base_units if u.card.name == "Recruit"]
        assert len(recruits) == (2 if empower else 0)
        assert all(u.might == 1 for u in recruits)


def test_sacred_protector_deals_combat_damage_only_beside_exactly_one_other_unit():
    """'I don't deal combat damage unless I'm at a battlefield with exactly one
    other unit you control.'"""
    for pals, enemy_dies in ((0, False), (1, True)):
        loop, a, b = _setup()
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Sacred Protector"))
        for i in range(pals):
            bf.add_unit("A", _unit(f"Pal{i}", 0))
        enemy = _unit("Enemy", 5)
        bf.add_unit("B", enemy)
        loop._recompute_passives()
        _fight(loop, 0, "A")
        assert (not _on_board(loop, enemy)) == enemy_dies


def test_kennen_keeper_of_balance_pays_two_to_stun_and_grows_beside_a_stunned_enemy():
    """'When you play me or I attack, you may pay [2] to STUN a unit. While
    there's a stunned enemy unit here, I have +2 [might].'"""
    loop, a, b = _setup()
    enemy = _unit("Enemy", 3)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.hand = [CARD_REGISTRY["Kennen Keeper of Balance"].instantiate()]
    _chooser(loop, {"optional:stun_unit": lambda l, o: o.index(True),
                    "target": lambda l, o: next(i for i, u in enumerate(o)
                                                if getattr(u, "card", None) and u.card.name == "Enemy")})
    energy = a.energy
    loop._apply_action(a, ("UNIT", 0, 0))
    kennen = next(u for u in a.base_units if u.card.name == "Kennen Keeper of Balance")
    assert enemy.stunned and energy - a.energy == 3 + 2
    loop._recompute_passives()
    assert kennen.might == 2                                 # in base: not "here"
    a.base_units.remove(kennen)
    loop.gs.battlefields[0].add_unit("A", kennen)
    loop._recompute_passives()
    assert kennen.might == 4


def test_shen_eye_of_twilight_gives_a_friendly_unit_tank():
    """'ACTION [tap]: Give a friendly unit TANK this turn.'"""
    loop, a, b = _setup()
    loop.gs.legend_A = CARD_REGISTRY["Shen Eye of Twilight"].instantiate()
    loop.gs.legend_unit_A = UnitInPlay(card=loop.gs.legend_A, ready=True)
    mine = _unit("Mine", 2)
    a.base_units.append(mine)
    b.base_units.append(_unit("Theirs", 2))
    assert _use(loop, a, "Shen Eye of Twilight")
    assert mine.has_keyword("TANK") and not loop.gs.legend_unit_A.ready


def test_resonating_strike_moves_your_unit_to_a_battlefield_you_control_with_two_more():
    """'Choose a battlefield you control and a unit you control at a different
    location. Move that unit to that battlefield and give it +2 [might] this turn.'"""
    loop, a, b = _setup()
    loop.gs.battlefields[1].add_unit("A", _unit("Holder", 1))
    mover = _unit("Mover", 2)
    a.base_units.append(mover)
    seen = _chooser(loop, {})
    _cast(loop, a, "Resonating Strike", lane=0)
    assert mover in loop.gs.battlefields[1].units_A and mover.might == 4
    dests = [names for kind, names in seen if kind.startswith("destination")]
    assert all(len(d) == 1 for d in dests)                 # only the one you control
    assert CARD_REGISTRY["Resonating Strike"].instantiate().has_keyword("HIDDEN")


def test_twilight_shroud_gives_one_and_shields_the_unit_from_enemy_choices():
    """'Give a friendly unit +1 [might] this turn. It can't be chosen by enemy
    spells and abilities this turn. FLOW 2'"""
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    a.base_units.append(mine)
    _cast(loop, a, "Twilight Shroud")
    assert mine.might == 3
    assert not loop._can_choose(mine, "B") and loop._can_choose(mine, "A")
    flow = CARD_REGISTRY["Twilight Shroud"].instantiate().flow_cost
    assert flow["energy"] == 2 and not flow["power"]


def test_serene_ascetic_empowered_has_deflect_and_shield_three():
    """'EMPOWER [3]. EMPOWERED I have DEFLECT and SHIELD 3.'"""
    loop, a, b = _setup()
    ascetic = _unit("Serene Ascetic")
    a.base_units.append(ascetic)
    assert not ascetic.has_keyword("DEFLECT")
    energy = a.energy
    assert _use(loop, a, "Serene Ascetic")
    assert energy - a.energy == 3
    assert ascetic.keyword_value("DEFLECT") == 1 and ascetic.keyword_value("SHIELD") == 3


def test_mournful_witness_empowers_when_a_combat_it_was_in_ends():
    """'When a combat that I was in ends, empower me. EMPOWERED I have +2.'
    Win, lose by recall, or survive a tie: it was in the combat."""
    loop, a, b = _setup()
    witness = _unit("Mournful Witness")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", witness)
    wall = _unit("Wall", 9)
    wall.stunned = True                                    # both survive: recalled
    bf.add_unit("B", wall)
    _fight(loop, 0, "A")
    loop._recompute_passives()
    assert witness.empowered and witness.might == 4


def test_mournful_witness_dying_in_the_combat_doesnt_empower():
    loop, a, b = _setup()
    witness = _unit("Mournful Witness")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", witness)
    bf.add_unit("B", _unit("Big", 9))
    _fight(loop, 0, "B")
    assert not _on_board(loop, witness)


def test_hand_hammer_equips_for_calm_and_gives_two_beside_exactly_one_other_unit():
    """'EQUIP [calm]. I have +2 [might] while I'm at a battlefield with exactly
    one other unit you control.' (and the Equipment's printed +1)"""
    loop, a, b = _setup()
    hammer = CARD_REGISTRY["Hand Hammer"].instantiate()
    assert loop._equip_cost(hammer)["domain_power"] == {"calm": 1}
    holder = _unit("Holder", 2)
    holder.gear = [hammer]
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", holder)
    loop._recompute_passives()
    assert holder.might == 3
    bf.add_unit("A", _unit("Pal", 1))
    loop._recompute_passives()
    assert holder.might == 5


def test_field_musicians_gives_any_unit_three():
    """'When you play me, give a unit +3 [might] this turn.'"""
    loop, a, b = _setup()
    target = _unit("Target", 2)
    loop.gs.battlefields[1].add_unit("A", target)
    a.hand = [CARD_REGISTRY["Field Musicians"].instantiate()]
    _choose(loop, "Target")
    loop._apply_action(a, ("UNIT", 0, 0))
    assert target.might == 5


def test_loyal_poro_draws_only_if_it_didnt_die_alone():
    """'DEATHKNELL If I didn't die alone, draw 1.'"""
    for pals, drawn in ((0, 0), (1, 1)):
        loop, a, b = _setup()
        a.deck.cards = [UnitCard(name="Top", might=1)]
        bf = loop.gs.battlefields[0]
        bf.add_unit("A", _unit("Loyal Poro"))
        for i in range(pals):
            pal = _unit(f"Pal{i}", 9)
            pal.stunned = True                             # Poro takes the hit
            bf.add_unit("A", pal)
        bf.add_unit("B", _unit("Killer", 3))
        _fight(loop, 0, "B")
        assert not any(u.card.name == "Loyal Poro" for u in bf.units_A)
        assert len(a.hand) == drawn


def test_discipline_is_a_reaction_giving_two_and_drawing():
    """'REACTION. Give a unit +2 [might] this turn. Draw 1.'"""
    from riftbound.core.legality import _reaction_actions
    loop, a, b = _setup()
    a.deck.cards = [UnitCard(name="Top", might=1)]
    target = _unit("Target", 2)
    a.base_units.append(target)
    a.hand = [CARD_REGISTRY["Discipline"].instantiate()]
    assert any(ga.kind == "SPELL" for ga in _reaction_actions(loop, a))
    a.hand = []
    _cast(loop, a, "Discipline")
    assert target.might == 4 and [c.name for c in a.hand] == ["Top"]


def test_grove_of_the_god_willow_draws_when_you_hold_it():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Grove of the God-Willow")
    a.deck.cards = [UnitCard(name="Top", might=1)]
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    assert [c.name for c in a.hand] == ["Top"]
