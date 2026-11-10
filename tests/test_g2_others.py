"""BACKLOG G2, the others. Jhin Meticulous Killer may be played for [mind] once
[4] was spent on a spell this turn; Hunters' Circle's [1] off also applies to
AMBUSH units and champions played there on your turn; "spent [4]" is Energy
only (§163.1: numeric costs are Energy; the printed [4] is the Energy icon);
Forbidding Waste / Master Yi Wuju Bladesman change a lone defender's Might from
the designation on (MIGHTY sees it), not only for the damage; Resonating
Strike's unit comes from a different location, and from face down goes to the
battlefield it was hidden at (§811.1.d.2); Tornado Warrior empowers any unit or
gear at its battlefield, either side's."""

from __future__ import annotations

from riftbound.core.battlefield import DeployedGear, FacedownCard
from riftbound.core.cards import UnitCard
from riftbound.core.enums import Domain
from riftbound.core.legality import _reaction_actions, _turn_actions
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import (_always, _battlefield, _fight, _pick, _play_spell, _setup, _spec,
                               _spell, _unit)
from test_corpus_vendetta import _attack_at


def _card(name):
    return CARD_REGISTRY[name].instantiate()


# -- Jhin Meticulous Killer -------------------------------------------------

def _jhin_hand(a, energy, mind):
    """`a` holds Jhin with `energy` Energy and `mind` Mind Power."""
    a.hand.append(_card("Jhin Meticulous Killer"))
    a.energy = energy
    a.power_pool = {Domain.MIND: mind} if mind else {}
    return len(a.hand) - 1


def _jhin_plays(loop, a):
    return [x for x in _turn_actions(loop, a) if x.kind == "UNIT"
            and a.hand[x.index].name == "Jhin Meticulous Killer"]


def test_jhin_text_is_the_printed_one():
    assert "If you've spent [4] or more to play a spell this turn, you may play me for [mind]." \
        in CARD_REGISTRY["Jhin Meticulous Killer"].raw["effect"]


def test_jhin_costs_four_until_four_is_spent_on_a_spell():
    """'If you've spent [4] or more to play a spell this turn, you may play me
    for [mind].' A [3] spell isn't enough."""
    loop, a, b = _setup()
    _play_spell(loop, a, _spell(3))
    _jhin_hand(a, 3, 1)
    assert _jhin_plays(loop, a) == []
    loop._apply_action(a, ("UNIT", 0, None))
    assert a.hand and not a.base_units


def test_jhin_is_played_for_mind_after_a_four_spell():
    loop, a, b = _setup()
    _play_spell(loop, a, _spell(4))
    idx = _jhin_hand(a, 0, 1)
    assert _jhin_plays(loop, a)
    loop._apply_action(a, ("UNIT", idx, None))
    assert [u.card.name for u in a.base_units] == ["Jhin Meticulous Killer"]
    assert a.energy == 0 and not a.power_pool.get(Domain.MIND)


def test_jhin_alternate_cost_is_a_choice():
    """Baseline: the [mind] when it can be paid; the player may pay [4]."""
    loop, a, b = _setup()
    _play_spell(loop, a, _spell(4))
    idx = _jhin_hand(a, 4, 1)
    loop._apply_action(a, ("UNIT", idx, None))
    assert a.energy == 4 and not a.power_pool.get(Domain.MIND)
    loop, a, b = _setup()
    _play_spell(loop, a, _spell(4))
    idx = _jhin_hand(a, 4, 1)
    loop.chooser = _always(False)
    loop._apply_action(a, ("UNIT", idx, None))
    assert a.energy == 0 and a.power_pool.get(Domain.MIND) == 1


def test_jhin_alternate_cost_needs_mind_power():
    loop, a, b = _setup()
    _play_spell(loop, a, _spell(4))
    _jhin_hand(a, 0, 0)
    a.power_pool = {Domain.FURY: 3}
    assert _jhin_plays(loop, a) == []


def test_jhin_alternate_cost_from_the_champion_zone():
    loop, a, b = _setup()
    _play_spell(loop, a, _spell(4))
    loop.gs.champion_A = _card("Jhin Meticulous Killer")
    a.energy, a.power_pool = 0, {Domain.MIND: 1}
    loop._apply_action(a, ("CHAMPION", None, None))
    assert loop.gs.champion_A_deployed
    assert any(u.card.name == "Jhin Meticulous Killer" for u in a.base_units)


# -- "spent [4]": Energy only -----------------------------------------------

def test_forgotten_library_counts_energy_not_power(monkeypatch):
    """'... when you play a spell, if you spent [4] or more, PREDICT.' A [3]
    spell with two Power spent [3]."""
    from riftbound.core.effects import REGISTRY
    loop, a, b = _setup()
    _battlefield(loop, 0, "Forgotten Library")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    predicted = []
    monkeypatch.setitem(REGISTRY, "predict", lambda ctx, spec: predicted.append(ctx.actor.name))
    _spec("Power Spell", category="Spell", cost_energy=3, cost_power=2, cost_power_domain="Fury",
          effects=[{"effect": "draw_cards", "trigger": "on_cast", "count": 0}])
    _play_spell(loop, a, "Power Spell")
    assert predicted == [] and loop.gs.spell_spent["A"][1] == 3


