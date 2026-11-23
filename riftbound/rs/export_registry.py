"""Esporta il CARD_REGISTRY risolto (all_cards.json + cards_registry.py) in un
JSON per il motore Rust: una sola fonte dei dati delle carte. Per ogni carta:
i campi della CardSpec, le EffectSpec (campi, `to_dict`, `merged_params`) e
ciò che `instantiate()` mette sulla carta in gioco (classe Python, categoria,
Might, costi, parole chiave, tag, effetti come dict, damage, repeat_cost,
flow_cost, grants_tags, also_gear).

  python -m riftbound.rs.export_registry [out.json]   (default rust/data/registry.json)
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "rust/data/registry.json"


def _plain(v):
    if isinstance(v, enum.Enum):
        return v.name
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def _spec(es) -> dict:
    from riftbound.rs.canon import spec_ref
    d = {f.name: _plain(getattr(es, f.name)) for f in dataclasses.fields(es)}
    d["to_dict"] = _plain(es.to_dict())
    d["merged"] = _plain(es.merged_params())
    d["spec_ref"] = spec_ref(es)          # how the canonical dump names it
    return d


def export() -> dict:
    from riftbound.registry.cards_registry import CARD_REGISTRY
    cards = []
    for name, cs in CARD_REGISTRY.items():
        inst = cs.instantiate() if cs.category is not None else None
        i = None
        if inst is not None:
            i = {"class": type(inst).__name__, "category": _plain(inst.category), "might": inst.might,
                 "cost_energy": inst.cost_energy, "cost_power": inst.cost_power,
                 "cost_power_domain": _plain(inst.cost_power_domain), "domain": _plain(inst.domain),
                 "keywords": list(inst.keywords), "tags": list(inst.tags), "effects": _plain(inst.effects),
                 "damage": getattr(inst, "damage", None), "repeat_cost": _plain(getattr(inst, "repeat_cost", None)),
                 "flow_cost": _plain(getattr(inst, "flow_cost", None)),
                 "grants_tags": list(getattr(inst, "grants_tags", ()) or ()),
                 "also_gear": bool(getattr(inst, "also_gear", False))}
        cards.append({"name": name, "category": _plain(cs.category), "domain": _plain(cs.domain),
                      "cost_energy": cs.cost_energy, "cost_power": cs.cost_power,
                      "cost_power_domain": _plain(cs.cost_power_domain), "might": cs.might, "damage": cs.damage,
                      "keywords": list(cs.keywords), "tags": list(cs.tags),
                      "effects": [_spec(e) for e in cs.effects], "raw": _plain(cs.raw), "inst": i})
    return {"cards": cards}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    data = export()
    text = json.dumps(data, sort_keys=True, ensure_ascii=False)
    out.write_text(text)
    print(out, len(data["cards"]), "carte", hashlib.sha256(text.encode()).hexdigest()[:16])


if __name__ == "__main__":
    main()
