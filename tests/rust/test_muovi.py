"""Muovo prima contro schiero in base (riftbound/rs/muovi.py): selezione su righe finte, riepilogo con bootstrap sulle
partite su dati finti, deck di un replay con percorsi del Mac, corsa da capo a fondo su partite autonome a pesi casuali."""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("torch")

from riftbound.rs import arena_rs  # noqa: E402
from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import muovi as M  # noqa: E402

UNITA = {"Fiora Victorious", "Pyke Returned", "Vex Apathetic"}


def _u(nome):
    return nome in UNITA


def _vista(*campi):
    """campi: (controlla, unita avversario, unita campione) per campo."""
    return {"campi": [{"campo": i, "controlla": c, "avversario": {"unita": [("x", 1)] * a},
                       "campione": {"unita": [("y", 1)] * m}} for i, (c, a, m) in enumerate(campi)]}


def _riga(menu, azione, prior, k=3, turno=5):
    """Riga finta di `D.originale`: le azioni della ricerca sono numeri (indice del menu)."""
    return {"k": k, "turn": turno, "menu": menu, "action": azione,
            "riga": {"menu": list(range(len(menu))), "P": [[i, p] for i, p in prior.items()]}}


MENU = ["Pass", "Play Fiora Victorious", "Play Fiora Victorious to BF1", "Move Sett Kingpin base→BF1",
        "Move Sett Kingpin base→BF0", "Play Pyke Returned", "Play Cleave"]


def test_campi_liberi():
    o = _riga(MENU, "Pass", {})
    # BF0 con nemici, BF1 libero: solo lo spostamento verso BF1 (e l'unita' in base, non "to BF1", non l'incantesimo)
    s = M.scegli(o, _vista((None, 1, 0), (None, 0, 0)), _u)
    assert s["lab_M"] == "Move Sett Kingpin base→BF1" and s["lab_B"] == "Play Fiora Victorious"
    assert s["liberi"] == [1] and s["n_M"] == 1 and s["n_B"] == 2
    # BF1 controllato dal campione: non e' libero; BF0 nemico: niente M
    assert M.scegli(o, _vista((None, 1, 0), ("campione", 0, 1)), _u) is None
    # controllato dall'avversario ma senza unita' (coperta): libero
    assert M.scegli(o, _vista(("avversario", 1, 0), ("avversario", 0, 0)), _u)["liberi"] == [1]
    # nessun campo libero verso cui muovere / niente unita' da schierare / menu corto
    assert M.scegli(_riga(MENU[:1] + MENU[6:], "Pass", {}), _vista((None, 0, 0), (None, 0, 0)), _u) is None
    assert M.scegli(_riga(["Pass"], "Pass", {}), _vista((None, 0, 0)), _u) is None


def test_filtro_unita():
    o = _riga(["Pass", "Play Cleave", "Move Sett Kingpin base→BF0"], "Pass", {})
    assert M.scegli(o, _vista((None, 0, 0)), _u) is None
    o = _riga(["Pass", "Play Fiora Victorious to BF0", "Move Sett Kingpin base→BF0"], "Pass", {})
    assert M.scegli(o, _vista((None, 0, 0)), _u) is None       # solo "to BF": non e' "in base"


def test_unita_del_motore():
    assert M.e_unita("Fiora Victorious") and M.e_unita("Sett Kingpin") and M.e_unita("Pyke Returned")
    assert not M.e_unita("Cleave") and not M.e_unita("Carta che non esiste")


