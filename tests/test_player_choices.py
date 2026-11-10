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
    def unit(o):
        return o[-1] if isinstance(o, tuple) else o      # move choices offer (side, unit)
    return lambda options: next(o for o in options if getattr(getattr(unit(o), "card", None), "name", None) == name)


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


def test_the_assigner_orders_every_unit_while_damage_runs_short():
    """§467.2.c: the attacker assigns lethal unit by unit in the order they
    choose (only the first was asked, the rest were the engine's)."""
    from riftbound.core.combat import resolve_might_combat
    a_units = [UnitInPlay(card=UnitCard(name="Hitter", might=5))]
    b_units = [UnitInPlay(card=UnitCard(name=n, might=2)) for n in ("X", "Y", "Z")]
    asked = []

    def first(units, damage):
        asked.append(([u.card.name for u in units], damage))
        return next(u for u in units if u.card.name == ("Z" if len(units) == 3 else "X"))
    resolve_might_combat(a_units, b_units, attacker_side="A", first_b=first)
    assert asked == [(["X", "Y", "Z"], 5), (["X", "Y"], 3)]
    assert [u.card.name for u in b_units] == ["Y"]                # Z then X died


def test_extra_combat_damage_kills_through_a_ki_barrier():
    """Ki Barrier: 'Prevent the next 7 damage ... (Opponents can assign it
    extra combat damage to kill it.)'"""
    from riftbound.core.combat import resolve_might_combat
    loop, a, b = _setup()
    shielded = UnitInPlay(card=UnitCard(name="Shielded", might=2))
    shielded.damage_shield = 7
    a_units = [UnitInPlay(card=UnitCard(name="Hitter", might=9))]
    b_units = [shielded]
    resolve_might_combat(a_units, b_units, attacker_side="A",
                         take=lambda u, n: loop._take_damage(u, n, "combat"))
    assert not b_units


def test_when_you_choose_me_fires_as_the_spell_is_played():
    """A spell chooses as it goes on the chain (§355): Jae Medarda's 'When you
    choose me with a spell, draw 1' happens before the opponent can react, not
    when the spell resolves."""
    from riftbound.core.enums import Domain
    loop, a, b = _setup()
    a.energy = 9
    for d in Domain:
        a.add_power(d, 2)
    a.deck.cards = [UnitCard(name="Drawn", might=1)]
    jae = UnitInPlay(card=CARD_REGISTRY["Jae Medarda"].instantiate(), ready=True)
    a.base_units.append(jae)
    a.hand = [CARD_REGISTRY["Discipline"].instantiate()]
    hands_seen = []

    class Watcher:
        def __init__(self, player):
            self.player = player

        def decide_reaction(self, opponent, chain):
            hands_seen.append([c.name for c in a.hand])
            return ("PASS", None, None)
    b.agent = Watcher(b)
    loop._apply_action(a, ("SPELL", 0, 0))
    # Jae's ability went on the chain above the spell (§383.4.b.2): B could
    # answer it, then the spell once it had drawn (§340.4).
    assert hands_seen == [[], ["Drawn"]]
    assert [c.name for c in a.hand] == ["Drawn"] and jae.might == jae.card.might + 2   # once, +2 resolved


def test_a_spell_needs_a_gear_or_trash_card_to_choose():
    """§355.8 for gear and trash targets: Detonate 'Kill a gear' with no gear,
    Morbid Return 'Return a unit from your trash' with none, can't be played;
    by FLOW neither (Brittle Steel)."""
    from riftbound.core.cards import GearCard
    from riftbound.core.enums import Domain
    loop, a, b = _setup()
    a.energy = 9
    for d in Domain:
        a.add_power(d, 3)
    assert not loop._spell_has_targets(CARD_REGISTRY["Detonate"].instantiate(), "A", 0)
    b.base_gear.append(GearCard(name="Junk"))
    assert loop._spell_has_targets(CARD_REGISTRY["Detonate"].instantiate(), "A", 0)
    assert not loop._spell_has_targets(CARD_REGISTRY["Morbid Return"].instantiate(), "A", 0)
    a.trash.append(UnitCard(name="Fallen", might=2))
    assert loop._spell_has_targets(CARD_REGISTRY["Morbid Return"].instantiate(), "A", 0)


