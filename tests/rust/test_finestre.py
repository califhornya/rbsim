"""Opzione `finestre` della ricerca del campione (rust/rbsim-core/src/search.rs, `Pilota`) e quota alla radice.

Le simulazioni della ricerca giocavano senza agenti: ai due posti le finestre di reazione e di showdown erano
due passi. Con `finestre` (default spento, tutto identico) ogni posto della copia ha un pilota; la ricerca di una
finestra riprende il ciclo di priorita' esattamente da dove il ciclo vero era (posto interrogato, passi di fila:
`Game.win_chain` / `win_show`) invece di chiudere per passi.

Qui i piloti sono copioni (`set_search_pilot_script`: prefissi di etichetta per punto, poi passo) e la diagnosi tiene
per ogni simulazione le giocate dei piloti e dove la finestra e' finita. Posizioni costruite in Python
(tests/audit/audit_helpers.py) e giocate su Rust; seat A cerca, B e' un copione.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/audit"))
sys.path.insert(0, str(ROOT / "tests/rust"))
sys.path.insert(0, str(ROOT / "scripts/rust"))

from audit_helpers import card, hide, setup, unit  # noqa: E402
from test_d72_d76 import rust  # noqa: E402

PROFILO = "6427b90+D72-D82"
ITER = 24


def _gioca(loop, b_script, *, finestre=True, pilota=None, quota=None, iterazioni=ITER):
    """A cerca (senza prior), B segue `b_script`; gioca fino alla fine del segmento. -> diag del seat A."""
    g = rust(loop, PROFILO, A={}, B=b_script)
    g.set_search_agent("A", iterazioni, 1)
    if finestre:
        g.set_search_finestre("A", True)
    if pilota is not None:
        g.set_search_pilot_script("A", **pilota)
    if quota is not None:
        g.set_search_quota_at("A", 0, quota[0], quota[1])
    g.set_side_chooser()
    g.run_segment(1)
    return json.loads(g.search_finestre_diag("A"))


def _sims(diag, figlio):
    assert diag, "nessuna diagnosi"
    return [s for s in diag[0]["sims"] if s["child"].startswith(figlio)]


# -- finestra aperta: catena ----------------------------------------------------------------------------

def _catena():
    """B (attivo) lancia Discipline al BF0 e passa; tocca ad A (passi registrati: 1). A ha Discipline e Stupefy,
    B un'altra Stupefy per rispondere."""
    loop, a, b = setup(active="B")
    loop.gs.battlefields[0].add_unit("A", unit("Pit Rookie"))
    loop.gs.battlefields[0].add_unit("B", unit("First Mate"))
    loop.gs.battlefields[0].held_by = "B"
    b.hand.extend([card("Discipline"), card("Stupefy")])
    a.hand.extend([card("Discipline"), card("Stupefy"), card("Stupefy")])
    return loop


def test_catena_noi_agiamo_loro_rispondono_noi_rispondiamo_si_chiude():
    pilota = dict(a_reaction=["PASS", "React Stupefy"], b_reaction=["React Stupefy", "PASS"])
    diag = _gioca(_catena(), {"main": ["Cast Discipline"]}, pilota=pilota)
    sims = _sims(diag, "React Discipline")
    assert sims
    atteso = [["A", "reaction", "PASS"],                    # noi: la catena e' nostra, in cima
              ["B", "reaction", "React Stupefy @BF0"],      # loro rispondono
              ["B", "reaction", "PASS"],                    # (la risposta e' in cima: tocca ancora a loro)
              ["A", "reaction", "React Stupefy @BF0"],      # noi controrispondiamo
              ["A", "reaction", "PASS"],
              ["B", "reaction", "PASS"]]                    # due passi di fila: la catena si chiude
    for s in sims:
        w = s["window"]
        assert [x[:2] + [x[2].split(" @")[0]] for x in w[:6]] == [x[:2] + [x[2].split(" @")[0]] for x in atteso], w
        assert all(x[2] == "PASS" for x in w[6:]), w        # poi si risolve: nessuno ha altro da giocare
        assert s["end"] == {"chain": 0, "showdown": False}


