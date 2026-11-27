"""Analisi dell'esperimento «fondo»: dove sbaglia il campione e quanto e' affidabile la sua valutazione (Q).

Uso: python scripts/rust/fondo_analisi.py <cartella fondo/>   (scrive analisi.txt e analisi.json nella cartella sopra)
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

TIPI = ["Pass", "Deploy campione", "Play (carta)", "Play su campo", "Cast (magia)", "Move avanti", "Move ritirata",
        "Hide", "Equip/Activate/Gear"]
SOGLIE = [0.0, 0.1, 0.2, 0.3]


def tipo(m: str) -> str:
    if m == "Pass":
        return "Pass"
    if m.startswith("Deploy champion"):
        return "Deploy campione"
    if m.startswith("Play "):
        return "Play su campo" if re.search(r" to BF\d$", m) else "Play (carta)"
    if m.startswith("Cast "):
        return "Cast (magia)"
    if m.startswith("Move "):
        return "Move ritirata" if m.endswith("→base") else "Move avanti"
    if m.startswith("Hide "):
        return "Hide"
    return "Equip/Activate/Gear"


def carta(m: str) -> str | None:
    for pat in (r"^Deploy champion (.+)$", r"^Play (.+?)(?: to BF\d)?$", r"^Cast (.+?) @BF\d$", r"^Hide (.+?) @BF\d$",
                r"^Equip (.+)$", r"^Move (.+?) (?:base|BF\d)→\w+$", r"^Activate \w+ \((.+)\)$"):
        mm = re.match(pat, m)
        if mm:
            return mm.group(1)
    return None


def fase(t: int) -> str:
    return "turno<=3" if t <= 3 else ("turno 4-6" if t <= 6 else "turno>=7")


def rango(x):
    x = np.asarray(x, float)
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    s = x[o]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and s[j + 1] == s[i]:
            j += 1
        r[o[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return float("nan")
    ra, rb = rango(a), rango(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def acc(pairs, soglia):
    """pairs: (ordine_stimato, differenza_vera). Accordo = segno uguale; differenze nulle escluse."""
    sel = [(s, d) for s, d in pairs if abs(d) >= max(soglia, 1e-12) and s != 0]
    if not sel:
        return {"n": 0, "accordo": None}
    return {"n": len(sel), "accordo": float(np.mean([np.sign(s) == np.sign(d) for s, d in sel]))}


def main(cart: Path):
    out_dir = cart.parent
    dec = {}
    for riga in open(cart / "decisioni.jsonl"):
        r = json.loads(riga)
        for d in r["decisioni"]:
            dec[(d["nome"], d["k"])] = d
    pos = []
    for d in sorted(p for p in cart.iterdir() if p.is_dir()):
        m = re.match(r"^(\d+)_(.*)_k(\d+)$", d.name)
        if not m:
            continue
        s = json.loads((d / "scelta.json").read_text())
        info = dec.get((m.group(2), int(m.group(3))), {})
        p = {"id": d.name, "matchup": info.get("matchup", "?"), "turno": info.get("turno", 0), "cand": s["candidati"],
             "n": s["n"], "q": s["q"], "medie": s.get("medie"), "scelta": s["scelta"], "R": None, "delta": None}
        f = d / "scelta_mondi.jsonl"
        if f.exists() and len(s["candidati"]) >= 2:
            per = defaultdict(dict)
            for l in open(f):
                for x in json.loads(l):
                    per[x["world"]][x["line"]] = x["returns"]
            nc = len(s["candidati"])
            mat = [[w[f"c{j}"] for j in range(nc)] for w in per.values() if all(f"c{j}" in w for j in range(nc))]
            p["R"] = np.array(mat, float).T  # candidati x mondi
        v = d / "verifica.json"
        if v.exists():
            p["delta"] = float(json.loads(v.read_text())["media"])
            p["deltas"] = json.loads(v.read_text())["deltas"]
        pos.append(p)
    campo = [p for p in pos if p["R"] is not None]
    camb = [p for p in pos if p["scelta"] != 0 and p["delta"] is not None]
    J = {"n_posizioni": len(pos), "n_con_mondi": len(campo), "n_cambiate": len(camb)}
    L = []
    w = L.append
    w(f"Posizioni {len(pos)}, con >=2 candidati e mondi {len(campo)}, cambiate {len(camb)}; "
      f"delta medio sulle cambiate {np.mean([p['delta'] for p in camb]):+.4f}, "
      f"su tutte le posizioni {np.sum([p['delta'] or 0 for p in pos]) / len(pos):+.4f}")

    # ---------------- A
    w("\n=== A. Che mosse sbaglia il campione ===\nTipi: " + ", ".join(TIPI))
    tt = defaultdict(list)
    for p in camb:
        tt[(tipo(p["cand"][0]), tipo(p["cand"][p["scelta"]]))].append(p["delta"])
    w("\nA1. Tipo campione -> tipo Pensa (cambiate): n, delta medio, somma delta")
    righe = sorted(tt.items(), key=lambda kv: -len(kv[1]))
    J["A_tipo_tipo"] = []
    for (a, b), ds in righe:
        w(f"  {a:20s} -> {b:20s} n={len(ds):3d} delta={np.mean(ds):+.3f} somma={np.sum(ds):+.2f}")
        J["A_tipo_tipo"].append({"campione": a, "pensa": b, "n": len(ds), "delta": float(np.mean(ds)), "somma": float(np.sum(ds))})
    for nome, fn in (("fase", lambda p: fase(p["turno"])), ("matchup", lambda p: p["matchup"])):
        g = defaultdict(list)
        allg = Counter()
        for p in pos:
            allg[fn(p)] += 1
        for p in camb:
            g[fn(p)].append(p["delta"])
        w(f"\nA2. Cambiate per {nome}: n cambiate / n posizioni, delta medio, contributo (somma delta / posizioni totali)")
        J[f"A_{nome}"] = {}
        for k in sorted(allg):
            ds = g.get(k, [])
            c = float(np.sum(ds)) / allg[k]
            w(f"  {k:10s} {len(ds):3d}/{allg[k]:3d} delta={np.mean(ds) if ds else float('nan'):+.3f} contributo={c:+.4f}")
            J[f"A_{nome}"][k] = {"cambiate": len(ds), "posizioni": allg[k], "delta": float(np.mean(ds)) if ds else None, "contributo": c}
    # confronto
    w("\nA3. Sulle posizioni con >=2 candidati: quanto spesso il campione sceglie il tipo, tasso di cambio per tipo, delta medio")
    cc = Counter(); ch = Counter(); dd = defaultdict(list)
    m2 = [p for p in pos if len(p["cand"]) >= 2]
    for p in m2:
        t = tipo(p["cand"][0])
        cc[t] += 1
        if p["scelta"] != 0 and p["delta"] is not None:
            ch[t] += 1
            dd[t].append(p["delta"])
    J["A_confronto"] = {}
    for t in TIPI:
        if cc[t]:
            w(f"  {t:20s} scelto {cc[t]:3d} ({cc[t] / len(m2):5.1%})  cambiato {ch[t]:3d} ({ch[t] / cc[t]:5.1%})  delta medio sui cambi {np.mean(dd[t]) if dd[t] else float('nan'):+.3f}")
            J["A_confronto"][t] = {"scelto": cc[t], "cambiato": ch[t], "tasso": ch[t] / cc[t]}
    w(f"  (posizioni con >=2 candidati: {len(m2)})")
    # tipo di Pensa come destinazione
    cp = Counter(tipo(p["cand"][p["scelta"]]) for p in camb)
    w("  Tipo scelto da Pensa sulle cambiate: " + ", ".join(f"{k} {v}" for k, v in cp.most_common()))
    # top 12
    w("\nA4. Le 12 cambiate con delta piu' alto (matchup, turno, campione | Pensa, delta, n, q dei candidati)")
    J["A_top12"] = []
    for p in sorted(camb, key=lambda p: -p["delta"])[:12]:
        w(f"  {p['id']} {p['matchup']} t{p['turno']}: {p['cand'][0]} | {p['cand'][p['scelta']]} delta={p['delta']:+.2f} "
          f"n={p['n']} q={[round(x, 3) for x in p['q']]} medie={[round(x, 2) for x in p['medie']]}")
        J["A_top12"].append({"id": p["id"], "matchup": p["matchup"], "turno": p["turno"], "campione": p["cand"][0],
                             "pensa": p["cand"][p["scelta"]], "delta": p["delta"], "n": p["n"], "q": p["q"], "medie": p["medie"]})
    # carte
    cd = defaultdict(list)
    for p in camb:
        for lato, m in (("camp", p["cand"][0]), ("pensa", p["cand"][p["scelta"]])):
            c = carta(m)
            if c:
                cd[(c, lato)].append(p["delta"])
    w("\nA5. Carte piu' ricorrenti nei cambi: n volte come mossa del campione (rimossa) / di Pensa (scelta), delta medio dei cambi in cui compaiono")
    cart_n = defaultdict(lambda: {"camp": [], "pensa": []})
    for (c, lato), ds in cd.items():
        cart_n[c][lato] = ds
    J["A_carte"] = []
    for c, v in sorted(cart_n.items(), key=lambda kv: -(len(kv[1]["camp"]) + len(kv[1]["pensa"])))[:15]:
        tot = v["camp"] + v["pensa"]
        w(f"  {c:30s} campione {len(v['camp']):2d}  pensa {len(v['pensa']):2d}  delta medio {np.mean(tot):+.3f}"
          f"  (quando e' del campione {np.mean(v['camp']) if v['camp'] else float('nan'):+.3f}, di Pensa {np.mean(v['pensa']) if v['pensa'] else float('nan'):+.3f})")
        J["A_carte"].append({"carta": c, "come_campione": len(v["camp"]), "come_pensa": len(v["pensa"]), "delta": float(np.mean(tot))})

    # ---------------- B
    w("\n=== B. Affidabilita' della valutazione ===")
    qa = np.array([x for p in pos for x in p["q"]])
    qq = np.quantile(qa, [0, .01, .05, .25, .5, .75, .95, .99, 1])
    w("B1. Scala di tutte le q (min, 1%, 5%, 25%, 50%, 75%, 95%, 99%, max): " + ", ".join(f"{x:.3f}" for x in qq))
    q0 = np.array([p["q"][0] for p in campo]); m0 = np.array([p["medie"][0] for p in campo])
    qturno = defaultdict(list)
    for p in pos:
        qturno[fase(p["turno"])].append(p["q"][0])
    w("    q[0] mediana per fase: " + ", ".join(f"{k} {np.median(v):.3f}" for k, v in sorted(qturno.items())) +
      f";  q<0: {np.mean(qa < 0):.1%}, q>1: {np.mean(qa > 1):.1%}")
    J["B_scala"] = {"quantili": [float(x) for x in qq], "frac_neg": float(np.mean(qa < 0)), "frac_sopra1": float(np.mean(qa > 1))}
    rho = spearman(q0, m0)
    w(f"\nB2. Valore: Spearman q[0] vs medie[0] su {len(campo)} posizioni: {rho:+.3f}; media di medie[0] = {m0.mean():.3f}")
    J["B_spearman"] = {"tutte": rho}
    # intervallo bootstrap
    rng = np.random.default_rng(0)
    bs = [spearman(q0[i], m0[i]) for i in (rng.integers(0, len(q0), len(q0)) for _ in range(500))]
    w(f"    IC95 bootstrap sulle posizioni: [{np.nanpercentile(bs, 2.5):+.3f}, {np.nanpercentile(bs, 97.5):+.3f}]")
    def decili(q, m, k):
        e = np.quantile(q, np.linspace(0, 1, k + 1)); e[-1] += 1e-9
        res = []
        for i in range(k):
            s = (q >= e[i]) & (q < e[i + 1])
            res.append((e[i], e[i + 1], int(s.sum()), float(m[s].mean()) if s.any() else float("nan")))
        return res
    w("    Decili di q[0]: [da, a) n media(medie[0])")
    J["B_decili"] = []
    for a, b, n, mm in decili(q0, m0, 10):
        w(f"      [{a:7.3f},{b:7.3f}) n={n:3d} {mm:.3f}")
        J["B_decili"].append({"da": float(a), "a": float(b), "n": n, "media": mm})
    ph = defaultdict(list)
    for p in campo:
        ph[fase(p["turno"])].append(p)
    for f_, ps in sorted(ph.items()):
        a = np.array([p["q"][0] for p in ps]); b = np.array([p["medie"][0] for p in ps])
        r = spearman(a, b)
        J["B_spearman"][f_] = r
        w(f"    {f_}: n={len(ps)} Spearman {r:+.3f}; quintili di q[0] -> media medie[0]: " +
          ", ".join(f"{mm:.2f}" for *_, mm in decili(a, b, 5)))
    for mu in sorted({p["matchup"] for p in campo}):
        ps = [p for p in campo if p["matchup"] == mu]
        r = spearman([p["q"][0] for p in ps], [p["medie"][0] for p in ps])
        J["B_spearman"][mu] = r
        w(f"    matchup {mu}: n={len(ps)} Spearman {r:+.3f}")

    # coppie (0, j)
    pq, pn, rows = [], [], []
    for p in campo:
        for j in range(1, len(p["cand"])):
            dm = p["medie"][j] - p["medie"][0]
            rows.append({"dm": dm, "sq": np.sign(p["q"][j] - p["q"][0]), "sn": np.sign(p["n"][j] - p["n"][0]),
                         "dq": abs(p["q"][j] - p["q"][0]), "R": p["R"], "j": j})
    w(f"\nB3. Ordine fra candidati: coppie (0,j) con mondi: {len(rows)}; medie pari (escluse): {sum(r['dm'] == 0 for r in rows)}; "
      f"visite pari (escluse dal conto visite): {sum(r['sn'] == 0 for r in rows)}")
    w("    accordo con l'ordine delle medie (32 mondi); soglia su |diff. medie|")
    J["B_accordo"] = {}
    for nome, k in (("Q", "sq"), ("visite", "sn")):
        J["B_accordo"][nome] = {}
        pairs = [(r[k], r["dm"]) for r in rows]
        txt = []
        for s in SOGLIE:
            a = acc(pairs, s)
            J["B_accordo"][nome][str(s)] = a
            txt.append(f">={s}: {a['accordo']:.1%} (n={a['n']})" if a["accordo"] is not None else f">={s}: n/d")
        w(f"      {nome:7s} " + "  ".join(txt))
    # per stesso insieme (non pari in entrambi)
    pr = [r for r in rows if r["sn"] != 0 and r["sq"] != 0 and r["dm"] != 0]
    w(f"    Stesse coppie per Q e visite (nessun pari, n={len(pr)}): Q {np.mean([r['sq'] == np.sign(r['dm']) for r in pr]):.1%}, "
      f"visite {np.mean([r['sn'] == np.sign(r['dm']) for r in pr]):.1%}")
    J["B_accordo"]["stesse_coppie"] = {"n": len(pr), "Q": float(np.mean([r['sq'] == np.sign(r['dm']) for r in pr])),
                                       "visite": float(np.mean([r['sn'] == np.sign(r['dm']) for r in pr]))}
    # per gap di Q
    dqa = np.array([r["dq"] for r in rows])
    tr = np.quantile(dqa, [1 / 3, 2 / 3])
    w("    Accordo Q per ampiezza del gap di Q (terzili): " + ", ".join(
        f"{lab} {acc([(r['sq'], r['dm']) for r in rows if lo <= r['dq'] < hi], 0)['accordo']:.1%}"
        for lab, lo, hi in (("piccolo", 0, tr[0]), ("medio", tr[0], tr[1]), ("grande", tr[1], 9))))
    # dove i candidati sono 'sbagliati': quota dove la media di j > media di 0
    w(f"    Quota coppie in cui la media (32 mondi) del candidato j supera quella del campione: {np.mean([r['dm'] > 0 for r in rows]):.1%}; "
      f"di queste Q dice 'campione meglio' sempre (coerente)")

    # cambiate: verifica
    w(f"\nB4. Sulle {len(camb)} cambiate, delta di verifica (100 mondi nuovi) come verita'")
    cp_ = []
    for p in camb:
        j = p["scelta"]
        cp_.append((np.sign(p["q"][j] - p["q"][0]), np.sign(p["n"][j] - p["n"][0]), p["delta"]))
    J["B_cambiate"] = {"delta_medio": float(np.mean([p["delta"] for p in camb]))}
    for nome, i in (("Q", 0), ("visite", 1)):
        J["B_cambiate"][nome] = {}
        txt = []
        for s in SOGLIE:
            a = acc([(c[i], c[2]) for c in cp_], s)
            J["B_cambiate"][nome][str(s)] = a
            txt.append(f">={s}: {a['accordo']:.1%} (n={a['n']})" if a["accordo"] is not None else f">={s}: n/d")
        w(f"      {nome:7s} " + "  ".join(txt))
    dl = np.array([c[2] for c in cp_])
    w(f"    delta>0 in {np.mean(dl > 0):.1%}, delta<0 in {np.mean(dl < 0):.1%}, =0 in {np.mean(dl == 0):.1%}; delta medio {dl.mean():+.3f} "
      f"(IC95 su posizioni {dl.mean() - 1.96 * dl.std(ddof=1) / math.sqrt(len(dl)):+.3f}..{dl.mean() + 1.96 * dl.std(ddof=1) / math.sqrt(len(dl)):+.3f})")
    # selezione: media 32 mondi del guadagno di Pensa vs verifica
    gs = np.array([p["medie"][p["scelta"]] - p["medie"][0] for p in camb])
    w(f"    Guadagno visto sui 32 mondi di scelta (da cui Pensa ha scelto): {gs.mean():+.3f}; sui 100 mondi nuovi: {dl.mean():+.3f} "
      f"(la differenza e' il 'vincitore tra rumore')")
    J["B_cambiate"]["guadagno_32"] = float(gs.mean())
    J["B_cambiate"]["delta_100"] = float(dl.mean())
    # confronto dei delta 100 mondi: per fase di |gap Q| delle cambiate
    # rumore
    w("\nB5. Rumore (limite dell'accordo anche con Q perfette)")
    ses = []
    for r in rows:
        R = r["R"]; d = R[r["j"]] - R[0]
        ses.append(d.std(ddof=1) / math.sqrt(len(d)))
    ses = np.array(ses)
    w(f"    SE della differenza appaiata (stesso mondo) fra due candidati: mediana {np.median(ses):.3f}, media {ses.mean():.3f} "
      f"(la SE di una media singola ~0,09; il confronto appaiato e' piu' stretto per la correlazione fra linee)")
    dmv = np.array([r["dm"] for r in rows])
    pe = []
    for s in SOGLIE:
        sel = (np.abs(dmv) >= max(s, 1e-12)) & (ses > 0)
        pe.append((s, float(np.mean([Phi(abs(d) / e) for d, e in zip(dmv[sel], ses[sel])])), int(sel.sum())))
    w("    Accordo atteso dal solo rumore se Q fosse perfetta, ricavato dalle differenze osservate (stima OTTIMISTA: |diff.| osservate sono gonfiate dal rumore): " +
      "  ".join(f">={s}: {a:.1%} (n={n})" for s, a, n in pe))
    # split-half
    rng = np.random.default_rng(1)
    sh = []
    for r in rows:
        R = r["R"]; nm = R.shape[1]
        agree = []
        for _ in range(50):
            perm = rng.permutation(nm); a, b = perm[:nm // 2], perm[nm // 2:]
            da = R[r["j"], a].mean() - R[0, a].mean(); db = R[r["j"], b].mean() - R[0, b].mean()
            if da != 0 and db != 0:
                agree.append(np.sign(da) == np.sign(db))
        sh.append((float(np.mean(agree)) if agree else float("nan"), r["dm"]))
    shv = [x for x, _ in sh if not math.isnan(x)]
    w(f"    Split-half (due meta' da 16 mondi): accordo medio fra le due meta' (come test-retest a 16 mondi): {np.mean(shv):.1%} "
      f"(coppie con parita' nelle meta' escluse). Con 32 mondi l'accordo reale con la verita' sarebbe un po' piu' alto.")
    J["B_rumore"] = {"se_mediana": float(np.median(ses)), "atteso_Phi": {str(s): a for s, a, n in pe}, "split_half": float(np.mean(shv))}
    # simulazione: Q perfette = verita' nota; vera differenza ~ media osservata ridotta (shrink) 
    sim = []
    tv = dmv * 0.7
    for s in SOGLIE:
        sel = (np.abs(dmv) >= max(s, 1e-12)) & (ses > 0)
        sim.append((s, float(np.mean([Phi(abs(d) / e) for d, e in zip(tv[sel], ses[sel])]))))
    w("    Stessa stima con differenze vere ridotte del 30% (scenario prudente, soglia sulle osservate): " + "  ".join(f">={s}: {a:.1%}" for s, a in sim))
    J["B_rumore"]["atteso_ridotto30"] = {str(s): a for s, a in sim}
    txt = "\n".join(L) + "\n"
    (out_dir / "analisi.txt").write_text(txt)
    (out_dir / "analisi.json").write_text(json.dumps(J, indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(txt)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
