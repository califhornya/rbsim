"""Pilota «studente» (riftbound/rs/studente.py, docs/bot/STUDENTE.md): input della rete (prior, identita', informazione
nascosta), prospettive, studente su dati sintetici, congelamento, tetto di tempo."""
from __future__ import annotations

import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("riftbound_rs")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import rust_bridge  # noqa: E402
from riftbound.rs import seguiti as S  # noqa: E402
from riftbound.rs import studente as T  # noqa: E402

ITER = 20          # iterazioni delle partite di prova (la logica non dipende dal budget)


@pytest.fixture(scope="module")
def ckpt(tmp_path_factory):
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(0)
    p = tmp_path_factory.mktemp("rete") / "casuale.pt"
    save(PPONet(), p)
    return str(p)


def _partita(ckpt, seme=T.BASE_RACCOLTA, campione="A", mu="EK"):
    return D.autonoma(mu, seme, ckpt, False, ITER, campione, regole=S.REGOLE,
                      valutazione=D._valutazione_registrata("rimonta"), entrambi=True)


@pytest.fixture(scope="module")
def posizioni(ckpt):
    """Le posizioni selezionate di una partita vera, con la `pos` per le rigiocate."""
    partita = _partita(ckpt)
    out = []
    for o in S.selezionate(partita, 4):
        spec = {"mu": "EK", "seme": T.BASE_RACCOLTA, "j": 0, "campione": "A"}
        pos = A.posizione(partita, o["k"])
        out.append((o, pos, T._posizione(partita, o, spec, ckpt)))
    D._ORIGINALI.clear()
    assert out
    return out


# -- 1. prior -----------------------------------------------------------------------------------------------

def test_prior_del_forward_uguale_al_registrato(ckpt, posizioni):
    from riftbound.ai.ppo.model import load
    net = load(ckpt).eval()
    visti = 0
    for o, pos, p in posizioni:
        inp = T.input_rete(pos)
        h, om, logit = T.calcola_rete(net, inp)
        pr = T.prior_da_logit(logit)
        # il prior registrato dalla ricerca minima e quello della ricerca ORIGINALE a quella decisione
        orig = np.array([x[1] for x in o["riga"]["P"]], np.float32)
        assert len(pr) == len(orig) == len(o["menu"])
        assert np.max(np.abs(pr - inp["P"])) < 1e-4
        assert np.max(np.abs(pr - orig)) < 1e-4
        # la scomposizione (h, o_j, testa `score`) e' il forward della rete
        with torch.no_grad():
            m = len(inp["otype"])
            lg, _ = net(torch.as_tensor(inp["x"][None]), torch.tensor([inp["q"]]), torch.tensor([0]),
                        torch.as_tensor(inp["ctx"][None]), torch.as_tensor(inp["otype"][None]),
                        torch.as_tensor(inp["ocards"][None]), torch.as_tensor(inp["ofeats"][None]),
                        torch.ones(1, m, dtype=torch.bool))
        assert np.max(np.abs(lg[0].numpy() - logit)) < 1e-5
        assert h.shape == (256,) and om.shape == (m, 128)
        visti += 1
    assert visti >= 1


# -- 2. identita' ---------------------------------------------------------------------------------------------

def test_identita_azioni_json_e_candidate_univoche(posizioni):
    for o, pos, p in posizioni:
        inp = T.input_rete(pos)
        assert inp["azioni"] == o["riga"]["menu"]          # stessi JSON, stesso ordine
        assert inp["menu"] == o["menu"]
        if p["stato"] != "ok" or "feat" not in p:
            continue
        js = [json.dumps(a) for a in o["riga"]["menu"]]
        for lab, az, i in zip(p["candidati"], p["azioni"], p["indici"]):
            assert o["menu"].count(lab) == 1 and js.count(json.dumps(az)) == 1
            assert o["menu"][i] == lab and o["riga"]["menu"][i] == az
        assert len(set(p["candidati"])) == len(p["candidati"])
        assert p["candidati"][0] == o["action"]


def _o(children, giocata, etichette, azioni=None):
    menu = azioni or [f"a{i}" for i in range(len(etichette))]
    ch = [[menu[i], n, q, 0.0, []] for i, n, q in children]
    return {"k": 3, "turn": 2, "action": giocata, "menu": list(etichette), "riga": {"menu": menu, "children": ch}}