def test_preferenza_campione_e_prior():
    vista = _vista((None, 0, 0), (None, 0, 0))
    menu = ["Pass", "Move A base→BF0", "Move B base→BF1", "Play Fiora Victorious", "Play Pyke Returned"]
    # il campione ha giocato B: lo e' anche se il prior e' piu' basso
    s = M.scegli(_riga(menu, "Play Pyke Returned", {1: 0.6, 2: 0.1, 3: 0.2, 4: 0.1}), vista, _u)
    assert s["lab_B"] == "Play Pyke Returned" and s["lab_M"] == "Move A base→BF0"
    assert s["scelta_campione"] == "B" and s["P_B"] == 0.1 and s["P_M"] == 0.6
    # altrimenti il prior piu' alto
    s = M.scegli(_riga(menu, "Pass", {1: 0.1, 2: 0.5, 3: 0.2, 4: 0.3}), vista, _u)
    assert (s["lab_M"], s["lab_B"], s["scelta_campione"]) == ("Move B base→BF1", "Play Pyke Returned", None)
    # a pari prior l'ordine del menu
    s = M.scegli(_riga(menu, "Pass", {1: 0.3, 2: 0.3, 3: 0.2, 4: 0.2}), vista, _u)
    assert (s["lab_M"], s["lab_B"]) == ("Move A base→BF0", "Play Fiora Victorious")
    # prior assente: ordine del menu
    s = M.scegli(_riga(menu, "Pass", {}), vista, _u)
    assert s["lab_M"] == "Move A base→BF0" and s["P_M"] is None


def _selezione_finta(monkeypatch, righe):
    vista = _vista((None, 0, 0), (None, 0, 0))
    real = M.scegli
    monkeypatch.setattr(D, "_prepara", lambda p: {"camp": "A"})
    monkeypatch.setattr(D, "originale", lambda p, stato=None: righe)
    monkeypatch.setattr(D, "riassunto", lambda st, seat: vista)
    monkeypatch.setattr(M, "scegli", lambda o, v: real(o, v, _u))
    return M.selezionate({"tipo": "autonoma", "matchup": "ES", "seed": 1})


def test_una_posizione_per_turno(monkeypatch):
    ok = ["Pass", "Move A base→BF0", "Play Fiora Victorious"]
    no = ["Pass", "Play Cleave"]

    def r(menu, k, turno, seat="A", point="turn_action"):
        return {**_riga(menu, "Pass", {}, k=k, turno=turno), "seat": seat, "point": point, "e": {"state_raw": {}}}
    righe = [r(no, 0, 3), r(ok, 1, 3), r(ok, 2, 3), r(ok, 3, 5, seat="B"), r(ok, 4, 5, point="reaction"),
             r(ok, 5, 5), r(ok, 6, 5)]
    out = _selezione_finta(monkeypatch, righe)
    assert [(x["k"], x["turno"]) for x in out] == [(1, 3), (5, 5)]


# -- riepilogo --------------------------------------------------------------------------------------

def _pos(nome, media, ic=None, n=10, flip=(0, 0), delta=None):
    return {"nome": nome, "stat": {"M-B": {"n": n, "media": media, "ic95": ic}},
            "flip": {"B_perde_M_vince": flip[0], "B_vince_M_perde": flip[1]},
            "delta_MB": [] if delta is None else delta}


def test_riassunto_bootstrap_sulle_partite():
    righe = [_pos("g1", 0.5, [0.2, 0.8], flip=(3, 1), delta=[0.5] * 10), _pos("g1", 0.1, [-0.1, 0.3], flip=(1, 1)),
             _pos("g2", -0.4, [-0.7, -0.1], flip=(0, 2)), _pos("g3", 0.0, [-0.2, 0.2]), _pos("g3", None, None, n=0)]
    r = M.riassunto(righe, 2000)
    assert r["posizioni"] == 5 and r["valide"] == 4
    assert r["media"] == pytest.approx((0.5 + 0.1 - 0.4 + 0.0) / 4)
    assert r["ic95"][0] <= r["media"] <= r["ic95"][1] or r["ic95"][0] < r["ic95"][1]
    assert (r["a_favore"], r["contro"], r["pari"]) == (2, 1, 1)
    assert (r["pos_ic_positivo"], r["pos_ic_negativo"]) == (1, 1)
    assert (r["flip_B_perde_M_vince"], r["flip_B_vince_M_perde"]) == (4, 4)
    assert r["per_partita"]["g1"]["media"] == pytest.approx(0.3) and r["per_partita"]["g1"]["posizioni"] == 2
    assert M.riassunto(righe, 2000) == r                    # seme fisso
    # il ricampionamento e' per partita: con una sola partita l'IC si riduce al punto
    una = M.riassunto([_pos("g", 0.2), _pos("g", 0.4)], 500)
    assert una["ic95"] == pytest.approx([0.3, 0.3])
    assert M.riassunto([], 10)["media"] is None


