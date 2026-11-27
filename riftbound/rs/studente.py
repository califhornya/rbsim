"""Pilota «studente» (specifica: docs/bot/STUDENTE.md): un modello veloce impara da «Pensa» quale delle <=3 mosse candidate
scegliere alla fine della ricerca del campione, senza giocare partite in turno.

  Partite e posizioni   `ordine`, `_lavoro_partita`: partite autonome campione contro campione, due prospettive per seme,
                        posizioni di turno (`seguiti.selezionate`), candidati con identita' esatta (JSON di `action_list`).
  Input della rete      `input_rete`: ricerca minima (2 iterazioni, sonda spenta) col registro acceso dallo stato canonico
                        della posizione: la riga "cercata" porta (x, q, ctx, otype, ocards, ofeats) e le azioni JSON.
  Caratteristiche       `calcola_rete`, `caratteristiche`: h = uscita di `net.ctx`, o_j = `net.opt`, logit = `net.score`.
  Studente              `addestra`, `Studente`: ridge e MLP 64, divisione per semi, tau, cancello; `congela`,
                        `carica_congelato` (sha256).
  Corsa                 `Corsa`: compiti in ordine intercalato con scadenza; le posizioni usate sono un prefisso.
  Fasi                  `raccolta`, `verifica`, `esegui` (tutto); scrive `riepilogo.txt` (ultima riga `totale:`),
                        `riepilogo.json`, `esito.json`.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import multiprocessing
import pickle
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from datetime import datetime
from pathlib import Path

import numpy as np

from riftbound.rs import arena_rs, attacco as A, decisione_esp as E, decisione_rs as D, fondo as F, seguiti as S
from riftbound.rs.seguiti import ITERAZIONI, N_BOOT, REGOLE, VALUTAZIONE

BASE_RACCOLTA = 110_000_000
BASE_VERIFICA = 130_000_000
PER_POSTO = 4
MONDI_RACCOLTA0, N_RACCOLTA = 60_000, 8
MONDI_VERIFICA0, N_VERIFICA = 70_000, 64
MONDI_MAESTRO0, N_MAESTRO = F.MONDI_SCELTA, F.N_SCELTA          # «Pensa» piena: 32 mondi 40000..
SEMI_RACCOLTA = 60                  # semi per matchup messi in coda (il tetto di tempo taglia in coda)
SEMI_VERIFICA = 40
SEMI_MAESTRO = 1
TETTO_RACCOLTA_MIN = 50
TETTO_VERIFICA_MIN = 55
TAU = (0.0, 0.03, 0.06, 0.10)
SOGLIA = 0.010                      # +1,0 pp, fissata prima dei risultati
FRAZIONE_VALIDAZIONE = 0.2
ALFA_RIDGE = (10.0, 100.0, 1000.0)
PROCESSI_SERVER = 47
INPUT_ITER = 2                      # iterazioni della ricerca minima che registra l'input alla radice
FORMATO = "studente-1"
CARATTERISTICHE = ("[h (256), o_j (128), o_0 (128), Q_j-Q_0, (log1p N_j - log1p N_0)/log 139, P_j-P_0, logit_j-logit_0, "
                   "turno/20, ruolo (1 = inizia)]")
RUOLI = ("inizia", "risponde")


# -- ordine, ruoli ------------------------------------------------------------------------------------

def ordine(matchup, n_semi: int, base: int) -> list[dict]:
    """Le partite-prospettiva in ordine fisso intercalato: seme j (esterno), matchup, prospettiva `A` poi `B`."""
    if n_semi > 1000:
        raise ValueError("Al piu' 1000 semi per matchup (seme = base + 1000 i + j).")
    out = []
    for j in range(n_semi):
        for mu in matchup:
            i = arena_rs.COPERTI.index(mu)
            for campione in ("A", "B"):
                out.append({"mu": mu, "i": i, "j": j, "seme": base + 1000 * i + j, "campione": campione})
    return out


def ruolo(partita: dict) -> str:
    """«inizia» se il posto del campione e' lo starter della partita."""
    return "inizia" if str(partita["starter"]).upper() == partita["campione"] else "risponde"


def mondi(n_raccolta: int = N_RACCOLTA, n_verifica: int = N_VERIFICA, n_maestro: int = N_MAESTRO) -> tuple:
    """Gli indici di mondo di raccolta, verifica e maestro: disgiunti (mondi nuovi)."""
    if min(n_raccolta, n_verifica, n_maestro) < 1:
        raise ValueError("Servono almeno un mondo per ogni fase.")
    r = [("maestro", range(MONDI_MAESTRO0, MONDI_MAESTRO0 + n_maestro)),
         ("raccolta", range(MONDI_RACCOLTA0, MONDI_RACCOLTA0 + n_raccolta)),
         ("verifica", range(MONDI_VERIFICA0, MONDI_VERIFICA0 + n_verifica))]
    for (na, a), (nb, b) in zip(r, r[1:]):
        if a.stop > b.start:
            raise ValueError(f"Mondi di {na} {a.start}..{a.stop - 1} e di {nb} {b.start}..{b.stop - 1} si sovrappongono.")
    return r[1][1], r[2][1], r[0][1]


# -- candidati con identita' esatta -------------------------------------------------------------------------

def candidati_identita(o: dict, partita: dict | None = None) -> dict:
    """`fondo.candidati` piu' l'identita' esatta: per ogni candidata l'indice nel menu e il JSON dell'azione
    (`riga["menu"]`, la `action_list`). `stato`: "ok"; "incoerente" (la scelta per Q non e' la mossa giocata);
    "ambigua" (l'etichetta del campione compare piu' volte nel menu: posizione saltata); "identita" (menu e JSON non
    parallele). Una candidata alternativa con etichetta (o JSON) ripetuta nel menu e' esclusa (`alt_escluse`), non
    sostituita da un'altra."""
    c = F.candidati(o, partita)
    menu, azioni = list(o["menu"]), list(o["riga"]["menu"])
    c["alt_escluse"] = 0
    c["stato"] = "ok"
    if len(menu) != len(azioni):
        c["stato"] = "identita"
    elif not c["coerente"]:
        c["stato"] = "incoerente"
    else:
        js = [json.dumps(a) for a in azioni]
        et, jc = Counter(menu), Counter(js)
        if et[c["campione"]] != 1 or jc[js[menu.index(c["campione"])]] != 1:
            c["stato"] = "ambigua"
        else:
            tieni = [0]
            for t in range(1, len(c["candidati"])):
                lab = c["candidati"][t]
                if et[lab] == 1 and jc[js[menu.index(lab)]] == 1:
                    tieni.append(t)
                else:
                    c["alt_escluse"] += 1
            for ch in ("candidati", "n", "q"):
                c[ch] = [c[ch][t] for t in tieni]
    if c["stato"] == "ok":
        c["indici"] = [menu.index(lab) for lab in c["candidati"]]
        c["azioni"] = [azioni[i] for i in c["indici"]]
    return c


# -- l'input della rete alla posizione ----------------------------------------------------------------------

class _Ferma(Exception):
    """La ricerca minima ha registrato la prima decisione del campione."""


