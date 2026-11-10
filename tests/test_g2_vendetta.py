"""BACKLOG G2, Vendetta approximations. Nasus Curator of the Sands also answers
activated abilities with a base Energy cost of [7]+ (§206.1); Tail-Cloaked
Matriarch's printed text says "a unit in your trash" (the data lacked it);
Decree of Focus reads "an enemy Fury spell" only (no abilities), and a domain
check sees every domain of a card ("Fury Chaos" Tibbers is a Chaos unit);
Bottled Constellation waits for the Main Phase and may kill any friendly gear;
Sanction empowers or disempowers any unit, and "at end of turn" sets the
status (not a toggle), an empower firing "When I become EMPOWERED"."""

from __future__ import annotations

from riftbound.core.cards import GearCard, UnitCard
from riftbound.core.effects import _card_domains
from riftbound.core.enums import Domain
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _always, _cast_now, _setup, _unit
from test_corpus_vendetta import _ability, _attack_at, _runes


def _card(name):
    return CARD_REGISTRY[name].instantiate()


# -- Nasus Curator of the Sands ---------------------------------------------

def _nasus(loop, a, answer=True):
    loop.chooser = _always(answer)
    loop.gs.legend_unit_A = _unit("Nasus Curator of the Sands")
    _runes(a, 3)
    for r in a.rune_pool[Domain.FURY]:
        r.ready = False
    return loop.gs.legend_unit_A


def test_nasus_curator_answers_an_ability_costing_seven():
    """'When you play a unit, gear, or activated ability with Energy cost [7] or
    more, you may exhaust me to ready up to 2 runes.' (Steel Paws: EMPOWER [7])"""
    loop, a, b = _setup()
    nasus = _nasus(loop, a)
    paws = _unit("Steel Paws")
    a.base_units.append(paws)
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert paws.empowered and not nasus.ready
    assert a.energy == 20 - 7 + 2                 # a readied rune = its Energy back


def test_nasus_curator_reads_the_base_cost_not_the_paid_one():
    """§206.1: Frostcoat Mother's EMPOWER [12] costs [1] less per rune (here
    [9]) and still counts as [12]; Baccai Sandspinner's EMPOWER [5] never does."""
    loop, a, b = _setup()
    nasus = _nasus(loop, a)
    a.base_units.append(_unit("Frostcoat Mother"))
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert not nasus.ready and a.energy == 20 - 9 + 2
    loop, a, b = _setup()
    nasus = _nasus(loop, a)
    a.base_units.append(_unit("Baccai Sandspinner"))           # [5], [2] with 3 runes
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert nasus.ready and a.energy == 18


def test_nasus_curator_may_decline():
    loop, a, b = _setup()
    nasus = _nasus(loop, a, answer=False)
    a.base_units.append(_unit("Steel Paws"))
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert nasus.ready and a.energy == 13


# -- Tail-Cloaked Matriarch -------------------------------------------------

def test_tail_cloaked_matriarch_text_names_the_trash_and_power_limit():
    """'... you may choose a unit in your trash with Energy cost no more than [3]
    and Power cost no more than [rune]. Play it to your base, ignoring its
    cost.'"""
    assert "a unit in your trash" in CARD_REGISTRY["Tail-Cloaked Matriarch"].raw["effect"]
    loop, a, b = _setup()
    loop.chooser = _always(True)
    a.base_units.append(_unit("Tail-Cloaked Matriarch"))
    two = UnitCard(name="Two", might=3, cost_energy=2, cost_power=2, cost_power_domain=Domain.CHAOS)
    one = UnitCard(name="One", might=2, cost_energy=3, cost_power=1, cost_power_domain=Domain.CHAOS)
    a.trash.extend([two, one])
    loop._apply_activated_ability(a, b, _ability(loop, "A", "empower_self"))
    assert any(u.card is one for u in a.base_units) and two in a.trash


# -- Decree of Focus, and domains -------------------------------------------

def test_every_domain_of_a_card_counts():
    assert _card_domains(_card("Tibbers")) == {"FURY", "CHAOS"}
    assert _card_domains(UnitCard(name="Plain", might=1, domain=Domain.BODY)) == {"BODY"}


def test_decree_of_unity_kills_a_chaos_unit_whose_first_domain_is_fury():
    """'Kill an enemy Chaos ([chaos]) unit or gear.' Tibbers is Fury and Chaos."""
    loop, a, b = _setup()
    tibbers = _unit("Tibbers")
    loop.gs.battlefields[0].add_unit("B", tibbers)
    _cast_now(loop, a, "Decree of Unity")
    assert tibbers not in loop.gs.battlefields[0].units_B


