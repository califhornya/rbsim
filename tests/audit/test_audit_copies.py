"""Rules audit, eighth pass (docs/audit/AUDIT.md): the copies of the game.

The search copies the game (GameState.clone, by pickle) and so does a spell's
declaration (a deepcopy of the state, its players' agents left out; then of the
whole loop, with the board restored), and plays on with a new GameLoop. Three
stores kept `id()` integers, which in a copy still name the original's objects:
`once_per_turn_used` (D66), `combat_designated` (D67), `conquer_return` (D68).

The reviewer's reproductions, run on the three copy routes: M1-M7 of
docs/audit/revisione_esterna/clone_fidelity_probe_rbsim_e72318e.txt (section
4) and the tests of design_stable_identity_rbsim_2900311.txt (section 4.1-4.2),
there one for each once-per-turn record. The original is checked too: the copy
plays as it does and doesn't change it."""

from __future__ import annotations

import copy

import pytest

from riftbound.core.cards import GearCard, SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import EffectContext, GameLoop

from audit_helpers import Scripted, act, card, choices, labels, setup, unit

ROUTES = ["clone", "deepcopy", "loop"]


def _copy(loop: GameLoop, route: str) -> GameLoop:
    """The game copied and played on: `clone` as the search copies it,
    `deepcopy` as a declaration (the agents left out, a new GameLoop), `loop`
    as a declaration's second copy (the whole loop). Same chooser."""
    gs = loop.gs
    memo = {id(p.agent): None for p in (gs.A, gs.B) if p.agent is not None}
    if route == "clone":
        copied = GameLoop(gs.clone())
    elif route == "deepcopy":
        copied = GameLoop(copy.deepcopy(gs, memo))
    else:
        copied = copy.deepcopy(loop, memo)
    copied.chooser = loop.chooser
    return copied


def _twin(loop: GameLoop, u: UnitInPlay) -> UnitInPlay:
    """`u` in this game: a copy keeps every card's uuid."""
    gs = loop.gs
    units = [x for bf in gs.battlefields for x in bf.units_A + bf.units_B]
    return next(x for x in units + gs.A.base_units + gs.B.base_units if x.card.uuid == u.card.uuid)


def _yes(loop: GameLoop) -> list:
    """Every "you may" answered yes; the log of what was asked."""
    return choices(loop, {"optional:": lambda _l, options: options.index(True)})


# ------------------------------------------------- D66: once_per_turn_used

@pytest.mark.parametrize("route", ROUTES)
def test_pyke_returned_makes_one_gold_a_turn_in_a_copy(route):
    """Pyke, Returned: 'Once each turn, when an enemy unit dies while I'm at a
    battlefield, play a Gold gear token exhausted.' Copied after the first
    Gold, a second enemy death that turn makes none (M1)."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("Pyke Returned"))
    first, second = unit("v1", 1), unit("v2", 1)
    b.base_units += [first, second]
    loop._kill_unit_or_gear("B", first)
    loop._flush_triggers()
    copied = _copy(loop, route)
    golds = []
    for game in (loop, copied):
        game._kill_unit_or_gear("B", _twin(game, second))
        game._flush_triggers()
        golds.append([g.name for g in game.gs.A.base_gear])
    assert golds == [["Gold"], ["Gold"]]                     # the original, the copy


@pytest.mark.parametrize("route", ROUTES)
def test_black_market_used_this_turn_is_not_offered_in_a_copy(route):
    """Black Market: '[Rune] [Rune]: Draw 1. Each player may use this ability
    once on their turn.' Used once, with Power left for another use: the copy
    doesn't offer it again (M6; design 4.1.a, from the legal menu)."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].card = card("Black Market")
    loop.gs.battlefields[0].add_unit("B", unit("Owner", 1))
    a.deck.cards = [UnitCard(name=f"D{i}", might=1) for i in range(3)]
    act(loop, "A", "Battlefield draw_cards (Black Market)")
    copied = _copy(loop, route)
    offered = [any("Black Market" in lbl for lbl in labels(game, "A")) for game in (loop, copied)]
    assert len(copied.gs.A.hand) == 1 and offered == [False, False]