def input_rete(pos: dict, stato: dict | None = None, seme: int = 0) -> dict:
    """L'input della rete alla radice della posizione `pos` (di `attacco.posizione`): una ricerca minima (INPUT_ITER
    iterazioni, sonda spenta) del posto del campione dallo stato canonico `stato` (default: l'albero della posizione),
    col registro acceso; si ferma alla sua prima decisione e ne legge la riga "cercata". `stato` puo' essere un mondo
    `ignote` (l'input non deve dipendere dall'informazione nascosta). -> x, q, ctx, otype, ocards, ofeats, azioni (la
    lista JSON), menu (etichette), P (prior registrato), turno, punto."""
    P = pos["P"]
    camp = P["camp"]
    opp = "B" if camp == "A" else "A"
    g = E.gioco(P, pos["tree"] if stato is None else stato, seme)
    E._agente_campione(g, P, opp, seme + 7)
    g.set_search_agent(camp, INPUT_ITER, seme, None, D.rete(P["ckpt"], P["casuali"]), False)
    g.set_search_win_probe(camp, False)
    g.set_search_registro(camp, True)
    g.set_side_chooser()

    def watch(ev):
        if '"k":"decision"' in ev[:60] and json.loads(ev).get("seat") == camp:
            raise _Ferma()

    g.trace_on(watch)
    try:
        g.run_actions_end()
    except _Ferma:
        pass
    righe = [r for r in g.search_registro(camp) if r["kind"] == "cercata"]
    if not righe:
        raise RuntimeError("la ricerca minima non ha registrato l'input alla radice")
    r = righe[0]
    return {"x": r["x"], "q": int(r["q"]), "ctx": r["ctx"], "otype": r["otype"], "ocards": r["ocards"],
            "ofeats": r["ofeats"], "azioni": json.loads(r["azioni"]), "menu": list(r["menu"]),
            "P": np.asarray(r["P"], np.float32), "turno": r["turn"], "punto": r["point"]}


_RETI: dict = {}


def rete_ckpt(ckpt: str):
    """La `PPONet` congelata del campione (una per processo), in valutazione."""
    if ckpt not in _RETI:
        import torch
        from riftbound.ai.ppo.model import load
        torch.set_num_threads(1)
        _RETI[ckpt] = load(Path(ckpt)).eval()
    return _RETI[ckpt]


def calcola_rete(net, inp: dict) -> tuple:
    """(h [256], o [n, 128], logit [n]) del forward della rete sull'input: h = `net.ctx` (src = 0), o = `net.opt`,
    logit = `net.score`; gli stessi passaggi di `PPONet.forward`, con maschera tutta vera."""
    import torch
    with torch.no_grad():
        x = torch.as_tensor(np.asarray(inp["x"])[None])
        q = torch.tensor([int(inp["q"])])
        src = torch.tensor([0])
        ctx = torch.as_tensor(np.asarray(inp["ctx"])[None])
        otype = torch.as_tensor(np.asarray(inp["otype"])[None])
        ocards = torch.as_tensor(np.asarray(inp["ocards"])[None])
        ofeats = torch.as_tensor(np.asarray(inp["ofeats"])[None])
        h = net.ctx(torch.cat([net.state(x), net.q_embed(q), net.card_embed(src), ctx], dim=1))
        m = otype.shape[1]
        o = net.opt(torch.cat([net.t_embed(otype), net.card_embed(ocards).reshape(1, m, -1), ofeats], dim=2))
        logit = net.score(torch.cat([h.unsqueeze(1).expand(-1, m, -1), o], dim=2)).squeeze(-1)
    return h[0].numpy(), o[0].numpy(), logit[0].numpy()


def prior_da_logit(logit: np.ndarray) -> np.ndarray:
    e = np.exp(logit - logit.max())
    return (e / e.sum()).astype(np.float32)


def caratteristiche(h, o, logit, dec: dict, inizia: bool) -> np.ndarray:
    """Una riga per candidata alternativa j: [h, o_j, o_0, Q_j-Q_0, (log1p N_j - log1p N_0)/log 139, P_j-P_0,
    logit_j-logit_0, turno/20, ruolo], con 0 = la mossa del campione."""
    p = prior_da_logit(logit)
    idx, n, q = dec["indici"], dec["n"], dec["q"]
    i0 = idx[0]
    righe = []
    for t in range(1, len(idx)):
        j = idx[t]
        extra = [q[t] - q[0], (math.log1p(n[t]) - math.log1p(n[0])) / math.log(139), float(p[j] - p[i0]),
                 float(logit[j] - logit[i0]), dec["turno"] / 20.0, 1.0 if inizia else 0.0]
        righe.append(np.concatenate([h, o[j], o[i0], np.asarray(extra, np.float32)]))
    return np.asarray(righe, np.float32).reshape(len(righe), -1)


# -- il lavoro di una partita-prospettiva (in un processo) ---------------------------------------------------

def _posizione(partita: dict, o: dict, spec: dict, ckpt: str) -> dict:
    dec = candidati_identita(o, partita)
    p = {"matchup": spec["mu"], "seme": spec["seme"], "j": spec["j"], "campione": spec["campione"],
         "ruolo": ruolo(partita), "nome": dec["nome"], "k": dec["k"], "turno": dec["turno"], "stato": dec["stato"],
         "alt_escluse": dec["alt_escluse"], "menu": dec["menu"]}
    if dec["stato"] == "ok":
        p |= {"candidati": dec["candidati"], "indici": dec["indici"], "azioni": dec["azioni"], "n": dec["n"],
              "q": dec["q"]}
        if len(p["candidati"]) >= 2:
            pos = A.posizione(partita, o["k"])
            inp = input_rete(pos)
            if inp["azioni"] != o["riga"]["menu"] or inp["menu"] != o["menu"]:
                p["stato"] = "identita"
            else:
                h, om, logit = calcola_rete(rete_ckpt(ckpt), inp)
                p["feat"] = caratteristiche(h, om, logit, dec, p["ruolo"] == "inizia")
                p["prior_ok"] = bool(np.max(np.abs(prior_da_logit(logit) - inp["P"])) < 1e-4)
                p["inp"] = inp
                p["pos"] = pos
    return p


def _lavoro_partita(args) -> dict:
    """Una partita-prospettiva: la partita autonoma, le posizioni selezionate con candidati, input e caratteristiche."""
    spec, ckpt, iterazioni, regole, per_posto = args
    t = time.process_time()
    partita = D.autonoma(spec["mu"], spec["seme"], ckpt, False, iterazioni, spec["campione"], regole=regole,
                         valutazione=D._valutazione_registrata(VALUTAZIONE), entrambi=True)
    try:
        out = [_posizione(partita, o, spec, ckpt) for o in S.selezionate(partita, per_posto)]
    finally:
        D._ORIGINALI.clear()
    return {"spec": spec, "posizioni": out, "cpu": time.process_time() - t}


# -- la corsa: compiti a ordine fisso con scadenza -------------------------------------------------------------

class _Subito:
    """Esecutore in linea (un processo): esegue al momento."""

    def submit(self, fn, *args):
        f: Future = Future()
        try:
            f.set_result(fn(*args))
        except BaseException as e:  # noqa: BLE001 - lo rilancia `result()`
            f.set_exception(e)
        return f

    def shutdown(self, **_k):
        pass


