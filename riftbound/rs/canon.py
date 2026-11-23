"""Dump canonico dello stato di gioco, per confrontare il motore Python con
quello Rust (porting, F1).

Due passi:
1. `raw_state(gs)`: un albero JSON grezzo dello stato Python, ottenuto
   visitando in modo generico i campi dataclass e gli attributi dinamici
   (`card._kicker_paid`, ...). Gli oggetti con identità (carte, unità, gear
   schierati, campi, ...) diventano {"$ref": id} e vanno in una tabella
   {"$objs": {id: {"$t": tipo, campi...}}}. Un tipo che non so visitare è un
   errore (nessun campo deve sfuggire al confronto). Il motore Rust produce lo
   stesso albero grezzo con i suoi id.
2. `Canon.canonical(raw)`: sostituisce gli id con id canonici stabili e uguali
   nei due linguaggi, assegnati alla prima vista (visita in ordine
   dell'albero) e ricordati fra un dump e il successivo della stessa partita:
   - carta: "A:Pyke Returned:2" (lato in cui è vista la prima volta, nome,
     numero d'ordine fra le carte con quel lato e quel nome); campo: "BF:nome:n";
   - unità / gear schierato: "<id della carta>@<incarnazione>", una nuova
     incarnazione a ogni nuovo oggetto per la stessa carta (rientro in gioco);
   - campo di battaglia: "bf0", "bf1" (indice).
   Copie della stessa carta restano distinte. Le chiavi non stringa dei
   dizionari e gli insiemi diventano liste ordinate dopo la canonicalizzazione.

Il primo diff fra due alberi canonici: `first_diff(a, b)` -> (percorso, a, b).
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from typing import Any, Optional

# Printed card text and static card data: never changed in play, left out of
# the dump (the name identifies the card). `uuid` is random (uuid4).
CARD_STATIC = frozenset({"uuid", "tags", "keywords", "effects", "category", "cost_energy", "cost_power",
                         "cost_power_domain", "domain", "might", "also_gear"})
# Not game state: the agent and the RNG object (the RNG's state goes in "$rng").
SKIP_FIELDS = {"Player": frozenset({"agent"}), "GameState": frozenset({"rng"})}

# Objects compared by identity (a reference each), by class name.
IDENTITY_TYPES = frozenset({"Card", "UnitCard", "SpellCard", "GearCard", "RuneCard", "LegendCard",
                            "BattlefieldCard", "UnitInPlay", "DeployedGear", "Battlefield"})


def _cls_name(obj) -> str:
    return type(obj).__name__


def _is_card(obj) -> bool:
    from riftbound.core.cards import Card
    return isinstance(obj, Card)


_SPEC_INDEX: Optional[dict] = None


def _spec_key(spec) -> str:
    return json.dumps(dataclasses.asdict(spec), sort_keys=True, default=str)


def spec_ref(spec) -> str:
    """An EffectSpec as 'Card name#index' in CARD_REGISTRY (first card with
    an equal spec), else its value."""
    global _SPEC_INDEX
    if _SPEC_INDEX is None:
        from riftbound.registry.cards_registry import CARD_REGISTRY
        _SPEC_INDEX = {}
        for name, cs in CARD_REGISTRY.items():
            for i, s in enumerate(cs.effects):
                _SPEC_INDEX.setdefault(_spec_key(s), f"{name}#{i}")
    key = _spec_key(spec)
    return _SPEC_INDEX.get(key, key)


class RawDumper:
    """Python state -> raw tree. One per dump."""

    def __init__(self):
        self.objs: dict[str, dict] = {}
        self.keep: list = []          # strong refs: id() must not be reused meanwhile

    def ref(self, obj) -> dict:
        key = str(id(obj))
        if key not in self.objs:
            self.objs[key] = {}       # placeholder against cycles
            self.keep.append(obj)
            self.objs[key] = self.fields(obj)
        return {"$ref": key}

    def fields(self, obj) -> dict:
        t = _cls_name(obj)
        card = _is_card(obj)
        out: dict = {"$t": "Card" if card else t}
        skip = SKIP_FIELDS.get(t, frozenset())
        names = [f.name for f in dataclasses.fields(obj)] if dataclasses.is_dataclass(obj) else []
        extra = [k for k in vars(obj) if k not in names] if hasattr(obj, "__dict__") else []
        for k in names + sorted(extra):
            if k in skip or (card and k in CARD_STATIC):
                continue
            out[k] = self.value(getattr(obj, k))
        return out

    def value(self, v: Any):
        if v is None or isinstance(v, (bool, int, str)):
            return v
        if isinstance(v, float):
            return {"$f": repr(v)}
        if isinstance(v, enum.Enum):
            return v.name
        name = _cls_name(v)
        if name in IDENTITY_TYPES or _is_card(v):
            return self.ref(v)
        if name == "EffectSpec":
            return {"$spec": spec_ref(v)}
        if isinstance(v, (list, tuple)):
            return [self.value(x) for x in v]
        if isinstance(v, dict):
            if all(isinstance(k, str) for k in v):
                return {k: self.value(x) for k, x in v.items()}
            return {"$dict": [[self.value(k), self.value(x)] for k, x in v.items()]}
        if isinstance(v, (set, frozenset)):
            return {"$set": [self.value(x) for x in v]}
        if dataclasses.is_dataclass(v):
            return {"$v": self.fields(v)}
        if name == "Random":
            return {"$rng": rng_digest(v)}
        if callable(v):
            return {"$fn": getattr(v, "__qualname__", name)}
        if name == "_NoMore":
            return "$NO_MORE"
        raise TypeError(f"canon: tipo non previsto {name}: {v!r}")


def rng_digest(rng) -> str:
    """The Mersenne Twister state (624 words + index) of a random.Random,
    hashed: equal in Python and Rust when both generators are in step."""
    _version, internal, _gauss = rng.getstate()
    return hashlib.sha256(json.dumps(list(internal)).encode()).hexdigest()[:16]


def raw_state(gs) -> dict:
    d = RawDumper()
    root = d.fields(gs)
    root["$rng"] = rng_digest(gs.rng)
    return {"root": root, "objs": d.objs}


class Canon:
    """Raw ids -> canonical ids, kept across the dumps of one game (one
    engine). For Python raw ids are id(): keep the dumper's strong refs alive
    (`hold`) as long as this Canon lives."""

    def __init__(self):
        self.ids: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self.card_of_unit: dict[str, int] = {}
        self.hold: list = []

    def _new(self, prefix: str) -> str:
        n = self.counts.get(prefix, 0) + 1
        self.counts[prefix] = n
        return f"{prefix}:{n}"

    def canonical(self, raw: dict, dumper_keep: Optional[list] = None) -> dict:
        if dumper_keep:
            self.hold.extend(dumper_keep)
        objs = raw["objs"]
        # Battlefields first, by position.
        for i, r in enumerate(raw["root"].get("battlefields", [])):
            if isinstance(r, dict) and "$ref" in r:
                self.ids.setdefault(r["$ref"], f"bf{i}")
        self._visited: set = set()
        self._assign(raw["root"], objs, path=())
        out_objs: dict = {}
        for rid, cid in self.ids.items():
            if rid in objs:
                out_objs[cid] = self._sub(objs[rid])
        return {"root": self._sub(raw["root"]), "objs": dict(sorted(out_objs.items()))}

    # -- first-sight assignment ---------------------------------------------
    def _assign(self, node, objs, path) -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                self._see(node["$ref"], objs, path)
                return
            for k, v in node.items():
                self._assign(v, objs, path + (k,))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                self._assign(v, objs, path + (i,))

    @staticmethod
    def _side_of(path) -> str:
        for p in reversed(path):
            if isinstance(p, str):
                if p.endswith("_A") or p == "A":
                    return "A"
                if p.endswith("_B") or p == "B":
                    return "B"
        return "X"

    def _see(self, rid: str, objs, path) -> None:
        if rid in self._visited:
            return
        self._visited.add(rid)
        o = objs.get(rid, {})
        if rid not in self.ids:
            t = o.get("$t")
            if t == "Card":
                side = "BF" if path and path[-1] in ("card", "replaced") and "battlefields" in path else self._side_of(path)
                self.ids[rid] = self._new(f"{side}:{o.get('name')}")
            elif t in ("UnitInPlay", "DeployedGear"):
                card = o.get("card")
                if isinstance(card, dict) and "$ref" in card:
                    self._see(card["$ref"], objs, path)
                    base = self.ids[card["$ref"]]
                else:
                    base = "?"
                n = self.card_of_unit.get(base, 0) + 1
                self.card_of_unit[base] = n
                self.ids[rid] = f"{base}@{'g' if t == 'DeployedGear' else ''}{n}"
            elif t == "Battlefield":
                self.ids[rid] = self._new("bf?")
            else:
                self.ids[rid] = self._new(t or "?")
        self._assign(o, objs, path + (rid,))

    # -- substitution ------------------------------------------------------
    def _sub(self, node):
        if isinstance(node, dict):
            if "$ref" in node:
                return "#" + self.ids.get(node["$ref"], "?" + node["$ref"])
            if "$set" in node:
                return {"$set": sorted((self._sub(x) for x in node["$set"]), key=_sort_key)}
            if "$dict" in node:
                return {"$dict": sorted(([self._sub(k), self._sub(v)] for k, v in node["$dict"]),
                                        key=lambda kv: _sort_key(kv[0]))}
            return {k: self._sub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self._sub(x) for x in node]
        return node


def _sort_key(x) -> str:
    return json.dumps(x, sort_keys=True)


def canonical_state(gs, canon: Optional[Canon] = None) -> dict:
    canon = canon or Canon()
    d = RawDumper()
    root = d.fields(gs)
    root["$rng"] = rng_digest(gs.rng)
    return canon.canonical({"root": root, "objs": d.objs}, dumper_keep=d.keep)


def digest(tree) -> str:
    return hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest()[:16]


def first_diff(a, b, path=()):
    """The first difference between two canonical trees: (path, a, b) or None."""
    if type(a) is not type(b):
        return path, a, b
    if isinstance(a, dict):
        for k in list(a) + [k for k in b if k not in a]:
            if k not in a or k not in b:
                return path + (k,), a.get(k, "<assente>"), b.get(k, "<assente>")
            d = first_diff(a[k], b[k], path + (k,))
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, path + (i,))
            if d:
                return d
        if len(a) != len(b):
            return path + ("len",), len(a), len(b)
        return None
    return None if a == b else (path, a, b)
