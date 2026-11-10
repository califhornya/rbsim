"""BACKLOG G2, Unleashed approximations. Iascylla's move waits for the start of
the next Main Phase, to the battlefield she held (§359.3.f.3.a); Undying
Loyalty costs [2] less for a Bird, Cat, Dog or Poro, chosen as it's paid;
Hextech Gauntlets' Equip costs less by the chosen unit's Might (WEAPONMASTER
too, §821.1.c.2); Dancing Grenade's replay is a new play on the chain, answered
before it resolves (§420.3); Crescent Guardian's [chaos] is offered only after
a spell; Death from Below comes back right after it resolves, not later."""

from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _play_spell, _setup, _unit


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def _power(p):
    return sum(p.power_pool.values())


def _names_in(units):
    return [u.card.name for u in units]


# -- Iascylla ---------------------------------------------------------------

def _iascylla_holds(loop, a, b, chooser=None):
    """Iascylla holds battlefield 0 at the start of A's turn; returns the
    enemy in B's base and where it was when A drew (before the Main Phase)."""
    bf = loop.gs.battlefields[0]
    iascylla = _unit("Iascylla")
    bf.add_unit("A", iascylla)
    bf.control()
    enemy = _unit("Enemy", 1)
    b.base_units.append(enemy)
    a.deck.cards = [UnitCard(name="Top", might=1)]
    seen = {}
    draw = loop._phase_draw

    def phase_draw(p):
        seen["at_draw"] = enemy in b.base_units
        seen["delayed"] = len(loop.gs.delayed_main)
        if chooser == "leave":
            bf.remove_unit("A", iascylla)            # she leaves before the Main Phase
            a.base_units.append(iascylla)
        draw(p)
    loop._phase_draw = phase_draw
    if chooser == "decline":
        loop.chooser = lambda _l, kind, side, options, default, source: (
            options.index(False) if kind == "optional:move_unit" else None)
    loop._begin_turn()
    return bf, enemy, seen


def test_iascylla_moves_an_enemy_at_the_start_of_the_main_phase():
    """'When I hold, at the start of your next Main Phase, you may move an enemy
    unit to this battlefield.'"""
    loop, a, b = _setup()
    bf, enemy, seen = _iascylla_holds(loop, a, b)
    assert seen == {"at_draw": True, "delayed": 1}          # not at once
    assert enemy not in b.base_units and loop.gs.delayed_main == []
    assert enemy.card in b.trash                              # moved in, lost the fight


def test_iascylla_uses_the_battlefield_she_held_even_after_leaving_it():
    loop, a, b = _setup()
    bf, enemy, seen = _iascylla_holds(loop, a, b, chooser="leave")
    assert enemy in bf.units_B and "Iascylla" in _names_in(a.base_units)


def test_iascylla_may_decline():
    loop, a, b = _setup()
    bf, enemy, seen = _iascylla_holds(loop, a, b, chooser="decline")
    assert enemy in b.base_units and loop.gs.delayed_main == []


def test_iascylla_waits_for_her_controllers_main_phase():
    loop, a, b = _setup()
    loop.gs.delayed_main.append(("B", _card("Iascylla"), 0,
                                 {"effect": "move_unit", "target": "enemy_unit", "destination": "here"}))
    a.base_units.append(_unit("Mine", 1))
    loop._resolve_delayed_main("A")
    assert len(loop.gs.delayed_main) == 1 and len(a.base_units) == 1
    loop._resolve_delayed_main("B")
    assert loop.gs.delayed_main == [] and _names_in(loop.gs.battlefields[0].units_A) == ["Mine"]


# -- Undying Loyalty ---------------------------------------------------------

def _loyalty_chooser(take_discount, pick):
    def chooser(_loop, kind, side, options, default, source):
        if kind == "cost_extras":
            return 0 if take_discount else len(options) - 1
        if kind == "card:play_from_trash":
            return next(i for i, o in enumerate(options) if o.name == pick)
        return None
    return chooser


def test_undying_loyalty_costs_two_less_for_a_poro():
    """'This costs [2] less if you choose a Bird, Cat, Dog, or Poro. Play a unit
    with cost no more than [2] and no more than [rune] from your trash, ignoring
    its cost.'"""
    loop, a, b = _setup()
    a.trash = [_card("Pouty Poro")]
    a.energy = 0                                  # only playable with the discount
    _play_spell(loop, a, "Undying Loyalty")
    assert _names_in(a.base_units) == ["Pouty Poro"] and a.energy == 0