def gruppo(tipo: str, fn, args: list, fine) -> dict:
    """Un gruppo di lavori (un mondo ciascuno) di una posizione; `fine(payload)` riceve i payload in ordine e puo'
    restituire altri gruppi della stessa posizione (passano davanti)."""
    return {"tipo": tipo, "fn": fn, "args": list(args), "fine": fine, "ris": {}, "prossimo": 0}


class Corsa:
    """Le partite-prospettiva `specs` in ordine; le loro posizioni (nell'ordine delle partite, poi di `k`) generano gruppi
    di lavori di mondo (`prepara`). I compiti si inviano solo finche' `orologio() < scadenza`; poi si aspettano quelli in
    corso. La posizione e' completa se tutti i suoi gruppi (anche quelli nati dopo) sono finiti; le posizioni usate sono
    il prefisso di quelle complete: il taglio dipende dall'ordine e dal tempo, mai da cosa i compiti hanno dato.
    Le funzioni dei lavori restituiscono (payload, cpu)."""

    def __init__(self, processi: int, tetto_s: float, orologio=time.monotonic, esecutore=None, print_=print):
        self.processi, self.tetto_s, self.orologio, self.print_ = processi, tetto_s, orologio, print_
        self.esecutore = esecutore
        self.coda: deque = deque()
        self.registro: list[dict] = []
        self.cpu: dict = {}
        self.scaduto = False

    def _conta(self, tipo: str, cpu: float, n: int) -> None:
        c = self.cpu.setdefault(tipo, [0.0, 0])
        c[0] += cpu
        c[1] += n

    def esegui(self, specs: list, fn_partita, args_partita, prepara) -> dict:
        """`args_partita(spec)` -> argomenti di `fn_partita` (-> {"posizioni": [...], "cpu": s}); `prepara(posizione,
        indice)` -> gruppi della posizione."""
        owned = self.esecutore is None
        pool = self.esecutore or (_Subito() if self.processi <= 1 else
                                  ProcessPoolExecutor(self.processi, mp_context=multiprocessing.get_context("spawn")))
        cap = max(2, self.processi + 2)
        t0 = self.orologio()
        scadenza = t0 + self.tetto_s
        volo: dict = {}
        pronte: dict = {}
        prossima = rilasciata = 0
        lanciate = 0

        def rilascia():
            nonlocal rilasciata
            while rilasciata in pronte:
                for p in pronte.pop(rilasciata)["posizioni"]:
                    e = {"p": p, "pend": 0}
                    self.registro.append(e)
                    for g in prepara(p, len(self.registro) - 1):
                        self._nuovo(e, g)
                rilasciata += 1

        try:
            while True:
                if not self.scaduto and self.orologio() >= scadenza:
                    self.scaduto = True
                while len(volo) < cap and not self.scaduto:
                    if self.coda:
                        e, g = self.coda[0]
                        i = g["prossimo"]
                        volo[pool.submit(g["fn"], g["args"][i])] = ("mondo", e, g, i)
                        g["prossimo"] += 1
                        if g["prossimo"] == len(g["args"]):
                            self.coda.popleft()
                    elif prossima < len(specs):
                        volo[pool.submit(fn_partita, args_partita(specs[prossima]))] = ("partita", prossima)
                        prossima += 1
                        lanciate += 1
                    else:
                        break
                if not volo:
                    break
                fatti, _ = wait(list(volo), return_when=FIRST_COMPLETED)
                for f in fatti:
                    chi = volo.pop(f)
                    res = f.result()
                    if chi[0] == "partita":
                        self._conta("partita", res["cpu"], 1)
                        pronte[chi[1]] = res
                        rilascia()
                    else:
                        _, e, g, i = chi
                        payload, cpu = res
                        self._conta(g["tipo"], cpu, len(payload))
                        g["ris"][i] = payload
                        if len(g["ris"]) == len(g["args"]):
                            nuovi = g["fine"]([g["ris"][k] for k in range(len(g["args"]))]) or []
                            for h in reversed(nuovi):
                                self._nuovo(e, h, davanti=True)
                            e["pend"] -= 1
        finally:
            if owned:
                pool.shutdown(cancel_futures=True)
        usate = []
        for e in self.registro:
            if e["pend"]:
                break
            usate.append(e["p"])
        return {"usate": usate, "registrate": len(self.registro), "partite_lanciate": lanciate,
                "partite_rilasciate": rilasciata, "scaduto": self.scaduto, "minuti": (self.orologio() - t0) / 60,
                "cpu": {k: {"s": v[0], "rigiocate": v[1]} for k, v in self.cpu.items()}}

    def _nuovo(self, e: dict, g: dict, davanti: bool = False) -> None:
        e["pend"] += 1
        (self.coda.appendleft if davanti else self.coda.append)((e, g))


# -- raccolta ---------------------------------------------------------------------------------------------

def _gruppo_raccolta(p: dict, mondi_r: range):
    linee = [A.linea_primo(f"c{t}", lab) for t, lab in enumerate(p["candidati"])]
    nomi = [f"c{t}" for t in range(len(linee))]

    def fine(payload):
        v = F.valuta_scelta(payload, nomi)
        m = v["medie"]
        d = None if v["n_mondi"] == 0 else [float(m[t] - m[0]) for t in range(1, len(m))]
        p["raccolta"] = {"d": d, "medie": m, "n_mondi": v["n_mondi"], "mondi_esclusi": v["mondi_esclusi"]}
        return []

    return gruppo("raccolta", F._lavoro_mondo, [(p["pos"], "ignote", i, linee) for i in mondi_r], fine)


def raccolta(matchup, n_semi: int, per_posto: int, n_mondi: int, ckpt: str, processi: int, tetto_min: float,
             iterazioni: int = ITERAZIONI, regole: str = REGOLE, orologio=time.monotonic, esecutore=None,
             print_=print) -> dict:
    """Fase di raccolta: partite con semi `BASE_RACCOLTA + 1000 i + j`, per ogni posizione le candidate giocate fino in
    fondo su `n_mondi` mondi appaiati. -> la corsa (`usate`, ...)."""
    mr, _, _ = mondi(n_mondi)
    specs = ordine(matchup, n_semi, BASE_RACCOLTA)
    print_(f"== raccolta: {len(specs)} partite-prospettiva in coda, tetto {tetto_min:g} min, {processi} processi")
    corsa = Corsa(processi, tetto_min * 60, orologio, esecutore, print_)

    def prepara(p, _i):
        if p["stato"] != "ok" or "feat" not in p:
            return []
        return [_gruppo_raccolta(p, mr)]

    return corsa.esegui(specs, _lavoro_partita, lambda s: (s, ckpt, iterazioni, regole, per_posto), prepara)


def _leggero(p: dict) -> dict:
    """La posizione senza `pos` (pesante, solo per le rigiocate)."""
    return {k: v for k, v in p.items() if k != "pos"}


def conteggi(usate: list[dict]) -> dict:
    """Esclusioni e conteggi delle posizioni usate."""
    c = {"posizioni": len(usate), "incoerenti": 0, "ambigue": 0, "identita": 0, "un_candidato": 0, "con_alternative": 0,
         "alt_escluse": sum(p["alt_escluse"] for p in usate), "prior_diverso": 0}
    for p in usate:
        s = p["stato"]
        if s == "incoerente":
            c["incoerenti"] += 1
        elif s == "ambigua":
            c["ambigue"] += 1
        elif s == "identita":
            c["identita"] += 1
        elif "feat" in p:
            c["con_alternative"] += 1
            c["prior_diverso"] += not p.get("prior_ok", True)
        else:
            c["un_candidato"] += 1
    return c


