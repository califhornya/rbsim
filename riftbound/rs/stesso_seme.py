"""Serie «stesso seme»: una partita giocata da Matteo nella pagina coach (Evelynn contro il campione Sett) rifatta
dal Mac, da sola, dal turno 1, con lo stesso seme di partita, finche' Sett non vince (o finiscono i tentativi).

Il seme della partita (`replay.seed`) e' sempre quello della base: stesse mani, stessi mazzi, stessi campi, chi comincia.
Cambiano solo i semi delle ricerche:
- Sett (il posto avversario di Matteo): `seme_sett(j) = seed*2 + (posto == "B") + j`; j = 0 e' il seme di Sett nella
  partita di Matteo;
- Evelynn (il posto di Matteo): lo stesso campione (rete, iterazioni, valutazione, sonda di vittoria) con seme fisso
  `seed*2 + (posto == "B")` in tutta la serie.
Evelynn e' automatica dal turno 1: l'unico risultato contro Matteo e' la sua partita (`partita_matteo`, il termine di
confronto). Una «vittoria nella simulazione» di Sett NON e' una vittoria contro Matteo.

Registro leggibile (`registro`): una riga per decisione e per scelta di entrambi i posti, nel formato del `log` della
pagina (`RustGame._tech_line`: `T{turno} {posto} decision {PUNTO}: {etichetta}`, `T{turno} {posto} choice {kind}: ...`),
piu' una riga `T0 {posto} mulligan: ...` per posto (la pagina non la scrive: nel confronto col `log` salvato si salta).
"""
from __future__ import annotations

import json
import multiprocessing
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
DECK_DIR = ROOT / "riftbound" / "data" / "decks"
CONTESTO_VITTORIA = 12      # righe dopo la prima differenza vittoria/sconfitta
CONTESTO_MATTEO = 8         # righe dopo la prima differenza dal registro di Matteo
# Chiavi dell'evento di trace che non servono nel file degli eventi (stati interi e opzioni codificate).
_PESANTI = {"state_raw", "options_raw", "source_raw", "obs", "correzioni", "args", "win", "dying"}


# -- la base ----------------------------------------------------------------------------------------

def _mazzo(p: str) -> Path:
    """Il mazzo della partita salvata: il percorso se esiste, se no lo stesso nome in riftbound/data/decks/."""
    q = Path(p)
    if q.is_file():
        return q
    r = DECK_DIR / q.name
    if r.is_file():
        return r
    raise FileNotFoundError(f"mazzo {p}: non c'e' ne' li' ne' in {DECK_DIR}")


def _checkpoint(info: dict, ckpt: str | None) -> str:
    """`--ckpt`, se no `info.campione` della partita (cosi' com'e' o rispetto alla radice del repo), se no il default."""
    from riftbound.rs import decisione_rs as D
    if ckpt:
        return str(ckpt)
    c = info.get("campione")
    if c:
        for p in (Path(c), ROOT / c):
            if p.is_file():
                return str(p.resolve())
    return str(ROOT / D.CKPT_DEFAULT)


