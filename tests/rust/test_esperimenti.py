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
    j = json.loads(f3.with_suffix(".json").read_text())
    assert all(len(v["mondi"]) == 2 for v in j["mosse"].values())


def test_un_mondo_si_ferma_al_tetto_di_turni(pos):
    """Oltre max_turns dello stato la continuazione è patta, come play_all_turns (segnalazione di Codex, PR 60)."""
    _D, P, k, Pp, e = pos
    tree = E.albero(e["state_raw"])
    tree["root"]["max_turns"] = tree["root"]["turn"]
    r = E.un_mondo(Pp, tree, "Pass", 0, 77)
    assert r["vince"] in ("A", "B", "DRAW")
    assert r["turni"] <= tree["root"]["turn"] + 1


# -- continua con linee intere ---------------------------------------------------------------------

def test_parse_linea():
    assert E.parse_linea("Play X") == ["Play X"]
    assert E.parse_linea("Play gear Z @BF0 ; Kinkou ; Move A base→BF0 ; Pass") == \
        ["Play gear Z @BF0", "Kinkou", "Move A base→BF0", "Pass"]
    assert E.parse_linea("  A  ;  B  ") == ["A", "B"]
    assert E.parse_linea("Play A;B") == ["Play A;B"]          # il separatore e' " ; "


def test_guida_consegna_si_ferma_al_primo_punto_di_turno_a_sequenza_esaurita():
    g = E.Guida(["Move X"], "B", lambda t: None, consegna=True)
    g._tavolo = lambda raw: "tavolo"
    assert g.ask(_evento(["Pass", "Move X"], "turn_action")) == 1 and g.i == 1
    # finestra a sequenza esaurita: passa e lo conta; il punto di turno: Stop con lo stato
    assert g.ask(_evento(["Pass", "Showdown Z"], "showdown_action")) == 0 and g.finestre_passate == 1
    with pytest.raises(E.Stop):
        g.ask(_evento(["Pass", "Move Y"], "turn_action", raw={"x": 1}))
    assert g.resume == {"x": 1} and g.non_legale is None


def test_guida_consegna_etichetta_non_offerta_devia_e_consegna():
    g = E.Guida(["Move X", "Punch First"], "B", lambda t: None, consegna=True)
    g._tavolo = lambda raw: "tavolo"
    assert g.ask(_evento(["Pass", "Move X"], "turn_action")) == 1
    with pytest.raises(E.Stop):
        g.ask(_evento(["Pass", "Move Y"], "turn_action", raw={"x": 2}))
    assert g.deviazione[0] == 2 and g.deviazione[1] == "Punch First" and g.resume == {"x": 2} and g.non_legale is None


def test_linea_che_devia_conta_il_mondo_e_ne_dice_il_passo(pos):
    _D, P, k, Pp, e = pos
    gioca = next(m for m in e["menu"] if m.startswith("Play "))
    brutta = f"{gioca} ; etichetta che non esiste"
    righe = []
    res = E.continua(P, k, [brutta, e["menu"][0]], 3, 1, righe.append)
    r = res["mosse"][brutta]
    assert r["n"] == 3 and r["deviati"] == 3 and set(r["passi_deviazione"]) <= {2, 3} and len(r["mondi"]) == 3
    assert all(w["deviato"] for w in r["mondi"]) and res["mosse"][e["menu"][0]]["deviati"] == 0
    t = "\n".join(E.testo_continua(res))
    assert "mondi deviati dalla linea 3/3" in t and "appaiata" in t and "Newcombe" in t


def test_differenza_appaiata():
    m, lo, hi = E.differenza_appaiata([1, 1, 0, 1, 0, 1], [0, 1, 0, 0, 0, 1])
    assert abs(m - 1 / 3) < 1e-9 and lo < m < hi
    assert E.differenza_appaiata([1, 0], [1, 0])[0] == 0


def test_linea_legale_arriva_alla_fine_e_conta_le_etichette(pos):
    _D, P, k, Pp, e = pos
    gioca = next(m for m in e["menu"] if m.startswith("Play ") and " to " not in m and "@" not in m and "gear" not in m)
    linea = f"{gioca} ; Pass"
    res = E.continua(P, k, [linea, "Pass"], 2, 1, lambda t: None)
    r = res["mosse"][linea]
    assert r["n"] == 2 and r["etichette"] == 2 and r["consumate"] is not None and 1 <= r["consumate"] <= 2
    assert r["deviati"] <= 2
    assert res["mosse"]["Pass"]["consumate"] is None
    assert "etichette consumate in media" in "\n".join(E.testo_continua(res))
    # riproducibile, e uno stesso mondo giocato a mano coincide
    tree = E.albero(e["state_raw"])
    a = E.un_mondo(Pp, tree, [gioca, "Pass"], 0, 77)
    b = E.un_mondo(Pp, tree, [gioca, "Pass"], 0, 77)
    assert {x: a[x] for x in ("vince", "punti_turno", "punti_fine", "turni", "passi")} == \
        {x: b[x] for x in ("vince", "punti_turno", "punti_fine", "turni", "passi")}


