"""Variante (d) dell'arena di sviluppo (prior del campione, valore della rete nuova) e confronto appaiato."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytest.importorskip("riftbound_rs")
torch = pytest.importorskip("torch")

from riftbound.rs import arena_rs, generazione, raccolta  # noqa: E402


def _net(seme):
    from riftbound.ai.ppo.model import PPONet
    torch.manual_seed(seme)
    return PPONet().eval()


@pytest.fixture(scope="module")
def reti(tmp_path_factory):
    from riftbound.ai.ppo.model import save
    d = tmp_path_factory.mktemp("reti")
    save(_net(0), d / "campione.pt")
    save(_net(1), d / "rete.pt")
    return str(d / "campione.pt"), str(d / "rete.pt")


def _arena(reti, righe, varianti):
    camp, rete = reti
    return generazione.arena(rete, camp, ["EK"], 2, raccolta.REGOLE_DEFAULT, righe, 1, 6, varianti, lambda t: None)


@pytest.fixture(scope="module")
def righe_d(reti, tmp_path_factory):
    r = tmp_path_factory.mktemp("d") / "righe.jsonl"
    return r, _arena(reti, r, ("d",))


@pytest.fixture(scope="module")
def righe_bc(reti, tmp_path_factory):
    r = tmp_path_factory.mktemp("bc") / "righe.jsonl"
    return r, _arena(reti, r, ("b", "c"))


@pytest.mark.parametrize("v", ["b", "c", "d"])
def test_gioca_sceglie_checkpoint_e_valore(v, monkeypatch):
    visto = {}

    def finto(task):
        visto["task"] = task
        return (0, 0, 0, 0.5, 0, 0, 0, 0, {})

    monkeypatch.setattr(arena_rs, "game", finto)
    generazione._gioca({"seme": 1, "mu": "EK", "posto": "A", "variante": v, "rete": "RETE", "campione": "CAMP",
                        "regole": raccolta.REGOLE_DEFAULT, "iterazioni": 6})
    t = visto["task"]
    opz = t[-1]
    assert t[6] == "CAMP"
    if v == "d":
        assert t[4] == "CAMP" and opz["vc_cand"] == "RETE" and opz["vr_cand"] == 0.2
    elif v == "c":
        assert t[4] == "RETE" and "vc_cand" not in opz and opz["vr_cand"] == 0.2
    else:
        assert t[4] == "RETE" and "vc_cand" not in opz and "vr_cand" not in opz


def test_manifest_b_c_invariato(reti, tmp_path):
    righe = tmp_path / "r.jsonl"
    camp, rete = reti
    generazione.arena(rete, camp, [], 1, raccolta.REGOLE_DEFAULT, righe, 1, 6, ("b", "c"), lambda t: None)
    m = json.loads(righe.with_name(righe.name + ".provenienza.json").read_text())
    assert m["ricerca"] == {v: generazione._opz(p, 6, False) for v, p in {"b": 0.0, "c": 0.2}.items()}


def test_manifest_con_d(righe_d):
    m = json.loads(righe_d[0].with_name("righe.jsonl.provenienza.json").read_text())
    assert set(m["ricerca"]) == {"b", "c", "d"}
    assert m["ricerca"]["d"] == generazione._opz(0.2, 6, False) | {"vc_cand": "rete", "prior": "campione"}


def test_arena_con_d(righe_d):
    righe, res = righe_d
    rr = [json.loads(x) for x in righe.read_text().splitlines()]
    assert len(rr) == 4 and {r["variante"] for r in rr} == {"d"}
    assert set(res["varianti"]) == {"d"} and res["varianti"]["d"]["chiamate_rete"]["candidato"][0] > 0
    assert generazione.testo_arena(res)[-1].startswith("durata")


def test_confronto_con_se_stesso_e_fra_file(righe_d, righe_bc, tmp_path):
    d, bc = righe_d[0], righe_bc[0]
    z = generazione.confronto_appaiato(d, "d", d, "d", n_boot=200)
    assert z["totale"] == [0, 0, 0] and z["coppie"] == {"EK": 2}
    r = generazione.confronto_appaiato(d, "d", bc, "c", n_boot=200)
    assert r["coppie"] == {"EK": 2} and -1 <= r["totale"][0] <= 1
    assert generazione.testo_confronto([r])[0].startswith("d − c:")
    cb = generazione.confronto_appaiato(bc, "c", bc, "b", n_boot=200)
    assert cb["x"] == "c"
    # manifest alterato: regole diverse
    copia = tmp_path / "copia.jsonl"
    copia.write_text(bc.read_text())
    man = bc.with_name(bc.name + ".provenienza.json")
    m = json.loads(man.read_text())
    m["regole"] = "altre"
    copia.with_name(copia.name + ".provenienza.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="regole"):
        generazione.confronto_appaiato(d, "d", copia, "c", n_boot=200)
