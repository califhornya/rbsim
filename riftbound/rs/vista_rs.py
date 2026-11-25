"""Vista della pagina coach da un dump grezzo (porting, pagina su Rust).

Il motore Rust espone lo stato solo come dump grezzo (`Game.raw_dump()`,
`state_raw` degli eventi di `trace_on()`, `options_raw` / `source_raw` delle
scelte), nel formato di `canon.RawDumper`. Qui lo si ricostruisce in un
`GameState` Python di SOLA LETTURA, così le funzioni di vista del coach
(`Observation.from_state`, `_board_extras`, `action_info`, `option_text`,
`option_ref`, `_card_texts`) funzionano senza modifiche:

  gs, objs = carica(raw)              # raw = {"root": ..., "objs": ...}
  loop = vista_loop(gs)               # un GameLoop mai avviato
  v = vista(gs, loop, side, viewer, point, actions)
  valore(opzione_raw, objs)           # una opzione / source di una scelta

Il motore non deve mai giocare su questo stato; l'unica eccezione sono le
copie che `spell_lane_free` / `_cast_outcome` giocano per confrontare i campi
di una magia: lì il generatore è un segnaposto (il dump ha solo il digest) e
due copie dello stesso stato partono comunque dallo stesso punto.
Segnaposto innocui: `$rng` -> random.Random(0), `$fn` -> `_Fn` (non
chiamabile), campi saltati (`Player.agent`) -> None.
"""
from __future__ import annotations

import dataclasses
import enum
import json
import pkgutil
import random
import typing
from typing import Any, Optional

_CLASSI: Optional[dict] = None


class _Fn:
    """Segnaposto di un `$fn` del dump (un callable temporaneo del motore)."""

    def __init__(self, qualname: str):
        self.qualname = qualname

    def __call__(self, *a, **kw):
        raise RuntimeError(f"vista_rs: {self.qualname} è un segnaposto, il motore non gira su questo stato")

    def __repr__(self) -> str:
        return f"<fn {self.qualname}>"


def _classi() -> dict:
    """Nome -> classe (dataclass ed enum) dei moduli di riftbound.core."""
    global _CLASSI
    if _CLASSI is None:
        import importlib
        import riftbound.core as core
        out: dict = {}
        for m in pkgutil.iter_modules(core.__path__):
            mod = importlib.import_module(f"riftbound.core.{m.name}")
            for name, obj in vars(mod).items():
                if isinstance(obj, type) and obj.__module__ == mod.__name__ \
                        and (dataclasses.is_dataclass(obj) or issubclass(obj, enum.Enum)):
                    out.setdefault(name, obj)
        _CLASSI = out
    return _CLASSI


_HINTS: dict = {}

# Shapes the dataclass hints do not say (a bare `dict`): tuples dump as lists.
_FORME = {
    ("ChainItem", "declared"): Optional[typing.Dict[tuple, tuple]],      # {(run, instr, n): (kind, n, chosen)}
    ("GameState", "delayed_effects"): typing.List[tuple], ("GameState", "delayed_main"): typing.List[tuple],
    ("GameState", "held_hostage"): typing.List[tuple], ("GameState", "turn_cost_changes"): typing.List[tuple],
    ("GameState", "conquer_return"): typing.List[tuple], ("GameState", "staged_showdowns"): typing.List[tuple],
    ("GameState", "spell_spent"): typing.Dict[str, tuple],
    ("GameState", "added_legends"): typing.Dict[str, typing.List[tuple]],
    ("Battlefield", "excess_damage"): typing.Dict[str, tuple], ("Battlefield", "plays_here"): typing.Dict[str, tuple],
    ("UnitInPlay", "death_bonus"): Optional[tuple], ("UnitInPlay", "turn_abilities"): typing.List[tuple],
    ("PendingTrigger", "specs"): typing.List[tuple],
}


def _hints(cls) -> dict:
    if cls not in _HINTS:
        try:
            h = dict(typing.get_type_hints(cls, localns=_classi()))
        except Exception:  # noqa: BLE001 — a hint that cannot be resolved: fields stay untyped
            h = {}
        h.update({f: t for (c, f), t in _FORME.items() if c == cls.__name__})
        _HINTS[cls] = h
    return _HINTS[cls]


def _args(hint) -> list:
    """The alternatives of a hint (Optional[X] -> [X])."""
    if typing.get_origin(hint) is typing.Union or str(typing.get_origin(hint)) == "<class 'types.UnionType'>":
        return [a for a in typing.get_args(hint) if a is not type(None)]
    return [hint]


