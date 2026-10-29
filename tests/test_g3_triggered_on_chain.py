"""BACKLOG G3 "Abilities on the chain" (§383.3, §388, §334, §340.4), part 2:
triggered abilities. They resolved at once, so nobody could respond to one;
now each goes on the chain once the task that triggered it is done (HOT
FEPR), finalized there (a leading "you may" decided, a leading cost paid),
the turn player's first and each player's in the order they choose, its
choices declared; players may respond, and after each item resolves they
get priority again. Death from Below's reflexive "play this again" too."""

from __future__ import annotations

from riftbound.ai.coach import option_text
from riftbound.core.cards import UnitCard
from riftbound.core.state import PendingTrigger
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _battlefield, _play_spell, _setup, _unit
from test_g2_unleashed import _targets


class _Script:
    """An agent that answers the chain with `actions` in turn, then passes,
    noting what it saw there: (name, player, kind or None)."""

    def __init__(self, *actions):
        self.actions = list(actions)
        self.saw: list = []

    def decide_reaction(self, opponent, chain):
        self.saw.append([(it.card.name, it.player, it.ability and it.ability["kind"])
                         for it in chain])
        return self.actions.pop(0) if self.actions else ("PASS", None, None)

    def decide_showdown_action(self, opponent, bf_idx):
        return ("PASS", None, None)


def _hand(p, *names):
    p.hand = [CARD_REGISTRY[n].instantiate() for n in names]


def _rex_vs(loop, a, b):
    """A plays Riptide Rex ("When you play me, deal 6 to an enemy unit at a
    battlefield") with a 5 Might enemy at the first battlefield."""
    enemy = _unit("Plain", 5)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _hand(a, "Riptide Rex")
    return enemy


def test_a_play_effect_goes_on_the_chain_and_the_opponent_may_answer():
    loop, a, b = _setup()
    enemy = _rex_vs(loop, a, b)
    b.agent = _Script()
    loop._apply_action(a, ("UNIT", 0, None))
    assert b.agent.saw[0] == [("Riptide Rex", "A", "triggered")]
    assert enemy not in loop.gs.battlefields[0].units_B and not loop.gs.chain


def test_not_so_fast_counters_a_triggered_ability_choosing_my_unit():
    """'Counter an enemy spell or ability that chooses a friendly unit.'"""
    loop, a, b = _setup()
    enemy = _rex_vs(loop, a, b)
    _hand(b, "Not So Fast")
    b.agent = _Script(("SPELL", 0, 0))
    loop._apply_action(a, ("UNIT", 0, None))
    assert enemy in loop.gs.battlefields[0].units_B and enemy.damage == 0
    assert [u.card.name for u in a.base_units] == ["Riptide Rex"]      # the unit stays
    assert [c.name for c in b.trash] == ["Not So Fast"] and not loop.gs.chain


def test_a_play_effect_sees_the_additional_cost_its_play_paid():
    """'You may pay [1][fury] as an additional cost to play me. When you play
    me, if you paid the additional cost, deal 2 to a unit at a battlefield.'
    The ability waits for the play to end (§383.4.a.2); the payment is still
    its."""
    loop, a, b = _setup()
    enemy = _unit("Plain", 2)
    loop.gs.battlefields[0].add_unit("B", enemy)
    _hand(a, "Blast Corps Cadet")
    b.agent = _Script()
    loop._apply_action(a, ("UNIT", 0, None))
    assert b.agent.saw and b.agent.saw[0][0][0] == "Blast Corps Cadet"
    assert enemy not in loop.gs.battlefields[0].units_B


def test_a_leading_you_may_is_decided_as_it_goes_on_the_chain():
    """'When I conquer, you may kill a gear' (Noxian Demolitionist): declined as
    it is finalized, it never goes on the chain (§383.3.a.2)."""
    loop, a, b = _setup()
    demo = _unit("Noxian Demolitionist")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", demo)
    b.base_gear.append(CARD_REGISTRY["Long Sword"].instantiate())
    asked = []

    def chooser(_loop, kind, side, options, default, source):
        if kind.startswith("optional"):
            asked.append(kind)
            return options.index(False)
        return None
    loop.chooser = chooser
    b.agent = _Script()
    loop._fire_scoring_trigger("on_conquer", bf, "A")
    assert asked and b.agent.saw == [] and len(b.base_gear) == 1


def _sentries(loop, *sides):
    """A Watchful Sentry ('DEATHKNELL: Draw 1') per side at the first
    battlefield, each player with a card to draw."""
    out = []
    for side in sides:
        unit = _unit("Watchful Sentry")
        loop.gs.battlefields[0].add_unit(side, unit)
        out.append((unit, side))
        loop.gs.get_player(side).deck.cards.append(UnitCard(name=f"Draw{side}{len(out)}", might=1))
    return out


def _kill(loop, dead):
    bf = loop.gs.battlefields[0]
    for unit, side in dead:
        bf.remove_unit(side, unit)
    loop._route_deaths(dead, bf)


