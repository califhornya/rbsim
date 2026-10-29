"""BACKLOG G2, Origins approximations. Sivir Battle Mistress's "when you
recycle a rune" resolves before the card paid for (§818.1.c.1); Malzahar
Fanatic's cost kills any friendly unit or gear; Commander Ledros kills any
friendly units (baseline: tokens, more only if needed); Fading Memories takes
a unit at a battlefield or a gear (Turn to Dust: any gear, a deployed one
stays deployed); Pack of Wonders returns a unit, gear or facedown card;
Facebreaker's two units share a battlefield; Miss Fortune Captain / Jayce
Brilliant Inventor ready "something" (unit, legend, gear or rune)."""

from __future__ import annotations

from riftbound.core.battlefield import DeployedGear, FacedownCard
from riftbound.core.cards import GearCard, SpellCard
from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.player import Rune
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _cast_now, _setup, _unit
from test_corpus_vendetta import _ctx, _usable


def _card(name):
    return CARD_REGISTRY[name].instantiate()


def test_sivirs_gold_comes_before_the_spell_paid_with_power_resolves():
    """'When you recycle a rune, you may exhaust me to play a Gold gear token
    exhausted.' Paying Power recycles a rune."""
    loop, a, b = _setup()
    loop.gs.legend_unit_A = _unit("Sivir Battle Mistress")
    a.power_pool, a.floating_power = {Domain.FURY: 1}, {}
    a.rune_pool = {Domain.FURY: [Rune(Domain.FURY)]}
    seen = []
    resolve = loop._resolve_card_effects
    loop._resolve_card_effects = lambda card, *args: (seen.append([g.name for g in a.base_gear]),
                                                      resolve(card, *args))
    a.hand = [SpellCard(name="S", cost_energy=0, cost_power=1, cost_power_domain=Domain.FURY)]
    loop._apply_action(a, ("SPELL", 0, 0))
    assert seen == [["Gold"]]


def test_malzahar_fanatic_kills_a_real_gear_with_no_token():
    """'Kill a friendly unit or gear, [tap]: ADD [rune][rune].' Baseline: a
    token, else the cheapest gear, else the weakest unit, himself last."""
    loop, a, b = _setup()
    fanatic = _unit("Malzahar Fanatic")
    other = _unit("Other", 2)
    gear = GearCard(name="Trinket", cost_energy=1)
    a.base_units.extend([fanatic, other])
    a.base_gear.append(gear)
    assert loop._units_or_gear_to_kill("A", fanatic) == [gear, other, fanatic]
    power = sum(a.power_pool.values())
    loop._apply_activated_ability(a, b, _usable(loop, "A", "gain_power_any_domain"))
    assert gear in a.trash and other in a.base_units and not fanatic.ready
    assert sum(a.power_pool.values()) == power + 2


def _play_ledros(loop, a):
    a.hand = [_card("Commander Ledros")]                  # [6] [order]x4
    loop._apply_action(a, ("UNIT", 0, 0))
    return any(u.card.name == "Commander Ledros" for u in a.base_units)


def test_commander_ledros_kills_real_units_only_when_he_needs_them():
    """'As you play me, you may kill any number of friendly units as an
    additional cost. Reduce my cost by [order] for each killed this way.'"""
    loop, a, b = _setup()
    weak, strong = _unit("Weak", 1), _unit("Strong", 3)
    a.base_units.extend([weak, strong])
    a.energy, a.power_pool = 6, {Domain.ORDER: 4}
    assert _play_ledros(loop, a) and weak in a.base_units and strong in a.base_units
    loop, a, b = _setup()
    weak, strong = _unit("Weak", 1), _unit("Strong", 3)
    a.base_units.extend([weak, strong])
    a.energy, a.power_pool = 6, {Domain.ORDER: 3}
    assert _play_ledros(loop, a) and weak not in a.base_units and strong in a.base_units


