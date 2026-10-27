"""Cards fixed after the first coached games (2026-10-26), each checked against
its card image: EMPOWER costs (Steel Paws is [7], the source text said [1]),
EMPOWER abilities that were missing or never offered, "When I become
EMPOWERED" (a trigger the engine didn't have), and activated abilities whose
cost was missing so the engine never offered them."""

from __future__ import annotations

import random

from riftbound.core.battlefield import Battlefield
from riftbound.core.cards import SpellCard, UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.decisions import DecisionPoint
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState
from riftbound.registry.cards_registry import CARD_REGISTRY


def _setup(*names, energy=0):
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    gs = GameState(rng=random.Random(1), A=a, B=b, battlefields=[Battlefield(), Battlefield()])
    gs.active = "A"
    loop = GameLoop(gs)
    units = [UnitInPlay(card=CARD_REGISTRY[n].instantiate(), ready=True) for n in names]
    a.base_units.extend(units)
    a.energy = energy
    loop._recompute_passives()
    return loop, a, units


def _use(loop, name) -> bool:
    """Use `name`'s first offered ability; False if none is offered."""
    for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A"):
        if ga.kind == "ABILITY" and ga.label.endswith(f"({name})"):
            loop._apply_action(loop.gs.A, ga.to_engine())
            loop._recompute_passives()
            return True
    return False


def test_steel_paws_empowers_for_seven():
    loop, a, (paws,) = _setup("Steel Paws", energy=6)
    assert not _use(loop, "Steel Paws")
    a.energy = 7
    assert _use(loop, "Steel Paws")
    assert a.energy == 0 and paws.empowered and paws.might == 7


def test_apprentice_mage_predicts_when_it_becomes_empowered():
    loop, a, (mage,) = _setup("Apprentice Mage", energy=2)
    # Top of the deck = end of the list; PREDICT's baseline puts the mightiest on top.
    a.deck.cards = [UnitCard(name=n, might=m) for n, m in (("Z", 1), ("Big", 3), ("Top", 1))]
    assert _use(loop, "Apprentice Mage")
    assert mage.empowered and [c.name for c in a.deck.cards] == ["Z", "Top", "Big"]


def test_mel_defiant_soul_discards_a_spell_and_banishes_a_small_enemy_at_a_battlefield():
    loop, a, (mel,) = _setup("Mel Defiant Soul")
    a.hand = [UnitCard(name="Keep", might=1), SpellCard(name="Spare", cost_energy=1)]
    small = UnitInPlay(card=UnitCard(name="Small", might=3), ready=True)
    loop.gs.battlefields[0].add_unit("B", small)
    loop.gs.B.base_units.append(UnitInPlay(card=UnitCard(name="AtHome", might=1), ready=True))
    assert _use(loop, "Mel Defiant Soul")
    assert [c.name for c in a.hand] == ["Keep"] and mel.empowered
    assert not loop.gs.battlefields[0].units_B and [c.name for c in loop.gs.B.banished] == ["Small"]
    assert [u.card.name for u in loop.gs.B.base_units] == ["AtHome"]       # not at a battlefield


def test_escaped_grayback_kills_another_friendly_unit_to_empower():
    loop, a, (grayback,) = _setup("Escaped Grayback")
    assert not _use(loop, "Escaped Grayback")                 # nothing else to kill
    a.base_units.append(UnitInPlay(card=UnitCard(name="Friend", might=1), ready=True))
    assert _use(loop, "Escaped Grayback")
    assert grayback.empowered and [u.card.name for u in a.base_units] == ["Escaped Grayback"]


def test_punching_poro_empowers_by_discarding():
    loop, a, (poro,) = _setup("Punching Poro")
    assert not _use(loop, "Punching Poro")                    # empty hand
    a.hand = [UnitCard(name="Card", might=1)]
    assert _use(loop, "Punching Poro")
    assert not a.hand and poro.empowered


def test_jinx_rebel_readies_when_you_discard():
    loop, a, (jinx,) = _setup("Jinx Rebel")
    jinx.ready = False
    might = jinx.might
    a.hand = [UnitCard(name="Card", might=1)]
    loop._discard(a, a.hand[0])
    loop._recompute_passives()
    assert jinx.ready and jinx.might == might + 1