def test_catena_loro_avevano_passato_passiamo_si_chiude_subito():
    pilota = dict(a_reaction=["React Stupefy"], b_reaction=["React Stupefy"])  # se fossero interrogati, giocherebbero
    diag = _gioca(_catena(), {"main": ["Cast Discipline"]}, pilota=pilota)
    sims = _sims(diag, "Pass")
    assert sims, [c["label"] for c in diag[0]["children"]]
    for s in sims:
        assert s["window"] == [], s                         # nessuno interrogato: 1 passo registrato + il nostro
        assert s["end"] == {"chain": 0, "showdown": False}


# -- finestra aperta: showdown --------------------------------------------------------------------------

def _showdown():
    """B (attivo) muove First Mate al BF0 dove c'e' Pit Rookie di A: showdown, B passa, tocca ad A (passi: 1)."""
    loop, a, b = setup(active="B")
    loop.gs.battlefields[0].add_unit("A", unit("Pit Rookie"))
    loop.gs.battlefields[0].held_by = "A"
    b.base_units.append(unit("First Mate"))
    a.hand.extend([card("Discipline"), card("Stupefy"), card("Stupefy")])
    b.hand.append(card("Stupefy"))
    return loop


def test_showdown_noi_agiamo_loro_rispondono_noi_rispondiamo_si_chiude():
    pilota = dict(a_reaction=["PASS", "React Stupefy"], b_reaction=["React Stupefy", "PASS"])
    diag = _gioca(_showdown(), {"main": ["Move First Mate base→BF0"]}, pilota=pilota)
    sims = _sims(diag, "Showdown Discipline")
    assert sims
    atteso = [["A", "reaction", "PASS"], ["B", "reaction", "React Stupefy"], ["B", "reaction", "PASS"],
              ["A", "reaction", "React Stupefy"], ["A", "reaction", "PASS"], ["B", "reaction", "PASS"]]
    for s in sims:
        w = s["window"]
        assert [x[:2] + [x[2].split(" @")[0]] for x in w[:6]] == atteso, w
        # dopo la catena il ciclo di showdown prosegue come dopo un'azione: tocca a B, poi ad A: due passi
        assert w[-2:] == [["B", "showdown", "PASS"], ["A", "showdown", "PASS"]], w
        assert s["end"] == {"chain": 0, "showdown": False}


def test_showdown_loro_avevano_passato_passiamo_si_chiude_subito():
    pilota = dict(a_showdown=["Showdown Stupefy"], b_showdown=["Showdown Stupefy"])
    diag = _gioca(_showdown(), {"main": ["Move First Mate base→BF0"]}, pilota=pilota)
    sims = _sims(diag, "Pass")
    assert sims
    for s in sims:
        assert s["window"] == [], s
        assert s["end"] == {"chain": 0, "showdown": False}  # finish_showdown fatto


def test_con_finestre_spente_la_finestra_si_chiude_per_passi_come_prima():
    diag = _gioca(_showdown(), {"main": ["Move First Mate base→BF0"]}, finestre=False,
                  pilota=dict(a_showdown=["Showdown Stupefy"]))
    assert diag and diag[0]["sims"] and all(not s["window"] for s in diag[0]["sims"])     # nessun pilota
    assert all(s["end"] == {"chain": 0, "showdown": False} for s in diag[0]["sims"])


# -- ricerca di turno ----------------------------------------------------------------------------------

def _turno():
    """A (attivo, cerca) ha Pit Rookie in base; B tiene il BF0 con First Mate, ha Stupefy in mano e Edge of Night
    coperto al BF0."""
    loop, a, b = setup(active="A")
    a.base_units.append(unit("Pit Rookie"))
    loop.gs.battlefields[0].add_unit("B", unit("First Mate"))
    loop.gs.battlefields[0].held_by = "B"
    b.hand.append(card("Stupefy"))
    hide(loop, "B", 0, "Edge of Night")
    return loop


