"""BACKLOG G3 "Abilities on the chain" (§377.3, §337.2), part 1: activated
abilities. They resolved at once, so nobody could respond to one; now each
goes on the chain with its choices declared, players may react (and Not So
Fast / Repulse may counter it), and it resolves once they pass. An ability
that Adds resources still resolves at once."""

from __future__ import annotations

from riftbound.ai.coach import option_text
from riftbound.core.battlefield import DeployedGear
from riftbound.core.cards import SpellCard
from riftbound.core.enums import Domain
from riftbound.core.state import ChainItem
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _pick, _setup, _unit
from test_corpus_proving_grounds import _legend
from test_corpus_vendetta import _ability


class _Script:
    """An agent that answers the chain with `actions` in turn, then passes,
    noting what it saw there."""

    def __init__(self, *actions):
        self.actions = list(actions)
        self.saw: list = []

    def decide_reaction(self, opponent, chain):
        self.saw.append([(it.card.name, it.ability is not None) for it in chain])
        return self.actions.pop(0) if self.actions else ("PASS", None, None)

    def decide_showdown_action(self, opponent, bf_idx):
        return ("PASS", None, None)


def _xerath_vs(loop, a, b, hand=()):
    """Xerath Freed ("[fury], [tap]: Deal 3 to a unit") and a 3 Might enemy
    at the first battlefield; `hand` in B's hand, its agent scripted."""
    xerath = _unit("Xerath Freed")
    enemy = _unit("Plain", 3)
    loop.gs.battlefields[0].add_unit("A", xerath)
    loop.gs.battlefields[0].add_unit("B", enemy)
    b.hand = [CARD_REGISTRY[n].instantiate() for n in hand]
    return xerath, enemy


def _use(loop, p, effect):
    loop._apply_action(p, ("ABILITY", "ACTIVATED", _ability(loop, p.name, effect), None))


def test_the_opponent_may_react_before_an_ability_resolves():
    loop, a, b = _setup()
    _deck(b, SpellCard(name="B1"))
    xerath, enemy = _xerath_vs(loop, a, b, ["Discipline"])
    b.agent = _Script(("SPELL", 0, 0))
    _pick(loop, "Plain")
    _use(loop, a, "deal_damage")
    # On the chain as B answered, then Discipline's +2 resolved first.
    assert b.agent.saw[0] == [("Xerath Freed", True)]
    assert not loop.gs.chain and not xerath.ready
    assert enemy in loop.gs.battlefields[0].units_B and enemy.damage == 3 and enemy.might == 5


def test_without_an_answer_the_ability_resolves():
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b)
    b.agent = _Script()
    _use(loop, a, "deal_damage")
    assert b.agent.saw and enemy not in loop.gs.battlefields[0].units_B


def test_not_so_fast_counters_an_enemy_ability_choosing_my_unit():
    """'Counter an enemy spell or ability that chooses a friendly unit or gear.'
    Its cost stays paid."""
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b, ["Not So Fast"])
    b.agent = _Script(("SPELL", 0, 0))
    _use(loop, a, "deal_damage")
    assert enemy in loop.gs.battlefields[0].units_B and enemy.damage == 0
    assert not xerath.ready and not loop.gs.chain
    assert [c.name for c in b.trash] == ["Not So Fast"]


def test_not_so_fast_needs_an_ability_choosing_mine():
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b)
    fast = CARD_REGISTRY["Not So Fast"].instantiate()
    held = []
    b.agent = _Script()
    b.agent.decide_reaction = lambda _o, chain: held.append(
        loop._spell_has_targets(fast, "B", 0)) or ("PASS", None, None)
    _pick(loop, "Xerath Freed")            # Xerath deals 3 to himself
    _use(loop, a, "deal_damage")
    assert held == [False]


def test_repulse_counters_an_ability_choosing_only_that_unit():
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b, ["Repulse"])
    b.agent = _Script(("SPELL", 0, 0))
    _use(loop, a, "deal_damage")
    assert enemy.damage == 0 and not loop.gs.chain


def test_mel_makes_abilities_uncounterable():
    """'Your spells and abilities can't be countered' (Mel EMPOWERED)."""
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b)
    mel = _unit("Mel Newly Awakened")
    mel.empowered = True
    a.base_units.append(mel)
    loop._recompute_passives()
    fast = CARD_REGISTRY["Not So Fast"].instantiate()
    held = []
    b.agent = _Script()
    b.agent.decide_reaction = lambda _o, chain: held.append(
        loop._spell_has_targets(fast, "B", 0)) or ("PASS", None, None)
    _use(loop, a, "deal_damage")
    assert held == [False] and enemy not in loop.gs.battlefields[0].units_B


def test_the_ability_resolves_even_if_its_source_is_gone():
    """An ability on the chain is independent of its source (§377.3)."""
    loop, a, b = _setup()
    _deck(b, SpellCard(name="B1"))
    xerath, enemy = _xerath_vs(loop, a, b)
    b.agent = _Script()

    def kill_xerath(_o, chain):
        if loop.gs.battlefields[0].units_A:
            loop.gs.battlefields[0].remove_unit("A", xerath)
        return ("PASS", None, None)
    b.agent.decide_reaction = kill_xerath
    _use(loop, a, "deal_damage")
    assert enemy not in loop.gs.battlefields[0].units_B


