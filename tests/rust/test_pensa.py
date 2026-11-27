"""Pensare di piu' (riftbound/rs/pensa.py): aggregazione della latenza e arena piccola con ripresa e rifiuto."""
from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("riftbound_rs", reason="estensione Rust non installata")

from riftbound.rs import pensa as P  # noqa: E402


def test_latenza_su_righe_sintetiche():
    fatte = {
        ("EK", 1, "A"): {"log": {"cand": [[1, 10, 1.0], [1, 10, 2.0], [2, 10, 4.0]], "opp": [[1, 5, 0.5]]}},
        ("EK", 1, "B"): {"log": {"cand": [[1, 10, 3.0]], "opp": []}},
    }
    lat = P.latenza(fatte)
    d, t = lat["cand"]["decisione"], lat["cand"]["turno"]
    assert d["n"] == 4 and d["max"] == 4.0 and d["media"] == pytest.approx(2.5) and d["mediana"] == pytest.approx(2.5)
    assert t["n"] == 3      # turno 1 = 1+2, turno 2 = 4, altra partita 3
    assert t["media"] == pytest.approx(10 / 3) and t["max"] == 4.0 and t["mediana"] == 3.0
    assert t["p95"] == pytest.approx(3.9) and t["p99"] == pytest.approx(3.98)
    assert lat["opp"]["turno"]["n"] == 1 and lat["opp"]["decisione"]["media"] == 0.5


def test_arena_piccola(tmp_path):
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(3)
    ck = tmp_path / "rete.pt"
    save(PPONet().eval(), ck)
    out = tmp_path / "pensa"
    righe = P.arena(["EK"], 1, out, ck, iter_pensa=20, iter_base=6, n_boot=100, print_=lambda *_: None)
    testo = (out / "arena.txt").read_text()
    assert "per decisione cercata" in testo and "per turno" in testo and "limite inferiore > 50%" in testo
    assert "max per turno <= 5 min" in testo and any(x.startswith("criterio:") for x in righe)
    f = out / "arena_righe.jsonl"
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    assert len(rows) == 2 and all(r["log"]["cand"] and r["log"]["opp"] for r in rows)
    assert {x[1] for r in rows for x in r["log"]["cand"] if x[1]} == {20}
    assert max(x[1] for r in rows for x in r["log"]["opp"]) < 20          # l'avversario fa il suo lavoro (6, con qualche iterazione in piu')
    res = json.loads((out / "arena.json").read_text())
    assert res["latenza"]["cand"]["turno"]["n"] > 0 and isinstance(res["limite_inferiore_sopra_50"], bool)
    man = json.loads(f.with_name(f.name + ".provenienza.json").read_text())
    assert man["iter_pensa"] == 20 and man["iter_base"] == 6
    with pytest.raises(ValueError):
        P.arena(["EK"], 1, out, ck, iter_pensa=21, iter_base=6, print_=lambda *_: None)
    P.arena(["EK"], 1, out, ck, iter_pensa=20, iter_base=6, n_boot=100, print_=lambda *_: None)
    assert f.read_text().splitlines() == [json.dumps(r) for r in rows]     # la ripresa non rigioca
