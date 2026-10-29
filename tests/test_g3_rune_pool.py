"""BACKLOG G3 "Rune Pool empties" (B35): every player's Rune Pool empties at
the start of each Main Phase and at the end of each turn (§167, §316.3,
§317.2.d); unspent Energy and Power are lost. The engine exhausts every rune
for its Energy as the turn begins, so the Energy left stands for runes still
ready (`Player.rune_energy`, kept through the opponent's turn); only what an
ADD put in the pool (`pool_energy`, `floating_power`, the earmarked ones) is
lost."""

from __future__ import annotations

from riftbound.core.effects import REGISTRY
from riftbound.core.enums import Domain
from riftbound.core.player import Rune, RuneDeck

from test_corpus_cards import _setup, _unit
from test_corpus_vendetta import _ctx


def _pool(p, n, domain=Domain.FURY):
    """`p` with n runes of `domain`, every one's Energy still unused, nothing
    ADDed."""
    p.energy = 0
    p.pool_energy = 0
    p.power_pool.clear()
    p.floating_power.clear()
    p.rune_pool = {domain: [Rune(domain) for _ in range(n)]}
    p.channel()


def _power(p, domain):
    return p._power_left(domain)


def test_added_energy_is_lost_at_end_of_turn_rune_energy_stays():
    loop, a, b = _setup()
    _pool(a, 3)
    REGISTRY["gain_energy"](_ctx(loop, a), {"amount": 2})
    assert a.energy == 5 and a.pool_energy == 2
    loop._end_turn()
    assert a.energy == 3 and a.pool_energy == 0


def test_spending_takes_the_added_energy_first():
    loop, a, b = _setup()
    _pool(a, 3)
    a.add_energy(2)
    assert a.pay_cost(2)
    assert a.rune_energy == 3 and a.pool_energy == 0
    assert a.pay_cost(1)
    loop._end_turn()
    assert a.energy == 2


def test_the_opponents_ready_runes_last_through_my_main_phase():
    """B left 3 runes ready on their turn: still there for reactions on mine,
    but an ADD of theirs doesn't outlast my Main Phase starting."""
    loop, a, b = _setup()
    _pool(b, 3)
    b.add_energy(1)
    loop._start_of_main("A")
    assert b.energy == 3


def test_an_opponents_add_is_lost_at_the_end_of_my_turn():
    """Threshold of the Gray: 'When combat starts here, the attacker and
    defender each ADD [1].'"""
    loop, a, b = _setup()
    _pool(b, 2)
    REGISTRY["gain_energy"](_ctx(loop, b), {"amount": 1})
    assert b.energy == 3
    loop._end_turn()
    assert b.energy == 2


def test_added_power_is_lost_rune_power_stays():
    """Seal of Focus: '[tap]: REACTION - ADD [calm].'"""
    loop, a, b = _setup()
    _pool(a, 2)
    a.add_power(Domain.CALM, 1)
    assert _power(a, Domain.CALM) == 1 and _power(a, Domain.FURY) == 2
    loop._start_of_main("A")
    assert _power(a, Domain.CALM) == 0 and _power(a, Domain.FURY) == 2
    a.add_power(Domain.CALM, 1)
    loop._end_turn()
    assert _power(a, Domain.CALM) == 0 and _power(a, Domain.FURY) == 2


def test_earmarked_resources_are_lost_with_the_pool():
    """Lux Crownguard: 'ADD [2]. Use only to play spells.' Diana Scorn of the
    Moon: 'ADD [1]. Spend this Energy only during showdowns.'"""
    loop, a, b = _setup()
    REGISTRY["gain_energy"](_ctx(loop, a), {"amount": 2, "restriction": "spells_only"})
    _ctx(loop, a).add_earmarked_energy(1)
    _ctx(loop, a).add_earmarked_power(1, use="spell")
    assert a.earmarked_energy_spell == 2 and a.earmarked_energy_showdown == 1
    loop._end_turn()
    assert a.earmarked_energy_spell == a.earmarked_energy_showdown == a.earmarked_power_spell == 0


