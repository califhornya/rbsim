"""State & action encoding — the neural network's input/output contract (RL Chunk 1).

Two jobs, both deterministic and framework-light (numpy only; no torch here):

1. ``encode_observation(obs) -> np.ndarray`` turns the information-set
   :class:`Observation` (decisions.py) into a fixed-size float32 vector the network
   reads. It uses only what a player may legitimately see (no hidden info).

2. A **canonical fixed action space**: every turn/reaction/showdown ``GameAction``
   maps to a stable integer slot (``action_to_index``); ``legal_mask`` marks which
   slots are legal right now (to zero illegal policy logits); ``index_to_legal_action``
   maps a chosen slot back to the concrete legal action to play. MULLIGAN is a
   separate small head (a ``list[int]`` of hand cards to return), see the bottom.

This is v1: card features are bag-of-counts over the card vocabulary. A learned
embedding can replace them later without changing the contract (OBS_DIM would just
change, which the net reads from this module).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from riftbound.core.decisions import GameAction, Observation
from riftbound.registry.cards_registry import CARD_REGISTRY

# --- fixed dimensions ---------------------------------------------------------
N_BF = 2
MAX_HAND = 12
MAX_ABIL = 8
DOMAINS = ("FURY", "CALM", "MIND", "BODY", "CHAOS", "ORDER")
N_DOM = len(DOMAINS)
_DOM_INDEX = {d: i for i, d in enumerate(DOMAINS)}

# Card vocabulary: sorted registry names → stable index (order-stable across runs).
CARD_VOCAB: tuple[str, ...] = tuple(sorted(CARD_REGISTRY.keys()))
_CARD_INDEX = {name: i for i, name in enumerate(CARD_VOCAB)}
VOCAB_SIZE = len(CARD_VOCAB)

# Battlefield-name vocabulary for the per-BF "named" one-hot (+1 for "no card").
_BF_VOCAB: tuple[str, ...] = tuple(sorted(
    name for name, spec in CARD_REGISTRY.items()
    if getattr(spec.category, "name", "") == "BATTLEFIELD"
))
_BF_INDEX = {name: i for i, name in enumerate(_BF_VOCAB)}
_BF_ONEHOT = len(_BF_VOCAB) + 1  # last slot = unnamed / unknown

# Per-battlefield feature width: counts(2) + mights(2) + controller one-hot(3) + named one-hot.
_PER_BF = 2 + 2 + 3 + _BF_ONEHOT

# Scalar features (see _scalars); kept in a list so the count is self-documenting.
_N_SCALARS = 14 + 2 * N_DOM

OBS_DIM = _N_SCALARS + N_BF * _PER_BF + 4 * VOCAB_SIZE


def card_index(name: str) -> Optional[int]:
    return _CARD_INDEX.get(name)


# --- state encoding -----------------------------------------------------------

def _bag(names) -> np.ndarray:
    v = np.zeros(VOCAB_SIZE, dtype=np.float32)
    for n in names:
        i = _CARD_INDEX.get(n)
        if i is not None:
            v[i] += 1.0
    return v


def _scalars(obs: Observation) -> np.ndarray:
    vs = max(1, obs.victory_score)
    s = [
        obs.turn / 20.0,
        obs.my_points / vs,
        obs.opp_points / vs,
        obs.victory_score / 8.0,
        obs.my_energy / 15.0,
        obs.opp_energy / 15.0,
        obs.my_xp / 15.0,
        obs.opp_xp / 15.0,
        len(obs.my_hand) / 12.0,
        obs.opp_hand_count / 12.0,
        obs.my_deck_count / 40.0,
        obs.opp_deck_count / 40.0,
        obs.my_runes / 12.0,
        obs.opp_runes / 12.0,
    ]
    for d in DOMAINS:
        s.append(obs.my_power.get(d, 0) / 12.0)
    for d in DOMAINS:
        s.append(obs.opp_power.get(d, 0) / 12.0)
    return np.asarray(s, dtype=np.float32)


def _bf_features(bfview, me_side: str) -> np.ndarray:
    mine = bfview.A if me_side == "A" else bfview.B
    opp = bfview.B if me_side == "A" else bfview.A
    ctrl = bfview.controller
    ctrl_me = 1.0 if ctrl == me_side else 0.0
    ctrl_opp = 1.0 if (ctrl is not None and ctrl != me_side) else 0.0
    ctrl_none = 1.0 if ctrl is None else 0.0
    named = np.zeros(_BF_ONEHOT, dtype=np.float32)
    idx = _BF_INDEX.get(bfview.named) if bfview.named else None
    named[idx if idx is not None else _BF_ONEHOT - 1] = 1.0
    head = np.asarray([
        len(mine) / 6.0, len(opp) / 6.0,
        sum(u.might for u in mine) / 20.0, sum(u.might for u in opp) / 20.0,
        ctrl_me, ctrl_opp, ctrl_none,
    ], dtype=np.float32)
    return np.concatenate([head, named])


def encode_observation(obs: Observation) -> np.ndarray:
    """Fixed-size float32 encoding of an information-set observation."""
    me = obs.viewer
    parts = [_scalars(obs)]

    bfs = list(obs.battlefields)
    for i in range(N_BF):
        if i < len(bfs):
            parts.append(_bf_features(bfs[i], me))
        else:
            parts.append(np.zeros(_PER_BF, dtype=np.float32))

    # Bag-of-counts: my hand, my trash, my board units, opp board units.
    my_board = [u.name for bf in bfs for u in (bf.A if me == "A" else bf.B)]
    my_board += [u.name for u in obs.my_base_units]
    opp_board = [u.name for bf in bfs for u in (bf.B if me == "A" else bf.A)]
    opp_board += [u.name for u in obs.opp_base_units]
    parts.append(_bag(obs.my_hand))
    parts.append(_bag(obs.my_trash))
    parts.append(_bag(my_board))
    parts.append(_bag(opp_board))

    vec = np.concatenate(parts).astype(np.float32)
    assert vec.shape[0] == OBS_DIM, f"encoding {vec.shape[0]} != OBS_DIM {OBS_DIM}"
    return vec


# --- action space -------------------------------------------------------------
# Contiguous slot layout. Offsets computed once; ACTION_DIM is the total width.
_OFF_PASS = 0
_OFF_UNIT = _OFF_PASS + 1                          # MAX_HAND
_OFF_SPELL = _OFF_UNIT + MAX_HAND                  # MAX_HAND * N_BF
_OFF_GEAR = _OFF_SPELL + MAX_HAND * N_BF           # MAX_HAND * N_BF
_OFF_CHAMP = _OFF_GEAR + MAX_HAND * N_BF           # N_BF
_OFF_MOVE = _OFF_CHAMP + N_BF                      # (N_BF+1)^2
_OFF_HIDE = _OFF_MOVE + (N_BF + 1) ** 2            # MAX_HAND * N_BF
_OFF_HIDDEN = _OFF_HIDE + MAX_HAND * N_BF          # N_BF
_OFF_ABIL = _OFF_HIDDEN + N_BF                     # PYKE(1) + GOLD(N_DOM) + ACTIVATED(MAX_ABIL)
ACTION_DIM = _OFF_ABIL + 1 + N_DOM + MAX_ABIL


def action_to_index(action) -> Optional[int]:
    """Map a GameAction (or its raw engine tuple) to its fixed slot, or None if it
    falls outside the encodable space (e.g. a hand slot >= MAX_HAND — rare; such an
    action stays playable via the legal list, just not policy-addressable)."""
    t = action.to_engine() if isinstance(action, GameAction) else tuple(action)
    kind = t[0]
    idx = t[1]
    lane = t[2] if len(t) > 2 else None
    dst = t[3] if len(t) > 3 else None

    def hb(base, slot, nlanes=1, ln=0):  # hand-slot (+lane) bounded helper
        if slot is None or not (0 <= slot < MAX_HAND):
            return None
        if not (0 <= ln < nlanes):
            return None
        return base + slot * nlanes + ln

    if kind == "PASS":
        return _OFF_PASS
    if kind == "UNIT":
        return None if idx is None or not (0 <= idx < MAX_HAND) else _OFF_UNIT + idx
    if kind == "SPELL":
        return hb(_OFF_SPELL, idx, N_BF, lane if isinstance(lane, int) else 0)
    if kind == "GEAR":
        return hb(_OFF_GEAR, idx, N_BF, lane if isinstance(lane, int) else 0)
    if kind == "CHAMPION":
        return _OFF_CHAMP + lane if isinstance(lane, int) and 0 <= lane < N_BF else None
    if kind == "MOVE":
        src = lane
        if not (isinstance(src, int) and isinstance(dst, int)):
            return None
        if not (0 <= src <= N_BF and 0 <= dst <= N_BF):
            return None
        return _OFF_MOVE + src * (N_BF + 1) + dst
    if kind == "HIDE":
        return hb(_OFF_HIDE, idx, N_BF, lane if isinstance(lane, int) else 0)
    if kind == "HIDDEN_PLAY":
        return _OFF_HIDDEN + lane if isinstance(lane, int) and 0 <= lane < N_BF else None
    if kind == "ABILITY":
        ability_id, arg = idx, lane
        if ability_id == "PYKE_LEGEND":
            return _OFF_ABIL
        if ability_id == "GOLD_SACRIFICE":
            di = _DOM_INDEX.get(arg)
            return None if di is None else _OFF_ABIL + 1 + di
        if ability_id == "ACTIVATED":
            return _OFF_ABIL + 1 + N_DOM + arg if isinstance(arg, int) and 0 <= arg < MAX_ABIL else None
    return None


def legal_mask(legal: list) -> np.ndarray:
    """Boolean vector length ACTION_DIM: True at each currently-legal action's slot."""
    mask = np.zeros(ACTION_DIM, dtype=bool)
    for a in legal:
        i = action_to_index(a)
        if i is not None:
            mask[i] = True
    return mask


def index_to_legal_action(index: int, legal: list):
    """The concrete legal action occupying ``index``, or None. Use to turn a
    policy's chosen slot back into a move to play."""
    for a in legal:
        if action_to_index(a) == index:
            return a
    return None


# --- mulligan head (separate: the engine action is a list[int], not a GameAction) --

def encode_mulligan_choice(return_indices) -> np.ndarray:
    """Multi-binary length MAX_HAND: 1 for each hand card to return (engine caps at 2)."""
    v = np.zeros(MAX_HAND, dtype=np.float32)
    for i in return_indices:
        if 0 <= i < MAX_HAND:
            v[i] = 1.0
    return v


def decode_mulligan_choice(vec, threshold: float = 0.5) -> list:
    """Hand indices whose value clears ``threshold``, capped at the engine's 2."""
    chosen = [i for i in range(min(MAX_HAND, len(vec))) if vec[i] >= threshold]
    return chosen[:2]