def test_fading_memories_takes_a_unit_at_a_battlefield_or_a_gear():
    """'Give a unit at a battlefield or a gear TEMPORARY.'"""
    loop, a, b = _setup()
    gear = GearCard(name="Their Gear", cost_energy=3)
    b.base_gear.append(gear)
    assert loop._spell_has_targets(_card("Fading Memories"), "A", 0)
    _cast_now(loop, a, "Fading Memories")
    loop._phase_beginning("B")
    assert gear not in b.base_gear and gear in b.trash
    enemy = _unit("Enemy", 4)
    loop.gs.battlefields[1].add_unit("B", enemy)
    _cast_now(loop, a, "Fading Memories")
    assert enemy.has_keyword("TEMPORARY")


def test_turn_to_dust_leaves_a_deployed_gear_where_it_is():
    """'Give a gear TEMPORARY. (Kill it at the start of its controller's
    Beginning Phase, before scoring.)'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    dg = DeployedGear(card=GearCard(name="Deployed", cost_energy=2))
    bf.gear_for("B").append(dg)
    _cast_now(loop, a, "Turn to Dust")
    assert dg in bf.gear_for("B") and dg.card not in b.base_gear
    loop._phase_beginning("B")
    assert dg not in bf.gear_for("B") and dg.card in b.trash


def test_pack_of_wonders_returns_a_gear_or_a_facedown_card():
    """'[tap]: Return another friendly gear, unit, or facedown card to its
    owner's hand.'"""
    loop, a, b = _setup()
    pack = _card("Pack of Wonders")
    gear = GearCard(name="Mine", cost_energy=1)
    a.base_gear.extend([pack, gear])
    hidden = SpellCard(name="Hidden")
    loop.gs.battlefields[0].facedowns.append(FacedownCard(card=hidden, owner="A", turn_hidden=0))
    loop._apply_activated_ability(a, b, _usable(loop, "A", "return_friendly_to_hand"))
    assert gear in a.hand and pack in a.base_gear and pack.tapped
    pack.tapped = False
    loop._apply_activated_ability(a, b, _usable(loop, "A", "return_friendly_to_hand"))
    assert hidden in a.hand and not loop.gs.battlefields[0].facedowns


def test_facebreaker_needs_both_units_at_one_battlefield():
    """'Stun a friendly unit and an enemy unit at the same battlefield.'"""
    loop, a, b = _setup()
    bf0, bf1 = loop.gs.battlefields
    mine, theirs = _unit("Mine", 2), _unit("Theirs", 2)
    bf0.add_unit("A", mine)
    bf1.add_unit("B", theirs)
    card = _card("Facebreaker")
    assert not loop._spell_has_targets(card, "A", 0) and not loop._spell_has_targets(card, "A", 1)
    other = _unit("Other", 2)
    bf1.add_unit("A", other)
    assert loop._spell_has_targets(card, "A", 1)
    loop._resolve_card_effects(card, bf1, a, b)
    assert other.stunned and theirs.stunned and not mine.stunned


def test_jayce_brilliant_inventor_readies_a_gear():
    """'When you play me or the first time you play a non-token gear each
    turn, you may ready something besides me that's exhausted.'"""
    loop, a, b = _setup()
    gear = GearCard(name="Tapped", cost_energy=2)
    gear.tapped = True
    a.base_gear.append(gear)
    a.hand = [_card("Jayce Brilliant Inventor")]
    loop._apply_action(a, ("UNIT", 0, 0))
    assert not gear.tapped


def test_ready_something_takes_a_legend_then_a_rune():
    """Miss Fortune Captain: 'you may ready something else that's exhausted.'"""
    loop, a, b = _setup()
    legend = _unit("Legend", 0)
    legend.ready = False
    loop.gs.legend_unit_A = legend
    rune = Rune(Domain.BODY)
    rune.ready = False
    a.rune_pool = {Domain.BODY: [rune]}
    REGISTRY["ready_something"](_ctx(loop, a, _card("Miss Fortune Captain")), {})
    assert legend.ready
    energy = a.energy
    REGISTRY["ready_something"](_ctx(loop, a, _card("Miss Fortune Captain")), {})
    assert a.energy == energy + 1