def test_undying_loyalty_costs_full_for_another_unit():
    loop, a, b = _setup()
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=2)]
    _play_spell(loop, a, "Undying Loyalty")
    assert _names_in(a.base_units) == ["Grunt"] and a.energy == 18
    loop, a, b = _setup()
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=2)]
    a.energy = 1
    a.hand = [_card("Undying Loyalty")]
    assert not loop._can_pay_card(a, a.hand[0], *loop._effective_cost(a.hand[0], a))


def test_undying_loyalty_discount_chooses_the_pet_as_it_is_paid():
    loop, a, b = _setup()
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=2), _card("Pouty Poro")]
    _play_spell(loop, a, "Undying Loyalty")                     # baseline: the discount
    assert _names_in(a.base_units) == ["Pouty Poro"] and a.energy == 20
    loop, a, b = _setup()
    a.trash = [UnitCard(name="Grunt", might=2, cost_energy=2), _card("Pouty Poro")]
    loop.chooser = _loyalty_chooser(False, "Grunt")
    _play_spell(loop, a, "Undying Loyalty")
    assert _names_in(a.base_units) == ["Grunt"] and a.energy == 18


def test_undying_loyalty_ignores_a_pet_too_expensive_to_play():
    loop, a, b = _setup()
    a.trash = [_card("Pakaa Cub")]                              # a Cat costing [3]
    a.hand = [_card("Undying Loyalty")]
    assert loop._effective_cost(a.hand[0], a) == (2, 1)


# -- Hextech Gauntlets --------------------------------------------------------

def _gauntlets(loop, a, *mights):
    a.base_gear.append(_card("Hextech Gauntlets"))
    units = [_unit(f"U{m}", m) for m in mights]
    a.base_units.extend(units)
    a.power_pool = {Domain.FURY: 1}
    return units


def _equip_entry(loop, side="A"):
    return next(i for i, e in enumerate(loop.activatable_abilities(side)) if e["type"] == "equip")


def test_hextech_gauntlets_equip_costs_less_by_the_chosen_units_might():
    """'EQUIP [3] [rune]. This ability's Energy cost is reduced by the Might of
    the unit you choose.'"""
    loop, a, b = _setup()
    small, big = _gauntlets(loop, a, 2, 4)
    a.energy = 1
    loop.chooser = lambda _l, kind, side, options, default, source: (
        options.index(small) if kind == "equip" else None)
    loop._apply_activated_ability(a, b, _equip_entry(loop))
    assert [g.name for g in small.gear] == ["Hextech Gauntlets"]
    assert a.energy == 0 and _power(a) == 0


def test_hextech_gauntlets_offers_only_the_units_it_can_pay_for():
    loop, a, b = _setup()
    small, big = _gauntlets(loop, a, 2, 4)
    a.energy = 0
    offered = []
    loop.chooser = lambda _l, kind, side, options, default, source: (
        offered.append(list(options)) if kind == "equip" else None)
    loop._apply_activated_ability(a, b, _equip_entry(loop))
    assert offered == [[big]] and big.gear and a.energy == 0
    loop, a, b = _setup()
    _gauntlets(loop, a, 1)
    a.energy = 1
    entry = loop.activatable_abilities("A")[_equip_entry(loop)]
    assert not loop._ability_usable(a, entry)


def test_weaponmaster_counts_its_own_might_for_hextech_gauntlets():
    """§821.1.c.2: the cost as though the Equip chose the WEAPONMASTER unit."""
    loop, a, b = _setup()
    a.base_gear.append(_card("Hextech Gauntlets"))
    a.power_pool = {}
    a.energy = 3
    a.hand = [_card("Sentinel Adept")]                          # 3 Might, [3]
    loop._apply_action(a, ("UNIT", 0, 0))
    adept = next(u for u in a.base_units if u.card.name == "Sentinel Adept")
    assert [g.name for g in adept.gear] == ["Hextech Gauntlets"] and a.energy == 0


# -- Dancing Grenade ----------------------------------------------------------

class _Watcher:
    """A's agent: passes, noting the chain each time it may respond."""
    def __init__(self):
        self.seen = []

    def decide_reaction(self, opponent, chain):
        self.seen.append([it.card.name for it in chain])
        return ("PASS",)


def _grenade_chooser(replays):
    """`replays`: whether each "play this spell again" in turn says yes."""
    answers = list(replays)

    def chooser(_loop, kind, side, options, default, source):
        if kind == "optional:replay":
            return options.index(answers.pop(0) if answers else False)
        return None
    return chooser