def test_fretful_feline_grows_when_it_becomes_ready():
    loop, a, (cat,) = _setup("Fretful Feline")
    cat.ready = False
    might = cat.might
    loop._ready_active_units("A")
    loop._recompute_passives()
    assert cat.ready and cat.might == might + 2


def test_sett_brawler_spends_its_buff_for_four():
    loop, a, (sett,) = _setup("Sett Brawler")
    assert not _use(loop, "Sett Brawler")                     # no buff yet
    sett.might_counters = 1
    loop._recompute_passives()
    might = sett.might
    assert _use(loop, "Sett Brawler")
    assert sett.might_counters == 0 and sett.might == might - 1 + 4


def test_lux_crownguard_exhausts_for_two_energy_for_spells():
    loop, a, (lux,) = _setup("Lux Crownguard")
    assert _use(loop, "Lux Crownguard")
    assert not lux.ready and a.earmarked_energy_spell == 2


def test_ruthless_strike_deals_five_to_one_unit_when_kicked():
    """'Deal 3 to a unit. If you paid the additional cost, deal 5 to it instead':
    one target, not 3 to one unit and 2 more to a second one."""
    from riftbound.core.enums import Domain
    for kick, dealt in ((True, 5), (False, 3)):
        loop, a, _ = _setup(energy=10)
        for d in Domain:
            a.add_power(d, 3)
        a.hand = [CARD_REGISTRY["Ruthless Strike"].instantiate(), UnitCard(name="Fodder", might=1)]
        big = UnitInPlay(card=UnitCard(name="Big", might=8), ready=True)
        small = UnitInPlay(card=UnitCard(name="Small", might=3), ready=True)
        loop.gs.battlefields[0].add_unit("B", big)
        loop.gs.battlefields[0].add_unit("B", small)
        asked = []

        def chooser(_loop, kind, side, options, default, source, kick=kick):
            asked.append(kind)
            if kind.startswith("optional:"):
                return options.index(kick)
            if kind.startswith("target"):
                # Declared as it goes on the chain: on a copy of the game.
                return next(i for i, o in enumerate(options) if o.card.name == "Big")
            return None
        loop.chooser = chooser
        loop._apply_action(a, ("SPELL", 0, 0))
        assert sum(k.startswith("target") for k in asked) == 1
        assert big.damage == dealt and small.damage == 0
        assert [c.name for c in a.hand] == ([] if kick else ["Fodder"])


def test_shen_cards_need_exactly_one_other_unit():
    """Shen Leader of the Kinkou Order and Disciple of Shen say "exactly one
    other unit you control here": a third unit turns them off (they read
    "two or more")."""
    for others, point, shield in ((1, 1, True), (2, 0, False)):
        loop, a, _ = _setup()
        bf0 = loop.gs.battlefields[0]
        shen = UnitInPlay(card=CARD_REGISTRY["Shen Leader of the Kinkou Order"].instantiate())
        bf0.add_unit("A", shen)
        disciple = UnitInPlay(card=CARD_REGISTRY["Disciple of Shen"].instantiate())
        bf1 = loop.gs.battlefields[1]
        bf1.add_unit("A", disciple)
        for i in range(others):
            bf0.add_unit("A", UnitInPlay(card=UnitCard(name=f"Pal{i}", might=1)))
            bf1.add_unit("A", UnitInPlay(card=UnitCard(name=f"Mate{i}", might=1)))
        loop._recompute_passives()
        assert disciple.has_keyword("SHIELD 3") == shield
        loop._fire_scoring_trigger("on_hold", bf0, "A")
        assert loop.gs.points_A == point


def test_shadow_fiend_empower_pays_fury_not_any_power():
    """EMPOWER [2] [fury]: the Power must be Fury (the engine took any domain,
    so a Chaos rune was recycled)."""
    from riftbound.core.enums import Domain
    loop, a, (fiend,) = _setup("Shadow Fiend", energy=5)
    a.add_power(Domain.CHAOS, 3)
    assert not _use(loop, "Shadow Fiend")
    a.add_power(Domain.FURY, 1)
    assert _use(loop, "Shadow Fiend")
    assert fiend.empowered and a.energy == 3
    assert a.power_pool.get(Domain.FURY, 0) == 0 and a.power_pool[Domain.CHAOS] == 3