def test_candidati_identita_esclusioni():
    # campione ambiguo: posizione saltata
    c = T.candidati_identita(_o([(0, 5, 0.9), (1, 4, 0.3)], "x", ("x", "y", "x")))
    assert c["stato"] == "ambigua"
    # alternativa con etichetta ripetuta: esclusa, non sostituita
    c = T.candidati_identita(_o([(0, 9, 0.9), (1, 8, 0.3), (2, 7, 0.2), (3, 6, 0.1)], "x", ("x", "y", "y", "z")))
    assert c["stato"] == "ok" and c["candidati"] == ["x", "z"] and c["alt_escluse"] == 1
    assert c["indici"] == [0, 3] and c["azioni"] == ["a0", "a3"]
    # JSON ripetuto con etichette diverse: esclusa
    c = T.candidati_identita(_o([(0, 9, 0.9), (1, 8, 0.3), (2, 7, 0.2)], "x", ("x", "y", "z"), ["a0", "b", "b"]))
    assert c["candidati"] == ["x"] and c["alt_escluse"] == 1
    # incoerente
    assert T.candidati_identita(_o([(0, 3, 0.2), (1, 5, 0.8)], "x", ("x", "y")))["stato"] == "incoerente"
    # normale
    c = T.candidati_identita(_o([(0, 9, 0.9), (1, 8, 0.3), (2, 7, 0.2)], "x", ("x", "y", "z")))
    assert c["stato"] == "ok" and c["candidati"] == ["x", "y", "z"] and c["alt_escluse"] == 0


# -- 3. informazione nascosta ----------------------------------------------------------------------------------

def test_input_uguale_su_mondi_ignote_diversi(posizioni):
    provati = 0
    for o, pos, p in posizioni:
        base = T.input_rete(pos)
        mondi = [A.mondo(pos, "ignote", pos["base"] + i) for i in (60_000, 60_001, 60_002)]
        # i mondi sono davvero diversi (altrimenti il test non dice nulla)
        assert len({json.dumps(m, sort_keys=True) for m in mondi}) > 1
        for m, seme in zip(mondi, (11, 12, 13)):
            y = T.input_rete(pos, m, seme)
            for chiave in ("x", "ctx", "otype", "ocards", "ofeats"):
                assert np.array_equal(y[chiave], base[chiave]), chiave
            assert y["q"] == base["q"] and y["azioni"] == base["azioni"] and y["menu"] == base["menu"]
        provati += 1
    assert provati >= 1


# -- 4. prospettive ---------------------------------------------------------------------------------------------

def test_le_due_prospettive_sono_la_stessa_partita(ckpt, monkeypatch):
    class Proxy:
        def __init__(self, g):
            self._g, self.res = g, None

        def __getattr__(self, n):
            return getattr(self._g, n)

        def start(self):
            self.res = self._g.start()
            return self.res

    giochi = []
    orig = rust_bridge.build

    def build(*a, **k):
        giochi.append(Proxy(orig(*a, **k)))
        return giochi[-1]

    monkeypatch.setattr(rust_bridge, "build", build)
    for seme in (T.BASE_RACCOLTA, T.BASE_RACCOLTA + 1):
        esiti = []
        for campione in ("A", "B"):
            D._ORIGINALI.clear()
            D.originale(_partita(ckpt, seme, campione))
            esiti.append(giochi[-1].res)                # (vincitore, turni)
        assert esiti[0] == esiti[1], (seme, esiti)
    D._ORIGINALI.clear()


def test_ordine_intercalato_e_ruoli():
    o = T.ordine(["EK", "ER"], 2, T.BASE_RACCOLTA)
    assert [(x["mu"], x["j"], x["campione"]) for x in o] == [
        ("EK", 0, "A"), ("EK", 0, "B"), ("ER", 0, "A"), ("ER", 0, "B"),
        ("EK", 1, "A"), ("EK", 1, "B"), ("ER", 1, "A"), ("ER", 1, "B")]
    assert o[0]["seme"] == 110_000_000 and o[2]["seme"] == 110_001_000 and o[4]["seme"] == 110_000_001
    # i due ruoli di un seme: chi inizia dipende dalla parita' del seme
    for seme, inizia in ((110_000_000, "A"), (110_000_001, "B")):
        r = {c: T.ruolo({"starter": "a" if seme % 2 == 0 else "b", "campione": c}) for c in "AB"}
        assert r[inizia] == "inizia" and r["B" if inizia == "A" else "A"] == "risponde"
    assert T.mondi()[0].start == 60_000 and T.mondi()[1].start == 70_000 and T.mondi()[2].start == 40_000
    with pytest.raises(ValueError):
        T.mondi(20_000, 64, 32)           # raccolta e verifica si sovrappongono


# -- 5. studente su dati sintetici ---------------------------------------------------------------------------------

def _sintetico(n_semi=60, dim=24, seme=0, segnale=True):
    """Posizioni finte: d_j = 0,4 * feat[j, 0] + rumore; due prospettive per seme (stesso gruppo)."""
    rng = np.random.default_rng(seme)
    out = []
    for s in range(n_semi):
        for camp in "AB":
            na = int(rng.integers(1, 3))
            f = rng.normal(size=(na, dim)).astype(np.float32)
            d = (0.4 * f[:, 0] if segnale else np.zeros(na)) + rng.normal(scale=0.03, size=na)
            out.append({"matchup": "EK" if s % 2 else "ER", "seme": 1000 + s, "campione": camp, "feat": f,
                        "raccolta": {"d": [float(x) for x in d]}})
    return out


