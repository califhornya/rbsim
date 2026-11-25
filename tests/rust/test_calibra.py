"""Calibrare il campione: impostazioni nuove di arena_rs.game, campi iters/secs
del log di ricerca, scripts/rust/calibra_campione.py misura (pesi casuali, partite brevi)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))


@pytest.fixture(scope="module")
def rete(tmp_path_factory):
    import torch
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(1)
    path = tmp_path_factory.mktemp("rete") / "net.pt"
    save(PPONet(), path)
    return str(path)


def test_iterazioni_fisse_e_log(rete):
    from riftbound.rs import arena_rs
    opz = {"iter_cand": 6, "iter_opp": 6, "probe_cand": True, "log": True}
    task = (40000, "a", "A", "prior_ppo", rete, "mano", None, "EK", None, None, opz)
    r = arena_rs.game(task)
    log = r[8]["log"]
    assert log["cand"] and log["opp"]
    for punto, turno, it, secs, probe in log["cand"] + log["opp"]:
        assert punto in ("turn_action", "reaction", "showdown_action")
        assert it >= 6 and secs >= 0 and probe >= 0       # reazioni e showdown: almeno 8
    assert any(row[0] == "turn_action" and row[2] == 6 for row in log["cand"])
    # lavoro fisso = partita riproducibile
    r2 = arena_rs.game(task)
    assert r[:4] == r2[:4] and r[4:6] == r2[4:6]


def test_task_vecchi_invariati(rete):
    from riftbound.rs import arena_rs
    vecchio = (40001, "b", "B", "prior_ppo", rete, "mano", None, "EK", 0.01, 0.01)
    for task in (vecchio, vecchio + (None,), vecchio + ({},)):
        r = arena_rs.game(task)
        assert len(r) == 9 and r[3] in (0.0, 0.5, 1.0) and r[8] == {}
        assert r[4] and r[5]                             # iterazioni a tempo registrate come prima


def test_log_senza_tempi_resta_confrontabile(rete):
    """Senza set_search_timing il log non ha i campi variabili (le parità lo confrontano)."""
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.arena_rs import MAX_TURNS
    from riftbound.ai.ppo.collect import DECK_OF
    g = rb.build(40002, Path(DECK_OF["E"]), Path(DECK_OF["K"]), "a", MAX_TURNS)
    for seat in ("A", "B"):
        g.set_search_agent(seat, 4, 7, None, None, True)
    g.set_side_chooser()
    g.start()
    rows = json.loads(g.search_log("A"))
    assert rows and all("secs" not in r and "iters" not in r for r in rows)


def test_misura_su_due_partite(rete, tmp_path, monkeypatch):
    import calibra_campione as C
    out = tmp_path / "m"
    monkeypatch.setattr(sys, "argv", ["calibra_campione", "misura", "--ckpt", rete, "--matchup", "EK",
                                      "--partite", "2", "--iterazioni", "6", "--workers", "2", "--out", str(out)])
    C.main()
    j = json.loads((out / "misura.json").read_text())
    assert j["regole"] == "6427b90+D72-D77" and j["N_suggerito"]["turno"] >= 1
    m = j["matchup"]["EK"]
    assert m["partite"] == 2
    assert m["iterazioni_a_0030s"]["turno"]["n"] > 0 and m["iterazioni_a_0030s"]["turno"]["p90"] >= m["iterazioni_a_0030s"]["turno"]["mediana"]
    assert m["secondi_a_6_iterazioni"]["turno"]["n"] > 0
    assert (out / "misura_righe.jsonl").exists()
