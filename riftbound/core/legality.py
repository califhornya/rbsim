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


def _affordable(loop: "GameLoop", ap, card, lane: Optional[int] = None) -> bool:
    """Whether `ap` can pay `card`'s cost now (aimed at `lane` for a spell)."""
    energy, power = loop._effective_cost(card, ap, lane)
    return loop._can_pay_card(ap, card, energy, power)


def _turn_actions(loop: "GameLoop", ap) -> list[GameAction]:
    gs = loop.gs
    side = ap.name
    n_bf = len(gs.battlefields)
    base_index = n_bf

    actions: list[GameAction] = [GameAction.pass_()]

    # --- plays from hand (same cost the engine charges: GameLoop._effective_cost) ---
    for idx, card in enumerate(ap.hand):
        if isinstance(card, (UnitCard, LegendCard)):
            if _affordable(loop, ap, card):
                actions.append(GameAction.play("UNIT", idx, 0, f"Play {card.name}"))
        elif isinstance(card, SpellCard):
            for lane in range(n_bf):
                if _affordable(loop, ap, card, lane):
                    actions.append(GameAction.play("SPELL", idx, lane, f"Cast {card.name} @BF{lane}"))
        elif isinstance(card, GearCard):
            if _affordable(loop, ap, card):
                for lane in range(n_bf):
                    actions.append(GameAction.play("GEAR", idx, lane, f"Play gear {card.name} @BF{lane}"))

    # --- deploy champion ---
    champ = gs.champion_A if side == "A" else gs.champion_B
    deployed = gs.champion_A_deployed if side == "A" else gs.champion_B_deployed
    if champ is not None and not deployed and _affordable(loop, ap, champ):
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

    # --- HIDDEN keyword (Open State only) ---
    if not gs.showdown_active and not gs.chain:
        hide_lanes = loop._hide_lanes(side)
        if hide_lanes and loop._can_pay_generic_power(ap, 1):
            for idx, card in enumerate(ap.hand):
                if card.has_keyword("HIDDEN"):
                    for lane in hide_lanes:
                        actions.append(GameAction.hide(idx, lane, f"Hide {card.name} @BF{lane}"))
        # Play a card you hid on a previous turn, for [0].
        for lane in loop._hidden_playable_lanes(side):
            fd = gs.battlefields[lane].facedown
            actions.append(GameAction.hidden_play(lane, f"Play {fd.card.name} from Hidden @BF{lane}"))

    # --- abilities ---
    actions.extend(_ability_actions(loop, ap, side))
    return actions


def _ability_actions(loop: "GameLoop", ap, side: str) -> list[GameAction]:
    out: list[GameAction] = []

    # Generic activated abilities + base-gear equips (stable index order), those
    # the current window allows (GameLoop._ability_window) and that are usable.
    for i, entry in enumerate(loop.activatable_abilities(side)):
        if not loop._ability_usable(ap, entry):
            continue
        if entry["type"] == "equip":
            label = f"Equip {entry['gear'].name}"
        elif entry["type"] == "gear_ability":
            label = f"Gear {entry['eff'].effect} ({entry['gear'].name})"
        else:
            label = f"Activate {entry['eff'].effect} ({entry['unit'].card.name})"
        out.append(GameAction.ability("ACTIVATED", i, label))
    return out


def _reaction_actions(loop: "GameLoop", ap) -> list[GameAction]:
    """REACTION spells in hand that are affordable (mirrors _run_chain)."""
    n_bf = len(loop.gs.battlefields)
    actions: list[GameAction] = [GameAction.pass_()]
    for idx, card in enumerate(ap.hand):
        if isinstance(card, SpellCard) and card.has_keyword("REACTION"):
            for lane in range(n_bf):
                if _affordable(loop, ap, card, lane):
                    actions.append(GameAction.play("SPELL", idx, lane, f"React {card.name} @BF{lane}"))
        # QUICK-DRAW gear (§745): has Reaction — playable at reaction speed.
        elif isinstance(card, GearCard) and card.has_keyword("QUICK-DRAW"):
            if _affordable(loop, ap, card):
                for lane in range(n_bf):
                    actions.append(GameAction.play("GEAR", idx, lane, f"Quick-Draw {card.name} @BF{lane}"))
    # AMBUSH: deploy the champion to a legal lane at reaction speed.
    champ = loop.gs.champion_A if ap.name == "A" else loop.gs.champion_B
    if champ is not None and _affordable(loop, ap, champ):
        for lane in loop._ambush_legal_lanes(ap.name):
            actions.append(GameAction.champion(lane, f"AMBUSH {champ.name} @BF{lane}"))
    # HIDDEN: play a facedown card for [0] at reaction speed (§737.1.b).
    for lane in loop._hidden_playable_lanes(ap.name):
        fd = loop.gs.battlefields[lane].facedown
        actions.append(GameAction.hidden_play(lane, f"Play {fd.card.name} from Hidden @BF{lane}"))
    # REACTION abilities (mana abilities like Seals and Gold among them).
    actions.extend(_ability_actions(loop, ap, ap.name))
    return actions


def _showdown_actions(loop: "GameLoop", ap) -> list[GameAction]:
    """ACTION/REACTION spells playable during a showdown (mirrors _run_showdown)."""
    gs = loop.gs
    lane = gs.showdown_bf_idx if gs.showdown_bf_idx is not None else 0
    actions: list[GameAction] = [GameAction.pass_()]
    for idx, card in enumerate(ap.hand):
        if isinstance(card, SpellCard) and (card.has_keyword("ACTION") or card.has_keyword("REACTION")):
            if _affordable(loop, ap, card, lane):
                actions.append(GameAction.play("SPELL", idx, lane, f"Showdown {card.name} @BF{lane}"))
        # ACTION units (§732.1.c.1): may be played during showdowns (to base).
        elif isinstance(card, UnitCard) and card.has_keyword("ACTION"):
            if _affordable(loop, ap, card):
                actions.append(GameAction.play("UNIT", idx, lane, f"Showdown unit {card.name}"))
        # QUICK-DRAW gear (§745): has Reaction — playable during a showdown.
        elif isinstance(card, GearCard) and card.has_keyword("QUICK-DRAW"):
            if _affordable(loop, ap, card):
                actions.append(GameAction.play("GEAR", idx, lane, f"Quick-Draw {card.name} @BF{lane}"))
    # AMBUSH: deploy the champion into the showdown lane at reaction speed.
    champ = gs.champion_A if ap.name == "A" else gs.champion_B
    if (champ is not None and lane in loop._ambush_legal_lanes(ap.name)
            and _affordable(loop, ap, champ)):
        actions.append(GameAction.champion(lane, f"AMBUSH {champ.name} @BF{lane}"))
    # HIDDEN: play a facedown card into the showdown lane for [0] (§737.1.b).
    if lane in loop._hidden_playable_lanes(ap.name):
        fd = gs.battlefields[lane].facedown
        actions.append(GameAction.hidden_play(lane, f"Play {fd.card.name} from Hidden @BF{lane}"))
    # ACTION and REACTION abilities.
    actions.extend(_ability_actions(loop, ap, ap.name))
    return actions