@pytest.mark.parametrize("route", ROUTES)
def test_riven_ability_used_this_turn_leaves_only_svellsongurs_use_in_a_copy(route):
    """Riven Deserter: 'Exhaust a friendly unit: Ready a unit. Use this ability
    only once per turn.' Svellsongur copies her text: its copy of the ability
    has its own use. Riven's used, the copy offers only Svellsongur's (design
    4.2)."""
    loop, a, b = setup(active="A")
    riven = unit("Riven Deserter")
    riven.gear.append(card("Svellsongur"))
    a.base_units += [riven] + [unit(f"D{i}", 1) for i in range(3)]
    a.base_units += [unit(f"T{i}", 1, ready=False) for i in range(3)]
    act(loop, "A", "Activate ready_unit (Riven Deserter)")
    copied = _copy(loop, route)
    usable = []
    for game in (loop, copied):
        mine = _twin(game, riven)
        entries = [e for e in game.activatable_abilities("A") if e.get("unit") is mine]
        usable.append([(e.get("copy"), game._ability_usable(game.gs.A, e)) for e in entries])
    assert usable == [[(None, False), (1, True)]] * 2


@pytest.mark.parametrize("route", ROUTES)
def test_black_rose_sanctum_first_death_each_turn_per_player_in_a_copy(route):
    """Black Rose Sanctum: 'For each player, the first time each turn a
    non-token unit they control dies here, they play a 1 [Might] Recruit unit
    token to their base.' A's first is copied: in the copy A's second death
    makes no Recruit, B's first does (design 4.2, the per-player scope)."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.card = card("Black Rose Sanctum")
    first, second, theirs = unit("a1", 1), unit("a2", 1), unit("b1", 1)
    bf.add_unit("A", first)
    bf.add_unit("A", second)
    bf.add_unit("B", theirs)
    loop._kill_unit_or_gear("A", first)
    loop._flush_triggers()
    copied = _copy(loop, route)
    recruits = []
    for game in (loop, copied):
        game._kill_unit_or_gear("A", _twin(game, second))
        game._kill_unit_or_gear("B", _twin(game, theirs))
        game._flush_triggers()
        recruits.append([len(game.gs.A.base_units), len(game.gs.B.base_units)])
    assert recruits == [[1, 1], [1, 1]]


@pytest.mark.parametrize("route", ROUTES)
def test_mordekaiser_dies_the_second_time_in_a_copy(route):
    """Mordekaiser, Twice Slain: 'Once each turn, if I would die, you may kill
    a friendly unit to heal me, exhaust me, and recall me instead.' Saved
    once, copied: the second lethal damage that turn kills him (design 4.2, a
    replacement)."""
    loop, a, b = setup(active="A")
    mord = unit("Mordekaiser Twice Slain")
    loop.gs.battlefields[0].add_unit("A", mord)
    a.base_units += [unit("F1", 1), unit("F2", 1)]

    def lethal(game):
        target = _twin(game, mord)
        EffectContext(game, SpellCard(name="Z"), game.gs.B, game.gs.A,
                      game.gs.battlefields[0], {}).damage_units([target], 99)
        return target in game.gs.A.base_units

    assert lethal(loop)
    copied = _copy(loop, route)
    assert [lethal(game) for game in (loop, copied)] == [False, False]


@pytest.mark.parametrize("route", ROUTES)
def test_orianna_discounts_one_gear_a_turn_in_a_copy(route):
    """Orianna, Mechanical Marvel: 'Once each turn, while I'm at a battlefield,
    you may pay [1] [Rune] less to play a gear.' Used, copied: the second gear
    costs its Power (design 4.2)."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("Orianna Mechanical Marvel"))
    a.hand.append(GearCard(name="G1", cost_energy=1, cost_power=1))
    loop._apply_action(a, ("GEAR", 0, 0))
    copied = _copy(loop, route)
    paid = []
    for game in (loop, copied):
        p = game.gs.A
        power = sum(p.power_pool.values())
        p.hand.append(GearCard(name="G2", cost_energy=1, cost_power=1))
        game._apply_action(p, ("GEAR", 0, 0))
        paid.append(power - sum(p.power_pool.values()))
    assert paid == [1, 1]


