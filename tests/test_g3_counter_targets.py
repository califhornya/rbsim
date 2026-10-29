"""BACKLOG G3 "Counter targets" (§355.9.a.2): "counter a spell" chooses any
spell on the chain, as it is played (a declared target); it always hit the
chain's top item, so a REPEAT run (Hard Bargain) countered whatever came next,
our own spell too."""

from __future__ import annotations

from riftbound.ai.coach import option_text
from riftbound.core.cards import SpellCard
from riftbound.core.state import ChainItem
from riftbound.registry.cards_registry import CARD_REGISTRY

from test_corpus_cards import _deck, _setup, _unit


def _on_chain(loop, side, card):
    item = ChainItem(player=side, card=card, bf_idx=0)
    loop._put_on_chain(item)
    return item


def _cast(loop, name, side="A", **flags):
    card = CARD_REGISTRY[name].instantiate()
    for k, v in flags.items():
        setattr(card, k, v)
    return _on_chain(loop, side, card)


def _countered(item):
    return [got for kind, _n, got in (item.declared or {}).values() if kind == "target:counter_spell"]


def _pick_card(loop, name):
    """A counter's choice picks the spell called `name`."""
    def chooser(_loop, kind, side, options, default, source):
        if kind == "target:counter_spell":
            return next(i for i, o in enumerate(options) if o.card.name == name)
        return None
    loop.chooser = chooser


def test_baseline_counters_the_enemy_spell_under_my_own():
    loop, a, b = _setup()
    _deck(a, SpellCard(name="A1"), SpellCard(name="A2"))
    _deck(b, SpellCard(name="B1"), SpellCard(name="B2"))
    theirs = _cast(loop, "Consult the Past", "B")
    _cast(loop, "Consult the Past", "A")
    wall = _cast(loop, "Wind Wall")
    assert _countered(wall) == [theirs]
    loop._resolve_chain()
    assert [c.name for c in a.hand] == ["A1", "A2"] and not b.hand
    assert theirs.card in b.trash


def test_the_player_may_counter_a_spell_lower_on_the_chain():
    loop, a, b = _setup()
    _deck(b, SpellCard(name="B1"), SpellCard(name="B2"))
    consult = _cast(loop, "Consult the Past", "B")
    _on_chain(loop, "B", SpellCard(name="Plain"))
    _pick_card(loop, "Consult the Past")
    wall = _cast(loop, "Wind Wall")
    assert _countered(wall) == [consult]
    loop._resolve_chain()
    assert not b.hand and consult.card in b.trash


def test_the_declared_spell_gone_counters_nothing_else():
    """Chosen as played: if that spell has left the chain, the counter isn't
    followed (it used to counter the new top)."""
    loop, a, b = _setup()
    _deck(b, SpellCard(name="B1"), SpellCard(name="B2"))
    first = _on_chain(loop, "B", SpellCard(name="Plain"))
    wall = _cast(loop, "Wind Wall")
    assert _countered(wall) == [first]
    loop.gs.chain.remove(first)
    loop.gs.chain.insert(0, ChainItem(player="B", card=CARD_REGISTRY["Consult the Past"].instantiate(),
                                      bf_idx=0))
    loop._resolve_chain()
    assert [c.name for c in b.hand] == ["B1", "B2"]


def test_hard_bargain_repeat_spares_my_own_spell():
    """REPEAT: the second run doesn't fall on our spell below once theirs is
    countered (before: it countered the new top, ours)."""
    loop, a, b = _setup()
    _deck(a, SpellCard(name="A1"), SpellCard(name="A2"))
    a.energy = b.energy = 0                    # nobody pays "unless its controller pays [2]"
    _cast(loop, "Consult the Past", "A")
    plain = _on_chain(loop, "B", SpellCard(name="Plain"))
    _cast(loop, "Hard Bargain", _repeat_paid=True)
    loop._resolve_chain()
    assert [c.name for c in a.hand] == ["A1", "A2"] and plain.card in b.trash


def test_hard_bargain_repeat_taxes_the_same_spell_twice():
    """Both runs name their spell: it pays [2] once, then it's countered."""
    loop, a, b = _setup()
    _deck(b, SpellCard(name="B1"), SpellCard(name="B2"))
    b.energy = 2
    consult = _cast(loop, "Consult the Past", "B")
    bargain = _cast(loop, "Hard Bargain", _repeat_paid=True)
    assert _countered(bargain) == [consult, consult]
    loop._resolve_chain()
    assert b.energy == 0 and not b.hand and consult.card in b.trash


def test_not_so_fast_finds_the_spell_choosing_mine_under_the_top():
    loop, a, b = _setup()
    mine = _unit("Mine", 2)
    loop.gs.battlefields[0].add_unit("A", mine)
    aimed = ChainItem(player="B", card=SpellCard(name="Aimed"), bf_idx=0)
    aimed.declared = {(0, 0, 0): ("target:deal_damage", 0, [mine])}
    loop.gs.chain.append(aimed)
    loop.gs.chain.append(ChainItem(player="B", card=SpellCard(name="Elsewhere"), bf_idx=0))
    assert loop._spell_has_targets(CARD_REGISTRY["Not So Fast"].instantiate(), "A", 0)
    fast = _cast(loop, "Not So Fast")
    assert _countered(fast) == [aimed]


def test_a_spell_that_cant_be_countered_isnt_a_choice():
    loop, a, b = _setup()
    _deck(b, SpellCard(name="B1"), SpellCard(name="B2"))
    consult = _cast(loop, "Consult the Past", "B")
    _on_chain(loop, "B", CARD_REGISTRY["Decree of Rage"].instantiate())
    wall = _cast(loop, "Wind Wall")
    assert _countered(wall) == [consult]
    loop.gs.chain.clear()
    _on_chain(loop, "B", CARD_REGISTRY["Decree of Rage"].instantiate())
    assert not loop._spell_has_targets(CARD_REGISTRY["Wind Wall"].instantiate(), "A", 0)


def test_rebuttal_declares_its_spell_too():
    loop, a, b = _setup()
    consult = _cast(loop, "Consult the Past", "B")
    rebuttal = _cast(loop, "Rebuttal")
    assert [got for kind, _n, got in rebuttal.declared.values()
            if kind == "target:steal_or_counter_spell"] == [consult]


def test_coach_names_a_spell_on_the_chain():
    loop, a, b = _setup()
    item = _cast(loop, "Consult the Past", "B")
    assert option_text(loop.gs, "A", item) == "Consult the Past (magia avversaria sulla catena)"