def test_additional_costs_pay_their_domain():
    """Blast Corps Cadet: "you may pay [1] [fury] as an additional cost"."""
    from riftbound.core.enums import Domain
    loop, a, _ = _setup(energy=1)
    a.add_power(Domain.CHAOS, 2)
    cadet = CARD_REGISTRY["Blast Corps Cadet"].instantiate()
    ac = next(e.additional_cost for e in CARD_REGISTRY["Blast Corps Cadet"].effects
              if e.additional_cost)
    assert not loop._pay_one_additional_cost(cadet, a, ac, check_only=True)
    a.add_power(Domain.FURY, 1)
    assert loop._pay_one_additional_cost(cadet, a, ac)
    assert a.energy == 0 and a.power_pool.get(Domain.FURY, 0) == 0


def test_renata_glasc_scores_for_four_mind_at_a_battlefield():
    """Renata Glasc, Mastermind: "[4] [mind] [mind] [mind] [mind], [tap]: Score
    1 point" (the ability was missing)."""
    from riftbound.core.enums import Domain
    loop, a, _ = _setup(energy=5)
    renata = UnitInPlay(card=CARD_REGISTRY["Renata Glasc Mastermind"].instantiate(), ready=True)
    loop.gs.battlefields[0].add_unit("A", renata)

    def abilities():
        return [ga for ga in legal_actions(loop, DecisionPoint.TURN_ACTION, "A") if ga.kind == "ABILITY"]
    a.add_power(Domain.MIND, 3)
    assert len(abilities()) == 1          # only "[1] [mind]: Draw 1"
    a.add_power(Domain.MIND, 1)
    score = abilities()[1]
    loop._apply_action(a, score.to_engine())
    assert loop.gs.points_A == 1 and not renata.ready


def test_blade_twirler_burns_the_player_you_choose():
    """ "The first time I move each turn, choose a player. They BURN 1": the
    opponent by default, yourself if you pick it (it always burned the
    opponent)."""
    for pick_me in (False, True):
        loop, a, (twirler,) = _setup("Blade Twirler")
        a.deck.cards = [UnitCard(name="Mine")]
        loop.gs.B.deck.cards = [UnitCard(name="Theirs")]
        asked = []

        def chooser(_loop, kind, side, options, default, source, pick_me=pick_me):
            if kind == "player":
                asked.append(options[default] is _loop.gs.B)
                return options.index(_loop.gs.A if pick_me else _loop.gs.B)
            return None
        loop.chooser = chooser
        loop._apply_action(a, ("MOVE", 0, 2, 0))
        assert asked == [True]
        burned = a if pick_me else loop.gs.B
        assert [c.name for c in burned.trash] == ["Mine" if pick_me else "Theirs"]


def test_the_final_point_by_conquer_needs_every_battlefield_scored():
    """§473.1.b: at 7 points a conquer wins only if the other battlefield was
    scored this turn too; otherwise its player draws a card instead."""
    for other_scored, points, hand in ((False, 7, 1), (True, 8, 0)):
        loop, a, _ = _setup()
        a.deck.cards = [UnitCard(name="Top")]
        loop.gs.points_A = 7
        bf0, bf1 = loop.gs.battlefields
        if other_scored:
            bf1.mark_scored("A")
        assert loop._gain_points("A", 1, "conquer", bf0) == points - 7
        assert loop.gs.points_A == points and len(a.hand) == hand
    loop, a, _ = _setup()
    loop.gs.points_A = 7
    assert loop._gain_points("A", 1, "hold", loop.gs.battlefields[0]) == 1   # holding is free