@pytest.mark.parametrize("route", ROUTES)
def test_zilean_doubles_one_token_a_turn_in_a_copy(route):
    """Zilean, Time Mage: 'Once each turn, if you would play a token unit
    while I'm at a battlefield, you may play that token and an additional copy
    of it instead.' Used, copied: the next token is one (design 4.2)."""
    loop, a, b = setup(active="A")
    loop.gs.battlefields[0].add_unit("A", unit("Zilean Time Mage"))
    loop._play_token("Recruit", "A")
    copied = _copy(loop, route)
    recruits = []
    for game in (loop, copied):
        game._play_token("Recruit", "A")
        recruits.append(sum(u.card.name == "Recruit" for u in game.gs.A.base_units))
    assert recruits == [3, 3]


# ------------------------------------------------- D67: combat_designated

class _CopiesInTheShowdown(Scripted):
    """Scripted, and copies the game the first time it acts in a showdown
    (where the search copies it)."""
    route = "clone"
    copied = None

    def decide_showdown_action(self, opponent, bf_idx):
        if self.copied is None:
            self.copied = _copy(self.loop, self.route)
        return super().decide_showdown_action(opponent, bf_idx)


@pytest.mark.parametrize("route", ROUTES)
def test_a_copy_in_the_showdown_keeps_its_attackers_and_defenders(route):
    """ASSAULT is '+X [Might] while I'm an attacker', SHIELD 'while I'm a
    defender' (§807.1.c-d). A move opens the combat showdown; copied there, the
    units are still Attacker and Defender, with their bonus (design 4.1.b)."""
    loop, a, b = setup(active="A")
    atk = UnitInPlay(card=UnitCard(name="Atk", might=2, keywords=["ASSAULT 2"]), ready=True)
    dfn = UnitInPlay(card=UnitCard(name="Dfn", might=5, keywords=["SHIELD 1"]), ready=True)
    a.base_units.append(atk)
    loop.gs.battlefields[0].add_unit("B", dfn)
    a.agent, b.agent = _CopiesInTheShowdown(a, loop), Scripted(b, loop)
    a.agent.route = route
    act(loop, "A", "Move Atk base→BF0")
    loop._flush_pending_move()
    copied = a.agent.copied
    copied._recompute_passives()
    atk2, dfn2 = _twin(copied, atk), _twin(copied, dfn)
    assert (atk2.bonus_might, dfn2.bonus_might) == (2, 1)
    assert copied._is_attacking(atk2) and copied._in_combat(dfn2) and not copied._is_attacking(dfn2)


@pytest.mark.parametrize("route", ROUTES)
def test_khazix_attack_bonus_once_per_combat_in_a_copy(route):
    """Kha'Zix, Mutating Horror: 'When I attack or defend, if an enemy unit is
    alone here, give me +2 [Might] this turn and gain 2 XP.' The combat opened,
    copied, opened again (a unit arrived): no second bonus (M2)."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    kz = unit("Kha'Zix Mutating Horror")
    bf.add_unit("A", kz)
    bf.add_unit("B", unit("lonely", 5))
    loop._open_combat(bf, "A")
    copied = _copy(loop, route)
    seen = []
    for game in (loop, copied):
        game._open_combat(game.gs.battlefields[0], "A")
        seen.append((_twin(game, kz).might, game.gs.xp_A))
    assert seen == [(6, 2), (6, 2)]


@pytest.mark.parametrize("route", ROUTES)
def test_only_a_new_arrival_becomes_an_attacker_in_a_copy(route):
    """A unit arriving in the combat is designated and its attack trigger
    fires; the ones designated before the copy don't fire again (design
    4.1.b). Two Kha'Zix Mutating Horror, the second arriving in the copy."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    kz = unit("Kha'Zix Mutating Horror")
    bf.add_unit("A", kz)
    bf.add_unit("B", unit("lonely", 9))
    loop._open_combat(bf, "A")
    copied = _copy(loop, route)
    arrival = unit("Kha'Zix Mutating Horror")
    copied.gs.battlefields[0].add_unit("A", arrival)
    copied._open_combat(copied.gs.battlefields[0], "A")
    assert (_twin(copied, kz).might, arrival.might, copied.gs.xp_A) == (6, 6, 4)
    assert copied._in_combat(arrival) and (kz.might, loop.gs.xp_A) == (6, 2)