def _enum_of(hint):
    for a in _args(hint):
        if isinstance(a, type) and issubclass(a, enum.Enum):
            return a
    return None


def _origin(hint):
    for a in _args(hint):
        o = typing.get_origin(a) or a
        if o in (tuple, list, set, frozenset, dict):
            return o, typing.get_args(a)
    return None, ()


def _forme_catena(item) -> None:
    """A chain item's shapes the hints do not say: an ability's `rest` is a
    list of (index, spec) tuples; a declared choice's `chosen` is one option
    (a tuple option dumps as a list holding a side's name), or a list of
    options (a list of tuple options: lists of lists)."""
    ab = item.ability
    if isinstance(ab, dict) and isinstance(ab.get("rest"), list):
        ab["rest"] = [tuple(x) if isinstance(x, list) else x for x in ab["rest"]]
    for slot, (kind, n, got) in list((item.declared or {}).items()):
        if isinstance(got, list):
            got = tuple(got) if any(isinstance(x, str) for x in got) else \
                [tuple(x) if isinstance(x, list) else x for x in got]
        item.declared[slot] = (kind, n, got)


def _opzione(c, v):
    """An option of a choice: a tuple option dumps as a list."""
    return tuple(_opzione(c, x) for x in v) if isinstance(v, list) else c.valore(v)


def _hashable(k):
    """A dict key as the engine had it: a tuple key dumps as a list."""
    return tuple(_hashable(x) for x in k) if isinstance(k, list) else k


class _Carica:
    def __init__(self, raw: dict, objs: Optional[dict] = None):
        self.raw_objs = raw["objs"]
        self.objs: dict = {} if objs is None else objs
        self.specs: Optional[dict] = None

    # -- objects ---------------------------------------------------------
    def crea(self, rid: str):
        """The (empty) object of a raw id; its fields come with `riempi`."""
        o = self.raw_objs[rid]
        t = o["$t"]
        if t == "Card":
            from riftbound.registry.cards_registry import CARD_REGISTRY
            spec = CARD_REGISTRY.get(o.get("name"))
            if spec is not None:
                return spec.instantiate()
            from riftbound.core.cards import Card
            return Card.__new__(Card)          # a card the registry does not know: fields only
        cls = _classi()[t]
        return self._vuoto(cls)

    @staticmethod
    def _vuoto(cls):
        obj = cls.__new__(cls)
        for f in dataclasses.fields(cls):
            if f.default is not dataclasses.MISSING:
                setattr(obj, f.name, f.default)
            elif f.default_factory is not dataclasses.MISSING:
                setattr(obj, f.name, f.default_factory())
        return obj

    def riempi(self, obj, campi: dict) -> None:
        cls = type(obj)
        hints = _hints(cls)
        for k, v in campi.items():
            if k == "$t":
                continue
            obj.__dict__[k] = self.valore(v, hints.get(k))
        if cls.__name__ == "ChainItem":
            _forme_catena(obj)

    def oggetto(self, rid: str):
        if rid in self.objs:
            return self.objs[rid]
        if rid not in self.raw_objs:
            raise KeyError(f"vista_rs: riferimento {rid} senza oggetto")
        obj = self.crea(rid)
        self.objs[rid] = obj                    # before the fields: cycles
        self.riempi(obj, self.raw_objs[rid])
        return obj

    # -- values ----------------------------------------------------------
    def spec(self, key: str):
        if self.specs is None:
            from riftbound.registry.cards_registry import CARD_REGISTRY
            self.specs = CARD_REGISTRY
        if "#" in key and not key.startswith("{"):
            name, _, i = key.rpartition("#")
            return self.specs[name].effects[int(i)]
        from riftbound.registry.cards_registry import EffectSpec
        d = json.loads(key)
        return EffectSpec(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})

    def valore(self, v: Any, hint=None):
        if v is None or isinstance(v, (bool, int)):
            return v
        if isinstance(v, str):
            if v == "$NO_MORE":
                from riftbound.core.loop import NO_MORE
                return NO_MORE
            en = _enum_of(hint) if hint is not None else None
            return en[v] if en is not None else v
        origin, targs = _origin(hint) if hint is not None else (None, ())
        if isinstance(v, list):
            elem = targs[0] if targs and origin in (list, set, frozenset) else None
            if origin is tuple:
                if len(targs) == 2 and targs[1] is Ellipsis:
                    items = [self.valore(x, targs[0]) for x in v]
                elif len(targs) == len(v):
                    items = [self.valore(x, h) for x, h in zip(v, targs)]
                else:
                    items = [self.valore(x) for x in v]
                return tuple(items)
            return [self.valore(x, elem) for x in v]
        if not isinstance(v, dict):
            raise TypeError(f"vista_rs: valore non previsto {v!r}")
        if "$ref" in v:
            return self.oggetto(v["$ref"])
        if "$f" in v:
            return float(v["$f"])
        if "$spec" in v:
            return self.spec(v["$spec"])
        if "$set" in v:
            elem = targs[0] if targs and origin in (set, frozenset) else None
            s = [self.valore(x, elem) for x in v["$set"]]
            return frozenset(s) if origin is frozenset else set(s)
        if "$dict" in v:
            kh, vh = (targs + (None, None))[:2] if origin is dict and len(targs) == 2 else (None, None)
            return {_hashable(self.valore(k, kh)): self.valore(x, vh) for k, x in v["$dict"]}
        if "$v" in v:
            return self.dataclass(v["$v"])
        if "$rng" in v:
            return random.Random(0)
        if "$fn" in v:
            return _Fn(v["$fn"])
        vh = targs[1] if origin is dict and len(targs) == 2 else None
        return {k: self.valore(x, vh) for k, x in v.items()}

    def dataclass(self, campi: dict):
        cls = _classi()[campi["$t"]]
        obj = self._vuoto(cls)
        self.riempi(obj, campi)
        return obj