# -- etichette `?` (condizionali), `danni:` / `scelta:` (con ambito), `@finestre` -------------------

def _posizione_conteso(mano_b):
    """A: Kinkou Initiate in base e Punch First in mano; B: Pit Rookie (Might 2) e First Mate (Might 3) al BF0
    (lo tiene), `mano_b` in mano."""
    from audit_helpers import card, setup, unit
    loop, a, b = setup(active="A")
    a.base_units.append(unit("Kinkou Initiate"))
    a.hand.append(card("Punch First"))
    loop.gs.battlefields[0].add_unit("B", unit("Pit Rookie"))
    loop.gs.battlefields[0].add_unit("B", unit("First Mate"))
    loop.gs.battlefields[0].held_by = "B"
    for n in mano_b:
        b.hand.append(card(n))
    return loop


def _gioca_condizionale(seq, mano_b=(), script_b=None):
    import riftbound_rs
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.canon import canonical_state
    righe = []
    g = riftbound_rs.Game.from_canonical(rb.registry("6427b90+D72-D82"),
                                         json.dumps(canonical_state(_posizione_conteso(mano_b).gs)), 1)
    guida = E.Guida(seq, "A", righe.append)
    g.set_script("B", **(script_b or {}))
    g.set_human_agent("A", guida.ask, False, None)
    g.set_side_chooser()
    g.trace_on(guida.osserva)
    try:
        g.run_actions_end()
    except E.Stop:
        pass
    guida._chiudi_attesa(json.loads(g.raw_dump()))
    sopravvissuti = {u["card"] for u in json.loads(g.units()) if u["side"] == "B"}
    return guida, "\n".join(righe), sopravvissuti, g


LINEA = ["Move Kinkou Initiate base→BF0", "Pass", "?Punch First", "danni:Pit Rookie"]


def test_condizionale_saltata_se_l_avversario_passa():
    guida, t, vivi, g = _gioca_condizionale(LINEA)
    assert "?Punch First: condizione non verificata: saltata" in t and guida.saltate == 1
    assert "Showdown Punch First" not in t
    assert guida.i == 4 and "[scelta] combat_damage_order: Pit Rookie" in t   # la 4 e' diventata in attesa dopo la saltata
    assert vivi == {"First Mate"}                                              # Kinkou (3) uccide Pit Rookie per primo


def test_condizionale_giocata_dopo_la_risposta():
    guida, t, vivi, g = _gioca_condizionale(LINEA, ["Punch First"], {"showdown": ["Showdown Punch First"]})
    assert guida.saltate == 0 and "giocata dopo la risposta Showdown Punch First" in t
    assert guida.opp_log and guida.opp_log[0][1].startswith("Showdown Punch First")
    # la risposta di B e' precedente: A ha giocato DOPO (A: Punch First sul proprio Kinkou)
    ev = [e for e in json.loads(g.events()) if e["k"] == "decision" and e["action"][0] != "PASS"]
    assert [e["seat"] for e in ev if e["point"] != "turn_action"][:2] == ["B", "A"]
    assert "[scelta] combat_damage_order: Pit Rookie" in t


def test_analizza_etichette():
    assert [E.Guida.analizza(x)[0] for x in ("?x", "x", "?danni:x")] == [True, False, True]
    assert E.Guida.analizza("?danni: Vex") == (True, "danni", "Vex")
    assert E.Guida.analizza("Scelta:Kinkou") == (False, "scelta", "Kinkou")
    assert E.Guida.analizza("Pass") == (False, None, "Pass")


def test_danni_assegna_a_vex_e_il_default_resta_altrove():
    guida, t, vivi, _g = _gioca_condizionale(["Move Kinkou Initiate base→BF0", "Pass", "danni:First Mate"])
    assert vivi == {"Pit Rookie"} and "combat_damage_order: First Mate" in t
    guida, t, vivi, _g = _gioca_condizionale(["Move Kinkou Initiate base→BF0", "Pass", "danni:Pit Rookie"])
    assert vivi == {"First Mate"}


def _scelta(kind, opzioni):
    return json.dumps({"k": "choice", "seat": "A", "kind": kind, "options_raw": [1, 2], "default": 1, "state_raw": None}), opzioni


def test_danni_non_e_consumata_da_una_scelta_di_bersaglio(monkeypatch):
    for etichetta, atteso_i, scelta in (("danni:Vex", 0, 1), ("Vex", 1, 0), ("scelta:Vex", 1, 0)):
        g = E.Guida([etichetta], "A", lambda t: None)
        ev, opz = _scelta("target:grant_temporary_might", ["target: Vex", "target: Ahri"])
        monkeypatch.setattr(E, "etichette_scelta", lambda e, o=opz: o)
        assert g.ask(ev) == scelta                               # 0 = Vex; 1 = il default del motore
        assert g.i == atteso_i, etichetta
    # la scelta dei danni la consuma, e `scelta:` consuma qualunque scelta
    g = E.Guida(["danni:Vex"], "A", lambda t: None)
    ev, opz = _scelta("combat_damage_order", ["combat_damage_order: Ahri", "combat_damage_order: Vex"])
    monkeypatch.setattr(E, "etichette_scelta", lambda e: opz)
    assert g.ask(ev) == 1 and g.i == 1
    # le etichette con ambito non vincono mai nei menu: la finestra passa
    g = E.Guida(["danni:Pass"], "A", lambda t: None)
    assert g.ask(_evento(["Pass", "Showdown Z"], "showdown_action")) == 0 and g.i == 0