# -- il modello ---------------------------------------------------------------------------------------------

class Studente:
    """Testa congelata: caratteristiche standardizzate -> predizione di d_j; `tau` la soglia della regola."""

    def __init__(self, tipo: str, media, dev, pesi: dict, tau: float):
        self.tipo, self.media, self.dev, self.pesi, self.tau = tipo, np.asarray(media, np.float32), \
            np.asarray(dev, np.float32), pesi, float(tau)

    def predici(self, X) -> np.ndarray:
        Z = (np.asarray(X, np.float32) - self.media) / self.dev
        if self.tipo == "ridge":
            return (Z @ self.pesi["beta"] + self.pesi["b"]).astype(np.float32)
        h = np.maximum(Z @ self.pesi["w1"].T + self.pesi["b1"], 0.0)
        return (h @ self.pesi["w2"].T + self.pesi["b2"]).reshape(-1).astype(np.float32)

    def decidi(self, feat) -> int | None:
        """Indice t (1..) della candidata alternativa scelta, o None (resta il campione): j* = argmax della predizione,
        si cambia solo se predizione(j*) > tau (a parita' resta il campione)."""
        return decidi(self.predici(feat), self.tau)

    def stato(self) -> dict:
        return {"formato": FORMATO, "tipo": self.tipo, "media": self.media, "dev": self.dev, "tau": self.tau,
                "caratteristiche": CARATTERISTICHE,
                "dim": int(self.media.shape[0]), "pesi": {k: np.asarray(v, np.float32) for k, v in self.pesi.items()}}

    @staticmethod
    def da_stato(s: dict) -> "Studente":
        if s.get("formato") != FORMATO:
            raise ValueError(f"formato dello studente sconosciuto: {s.get('formato')}")
        return Studente(s["tipo"], s["media"], s["dev"], {k: np.asarray(v) for k, v in s["pesi"].items()}, s["tau"])


def decidi(pred, tau: float) -> int | None:
    """Regola: j* = argmax predizione (il primo in caso di parita'); cambia solo se pred[j*] > tau."""
    pred = np.asarray(pred, float)
    if not len(pred):
        return None
    j = int(np.argmax(pred))
    return j + 1 if pred[j] > tau else None


def _standardizza(X):
    media = X.mean(axis=0)
    dev = X.std(axis=0)
    dev = np.where(dev < 1e-6, 1.0, dev)
    return media.astype(np.float32), dev.astype(np.float32)


def addestra_ridge(X, y, w, alfa: float, media, dev) -> dict:
    Z = (X - media) / dev
    w = np.asarray(w, float)
    mz = (w[:, None] * Z).sum(0) / w.sum()
    my = float((w * y).sum() / w.sum())
    Zc, yc = Z - mz, y - my
    G = Zc.T @ (w[:, None] * Zc) + alfa * np.eye(Z.shape[1])
    beta = np.linalg.solve(G, Zc.T @ (w * yc))
    return {"beta": beta.astype(np.float32), "b": np.float32(my - mz @ beta)}


def addestra_mlp(X, y, w, media, dev, epoche: int = 300, seme: int = 0) -> dict:
    """MLP 64 (ReLU) -> 1, perdita MSE pesata, Adam; pesi come array numpy."""
    import torch
    g = torch.Generator().manual_seed(seme)
    torch.manual_seed(seme)
    Z = torch.as_tensor((X - media) / dev, dtype=torch.float32)
    Y = torch.as_tensor(y, dtype=torch.float32)
    W = torch.as_tensor(w, dtype=torch.float32)
    rete = torch.nn.Sequential(torch.nn.Linear(Z.shape[1], 64), torch.nn.ReLU(), torch.nn.Linear(64, 1))
    ott = torch.optim.Adam(rete.parameters(), lr=1e-3, weight_decay=1e-4)
    n = len(Z)
    for _ in range(epoche):
        perm = torch.randperm(n, generator=g)
        for a in range(0, n, 256):
            b = perm[a:a + 256]
            perdita = (W[b] * (rete(Z[b]).squeeze(-1) - Y[b]) ** 2).sum() / W[b].sum()
            ott.zero_grad()
            perdita.backward()
            ott.step()
    return {"w1": rete[0].weight.detach().numpy(), "b1": rete[0].bias.detach().numpy(),
            "w2": rete[2].weight.detach().numpy(), "b2": rete[2].bias.detach().numpy()}


def dataset(posizioni: list[dict]) -> dict:
    """Le righe di addestramento (una per candidata alternativa) delle posizioni con caratteristiche e bersaglio valido:
    X, y = d_j, w = 1/sqrt(alternative), pid (indice posizione), gruppo (matchup, seme)."""
    X, y, w, pid, gr = [], [], [], [], []
    for n, p in enumerate(posizioni):
        d = (p.get("raccolta") or {}).get("d")
        if d is None or "feat" not in p:
            continue
        for t in range(len(d)):
            X.append(p["feat"][t])
            y.append(d[t])
            w.append(1.0 / math.sqrt(len(d)))
            pid.append(n)
            gr.append((p["matchup"], p["seme"]))
    dim = posizioni[0]["feat"].shape[1] if posizioni and "feat" in posizioni[0] else 0
    return {"X": np.asarray(X, np.float32).reshape(len(X), dim), "y": np.asarray(y, float), "w": np.asarray(w, float),
            "pid": np.asarray(pid, int), "gruppo": gr}


def dividi_semi(gruppi, frazione: float = FRAZIONE_VALIDAZIONE, seme: int = 0) -> tuple[set, set]:
    """Gruppi unici (matchup, seme) -> (allenamento, validazione), 80/20 (almeno uno per parte se ce ne sono due)."""
    ch = sorted(set(gruppi))
    rng = np.random.default_rng(seme)
    perm = [ch[i] for i in rng.permutation(len(ch))]
    nv = min(max(1, round(frazione * len(ch))), len(ch) - 1) if len(ch) > 1 else 0
    return set(perm[nv:]), set(perm[:nv])


def guadagno(pred, y, pid, tau: float) -> tuple[float, int]:
    """Guadagno realizzato sulle posizioni delle righe: la mossa scelta da `decidi` vale d_j, 0 se resta il campione.
    -> (media per posizione, numero di posizioni)."""
    pred, y, pid = np.asarray(pred, float), np.asarray(y, float), np.asarray(pid)
    tot, n = 0.0, 0
    for k in np.unique(pid):
        m = pid == k
        t = decidi(pred[m], tau)
        tot += 0.0 if t is None else float(y[m][t - 1])
        n += 1
    return (tot / n if n else 0.0), n