def test_abandoned_hall_pumps_a_unit_here_of_whoever_played_the_spell():
    """'When a player plays a spell, they may give a unit they control here +1
    [might] this turn.' Not a unit elsewhere; the opponent's spell pumps theirs."""
    loop, a, b = _setup()
    loop.chooser = _always(True)
    _battlefield(loop, 0, "Abandoned Hall")
    here, there, theirs = _unit("Here", 2), _unit("There", 5), _unit("Theirs", 2)
    loop.gs.battlefields[0].add_unit("A", here)
    loop.gs.battlefields[1].add_unit("A", there)
    loop.gs.battlefields[0].add_unit("B", theirs)
    _play_spell(loop, a, _spell(1))
    assert (here.might, there.might, theirs.might) == (3, 5, 2)
    _play_spell(loop, b, _spell(1))
    assert (here.might, there.might, theirs.might) == (3, 5, 3)


# -- Hunters' Circle --------------------------------------------------------

def _ambusher(p, cost=3):
    p.hand.append(UnitCard(name=f"Ambusher{len(p.hand)}", might=2, cost_energy=cost, keywords=["AMBUSH"]))
    return len(p.hand) - 1


def test_hunters_circle_discounts_an_ambush_unit_on_your_turn():
    """'For each player, the first unit or gear they play here on their turn
    costs [1] less.' An AMBUSH unit is played here too."""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hunters' Circle")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    assert loop._play_ambush_unit(a, _ambusher(a), 0)
    assert a.energy == 18
    assert loop._play_ambush_unit(a, _ambusher(a), 0)
    assert a.energy == 15                                 # the second pays in full


def test_hunters_circle_not_on_the_opponents_turn():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hunters' Circle")
    loop.gs.battlefields[0].add_unit("B", _unit("Holder", 1))
    assert loop._play_ambush_unit(b, _ambusher(b), 0)
    assert b.energy == 17


def test_hunters_circle_makes_an_ambush_unit_affordable_there_only():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hunters' Circle")
    for bf in loop.gs.battlefields:
        bf.add_unit("A", _unit("Holder", 1))
    idx = _ambusher(a)
    a.energy = 2
    lanes = [x.dst_lane for x in _reaction_actions(loop, a) if x.kind == "UNIT" and x.index == idx]
    assert lanes == [0]


def test_hunters_circle_discounts_an_ambush_champion():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hunters' Circle")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    loop.gs.champion_A = UnitCard(name="Champ", might=3, cost_energy=4, keywords=["AMBUSH"])
    assert loop._deploy_ambush_champion("A", 0)
    assert a.energy == 17


# -- Forbidding Waste / Master Yi Wuju Bladesman ----------------------------

def test_wuju_bladesman_makes_a_lone_defender_mighty_during_the_combat():
    """'While a friendly unit defends alone, it gets +2 [might].' 3 + 2 = 5:
    MIGHTY from the designation on, gone after the combat."""
    loop, a, b = _setup()
    loop.gs.legend_unit_B = _unit("Master Yi Wuju Bladesman")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 1))
    dfn = _unit("Def", 3)
    bf.add_unit("B", dfn)
    _attack_at(loop)
    loop._recompute_passives()
    assert dfn.might == 5
    _fight(loop)
    loop._recompute_passives()
    assert dfn.might == 3


def test_forbidding_waste_shrinks_a_lone_defender_during_the_combat():
    """'While a unit here is defending alone, it has -2 [might].' A 6 is no
    longer MIGHTY once it defends; the damage counts it once."""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Forbidding Waste")
    bf = loop.gs.battlefields[0]
    atk, dfn = _unit("Atk", 4), _unit("Def", 6)
    bf.add_unit("A", atk)
    bf.add_unit("B", dfn)
    _attack_at(loop)
    loop._recompute_passives()
    assert dfn.might == 4
    _fight(loop)
    assert atk not in bf.units_A and dfn not in bf.units_B   # 4 against 4


def test_forbidding_waste_spares_an_attacker_alone():
    loop, a, b = _setup()
    _battlefield(loop, 0, "Forbidding Waste")
    bf = loop.gs.battlefields[0]
    atk = _unit("Atk", 6)
    bf.add_unit("A", atk)
    bf.add_unit("B", _unit("Def", 1))
    _attack_at(loop)
    loop._recompute_passives()
    assert atk.might == 6


# -- Resonating Strike ------------------------------------------------------

def _resonating(loop, a):
    a.hand.append(_card("Resonating Strike"))
    return a.hand[-1]


def test_resonating_strike_needs_a_unit_at_a_different_location():
    """'Choose a battlefield you control and a unit you control at a different
    location.' The only unit is at the only battlefield held: no target."""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    card = _resonating(loop, a)
    assert not loop._spell_has_targets(card, "A", 0)
    a.base_units.append(_unit("Runner", 2))
    assert loop._spell_has_targets(card, "A", 0)


