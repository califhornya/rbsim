"""Choices the rules give a player that handlers used to make on their own
(BACKLOG B: "handlers that pick a unit without loop.choose"): each now goes
through GameLoop.choose, the old pick as the baseline, so the coach, the
search and the declared choices of a spell all see it."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup():
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    return GameLoop(gs), a, b


def _unit(name, might):
    return UnitInPlay(card=UnitCard(name=name, might=might), ready=True)


def _picker(loop, picks):
    """Answer choices by kind prefix: picks = {prefix: (side, f(options) -> option)};
    records every (kind, side)."""
    seen = []

    def chooser(_loop, kind, side, options, default, source):
        seen.append((kind, side))
        for prefix, (who, f) in picks.items():
            if kind.startswith(prefix) and side == who:
                choice = f(options)
                return next(i for i, o in enumerate(options) if o is choice or o == choice)
        return None
    loop.chooser = chooser
    return seen


def _resolve(loop, a, name, bf=0):
    loop._resolve_card_effects(CARD_REGISTRY[name].instantiate(), loop.gs.battlefields[bf], a, loop.gs.B)


def _named(name):
    return lambda options: next(o for o in options if getattr(getattr(o, "card", None), "name", None) == name)


def test_convergent_mutation_lets_the_player_pick_both_units():
    """'Choose a friendly unit. This turn, increase its Might to the Might of
    another friendly unit.'"""
    loop, a, b = _setup()
    for name, might in (("Low", 1), ("Mid", 3), ("Top", 6)):
        a.base_units.append(_unit(name, might))
    _picker(loop, {"target:match_might:other": ("A", _named("Mid")),
                   "target:match_might": ("A", _named("Low"))})
    _resolve(loop, a, "Convergent Mutation")
    assert [u.might for u in a.base_units] == [3, 3, 6]


def test_keepers_verdict_owner_chooses_top_or_bottom():
    """'Choose an enemy unit at a battlefield. Its owner places it on the top or
    bottom of their Main Deck.'"""
    loop, a, b = _setup()
    b.deck.cards = [UnitCard(name="Old", might=1)]
    loop.gs.battlefields[0].add_unit("B", _unit("Victim", 4))
    seen = _picker(loop, {"mode:tuck_unit": ("B", lambda o: "deck_bottom")})
    _resolve(loop, a, "Keeper's Verdict")
    assert ("mode:tuck_unit", "B") in seen
    assert [c.name for c in b.deck.cards] == ["Victim", "Old"]        # bottom = index 0


def test_shakedown_controller_chooses_damage_or_draw():
    """'Choose an enemy unit. Deal 6 to it unless its controller has you draw 2.'"""
    for let_draw in (True, False):
        loop, a, b = _setup()
        a.deck.cards = [UnitCard(name=f"C{i}", might=1) for i in range(2)]
        big = _unit("Big", 9)
        loop.gs.battlefields[0].add_unit("B", big)
        _picker(loop, {"optional:damage_unless_draw": ("B", lambda o: let_draw)})
        _resolve(loop, a, "Shakedown")
        assert (len(a.hand) == 2) == let_draw and (big.damage == 6) == (not let_draw)


def test_glowstone_player_chooses_who_gets_it():
    """'Choose a player. They gain control of this and recall it.'"""
    loop, a, b = _setup()
    stone = CARD_REGISTRY["Glowstone"].instantiate()
    a.base_gear.append(stone)
    _picker(loop, {"player": ("A", lambda o: a)})
    ctx = EffectContext(loop, stone, a, b, loop.gs.battlefields[0])
    from riftbound.core.effects import REGISTRY
    REGISTRY["give_this_to_opponent"](ctx, {})
    assert stone in a.base_gear and stone not in b.base_gear


def test_stare_down_player_picks_the_unit_and_the_battlefield():
    """'Choose a friendly unit and a battlefield. Move all enemy units at that
    battlefield with less Might than the chosen unit to their base.'"""
    loop, a, b = _setup()
    a.base_units.append(_unit("Big", 5))
    a.base_units.append(_unit("Small", 2))
    left, right = _unit("Left", 1), _unit("Right", 4)
    loop.gs.battlefields[0].add_unit("B", left)
    loop.gs.battlefields[1].add_unit("B", right)
    _picker(loop, {"target:stare_down": ("A", _named("Small")),
                   "battlefield:stare_down": ("A", lambda o: loop.gs.battlefields[0])})
    _resolve(loop, a, "Stare Down")
    assert left in b.base_units and right in loop.gs.battlefields[1].units_B


def test_fox_fire_player_picks_which_units_die():
    """'Kill any number of units at a battlefield with total Might 4 or less.'"""
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    keep, kill = _unit("Keep", 2), _unit("Kill", 2)
    bf.add_unit("B", keep)
    bf.add_unit("B", kill)
    _picker(loop, {"battlefield:kill_total": ("A", lambda o: bf)})
    loop.chooser_inner = loop.chooser

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("optional:kill_total"):
            return options.index(source is kill.card)
        return loop.chooser_inner(_loop, kind, side, options, default, source)
    loop.chooser = chooser
    _resolve(loop, a, "Fox-Fire")
    assert keep in bf.units_B and kill not in bf.units_B


def test_a_recall_changes_nothing_about_the_unit():
    """§460: 'Recalls do not affect the state of the Permanent being recalled'
    (damage, exhausted, buffs). Possession takes control and recalls; only
    Conscription says 'exhaust it'."""
    for card, exhausted in (("Possession", False), ("Conscription", True)):
        loop, a, b = _setup()
        enemy = _unit("Enemy", 2)                          # 3 with its buff: Conscription's cap
        enemy.damage, enemy.might_counters = 1, 1
        loop.gs.battlefields[0].add_unit("B", enemy)
        _resolve(loop, a, card)
        assert enemy in a.base_units
        assert enemy.damage == 1 and enemy.might_counters == 1 and enemy.ready == (not exhausted)


def test_attackers_recalled_after_combat_keep_their_buff_and_status():
    loop, a, b = _setup()
    bf = loop.gs.battlefields[0]
    attacker = _unit("Attacker", 2)
    attacker.might_counters = 1
    attacker.ready = False
    wall = _unit("Wall", 9)
    wall.stunned = True
    bf.add_unit("A", attacker)
    bf.add_unit("B", wall)
    bf.contested_this_turn = True
    loop._phase_combat_and_conquer_single(0, "A")
    assert attacker in a.base_units and attacker.might_counters == 1 and not attacker.ready
