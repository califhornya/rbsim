"""Atakhan's additional cost (BACKLOG E): "You may kill a friendly unit as an
additional cost to play me. If you do, I cost [1] less for each Energy it costs
and [order] less for each Power it costs." Every payment of him (_can_pay_card /
_pay_card) may take it (GameLoop._kill_discounts, _kill_discount); baseline:
only when he can't be paid without it. FAQ rulings with Mordekaiser, Iron
Revenant: the unit Atakhan kills is killed after his Energy and Power are paid,
so it isn't in the trash for Mordekaiser (§357.1-2); Meticulous Restorationist's
"play me for [order]" is an alternate cost of a unit, so Mordekaiser's Power
may pay it."""

from __future__ import annotations

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.enums import Domain
from riftbound.core.legality import legal_actions
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _always, _setup, _unit


def _atakhan(p):
    card = CARD_REGISTRY["Atakhan"].instantiate()      # [10] [order][order][order]
    p.hand.append(card)
    return card


def _plays(loop, p):
    return [a for a in legal_actions(loop, player=p.name) if a.kind == "UNIT"]


def _play(loop, p, card):
    loop._apply_action(p, ("UNIT", next(i for i, c in enumerate(p.hand) if c is card), 0))


def _victim(name="Victim", energy=4, power=0, might=2):
    return UnitInPlay(card=UnitCard(name=name, might=might, cost_energy=energy, cost_power=power,
                                    cost_power_domain=Domain.FURY if power else None), ready=True)


def _only_order(p, n):
    p.power_pool = {Domain.ORDER: n}


def _mordekaiser(loop, side="A"):
    unit = UnitInPlay(card=CARD_REGISTRY["Mordekaiser Iron Revenant"].instantiate(), ready=True)
    setattr(loop.gs, f"legend_unit_{side}", unit)
    return unit


def _add_with_mordekaiser(loop, p):
    entries = [i for i, e in enumerate(loop.activatable_abilities(p.name))
               if e["type"] == "ability" and e["eff"].effect == "add_earmarked_power"
               and loop._ability_usable(p, e)]
    assert entries
    loop._apply_action(p, ("ABILITY", "ACTIVATED", entries[0], None))


def _in_base(p, card):
    return any(u.card is card for u in p.base_units)


# --- Atakhan ---------------------------------------------------------------

def test_short_on_energy_he_kills_a_friendly_unit_for_its_cost():
    loop, a, b = _setup()
    victim = _victim(energy=4, power=1)
    a.base_units.append(victim)
    a.energy = 6                                        # [10] - [4]
    _only_order(a, 2)                                   # [order]x3 - 1
    atakhan = _atakhan(a)
    assert _plays(loop, a)
    _play(loop, a, atakhan)
    assert _in_base(a, atakhan) and atakhan not in a.hand
    assert victim not in a.base_units and victim.card in a.trash
    assert a.energy == 0 and a.power_pool.get(Domain.ORDER, 0) == 0


def test_a_token_copy_counts_its_copied_cost():
    """CORE_RULES §206: a Reflection that is a copy of Noxus Hopeful: [4] less."""
    loop, a, b = _setup()
    copy = CARD_REGISTRY["Noxus Hopeful"].instantiate()
    copy.is_token = True
    token = UnitInPlay(card=copy, ready=True, is_token=True)
    a.base_units.append(token)
    a.energy = 6
    atakhan = _atakhan(a)
    _play(loop, a, atakhan)
    assert _in_base(a, atakhan) and a.energy == 0
    assert token not in a.base_units and copy not in a.trash     # a token ceases to exist


def test_power_less_for_each_power_the_unit_costs():
    loop, a, b = _setup()
    victim = _victim(energy=0, power=3)                 # [fury]x3: still [order] less each
    a.base_units.append(victim)
    a.energy = 10
    _only_order(a, 0)
    atakhan = _atakhan(a)
    _play(loop, a, atakhan)
    assert _in_base(a, atakhan) and a.energy == 0 and victim.card in a.trash


def test_without_a_friendly_unit_he_costs_full():
    loop, a, b = _setup()
    a.energy = 6
    _atakhan(a)
    assert not _plays(loop, a)


def test_a_unit_too_cheap_to_make_him_affordable_isnt_enough():
    loop, a, b = _setup()
    a.base_units.append(_victim(energy=3))
    a.energy = 6
    _atakhan(a)
    assert not _plays(loop, a)


def test_baseline_pays_in_full_when_it_can():
    loop, a, b = _setup()
    victim = _victim()
    a.base_units.append(victim)
    atakhan = _atakhan(a)
    _play(loop, a, atakhan)
    assert _in_base(a, atakhan) and victim in a.base_units
    assert a.energy == 10 and a.power_pool[Domain.ORDER] == 2


def test_the_player_may_kill_even_when_he_could_pay():
    loop, a, b = _setup()
    victim = _victim(energy=4)
    a.base_units.append(victim)
    loop.chooser = _always(True)
    atakhan = _atakhan(a)
    _play(loop, a, atakhan)
    assert _in_base(a, atakhan) and victim.card in a.trash and a.energy == 14


def test_only_units_that_make_him_affordable_are_offered_and_the_player_picks():
    loop, a, b = _setup()
    small = _victim("Small", energy=3, might=1)
    big = _victim("Big", energy=5, might=6)
    mid = _victim("Mid", energy=4, might=3)
    a.base_units.extend([small, big, mid])
    a.energy = 6
    offered = []

    def chooser(_loop, kind, side, options, default, source):
        if kind == "cost_unit:kill":
            offered.extend(o.card.name for o in options)
            assert options[default] is mid               # baseline: the weakest that pays
            return options.index(big)
        return None
    loop.chooser = chooser
    atakhan = _atakhan(a)
    _play(loop, a, atakhan)
    assert offered == ["Big", "Mid"]
    assert big.card in a.trash and small in a.base_units and mid in a.base_units
    assert a.energy == 1