def test_dancing_grenade_replay_goes_on_the_chain_and_can_be_answered():
    """'Deal 2 to a unit. Its controller may play this spell again for [rune]. If
    they do, this deals 1 additional Bonus Damage for each time this spell has
    dealt damage this turn.'"""
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 9), _unit("Theirs", 9)
    a.base_units.append(mine)
    b.base_units.append(theirs)
    a.agent = _Watcher()
    loop.chooser = _grenade_chooser([True, False])               # B throws it back
    before = _power(b)
    _play_spell(loop, a, "Dancing Grenade")
    assert theirs.damage == 2 and mine.damage == 3
    assert a.agent.seen == [["Dancing Grenade"], ["Dancing Grenade"]]   # A could answer both
    assert _power(b) == before - 1
    assert [c.name for c in a.trash] == ["Dancing Grenade"] and not b.trash   # its owner's


def test_dancing_grenade_adds_one_per_hit_this_turn():
    loop, a, b = _setup()
    mine, theirs = _unit("Mine", 9), _unit("Theirs", 9)
    a.base_units.append(mine)
    b.base_units.append(theirs)
    loop.chooser = _grenade_chooser([True, True, False])
    _play_spell(loop, a, "Dancing Grenade")
    assert theirs.damage == 2 + 4 and mine.damage == 3
    assert not loop.gs.chain and [c.name for c in a.trash] == ["Dancing Grenade"]


def test_dancing_grenade_played_anew_gets_no_bonus():
    loop, a, b = _setup()
    theirs = _unit("Theirs", 9)
    b.base_units.append(theirs)
    loop.chooser = _grenade_chooser([])
    _play_spell(loop, a, "Dancing Grenade")
    grenade = a.trash.pop()
    a.hand.append(grenade)
    loop._apply_action(a, ("SPELL", len(a.hand) - 1, 0))
    assert theirs.damage == 4                                  # "If they do": a replay only


# -- Crescent Guardian ---------------------------------------------------------

def test_crescent_guardian_doesnt_take_chaos_without_a_spell():
    """'If you've played a spell this turn, you may pay [chaos] as an additional
    cost to play me. If you do, I enter ready.'"""
    loop, a, b = _setup()
    a.hand = [_card("Crescent Guardian")]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert not a.base_units[-1].ready and a.power_pool[Domain.CHAOS] == 5
    loop.gs.spells_played_this_turn["A"] = 1
    a.hand = [_card("Crescent Guardian")]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert a.base_units[-1].ready and a.power_pool[Domain.CHAOS] == 4


# -- Death from Below -----------------------------------------------------------

def _targets(*names):
    """Each spell's target choice picks the next of `names`; "play this again"
    says `replay`."""
    queue = list(names)

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target") and queue:
            name = queue.pop(0)
            return next(i for i, o in enumerate(options) if o.card.name == name)
        return None
    return chooser


def test_death_from_below_comes_back_right_after_a_small_kill():
    """'Kill a unit at a battlefield. Then, if it had 3 [might] or less, you may
    play this from your trash for [rune].'"""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Small", 2))
    loop.gs.battlefields[1].add_unit("B", _unit("Next", 4))
    loop.chooser = _targets("Small", "Next")
    before = _power(a)
    _play_spell(loop, a, "Death from Below")
    assert sorted(c.name for c in b.trash) == ["Next", "Small"]
    assert [c.name for c in a.trash] == ["Death from Below"]     # 4 Might: no third time
    assert a.energy == 16 and _power(a) == before - 2


def test_death_from_below_cant_be_played_later():
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Small", 2))
    loop.gs.battlefields[1].add_unit("B", _unit("Next", 4))
    asked = []

    def chooser(_loop, kind, side, options, default, source):
        if kind == "optional:replay":
            asked.append(side)
            return options.index(False)
        return None
    loop.chooser = chooser
    _play_spell(loop, a, "Death from Below")
    assert asked == ["A"] and [c.name for c in a.trash] == ["Death from Below"]
    assert not [e for e in loop.activatable_abilities("A") if e["type"] == "trash_play"]


def test_death_from_below_isnt_offered_after_a_big_kill():
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Big", 4))
    asked = []
    loop.chooser = lambda _l, kind, side, options, default, source: (
        asked.append(kind) if kind == "optional:replay" else None)
    _play_spell(loop, a, "Death from Below")
    assert asked == [] and [c.name for c in a.trash] == ["Death from Below"]
