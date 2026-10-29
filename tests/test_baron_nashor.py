"""Baron Nashor (BACKLOG E): "As you play me, add the Baron Pit battlefield token
to the board if it's not there already. If you do, I enter there. I can't be
chosen by enemy spells and abilities. Other friendly units have +2 [might]." The
Baron Pit (§187.9): "Units can move here from anywhere." """
from __future__ import annotations

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.enums import CardType, Domain
from riftbound.core.legality import legal_actions
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _battlefield, _setup, _unit
from test_corpus_proving_grounds import _legend


def _baron(p):
    p.hand.append(CARD_REGISTRY["Baron Nashor"].instantiate())
    return p.hand[-1]


def _play_baron(loop, p, dst=None):
    p.energy = max(p.energy, 10)
    p.add_power(Domain.CHAOS, 3)
    card = _baron(p)
    loop._apply_action(p, ("UNIT", len(p.hand) - 1, 0, dst))
    return card


def _zones(loop, card):
    """Every place `card` is: hands, bases, battlefields."""
    gs = loop.gs
    out = [f"hand {p.name}" for p in (gs.A, gs.B) for c in p.hand if c is card]
    out += [f"base {p.name}" for p in (gs.A, gs.B) for u in p.base_units if u.card is card]
    out += [f"BF{i}" for i, bf in enumerate(gs.battlefields)
            for u in bf.units_A + bf.units_B if u.card is card]
    return out


def test_baron_pit_is_a_battlefield_token():
    assert CARD_REGISTRY["Baron Pit"].category is CardType.BATTLEFIELD


def test_baron_adds_the_pit_enters_there_and_conquers_it():
    loop, a, b = _setup()
    a.energy = 20
    card = _play_baron(loop, a)
    assert a.energy == 10
    pit = loop.gs.battlefields[2]
    assert pit.card.name == "Baron Pit"
    assert _zones(loop, card) == ["BF2"]               # one card, one zone
    baron = pit.units_A[0]
    assert not baron.ready and baron.might == 12
    loop._flush_pending_move()                         # he contested the new battlefield
    assert pit.control() == "A" and loop.gs.points_A == 1


def test_a_second_baron_enters_where_he_was_played():
    loop, a, b = _setup()
    _play_baron(loop, a)
    loop._flush_pending_move()
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    second = _play_baron(loop, a, dst=0)
    assert len(loop.gs.battlefields) == 3              # the Pit is there already
    assert _zones(loop, second) == ["BF0"]
    loop, a, b = _setup()
    _play_baron(loop, a)
    other = _play_baron(loop, b)                       # the opponent's too
    assert len(loop.gs.battlefields) == 3 and _zones(loop, other) == ["base B"]


def test_baron_gives_other_friendly_units_two_wherever_they_are():
    loop, a, b = _setup()
    home, there = _unit("Home", 1), _unit("There", 3)
    enemy = _unit("Enemy", 2)
    a.base_units.append(home)
    loop.gs.battlefields[0].add_unit("A", there)
    loop.gs.battlefields[1].add_unit("B", enemy)
    _play_baron(loop, a)
    loop._recompute_passives()
    assert (home.might, there.might, enemy.might) == (3, 5, 2)
    baron = loop.gs.battlefields[2].units_A[0]
    assert baron.might == 12
    loop.gs.battlefields[2].remove_unit("A", baron)    # he leaves: the bonus ends
    loop._recompute_passives()
    assert (home.might, there.might) == (1, 3)
    assert loop.gs.battlefields[2].card.name == "Baron Pit"   # the Pit stays


def test_baron_cant_be_chosen_by_enemy_spells_and_abilities():
    loop, a, b = _setup()
    _play_baron(loop, a)
    loop._recompute_passives()
    baron = loop.gs.battlefields[2].units_A[0]
    assert not loop._can_choose(baron, "B", SpellCard(name="S"))
    assert loop._can_choose(baron, "A", SpellCard(name="S"))


def test_units_can_move_to_the_pit_from_anywhere_but_not_back():
    loop, a, b = _setup()
    _play_baron(loop, a)
    loop._flush_pending_move()
    walker = _unit("Walker", 2)
    loop.gs.battlefields[0].add_unit("A", walker)

    def moves(side):
        return {(act.lane, act.dst_lane) for act in legal_actions(loop, player=side)
                if act.kind == "MOVE"}
    assert (0, 2) in moves("A") and (0, 1) not in moves("A")   # BF0 -> Pit, not BF0 -> BF1
    loop._apply_action(a, ("MOVE", 0, 0, 2))
    loop._flush_pending_move()
    assert walker in loop.gs.battlefields[2].units_A
    walker.ready = True
    assert (2, 0) not in moves("A") and (2, 3) in moves("A")   # Pit -> base only
    loop.gs.active = "B"                               # an enemy unit too
    loop.gs.battlefields[1].add_unit("B", _unit("Rival", 1))
    assert (1, 2) in moves("B") and (1, 0) not in moves("B")


def test_riven_baron_played_to_a_battlefield_you_control_enters_ready_at_the_pit():
    """FAQ: both replacement effects apply (§355.2): he enters ready at the Pit."""
    loop, a, b = _setup()
    _legend(loop, "A", "Riven The Exile")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    _play_baron(loop, a, dst=0)
    assert loop.gs.battlefields[2].units_A[0].ready
    loop, a, b = _setup()
    _legend(loop, "A", "Riven The Exile")
    _play_baron(loop, a)                               # played to base: no
    assert not loop.gs.battlefields[2].units_A[0].ready


def test_hunters_circle_takes_one_off_baron_played_there():
    """FAQ: the location and cost are fixed when he is played; entering at the
    Pit comes later: [9][C][C][C]."""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Hunters' Circle")
    loop.gs.battlefields[0].add_unit("A", _unit("Holder", 1))
    _play_baron(loop, a, dst=0)
    assert a.energy == 11
    assert loop.gs.battlefields[2].units_A[0].card.name == "Baron Nashor"
    a.hand.append(UnitCard(name="Next", might=1, cost_energy=3))
    loop._apply_action(a, ("UNIT", len(a.hand) - 1, 0, 0))
    assert a.energy == 8                               # Baron was the first played there