def test_resonating_strike_moves_between_battlefields_you_control():
    loop, a, b = _setup()
    bf0, bf1 = loop.gs.battlefields
    runner = _unit("Runner", 2)
    bf0.add_unit("A", runner)
    bf1.add_unit("A", _unit("Holder", 1))
    _pick(loop, "Runner")
    loop._apply_action(a, ("SPELL", a.hand.index(_resonating(loop, a)), 0))
    assert runner in bf1.units_A and runner.might == 4


def test_resonating_strike_from_face_down_goes_to_its_battlefield():
    """§811.1.d.2: played from face down, the battlefield is the one it was
    hidden at; the unit comes from anywhere else (it can't be there)."""
    loop, a, b = _setup()
    loop.gs.turn = 3
    bf0, bf1 = loop.gs.battlefields
    bf0.add_unit("A", _unit("Holder", 1))
    bf1.add_unit("A", _unit("Other Holder", 1))
    runner = _unit("Runner", 2)
    a.base_units.append(runner)

    def chooser(_l, kind, side, options, default, source):
        if kind.startswith("target"):                                # (side, unit) pairs
            return next(i for i, (_s, u) in enumerate(options) if u.card.name == "Runner")
        if kind.startswith("destination"):
            return len(options) - 1                 # the last: bf1, if it were allowed
        return None
    loop.chooser = chooser
    bf0.facedown = FacedownCard(card=_card("Resonating Strike"), owner="A", turn_hidden=1)
    assert loop._play_from_hidden("A", 0)
    assert runner in bf0.units_A and runner.might == 4


# -- Tornado Warrior --------------------------------------------------------

def _tornado(loop, chooser=None):
    loop.chooser = chooser or _always(True)
    loop.gs.turn = 3
    bf = loop.gs.battlefields[0]
    bf.facedown = FacedownCard(card=_card("Tornado Warrior"), owner="A", turn_hidden=1)
    return bf


def _choose_name(name):
    def chooser(_l, kind, side, options, default, source):
        if kind.startswith("optional:"):
            return options.index(True)
        if kind.startswith("target"):
            return next((i for i, o in enumerate(options) if getattr(o, "name", None) == name), None)
        return None
    return chooser


def test_tornado_warrior_may_empower_an_enemy_unit_here():
    """'When you play me from face down, you may empower something here.
    Disempower it at end of turn.' Something: either side's."""
    loop, a, b = _setup()
    bf = _tornado(loop, _choose_name("Foe"))
    foe = _unit("Foe", 2)
    bf.add_unit("B", foe)
    assert loop._play_from_hidden("A", 0)
    assert foe.empowered
    loop._resolve_delayed_effects()                        # (the end of turn's combat kills it)
    assert not foe.empowered


def test_tornado_warrior_may_empower_a_gear_here():
    loop, a, b = _setup()
    bf = _tornado(loop, _choose_name("Long Sword"))
    holder = _unit("Holder", 1)
    bf.add_unit("A", holder)
    sword = _card("Long Sword")
    holder.gear.append(sword)
    assert loop._play_from_hidden("A", 0)
    assert loop._is_empowered(sword)
    loop._end_turn()
    assert not loop._is_empowered(sword)


def test_tornado_warrior_may_empower_a_deployed_gear_here():
    loop, a, b = _setup()
    bf = _tornado(loop, _choose_name("Long Sword"))
    bf.add_unit("A", _unit("Holder", 1))
    sword = _card("Long Sword")
    bf.gear_for("A").append(DeployedGear(card=sword))
    assert loop._play_from_hidden("A", 0)
    assert loop._is_empowered(sword)


def test_tornado_warrior_offers_only_what_is_here():
    loop, a, b = _setup()
    seen = []

    def chooser(_l, kind, side, options, default, source):
        if kind.startswith("target"):
            seen.extend(getattr(o, "name", None) for o in options)
        return options.index(True) if kind.startswith("optional:") else None
    bf = _tornado(loop, chooser)
    bf.add_unit("B", _unit("Foe", 2))
    a.base_units.append(_unit("Away", 2))
    loop.gs.battlefields[1].add_unit("A", _unit("Elsewhere", 2))
    assert loop._play_from_hidden("A", 0)
    assert sorted(seen) == ["Foe", "Tornado Warrior"]


def test_tornado_warrior_baseline_prefers_a_friend_with_an_empowered_ability():
    loop, a, b = _setup()
    bf = _tornado(loop)
    lifeblade, big = _unit("Kinkou Lifeblade"), _unit("Big", 9)
    bf.add_unit("A", lifeblade)
    bf.add_unit("A", big)
    bf.add_unit("B", _unit("Foe", 2))
    assert "EMPOWERED" in CARD_REGISTRY["Kinkou Lifeblade"].raw["effect"]
    assert loop._play_from_hidden("A", 0)
    assert lifeblade.empowered and not big.empowered
