"""Legal-action enumeration — the validity checks that used to live implicitly
inside ``GameLoop._apply_action`` (which silently no-ops an illegal action),
made explicit so search agents, the web UI, and tests can ask "what can this
player actually do right now?".

Design: these functions take the live ``GameLoop`` (not a bare ``GameState``) so
they can reuse the engine's own cost helpers — ``_cost_reduction``,
``_deflect_surcharge``, ``activatable_abilities``, ``_parse_activated_cost``,
``_activated_affordable`` — rather than reimplementing them and risking drift.
Search passes a loop built over a *clone* (whose agents are stripped, so building
a loop over it has no side effects); the live game passes its own loop.

Guarantee (tested in tests/test_legality.py): every returned :class:`GameAction`
is *sound* — applying it to a clone changes the game state (it is never one of
the no-ops the engine's fingerprint guard would swallow). PASS is always offered
at every non-mulligan point.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .cards import GearCard, LegendCard, SpellCard, UnitCard
from .decisions import DecisionPoint, GameAction
from .effects import REGISTRY as EFFECT_REGISTRY
from .enums import Domain
from .legion_effects import get_legion_cost_reduction

if TYPE_CHECKING:
    from .loop import GameLoop


def legal_actions(
    loop: "GameLoop",
    point: DecisionPoint = DecisionPoint.TURN_ACTION,
    player: Optional[str] = None,
) -> list[GameAction]:
    """Enumerate the legal actions for ``player`` (default: the active player) at
    ``point``. MULLIGAN returns ``[]`` — its choice is a subset of hand indices,
    not a tuple action, so consumers read ``Observation.my_hand`` instead."""
    gs = loop.gs
    if point == DecisionPoint.TURN_ACTION:
        return _turn_actions(loop, gs.get_player(player or gs.active))
    if point == DecisionPoint.REACTION:
        if player is None:
            raise ValueError("REACTION legal_actions requires an explicit player")
        return _reaction_actions(loop, gs.get_player(player))
    if point == DecisionPoint.SHOWDOWN_ACTION:
        if player is None:
            raise ValueError("SHOWDOWN_ACTION legal_actions requires an explicit player")
        return _showdown_actions(loop, gs.get_player(player))
    if point == DecisionPoint.MULLIGAN:
        return []
    raise ValueError(f"unknown decision point: {point!r}")


def _turn_actions(loop: "GameLoop", ap) -> list[GameAction]:
    gs = loop.gs
    side = ap.name
    n_bf = len(gs.battlefields)
    base_index = n_bf
    cards_played = gs.cards_played_this_turn.get(side, 0)

    actions: list[GameAction] = [GameAction.pass_()]

    # --- plays from hand ---
    for idx, card in enumerate(ap.hand):
        if isinstance(card, (UnitCard, LegendCard)):
            effective = card.cost_energy
            if card.has_keyword("LEGION") and cards_played > 0:
                red = get_legion_cost_reduction(card.name)
                if red is not None:
                    effective = max(0, card.cost_energy - red)
            effective = max(0, effective - loop._cost_reduction(card, ap))
            if ap.can_pay_cost(effective, card.cost_power, card.cost_power_domain):
                actions.append(GameAction.play("UNIT", idx, 0, f"Play {card.name}"))
        elif isinstance(card, SpellCard):
            for lane in range(n_bf):
                surcharge = loop._deflect_surcharge(card, lane)
                bf_e_red, bf_p_red = loop._bf_cost_reduction(card, lane)
                energy = max(0, card.cost_energy + surcharge - loop._cost_reduction(card, ap) - bf_e_red)
                power = card.cost_power
                if power is not None and bf_p_red:
                    power = max(0, power - bf_p_red)
                if ap.can_pay_cost(energy, power, card.cost_power_domain):
                    actions.append(GameAction.play("SPELL", idx, lane, f"Cast {card.name} @BF{lane}"))
        elif isinstance(card, GearCard):
            energy = max(0, card.cost_energy - loop._cost_reduction(card, ap))
            if ap.can_pay_cost(energy, card.cost_power, card.cost_power_domain):
                for lane in range(n_bf):
                    actions.append(GameAction.play("GEAR", idx, lane, f"Play gear {card.name} @BF{lane}"))

    # --- deploy champion ---
    champ = gs.champion_A if side == "A" else gs.champion_B
    deployed = gs.champion_A_deployed if side == "A" else gs.champion_B_deployed
    if champ is not None and not deployed and ap.can_pay_cost(
        champ.cost_energy, champ.cost_power, champ.cost_power_domain
    ):
        actions.append(GameAction.champion(0, f"Deploy champion {champ.name}"))

    # --- movement (illegal during showdown or an open chain) ---
    if not gs.showdown_active and not gs.chain:
        if ap.has_movable_base_unit():
            for dst in range(n_bf):
                actions.append(GameAction.move(base_index, dst, f"Move base→BF{dst}"))
        for src in range(n_bf):
            units = gs.battlefields[src].units_A if side == "A" else gs.battlefields[src].units_B
            first_ready = next((u for u in units if u.ready), None)
            if first_ready is None:
                continue
            actions.append(GameAction.move(src, base_index, f"Move BF{src}→base"))
            # bf→bf only applies if the moving unit (first ready) has GANKING —
            # otherwise the engine refuses it (see _apply_action MOVE branch).
            if first_ready.has_keyword("GANKING"):
                for dst in range(n_bf):
                    if dst != src:
                        actions.append(GameAction.move(src, dst, f"Move BF{src}→BF{dst}"))

    # --- abilities ---
    actions.extend(_ability_actions(loop, ap, side))
    return actions


def _ability_actions(loop: "GameLoop", ap, side: str) -> list[GameAction]:
    gs = loop.gs
    out: list[GameAction] = []

    # Pyke legend: [1],[tap] a ready Pyke on a battlefield.
    pyke_ready = any(
        u.card.name == "Pyke Bloodharbor Ripper" and u.ready
        for bf in gs.battlefields
        for u in (bf.units_A if side == "A" else bf.units_B)
    )
    if pyke_ready and ap.can_pay_cost(1, None, None):
        out.append(GameAction.ability("PYKE_LEGEND", 0, "Pyke: bounce a unit, spawn Gold"))

    # Gold sacrifice: kill a Gold token → add a rune of a chosen domain.
    if any(u.card.name == "Gold" and u.is_token for u in ap.base_units):
        domains = [d for d in Domain if d in ap.rune_pool] or list(Domain)
        for d in domains:
            out.append(GameAction.ability("GOLD_SACRIFICE", d.name, f"Sacrifice Gold → {d.name} rune"))

    # Generic activated abilities + base-gear equips (stable index order).
    for i, entry in enumerate(loop.activatable_abilities(side)):
        if entry["type"] == "equip":
            gear = entry["gear"]
            if (
                gear in ap.base_gear
                and ap.can_pay_cost(gear.cost_energy, gear.cost_power, gear.cost_power_domain)
                and loop._first_friendly_unit_on_board(side) is not None
            ):
                out.append(GameAction.ability("ACTIVATED", i, f"Equip {gear.name}"))
        else:
            unit, eff = entry["unit"], entry["eff"]
            parsed = loop._parse_activated_cost(eff.cost)
            if loop._activated_affordable(ap, unit, parsed) and EFFECT_REGISTRY.get(eff.effect) is not None:
                out.append(GameAction.ability("ACTIVATED", i, f"Activate {eff.effect} ({unit.card.name})"))
    return out


def _reaction_actions(loop: "GameLoop", ap) -> list[GameAction]:
    """REACTION spells in hand that are affordable (mirrors _run_chain)."""
    n_bf = len(loop.gs.battlefields)
    actions: list[GameAction] = [GameAction.pass_()]
    for idx, card in enumerate(ap.hand):
        if isinstance(card, SpellCard) and card.has_keyword("REACTION"):
            if ap.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                for lane in range(n_bf):
                    actions.append(GameAction.play("SPELL", idx, lane, f"React {card.name} @BF{lane}"))
    # AMBUSH: deploy the champion to a legal lane at reaction speed.
    champ = loop.gs.champion_A if ap.name == "A" else loop.gs.champion_B
    if champ is not None and ap.can_pay_cost(champ.cost_energy, champ.cost_power, champ.cost_power_domain):
        for lane in loop._ambush_legal_lanes(ap.name):
            actions.append(GameAction.champion(lane, f"AMBUSH {champ.name} @BF{lane}"))
    return actions


def _showdown_actions(loop: "GameLoop", ap) -> list[GameAction]:
    """ACTION/REACTION spells playable during a showdown (mirrors _run_showdown)."""
    gs = loop.gs
    lane = gs.showdown_bf_idx if gs.showdown_bf_idx is not None else 0
    actions: list[GameAction] = [GameAction.pass_()]
    for idx, card in enumerate(ap.hand):
        if isinstance(card, SpellCard) and (card.has_keyword("ACTION") or card.has_keyword("REACTION")):
            if ap.can_pay_cost(card.cost_energy, card.cost_power, card.cost_power_domain):
                actions.append(GameAction.play("SPELL", idx, lane, f"Showdown {card.name} @BF{lane}"))
    # AMBUSH: deploy the champion into the showdown lane at reaction speed.
    champ = gs.champion_A if ap.name == "A" else gs.champion_B
    if (champ is not None and lane in loop._ambush_legal_lanes(ap.name)
            and ap.can_pay_cost(champ.cost_energy, champ.cost_power, champ.cost_power_domain)):
        actions.append(GameAction.champion(lane, f"AMBUSH {champ.name} @BF{lane}"))
    return actions