def test_blue_sentinel_adds_after_the_main_phase_empties():
    """'Your hold effects for holding here trigger an additional time. When I
    hold, ADD [rune] at the start of your next Main Phase.' The hold is in the
    Beginning Phase; an ADD then would be lost as the Main Phase starts."""
    loop, a, b = _setup()
    _pool(a, 0)
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Blue Sentinel"))
    loop._fire_scoring_trigger("on_hold", bf, "A")
    assert not sum(a.floating_power.values())
    loop._start_of_main("A")
    assert sum(a.floating_power.values()) == 2       # its own hold effect, twice


def test_runes_readied_at_end_of_turn_last_through_the_opponents_turn():
    """Sona Harmonious: 'At the end of your turn, if I'm at a battlefield,
    ready up to 4 friendly runes.' Spent runes come back ready for the
    opponent's turn."""
    loop, a, b = _setup()
    _pool(a, 5)
    a.energy = 0                     # every rune used
    loop.gs.battlefields[0].add_unit("A", _unit("Sona Harmonious"))
    loop._end_turn()
    assert a.energy == 4 and a.pool_energy == 0
    loop._start_of_main("B")
    assert a.energy == 4


def test_readying_a_rune_whose_energy_is_unused_adds_to_the_pool():
    """Its player exhausts it first (ADD [1]), then readies it: that Energy is
    the pool's, lost at end of turn."""
    loop, a, b = _setup()
    _pool(a, 3)
    a.energy = 2                     # one rune used
    REGISTRY["ready_runes"](_ctx(loop, a), {"amount": 2})
    assert a.energy == 4 and a.rune_energy == 3 and a.pool_energy == 1
    loop._end_turn()
    assert a.energy == 3


def test_recycling_a_ready_rune_puts_its_energy_in_the_pool():
    """A rune recycled for its Power while its Energy is unused: the player
    exhausts it first, so that Energy is in the pool (§164.2)."""
    loop, a, b = _setup()
    _pool(a, 2)
    assert a.pay_cost(0, 1, Domain.FURY)
    assert a.total_runes_in_play() == 1 and a.energy == 2 and a.pool_energy == 1
    loop._end_turn()
    assert a.energy == 1
    # An exhausted one goes first: no Energy moves.
    loop, a, b = _setup()
    _pool(a, 2)
    assert a.pay_cost(1, 1, Domain.FURY)
    assert a.rune_energy == 1 and a.pool_energy == 0


def test_seraphic_wyverns_extra_rune_gives_no_energy_as_the_turn_begins():
    """'If you would channel runes, channel that many runes plus 1 exhausted
    rune instead.' The Channel Phase's runes come after the Awaken, so the
    extra one stays exhausted (its Power is there: recycling needs no ready
    rune)."""
    loop, a, b = _setup()
    loop.gs.turn = 3
    _pool(a, 2)
    a.rune_deck = RuneDeck([Rune(Domain.BODY) for _ in range(6)])
    a.base_units.append(_unit("Seraphic Wyvern"))
    loop._phase_beginning("A")
    assert a.total_runes_in_play() == 5
    assert a.energy == 4 and _power(a, Domain.BODY) == 3 and _power(a, Domain.FURY) == 2


def test_a_rune_channeled_mid_turn_is_usable_at_once():
    """K'Sante Courageous: 'When I hold, channel 1 rune.' A ready rune gives
    its Energy; an exhausted one (Retreat) still its Power."""
    loop, a, b = _setup()
    _pool(a, 0)
    a.rune_deck = RuneDeck([Rune(Domain.BODY), Rune(Domain.CALM)])
    REGISTRY["channel_rune"](_ctx(loop, a), {"amount": 1})
    assert a.energy == 1 and a.pool_energy == 0 and _power(a, Domain.BODY) == 1
    REGISTRY["channel_rune"](_ctx(loop, a), {"amount": 1, "exhausted": True})
    assert a.energy == 1 and _power(a, Domain.CALM) == 1
    loop._start_of_main("A")
    assert a.energy == 1


def test_a_whole_turn_keeps_the_runes_energy_for_the_reactions():
    """A passes with 3 runes unused, B's turn begins: A's 3 are still there
    after B's Main Phase starts; A's ADD from the turn before is not."""
    loop, a, b = _setup()
    _pool(a, 3)
    _pool(b, 0)
    a.add_energy(2)
    a.agent = b.agent = None
    loop._end_turn()
    assert loop.gs.active == "B"
    loop._begin_turn()
    assert a.energy == 3