def carica(raw: dict) -> tuple:
    """A raw dump {"root", "objs"} -> (GameState, objs): `objs` maps each raw
    id to its rebuilt object. Read-only reconstruction (see the module doc)."""
    c = _Carica(raw)
    root = dict(raw["root"])
    root.pop("$rng", None)
    from riftbound.core.state import GameState
    gs = c._vuoto(GameState)
    gs.rng = random.Random(0)
    c.riempi(gs, root)
    for rid in raw["objs"]:                    # objects no field reaches (none expected)
        c.oggetto(rid)
    for p in (gs.A, gs.B):
        p.agent = None
    return gs, c.objs


def valore(raw_value, objs: dict):
    """An `options_raw` / `source_raw` value of a choice -> Python objects.
    `raw_value` is {"root": {"o": v}, "objs": {...}} (as the Rust events carry
    it) or a bare raw value; a reference found in `objs` (the state's, from
    `carica`) is that object, any other is rebuilt from the value's own table
    and added to `objs`."""
    if isinstance(raw_value, dict) and "root" in raw_value and "objs" in raw_value:
        table, v = raw_value["objs"], raw_value["root"]["o"]
    else:
        table, v = {}, raw_value
    c = _Carica({"objs": table}, objs)
    return _opzione(c, v)


def vista_loop(gs):
    """What `action_info` and `legal_actions` read from the loop: a GameLoop
    never started (its own counters at rest) over the rebuilt state."""
    from riftbound.core.loop import GameLoop
    return GameLoop(gs)


def vista(gs, loop, side: str, viewer: str, point, actions) -> dict:
    """The page's view of a decision of `side` as `viewer` sees it: the
    Observation, the board extras, each action's info and the card texts.
    A thin wrapper over riftbound/ai/coach.py."""
    from riftbound.ai.coach import _board_extras, _card_texts, action_info
    from riftbound.core.decisions import Observation
    obs = Observation.from_state(gs, viewer).to_dict()
    extras = _board_extras(gs, viewer)
    return {"obs": obs, "extras": extras, "texts": _card_texts(obs, extras),
            "actions": [action_info(loop, side, viewer, point, a) for a in actions]}


def vista_scelta(gs, viewer: str, options: list, source=None) -> dict:
    """The page's view of an in-move choice: the board and each option's text
    and place on the table (option_text / option_ref), the source's text."""
    from riftbound.ai.coach import _board_extras, _card_texts, option_ref, option_text
    from riftbound.core.decisions import Observation
    obs = Observation.from_state(gs, viewer).to_dict()
    extras = _board_extras(gs, viewer)
    return {"obs": obs, "extras": extras, "texts": _card_texts(obs, extras),
            "options": [{"text": option_text(gs, viewer, o), "ref": option_ref(gs, viewer, o)} for o in options],
            "source": None if source is None else option_text(gs, viewer, source)}