def test_decree_of_focus_sees_a_fury_unit_with_two_domains():
    """'Choose a friendly unit that's in combat with an enemy Fury unit ...'"""
    loop, a, b = _setup()
    fighter = _unit("Fighter", 2)
    loop.gs.battlefields[0].add_unit("A", fighter)
    loop.gs.battlefields[0].add_unit("B", _unit("Tibbers"))
    _attack_at(loop)
    _cast_now(loop, a, "Decree of Focus")
    assert fighter.might == 6


# -- Bottled Constellation --------------------------------------------------

def test_bottled_constellation_waits_for_the_main_phase():
    """'At the start of your Main Phase, you may kill 3 other friendly units
    and/or gear to score 1 point.'"""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    bottle = _card("Bottled Constellation")
    a.base_gear.append(bottle)
    a.base_units.extend([_unit("U1", 1), _unit("U2", 1), _unit("U3", 1)])
    a.deck.cards = [UnitCard(name="Top", might=1)]
    seen = {}
    draw = loop._phase_draw

    def phase_draw(p):
        seen["at_draw"] = loop.gs.points_A
        draw(p)
    loop._phase_draw = phase_draw
    loop._begin_turn()
    assert seen == {"at_draw": 0} and loop.gs.points_A == 1
    assert a.base_gear == [bottle] and not a.base_units


def test_bottled_constellation_may_kill_an_attached_gear():
    loop, a, b = _setup()
    loop.chooser = _always(True)
    bottle = _card("Bottled Constellation")
    sword = GearCard(name="Sword", cost_energy=1)
    holder = _unit("Holder", 1)
    holder.gear.append(sword)
    loop.gs.battlefields[0].add_unit("A", holder)
    a.base_gear.extend([bottle, GearCard(name="Shield", cost_energy=2)])
    loop._fire_turn_trigger("on_start_of_main", "A")
    assert loop.gs.points_A == 1 and a.base_gear == [bottle]
    assert sword in a.trash and holder.card in a.trash


def test_bottled_constellation_not_at_the_start_of_turn():
    loop, a, b = _setup()
    loop.chooser = _always(True)
    a.base_gear.append(_card("Bottled Constellation"))
    a.base_units.extend([_unit("U1", 1), _unit("U2", 1), _unit("U3", 1)])
    loop._fire_turn_trigger("on_start_of_turn", "A")
    assert loop.gs.points_A == 0 and len(a.base_units) == 3


# -- Sanction ---------------------------------------------------------------

def _sanction(loop, mode, name):
    """Sanction with mode `mode` (0: empower, 1: disempower) aimed at `name`."""
    def chooser(_loop, kind, side, options, default, source):
        if kind == "mode":
            return options.index(mode)
        if kind.startswith("target"):
            return next((i for i, o in enumerate(options) if o.card.name == name), None)
        return None
    loop.chooser = chooser
    _cast_now(loop, loop.gs.A, "Sanction")


def test_sanction_may_empower_an_enemy_unit_until_end_of_turn():
    """'Choose one - Empower a unit. Disempower it at end of turn. / Disempower
    a unit that's EMPOWERED. Empower it at end of turn.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Mine", 2))
    enemy = _unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _sanction(loop, 0, "Enemy")
    assert enemy.empowered
    loop._resolve_delayed_effects()
    assert not enemy.empowered


def test_sanction_may_disempower_a_friendly_unit_and_empower_it_at_end():
    """Re-empowered at end of turn, Tail-Cloaked Matriarch's 'When I become
    EMPOWERED' fires: she plays a unit from the trash."""
    loop, a, b = _setup()
    matriarch = _unit("Tail-Cloaked Matriarch", empowered=True)
    a.base_units.append(matriarch)
    loop.gs.battlefields[0].add_unit("B", _unit("Enemy", 2, empowered=True))
    small = UnitCard(name="Small", might=2, cost_energy=2)
    a.trash.append(small)
    _sanction(loop, 1, "Tail-Cloaked Matriarch")
    assert not matriarch.empowered
    loop.chooser = _always(True)
    loop._resolve_delayed_effects()
    assert matriarch.empowered and any(u.card is small for u in a.base_units)


def test_sanction_end_of_turn_sets_the_status_not_a_toggle():
    """Empowered by Sanction, then disempowered by something else: at end of
    turn 'Disempower it' leaves it disempowered (a toggle re-empowered it)."""
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    a.base_units.append(mine)
    _sanction(loop, 0, "Mine")
    loop._disempower(mine.card)
    loop._resolve_delayed_effects()
    assert not mine.empowered


def test_sanction_baseline_disempowers_an_enemy():
    loop, a, b = _setup()
    mine = _unit("Mine", 2, empowered=True)
    enemy = _unit("Enemy", 2, empowered=True)
    a.base_units.append(mine)
    loop.gs.battlefields[0].add_unit("B", enemy)

    def chooser(_loop, kind, side, options, default, source):
        return options.index(1) if kind == "mode" else None
    loop.chooser = chooser
    _cast_now(loop, a, "Sanction")
    assert mine.empowered and not enemy.empowered