def base(path, ckpt: str | None = None, casuali: bool = False) -> dict:
    """La partita salvata dalla pagina come base della serie (formato del file 013325: `replay`, `info`, `result`,
    `winner`, `turns`, `log`). -> dict con: file, seed, umano (il posto di Matteo), camp (quello di Sett), deck_a, deck_b
    (percorsi esistenti), bf_a, bf_b, starter ("a"/"b"), iterazioni, regole, valutazione, answers, ckpt, casuali, max_turni
    e il salvato (winner, turns, log)."""
    from riftbound.rs import decisione_rs as D
    path = Path(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    rp = d["replay"]
    if rp.get("opponent") != "campione":
        raise ValueError("la partita non e' contro il campione")
    rp = {**rp, "deck_a": str(_mazzo(rp["deck_a"])), "deck_b": str(_mazzo(rp["deck_b"]))}
    # `_prepara` legge il file: gli passo una copia con i percorsi dei mazzi risolti.
    tmp = {"replay": rp, "info": d.get("info", {})}
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "p.json"
        f.write_text(json.dumps(tmp), encoding="utf-8")
        P = D._prepara({"tipo": "pagina", "file": str(f), "ckpt": _checkpoint(d.get("info", {}), ckpt),
                        "casuali": casuali})
    P["ckpt"] = str(P["ckpt"])
    P.update(file=str(path), nome=path.name,
             salvato={"winner": d.get("winner"), "turns": d.get("turns"), "log": d.get("log") or []})
    return P


def seme_sett(B: dict, j: int) -> int:
    return B["seed"] * 2 + (B["camp"] == "B") + j


def seme_evelynn(B: dict) -> int:
    return B["seed"] * 2 + (B["umano"] == "B")


# -- il registro ------------------------------------------------------------------------------------

class _Registro:
    """Il `watch` di trace_on che scrive il registro (e, se serve, gli eventi snelli). Le righe sono quelle della
    pagina: si usa `RustGame._tech_line` su un oggetto senza pagina (`s.gs` si carica dall'evento)."""

    def __init__(self, eventi: bool = False):
        from riftbound.ai.coach_rs import RustGame
        self.rg = RustGame.__new__(RustGame)
        self.rg.s = SimpleNamespace(gs=None, side=None)
        self.rg.objs = {}
        self.righe: list[str] = []
        self.eventi: list | None = [] if eventi else None

    def _riga(self, e: dict) -> str | None:
        k = e["k"]
        if k in ("decision", "choice"):
            try:
                return self.rg._tech_line(e)
            except Exception as exc:  # noqa: BLE001 — una riga che non si formatta non ferma la partita
                return f"? {e.get('seat')} {k} {e.get('kind') or e.get('point')} (non formattata: {exc!r})"
        if k == "decide_mulligan":
            try:
                self.rg._load(e)
                mano = [c.name for c in self.rg.s.gs.get_player(e["seat"]).hand]
                rese = ", ".join(mano[i] for i in e["out"]) or "none"
            except Exception as exc:  # noqa: BLE001
                rese = f"? ({exc!r})"
            return f"T0 {e['seat']} mulligan: {rese}"
        return None

    def watch(self, ev: str) -> None:
        e = json.loads(ev)
        riga = self._riga(e)
        if riga is not None:
            self.righe.append(riga)
        if self.eventi is not None:
            s = {k: v for k, v in e.items() if k not in _PESANTI}
            turno = (e.get("win") or {}).get("turn")
            if turno is not None:
                s["turno"] = turno
            if riga is not None:
                s["riga"] = riga
            self.eventi.append(s)


class _Finite(Exception):
    """Le risposte registrate di Matteo sono finite (partita salvata a meta': abbandonata)."""


def _gioca(B: dict, ask=None, sett_seme: int = 0, eventi: bool = False) -> dict:
    """Una partita completa con il seme di B. `ask` (le risposte di Matteo): il posto umano le segue e Sett e' il
    campione; senza, anche il posto di Matteo e' il campione (Evelynn automatica). -> dict (vedi `tentativo`)."""
    from riftbound.rs import decisione_rs as D
    from riftbound.rs import rust_bridge, vista_rs
    t0 = time.time()
    g = rust_bridge.build(B["seed"], Path(B["deck_a"]), Path(B["deck_b"]), B["starter"], B["max_turni"],
                          regole=B["regole"], bf_a=B["bf_a"], bf_b=B["bf_b"])
    probs = D.rete(B["ckpt"], B["casuali"])
    val = B.get("valutazione")
    posti = [(B["camp"], sett_seme)] + ([] if ask else [(B["umano"], seme_evelynn(B))])
    for seat, seme in posti:
        g.set_search_agent(seat, B["iterazioni"], seme, None, probs, False)
        g.set_search_win_probe(seat, bool(B.get("probe", True)))
        if val and val[0] != "storica":
            g.set_search_valutazione(seat, val[0], float(val[1]), float(val[2]))
    if ask:
        g.set_human_agent(B["umano"], ask, True, None)
    g.set_side_chooser()
    reg = _Registro(eventi)
    g.trace_on(reg.watch)
    errore = None
    try:
        winner, turni = g.start()
    except _Finite:
        winner, turni = None, None
        errore = "le risposte di Matteo sono finite"
    except Exception as exc:  # noqa: BLE001 — solo con le risposte di Matteo: se la partita diverge non regge
        if not ask:
            raise
        winner, turni = None, None
        errore = f"la partita diverge dalle risposte di Matteo: {exc}"
    try:
        gs, _ = vista_rs.carica(json.loads(g.raw_dump()))
        punti = {"A": gs.points_A, "B": gs.points_B}
    except Exception:  # noqa: BLE001
        punti = {"A": None, "B": None}
    return {"errore": errore, "vincitore": winner, "turni": turni, "punti": punti, "punti_sett": punti[B["camp"]],
            "punti_evelynn": punti[B["umano"]], "secondi": round(time.time() - t0, 2),
            "registro": reg.righe, "eventi": reg.eventi}


# -- la partita di Matteo ---------------------------------------------------------------------------

def _ask_matteo(answers: list):
    """Le risposte registrate, in ordine, con il controllo del tipo di `RustGame.ask`."""
    n = [0]

    def ask(ev: str):
        e = json.loads(ev)
        if n[0] >= len(answers):
            raise _Finite()
        kind, answer = answers[n[0]]
        if kind != e["k"]:
            raise ValueError(f"atteso {kind}, chiesto {e['k']} ({n[0]}): la partita non si riproduce")
        n[0] += 1
        return answer
    return ask


def _pagina(righe: list) -> list:
    """Le righe del registro come quelle del `log` della pagina (senza i mulligan)."""
    return [r for r in righe if not r.startswith("T0 ")]


def prefisso(a: list, b: list) -> int:
    """Quante righe iniziali hanno in comune."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def partita_matteo(B: dict, eventi: bool = False) -> dict:
    """La partita di Matteo rifatta come il rewind della pagina (il suo posto segue `answers`, Sett e' il campione con
    il seme della pagina, j = 0). Controllo: vincitore e turni come quelli salvati e righe del registro uguali al `log`
    salvato (prefisso comune e righe uguali in tutto). Non blocca se non coincide (con la rete casuale non coincide)."""
    r = _gioca(B, _ask_matteo(B["answers"]), seme_sett(B, 0), eventi)
    sal = B["salvato"]
    mio, log = _pagina(r["registro"]), sal["log"]
    r["controllo"] = {
        "vincitore_uguale": r["vincitore"] == sal["winner"], "turni_uguali": r["turni"] == sal["turns"],
        "vincitore_salvato": sal["winner"], "turni_salvati": sal["turns"],
        "righe": len(mio), "righe_salvate": len(log), "prefisso": prefisso(mio, log),
        "righe_uguali": sum(x == y for x, y in zip(mio, log)),
        "errore": r["errore"],
        "identica": r["vincitore"] == sal["winner"] and r["turni"] == sal["turns"] and mio == log}
    return r


# -- un tentativo e la serie ------------------------------------------------------------------------

def tentativo(B: dict, j: int, eventi: bool = False) -> dict:
    """Una partita completa, Evelynn automatica, Sett col seme `seme_sett(B, j)`. -> dict: j, seme_sett, seme_evelynn,
    vincitore, vince_sett, turni, punti (finali, per posto), punti_sett, punti_evelynn, secondi, registro (righe) ed
    eventi (snelli, solo con `eventi=True`; None se no)."""
    r = _gioca(B, None, seme_sett(B, j), eventi)
    return {"j": j, "seme_sett": seme_sett(B, j), "seme_evelynn": seme_evelynn(B),
            "vince_sett": r["vincitore"] == B["camp"], **r}


def _lavoro(args):
    B, j = args
    return tentativo(B, j)


def _senza_registro(t: dict) -> dict:
    return {k: v for k, v in t.items() if k not in ("registro", "eventi")}


def prima_differenza(a: list, b: list) -> int | None:
    """L'indice della prima riga diversa (anche se una e' finita prima dell'altra); None se uguali."""
    n = prefisso(a, b)
    return None if n == len(a) == len(b) else n


def _riga_i(r: list, i: int) -> str:
    return r[i] if i < len(r) else "(fine della partita)"


def _confronto(titolo_a: str, a: list, titolo_b: str, b: list, contesto: int, comuni: int = 2) -> list[str]:
    i = prima_differenza(a, b)
    if i is None:
        return [f"{titolo_a} e {titolo_b}: registri identici"]
    out = [f"prima riga diversa: la n. {i + 1} (indice {i})"]
    for k in range(max(0, i - comuni), i):
        out.append(f"   = {k:>3} {a[k]}")
    for titolo, r in ((titolo_a, a), (titolo_b, b)):
        out.append(f"  {titolo}:")
        for k in range(i, min(i + contesto + 1, max(len(r), i + 1))):
            out.append(f"   {k:>3} {_riga_i(r, k)}")
    return out


def _posto_riga(riga: str) -> str | None:
    p = riga.split(" ")
    return p[1] if len(p) > 1 and p[0].startswith("T") else None


def _confronto_vs(B: dict, vitt: list, sconf: list) -> list[str]:
    i = prima_differenza(vitt, sconf)
    out = _confronto("vittoria", vitt, "sconfitta", sconf, CONTESTO_VITTORIA)
    if i is not None:
        posto = _posto_riga(_riga_i(vitt, i))
        if posto == B["camp"]:
            out.insert(1, "e' la prima scelta diversa di Sett")
        else:
            out.insert(1, f"la prima riga diversa e' del posto {posto} (Evelynn o altro): non e' una scelta di Sett")
    return out


def _scrivi_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def serie(B: dict, x: int, processi: int, out_dir, print_=print) -> list[str]:
    """Tentativi j = 0..x-1 in parallelo (spawn, come `attacco.esegui`), in ordine di j. Ci si ferma alla prima
    vittoria di Sett nell'ordine di j: i j minori si completano tutti (partono in ordine), non se ne lanciano di
    nuovi. Scrive in `out_dir`: tentativi.jsonl, vittoria.json / sconfitta.json, riepilogo.txt (ultima riga
    `totale:`). -> le righe del riepilogo."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print_(f"  partita di Matteo: rifatta con le sue risposte...")
    matteo = partita_matteo(B)
    c = matteo["controllo"]
    print_(f"  partita di Matteo: vince {matteo['vincitore']} in {matteo['turni']} turni "
           f"({'coincide con la salvata' if c['identica'] else 'NON coincide con la salvata'}); {matteo['secondi']} s")
    risultati: dict[int, dict] = {}
    f = (out / "tentativi.jsonl").open("w", encoding="utf-8")
    scritti = 0
    primo = None            # il j minore con una vittoria di Sett fra i completati
    prossimo = 0
    inflight: dict = {}
    pool = ProcessPoolExecutor(max(1, processi), mp_context=multiprocessing.get_context("spawn")) if processi > 1 else None
    try:
        while True:
            while prossimo < x and primo is None and len(inflight) < max(1, processi):
                if pool:
                    inflight[pool.submit(_lavoro, (B, prossimo))] = prossimo
                else:
                    t = _lavoro((B, prossimo))
                    risultati[prossimo] = t
                    if t["vince_sett"] and primo is None:
                        primo = prossimo
                prossimo += 1
                if not pool:
                    break
            if pool and inflight:
                from concurrent.futures import FIRST_COMPLETED, wait
                fatti, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
                for fu in fatti:
                    j = inflight.pop(fu)
                    t = fu.result()
                    risultati[j] = t
                    if t["vince_sett"] and (primo is None or j < primo):
                        primo = j
            while scritti in risultati:          # una riga per tentativo, in ordine di j
                t = risultati[scritti]
                f.write(json.dumps(_senza_registro(t), ensure_ascii=False) + "\n")
                f.flush()
                scritti += 1
                if scritti == 1 or scritti % 10 == 0:
                    print_(f"  tentativi: {scritti} fatti, {time.time() - t0:.0f} s")
            if not inflight and (prossimo >= x or primo is not None):
                break
    finally:
        f.close()
        if pool:
            pool.shutdown()
    return _riepilogo(B, x, out, matteo, risultati, primo, time.time() - t0)


def _riepilogo(B: dict, x: int, out: Path, matteo: dict, ris: dict, primo: int | None, secondi: float) -> list[str]:
    camp, umano = B["camp"], B["umano"]
    tutti = [ris[j] for j in sorted(ris)]
    vitt_sett = [t for t in tutti if t["vince_sett"]]
    patte = [t for t in tutti if t["vincitore"] == "DRAW"]
    perse = [t for t in tutti if t["vincitore"] == umano]
    righe: list[str] = []
    P = righe.append
    P("== serie «stesso seme»")
    P(f"base: {B['nome']} (seme {B['seed']}); mazzi {Path(B['deck_a']).stem} (A) contro {Path(B['deck_b']).stem} (B); "
      f"Matteo = posto {umano} (Evelynn), Sett (campione) = posto {camp}; comincia {B['starter'].upper()}")
    P(f"campi: A {B['bf_a']}; B {B['bf_b']}; regole {B['regole']}; campione {B['iterazioni']} iterazioni fisse, "
      f"valutazione {(B['valutazione'] or ['storica'])[0]}, sonda di vittoria {'si' if B.get('probe', True) else 'no'}; "
      f"rete {'a pesi casuali' if B['casuali'] else B['ckpt']}")
    P(f"semi: partita {B['seed']}; Sett j = {seme_sett(B, 0)} + j; Evelynn automatica {seme_evelynn(B)} (fisso)")
    c = matteo["controllo"]
    P("")
    P("partita di Matteo (l'unico risultato contro Matteo e' la sua partita):")
    P(f"  salvata: vince {c['vincitore_salvato']} in {c['turni_salvati']} turni; rifatta con le sue risposte: "
      + (f"interrotta ({c['errore']})" if c["errore"] else
         f"vince {matteo['vincitore']} in {matteo['turni']} turni, punti {matteo['punti']}"))
    if c["identica"]:
        P(f"  controllo: IDENTICA (vincitore, turni e tutte le {c['righe']} righe del registro come il log salvato)")
    else:
        P(f"  controllo: NON COINCIDE con la salvata (vincitore {'si' if c['vincitore_uguale'] else 'no'}, turni "
          f"{'si' if c['turni_uguali'] else 'no'}; righe {c['righe']} contro {c['righe_salvate']} salvate, prefisso comune "
          f"{c['prefisso']}, uguali in posizione {c['righe_uguali']})"
          + ("; atteso: rete a pesi casuali, non e' il campione della partita" if B["casuali"] else
             "; NON atteso con il campione della partita: il rifacimento non e' fedele"))
    P("")
    P(f"tentativi (Evelynn automatica dal turno 1): {len(tutti)} fatti su {x} previsti")
    P(f"  Sett vince {len(vitt_sett)}, Evelynn vince {len(perse)}, patte {len(patte)}")
    # il seme della ricerca cambia le simulazioni, non sempre le mosse: quante partite diverse ha davvero esplorato
    distinte = len({tuple(t["registro"]) for t in tutti})
    diversa = next((t["j"] for t in tutti if tutti and t["registro"] != tutti[0]["registro"]), None)
    P(f"  partite distinte (registro diverso): {distinte} su {len(tutti)}; la prima diversa da j = 0: "
      + (f"j = {diversa}" if diversa is not None else "nessuna"))
    vitt = sconf = None
    if primo is not None:
        P(f"esito: vittoria nella simulazione al tentativo j* = {primo} (simulazioni servite: {primo + 1})")
        vitt = tentativo(B, primo, eventi=True)
        if vitt["registro"] != ris[primo]["registro"]:
            P("  ATTENZIONE: rifatta con gli eventi, la vittoria ha un registro diverso (non deterministica?)")
        sce = None
        if perse:
            sce = max(perse, key=lambda t: (prefisso(t["registro"], vitt["registro"]), -t["j"]))
            sconf = tentativo(B, sce["j"], eventi=True)
    else:
        P(f"esito: Sett senza vittorie nella simulazione dopo {x} tentativi")
        if perse or patte:
            # la sconfitta con piu' punti di Sett alla fine (a pari, j minore)
            sce = max(perse or patte, key=lambda t: (t["punti_sett"], -t["j"]))
            sconf = tentativo(B, sce["j"], eventi=True)
    for nome, t in (("vittoria", vitt), ("sconfitta", sconf)):
        if t is not None:
            _scrivi_json(out / f"{nome}.json", {
                "esito": {k: t[k] for k in ("j", "vincitore", "vince_sett", "turni", "punti", "secondi")},
                "semi": {"partita": B["seed"], "sett": t["seme_sett"], "evelynn": t["seme_evelynn"]},
                "registro": t["registro"], "eventi": t["eventi"]})
    if vitt is not None:
        P(f"  vittoria j = {vitt['j']}: {vitt['turni']} turni, punti Sett {vitt['punti_sett']} contro "
          f"{vitt['punti_evelynn']} di Evelynn (vittoria.json)")
    if sconf is not None:
        P(f"  sconfitta scelta j = {sconf['j']}: {sconf['turni']} turni, punti Sett {sconf['punti_sett']} contro "
          f"{sconf['punti_evelynn']} di Evelynn (sconfitta.json)"
          + (f"; prefisso comune con la vittoria {prefisso(sconf['registro'], vitt['registro'])} righe" if vitt else
             "; quella con piu' punti di Sett alla fine"))
    elif primo is not None:
        P("  nessuna sconfitta di Sett fra i tentativi fatti: niente da confrontare")
    if vitt is not None and sconf is not None:
        P("")
        P("confronto vittoria / sconfitta (la prima riga diversa e le righe che seguono):")
        righe += ["  " + r for r in _confronto_vs(B, vitt["registro"], sconf["registro"])]
    ref = vitt or sconf
    if ref is not None:
        P("")
        P(f"confronto con la partita di Matteo (registro di Matteo contro {'la vittoria' if vitt else 'la sconfitta scelta'}"
          f" j = {ref['j']}):")
        righe += ["  " + r for r in _confronto("Matteo", matteo["registro"], f"simulazione j={ref['j']}",
                                                  ref["registro"], CONTESTO_MATTEO)]
    P("")
    P(f"totale: {len(tutti)} tentativi; Sett vince {len(vitt_sett)}, Evelynn {len(perse)}, patte {len(patte)}; "
      + (f"vittoria nella simulazione al tentativo {primo} (servite {primo + 1})" if primo is not None
         else f"senza vittorie di Sett dopo {x} tentativi")
      + f"; partita di Matteo {'identica' if c['identica'] else 'non coincide'}; {secondi:.0f} s")
    (out / "riepilogo.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    _scrivi_json(out / "matteo.json", {"controllo": c, "registro": matteo["registro"]})
    return righe


def copia_base(path, *dest: Path) -> None:
    """Copia la partita base nelle cartelle indicate (la serie si rilegge da li')."""
    for d in dest:
        d.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, d / Path(path).name)
        except shutil.SameFileError:
            pass
