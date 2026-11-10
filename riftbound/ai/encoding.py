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

The state vector has two parts: DENSE_DIM scalar features (points, energy, runes,
each battlefield's state...), then MAX_TOKENS rows of TOKEN_WIDTH, one per card
the viewer can see: (zone, card id, features). A unit's row carries its state
(Might, damage, ready, stunned, buff, keywords in effect...); a card in a zone
(hand, trash, deck...) its number of copies. The network embeds each card once,
the same wherever it is, and pools the rows zone by zone (net.py).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from riftbound.core.decisions import UNIT_KEYWORDS, GameAction, Observation
from riftbound.registry.cards_registry import CARD_REGISTRY

# --- fixed dimensions ---------------------------------------------------------
N_BF = 3                # two battlefields, plus the one Baron Nashor adds (Baron Pit)
MAX_HAND = 12
MAX_ABIL = 16
MAX_MOVERS = 8          # unit positions per location a MOVE can name
MAX_FACEDOWN = 3        # facedown cards per battlefield a HIDDEN_PLAY can name
DOMAINS = ("FURY", "CALM", "MIND", "BODY", "CHAOS", "ORDER")
N_DOM = len(DOMAINS)
_DOM_INDEX = {d: i for i, d in enumerate(DOMAINS)}

# Card vocabulary: sorted registry names → stable index (order-stable across runs).
CARD_VOCAB: tuple[str, ...] = tuple(sorted(CARD_REGISTRY.keys()))
_CARD_INDEX = {name: i for i, name in enumerate(CARD_VOCAB)}
VOCAB_SIZE = len(CARD_VOCAB)
# Card ids in token rows: 0 = empty row, 1..VOCAB_SIZE = a card, then "unknown".
UNKNOWN_CARD = VOCAB_SIZE + 1
N_CARD_IDS = VOCAB_SIZE + 2

# Where a token's card is, from the viewer's side ("bf0" = battlefield 0).
_LOCATIONS = ("base",) + tuple(f"bf{i}" for i in range(N_BF))
ZONES: tuple[str, ...] = (
    "my_hand", "my_trash", "opp_trash", "my_deck", "my_banished", "opp_banished",
    "my_chain", "opp_chain", "my_legend", "opp_legend", "my_champion", "opp_champion",
    *(f"{w}_units_{loc}" for w in ("my", "opp") for loc in _LOCATIONS),
    *(f"{w}_attached_{loc}" for w in ("my", "opp") for loc in _LOCATIONS),
    "my_base_gear", "opp_base_gear",
    *(f"{w}_deployed_bf{i}" for w in ("my", "opp") for i in range(N_BF)),
    *(f"battlefield_{i}" for i in range(N_BF)),
)
_ZONE = {z: i for i, z in enumerate(ZONES)}
N_ZONES = len(ZONES)

# A unit's row: Might, damage, ready, stunned, token, buffed, empowered,
# Equipment count, then UNIT_KEYWORDS in effect. A card in a zone: copies / 3.
N_TOKEN_FEATURES = 8 + len(UNIT_KEYWORDS)
TOKEN_WIDTH = 2 + N_TOKEN_FEATURES
MAX_TOKENS = 160

# Dense features (see _dense): 14 counts, Power by domain for both players, the
# turn player, the showdown's battlefield, runes ready and by domain for both,
# legends ready, champions available, cards played this turn, per battlefield
# (controller x3, scored by each, facedown card of each, units and Might of each,
# deployed gear of each), units and Might in each base, and the battlefield of a
# Standard Move being declared, the viewer's or the opponent's (§144.3: more
# units may still join it, its showdown hasn't started).
_PER_BF_DENSE = 3 + 2 + 2 + 2 + 2 + 2
DENSE_DIM = 14 + 2 * N_DOM + 1 + N_BF + 2 + 2 * N_DOM + 2 + 2 + 2 + N_BF * _PER_BF_DENSE + 4 + 2 * N_BF

OBS_DIM = DENSE_DIM + MAX_TOKENS * TOKEN_WIDTH


def card_index(name: str) -> Optional[int]:
    return _CARD_INDEX.get(name)


def card_id(name: Optional[str]) -> int:
    """A card's id in token rows (1-based; UNKNOWN_CARD if not in the vocabulary)."""
    i = _CARD_INDEX.get(name) if name else None
    return UNKNOWN_CARD if i is None else i + 1


# --- state encoding -----------------------------------------------------------

def _dense(obs: Observation) -> np.ndarray:
    vs = max(1, obs.victory_score)
    me = obs.viewer
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
    s += [obs.my_power.get(d, 0) / 12.0 for d in DOMAINS]
    s += [obs.opp_power.get(d, 0) / 12.0 for d in DOMAINS]
    s.append(1.0 if obs.active == me else 0.0)
    s += [1.0 if obs.showdown_bf == i else 0.0 for i in range(N_BF)]
    s += [obs.my_runes_ready / 12.0, obs.opp_runes_ready / 12.0]
    s += [obs.my_rune_domains.get(d, 0) / 12.0 for d in DOMAINS]
    s += [obs.opp_rune_domains.get(d, 0) / 12.0 for d in DOMAINS]
    s += [float(obs.my_legend_ready), float(obs.opp_legend_ready)]
    s += [float(obs.my_champion is not None), float(obs.opp_champion is not None)]
    s += [obs.my_cards_played / 5.0, obs.opp_cards_played / 5.0]
    bfs = list(obs.battlefields)
    for i in range(N_BF):
        if i >= len(bfs):
            s += [0.0] * _PER_BF_DENSE
            continue
        bf = bfs[i]
        mine, opp = (bf.A, bf.B) if me == "A" else (bf.B, bf.A)
        ctrl = bf.controller
        s += [float(ctrl == me), float(ctrl is not None and ctrl != me), float(ctrl is None)]
        my_scored, opp_scored = (bf.scored_A, bf.scored_B) if me == "A" else (bf.scored_B, bf.scored_A)
        s += [float(my_scored), float(opp_scored)]
        s += [float(bf.facedowns.count(me)), float(sum(o != me for o in bf.facedowns))]
        s += [len(mine) / 6.0, len(opp) / 6.0]
        s += [sum(u.might for u in mine) / 20.0, sum(u.might for u in opp) / 20.0]
        my_gear, opp_gear = (bf.gear_A, bf.gear_B) if me == "A" else (bf.gear_B, bf.gear_A)
        s += [len(my_gear) / 4.0, len(opp_gear) / 4.0]
    s += [len(obs.my_base_units) / 6.0, len(obs.opp_base_units) / 6.0,
          sum(u.might for u in obs.my_base_units) / 20.0,
          sum(u.might for u in obs.opp_base_units) / 20.0]
    s += [1.0 if obs.my_held_move == i else 0.0 for i in range(N_BF)]
    s += [1.0 if obs.opp_held_move == i else 0.0 for i in range(N_BF)]
    vec = np.asarray(s, dtype=np.float32)
    assert vec.shape[0] == DENSE_DIM, f"dense {vec.shape[0]} != DENSE_DIM {DENSE_DIM}"
    return vec


def _unit_features(u) -> list:
    return [u.might / 10.0, u.damage / 10.0, float(u.ready), float(u.stunned),
            float(u.is_token), float(u.buffed), float(u.empowered), len(u.gear) / 3.0] + \
        [float(k in u.keywords) for k in UNIT_KEYWORDS]


def _tokens(obs: Observation) -> list:
    """(zone, card id, features) rows, most important first (a full table drops
    the end: deck, banished)."""
    me = obs.viewer
    rows: list = []

    def card(zone, name, feats=None):
        rows.append((_ZONE[zone], card_id(name), feats or [1.0 / 3.0] + [0.0] * (N_TOKEN_FEATURES - 1)))

    def counted(zone, names):
        counts: dict = {}
        for n in names:
            counts[n] = counts.get(n, 0) + 1
        for n in sorted(counts):
            card(zone, n, [counts[n] / 3.0] + [0.0] * (N_TOKEN_FEATURES - 1))

    bfs = list(obs.battlefields)
    units = {("my", "base"): obs.my_base_units, ("opp", "base"): obs.opp_base_units}
    for i, bf in enumerate(bfs[:N_BF]):
        mine, opp = (bf.A, bf.B) if me == "A" else (bf.B, bf.A)
        units[("my", f"bf{i}")], units[("opp", f"bf{i}")] = mine, opp
    for (who, loc), us in units.items():
        for u in us:
            card(f"{who}_units_{loc}", u.name, _unit_features(u))
    counted("my_chain", obs.my_chain)
    counted("opp_chain", obs.opp_chain)
    for zone, name, ready in (("my_legend", obs.my_legend, obs.my_legend_ready),
                              ("opp_legend", obs.opp_legend, obs.opp_legend_ready)):
        if name:
            card(zone, name, [float(ready)] + [0.0] * (N_TOKEN_FEATURES - 1))
    # The legends Neeko Blending In added: legends of that player too.
    for zone, added in (("my_legend", obs.my_added_legends), ("opp_legend", obs.opp_added_legends)):
        for name, ready in added:
            card(zone, name, [float(ready)] + [0.0] * (N_TOKEN_FEATURES - 1))
    for zone, name in (("my_champion", obs.my_champion), ("opp_champion", obs.opp_champion)):
        if name:
            card(zone, name)
    for i, bf in enumerate(bfs[:N_BF]):
        if bf.named:
            card(f"battlefield_{i}", bf.named)
    counted("my_hand", obs.my_hand)
    for (who, loc), us in units.items():
        counted(f"{who}_attached_{loc}", [g for u in us for g in u.gear])
    counted("my_base_gear", obs.my_base_gear)
    counted("opp_base_gear", obs.opp_base_gear)
    for i, bf in enumerate(bfs[:N_BF]):
        my_gear, opp_gear = (bf.gear_A, bf.gear_B) if me == "A" else (bf.gear_B, bf.gear_A)
        counted(f"my_deployed_bf{i}", my_gear)
        counted(f"opp_deployed_bf{i}", opp_gear)
    counted("my_trash", obs.my_trash)
    counted("opp_trash", obs.opp_trash)
    counted("my_banished", obs.my_banished)
    counted("opp_banished", obs.opp_banished)
    counted("my_deck", obs.my_deck)
    return rows


def encode_observation(obs: Observation) -> np.ndarray:
    """Fixed-size float32 encoding of an information-set observation: the dense
    features, then the token table (see the module docstring)."""
    table = np.zeros((MAX_TOKENS, TOKEN_WIDTH), dtype=np.float32)
    for r, (zone, cid, feats) in enumerate(_tokens(obs)[:MAX_TOKENS]):
        table[r, 0] = zone
        table[r, 1] = cid
        table[r, 2:] = feats
    vec = np.concatenate([_dense(obs), table.reshape(-1)])
    assert vec.shape[0] == OBS_DIM, f"encoding {vec.shape[0]} != OBS_DIM {OBS_DIM}"
    return vec


def token_rows(vec: np.ndarray) -> list:
    """The card rows of an encoded state as (zone, card name, features): for
    tests and debugging."""
    table = np.asarray(vec[DENSE_DIM:]).reshape(MAX_TOKENS, TOKEN_WIDTH)
    out = []
    for row in table:
        cid = int(round(row[1]))
        if cid == 0:
            continue
        name = CARD_VOCAB[cid - 1] if 1 <= cid <= VOCAB_SIZE else "?"
        out.append((ZONES[int(round(row[0]))], name, row[2:]))
    return out


# --- action space -------------------------------------------------------------
# Contiguous slot layout. Offsets computed once; ACTION_DIM is the total width.
# A location (where a unit is played, moves from or to) is 0 for the base, then
# 1 + each battlefield's index: the engine's base index is the number of
# battlefields (2, or 3 with the Baron Pit), so each mapping takes n_bf.
_OFF_PASS = 0
_OFF_UNIT = _OFF_PASS + 1                          # MAX_HAND * (N_BF+1): base, then each BF
_OFF_SPELL = _OFF_UNIT + MAX_HAND * (N_BF + 1)     # MAX_HAND * N_BF
_OFF_GEAR = _OFF_SPELL + MAX_HAND * N_BF           # MAX_HAND * N_BF
_OFF_CHAMP = _OFF_GEAR + MAX_HAND * N_BF           # N_BF
_OFF_MOVE = _OFF_CHAMP + N_BF                      # (N_BF+1)^2 * MAX_MOVERS
_OFF_HIDE = _OFF_MOVE + (N_BF + 1) ** 2 * MAX_MOVERS  # (MAX_HAND + the champion) * N_BF
_OFF_HIDDEN = _OFF_HIDE + (MAX_HAND + 1) * N_BF    # N_BF * MAX_FACEDOWN
_OFF_ABIL = _OFF_HIDDEN + N_BF * MAX_FACEDOWN      # ACTIVATED(MAX_ABIL)
ACTION_DIM = _OFF_ABIL + MAX_ABIL


def _location(i, n_bf: int) -> Optional[int]:
    """A location's slot: the base (engine index n_bf, or None) 0, battlefield i
    i + 1; None if the action space has no room for it."""
    if i is None or i == n_bf:
        return 0
    if isinstance(i, int) and 0 <= i < min(n_bf, N_BF):
        return i + 1
    return None


def action_to_index(action, n_bf: int) -> Optional[int]:
    """Map a GameAction (or its raw engine tuple) to its fixed slot, or None if it
    falls outside the encodable space (e.g. a hand slot >= MAX_HAND — rare; such an
    action stays playable via the legal list, just not policy-addressable).
    `n_bf`: the game's number of battlefields (the engine's base index)."""
    t = action.to_engine() if isinstance(action, GameAction) else tuple(action)
    kind = t[0]
    idx = t[1]
    lane = t[2] if len(t) > 2 else None
    dst = t[3] if len(t) > 3 else None

    def hb(base, slot, nlanes=1, ln=0, rows=MAX_HAND):  # hand-slot (+lane) bounded helper
        if not isinstance(slot, int) or not (0 <= slot < rows):
            return None
        if not isinstance(ln, int) or not (0 <= ln < nlanes):
            return None
        return base + slot * nlanes + ln

    if kind == "PASS":
        return _OFF_PASS
    if kind == "UNIT":
        # Where it is played: base (dst None) or battlefield dst.
        return hb(_OFF_UNIT, idx, N_BF + 1, _location(dst, n_bf))
    if kind == "SPELL":
        return hb(_OFF_SPELL, idx, N_BF, lane if isinstance(lane, int) else 0)
    if kind == "GEAR":
        return hb(_OFF_GEAR, idx, N_BF, lane if isinstance(lane, int) else 0)
    if kind == "CHAMPION":
        return _OFF_CHAMP + lane if isinstance(lane, int) and 0 <= lane < N_BF else None
    if kind == "MOVE":
        if not (isinstance(lane, int) and isinstance(dst, int)):
            return None
        src, to = _location(lane, n_bf), _location(dst, n_bf)
        if src is None or to is None:
            return None
        unit = 0 if idx is None else idx   # None = the first ready unit there
        if not (isinstance(unit, int) and 0 <= unit < MAX_MOVERS):
            return None
        return _OFF_MOVE + (src * (N_BF + 1) + to) * MAX_MOVERS + unit
    if kind == "HIDE":
        # A hand card, or the champion from the Champion Zone (§811.1.b).
        slot = MAX_HAND if idx == "champion" else idx
        return hb(_OFF_HIDE, slot, N_BF, lane if isinstance(lane, int) else 0, rows=MAX_HAND + 1)
    if kind == "HIDDEN_PLAY":
        # idx: the card's slot in that battlefield's Facedown Zone (None: the first).
        return hb(_OFF_HIDDEN, lane, MAX_FACEDOWN, idx or 0, rows=N_BF)
    if kind == "ABILITY":
        ability_id, arg = idx, lane
        if ability_id == "ACTIVATED":
            return _OFF_ABIL + arg if isinstance(arg, int) and 0 <= arg < MAX_ABIL else None
    return None


def legal_mask(legal: list, n_bf: int) -> np.ndarray:
    """Boolean vector length ACTION_DIM: True at each currently-legal action's slot."""
    mask = np.zeros(ACTION_DIM, dtype=bool)
    for a in legal:
        i = action_to_index(a, n_bf)
        if i is not None:
            mask[i] = True
    return mask


def index_to_legal_action(index: int, legal: list, n_bf: int):
    """The concrete legal action occupying ``index``, or None. Use to turn a
    policy's chosen slot back into a move to play."""
    for a in legal:
        if action_to_index(a, n_bf) == index:
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