def test_studente_ritrova_il_segnale():
    pos = _sintetico()
    r = T.addestra(pos, epoche=60)
    assert r["impara"] and r["guadagno"] > 0.1
    st = r["studente"]
    # separato per semi: nessun seme sta sia in allenamento sia in validazione
    tr, va = T.dividi_semi([(p["matchup"], p["seme"]) for p in pos])
    assert not tr & va and len(va) == round(0.2 * len(tr | va))
    # la predizione segue il segnale (sulle posizioni nuove)
    nuove = _sintetico(seme=5)
    X = np.concatenate([p["feat"] for p in nuove])
    y = np.concatenate([p["raccolta"]["d"] for p in nuove])
    assert np.corrcoef(st.predici(X), y)[0, 1] > 0.8
    # una candidata alternativa con segnale forte positivo -> cambia; con segnale negativo -> resta
    f = np.zeros((1, X.shape[1]), np.float32)
    f[0, 0] = 2.0
    assert st.decidi(f) == 1
    f[0, 0] = -2.0
    assert st.decidi(f) is None


def test_senza_segnale_non_impara_e_la_regola_resta_sul_campione():
    r = T.addestra(_sintetico(segnale=False), epoche=30)
    assert r["guadagno"] <= 0.02            # niente da guadagnare: al piu' rumore
    # la regola: resta sul campione quando nessuna predizione supera tau (parita' compresa)
    assert T.decidi([0.05, 0.02], 0.06) is None
    assert T.decidi([0.06, 0.02], 0.06) is None
    assert T.decidi([0.05, 0.07], 0.06) == 2
    assert T.decidi([0.07, 0.07], 0.06) == 1
    assert T.decidi([-0.2], 0.0) is None and T.decidi([], 0.0) is None
    # il guadagno realizzato vale d della mossa scelta, 0 se resta
    pred, y, pid = np.array([0.1, 0.5, -1.0]), np.array([0.2, -0.1, 0.9]), np.array([0, 0, 1])
    assert T.guadagno(pred, y, pid, 0.0) == (pytest.approx(-0.05), 2)
    assert T.guadagno(pred, y, pid, 0.6) == (0.0, 2)


def test_cancello_senza_dati():
    r = T.addestra([])
    assert not r["impara"] and r["studente"] is None


# -- 6. congelamento ------------------------------------------------------------------------------------------------

def _studente_finto(dim=8):
    rng = np.random.default_rng(1)
    return T.Studente("ridge", np.zeros(dim), np.ones(dim), {"beta": rng.normal(size=dim), "b": np.float32(0.1)}, 0.03)


def test_congelamento_sha(ckpt, tmp_path):
    T.congela(tmp_path, _studente_finto(), ckpt, "6427b90+D72-D83", {"x": 1})
    st, c = T.carica_congelato(tmp_path, ckpt, "6427b90+D72-D83")
    assert st.tau == 0.03 and c["sha256_studente"] == T.sha256_file(tmp_path / "studente.pt")
    X = np.ones((2, 8), np.float32)
    assert np.allclose(st.predici(X), _studente_finto().predici(X), atol=1e-6)
    # studente.pt alterato
    pt = tmp_path / "studente.pt"
    b = bytearray(pt.read_bytes())
    b[-20] ^= 0xFF
    pt.write_bytes(bytes(b))
    with pytest.raises(T.ErroreCongelamento):
        T.carica_congelato(tmp_path, ckpt)
    # la verifica rifiuta di partire (prima di qualunque partita)
    with pytest.raises(T.ErroreCongelamento):
        T.verifica(["EK"], 1, 1, 2, 1, tmp_path, ckpt, 1, 0.01)
    # sha dichiarato alterato
    T.congela(tmp_path, _studente_finto(), ckpt, "6427b90+D72-D83", {})
    jf = tmp_path / "congelato.json"
    c = json.loads(jf.read_text())
    c["sha256_studente"] = "0" * 64
    jf.write_text(json.dumps(c))
    with pytest.raises(T.ErroreCongelamento):
        T.carica_congelato(tmp_path, ckpt)
    # checkpoint diverso
    T.congela(tmp_path, _studente_finto(), ckpt, "6427b90+D72-D83", {})
    altro = tmp_path / "altro.pt"
    altro.write_bytes(b"altro")
    with pytest.raises(T.ErroreCongelamento):
        T.carica_congelato(tmp_path, str(altro))
    # regole diverse
    with pytest.raises(T.ErroreCongelamento):
        T.carica_congelato(tmp_path, ckpt, "altre")
    # senza congelamento
    with pytest.raises(T.ErroreCongelamento):
        T.carica_congelato(tmp_path / "vuota", ckpt)