def test_an_ability_whose_target_left_is_not_followed():
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b)
    other = _unit("Other", 3)
    loop.gs.battlefields[0].add_unit("B", other)
    b.agent = _Script()
    _pick(loop, "Plain")

    def recall(_o, chain):
        if enemy in loop.gs.battlefields[0].units_B:
            loop.gs.battlefields[0].remove_unit("B", enemy)
            b.base_units.append(enemy)
        return ("PASS", None, None)
    b.agent.decide_reaction = recall
    _use(loop, a, "deal_damage")
    assert enemy.damage == 0 and other.damage == 0


def test_an_add_ability_resolves_at_once_and_keeps_priority():
    """'[tap]: REACTION - ADD [1]. (Abilities that add resources can't be
    reacted to.)' (Energy Conduit), used on an open chain."""
    loop, a, b = _setup()
    a.base_gear.append(CARD_REGISTRY["Energy Conduit"].instantiate())
    loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="Plain"), bf_idx=0))
    energy = a.energy
    step = loop._reaction_step(a, "A", ("ABILITY", "ACTIVATED", _ability(loop, "A", "gain_energy")))
    assert step == "kept" and a.energy == energy + 1 and len(loop.gs.chain) == 1


def test_a_reaction_ability_goes_on_top_of_the_chain():
    """Ezreal Prodigal Explorer's '[tap]: REACTION - Draw 1', used in answer to
    a spell: it resolves first, and priority passes."""
    loop, a, b = _setup()
    ezreal = _legend(loop, "A", "Ezreal Prodigal Explorer")
    ezreal.ready = True
    loop.gs.enemy_choices_this_turn["A"] = 2
    _deck(a, SpellCard(name="A1"))
    spell = ChainItem(player="B", card=SpellCard(name="Plain"), bf_idx=0)
    loop.gs.chain.append(spell)
    step = loop._reaction_step(a, "A", ("ABILITY", "ACTIVATED", _ability(loop, "A", "draw_cards")))
    assert step == "acted" and not a.hand
    assert loop.gs.chain[0] is spell and loop.gs.chain[1].ability is not None
    loop._resolve_chain()
    assert [c.name for c in a.hand] == ["A1"]


def test_a_showdown_ability_passes_focus():
    """§346: the chain an ability opened in a showdown closes, focus passes;
    an Add ability keeps it (§346.1)."""
    loop, a, b = _setup()
    xerath, enemy = _xerath_vs(loop, a, b)
    loop.gs.showdown_active, loop.gs.showdown_bf_idx = True, 0
    step = loop._showdown_step(a, "A", ("ABILITY", "ACTIVATED", _ability(loop, "A", "deal_damage")), 0)
    assert step == "acted" and enemy not in loop.gs.battlefields[0].units_B
    a.base_gear.append(CARD_REGISTRY["Energy Conduit"].instantiate())
    step = loop._showdown_step(a, "A", ("ABILITY", "ACTIVATED", _ability(loop, "A", "gain_energy")), 0)
    assert step == "kept"


def test_equip_goes_on_the_chain_and_needs_its_unit_still_there():
    """EQUIP (§818: '[cost]: Attach this to a unit you control', its unit a
    target): a unit gone in answer, the gear stays at base."""
    loop, a, b = _setup()
    holder = _unit("Holder", 2)
    loop.gs.battlefields[0].add_unit("A", holder)
    sword = CARD_REGISTRY["Long Sword"].instantiate()
    a.base_gear.append(sword)
    b.agent = _Script()

    def bounce(_o, chain):
        assert chain[-1].ability["kind"] == "equip" and chain[-1].declared[(0, 0, 0)][2] is holder
        loop.gs.battlefields[0].remove_unit("A", holder)
        return ("PASS", None, None)
    b.agent.decide_reaction = bounce
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "equip")
    loop._apply_action(a, ("ABILITY", "ACTIVATED", idx, None))
    assert sword in a.base_gear and not holder.gear


def test_equip_attaches_as_it_resolves():
    loop, a, b = _setup()
    holder = _unit("Holder", 2)
    loop.gs.battlefields[0].add_unit("A", holder)
    sword = CARD_REGISTRY["Long Sword"].instantiate()
    a.base_gear.append(sword)
    idx = next(i for i, e in enumerate(loop.activatable_abilities("A")) if e["type"] == "equip")
    loop._apply_action(a, ("ABILITY", "ACTIVATED", idx, None))
    assert holder.gear == [sword] and sword not in a.base_gear


def test_nasus_curator_hears_an_ability_as_it_resolves():
    """'When you play a unit, gear or activated ability with Energy cost [7]
    or more, you may exhaust me to ready up to 2 runes': "playing" an ability
    is fulfilled as it resolves (§377.2.a)."""
    loop, a, b = _setup()
    from riftbound.core.player import Rune
    nasus = _unit("Nasus Curator of the Sands")
    a.base_units.append(nasus)
    paws = _unit("Steel Paws")
    loop.gs.battlefields[0].add_unit("A", paws)
    a.rune_pool = {Domain.BODY: [Rune(Domain.BODY, ready=False) for _ in range(2)]}
    b.agent = _Script()
    seen = []
    b.agent.decide_reaction = lambda _o, chain: seen.append(nasus.ready) or ("PASS", None, None)
    _use(loop, a, "empower_self")
    assert seen == [True] and paws.empowered and not nasus.ready


def test_coach_names_an_ability_on_the_chain():
    loop, a, b = _setup()
    item = ChainItem(player="B", card=_unit("Xerath Freed").card, bf_idx=0,
                     ability={"eff": None, "kind": "ability", "energy": 0, "extra": {}, "target": None})
    assert option_text(loop.gs, "A", item) == "Xerath Freed (abilità avversaria sulla catena)"