def test_analizza_esclude_linee_non_ok_e_conta_flip():
    def riga(nome, ret, ok=None):
        d = {"line": nome, "returns": ret}
        if ok is not None:
            d["primo_ok"] = ok
        return d
    dati = [[riga(A.NOME_RIF, 0.0), riga(M.NOME_M, 1.0, True), riga(M.NOME_B, 0.0, True)],     # flip B perde, M vince
            [riga(A.NOME_RIF, 1.0), riga(M.NOME_M, 0.0, True), riga(M.NOME_B, 1.0, True)],     # flip B vince, M perde
            [riga(A.NOME_RIF, 0.5), riga(M.NOME_M, 1.0, False), riga(M.NOME_B, 0.5, True)],    # M escluso
            [riga(A.NOME_RIF, 1.0), riga(M.NOME_M, 1.0, True), riga(M.NOME_B, 1.0, True)]]
    r = M.analizza(dati)
    assert r["linee"][M.NOME_M]["esclusi"] == 1 and r["linee"][M.NOME_B]["esclusi"] == 0
    assert r["linee"][M.NOME_M]["vittorie"] == 2 and r["linee"][M.NOME_B]["vittorie"] == 2
    assert r["linee"][M.NOME_B]["patte"] == 1 and r["linee"][A.NOME_RIF]["n"] == 4
    assert r["flip"] == {"B_perde_M_vince": 1, "B_vince_M_perde": 1}
    assert r["deltas"]["M-B"] == [1.0, -1.0, 0.0] and r["stat"]["M-B"]["n"] == 3
    assert r["deltas"]["B-rif"] == [0.0, 0.0, 0.0, 0.0] and r["deltas"]["M-rif"] == [1.0, -1.0, 0.0]


# -- replay e deck ----------------------------------------------------------------------------------

def test_replay_default_esclude_il_seme_della_scoperta():
    files = M.replay_default()
    nomi = [f.name[:15] for f in files]
    assert "20261126_155859" not in nomi and "20261126_013325" not in nomi and len(nomi) >= 4
    assert all(f.suffix == ".json" for f in files)


def test_deck_con_percorsi_del_mac(tmp_path):
    src = sorted(M.CARTELLA_REPLAY.glob("2026*.json"))[0]
    d = json.loads(src.read_text(encoding="utf-8"))
    nome_a, nome_b = (d["replay"][k].rsplit("/", 1)[-1] for k in ("deck_a", "deck_b"))
    d["replay"]["deck_a"] = "/Users/nessuno/non/esiste/" + nome_a
    d["replay"]["deck_b"] = "/Users/nessuno/non/esiste/" + nome_b
    f = tmp_path / "r.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    P = D._prepara({"tipo": "pagina", "file": str(f)})
    assert P["deck_a"] == D.ROOT / "riftbound/data/decks" / nome_a and P["deck_a"].exists()
    assert P["deck_b"] == D.ROOT / "riftbound/data/decks" / nome_b
    # un percorso che esiste resta; uno che non esiste da nessuna parte resta com'e'
    d["replay"]["deck_a"] = str(tmp_path / "xx.json")
    f.write_text(json.dumps(d), encoding="utf-8")
    assert D._prepara({"tipo": "pagina", "file": str(f)})["deck_a"] == tmp_path / "xx.json"


# -- da capo a fondo --------------------------------------------------------------------------------

