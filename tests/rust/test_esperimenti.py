"""incrocio, guidata, continua (scripts/rust/decisione.py, riftbound/rs/decisione_esp.py): le parti economiche.

Partita autonoma ES:3:a con la rete a pesi casuali (come test_finestre.py); la scelta forzata e' provata su una
posizione costruita (tests/audit/audit_helpers.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "tests/audit", ROOT / "tests/rust", ROOT / "scripts/rust"):
    sys.path.insert(0, str(p))

from riftbound.rs import decisione_esp as E  # noqa: E402


# -- pure ------------------------------------------------------------------------------------------

def test_wilson_e_differenza():
    p, lo, hi = E.wilson(50, 100)
    assert p == 0.5 and 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    d, lo, hi = E.differenza(60, 100, 40, 100)
    assert abs(d - 0.2) < 1e-9 and 0 < lo < d < hi < 0.4
    assert E.wilson(0, 0)[0] != E.wilson(0, 0)[0]          # nan


def test_cerca_preferisce_l_uguale_poi_la_sottostringa():
    menu = ["Pass", "Play Vi Peacekeeper to BF0", "Play Vi", "Move Kinkou Initiate base→BF0"]
    assert E.Guida.cerca("play vi", menu) == 2             # uguale, senza maiuscole, prima della sottostringa
    assert E.Guida.cerca("Vi Peacekeeper", menu) == 1
    assert E.Guida.cerca("kinkou initiate base→bf0", menu) == 3
    assert E.Guida.cerca("Punch First", menu) is None


def _evento(menu, point="showdown_action", raw=None):
    return json.dumps({"k": "decision", "seat": "B", "point": point, "menu": menu, "win": {"turn": 9}, "state_raw": raw})


def test_guida_finestre_non_volute_passano_il_turno_no():
    g = E.Guida(["Vi Peacekeeper"], "B", lambda t: None)
    # una finestra dove l'etichetta non e' offerta: si passa e l'etichetta resta
    assert g.ask(_evento(["Pass", "Showdown Punch First @BF0"])) == 0
    assert g.i == 0
    # il turno dove non e' offerta: non legale, si ferma
    with pytest.raises(E.Stop):
        g.ask(_evento(["Pass", "Move Sett Kingpin base→BF0"], "turn_action"))
    assert g.non_legale and g.non_legale[0] == "Vi Peacekeeper"
    # dove e' offerta si gioca e si avanza
    g = E.Guida(["Vi Peacekeeper"], "B", lambda t: None)
    assert g.ask(_evento(["Pass", "Play Vi Peacekeeper to BF0"], "turn_action")) == 1 and g.i == 1
    # sequenza finita: si passa
    assert g.ask(_evento(["Pass", "Play Vi Peacekeeper to BF0"], "turn_action")) == 0


def test_guida_opzionale_e_modo():
    g = E.Guida(["accelerate: no"], "B", lambda t: None)
    ev = json.dumps({"k": "decide_optional", "seat": "B", "args": [{"root": {"o": {"$ref": "c0"}}, "objs": {
        "c0": {"$t": "Card", "name": "Vi", "tapped": False}}}, "accelerate"]})
    assert g.ask(ev) is False and g.i == 1
    assert g.ask(ev) is True                                # senza etichetta: il default del motore


# -- posizione costruita: una scelta forzata -------------------------------------------------------

def _stupefy():
    from audit_helpers import card, setup, unit
    loop, a, _b = setup(active="A")
    loop.gs.battlefields[0].add_unit("B", unit("Pit Rookie"))
    loop.gs.battlefields[0].add_unit("B", unit("First Mate"))
    loop.gs.battlefields[0].held_by = "B"
    a.hand.append(card("Stupefy"))
    return loop


def _gioca_guida(seq):
    import riftbound_rs
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.canon import canonical_state
    righe = []
    g = riftbound_rs.Game.from_canonical(rb.registry("6427b90+D72-D82"), json.dumps(canonical_state(_stupefy().gs)), 1)
    guida = E.Guida(seq, "A", righe.append)
    g.set_script("B")
    g.set_human_agent("A", guida.ask, False, None)
    g.set_side_chooser()
    g.run_actions_end()
    return guida, righe


def test_scelta_forzata_per_etichetta():
    guida, righe = _gioca_guida(["Stupefy", "First Mate"])
    testo = "\n".join(righe)
    assert guida.i == 2 and guida.non_legale is None
    assert "[scelta] " in testo and "First Mate" in testo.split("[scelta]")[1].split("\n")[0]
    # l'altra opzione: Pit Rookie
    guida, righe = _gioca_guida(["Stupefy", "Pit Rookie"])
    assert "Pit Rookie" in "\n".join(righe).split("[scelta]")[1].split("\n")[0]


def test_scelta_non_nominata_va_al_default_senza_consumare():
    guida, _ = _gioca_guida(["Stupefy"])
    assert guida.i == 1 and guida.default >= 1


# -- la partita autonoma ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pos():
    pytest.importorskip("torch")
    from riftbound.rs import decisione_rs as D
    P = {**D.autonoma("ES", 3, None, True, 138), "starter": "a"}
    k = next(r["k"] for r in D.elenca(P) if r["point"] == "turn_action" and r["n_menu"] > 8)
    Pp, e = E.posizione(P, k)
    return D, P, k, Pp, e


def test_rimescola_cambia_i_mazzi_e_lascia_il_resto(pos):
    _D, _P, _k, _Pp, e = pos
    t = E.albero(e["state_raw"])
    r1, r2 = E.rimescola(t, 1), E.rimescola(t, 1)
    assert r1 == r2 and r1 != E.rimescola(t, 2)
    for s in "AB":
        a, b = t["root"][s]["$v"], r1["root"][s]["$v"]
        assert sorted(a["deck"]["$v"]["cards"]) == sorted(b["deck"]["$v"]["cards"])
        assert a["deck"]["$v"]["cards"] != b["deck"]["$v"]["cards"]
        assert a["hand"] == b["hand"] and a["base_units"] == b["base_units"]
    assert t == E.albero(e["state_raw"])                     # l'originale non e' toccato


def test_incrocio_stessi_semi_nelle_quattro_condizioni(pos):
    _D, P, k, _Pp, e = pos
    mosse = [e["menu"][0], e["menu"][1]]
    res = E.incrocio(P, k, [30], mosse, ["Pass"], quota_n=5)
    b = res[0]
    assert b["semi_uguali"] and b["n_semi"] == 30 and b["prefisso_ok"] and len(b["righe"]) == 4
    quota = [r for r in b["righe"] if r["cond"][1]]
    assert all(m["n"] >= 5 for r in quota for m in r["mosse"])
    assert all((r["mosse"][0]["conta"] is not None) == r["cond"][0] for r in b["righe"])   # i piloti solo con finestre
    assert "stessi semi nelle 4 condizioni: sì" in "\n".join(E.testo_incrocio(res, mosse, ["Pass"], k, 5))


def test_guidata_non_legale_e_passi_forzati(pos):
    _D, P, k, Pp, e = pos
    gioca = next(m for m in e["menu"] if m.startswith("Play "))
    righe = []
    r = E.guidata(P, k, [gioca, "etichetta che non esiste"], "passa", righe.append)
    assert r["passi"] == 1 and r["non_legale"] and "NON LEGALE" in "\n".join(righe)
    r = E.guidata(P, k, [gioca, "Pass"], "campione", righe.append)
    assert r["non_legale"] is None and r["passi"] >= 1 and len(r["punti"]) == 2


def test_continuazione_la_prima_mossa_e_forzata(pos):
    _D, P, k, Pp, e = pos
    gioca = next(m for m in e["menu"] if m.startswith("Play ") and " to " not in m and "@" not in m and "gear" not in m)
    nome = gioca[len("Play "):]
    tree = E.albero(e["state_raw"])
    for primo, atteso in ((gioca, True), ("Pass", False)):
        g = E.gioco(Pp, E.rimescola(tree, 5), 5)
        for s in "AB":
            E._agente_campione(g, Pp, s, 11 + (s == "B"), primo if s == Pp["camp"] else None)
        g.set_side_chooser()
        g.run_actions_end()
        assert (nome in {u["card"] for u in json.loads(g.units()) if u["side"] == Pp["camp"]}) is atteso, primo


def test_un_mondo_arriva_alla_fine_ed_e_riproducibile(pos):
    _D, P, k, Pp, e = pos
    tree = E.albero(e["state_raw"])
    a = E.un_mondo(Pp, tree, "Pass", 0, 77)
    b = E.un_mondo(Pp, tree, "Pass", 0, 77)
    assert a["vince"] in ("A", "B", "DRAW") and a["turni"] > e["turn"] // 2
    assert {x: a[x] for x in ("vince", "punti_turno", "punti_fine", "turni")} == \
        {x: b[x] for x in ("vince", "punti_turno", "punti_fine", "turni")}


def test_cli_guidata_incrocio_continua_scrivono_il_rapporto(pos, tmp_path):
    import decisione
    _D, P, k, Pp, e = pos
    base = ["--autonoma", "ES:3:a", "--pesi-casuali", "--k", str(k)]
    gioca = next(m for m in e["menu"] if m.startswith("Play "))
    f1, f2, f3 = tmp_path / "g.txt", tmp_path / "i.txt", tmp_path / "c.txt"
    assert decisione.main(["guidata", *base, "--sequenza", gioca, "Pass", "--out", str(f1)]) == 0
    assert decisione.main(["incrocio", *base, "--iterazioni", "20", "--mosse", e["menu"][0], gioca, "--conta", "Pass",
                           "--quota-n", "4", "--out", str(f2)]) == 0
    assert decisione.main(["continua", *base, "--mosse", e["menu"][0], gioca, "--n", "2", "--out", str(f3)]) == 0
    assert "fine del turno" in f1.read_text() or "fermo" in f1.read_text()
    assert "stessi semi nelle 4 condizioni: sì" in f2.read_text()
    assert "differenza rispetto alla migliore" in f3.read_text() and "vittorie" in f3.read_text()