@pytest.mark.parametrize("copione,giocata", [
    (["Showdown Stupefy"], "Showdown Stupefy @BF0"),
    (["Play Edge of Night"], "Play Edge of Night from Hidden @BF0"),
])
def test_turno_entrando_in_un_campo_occupato_l_avversario_gioca(copione, giocata):
    diag = _gioca(_turno(), {}, pilota=dict(b_showdown=copione))
    fig = {c["label"]: c for c in diag[0]["children"]}
    mossa = fig["Move Pit Rookie base→BF0"]
    assert mossa["n"] > 0 and any(x[:3] == ["B", "showdown", giocata] and x[3] >= 1 for x in mossa["tally"]), mossa["tally"]
    assert not fig["Pass"]["tally"]


def test_turno_senza_finestre_nessuno_gioca_la_finestra():
    diag = _gioca(_turno(), {}, finestre=False, pilota=dict(b_showdown=["Showdown Stupefy"]))
    assert all(not s["window"] for s in diag[0]["sims"])


def test_i_mondi_nascosti_non_cambiano_con_finestre_e_quota():
    """I semi delle simulazioni (uno per simulazione, dalla RNG della ricerca) sono gli stessi: i piloti non
    pescano da `self.rng` e la quota non aggiunge estrazioni."""
    solo = dict(a_showdown=[], b_showdown=["Showdown Stupefy"])
    spento = _gioca(_turno(), {}, finestre=False, pilota=solo)
    acceso = _gioca(_turno(), {}, finestre=True, pilota=solo)
    quota = _gioca(_turno(), {}, finestre=True, pilota=solo, quota=(["Move"], 9))
    assert len(spento[0]["seeds"]) == ITER and spento[0]["seeds"] == acceso[0]["seeds"] == quota[0]["seeds"]


def test_quota_alla_radice_della_ricerca_di_turno():
    diag = _gioca(_turno(), {}, finestre=False, quota=(["move pit rookie"], 7), iterazioni=40,
                  pilota=dict())
    fig = {c["label"]: c for c in diag[0]["children"]}
    mosse = [c for k, c in fig.items() if k.startswith("Move Pit Rookie")]
    assert len(mosse) == 2 and all(c["n"] >= 7 for c in mosse), [(k, c["n"]) for k, c in fig.items()]
    # senza quota il radice non e' forzato: la diagnosi non c'e' (nessuna opzione acceso)
    assert _gioca(_turno(), {}, finestre=False) == []


# -- il bridge del campione --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def partita():
    pytest.importorskip("torch")
    from riftbound.rs import decisione_rs as D
    P = {**D.autonoma("ES", 3, None, True, 138), "starter": "a"}
    k = next(r["k"] for r in D.elenca(P) if r["point"] == "turn_action" and r["n_menu"] > 5)
    return D, P, k


def test_rifai_con_finestre_e_con_quota_gira(partita):
    D, P, k = partita
    base = D.rifai(P, k, 138, posizione=False)
    assert "diagnosi" not in base
    r = D.rifai(P, k, 138, posizione=False, finestre=True)
    d = r["diagnosi"]
    assert r["prefisso_ok"] and d["k"] == k and d["finestre"] and sum(c["n"] for c in d["children"]) >= 130
    assert any(c["tally"] for c in d["children"])          # i piloti hanno giocato (almeno dei passi) nelle finestre
    scelto = d["children"][1]["label"]
    r2 = D.rifai(P, k, 138, posizione=False, finestre=True, quota=([scelto], 40))
    assert next(c for c in r2["diagnosi"]["children"] if c["label"] == scelto)["n"] >= 40


def test_cli_rifai_stampa_visite_q_e_giocate(partita, capsys):
    D, P, k = partita
    import decisione
    argv = ["rifai", "--autonoma", "ES:3:a", "--k", str(k), "--iterazioni", "138", "--pesi-casuali", "--finestre",
            "--quota", "Pass", "--quota-n", "20", "--attese", "Pass"]
    assert decisione.main(argv) == 0
    out = capsys.readouterr().out
    assert "[finestre]" in out and "figli della radice" in out and "n=" in out and "attesa 'Pass'" in out
