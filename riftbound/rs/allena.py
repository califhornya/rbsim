"""Allenamento pilota della rete sui dati della raccolta (Astra, 26/11): la politica impara le visite della ricerca,
il valore impara l'esito della partita dal posto osservato.

Dati (`riftbound/rs/raccolta.py`, un pickle per partita, `insieme` allenamento / sviluppo / verifica):
  - decisioni: i record `cercata` con gli ingressi del prior (x, q, ctx, otype, ocards, ofeats), le visite N e l'esito
    del posto che decide (+1, 0, -1): servono alla politica e al valore;
  - stati di fine turno (`osserva`: x, q, ctx, esito): solo al valore (la domanda e' senza menu: una voce finta
    mascherata nel forward, i logit non contano).
Perdite: politica = entropia incrociata fra pi = N / somma(N) (sul menu, voci non visitate 0) e il softmax dei logit;
valore = errore quadratico fra `value` della rete e l'esito. Il valore della rete e' dal posto di chi decide: l'osservazione
`x` e' costruita da quel posto, e l'esito e' quello dello stesso posto. Perdita totale di un passo = politica (sul
minibatch di decisioni) + peso_valore x errore quadratico medio sull'unione del minibatch di decisioni e di quello di
stati di fine turno. Nessun termine di entropia.
Scelta dell'epoca: perdita di sviluppo = entropia incrociata delle decisioni + peso_valore x errore quadratico medio
(decisioni e stati insieme) sull'insieme di sviluppo; `rete.pt` e' l'epoca con la perdita minore (la verifica non
interviene mai nella scelta).
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CKPT_DEFAULT = "runs/sett/ekris_s12/ckpt_040000.pt"
BATCH_VALUTAZIONE = 1024


# -- dati ---------------------------------------------------------------------------------------

def carica_dati(raccolta: Path, insiemi=("allenamento", "sviluppo", "verifica"), scrivi=print) -> dict:
    """{insieme: {"dec": [dict], "stati": {"x","q","ctx","esito"} | None}} dalle partite della raccolta."""
    from riftbound.rs import raccolta as R
    righe = R.indice(raccolta)
    out = {k: {"dec": [], "x": [], "q": [], "ctx": [], "esito": []} for k in insiemi}
    scartate = 0
    for r in righe:
        ins = r["insieme"]
        if ins not in out:
            continue
        d = R.carica(raccolta / r["file"])
        o = out[ins]
        for rec in d["record"]:
            if rec["kind"] != "cercata" or "x" not in rec:
                continue
            n = np.asarray(rec["N"], dtype=np.float64)
            if len(rec["otype"]) != len(n) or n.sum() <= 0:
                scartate += 1
                continue
            o["dec"].append({"x": rec["x"], "q": int(rec["q"]), "src": 0, "ctx": rec["ctx"], "otype": rec["otype"],
                             "ocards": rec["ocards"], "ofeats": rec["ofeats"], "a": 0, "logp": 0.0,
                             "pi": (n / n.sum()).astype(np.float32), "esito": float(rec["esito"])})
        for st in d["stati"]:
            o["x"].append(st["x"])
            o["q"].append(int(st["q"]))
            o["ctx"].append(st["ctx"])
            o["esito"].append(float(st["esito"]))
    res = {}
    for k, o in out.items():
        res[k] = {"dec": o["dec"], "stati": ({"x": np.stack(o["x"]).astype(np.float32), "q": np.array(o["q"], dtype=np.int64),
                                              "ctx": np.stack(o["ctx"]).astype(np.float32),
                                              "esito": np.array(o["esito"], dtype=np.float32)} if o["x"] else None)}
        scrivi(f"  {k}: {len(o['dec'])} decisioni, {len(o['x'])} stati di fine turno")
    if scartate:
        scrivi(f"  scartati {scartate} record (menu e visite non allineati o senza visite)")
    return res


def _batch_dec(recs: list, device):
    import torch
    from riftbound.ai.ppo.train import tensors
    t = tensors(recs, device)
    m = t["otype"].shape[1]
    pi = np.zeros((len(recs), m), dtype=np.float32)
    for i, r in enumerate(recs):
        pi[i, :len(r["pi"])] = r["pi"]
    t["pi"] = torch.as_tensor(pi).to(device)
    t["esito"] = torch.as_tensor(np.array([r["esito"] for r in recs], dtype=np.float32)).to(device)
    return t


def _batch_stati(s: dict, idx, device):
    import torch
    n = len(idx)
    return {"x": torch.as_tensor(s["x"][idx]).to(device), "q": torch.as_tensor(s["q"][idx]).to(device),
            "src": torch.zeros(n, dtype=torch.long, device=device),
            "ctx": torch.as_tensor(s["ctx"][idx]).to(device),
            "otype": torch.zeros(n, 1, dtype=torch.long, device=device),
            "ocards": torch.zeros(n, 1, 3, dtype=torch.long, device=device),
            "ofeats": torch.zeros(n, 1, _f_opt(), device=device),
            "omask": torch.ones(n, 1, dtype=torch.bool, device=device),
            "esito": torch.as_tensor(s["esito"][idx]).to(device)}


def _f_opt() -> int:
    from riftbound.ai.ppo.features import F_OPT
    return F_OPT


def _fwd(net, t: dict):
    return net(t["x"], t["q"], t["src"], t["ctx"], t["otype"], t["ocards"], t["ofeats"], t["omask"])


def _ce(logits, t: dict):
    """Entropia incrociata fra pi e il softmax dei logit, per riga (le voci padding hanno pi 0 e logit -1e9)."""
    import torch
    logp = torch.log_softmax(logits, dim=1).masked_fill(~t["omask"], 0.0)
    return -(t["pi"] * logp).sum(1)


# -- misure -------------------------------------------------------------------------------------

def misura(net, dati: dict, device, riferimento=None) -> dict:
    """Le misure della rete su un insieme (e, se data, della rete di partenza sugli stessi dati)."""
    import torch
    net.eval()
    out = {}
    dec, st = dati["dec"], dati["stati"]
    with torch.no_grad():
        acc = {"ce": 0.0, "h": 0.0, "top1": 0.0, "v_sq": 0.0, "v_sg": 0.0, "v_n": 0, "n": 0}
        accr = {"ce": 0.0, "top1": 0.0, "v_sq": 0.0, "v_sg": 0.0}
        for b in range(0, len(dec), BATCH_VALUTAZIONE):
            t = _batch_dec(dec[b:b + BATCH_VALUTAZIONE], device)
            logits, v = _fwd(net, t)
            ce = _ce(logits, t)
            h = -(t["pi"] * torch.log(t["pi"].clamp_min(1e-12))).sum(1)
            acc["ce"] += float(ce.sum())
            acc["h"] += float(h.sum())
            piv = t["pi"].masked_fill(~t["omask"], -1.0)
            acc["top1"] += float((logits.argmax(1) == piv.argmax(1)).sum())
            e = t["esito"]
            acc["v_sq"] += float(((v - e) ** 2).sum())
            nz = e != 0
            acc["v_sg"] += float((torch.sign(v)[nz] == torch.sign(e)[nz]).sum())
            acc["v_n"] += int(nz.sum())
            acc["n"] += len(t["x"])
            if riferimento is not None:
                lr, vr = _fwd(riferimento, t)
                accr["ce"] += float(_ce(lr, t).sum())
                accr["top1"] += float((lr.argmax(1) == piv.argmax(1)).sum())
                accr["v_sq"] += float(((vr - e) ** 2).sum())
                accr["v_sg"] += float((torch.sign(vr)[nz] == torch.sign(e)[nz]).sum())
        n = max(acc["n"], 1)
        vn = max(acc["v_n"], 1)
        out["decisioni"] = {"n": acc["n"], "politica_ce": acc["ce"] / n, "kl": (acc["ce"] - acc["h"]) / n,
                            "top1_con_la_piu_visitata": acc["top1"] / n, "valore_eqm": acc["v_sq"] / n,
                            "valore_segno": acc["v_sg"] / vn}
        if riferimento is not None:
            out["decisioni_partenza"] = {"politica_ce": accr["ce"] / n, "kl": (accr["ce"] - acc["h"]) / n,
                                         "top1_con_la_piu_visitata": accr["top1"] / n, "valore_eqm": accr["v_sq"] / n,
                                         "valore_segno": accr["v_sg"] / vn}
        if st is not None:
            s = {"sq": 0.0, "sg": 0.0, "nz": 0, "sqr": 0.0, "sgr": 0.0}
            total = len(st["x"])
            for b in range(0, total, BATCH_VALUTAZIONE):
                t = _batch_stati(st, np.arange(b, min(b + BATCH_VALUTAZIONE, total)), device)
                _, v = _fwd(net, t)
                e = t["esito"]
                nz = e != 0
                s["sq"] += float(((v - e) ** 2).sum())
                s["sg"] += float((torch.sign(v)[nz] == torch.sign(e)[nz]).sum())
                s["nz"] += int(nz.sum())
                if riferimento is not None:
                    _, vr = _fwd(riferimento, t)
                    s["sqr"] += float(((vr - e) ** 2).sum())
                    s["sgr"] += float((torch.sign(vr)[nz] == torch.sign(e)[nz]).sum())
            nz = max(s["nz"], 1)
            out["stati_fine_turno"] = {"n": total, "valore_eqm": s["sq"] / total, "valore_segno": s["sg"] / nz}
            if riferimento is not None:
                out["stati_fine_turno_partenza"] = {"valore_eqm": s["sqr"] / total, "valore_segno": s["sgr"] / nz}
    return out


def perdita_sviluppo(m: dict, peso_valore: float) -> float:
    d, s = m["decisioni"], m.get("stati_fine_turno")
    sq, n = d["valore_eqm"] * d["n"], d["n"]
    if s is not None:
        sq += s["valore_eqm"] * s["n"]
        n += s["n"]
    return d["politica_ce"] + peso_valore * sq / max(n, 1)


def riga_misure(m: dict) -> str:
    d, s = m["decisioni"], m.get("stati_fine_turno")
    txt = (f"politica CE {d['politica_ce']:.4f} KL {d['kl']:.4f} top1 {d['top1_con_la_piu_visitata']:.3f} | "
           f"valore decisioni EQM {d['valore_eqm']:.4f} segno {d['valore_segno']:.3f}")
    if s is not None:
        txt += f" | valore fine turno EQM {s['valore_eqm']:.4f} segno {s['valore_segno']:.3f}"
    return txt


# -- allenamento --------------------------------------------------------------------------------

def dispositivo(scelta: str | None = None):
    import torch
    if scelta:
        return torch.device(scelta)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def rete_di_partenza(init: str | None, casuali: bool):
    import torch
    from riftbound.ai.ppo.model import PPONet, load
    if casuali:
        torch.manual_seed(0)
        return PPONet()
    return load(init)


def allena(raccolta: Path, out: Path, init: str | None, casuali: bool = False, epoche: int = 10, lr: float = 1e-4,
           minibatch: int = 512, peso_valore: float = 1.0, seme: int = 0, scegli_dispositivo: str | None = None,
           prova: bool = False, scrivi=print) -> dict:
    """Allena e scrive `out`/rete.pt, misure.json, misure.txt, provenienza.json. `prova`: con gli insiemi di sviluppo
    e di verifica vuoti (una mini raccolta) usa l'allenamento al loro posto (solo per le prove)."""
    import hashlib
    import os
    import torch
    from riftbound import provenienza as P
    from riftbound.ai.ppo.model import save
    out.mkdir(parents=True, exist_ok=True)
    dev = dispositivo(scegli_dispositivo)
    if dev.type == "cpu":
        torch.set_num_threads(max(1, min(os.cpu_count() or 1, 8)))
    torch.manual_seed(seme)
    rng = np.random.default_rng(seme)
    t0 = time.time()
    scrivi(f"dispositivo {dev}; carico {raccolta}")
    dati = carica_dati(raccolta, scrivi=scrivi)
    if prova:
        for k in ("sviluppo", "verifica"):
            if not dati[k]["dec"]:
                dati[k] = dati["allenamento"]
                scrivi(f"  PROVA: {k} = allenamento (insieme vuoto)")
    tr = dati["allenamento"]
    if not tr["dec"]:
        raise SystemExit("nessuna decisione cercata nell'insieme di allenamento")
    net = rete_di_partenza(init, casuali).to(dev)
    base = copy.deepcopy(net).eval()
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    st = tr["stati"]
    n_dec = len(tr["dec"])
    storia, migliore, best = [], None, None
    m0 = misura(net, dati["sviluppo"], dev, base)
    scrivi(f"partenza  sviluppo: {riga_misure(m0)}")
    for ep in range(1, epoche + 1):
        net.train()
        perm = rng.permutation(n_dec)
        perm_st = rng.permutation(len(st["x"])) if st is not None else None
        somma = {"pol": 0.0, "val": 0.0, "passi": 0}
        for i, b in enumerate(range(0, n_dec, minibatch)):
            recs = [tr["dec"][j] for j in perm[b:b + minibatch]]
            t = _batch_dec(recs, dev)
            logits, v = _fwd(net, t)
            pol = _ce(logits, t).mean()
            sq = (v - t["esito"]) ** 2
            if st is not None:
                k = len(perm_st)
                idx = perm_st[(i * minibatch + np.arange(minibatch)) % k]
                ts = _batch_stati(st, idx, dev)
                _, vs = _fwd(net, ts)
                sq = torch.cat([sq, (vs - ts["esito"]) ** 2])
            val = sq.mean()
            loss = pol + peso_valore * val
            opt.zero_grad()
            loss.backward()
            opt.step()
            somma["pol"] += float(pol.detach())
            somma["val"] += float(val.detach())
            somma["passi"] += 1
        m = misura(net, dati["sviluppo"], dev, base)
        pd = perdita_sviluppo(m, peso_valore)
        storia.append({"epoca": ep, "allenamento": {"politica_ce": somma["pol"] / somma["passi"],
                                                    "valore_eqm": somma["val"] / somma["passi"]},
                       "sviluppo": m, "perdita_sviluppo": pd})
        scrivi(f"epoca {ep:2d}  allenamento CE {somma['pol'] / somma['passi']:.4f} EQM {somma['val'] / somma['passi']:.4f}"
               f" | sviluppo {riga_misure(m)} | perdita {pd:.4f} ({time.time() - t0:.0f} s)")
        if migliore is None or pd < migliore:
            migliore, best = pd, (ep, copy.deepcopy({k: v.detach().cpu() for k, v in net.state_dict().items()}))
    ep_best, stato = best
    net.load_state_dict(stato)
    net.cpu().eval()
    save(net, out / "rete.pt")
    net.to(dev)
    finale = {"sviluppo": storia[ep_best - 1]["sviluppo"], "verifica": misura(net, dati["verifica"], dev, base)}
    totale = (f"totale: epoca scelta {ep_best}/{epoche}, perdita di sviluppo {migliore:.4f}; verifica: "
              f"{riga_misure(finale['verifica'])}; {time.time() - t0:.0f} s")
    misure = {"epoca_scelta": ep_best, "epoche": storia, "finale": finale, "dispositivo": str(dev),
              "secondi": round(time.time() - t0, 1),
              "dati": {k: {"decisioni": len(v["dec"]), "stati_fine_turno": 0 if v["stati"] is None else len(v["stati"]["x"])}
                       for k, v in dati.items()}}
    (out / "misure.json").write_text(json.dumps(misure, indent=1))
    righe = [f"allenamento da {raccolta}", f"epoca scelta {ep_best} di {epoche} (perdita di sviluppo {migliore:.4f})"]
    for s in storia:
        righe.append(f"epoca {s['epoca']:2d} sviluppo: {riga_misure(s['sviluppo'])} | perdita {s['perdita_sviluppo']:.4f}")
    for k in ("sviluppo", "verifica"):
        f = finale[k]
        righe.append(f"{k} (epoca {ep_best}): {riga_misure(f)}")
        if "decisioni_partenza" in f:
            d0, s0 = f["decisioni_partenza"], f.get("stati_fine_turno_partenza")
            righe.append(f"{k} (rete di partenza): politica CE {d0['politica_ce']:.4f} KL {d0['kl']:.4f} top1 "
                         f"{d0['top1_con_la_piu_visitata']:.3f} | valore decisioni EQM {d0['valore_eqm']:.4f} segno "
                         f"{d0['valore_segno']:.3f}" + (f" | valore fine turno EQM {s0['valore_eqm']:.4f} segno "
                                                        f"{s0['valore_segno']:.3f}" if s0 else ""))
    righe.append(totale)
    (out / "misure.txt").write_text("\n".join(righe) + "\n")
    sha = None
    if init and not casuali and Path(init).is_file():
        h = hashlib.sha256()
        with open(init, "rb") as f:
            for blocco in iter(lambda: f.read(1 << 20), b""):
                h.update(blocco)
        sha = h.hexdigest()
    prov = {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "raccolta": str(raccolta),
            "raccolta_provenienza": (json.loads((raccolta / "provenienza.json").read_text())
                                     if (raccolta / "provenienza.json").is_file() else None),
            "partenza": {"file": None if casuali else str(init), "sha256": sha, "pesi_casuali": bool(casuali)},
            "iperparametri": {"epoche": epoche, "lr": lr, "minibatch": minibatch, "peso_valore": peso_valore,
                              "seme": seme, "ottimizzatore": "Adam", "prova": prova},
            "dispositivo": str(dev), "revisione": P.revisione(), "estensione_rust": P.estensione_rust(),
            "rete_pt_sha256": hashlib.sha256((out / "rete.pt").read_bytes()).hexdigest()}
    (out / "provenienza.json").write_text(json.dumps(prov, indent=1))
    scrivi(totale)
    return misure