def test_the_killed_unit_dies_at_its_battlefield():
    loop, a, b = _setup()
    victim = _victim(energy=4)
    loop.gs.battlefields[1].add_unit("A", victim)
    a.energy = 6
    died = []
    orig = loop._route_deaths
    loop._route_deaths = lambda pairs, bf, **kw: (died.append((pairs, bf)), orig(pairs, bf, **kw))[1]
    atakhan = _atakhan(a)
    _play(loop, a, atakhan)
    assert died == [([(victim, "A")], loop.gs.battlefields[1])]
    assert victim not in loop.gs.battlefields[1].units_A and _in_base(a, atakhan)


def test_played_from_another_zone_he_may_kill_too():
    loop, a, b = _setup()
    victim = _victim(energy=4)
    a.base_units.append(victim)
    a.energy = 6
    atakhan = CARD_REGISTRY["Atakhan"].instantiate()
    a.banished.append(atakhan)
    atakhan._banish_play_side, atakhan._banish_play_until = "A", loop.gs.turn
    loop._play_banished(a, atakhan, "A")
    assert _in_base(a, atakhan) and victim.card in a.trash and a.energy == 0


# --- FAQ: Atakhan + Mordekaiser, Iron Revenant ------------------------------

def test_mordekaiser_cant_banish_the_unit_atakhan_kills_to_pay_him():
    """Energy and Power are paid before the kill: the unit isn't in the trash yet."""
    loop, a, b = _setup()
    _mordekaiser(loop)
    a.base_units.append(_victim(energy=4))
    a.energy = 6
    _only_order(a, 2)                                   # one [order] short
    _atakhan(a)
    assert not any(e["type"] == "ability" and loop._ability_usable(a, e)
                   for e in loop.activatable_abilities("A"))
    assert not _plays(loop, a)


def test_mordekaiser_pays_atakhan_with_a_unit_already_in_the_trash():
    loop, a, b = _setup()
    _mordekaiser(loop)
    victim = _victim(energy=4)
    a.base_units.append(victim)
    old = UnitCard(name="Old", might=1)
    a.trash.append(old)
    a.energy = 6
    _only_order(a, 2)
    _add_with_mordekaiser(loop, a)
    assert a.banished == [old] and a.earmarked_power_permanent == 1
    atakhan = _atakhan(a)
    assert _plays(loop, a)
    _play(loop, a, atakhan)
    assert _in_base(a, atakhan) and victim.card in a.trash
    assert a.earmarked_power_permanent == 0 and a.power_pool.get(Domain.ORDER, 0) == 0


# --- FAQ: Meticulous Restorationist + Mordekaiser, Iron Revenant -------------

def _restorationist_setup(earmark):
    loop, a, b = _setup()
    _mordekaiser(loop)
    resto = CARD_REGISTRY["Meticulous Restorationist"].instantiate()
    a.trash.append(resto)
    if earmark:
        a.trash.append(UnitCard(name="Old", might=1))
        _add_with_mordekaiser(loop, a)
    _only_order(a, 0)
    big = UnitCard(name="Big", might=7, cost_energy=7)
    a.hand.append(big)
    a.energy = 7
    return loop, a, resto, big


def test_mordekaisers_power_pays_the_restorationists_order():
    loop, a, resto, big = _restorationist_setup(earmark=True)
    _play(loop, a, big)
    assert _in_base(a, big) and _in_base(a, resto) and resto not in a.trash
    assert a.earmarked_power_permanent == 0


def test_without_it_the_restorationist_stays_in_the_trash():
    loop, a, resto, big = _restorationist_setup(earmark=False)
    _play(loop, a, big)
    assert _in_base(a, big) and resto in a.trash and not _in_base(a, resto)


def test_mordekaisers_power_pays_a_units_play_from_the_trash_cost():
    """Undying Legion: "LEGION: You may play me from your trash for [3] [fury]"."""
    loop, a, b = _setup()
    _mordekaiser(loop)
    legion = CARD_REGISTRY["Undying Legion"].instantiate()
    a.trash.extend([legion, UnitCard(name="Old", might=1)])
    a.power_pool = {}
    a.energy = 3
    loop.gs.played_cards_this_turn["A"] = [UnitCard(name="Earlier")]
    _add_with_mordekaiser(loop, a)
    entry = next(i for i, e in enumerate(loop.activatable_abilities("A"))
                 if e["type"] == "trash_play" and e["card"] is legion)
    assert loop._ability_usable(a, loop.activatable_abilities("A")[entry])
    loop._apply_action(a, ("ABILITY", "ACTIVATED", entry, None))
    assert _in_base(a, legion) and a.energy == 0 and a.earmarked_power_permanent == 0


def test_mordekaisers_power_doesnt_pay_a_spells_play_from_the_trash():
    loop, a, b = _setup()
    _mordekaiser(loop)
    spell = CARD_REGISTRY["Death from Below"].instantiate()
    a.trash.extend([spell, UnitCard(name="Old", might=1)])
    a.power_pool = {}
    _add_with_mordekaiser(loop, a)
    spell._trash_replay = (loop.gs.turn, {"power": 1})
    entries = [e for e in loop.activatable_abilities("A")
               if e["type"] == "trash_play" and e["card"] is spell]
    assert entries and not loop._ability_usable(a, entries[0])