def test_deaths_at_once_put_their_deathknells_on_the_chain_together():
    """They trigger in one task: both go on the chain before either resolves
    (HOT FEPR, §334), and after the first resolves players get priority again
    (§340.4)."""
    loop, a, b = _setup()
    dead = _sentries(loop, "A", "A")
    b.agent = _Script()
    _kill(loop, dead)
    assert b.agent.saw[0] == [("Watchful Sentry", "A", "triggered")] * 2
    assert b.agent.saw[1] == [("Watchful Sentry", "A", "triggered")]
    assert len(a.hand) == 2 and not loop.gs.chain


def test_the_turn_players_triggers_go_on_the_chain_first():
    """§383.3.d.1: A (the turn player) puts theirs first, so B's resolves
    first."""
    loop, a, b = _setup()
    dead = _sentries(loop, "A", "B")
    order = []
    a.agent = _Script()
    a.agent.decide_reaction = lambda _o, chain: order.append(
        [it.player for it in chain]) or ("PASS", None, None)
    _kill(loop, dead)
    assert order[0] == ["A", "B"]
    assert len(a.hand) == 1 and len(b.hand) == 1


def test_a_player_orders_their_simultaneous_triggers():
    """'trigger_order': the one picked first resolves first; the baseline
    keeps the order they triggered in."""
    loop, a, b = _setup()
    dead = _sentries(loop, "A")
    poro = _unit("Loyal Poro")          # 'If I didn't die alone, draw 1.'
    loop.gs.battlefields[0].add_unit("A", poro)
    a.deck.cards.append(UnitCard(name="Draw2", might=1))
    dead.append((poro, "A"))
    asked = []

    def chooser(_loop, kind, side, options, default, source):
        if kind == "trigger_order":
            asked.append([option_text(_loop.gs, side, o) for o in options])
            return next((i for i, o in enumerate(options) if o.card.name == "Loyal Poro"), None)
        return None
    loop.chooser = chooser
    b.agent = _Script()
    _kill(loop, dead)
    assert asked[0] == ["abilità di Watchful Sentry", "abilità di Loyal Poro"]
    assert [it[0] for it in b.agent.saw[0]] == ["Watchful Sentry", "Loyal Poro"]
    assert len(a.hand) == 2


def test_a_spells_kills_trigger_after_it_has_resolved():
    """The spell's resolution is the task: its deathknell goes on the chain
    once it is done, then players may respond."""
    loop, a, b = _setup()
    sentry = _unit("Watchful Sentry")
    loop.gs.battlefields[0].add_unit("B", sentry)
    b.deck.cards.append(UnitCard(name="Drawn", might=1))
    b.agent = _Script()
    loop.chooser = _targets("Watchful Sentry")
    _play_spell(loop, a, "Death from Below")
    # B answered the spell, then its own deathknell, then the reflexive
    # "play this again" (no unit left: A doesn't take it).
    assert b.agent.saw[0] == [("Death from Below", "A", None)]
    assert b.agent.saw[1] == [("Watchful Sentry", "B", "triggered")]
    assert [c.name for c in b.hand] == ["Drawn"]


def test_death_from_below_plays_again_through_the_chain():
    """§388.4: its reflexive trigger goes on the chain ("you may" taken as it
    is finalized); as it resolves the spell is played again."""
    loop, a, b = _setup()
    loop.gs.battlefields[0].add_unit("B", _unit("Small", 2))
    loop.gs.battlefields[1].add_unit("B", _unit("Next", 4))
    loop.chooser = _targets("Small", "Next")
    b.agent = _Script()
    _play_spell(loop, a, "Death from Below")
    assert [("Death from Below", "A", "reflexive")] in b.agent.saw
    assert sorted(c.name for c in b.trash) == ["Next", "Small"]
    assert [c.name for c in a.trash] == ["Death from Below"]


def test_an_ability_that_adds_resolves_at_once():
    """'When combat starts here, the attacker and defender each ADD [1]'
    (Threshold of the Gray): never on the chain (§337.2)."""
    loop, a, b = _setup()
    _battlefield(loop, 0, "Threshold of the Gray")
    bf = loop.gs.battlefields[0]
    bf.add_unit("A", _unit("Atk", 2))
    bf.add_unit("B", _unit("Def", 2))
    a.energy = b.energy = 0
    b.agent = _Script()
    loop._open_combat(bf, "A")
    assert a.energy == 1 and b.energy == 1 and b.agent.saw == []


def test_a_triggered_ability_resolves_without_its_source():
    """Its source killed in response, the ability still resolves (§383.2.a.1
    example)."""
    loop, a, b = _setup()
    enemy = _rex_vs(loop, a, b)
    killed = []

    def answer(_o, chain):
        rex = a.base_units[0]
        if not killed:
            killed.append(rex)
            a.base_units.remove(rex)
            a.trash.append(rex.card)
        return ("PASS", None, None)
    b.agent = _Script()
    b.agent.decide_reaction = answer
    loop._apply_action(a, ("UNIT", 0, None))
    assert killed and enemy not in loop.gs.battlefields[0].units_B


def test_the_coach_names_a_pending_trigger():
    loop, a, b = _setup()
    p = PendingTrigger(card=CARD_REGISTRY["Watchful Sentry"].instantiate(), trigger="on_death",
                       side="A", bf=loop.gs.battlefields[0], specs=[])
    assert option_text(loop.gs, "A", p) == "abilità di Watchful Sentry"