def test_attack_triggers_open_the_combat_showdown_so_players_can_still_act():
    """§466.2: a combat opens with its showdown; attack / defend triggers come
    first, then both players act, then damage. Shadow Clone banishes a unit
    from the trash, Zed Master of Shadows becomes EMPOWERED, and its ACTION
    is offered before damage (it fired after the showdown, just before
    damage)."""
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    loop, a, _ = _setup()
    gs = loop.gs
    gs.legend_A = CARD_REGISTRY["Zed Master of Shadows"].instantiate()
    gs.legend_unit_A = UnitInPlay(card=gs.legend_A, ready=True)
    a.trash = [CARD_REGISTRY["Punching Poro"].instantiate()]
    a.hand = [UnitCard(name="Spare")]
    clone = UnitInPlay(card=CARD_REGISTRY["Shadow Clone"].instantiate(), ready=True)
    clone.is_token = True
    gs.battlefields[0].add_unit("A", clone)
    gs.battlefields[0].add_unit("B", UnitInPlay(card=UnitCard(name="Wall", might=3)))
    seen = []

    class Agent:
        def __init__(self, side):
            self.side = side

        def decide_showdown_action(self, opponent, bf_idx):
            legal = legal_actions(loop, DecisionPoint.SHOWDOWN_ACTION, self.side)
            if self.side == "A":
                seen.append(([c.name for c in a.banished], [ga.label for ga in legal]))
            return ("PASS", None, None)
    a.agent, gs.B.agent = Agent("A"), Agent("B")
    loop._run_showdown(0, "A")
    banished, labels = seen[0]
    assert banished == ["Punching Poro"]                    # the trigger came first
    assert any("Zed Master of Shadows" in lbl for lbl in labels)
    assert gs.battlefields[0].units_A == [clone] and not gs.battlefields[0].units_B


def test_morgana_vindictive_doubles_the_damage_marked_on_a_unit():
    """ "When you play me, deal damage to a unit equal to the damage marked on
    it" (it dealt 0: the spec had no amount)."""
    loop, a, _ = _setup()
    hurt = UnitInPlay(card=UnitCard(name="Hurt", might=5))
    hurt.damage = 3
    fresh = UnitInPlay(card=UnitCard(name="Fresh", might=2))
    loop.gs.battlefields[0].add_unit("B", fresh)
    loop.gs.battlefields[0].add_unit("B", hurt)
    morgana = CARD_REGISTRY["Morgana Vindictive"].instantiate()
    loop._resolve_triggered_effects(morgana, "on_play", loop.gs.battlefields[0], a, loop.gs.B,
                                    context_extra={"battlefield": loop.gs.battlefields[0]})
    assert hurt not in loop.gs.battlefields[0].units_B          # 3 more: dead
    assert fresh in loop.gs.battlefields[0].units_B and fresh.damage == 0


def test_a_unit_anywhere_and_the_same_unit_for_it():
    """Perfect Execution "Ready a unit and give it ASSAULT 3": a unit in base
    can be chosen (spells only saw their battlefield's units), and one choice
    covers both effects (each asked its own target)."""
    from riftbound.core.enums import Domain
    loop, a, _ = _setup(energy=9)
    a.add_power(Domain.FURY, 2)
    zed = UnitInPlay(card=UnitCard(name="Zed", might=4), ready=True)
    a.base_units.append(zed)
    loop.gs.battlefields[0].add_unit("B", UnitInPlay(card=UnitCard(name="Morgana", might=5)))
    a.hand = [CARD_REGISTRY["Perfect Execution"].instantiate()]
    asked = []

    def chooser(_loop, kind, side, options, default, source):
        asked.append(kind)
        return options.index(zed) if zed in options else None
    loop.chooser = chooser
    loop._apply_action(a, ("SPELL", 0, 0))
    assert [k for k in asked if k.startswith("target")] == ["target:ready_unit"]
    assert zed.keyword_value("ASSAULT") == 3


def test_showstopper_buffs_a_unit_in_base_then_moves_it():
    loop, a, _ = _setup(energy=9)
    poro = UnitInPlay(card=UnitCard(name="Poro", might=2))
    a.base_units.append(poro)
    loop.gs.battlefields[1].add_unit("A", UnitInPlay(card=UnitCard(name="Elsewhere", might=1)))
    card = CARD_REGISTRY["Showstopper"].instantiate()
    loop._resolve_card_effects(card, loop.gs.battlefields[1], a, loop.gs.B)
    assert poro.might_counters == 1 and poro not in a.base_units


