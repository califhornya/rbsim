"""Rules audit, the owner's post-ban decks (docs/audit/AUDIT.md, seventh pass):
competitive_evelynn and competitive_khazix, given by the owner on 2026-11-17.
Their cards new to the audit, read against the printed text
(riftbound/data/reference/piltover_archive.json) and played in the engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riftbound.core.cards import UnitCard
from riftbound.registry.cards_registry import BANNED_CARDS, load_deck_json

from audit_helpers import act, card, choices, hide, legend, scripted, setup, unit

DECKS = Path(__file__).resolve().parents[2] / "riftbound" / "data" / "decks"


def _decks(*players):
    for p in players:
        p.deck.cards = [UnitCard(name=f"Deck{i}", might=1) for i in range(5)]


def _names(options):
    return [getattr(getattr(o, "card", None), "name", None) or getattr(o, "name", o)
            for o in options]


@pytest.mark.parametrize("name", ["competitive_evelynn", "competitive_khazix"])
def test_the_deck_is_the_list_given(name):
    """40 cards with the Chosen Champion, 12 runes, 3 battlefields, 10 in the
    sideboard, no banned card; every name is a card of the corpus."""
    cards, runes, champion, legend_spec, battlefields = load_deck_json(DECKS / f"{name}.json")
    data = json.loads((DECKS / f"{name}.json").read_text(encoding="utf-8"))
    assert sum(c["count"] for c in data["cards"]) + 1 == 40 and champion is not None
    assert sum(r["count"] for r in data["runes"]) == 12 and len(battlefields) == 3
    assert sum(c["count"] for c in data["sideboard"]) == 10 and legend_spec is not None
    names = {data["legend"], data["champion"]} | {b["name"] for b in data["battlefields"]}
    names |= {c["name"] for c in data["cards"] + data["sideboard"]}
    assert not names & BANNED_CARDS


# -- D57. Evelynn's legend: two cards from face down, discard before draw ------------

def test_evelynn_legend_draws_before_it_discards_with_two_plays_on_the_chain():
    """Evelynn, Agony's Embrace: 'Once each turn, when you play a card from face
    down, draw 1. Then, if it's not your turn, discard 1.' One ability, once each
    turn (§383.3.e.1). Two cards played from face down in a row on the
    opponent's turn: the second play's ability skipped the draw (used by the
    first, on the chain) and kept the discard, which resolved first: the
    player discarded from a hand without the card drawn."""
    loop, a, b = setup(active="B")
    _decks(a, b)
    legend(loop, "A", "Evelynn Agony's Embrace")
    a.hand.append(card("Rampage"))
    loop.gs.battlefields[0].add_unit("A", unit("mine", 2))
    loop.gs.battlefields[1].add_unit("B", unit("theirs", 2))
    hide(loop, "A", 0, "Momentary Companion")
    hide(loop, "A", 0, "Gutter Guardian")
    b.hand.append(card("Onslaught"))
    seen = choices(loop, {})
    scripted(loop, a, b, A={"reaction": ["Play Momentary Companion from Hidden",
                                         "Play Gutter Guardian from Hidden"]})
    act(loop, "B", "Cast Onslaught")
    assert [opts for kind, _s, opts in seen if kind == "discard"] == [["Rampage", "Deck4"]]
    assert len(a.hand) == 1 and len(a.deck.cards) == 4


def test_evelynn_legend_on_your_turn_draws_once_and_never_discards():
    loop, a, b = setup(active="A")
    _decks(a, b)
    legend(loop, "A", "Evelynn Agony's Embrace")
    loop.gs.battlefields[0].add_unit("A", unit("mine", 2))
    hide(loop, "A", 0, "Momentary Companion")
    hide(loop, "A", 0, "Gutter Guardian")
    seen = choices(loop, {})
    act(loop, "A", "Play Momentary Companion from Hidden @BF0")
    act(loop, "A", "Play Gutter Guardian from Hidden @BF0")
    assert len(a.hand) == 1 and not a.trash
    assert not [k for k, _s, _o in seen if k == "discard"]


# -- D58. Kha'Zix's legend buffs only a unit at the first battlefield ----------------

def test_khazix_legend_buffs_a_unit_anywhere():
    """Kha'Zix, Voidreaver: 'Spend 1 XP, [Tap]: [Buff] a unit.' A legend is at
    no battlefield: "a unit" is any unit, friendly or enemy, base included. The
    choice was the units at the first battlefield (a legend's "here")."""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Kha'Zix Voidreaver")
    loop.gs.xp_A = 1
    loop.gs.battlefields[0].add_unit("A", unit("first", 1))
    loop.gs.battlefields[1].add_unit("A", unit("second", 1))
    loop.gs.battlefields[1].add_unit("B", unit("enemy", 1))
    target = unit("home", 1)
    a.base_units.append(target)
    seen = choices(loop, {"target:buff_unit": lambda _l, o: _names(o).index("home")})
    act(loop, "A", "Activate buff_unit")
    assert sorted(*[opts for kind, _s, opts in seen if kind == "target:buff_unit"]) == \
        ["enemy", "first", "home", "second"]
    assert target.might_counters == 1 and loop.gs.xp_A == 0


# -- Read, played and found right ---------------------------------------------------

def _evelynn_board(active):
    loop, a, b = setup(active=active)
    _decks(a, b)
    loop.gs.battlefields[0].add_unit("A", unit("mine", 2))
    loop.gs.battlefields[0].add_unit("B", unit("here already", 1))
    loop.gs.battlefields[1].add_unit("B", unit("there", 3))
    b.base_units.append(unit("home", 4))
    return loop, a, b


def test_evelynn_champion_pulls_an_enemy_from_a_different_location():
    """Evelynn, Entrancing: 'When you play me from facedown on your turn, you may
    move an enemy unit at a different location to my battlefield.' Bases are
    locations; the unit moved in contests her battlefield: its player is the
    attacker (§466.2.c.1)."""
    loop, a, b = _evelynn_board("A")
    hide(loop, "A", 0, "Evelynn Entrancing")
    seen = choices(loop, {"target:move_unit": lambda _l, o: [_names([x[1]])[0] for x in o].index("home")})
    loop.verbose = False
    act(loop, "A", "Play Evelynn Entrancing from Hidden @BF0")
    assert [[_names([x[1]])[0] for x in o] for k, _s, o in seen if k == "target:move_unit"] == \
        [["there", "home"]]
    assert not b.base_units


@pytest.mark.parametrize("how", ["hand", "their turn"])
def test_evelynn_champion_moves_nothing_from_hand_or_on_their_turn(how):
    loop, a, b = _evelynn_board("A" if how == "hand" else "B")
    seen = choices(loop, {})
    if how == "hand":
        a.hand.append(card("Evelynn Entrancing"))
        act(loop, "A", "Play Evelynn Entrancing to BF0")
    else:
        hide(loop, "A", 0, "Evelynn Entrancing")
        b.hand.append(card("Onslaught"))
        scripted(loop, a, b, A={"reaction": ["Play Evelynn Entrancing from Hidden"]})
        act(loop, "B", "Cast Onslaught")
    assert not [k for k, _s, _o in seen if "move_unit" in k]
    assert [u.card.name for u in b.base_units] == ["home"]


@pytest.mark.parametrize("active, temporary", [("A", False), ("B", True)])
def test_momentary_companion_is_temporary_only_off_turn(active, temporary):
    """Momentary Companion: 'When you play me, if it's not your turn, give me
    [Temporary].'"""
    loop, a, b = setup(active=active)
    _decks(a, b)
    loop.gs.battlefields[0].add_unit("A", unit("mine", 2))
    hide(loop, "A", 0, "Momentary Companion")
    if active == "A":
        act(loop, "A", "Play Momentary Companion from Hidden @BF0")
    else:
        b.hand.append(card("Onslaught"))
        scripted(loop, a, b, A={"reaction": ["Play Momentary Companion from Hidden"]})
        act(loop, "B", "Cast Onslaught")
    mc = next(u for u in loop.gs.battlefields[0].units_A if u.card.name == "Momentary Companion")
    assert ("TEMPORARY" in mc.granted_keywords) is temporary


def test_pyke_plays_an_exhausted_gold_once_a_turn_while_at_a_battlefield():
    """Pyke, Returned: 'Once each turn, when an enemy unit dies while I'm at a
    battlefield, play a Gold gear token exhausted.' The enemy may die anywhere."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("Pyke Returned"))
    v1, v2 = unit("v1", 1), unit("v2", 1)
    b.base_units += [v1, v2]
    for v in (v1, v2):
        loop._kill_unit_or_gear("B", v)
        loop._flush_triggers()
    assert [(g.name, g.tapped) for g in a.base_gear] == [("Gold", True)]
    loop, a, b = setup(active="A")
    a.base_units.append(unit("Pyke Returned"))
    v = unit("v", 1)
    b.base_units.append(v)
    loop._kill_unit_or_gear("B", v)
    loop._flush_triggers()
    assert not a.base_gear


def test_khazix_alone_enemy_gives_might_and_xp_and_the_legend_its_xp():
    """Kha'Zix, Mutating Horror: 'When I attack or defend, if an enemy unit is
    alone here, give me +2 [Might] this turn and gain 2 XP.' Voidreaver: 'When
    you win a combat, gain 1 XP.'"""
    loop, a, b = setup(active="A")
    _decks(a, b)
    legend(loop, "A", "Kha'Zix Voidreaver")
    kz = unit("Kha'Zix Mutating Horror")
    a.base_units.append(kz)
    loop.gs.battlefields[0].add_unit("B", unit("lonely", 5))
    scripted(loop, a, b)
    act(loop, "A", "Move Kha'Zix Mutating Horror base→BF0")
    loop._flush_pending_move()
    assert kz.might == 6 and loop.gs.xp_A == 3
    assert [u.card.name for u in loop.gs.battlefields[0].units_A] == ["Kha'Zix Mutating Horror"]


def test_khazix_with_two_enemies_gets_nothing():
    loop, a, b = setup(active="B")
    _decks(a, b)
    kz = unit("Kha'Zix Mutating Horror")
    loop.gs.battlefields[0].add_unit("A", kz)
    b.base_units += [unit("e1", 1), unit("e2", 1)]
    scripted(loop, a, b)
    act(loop, "B", "Move e1")
    act(loop, "B", "Move e2")
    loop._flush_pending_move()
    assert loop.gs.xp_A == 0 and kz.might == 4


def test_khazix_legend_moves_an_exhausted_unit_from_a_battlefield_to_base():
    """Voidreaver: 'Spend 2 XP, [Tap]: Move an exhausted friendly unit from a
    battlefield to its base.'"""
    loop, a, b = setup(active="A")
    legend(loop, "A", "Kha'Zix Voidreaver")
    loop.gs.xp_A = 2
    loop.gs.battlefields[0].add_unit("A", unit("ready", 1))
    tired = unit("tired", 1, ready=False)
    loop.gs.battlefields[1].add_unit("A", tired)
    a.base_units.append(unit("in base", 1, ready=False))
    seen = choices(loop, {})
    act(loop, "A", "Activate move_unit")
    assert [[u.card.name for _side, u in o] for k, _s, o in seen if k == "target:move_unit"] == \
        [["tired"]]
    assert tired in a.base_units and loop.gs.xp_A == 0


def test_ksante_channels_a_rune_when_he_holds():
    """K'Sante, Courageous: 'When I hold, channel 1 rune.'"""
    from riftbound.core.enums import Domain
    from riftbound.core.player import Rune
    loop, a, b = setup(active="A", rich=())
    _decks(a, b)
    loop.gs.battlefields[0].add_unit("A", unit("K'Sante Courageous"))
    a.rune_deck.runes = [Rune(Domain.BODY) for _ in range(5)]
    scripted(loop, a, b)
    loop.gs.turn = 3
    loop._begin_turn()
    assert loop.gs.points_A == 1 and a.total_runes_in_play() == 3


def test_hold_em_costs_two_less_after_a_unit_played_to_a_battlefield():
    """Hold 'Em: 'This costs [2] less if you've played a unit or gear to a
    battlefield this turn.' A gear played to base doesn't count."""
    loop, a, b = setup(active="A", rich=())
    loop.gs.battlefields[0].add_unit("A", unit("x", 1))
    a.hand += [card("Hold 'Em"), card("Boots of Swiftness"), card("Gutter Guardian")]
    a.energy = 3
    act(loop, "A", "Play gear Boots of Swiftness")
    a.energy = 1
    assert not [lb for lb in _labels(loop) if "Hold 'Em" in lb]
    a.energy = 3
    act(loop, "A", "Play Gutter Guardian to BF0")
    a.energy = 1
    assert [lb for lb in _labels(loop) if "Hold 'Em" in lb]


def _labels(loop, side="A"):
    from audit_helpers import labels
    return labels(loop, side)


def test_boots_of_swiftness_equip_costs_a_chaos_rune_and_gives_ganking():
    """Boots of Swiftness: '[Equip] [Chaos]' and '[Ganking]', +2 [Might]."""
    loop, a, b = setup(active="A", rich=())
    boots = card("Boots of Swiftness")
    a.base_gear.append(boots)
    walker = unit("walker", 1)
    a.base_units.append(walker)
    assert loop._equip_cost(boots)["domain_power"] == {"chaos": 1}
    from riftbound.core.enums import Domain
    a.add_power(Domain.CHAOS, 1)
    act(loop, "A", "Equip Boots of Swiftness")
    assert walker.gear == [boots] and walker.might == 3 and walker.has_keyword("GANKING")


def test_void_assault_moves_both_and_its_caster_attacks():
    """Void Assault: 'Move a friendly unit, then move an enemy unit. (If they both
    move to a battlefield you don't control, you're the attacker.)'"""
    loop, a, b = setup(active="A")
    _decks(a, b)
    a.base_units.append(unit("mine", 3))
    b.base_units.append(unit("theirs", 1))
    a.hand.append(card("Void Assault"))
    bf1 = loop.gs.battlefields[1]
    seen = choices(loop, {"destination:move_unit": lambda _l, o: o.index(bf1)})
    scripted(loop, a, b)
    loop.verbose = False
    act(loop, "A", "Cast Void Assault @BF1")
    assert [u.card.name for u in bf1.units_A] == ["mine"] and not bf1.units_B
    assert bf1.controller() == "A" and loop.gs.points_A == 1
    assert [k for k, _s, _o in seen if k.startswith("target:move")] == \
        ["target:move_unit", "target:move_unit"]


def test_grim_resolve_gives_two_xp_when_the_unit_wins():
    """Grim Resolve: 'Give a friendly unit +3 [Might] this turn. When it wins a
    combat this turn, gain 2 XP.'"""
    loop, a, b = setup(active="A")
    _decks(a, b)
    hero = unit("hero", 1)
    a.base_units.append(hero)
    loop.gs.battlefields[0].add_unit("B", unit("foe", 3))
    a.hand.append(card("Grim Resolve"))
    scripted(loop, a, b)
    act(loop, "A", "Cast Grim Resolve")
    assert hero.might == 4 and loop.gs.xp_A == 0
    act(loop, "A", "Move hero")
    loop._flush_pending_move()
    assert loop.gs.xp_A == 2


def test_acceptable_losses_each_player_kills_one_of_theirs():
    loop, a, b = setup(active="A")
    for p in (a, b):
        p.base_gear += [card("Boots of Swiftness"), card("Edge of Night")]
    a.hand.append(card("Acceptable Losses"))
    seen = choices(loop, {})
    act(loop, "A", "Cast Acceptable Losses")
    assert [s for k, s, _o in seen if k.startswith("kill_own")] == ["A", "B"]
    assert len(a.base_gear) == 1 and len(b.base_gear) == 1


def test_decree_of_strength_recycles_a_mind_card_from_their_hand():
    """Decree of Strength: 'They reveal their hand and you choose a Mind card
    from it. They recycle that card.'"""
    loop, a, b = setup(active="A")
    _decks(a, b)
    b.hand += [card("Gust"), card("Time Warp"), card("Rampage")]
    a.hand.append(card("Decree of Strength"))
    seen = choices(loop, {})
    act(loop, "A", "Cast Decree of Strength")
    assert [o for k, _s, o in seen if k.startswith("card:")] == [["Time Warp"]]
    assert [c.name for c in b.hand] == ["Gust", "Rampage"] and b.deck.cards[0].name == "Time Warp"


def test_bandle_scouts_academy_gives_the_hider_an_exhausted_gold():
    loop, a, b = setup(active="B")
    bf = loop.gs.battlefields[0]
    bf.card = card("Bandle Scouts' Academy")
    bf.add_unit("B", unit("b", 1))
    b.hand.append(card("Momentary Companion"))
    act(loop, "B", "Hide Momentary Companion")
    assert [(g.name, g.tapped) for g in b.base_gear] == [("Gold", True)] and not a.base_gear


def test_packed_amphitheater_gives_every_champion_unit_here_one_might():
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.card = card("Packed Amphitheater")
    units = [unit("Evelynn Entrancing"), unit("Rengar Trophy Hunter"), unit("plain", 2)]
    for u in units:
        bf.add_unit("A", u)
    pyke = unit("Pyke Returned")
    bf.add_unit("B", pyke)
    loop._recompute_passives()
    assert [u.might - u.card.might for u in units + [pyke]] == [1, 1, 0, 1]


def test_rakelstake_predicts_once_for_two_units_played_there():
    """Rakelstake: 'For each player, the first time they play a unit or gear here
    each turn, they [Predict].'"""
    loop, a, b = setup(active="A")
    _decks(a, b)
    bf = loop.gs.battlefields[0]
    bf.card = card("Rakelstake")
    bf.add_unit("A", unit("held", 1))
    a.hand += [card("Gutter Guardian"), card("Momentary Companion")]
    seen = choices(loop, {})
    act(loop, "A", "Play Gutter Guardian to BF0")
    act(loop, "A", "Play Momentary Companion to BF0")
    assert [k for k, _s, _o in seen if k.startswith("predict")] == ["predict_recycle"]


@pytest.mark.parametrize("caster, offered", [("A", ["Ruin Runner", "plain"]), ("B", ["plain"])])
def test_ruin_runner_cant_be_chosen_by_enemy_spells(caster, offered):
    loop, a, b = setup(active=caster)
    loop.gs.battlefields[0].add_unit("A", unit("Ruin Runner"))
    loop.gs.battlefields[0].add_unit("A", unit("plain", 1))
    loop.gs.get_player(caster).hand.append(card("Onslaught"))
    loop._recompute_passives()
    seen = choices(loop, {})
    act(loop, caster, "Cast Onslaught @BF0")
    assert [o for k, _s, o in seen if k.startswith("target:")] == [offered]


def test_onslaught_is_played_from_the_trash_by_flow():
    loop, a, b = setup(active="A", rich=())
    loop.gs.battlefields[0].add_unit("A", unit("x", 1))
    a.trash.append(card("Onslaught"))
    a.energy = 4
    assert "Play Onslaught from trash (FLOW)" in _labels(loop)