@pytest.mark.parametrize("route", ROUTES)
def test_shadow_clone_banishes_once_per_combat_in_a_copy(route):
    """Shadow Clone: 'When I attack, you may banish a unit from your trash. If
    you do, give me [Assault 4] this turn.' Two units in the trash; opened,
    copied, opened again: one banished (M3)."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit("Shadow Clone"))
    bf.add_unit("B", unit("Wall", 9))
    a.trash = [UnitCard(name="F1"), UnitCard(name="F2")]
    loop._open_combat(bf, "A")
    copied = _copy(loop, route)
    banished = []
    for game in (loop, copied):
        game._open_combat(game.gs.battlefields[0], "A")
        banished.append([c.name for c in game.gs.A.banished])
    assert banished == [["F1"], ["F1"]]


@pytest.mark.parametrize("route", ROUTES)
def test_twilight_reveler_readies_once_per_combat_in_a_copy(route):
    """Twilight Reveler: 'When I attack, ready another friendly unit.' The
    unit readied is exhausted again in the combat; copied, opened again: it
    stays exhausted (M4)."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit("Twilight Reveler"))
    bf.add_unit("B", unit("Wall", 9))
    friend = unit("Friend", 2, ready=False)
    a.base_units.append(friend)
    loop._open_combat(bf, "A")
    assert friend.ready
    friend.ready = False
    copied = _copy(loop, route)
    ready = []
    for game in (loop, copied):
        game._open_combat(game.gs.battlefields[0], "A")
        ready.append(_twin(game, friend).ready)
    assert ready == [False, False]


@pytest.mark.parametrize("route", ROUTES)
def test_kennen_pays_to_stun_once_per_combat_in_a_copy(route):
    """Kennen, Keeper of Balance: 'When you play me or I attack, you may pay
    [2] to [Stun] a unit.' 8 Energy; opened (paid, stunned), copied, opened
    again: 6 Energy left (M5)."""
    loop, a, b = setup(active="A")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", unit("Kennen Keeper of Balance"))
    enemy = unit("Enemy", 3)
    bf.add_unit("B", enemy)
    a.energy = 8
    choices(loop, {"optional:stun_unit": lambda _l, o: o.index(True),
                   "target": lambda _l, o: next(i for i, u in enumerate(o)
                                                if getattr(getattr(u, "card", None), "name", None) == "Enemy")})
    loop._open_combat(bf, "A")
    assert enemy.stunned and a.energy == 6
    copied = _copy(loop, route)
    energy = []
    for game in (loop, copied):
        game._open_combat(game.gs.battlefields[0], "A")
        energy.append(game.gs.A.energy)
    assert energy == [6, 6]


# ------------------------------------------------- D68: conquer_return

@pytest.mark.parametrize("route", ROUTES)
def test_relentless_pursuit_runner_returns_after_conquering_in_a_copy(route):
    """Relentless Pursuit: 'Move a friendly unit. [...] This turn, that unit
    has "When I conquer, you may move me to my base."' Cast, copied: the
    runner conquers and goes back to base; a unit with the same name that
    wasn't moved isn't asked (M7; design 4.1.c)."""
    loop, a, b = setup(active="A")
    runner = unit("Runner", 2)
    a.base_units.append(runner)
    loop._resolve_card_effects(card("Relentless Pursuit"), loop.gs.battlefields[0], a, b)
    copied = _copy(loop, route)
    returned, asked = [], []
    for game in (loop, copied):
        log = _yes(game)
        mine = _twin(game, runner)
        bf = game._locate_unit(mine)[1]
        assert bf is not None
        bf.add_unit("A", unit("Runner", 2))                 # not moved by the spell
        game._fire_scoring_trigger("on_conquer", bf, "A")
        returned.append([u.card.name for u in game.gs.A.base_units])
        asked.append(sum(kind == "optional:return_to_base" for kind, _s, _o in log))
    assert returned == [["Runner"], ["Runner"]] and asked == [1, 1]