def test_da_capo_a_fondo_e_ripresa(tmp_path, monkeypatch):
    partita = D.autonoma("ES", 2, None, True, 8, "A", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
    out = tmp_path / "o"
    righe = M.muovi([partita], 2, out, None, casuali=True, iterazioni=10, n_boot=200, print_=lambda *_: None)
    assert righe[-1].startswith("totale:")
    assert (out / "riepilogo.txt").read_text().splitlines()[-1].startswith("totale:")
    rj = json.loads((out / "riepilogo.json").read_text())
    assert rj["riassunto"]["posizioni"] == 1 and rj["replay"][0]["iterazioni"] == 8
    imp = json.loads((out / "impostazioni.json").read_text())
    assert imp["iterazioni"] == 10 and imp["valutazione"] == "rimonta" and imp["mondi0"] == M.MONDI0
    cart = next(out.glob("000_*"))
    dj = json.loads((cart / "decisione.json").read_text())
    assert dj["n_mondi"] == 2 and set(dj["linee"]) == {A.NOME_RIF, M.NOME_M, M.NOME_B}
    assert (cart / "mondi.jsonl").exists()
    assert any(r.startswith("replay ") for r in righe) and "10 iterazioni, valutazione rimonta" in righe[0]

    def no(*_a, **_k):
        raise AssertionError("lavoro rifatto")
    monkeypatch.setattr(A, "esegui", no)
    monkeypatch.setattr(D, "originale", no)
    righe2 = M.muovi([partita], 2, out, None, casuali=True, iterazioni=10, n_boot=200, print_=lambda *_: None)
    assert righe2[-1].startswith("totale:")
    with pytest.raises(ValueError):
        M.muovi([partita], 3, out, None, casuali=True, iterazioni=10, n_boot=200, print_=lambda *_: None)


def test_continuazione_col_campione_di_oggi(tmp_path, monkeypatch):
    """Il prefisso resta con le impostazioni registrate; l'esecuzione usa ITERAZIONI e la valutazione di oggi."""
    partita = D.autonoma("ES", 2, None, True, 8, "A", valutazione=None, entrambi=True)
    pos = M.selezionate(partita)[0]
    visto = {}
    vero = A.esegui

    def spia(p, modo, indici, linee, path, processi, out):
        visto.update(it=p["P"]["iterazioni"], val=p["P"]["valutazione"], nomi=[l["nome"] for l in linee])
        return vero(p, modo, list(indici)[:1], linee, path, processi, out)
    monkeypatch.setattr(A, "esegui", spia)
    M.gioca_posizione(pos, 1, tmp_path, 1, iterazioni=10)
    assert visto["it"] == 10 and visto["val"][0] == "rimonta"
    assert visto["nomi"] == [A.NOME_RIF, M.NOME_M, M.NOME_B]
    assert M.ITERAZIONI == 138 and M.VALUTAZIONE == "rimonta"


def test_cli_aiuto():
    r = subprocess.run([sys.executable, str(D.ROOT / "scripts/rust/muovi.py"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--autonome" in r.stdout


def test_cli_rifiuta_casuali_con_i_replay(tmp_path):
    """PR 76 (Codex): --casuali con i replay della pagina farebbe un esperimento diverso da quello dichiarato."""
    r = subprocess.run([sys.executable, str(D.ROOT / "scripts/rust/muovi.py"), "--out", str(tmp_path / "x"), "--casuali"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "--casuali vale solo con --autonome" in r.stderr
    assert not (tmp_path / "x").exists()


# -- partite nuove, modo quota ----------------------------------------------------------------------

def test_partite_autonome_semi_e_posti():
    ps = M.partite_autonome(["ES", "EK"], 3, None, True, 20)
    assert len(ps) == 6 and all(p["tipo"] == "autonoma" and p["entrambi"] for p in ps)
    i_es, i_ek = (arena_rs.COPERTI.index(x) for x in ("ES", "EK"))
    assert [p["seed"] for p in ps[:3]] == [M.BASE_SEME_NUOVE + 1000 * i_es + j for j in range(3)]
    assert [p["seed"] for p in ps[3:]] == [M.BASE_SEME_NUOVE + 1000 * i_ek + j for j in range(3)]
    assert [p["campione"] for p in ps[:3]] == ["A", "B", "A"]
    assert M.BASE_SEME_NUOVE == 80_000_000 and all(p["iterazioni"] == 20 and p["regole"] == "6427b90+D72-D83"
                                                   for p in ps)
    assert ps[0]["valutazione"][0] == "rimonta"
    assert len(M.partite_autonome(arena_rs.COPERTI, 2, None, True)) == 20


def test_linee_quota_senza_duplicati():
    linee, mappa = M.linee_quota("x", "m", "b", "x")
    assert [l["nome"] for l in linee] == [M.NOME_CAMPIONE, M.NOME_M, M.NOME_B]
    assert mappa[M.NOME_Q] == M.NOME_CAMPIONE
    linee, mappa = M.linee_quota("b", "m", "b", "q")
    assert [l["nome"] for l in linee] == [M.NOME_CAMPIONE, M.NOME_M, M.NOME_Q] and mappa[M.NOME_B] == M.NOME_CAMPIONE


def _q(nome, mu, sc, q_media, lab_q="Q", q_uguale="altro", mb=0.0, prefisso=True):
    return {"nome": nome, "matchup": mu, "scelta_campione": sc, "campione": "C", "lab_Q": lab_q,
            "q_uguale": q_uguale, "q_media": q_media, "prefisso_ok": prefisso,
            "stat": {"M-B": {"n": 4, "media": mb, "ic95": None}}, "flip": {"B_perde_M_vince": 0, "B_vince_M_perde": 0},
            "delta_MB": []}


def test_riassunto_quota_regola_di_stop_nei_due_sensi():
    # molte posizioni a favore, il resto zeri: il limite inferiore sta sopra 0
    pos = [_q(f"g{g}", mu, "B", 0.3, q_uguale="M", mb=0.2) for mu in ("EK", "ES") for g in range(6)]
    pos += [_q(f"g{g}", mu, None, 0.0, lab_q="C", q_uguale="campione") for mu in ("EK", "ES") for g in range(6)]
    r = M.riassunto_quota(pos, 2000)
    assert r["passa"] and r["q_meno_campione"][0] == pytest.approx(0.15) and r["q_meno_campione"][1] > 0
    assert r["cambiano"] == 12 and r["cambiano_verso"] == {"M": 12, "B": 0, "altro": 0}
    assert r["sottoinsiemi"]["campione = B"]["posizioni"] == 12 and r["sottoinsiemi"]["campione = B"]["media"] == \
        pytest.approx(0.2)
    assert r["sottoinsiemi"]["campione = M"]["n"] == 0 and r["sottoinsiemi"]["altro"]["posizioni"] == 12
    assert M.riassunto_quota(pos, 2000) == r
    # effetti di segno diverso: il limite inferiore scende sotto 0
    pos = [_q(f"g{g}", "EK", "B", 0.5 if g % 2 else -0.5) for g in range(6)] + \
        [_q("z", "EK", None, 0.0, lab_q="C", q_uguale="campione")] * 2
    r = M.riassunto_quota(pos, 2000)
    assert not r["passa"] and r["q_meno_campione"][1] < 0 < r["q_meno_campione"][2]
    # prefissi non riprodotti: esclusi e contati; senza posizioni valide non passa
    r = M.riassunto_quota([_q("g", "EK", "B", 0.9, prefisso=False)], 100)
    assert r["esclusi_prefisso"] == 1 and r["n_valide"] == 0 and not r["passa"] and r["q_meno_campione"][0] is None


def test_analizza_quota_zero_esatto_se_uguale():
    def riga(nome, ret):
        return {"line": nome, "returns": ret, "primo_ok": True}
    dati = [[riga("campione", 1.0), riga(M.NOME_M, 0.0), riga(M.NOME_B, 1.0)],
            [riga("campione", 0.0), riga(M.NOME_M, 1.0), riga(M.NOME_B, 0.0)]]
    linee, mappa = M.linee_quota("c", "m", "b", "c")
    r = M.analizza_quota(dati, mappa)
    assert r["deltas"]["Q-campione"] == [0.0, 0.0] and r["stat"]["Q-campione"]["media"] == 0.0
    assert r["deltas"]["M-B"] == [-1.0, 1.0]
    # Q uguale a M: differenza appaiata
    linee, mappa = M.linee_quota("c", "m", "b", "m")
    r = M.analizza_quota(dati, mappa)
    assert r["deltas"]["Q-campione"] == [-1.0, 1.0] and r["stat"]["Q-campione"]["media"] == 0.0


def test_quota_su_una_partita_piccola(tmp_path):
    partita = D.autonoma("ES", 2, None, True, 40, "A", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
    out = tmp_path / "o"
    righe = M.muovi([partita], 2, out, None, casuali=True, iterazioni=40, n_boot=200, print_=lambda *_: None,
                    quota=(M.QUOTA_ETICHETTE, M.QUOTA_VISITE), base_seme=7)
    assert righe[-1].startswith("totale:") and any(x.startswith("regola di stop:") for x in righe)
    imp = json.loads((out / "impostazioni.json").read_text())
    assert imp["quota"] == [["base→bf"], 8] and imp["base_seme"] == 7
    esito = json.loads((out / "esito.json").read_text())
    assert isinstance(esito["passa"], bool) and len(esito["q_meno_campione"]) == 3
    dj = json.loads(next(out.glob("000_*")).joinpath("decisione.json").read_text())
    assert set(dj["linee"]) == {M.NOME_CAMPIONE, M.NOME_M, M.NOME_B, M.NOME_Q} and dj["prefisso_ok"]
    assert dj["q_uguale"] in ("campione", "M", "B", "altro")
    if dj["lab_Q"] == dj["campione"]:
        assert dj["stat"]["Q-campione"]["media"] == 0.0 and set(dj["deltas"]["Q-campione"]) <= {0.0}
    rj = json.loads((out / "riepilogo.json").read_text())
    assert rj["quota"]["posizioni"] == rj["riassunto"]["posizioni"] == 1
    with pytest.raises(ValueError):                                     # impostazioni diverse: nuova cartella
        M.muovi([partita], 2, out, None, casuali=True, iterazioni=40, n_boot=200, print_=lambda *_: None)


def test_cli_autonome_nuove_quota(tmp_path):
    out = tmp_path / "c"
    r = subprocess.run([sys.executable, str(D.ROOT / "scripts/rust/muovi.py"), "--out", str(out), "--casuali",
                        "--autonome-nuove", "1", "--matchup", "EK", "--mondi", "2", "--iterazioni", "30"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    assert "regola di stop:" in r.stdout
    assert json.loads((out / "impostazioni.json").read_text())["base_seme"] == M.BASE_SEME_NUOVE
    assert (out / "esito.json").exists()
    r = subprocess.run([sys.executable, str(D.ROOT / "scripts/rust/muovi.py"), "--out", str(tmp_path / "d"),
                        "--autonome-nuove", "0", "--casuali"], capture_output=True, text=True)
    assert r.returncode == 2


def test_arena_quota_piccola(tmp_path):
    from riftbound.ai.ppo.model import PPONet, save
    ck = tmp_path / "ck.pt"
    save(PPONet().eval(), ck)
    righe = M.arena_quota(["EK"], 1, tmp_path / "arena", ck, iterazioni=10, n_boot=100, print_=lambda *_: None)
    assert any(x.startswith("criterio: limite inferiore > 50%: candidato promuovibile: ") for x in righe)
    assert len((tmp_path / "arena" / "arena_righe.jsonl").read_text().splitlines()) == 2
    j = json.loads((tmp_path / "arena" / "arena.json").read_text())
    assert isinstance(j["promuovibile"], bool)
    assert j["configurazione"]["opz"]["quota_cand"] == [["base→bf"], 8] and j["configurazione"]["base_seme"] == 90_000_000
    with pytest.raises(ValueError):
        M.arena_quota(["EK"], 1, tmp_path / "arena", ck, iterazioni=11, print_=lambda *_: None)


def test_regola_di_stop_vuole_abbastanza_posizioni():
    """Con una partita per matchup l'intervallo a cluster si schiaccia: servono MIN_POSIZIONI posizioni valide e
    MIN_CAMBIANO posizioni in cui la quota cambia mossa."""
    poche = [_q("g0", "EK", "B", 0.3, q_uguale="M"), _q("g1", "ES", None, 0.0, lab_q="C", q_uguale="campione")]
    r = M.riassunto_quota(poche, 2000)
    assert r["q_meno_campione"][1] > 0 and not r["passa"]
    # abbastanza posizioni ma troppo poche che cambiano mossa
    pos = [_q(f"g{g}", mu, "B", 0.3, q_uguale="M") for mu in ("EK", "ES") for g in range(2)]
    pos += [_q(f"g{g}", mu, None, 0.0, lab_q="C", q_uguale="campione") for mu in ("EK", "ES") for g in range(10)]
    r = M.riassunto_quota(pos, 2000)
    assert r["cambiano"] == M.MIN_CAMBIANO - 1 and not r["passa"]
