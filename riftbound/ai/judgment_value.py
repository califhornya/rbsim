"""The bot's value written from the user's judgments (18/11).

Starts from the hand-written value of `scripts/diag/handwritten_value.py`
(points, battlefields, Might, cards) and adds what the user's answers in
docs/bot/GIUDIZI.md, TEORIA_PUNTI.md and BOT_SCENARI.md say it missed:

- hidden cards are worth something: a card, a threat the opponent can't see,
  and with Evelynn a draw at reaction speed (S6, S11b, S10);
- cards in hand are worth more, and a reaction (or an Action for a showdown)
  the open runes can pay for in the opponent's turn is an out (S8, S6, S11a);
- points by the deck's plan: Evelynn holds (7 is worth more: one hold wins),
  Kha'Zix scores two a turn (an odd point is worth less) (TEORIA_PUNTI.md);
- the threats the user named: Irresistible Faefolk on the board (it moves your
  pieces), Vex Apathetic at a battlefield (it stuns what you play) (S7, S9, S10);
- Might that lasts past this turn (UnitInPlay.lasting_might).

The weights are a first guess, to be checked on the scenarios
(`scripts/diag/scenari_bot.py`) and the baseline (`handwritten_value.py`).
"""
from __future__ import annotations

import math
from functools import lru_cache

# How each deck wins (the user, 18/11): "hold" plays on odd scores and wins by
# holding at 7; "two" scores two a turn and wins from 6 with both battlefields.
PLAN = {"Evelynn Agony's Embrace": "hold", "Kha'Zix Voidreaver": "two"}

W = {
    "point": 0.45,        # a point (the hand-written value's weight)
    "odd": 0.5,           # for "two", an odd point counts half
    "seven": 0.5,         # for "hold", being at victory - 1 counts half a point more
    "control": 0.30,      # a battlefield controlled
    "might_bf": 0.05,     # Might at a battlefield, per point of difference
    "might_base": 0.03,   # Might in base
    "hand": 0.06,         # a card in hand
    "hidden": 0.15,       # a face-down card
    "out": 0.05,          # a reaction/Action the open runes pay for, up to 2
    "threat": 0.12,       # Faefolk on the board, Vex at a battlefield
}

_OUT_KEYWORDS = ("REACTION", "ACTION", "AMBUSH")


def _m(u) -> int:
    return u.might if u.lasting_might is None else u.lasting_might


def _points(p: int, plan, victory: int) -> float:
    if plan == "two" and p % 2 == 1 and p < victory:
        return p - (1 - W["odd"])
    if plan == "hold" and p == victory - 1:
        return p + W["seven"]
    return float(p)


@lru_cache(maxsize=None)
def _out_cost(name: str):
    """(energy, power, power domain) of a card playable in the opponent's
    turn, or None."""
    from riftbound.registry.cards_registry import CARD_REGISTRY
    spec = CARD_REGISTRY.get(name)
    if spec is None:
        return None
    card = spec.instantiate()
    if not any(k in (card.keywords or []) for k in _OUT_KEYWORDS):
        return None
    return (int(card.cost_energy or 0), int(card.cost_power or 0),
            getattr(card.cost_power_domain, "name", None))


def _outs(obs) -> int:
    """Cards in hand playable in the opponent's turn (a reaction, or an
    Action/Ambush in a showdown) that the open runes pay for, up to 2."""
    n = 0
    for name in obs.my_hand:
        cost = _out_cost(name)
        if cost is None or cost[0] > obs.my_energy:
            continue
        if cost[1]:
            have = obs.my_rune_domains.get(cost[2], 0) if cost[2] else sum(obs.my_rune_domains.values())
            if have < cost[1]:
                continue
        n += 1
    return min(n, 2)


def _threats(units, at_battlefield: bool) -> int:
    n = 0
    for u in units:
        if u.name == "Irresistible Faefolk":
            n += 1
        elif u.name == "Vex Apathetic" and at_battlefield:
            n += 1
    return n


def judgment_value(obs) -> float:
    me = obs.viewer
    them = "B" if me == "A" else "A"
    vs = obs.victory_score
    s = W["point"] * (_points(obs.my_points, PLAN.get(obs.my_legend), vs)
                      - _points(obs.opp_points, PLAN.get(obs.opp_legend), vs))
    threats = _threats(obs.my_base_units, False) - _threats(obs.opp_base_units, False)
    for bf in obs.battlefields:
        mine, theirs = getattr(bf, me), getattr(bf, them)
        if bf.controller == me:
            s += W["control"]
        elif bf.controller is not None:
            s -= W["control"]
        s += W["might_bf"] * (sum(_m(u) for u in mine) - sum(_m(u) for u in theirs))
        s += W["hidden"] * (bf.facedowns.count(me) - bf.facedowns.count(them))
        threats += _threats(mine, True) - _threats(theirs, True)
    s += W["might_base"] * (sum(_m(u) for u in obs.my_base_units) - sum(_m(u) for u in obs.opp_base_units))
    s += W["hand"] * (len(obs.my_hand) - obs.opp_hand_count)
    s += W["out"] * _outs(obs)
    s += W["threat"] * threats
    return math.tanh(s)
