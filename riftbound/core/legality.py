"""Legal-action enumeration — the validity checks that used to live implicitly
inside ``GameLoop._apply_action`` (which silently no-ops an illegal action),
made explicit so search agents, the web UI, and tests can ask "what can this
player actually do right now?".

Design: these functions take the live ``GameLoop`` (not a bare ``GameState``) so
they can reuse the engine's own cost helpers — ``_cost_reduction``,
``_can_choose`` (DEFLECT), ``activatable_abilities``, ``_parse_activated_cost``,
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


def _affordable(loop: "GameLoop", ap, card, lane: Optional[int] = None, dst=None) -> bool:
    """Whether `ap` can pay `card`'s cost now (aimed at `lane` for a spell;
    a unit or DEPLOY gear played to battlefield `dst`: Hunters' Circle)."""
    energy, power = loop._effective_cost(card, ap, lane)
    energy = max(0, energy - loop._destination_discount(card, dst, ap.name))
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
            for dst in loop._unit_play_destinations(card, side):
                if _affordable(loop, ap, card, dst=dst):
                    surcharge = loop._destination_surcharge(card, dst, side)
                    if surcharge and not loop._can_pay_generic_power(
                            ap, surcharge + int(loop._effective_cost(card, ap)[1] or 0)):
                        continue
                    if dst is None:
                        actions.append(GameAction.play("UNIT", idx, 0, f"Play {card.name}"))
                    else:
                        actions.append(GameAction("UNIT", idx, 0, dst, f"Play {card.name} to BF{dst}"))
        elif isinstance(card, SpellCard):
            for lane in range(n_bf):
                if _affordable(loop, ap, card, lane) and loop._spell_has_targets(card, side, lane):
                    actions.append(GameAction.play("SPELL", idx, lane, f"Cast {card.name} @BF{lane}"))
        elif isinstance(card, GearCard):
            for lane in range(n_bf):
                if _affordable(loop, ap, card, dst=lane if card.has_keyword("DEPLOY") else None):
                    actions.append(GameAction.play("GEAR", idx, lane, f"Play gear {card.name} @BF{lane}"))

    # --- deploy champion ---
    champ = gs.champion_A if side == "A" else gs.champion_B
    deployed = gs.champion_A_deployed if side == "A" else gs.champion_B_deployed
    if champ is not None and not deployed and _affordable(loop, ap, champ):
        actions.append(GameAction.champion(0, f"Deploy champion {champ.name}"))

    # --- movement (illegal during showdown or an open chain), one action per
    # ready unit; consecutive moves to one battlefield go together (§144.3) ---
    if not gs.showdown_active and not gs.chain:
        def where(loc):
            return "base" if loc == base_index else f"BF{loc}"
        for src in range(n_bf + 1):
            units = ap.base_units if src == base_index else gs.battlefields[src]._units_for(side)
            for ui, u in enumerate(units):
                if not u.ready or u.cant_move_turn == gs.turn:
                    continue
                for dst in range(n_bf + 1):
                    if dst == src:
                        continue
                    # bf→bf needs GANKING (§144.4.c), or the Baron Pit.
                    if src != base_index and dst != base_index and \
                            not loop._can_move_bf_to_bf(u, gs.battlefields[dst]):
                        continue
                    if dst == base_index and not loop._can_move_to_base(
                            u, None if src == base_index else gs.battlefields[src]):
                        continue      # "can't move to base" (Vilemaw's Lair, Sentry)
                    if loop._group_move_toll(side, dst) > ap.energy:
                        continue      # Mageseeker Investigator
                    joining = gs.pending_move is not None and gs.pending_move == (dst, side)
                    if dst != base_index and not joining and \
                            not loop._can_pay_move_tax(side, gs.battlefields[dst]):
                        continue      # Gravity Field's tax
                    actions.append(GameAction.move(
                        src, dst, f"Move {u.card.name} {where(src)}→{where(dst)}", unit=ui))

    # --- HIDDEN keyword (Open State only) ---
    if not gs.showdown_active and not gs.chain:
        hide_lanes = loop._hide_lanes(side)
        if hide_lanes and loop._can_hide_pay(ap, side):
            for idx, card in enumerate(ap.hand):
                if card.has_keyword("HIDDEN"):
                    for lane in hide_lanes:
                        actions.append(GameAction.hide(idx, lane, f"Hide {card.name} @BF{lane}"))
            # The champion, from the Champion Zone (§811.1.b).
            champ = loop._hideable_champion(side)
            if champ is not None:
                for lane in hide_lanes:
                    actions.append(GameAction.hide("champion", lane, f"Hide {champ.name} @BF{lane}"))
        # Play a card you hid on a previous turn, for [0].
        actions.extend(_hidden_play_actions(loop, side))

    # --- abilities ---
    actions.extend(_ability_actions(loop, ap, side))

    # A move being declared (§144.3): more units may join it, to the same
    # battlefield; PASS ends it, and its showdown starts (§323.11).
    pending = gs.pending_move
    if pending is not None and pending[1] == side:
        actions = [a for a in actions
                   if a.kind == "PASS" or (a.kind == "MOVE" and a.dst_lane == pending[0])]
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
        elif entry["type"] == "flow":
            label = f"Play {entry['card'].name} from trash (FLOW)"
        elif entry["type"] == "banished_play":
            label = f"Play {entry['card'].name} from banishment"
        elif entry["type"] == "trash_play":
            label = f"Play {entry['card'].name} from trash"
        elif entry["type"] == "gear_ability":
            label = f"Gear {entry['eff'].effect} ({entry['gear'].name})"
        elif entry["type"] == "bf_ability":
            label = f"Battlefield {entry['eff'].effect} ({entry['bf'].card.name})"
        else:
            label = f"Activate {entry['eff'].effect} ({entry['unit'].card.name})"
        out.append(GameAction.ability("ACTIVATED", i, label))
    return out