def addestra(posizioni: list[dict], epoche: int = 300, seme: int = 0, taus=TAU, alfe=ALFA_RIDGE) -> dict:
    """Divisione per semi 80/20; su validazione si sceglie il modello (ridge con l'alfa a MSE minimo, o MLP) e tau per
    guadagno realizzato (a parita' il tau piu' grande, poi il ridge). `impara`: guadagno di validazione > 0 (cancello).
    -> {"studente", "impara", "guadagno", "tabella", "n_train", "n_val", "semi_train", "semi_val"}."""
    ds = dataset(posizioni)
    out = {"impara": False, "guadagno": 0.0, "studente": None, "tabella": [], "n_train": 0, "n_val": 0,
           "semi_train": 0, "semi_val": 0, "righe": int(len(ds["y"]))}
    if not len(ds["y"]):
        return out
    tr, va = dividi_semi(ds["gruppo"], seme=seme)
    it = np.array([g in tr for g in ds["gruppo"]])
    iv = ~it
    out |= {"semi_train": len(tr), "semi_val": len(va), "n_train": int(it.sum()), "n_val": int(iv.sum())}
    if not it.any() or not iv.any():
        return out
    Xt, yt, wt = ds["X"][it], ds["y"][it], ds["w"][it]
    Xv, yv, wv, pv = ds["X"][iv], ds["y"][iv], ds["w"][iv], ds["pid"][iv]
    media, dev = _standardizza(Xt)
    modelli = {}
    migliore = None
    for a in alfe:
        pesi = addestra_ridge(Xt, yt, wt, a, media, dev)
        mse = float((wv * (Studente("ridge", media, dev, pesi, 0.0).predici(Xv) - yv) ** 2).sum() / wv.sum())
        if migliore is None or mse < migliore[0]:
            migliore = (mse, a, pesi)
    modelli["ridge"] = (migliore[2], {"alfa": migliore[1], "mse_validazione": migliore[0]})
    modelli["mlp"] = (addestra_mlp(Xt, yt, wt, media, dev, epoche, seme), {"epoche": epoche})
    best = None
    for tipo, (pesi, info) in modelli.items():
        pred = Studente(tipo, media, dev, pesi, 0.0).predici(Xv)
        for tau in taus:
            gain, nv = guadagno(pred, yv, pv, tau)
            out["tabella"].append({"modello": tipo, "tau": tau, "guadagno": gain, "posizioni": nv} | info)
            if best is None or gain > best[0] or (gain == best[0] and tau > best[1]):
                best = (gain, tau, tipo)
    gain, tau, tipo = best
    out |= {"studente": Studente(tipo, media, dev, modelli[tipo][0], tau), "guadagno": gain, "impara": bool(gain > 0)}
    return out


# -- congelamento ---------------------------------------------------------------------------------------------

class ErroreCongelamento(RuntimeError):
    """Lo studente o il checkpoint non sono quelli congelati: la verifica non parte."""


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def congela(cart, studente: Studente, ckpt: str, regole: str, parametri: dict) -> dict:
    """Scrive `studente.pt` (pesi, caratteristiche, tau) e `congelato.json` (sha256 di `studente.pt` e del checkpoint,
    regole, parametri, ora) in `cart`; da qui in poi niente cambia."""
    import torch
    cart = Path(cart)
    cart.mkdir(parents=True, exist_ok=True)
    pt = cart / "studente.pt"
    torch.save(studente.stato(), pt)
    c = {"formato": FORMATO, "sha256_studente": sha256_file(pt), "sha256_checkpoint": sha256_file(ckpt),
         "checkpoint": str(ckpt), "regole": regole, "parametri": parametri,
         "ora": datetime.now().astimezone().isoformat(timespec="seconds")}
    (cart / "congelato.json").write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")
    return c


def carica_congelato(cart, ckpt: str, regole: str | None = None) -> tuple[Studente, dict]:
    """Carica lo studente SOLO da `cart` dopo aver controllato lo sha256 di `studente.pt` e del checkpoint (e le regole,
    se date). Qualunque differenza: `ErroreCongelamento`."""
    import torch
    cart = Path(cart)
    jf, pt = cart / "congelato.json", cart / "studente.pt"
    if not jf.exists() or not pt.exists():
        raise ErroreCongelamento(f"Manca il congelamento in {cart}: la verifica non parte.")
    c = json.loads(jf.read_text(encoding="utf-8"))
    if sha256_file(pt) != c.get("sha256_studente"):
        raise ErroreCongelamento("sha256 di studente.pt diverso da congelato.json: la verifica non parte.")
    if sha256_file(ckpt) != c.get("sha256_checkpoint"):
        raise ErroreCongelamento("sha256 del checkpoint diverso da congelato.json: la verifica non parte.")
    if regole is not None and regole != c.get("regole"):
        raise ErroreCongelamento(f"Regole {regole} diverse da quelle congelate ({c.get('regole')}).")
    st = torch.load(pt, map_location="cpu", weights_only=False)
    return Studente.da_stato(st), c


# -- verifica -------------------------------------------------------------------------------------------------

def _gruppo_verifica(p: dict, t: int, mondi_v: range, tipo: str):
    linee = [A.linea_primo("campione", p["candidati"][0]), A.linea_primo("scelta", p["candidati"][t])]

    def fine(payload):
        p["ver"][t] = F.delta_verifica(payload)
        return []

    return gruppo(tipo, F._lavoro_mondo, [(p["pos"], "ignote", i, linee) for i in mondi_v], fine)


def _richiedi(p: dict, t: int, mondi_v: range, tipo: str) -> list:
    """Il gruppo di verifica (campione contro candidata t) se non e' gia' stato chiesto da un altro pilota."""
    if t in p["ver"]:
        return []
    p["ver"][t] = None
    return [_gruppo_verifica(p, t, mondi_v, tipo)]


def _gruppo_maestro(p: dict, mondi_m: range, mondi_v: range):
    linee = [A.linea_primo(f"c{t}", lab) for t, lab in enumerate(p["candidati"])]
    nomi = [f"c{t}" for t in range(len(linee))]

    def fine(payload):
        v = F.valuta_scelta(payload, nomi)
        p["maestro"] = {"scelta": v["scelta"], "medie": v["medie"], "n_mondi": v["n_mondi"],
                        "mondi_esclusi": v["mondi_esclusi"]}
        return _richiedi(p, v["scelta"], mondi_v, "verifica_maestro") if v["scelta"] != 0 else []

    return gruppo("maestro", F._lavoro_mondo, [(p["pos"], "ignote", i, linee) for i in mondi_m], fine)


def verifica(matchup, n_semi: int, per_posto: int, n_mondi: int, n_maestro_semi: int, cart, ckpt: str,
             processi: int, tetto_min: float, iterazioni: int = ITERAZIONI, regole: str = REGOLE,
             n_mondi_maestro: int = N_MAESTRO, orologio=time.monotonic, esecutore=None, print_=print) -> dict:
    """Fase di verifica con lo studente congelato in `cart` (caricato SOLO da li', dopo il controllo degli sha256: se non
    tornano, `ErroreCongelamento` e non parte niente): partite con semi `BASE_VERIFICA + 1000 i + j`; dove lo studente
    cambia, campione e scelta su `n_mondi` mondi appaiati nuovi; il maestro («Pensa» piena) sui primi `n_maestro_semi`
    semi."""
    studente, _c = carica_congelato(cart, ckpt, regole)
    _, mv, mm = mondi(1, n_mondi, n_mondi_maestro)
    specs = ordine(matchup, n_semi, BASE_VERIFICA)
    print_(f"== verifica: {len(specs)} partite-prospettiva in coda, tetto {tetto_min:g} min, {processi} processi, "
           f"maestro sui primi {n_maestro_semi} semi")
    corsa = Corsa(processi, tetto_min * 60, orologio, esecutore, print_)

    def prepara(p, _i):
        p["ver"], p["scelta_studente"], p["di_maestro"] = {}, None, False
        if p["stato"] != "ok" or "feat" not in p:
            return []
        t = studente.decidi(p["feat"])
        p["scelta_studente"] = t
        gruppi = _richiedi(p, t, mv, "verifica_studente") if t is not None else []
        if p["j"] < n_maestro_semi:
            p["di_maestro"] = True
            gruppi.append(_gruppo_maestro(p, mm, mv))
        return gruppi

    return corsa.esegui(specs, _lavoro_partita, lambda s: (s, ckpt, iterazioni, regole, per_posto), prepara)