# -- 7. tetto -----------------------------------------------------------------------------------------------------

class _Orologio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _corsa_finta(esito: float, scadenza_s: float, n_semi=6, matchup=("EK", "ER", "KR"), extra_se_positivo=False):
    """La corsa con funzioni finte in linea: ogni partita costa 5 s, ogni mondo 1 s di orologio finto, qualunque sia
    l'esito (`esito` cambia solo i valori restituiti e quanti gruppi nascono dopo)."""
    ck = _Orologio()
    specs = T.ordine(list(matchup), n_semi, T.BASE_RACCOLTA)

    def partita(spec):
        ck.t += 5.0
        return {"posizioni": [{"spec": (spec["mu"], spec["j"], spec["campione"]), "k": k, "ris": esito}
                              for k in range(3)], "cpu": 5.0}

    def mondo(arg):
        ck.t += 1.0
        return [{"v": esito}], 1.0

    def prepara(p, _i):
        def fine(payload):
            p["fatto"] = payload
            # un secondo gruppo che nasce solo se l'esito lo vuole (dipende dagli esiti, non dall'ordine)
            if extra_se_positivo and esito <= 0:
                return []
            return [T.gruppo("v", mondo, [0, 1], lambda pl: [])]
        return [T.gruppo("r", mondo, [0, 1, 2, 3], fine)]

    corsa = T.Corsa(1, scadenza_s, ck, None, lambda *_: None)
    res = corsa.esegui(specs, partita, lambda s: s, prepara)
    return res, specs


def test_tetto_prefisso_dell_ordine_indipendente_dagli_esiti():
    atteso = None
    for esito in (0.0, 1.0, -3.0):
        res, specs = _corsa_finta(esito, 75.0, extra_se_positivo=False)
        usate = [(p["spec"], p["k"]) for p in res["usate"]]
        ordine = [((s["mu"], s["j"], s["campione"]), k) for s in specs for k in range(3)]
        assert res["scaduto"] and 0 < len(usate) < len(ordine)
        assert usate == ordine[:len(usate)]                  # un prefisso dell'ordine intercalato
        assert all("fatto" in p for p in res["usate"])
        atteso = atteso or usate                             # stessi costi: il taglio non guarda i valori
        assert usate == atteso
    # se gli esiti cambiano i costi (un gruppo in piu' solo con esito positivo) restano comunque prefissi dell'ordine
    for esito in (1.0, -1.0):
        res, specs = _corsa_finta(esito, 75.0, extra_se_positivo=True)
        usate = [(p["spec"], p["k"]) for p in res["usate"]]
        ordine = [((s["mu"], s["j"], s["campione"]), k) for s in specs for k in range(3)]
        assert 0 < len(usate) < len(ordine) and usate == ordine[:len(usate)]
    # senza scadenza (tetto enorme) si usa tutto, nell'ordine
    res, specs = _corsa_finta(1.0, 1e9)
    assert len(res["usate"]) == len(specs) * 3 and not res["scaduto"]
    # una scadenza che non fa partire nulla
    assert _corsa_finta(1.0, 0.0)[0]["usate"] == []


# -- regressioni di revisione -----------------------------------------------------------------------------------------

def test_dataset_dim_da_posizione_con_feat():
    pos = _sintetico(n_semi=6)
    pos.insert(0, {"matchup": "EK", "seme": 1, "campione": "A", "raccolta": {"d": [0.1]}})  # prima senza feat
    ds = T.dataset(pos)
    assert ds["X"].shape[1] == 24 and len(ds["X"]) == len(ds["y"]) > 0


def test_addestra_senza_righe_non_va_in_crash():
    r = T.addestra([{"matchup": "EK", "seme": 1, "campione": "A"}])
    assert not r["impara"] and r["studente"] is None and r["messaggio"] == "nessun dato di allenamento"


def test_verifica_una_candidata_nel_sottoinsieme_del_maestro():
    class Fisso:
        def decidi(self, feat):
            return None

    p = {"stato": "ok", "j": 0, "matchup": "EK", "seme": 1, "ruolo": "inizia", "candidati": ["a"],
         "feat": np.zeros((0, 4), np.float32)}
    assert T._prepara_verifica(p, Fisso(), range(1), range(1), 2) == []
    assert p["di_maestro"] is True
    righe, _ = T.righe_verifica([p], "maestro", solo_maestro=True)
    assert len(righe) == 1 and righe[0]["v"] == 0.0
    fuori = dict(p, j=5)
    T._prepara_verifica(fuori, Fisso(), range(1), range(1), 2)
    assert T.righe_verifica([fuori], "maestro", solo_maestro=True)[0] == []