def _reaction_actions(loop: "GameLoop", ap) -> list[GameAction]:
    """REACTION spells in hand that are affordable (mirrors _run_chain)."""
    n_bf = len(loop.gs.battlefields)
    actions: list[GameAction] = [GameAction.pass_()]
    for idx, card in enumerate(ap.hand):
        if isinstance(card, SpellCard) and loop._has_reaction(card, ap.name):
            for lane in range(n_bf):
                if _affordable(loop, ap, card, lane) and loop._spell_has_targets(card, ap.name, lane):
                    actions.append(GameAction.play("SPELL", idx, lane, f"React {card.name} @BF{lane}"))
        # REACTION gear (QUICK-DRAW §745, Sumpworks Map): playable at reaction speed.
        elif isinstance(card, GearCard) and loop._play_timing(card, ap.name) == "reaction":
            for lane in range(n_bf):
                if _affordable(loop, ap, card, dst=lane if card.has_keyword("DEPLOY") else None):
                    actions.append(GameAction.play("GEAR", idx, lane, f"Quick-Draw {card.name} @BF{lane}"))
    # AMBUSH units in hand, to a battlefield where we have units (Hunters'
    # Circle's discount there on your turn).
    for idx, card in enumerate(ap.hand):
        if isinstance(card, UnitCard):
            for lane in loop._ambush_unit_lanes(card, ap.name):
                if _affordable(loop, ap, card, dst=lane):
                    actions.append(GameAction("UNIT", idx, 0, lane, f"AMBUSH {card.name} @BF{lane}"))
    # AMBUSH: deploy the champion to a legal lane at reaction speed.
    champ = loop.gs.champion_A if ap.name == "A" else loop.gs.champion_B
    if champ is not None:
        for lane in loop._ambush_legal_lanes(ap.name):
            if _affordable(loop, ap, champ, dst=lane):
                actions.append(GameAction.champion(lane, f"AMBUSH {champ.name} @BF{lane}"))
    # HIDDEN: play a facedown card for [0] at reaction speed (§737.1.b).
    actions.extend(_hidden_play_actions(loop, ap.name))
    # REACTION abilities (mana abilities like Seals and Gold among them).
    actions.extend(_ability_actions(loop, ap, ap.name))
    return actions


def _showdown_actions(loop: "GameLoop", ap) -> list[GameAction]:
    """ACTION/REACTION spells playable during a showdown (mirrors _run_showdown)."""
    gs = loop.gs
    lane = gs.showdown_bf_idx if gs.showdown_bf_idx is not None else 0
    actions: list[GameAction] = [GameAction.pass_()]
    for idx, card in enumerate(ap.hand):
        if isinstance(card, SpellCard) and (card.has_keyword("ACTION") or loop._has_reaction(card, ap.name)):
            if _affordable(loop, ap, card, lane) and loop._spell_has_targets(card, ap.name, lane):
                actions.append(GameAction.play("SPELL", idx, lane, f"Showdown {card.name} @BF{lane}"))
        # ACTION units (§732.1.c.1): may be played during showdowns (to base).
        elif isinstance(card, UnitCard) and card.has_keyword("ACTION"):
            if _affordable(loop, ap, card):
                actions.append(GameAction.play("UNIT", idx, lane, f"Showdown unit {card.name}"))
        # AMBUSH units into the showdown's battlefield.
        if isinstance(card, UnitCard) and lane in loop._ambush_unit_lanes(card, ap.name) \
                and _affordable(loop, ap, card, dst=lane):
            actions.append(GameAction("UNIT", idx, lane, lane, f"AMBUSH {card.name} @BF{lane}"))
        # ACTION / REACTION gear (QUICK-DRAW §745, Jarvan IV's DEPLOY gear):
        # playable during a showdown.
        elif isinstance(card, GearCard) and loop._play_timing(card, ap.name) in ("action", "reaction"):
            if _affordable(loop, ap, card, dst=lane if card.has_keyword("DEPLOY") else None):
                actions.append(GameAction.play("GEAR", idx, lane, f"Quick-Draw {card.name} @BF{lane}"))
    # AMBUSH: deploy the champion into the showdown lane at reaction speed.
    champ = gs.champion_A if ap.name == "A" else gs.champion_B
    if (champ is not None and lane in loop._ambush_legal_lanes(ap.name)
            and _affordable(loop, ap, champ, dst=lane)):
        actions.append(GameAction.champion(lane, f"AMBUSH {champ.name} @BF{lane}"))
    # HIDDEN: play a facedown card into the showdown lane for [0] (§737.1.b).
    actions.extend(_hidden_play_actions(loop, ap.name, only_lane=lane))
    # ACTION and REACTION abilities.
    actions.extend(_ability_actions(loop, ap, ap.name))
    return actions


def _hidden_play_actions(loop: "GameLoop", side: str, only_lane=None) -> list[GameAction]:
    """Play each facedown card `side` may now play for [0] (§737.1.b), one action
    per card: a Facedown Zone can hold two (Bandle Tree)."""
    actions = []
    for lane, slot in loop._hidden_playable(side):
        if only_lane is None or lane == only_lane:
            fd = loop.gs.battlefields[lane].facedowns[slot]
            actions.append(GameAction.hidden_play(lane, f"Play {fd.card.name} from Hidden @BF{lane}", slot))
    return actions