def valori(p: dict, chi: str) -> tuple:
    """(valore, cambia, senza_mondi) della posizione verificata per `chi` ("studente" o "maestro"): 0 se resta sul
    campione (o se non c'era alternativa), la differenza media appaiata se cambia, None se cambia ma nessun mondo e'
    valido."""
    if chi == "studente":
        t = p.get("scelta_studente")
    else:
        t = (p.get("maestro") or {}).get("scelta") or None
    if t is None:
        return 0.0, False, False
    v = p["ver"].get(t)
    if v is None or v["media"] is None:
        return None, True, True
    return float(v["media"]), True, False


def riassumi(righe: list[dict], n_boot: int = N_BOOT, ruolo_: str | None = None, seme: int = 0) -> dict:
    """`righe`: matchup, seme, ruolo, v (valore). Ogni matchup pesa uguale (zeri compresi); IC 95% ricampionando i semi
    dentro il matchup (le due prospettive di un seme sono un unico gruppo). -> totale [media, lo, hi], per_matchup."""
    righe = [r for r in righe if (ruolo_ is None or r["ruolo"] == ruolo_) and r["v"] is not None]
    mus = sorted({r["matchup"] for r in righe})
    rng = np.random.default_rng(seme)
    boot, pm = [], {}
    for mu in mus:
        g: dict = {}
        for r in righe:
            if r["matchup"] == mu:
                x = g.setdefault(r["seme"], [0.0, 0])
                x[0] += r["v"]
                x[1] += 1
        c = np.array(list(g.values()), float)
        idx = rng.integers(0, len(c), (n_boot, len(c)))
        b = c[idx, 0].sum(axis=1) / c[idx, 1].sum(axis=1)
        boot.append(b)
        pm[mu] = {"n": int(c[:, 1].sum()), "semi": len(c), "media": float(c[:, 0].sum() / c[:, 1].sum()),
                  "ic95": [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]}
    if not mus:
        return {"totale": [0.0, 0.0, 0.0], "per_matchup": {}, "n": 0}
    tb = np.mean(boot, axis=0)
    return {"totale": [float(np.mean([m["media"] for m in pm.values()])), float(np.percentile(tb, 2.5)),
                       float(np.percentile(tb, 97.5))], "per_matchup": pm, "n": len(righe)}


def passa(totale, soglia: float = SOGLIA) -> bool:
    """Soglia fissata prima: media >= +1,0 pp e limite inferiore > 0."""
    return bool(totale[0] >= soglia and totale[1] > 0)


def righe_verifica(usate: list[dict], chi: str, solo_maestro: bool = False) -> tuple[list[dict], dict]:
    """Le righe per `riassumi` di `chi` e i conteggi (cambi, cambi senza mondi validi). Le posizioni con stato diverso da
    "ok" sono escluse (contate a parte); con una sola candidata valgono 0."""
    righe, cambi, senza = [], 0, 0
    for p in usate:
        if p["stato"] != "ok" or (solo_maestro and not p.get("di_maestro")):
            continue
        v, c, s = valori(p, chi) if "ver" in p else (0.0, False, False)
        cambi += c
        senza += s
        righe.append({"matchup": p["matchup"], "seme": p["seme"], "ruolo": p["ruolo"], "v": v})
    return righe, {"cambi": cambi, "cambi_senza_mondi": senza}


# -- tempi e stime ---------------------------------------------------------------------------------------------

def stima_tetti(racc: dict, ver: dict, n_matchup: int, per_posto: int, semi_maestro: int, tetto_r_min: float,
                tetto_v_min: float, processi: int = PROCESSI_SERVER, n_raccolta: int = N_RACCOLTA,
                n_verifica: int = N_VERIFICA, n_maestro: int = N_MAESTRO) -> dict:
    """Quante posizioni stanno nei tetti con `processi` processi, proiettando la cpu MISURATA sui mondi della specifica
    (`n_raccolta`, `n_verifica`, `n_maestro`, non quelli della prova): cpu per rigiocata (una linea in un mondo, mondo
    compreso), cpu per posizione delle partite, quota di posizioni con alternative, di cambi dello studente e del maestro.
    Raccolta: partita + quota con alternative x candidate x mondi x rigiocata. Verifica: partita + quota di cambi dello
    studente x 2 linee x mondi di verifica x rigiocata; il maestro in piu' sulle sue posizioni (`semi_maestro` semi,
    2 prospettive, `per_posto` posizioni)."""
    def rigiocata():
        s = r = 0
        for corsa in (racc, ver):
            for tipo, v in corsa["cpu"].items():
                if tipo != "partita":
                    s, r = s + v["s"], r + v["rigiocate"]
        return s / r if r else None

    def media(x):
        return sum(x) / len(x) if x else None

    c_rig = rigiocata()
    out = {"processi": processi, "rigiocata_s": c_rig}
    nr, nv = len(racc["usate"]), len(ver["usate"])
    cand_r = [len(p["candidati"]) for p in racc["usate"] if "feat" in p]
    cand_v = [len(p["candidati"]) for p in ver["usate"] if "feat" in p]
    g_r = racc["cpu"].get("partita", {"s": 0.0})["s"] / nr if nr else None
    g_v = ver["cpu"].get("partita", {"s": 0.0})["s"] / nv if nv else None
    fa_r = len(cand_r) / nr if nr else 0.0
    out["raccolta"] = {"cpu_partita_per_posizione_s": g_r, "con_alternative": fa_r, "candidate_medie": media(cand_r),
                       "cpu_per_posizione_s": None, "posizioni": None, "usate_nella_prova": nr}
    if c_rig and g_r is not None and cand_r:
        c = g_r + fa_r * media(cand_r) * n_raccolta * c_rig
        out["raccolta"] |= {"cpu_per_posizione_s": c, "posizioni": processi * tetto_r_min * 60 / c}
    cambi = sum(p.get("scelta_studente") is not None for p in ver["usate"])
    fc = cambi / nv if nv else 0.0
    maestri = [p for p in ver["usate"] if p.get("di_maestro") and "feat" in p]
    fm = (sum(bool((p.get("maestro") or {}).get("scelta")) for p in maestri) / len(maestri)) if maestri else 0.0
    previste = semi_maestro * n_matchup * 2 * per_posto
    out["verifica"] = {"cpu_partita_per_posizione_s": g_v, "cambi_studente": fc, "cambi_maestro": fm,
                       "posizioni_maestro_previste": previste, "cpu_per_posizione_s": None,
                       "cpu_maestro_per_posizione_s": None, "posizioni": None, "usate_nella_prova": nv}
    if c_rig and g_v is not None:
        c_o = g_v + fc * 2 * n_verifica * c_rig
        c_m = (media(cand_v) or 0.0) * n_maestro * c_rig + fm * 2 * n_verifica * c_rig if cand_v else 0.0
        out["verifica"] |= {"cpu_per_posizione_s": c_o, "cpu_maestro_per_posizione_s": c_m,
                            "posizioni": max(0.0, (processi * tetto_v_min * 60 - c_m * previste) / c_o)}
    return out