def test_parse_linea_finestre():
    assert E.parse_linea("Play X ; @finestre") == ["Play X"]
    assert E.parse_linea("Play X ; Pass ; @Finestre") == ["Play X", "Pass"]
    assert E.linea_finestre("Play X ; @finestre") and E.linea_finestre("A ; B ; @FINESTRE")
    assert not E.linea_finestre("Play X ; Pass") and not E.linea_finestre("@finestre")


def test_finestre_dopo_la_sequenza_accendono_le_finestre_del_campione(pos, monkeypatch):
    _D, P, k, Pp, e = pos
    gioca = next(m for m in e["menu"] if m.startswith("Play ") and " to " not in m and "@" not in m and "gear" not in m)
    tree = E.albero(e["state_raw"])
    visto = []
    orig = E._agente_campione

    def spia(g, P_, seat, seme, primo=None, finestre=False):
        visto.append((seat, finestre))
        return orig(g, P_, seat, seme, primo, finestre)
    monkeypatch.setattr(E, "_agente_campione", spia)
    r = E.un_mondo(Pp, tree, [gioca, "Pass"], 0, 77, finestre=True)
    assert r["vince"] in ("A", "B", "DRAW") and (Pp["camp"], True) in visto
    assert all(f is False for s, f in visto if s != Pp["camp"])
    visto.clear()
    E.un_mondo(Pp, tree, [gioca, "Pass"], 0, 77)
    assert visto and all(f is False for _s, f in visto)
    # una sola etichetta + @finestre e' una sequenza (non "la prima mossa e poi libero")
    visto.clear()
    res = E.continua(P, k, [f"{gioca} ; @finestre", gioca], 1, 1, lambda t: None)
    assert res["mosse"][f"{gioca} ; @finestre"]["finestre"] and res["mosse"][f"{gioca} ; @finestre"]["consumate"] is not None
    assert res["mosse"][gioca]["consumate"] is None
    assert "con le finestre" in "\n".join(E.testo_continua(res))


def test_condizionale_con_l_avversario_campione_e_in_continua(pos):
    _D, P, k, Pp, e = pos
    gioca = next(m for m in e["menu"] if m.startswith("Play "))
    righe = []
    r = E.guidata(P, k, [gioca, "?Punch First", "Pass"], "campione", righe.append)
    t = "\n".join(righe)
    assert r["non_legale"] is None and ("condizione non verificata: saltata" in t or "giocata dopo la risposta" in t
                                        or "Punch First" in t)
    res = E.continua(P, k, [f"{gioca} ; ?Punch First ; Pass ; @finestre"], 2, 1, lambda t: None)
    assert res["mosse"][list(res["mosse"])[0]]["n"] == 2


def test_danni_condizionale_resta_fino_alla_scelta_dei_danni():
    """`?danni:X`: con la risposta dell'avversario nello showdown i danni vanno a X; senza, l'etichetta si salta e
    l'ordine resta quello del motore (segnalazione di Codex, PR 62)."""
    seq = ["Move Kinkou Initiate base→BF0", "Pass", "?danni:First Mate"]
    guida, t, _vivi, _g = _gioca_condizionale(seq, ["Punch First"], {"showdown": ["Showdown Punch First"]})
    assert guida.saltate == 0 and "[scelta] combat_damage_order: First Mate" in t
    guida, t, _vivi, _g = _gioca_condizionale(seq)
    assert guida.saltate == 1 and "?danni:First Mate: condizione non verificata: saltata" in t
    assert "[scelta] combat_damage_order: First Mate" not in t


def test_condizionale_seguente_eredita_la_risposta():
    """`?Punch First ; ?scelta:Kinkou`: giocata la prima dopo la risposta, la seconda (il bersaglio) vale per la stessa
    risposta; senza risposta si saltano entrambe."""
    seq = ["Move Kinkou Initiate base→BF0", "Pass", "?Punch First", "?scelta:Kinkou", "danni:Pit Rookie"]
    guida, t, vivi, _g = _gioca_condizionale(seq, ["Punch First"], {"showdown": ["Showdown Punch First"]})
    assert guida.saltate == 0 and "[scelta] target:grant_temporary_might: Kinkou Initiate" in t
    assert "[scelta] combat_damage_order: Pit Rookie" in t
    guida, t, vivi, _g = _gioca_condizionale(seq)
    assert guida.saltate == 2 and "[scelta] combat_damage_order: Pit Rookie" in t