def test_an_ability_timing_is_not_a_card_keyword():
    """Zed Without a Sound: "ACTION [1] [Chaos]: Move me and a Shadow Clone you
    control to each other's locations" is an ability's timing; the unit itself
    isn't played in showdowns (it was offered there). The ability swaps."""
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.enums import Domain
    from riftbound.core.legality import legal_actions
    zed_card = CARD_REGISTRY["Zed Without a Sound"].instantiate()
    assert not zed_card.has_keyword("ACTION")
    loop, a, _ = _setup(energy=9)
    a.add_power(Domain.CHAOS, 2)
    loop.gs.showdown_active, loop.gs.showdown_bf_idx = True, 0
    a.hand = [zed_card]
    assert all(ga.kind != "UNIT" for ga in legal_actions(loop, DecisionPoint.SHOWDOWN_ACTION, "A"))
    loop.gs.showdown_active, loop.gs.showdown_bf_idx = False, None
    zed = UnitInPlay(card=CARD_REGISTRY["Zed Without a Sound"].instantiate(), ready=True)
    a.base_units.append(zed)
    clone = UnitInPlay(card=CARD_REGISTRY["Shadow Clone"].instantiate(), ready=True)
    clone.is_token = True
    loop.gs.battlefields[1].add_unit("A", clone)
    assert _use(loop, "Zed Without a Sound")
    assert zed in loop.gs.battlefields[1].units_A and clone in a.base_units
    assert a.energy == 8 and a.power_pool.get(Domain.CHAOS, 0) == 1


def test_wind_and_ghosts_banishes_a_small_unit_and_returns_a_big_one():
    """It banished a card from the caster's own trash (banish_card is the zone
    effect) instead of a unit at a battlefield."""
    for might, banished in ((3, True), (5, False)):
        loop, a, _ = _setup()
        a.trash = [UnitCard(name="Mine")]
        target = UnitInPlay(card=UnitCard(name="Target", might=might))
        loop.gs.battlefields[1].add_unit("B", target)
        card = CARD_REGISTRY["Wind and Ghosts"].instantiate()
        loop._resolve_card_effects(card, loop.gs.battlefields[0], a, loop.gs.B)
        assert not loop.gs.battlefields[1].units_B and [c.name for c in a.trash] == ["Mine"]
        assert ([c.name for c in loop.gs.B.banished] == ["Target"]) == banished
        assert ([c.name for c in loop.gs.B.hand] == ["Target"]) == (not banished)


def test_return_and_kill_reach_a_unit_in_base():
    """recall_unit / kill_unit only looked at the effect's battlefield: a unit
    "anywhere" (Retreat: "Return a friendly unit to its owner's hand") stayed."""
    loop, a, _ = _setup()
    mine = UnitInPlay(card=UnitCard(name="Mine", might=2))
    a.base_units.append(mine)
    loop._resolve_card_effects(CARD_REGISTRY["Retreat"].instantiate(), loop.gs.battlefields[0], a, loop.gs.B)
    assert mine not in a.base_units and [c.name for c in a.hand] == ["Mine"]
    theirs = UnitInPlay(card=UnitCard(name="Theirs", might=2))
    loop.gs.B.base_units.append(theirs)
    loop._resolve_card_effects(CARD_REGISTRY["Vengeance"].instantiate(), loop.gs.battlefields[0], a, loop.gs.B)
    assert theirs not in loop.gs.B.base_units and [c.name for c in loop.gs.B.trash] == ["Theirs"]


def test_a_moved_unit_is_the_one_chosen():
    """Twilight Step "Move a unit with 3 [might] or less": the coach chose their
    own unit in base; the destination went by the first candidate (an enemy:
    "to base"), the chosen unit was already there, and the enemy moved instead."""
    from riftbound.core.enums import Domain
    loop, a, _ = _setup(energy=5)
    a.add_power(Domain.CHAOS, 2)
    mine = UnitInPlay(card=UnitCard(name="Reveler", might=3), ready=True)
    a.base_units.append(mine)
    theirs = UnitInPlay(card=UnitCard(name="Merchant", might=2))
    loop.gs.battlefields[0].add_unit("B", theirs)
    a.hand = [CARD_REGISTRY["Twilight Step"].instantiate()]

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("target"):
            return next(i for i, o in enumerate(options) if (o[1] if isinstance(o, tuple) else o) is mine)
        return None
    loop.chooser = chooser
    loop._apply_action(a, ("SPELL", 0, 0))
    assert mine not in a.base_units and theirs in loop.gs.battlefields[0].units_B