# -- il riepilogo -----------------------------------------------------------------------------------------------

def _pp(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f} pp"


def _s(x, d=1) -> str:
    return "-" if x is None else f"{x:.{d}f}"


def _riga_ic(nome: str, r: dict) -> str:
    t, lo, hi = r["totale"]
    return f"{nome}: {_pp(t)} (IC 95% da {100 * lo:+.1f} a {100 * hi:+.1f}), {r['n']} posizioni"


def testo_riepilogo(res: dict) -> list[str]:
    """Il riepilogo in righe, dall'esito `res` di `esegui`; ultima riga `totale:`."""
    imp, ra, ad, ve, ri = res["impostazioni"], res.get("raccolta"), res.get("addestramento"), res.get("verifica"), \
        res["riassunto"]
    r = [f"Studente (docs/bot/STUDENTE.md): candidate del campione {imp['ckpt']}, {imp['iterazioni']} iterazioni, "
         f"valutazione {VALUTAZIONE}, regole {imp['regole']}",
         f"matchup {len(imp['matchup'])}, per posto {imp['per_posto']}; mondi di raccolta {imp['mondi_raccolta']}, di "
         f"verifica {imp['mondi_verifica']}, del maestro {imp['mondi_maestro']}; {imp['processi']} processi"]
    if ra:
        c = ra["conteggi"]
        r += [f"raccolta: {c['posizioni']} posizioni usate ({ra['partite_rilasciate']}/{ra['partite_lanciate']} partite-"
              f"prospettiva, tetto {'raggiunto' if ra['scaduto'] else 'non raggiunto'}, {ra['minuti']:.1f} min); "
              f"incoerenti {c['incoerenti']}, ambigue {c['ambigue']}, identita' non parallela {c['identita']}, "
              f"una sola candidata {c['un_candidato']}, candidate alternative escluse {c['alt_escluse']}, con "
              f"alternative {c['con_alternative']} (prior diverso: {c['prior_diverso']})",
              f"raccolta: bersagli validi {ra['bersagli']} posizioni, senza mondi validi {ra['senza_mondi']}"]
    if ad:
        r.append(f"addestramento: {ad['righe']} righe, semi {ad['semi_train']}/{ad['semi_val']} (allenamento/validazione), "
                 f"righe {ad['n_train']}/{ad['n_val']}; scelto {ad.get('modello', '-')} tau {ad.get('tau', '-')}, "
                 f"guadagno di validazione {_pp(ad['guadagno'])}"
                 + (" [CANCELLO FORZATO per la prova]" if ad.get("forzato") else ""))
    if res["esito"] == "NON IMPARA":
        r.append("cancello: il guadagno di validazione non e' > 0: lo studente non impara, la verifica non parte")
        r.append(f"totale: NON IMPARA, nessuna verifica, {res['minuti']:.1f} min")
        return r
    cs = ve["conteggi"]
    r += [f"verifica: {cs['posizioni']} posizioni usate ({ve['partite_rilasciate']}/{ve['partite_lanciate']} partite-"
          f"prospettiva, tetto {'raggiunto' if ve['scaduto'] else 'non raggiunto'}, {ve['minuti']:.1f} min); incoerenti "
          f"{cs['incoerenti']}, ambigue {cs['ambigue']}, identita' {cs['identita']}, una sola candidata "
          f"{cs['un_candidato']}, candidate alternative escluse {cs['alt_escluse']}",
          f"studente: cambia mossa in {ri['studente']['cambi']} posizioni (senza mondi validi: "
          f"{ri['studente']['cambi_senza_mondi']})",
          _riga_ic("studente - campione, due ruoli insieme (ogni matchup pesa uguale, resta = 0)", ri["studente"]["tutti"])]
    for ru in RUOLI:
        r.append("  " + _riga_ic(f"ruolo {ru}", ri["studente"][ru]))
    r.append("  per matchup (posizioni, studente - campione con IC 95%):")
    for mu, m in ri["studente"]["tutti"]["per_matchup"].items():
        r.append(f"    {mu}: {m['n']}, {_pp(m['media'])} ({100 * m['ic95'][0]:+.1f} a {100 * m['ic95'][1]:+.1f})")
    if ri["maestro"]["tutti"]["n"]:
        r += [f"maestro («Pensa» piena, primi {imp['semi_maestro']} semi): cambia mossa in {ri['maestro']['cambi']} "
              f"posizioni (senza mondi validi: {ri['maestro']['cambi_senza_mondi']})",
              _riga_ic("maestro - campione, due ruoli insieme", ri["maestro"]["tutti"])]
        for ru in RUOLI:
            r.append("  " + _riga_ic(f"ruolo {ru}", ri["maestro"][ru]))
        r.append(_riga_ic("studente - campione sulle stesse posizioni del maestro", ri["studente_su_maestro"]))
    tm = res["tempi"]
    r.append(f"tempi: cpu per rigiocata {_s(tm['rigiocata_s'], 2)} s (una linea in un mondo); cpu per partita-posizione "
             f"{_s(tm['raccolta']['cpu_partita_per_posizione_s'], 1)} s; proiettata sui mondi della specifica: raccolta "
             f"{_s(tm['raccolta']['cpu_per_posizione_s'], 0)} s di cpu per posizione, verifica "
             f"{_s(tm['verifica']['cpu_per_posizione_s'], 0)} s (maestro {_s(tm['verifica']['cpu_maestro_per_posizione_s'], 0)} s "
             f"per posizione del maestro); quota con alternative {100 * tm['raccolta']['con_alternative']:.0f}%, cambi "
             f"dello studente {100 * tm['verifica']['cambi_studente']:.0f}%, del maestro {100 * tm['verifica']['cambi_maestro']:.0f}%")
    r.append(f"stima con {tm['processi']} processi nei tetti della specifica: raccolta ({TETTO_RACCOLTA_MIN:g} min) "
             f"{_s(tm['raccolta']['posizioni'], 0)} posizioni; verifica ({TETTO_VERIFICA_MIN:g} min) "
             f"{_s(tm['verifica']['posizioni'], 0)} posizioni, di cui {tm['verifica']['posizioni_maestro_previste']} del "
             f"maestro ({imp['semi_maestro']} semi per matchup, {len(imp['matchup'])} matchup; la cpu misurata e' di questa "
             f"prova, non del server)")
    t, lo, hi = ri["studente"]["tutti"]["totale"]
    if res["esito"] == "PASSA":
        r.append(f"soglia (+{100 * SOGLIA:.1f} pp e limite inferiore > 0 sui due ruoli insieme): PASSA: candidato per l'arena "
                 f"lo studente veloce")
    else:
        r.append(f"soglia (+{100 * SOGLIA:.1f} pp e limite inferiore > 0 sui due ruoli insieme): NON PASSA: si ferma la "
                 f"spesa, resta il campione")
    r.append(f"totale: {res['esito']}, studente - campione {_pp(t)} (IC 95% da {100 * lo:+.1f} a {100 * hi:+.1f}), "
             f"{res['minuti']:.1f} min")
    return r