def _gravity_field(loop, side, bf_idx=0):
    from riftbound.core.battlefield import DeployedGear
    loop.gs.battlefields[bf_idx].gear_for(side).append(
        DeployedGear(card=CARD_REGISTRY["Gravity Field"].instantiate()))


def test_gravity_field_taxes_a_standard_move_once():
    """'Opponents must pay [1] [rune] to move one or more units to this
    battlefield': once for the units moving together; no tax, no move."""
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.enums import Domain
    from riftbound.core.legality import legal_actions
    loop, a, b = _setup()
    _gravity_field(loop, "B")
    a.base_units += [_unit("One", 2), _unit("Two", 2)]
    a.energy = 1
    moves = [ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A")
             if ga.kind == "MOVE" and ga.to_engine()[3] == 0]
    assert not moves                                           # no [rune] to pay
    a.add_power(Domain.FURY, 1)
    loop._apply_action(a, ("MOVE", 0, 2, 0))
    loop._apply_action(a, ("MOVE", 0, 2, 0))                   # joins the move: no second tax
    assert len(loop.gs.battlefields[0].units_A) == 2
    assert a.energy == 0 and not a.power_pool.get(Domain.FURY)


def test_gravity_field_is_paid_by_who_is_instructed_to_move():
    """FAQ: Charm moves an enemy unit to a battlefield with your opponent's
    Gravity Field: you pay. Your own Field doesn't tax you."""
    from riftbound.core.enums import Domain
    loop, a, b = _setup()
    _gravity_field(loop, "B", 1)
    enemy = _unit("Enemy", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    a.energy = 5
    a.add_power(Domain.CALM, 2)
    _picker(loop, {"destination": ("A", lambda o: loop.gs.battlefields[1])})
    _resolve(loop, a, "Charm")
    assert enemy in loop.gs.battlefields[1].units_B and a.energy == 4


def test_angler_wyrm_the_opponent_moves_a_unit_of_their_choice():
    """'[tap]: Choose an opponent. They must move a unit they control to my
    battlefield.'"""
    from riftbound.core.effects import REGISTRY
    loop, a, b = _setup()
    wyrm = UnitInPlay(card=CARD_REGISTRY["Angler Wyrm"].instantiate(), ready=True)
    loop.gs.battlefields[0].add_unit("A", wyrm)
    b.base_units += [_unit("Big", 6), _unit("Small", 1)]
    seen = _picker(loop, {"target": ("B", _named("Small"))})
    spec = CARD_REGISTRY["Angler Wyrm"].effects[0]
    ctx = EffectContext(loop, wyrm.card, a, b, loop.gs.battlefields[0])
    REGISTRY["move_unit"](ctx, spec.merged_params())
    assert any(kind.startswith("target") and side == "B" for kind, side in seen)
    assert [u.card.name for u in loop.gs.battlefields[0].units_B] == ["Small"]


def test_kayle_justified_is_empowered_up_to_three_times():
    """'I can be EMPOWERED up to three times. I have +2 [might] for each time
    I'm EMPOWERED. While I'm EMPOWERED three times, I have DEFLECT 3 and
    GANKING.' (§442.1.c.1)"""
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    loop, a, b = _setup()
    a.energy = 20
    kayle = UnitInPlay(card=CARD_REGISTRY["Kayle Justified"].instantiate(), ready=True)
    a.base_units.append(kayle)

    def empower():
        for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A"):
            if ga.kind == "ABILITY" and ga.label.endswith("(Kayle Justified)"):
                loop._apply_action(a, ga.to_engine())
                loop._recompute_passives()
                return True
        return False
    base = kayle.might
    for times in (1, 2, 3):
        assert empower()
        assert kayle.empower_times == times and kayle.might == base + 2 * times
    assert kayle.keyword_value("DEFLECT") == 3 and kayle.has_keyword("GANKING")
    assert not empower() and a.energy == 20 - 9