# -- la corsa completa ---------------------------------------------------------------------------------------------

def _salva_pkl(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        pickle.dump(obj, f)


def _info_fase(c: dict, conta: dict) -> dict:
    return {k: c[k] for k in ("partite_lanciate", "partite_rilasciate", "scaduto", "minuti", "registrate", "cpu")} | \
        {"conteggi": conta}


def esegui(matchup, out_dir, dati_dir, ckpt: str, processi: int = 1, per_posto: int = PER_POSTO,
           semi_raccolta: int = SEMI_RACCOLTA, semi_verifica: int = SEMI_VERIFICA, semi_maestro: int = SEMI_MAESTRO,
           n_raccolta: int = N_RACCOLTA, n_verifica: int = N_VERIFICA, n_maestro: int = N_MAESTRO,
           tetto_raccolta_min: float = TETTO_RACCOLTA_MIN, tetto_verifica_min: float = TETTO_VERIFICA_MIN,
           iterazioni: int = ITERAZIONI, regole: str = REGOLE, n_boot: int = N_BOOT, forza_cancello: bool = False,
           epoche: int = 300, print_=print) -> list[str]:
    """Tutto: raccolta, addestramento e cancello, congelamento, verifica, riepilogo. `forza_cancello`: SOLO per le prove,
    la verifica gira anche se lo studente non impara."""
    out_dir, dati_dir = Path(out_dir), Path(dati_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dati_dir.mkdir(parents=True, exist_ok=True)
    ckpt = str(Path(ckpt).resolve())
    t0 = time.time()
    mondi(n_raccolta, n_verifica, n_maestro)
    imp = {"ckpt": ckpt, "ckpt_sha256": sha256_file(ckpt), "iterazioni": iterazioni, "regole": regole,
           "matchup": list(matchup), "per_posto": per_posto, "semi_raccolta": semi_raccolta,
           "semi_verifica": semi_verifica, "semi_maestro": semi_maestro, "mondi_raccolta": n_raccolta,
           "mondi_verifica": n_verifica, "mondi_maestro": n_maestro, "tetto_raccolta_min": tetto_raccolta_min,
           "tetto_verifica_min": tetto_verifica_min, "processi": processi, "n_boot": n_boot, "soglia": SOGLIA,
           "tau": list(TAU), "base_raccolta": BASE_RACCOLTA, "base_verifica": BASE_VERIFICA,
           "forza_cancello": bool(forza_cancello)}
    (out_dir / "impostazioni.json").write_text(json.dumps(imp, indent=1), encoding="utf-8")

    # 1. raccolta
    rc = raccolta(matchup, semi_raccolta, per_posto, n_raccolta, ckpt, processi, tetto_raccolta_min, iterazioni, regole,
                  print_=print_)
    usate = rc["usate"]
    cr = conteggi(usate)
    ok = [p for p in usate if "feat" in p]
    bers = [p for p in ok if (p.get("raccolta") or {}).get("d") is not None]
    info_r = _info_fase(rc, cr) | {"bersagli": len(bers), "senza_mondi": len(ok) - len(bers)}
    _salva_pkl(dati_dir / "raccolta_posizioni.pkl.gz", [_leggero(p) for p in usate])
    print_(f"== raccolta: {len(usate)} posizioni, {len(bers)} con bersaglio, {rc['minuti']:.1f} min")

    # 2. addestramento e cancello
    ad = addestra(usate, epoche)
    st = ad.pop("studente")
    info_a = {k: v for k, v in ad.items()} | {"forzato": False}
    esito = None
    if st is not None:
        info_a |= {"modello": st.tipo, "tau": st.tau}
    (out_dir / "addestramento.json").write_text(json.dumps(info_a | {"raccolta": info_r}, indent=1, default=str),
                                                encoding="utf-8")
    print_(f"== addestramento: guadagno di validazione {_pp(ad['guadagno'])}, impara: {ad['impara']}")
    if st is None or not ad["impara"]:
        if forza_cancello and st is not None:
            info_a["forzato"] = True
        else:
            esito = "NON IMPARA"
    base = {"impostazioni": imp, "raccolta": info_r, "addestramento": info_a, "esito": esito}
    if esito:
        base |= {"minuti": (time.time() - t0) / 60, "riassunto": None}
        testo = testo_riepilogo(base)
        _fine(out_dir, base, testo, {"passa": False, "esito": esito, "guadagno_validazione": ad["guadagno"]})
        return testo

    # 3. congelamento (prima di generare le partite di verifica)
    congela(out_dir, st, ckpt, regole, {k: imp[k] for k in ("iterazioni", "per_posto", "mondi_verifica", "mondi_maestro",
                                                               "semi_maestro", "base_verifica", "soglia", "tau")})
    print_(f"== congelato: {st.tipo}, tau {st.tau}")

    # 4. verifica: carica solo dal congelamento
    vf = verifica(matchup, semi_verifica, per_posto, n_verifica, semi_maestro, out_dir, ckpt, processi, tetto_verifica_min,
                  iterazioni, regole, n_maestro, print_=print_)
    uv = vf["usate"]
    _salva_pkl(dati_dir / "verifica_posizioni.pkl.gz", [_leggero(p) for p in uv])

    rs_, cs_ = righe_verifica(uv, "studente")
    rm_, cm_ = righe_verifica(uv, "maestro", solo_maestro=True)
    rsm_, _ = righe_verifica(uv, "studente", solo_maestro=True)
    ris = {"studente": cs_ | {"tutti": riassumi(rs_, n_boot)} | {r: riassumi(rs_, n_boot, r) for r in RUOLI},
           "maestro": cm_ | {"tutti": riassumi(rm_, n_boot)} | {r: riassumi(rm_, n_boot, r) for r in RUOLI},
           "studente_su_maestro": riassumi(rsm_, n_boot)}
    passa_ = passa(ris["studente"]["tutti"]["totale"])
    tempi = stima_tetti(rc, vf, len(matchup), per_posto, semi_maestro, TETTO_RACCOLTA_MIN, TETTO_VERIFICA_MIN)
    base |= {"verifica": _info_fase(vf, conteggi(uv)), "riassunto": ris, "tempi": tempi,
             "esito": "PASSA" if passa_ else "NON PASSA", "minuti": (time.time() - t0) / 60}
    testo = testo_riepilogo(base)
    _fine(out_dir, base, testo, {"passa": passa_, "esito": base["esito"], "totale": ris["studente"]["tutti"]["totale"],
                                 "soglia": SOGLIA})
    return testo


def _fine(out_dir: Path, res: dict, testo: list[str], esito: dict) -> None:
    (out_dir / "riepilogo.txt").write_text("\n".join(testo) + "\n", encoding="utf-8")
    (out_dir / "riepilogo.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "esito.json").write_text(json.dumps(esito), encoding="utf-8")
