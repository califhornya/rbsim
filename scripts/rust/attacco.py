"""Attacco: il campione contro linee di attacco proposte, in una posizione di turno (riftbound/rs/attacco.py).

  attacco.py posizioni --pagina F.json [F2.json ...] [--autonoma ES:3:B ...] [--out F.json]
  attacco.py proposte  --pagina F.json --k 10 [--senza-deduplica] [--confronta-con proposte.json]
  attacco.py confronta --pagina F.json --k 10 --out DIR [--riferimento campione|"Play X ; Move Y base→BF1 ; Pass"]
        [--modo ignote|fisse] [--scelta 2000:16] [--verifica 4000:100] [--senza-deduplica] [--processi 4]
  attacco.py serie     --posizioni F.json --out DIR [--max 12] (come `confronta`, per ogni posizione)
  attacco.py rivedi    --serie DIR --out DIR [--quota 4] [--mirata 10] [--processi 4] [--ckpt F | --casuali]
  attacco.py riproduci-t9 --dati docs/bot/esperimenti/t9_attacco/dati [--rapida] [--processi 4]
  attacco.py sonda     --pagina F | --autonoma MU:S:P --k K --out DIR   (sonda A a un'ondata, riftbound/rs/sonda.py)
  attacco.py congela   --serie DIR --out DIR
  attacco.py fuori     --posizioni JSON --out DIR [--per-matchup ES=24,EK=24,ER=6] [--escludi JSON]
  attacco.py t9-foglia --out DIR

Partita: `--pagina FILE` (una partita della pagina contro il campione) oppure `--autonoma MU:SEME[:POSTO]` (campione
contro campione; POSTO = il posto studiato, A di default); `--ckpt` (default runs/sett/ekris_s12/ckpt_040000.pt) o
`--casuali` (rete a pesi casuali, per provare dove il checkpoint non c'è). Per le autonome anche `--regole`,
`--valutazione` (storica|rimonta|...) e `--iterazioni` (default: quelle della pagina, 138).

`posizioni`: per ogni turno del campione la prima decisione di turno in cui l'avversario controlla un campo con unità e il
menu ha uno spostamento dalla base verso di esso; `punto_libero` se c'è anche un campo libero raggiungibile. JSON.
`proposte`: solo la generazione (la griglia di Astra, per campo dell'avversario); con `--confronta-con` il confronto
con le proposte di Astra. `confronta`: proposte, selezione sui mondi di scelta, verifica sui mondi tenuti da parte
(riferimento contro la migliore, differenze appaiate +-1,96 errori standard), vista del campione ed esito.
`serie`: `confronta` per ogni posizione (con --max, al più N: metà con punto libero se possibile) e `riepilogo.txt`.
`rivedi`: su una serie già fatta, verifiche in più: la linea con la valutazione più alta a fine turno e dopo l'avversario
nei mondi di scelta (sonde), la proposta con più punti se la selezione ha scelto il riferimento; verificate sugli stessi
mondi di verifica (controllo prima del riferimento su 2 mondi); per gli attacchi verificati migliori, la ricerca del
campione con finestre e quota (4 per tutte le mosse, 10 sulla prima mossa dell'attacco). `rivedi.txt` con la riga `totale:`.
`riproduci-t9`: la prova di Astra sul T9 (partita 013325, k=10) confrontata mondo per mondo con i suoi dati.
`sonda`: la sonda A a un'ondata su una posizione (+ verifica a partita intera su mondi nuovi); `congela`: la sonda sulle
posizioni di una serie, con controllo di identità; `fuori`: la sonda fuori campione, riepilogo per gruppo e matchup;
`t9-foglia`: il caso diagnostico del T9 (linee guidate, foglia dopo l'avversario). Vedi riftbound/rs/sonda.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402
from riftbound.rs import sonda as S  # noqa: E402


def intervallo(testo: str) -> tuple[int, int]:
    i, n = testo.split(":")
    return int(i), int(n)


def partite(a) -> list[dict]:
    out = []
    for f in a.pagina or []:
        out.append({"tipo": "pagina", "file": f, "ckpt": a.ckpt, "casuali": a.casuali})
    for s in a.autonoma or []:
        v = s.split(":")
        mu, seed, posto = v[0], int(v[1]), (v[2].upper() if len(v) > 2 else "A")
        extra = {}
        if a.regole:
            extra["regole"] = a.regole
        if a.valutazione:
            extra["valutazione"] = D._valutazione_registrata(a.valutazione)
        extra["iterazioni"] = a.iterazioni or D.ITERAZIONI_CAMPIONE
        it = extra.pop("iterazioni")
        out.append(D.autonoma(mu, seed, a.ckpt, a.casuali, it, posto, **extra))
    return out


def una_partita(a) -> dict:
    p = partite(a)
    if len(p) != 1:
        raise SystemExit("serve esattamente una partita (--pagina FILE oppure --autonoma MU:SEME[:POSTO])")
    return p[0]


def riferimento(testo: str):
    if testo.strip().casefold() == "campione":
        return "campione"
    v = [x.strip() for x in testo.split(" ; ") if x.strip()]
    if not v:
        raise SystemExit("--riferimento vuoto")
    return v


def cmd_posizioni(a) -> int:
    out = []
    for p in partite(a):
        elenco = A.posizioni(p)
        for x in elenco:
            x["nome"] = A.nome_partita(p)
        print(f"{A.nome_partita(p)}: {len(elenco)} posizioni (k {[x['k'] for x in elenco]}; "
              f"con punto libero {sum(x['punto_libero'] for x in elenco)})", file=sys.stderr)
        out.extend(elenco)
    testo = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(testo, encoding="utf-8")
    else:
        print(testo)
    return 0


def cmd_proposte(a) -> int:
    pos = A.posizione(una_partita(a), a.k)
    proposte = A.genera(pos, not a.senza_deduplica)
    for p in proposte:
        q = p["proposal"]
        print(f"{p['nome']} campo {p['field']} gear={q['gear_target']} onde={q['waves']} magia={q['spell_wave']} "
              f"ambush={q['ambush_index']} -> onde fatte {p['waves']}, ambush {int(p['ambush'])}, magia {int(p['spell'])}"
              + (f" [uguale a {p['uguale_a']}]" if p["uguale_a"] else "") + f" | {len(p['events'])} eventi")
    print(f"{len(proposte)} proposte, {sum(p['uguale_a'] is None for p in proposte)} distinte")
    if a.confronta_con:
        dif = A.diff_proposte(json.loads(json.dumps(proposte)), json.loads(Path(a.confronta_con).read_text()))
        print("IDENTICHE a quelle di Astra" if not dif else "DIFFERENZE:\n" + "\n".join(dif[:20]))
    return 0


def cmd_confronta(a) -> int:
    e = A.confronta(una_partita(a), a.k, Path(a.out), riferimento(a.riferimento), a.modo, a.scelta, a.verifica,
                    not a.senza_deduplica, a.processi)
    print("\n".join(A.testo_esito(e)))
    return 0


def cmd_serie(a) -> int:
    elenco = json.loads(Path(a.posizioni).read_text(encoding="utf-8"))
    for x in elenco:
        if a.ckpt:
            x["partita"]["ckpt"] = a.ckpt
        if a.casuali:
            x["partita"]["casuali"] = True
    righe = A.serie(elenco, Path(a.out), a.max, riferimento(a.riferimento), a.modo, a.scelta, a.verifica,
                    not a.senza_deduplica, a.processi)
    print("\n".join(righe))
    return 0


def cmd_rivedi(a) -> int:
    righe = A.rivedi(Path(a.serie), Path(a.out), a.processi, a.quota, a.mirata, print, a.ckpt, a.casuali)
    print(righe[-1])
    return 0


def cmd_t9(a) -> int:
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="riproduci_t9_"))
    dif = A.riproduci_t9(Path(a.dati), out, a.rapida, a.ckpt, a.casuali, a.processi, print, a.replay or A.T9_REPLAY)
    print("IDENTICO" if not dif else f"DIFFERENTE ({len(dif)} differenze); prime:\n" + "\n".join(dif[:20]))
    print(f"file in {out}")
    return 0 if not dif else 1


def cmd_sonda(a) -> int:
    e = S.valuta(una_partita(a), a.k, Path(a.out), a.processi, a.verifica, print, a.mondi)
    print("\n".join(S.testo_esito(e)))
    return 0


def cmd_congela(a) -> int:
    righe = S.congela(Path(a.serie), Path(a.out), a.processi, print, a.ckpt, a.casuali, a.mondi, a.solo)
    print(righe[-1])
    return 0


def per_matchup(testo: str | None) -> dict | None:
    if not testo:
        return None
    return {v.split("=")[0]: int(v.split("=")[1]) for v in testo.split(",") if v.strip()}


def cmd_fuori(a) -> int:
    righe = S.fuori(Path(a.posizioni), Path(a.out), a.processi, per_matchup(a.per_matchup),
                    Path(a.escludi) if a.escludi else None, print, a.ckpt, a.casuali, a.verifica, a.mondi)
    print("\n".join(r for r in righe if r.startswith(("gruppo", "totale", "differenza media"))))
    return 0


def cmd_t9_foglia(a) -> int:
    righe = S.diagnosi_t9(Path(a.out), a.processi, a.ckpt, a.casuali, print, a.mondi_t9)
    print(righe[-1])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def comune(p, partita=True):
        if partita:
            p.add_argument("--pagina", nargs="+", help="partita della pagina (file json)")
            p.add_argument("--autonoma", nargs="+", metavar="MU:SEME[:POSTO]", help="partita campione contro campione")
            p.add_argument("--regole", help="profilo delle regole (solo autonome)")
            p.add_argument("--valutazione", help="valutazione del campione (solo autonome), es. rimonta")
            p.add_argument("--iterazioni", type=int, help="iterazioni del campione (solo autonome)")
        p.add_argument("--ckpt", help="checkpoint del campione")
        p.add_argument("--casuali", action="store_true", help="rete a pesi casuali")
        p.add_argument("--processi", type=int, default=1)

    def confr(p):
        p.add_argument("--riferimento", default="campione", help='"campione" o "etichetta ; etichetta ; ..."')
        p.add_argument("--modo", choices=["ignote", "fisse"], default="ignote")
        p.add_argument("--scelta", type=intervallo, default=A.SCELTA, help="INIZIO:N mondi di scelta (2000:16)")
        p.add_argument("--verifica", type=intervallo, default=A.VERIFICA, help="INIZIO:N mondi di verifica (4000:100)")
        p.add_argument("--senza-deduplica", action="store_true")
        p.add_argument("--out", required=True)

    p = sub.add_parser("posizioni", help="le posizioni candidate")
    comune(p)
    p.add_argument("--out", help="file json (se no, stdout)")
    p.set_defaults(f=cmd_posizioni)
    p = sub.add_parser("proposte", help="solo la generazione")
    comune(p)
    p.add_argument("--k", type=int, required=True)
    p.add_argument("--senza-deduplica", action="store_true")
    p.add_argument("--confronta-con", help="proposte.json di Astra")
    p.set_defaults(f=cmd_proposte)
    p = sub.add_parser("confronta", help="proposte, selezione, verifica, esito")
    comune(p)
    p.add_argument("--k", type=int, required=True)
    confr(p)
    p.set_defaults(f=cmd_confronta)
    p = sub.add_parser("serie", help="confronta per ogni posizione di un elenco")
    comune(p, partita=False)
    p.add_argument("--posizioni", required=True, help="json di `posizioni`")
    p.add_argument("--max", type=int, help="al più N posizioni (metà con punto libero se possibile)")
    confr(p)
    p.set_defaults(f=cmd_serie)
    p = sub.add_parser("rivedi", help="verifiche in più su una serie già fatta")
    comune(p, partita=False)
    p.add_argument("--serie", required=True, help="cartella di una serie (con le cartelle NN_..._kK)")
    p.add_argument("--out", required=True)
    p.add_argument("--quota", type=int, default=4, help="quota per tutte le mosse (4)")
    p.add_argument("--mirata", type=int, default=10, help="quota sulla prima mossa dell'attacco (10)")
    p.set_defaults(f=cmd_rivedi)
    p = sub.add_parser("riproduci-t9", help="la prova di Astra sul T9, confrontata coi suoi dati")
    comune(p, partita=False)
    p.add_argument("--dati", required=True, help="docs/bot/esperimenti/t9_attacco/dati")
    p.add_argument("--rapida", action="store_true", help="solo proposte e i primi 2 mondi di scelta")
    p.add_argument("--out", help="cartella dei file prodotti (default: temporanea)")
    p.add_argument("--replay", help="partita del T9 (default: la 013325 in docs/bot/partite/coach)")
    p.set_defaults(f=cmd_t9)

    def sond(p):
        p.add_argument("--out", required=True)
        p.add_argument("--verifica", type=intervallo, default=S.VERIFICA, help="INIZIO:N mondi di verifica (6000:100)")
        p.add_argument("--mondi", type=intervallo, default=S.MONDI, help="INIZIO:N mondi della sonda (2000:16)")

    p = sub.add_parser("sonda", help="la sonda A a un'ondata su una posizione")
    comune(p)
    p.add_argument("--k", type=int, required=True)
    sond(p)
    p.set_defaults(f=cmd_sonda)
    p = sub.add_parser("congela", help="la sonda sulle posizioni di una serie, con controllo di identità")
    comune(p, partita=False)
    p.add_argument("--serie", required=True, help="cartella di una serie (con le cartelle NN_..._kK)")
    p.add_argument("--out", required=True)
    p.add_argument("--mondi", type=intervallo, default=S.MONDI, help="INIZIO:N mondi della sonda (2000:16)")
    p.add_argument("--solo", nargs="+", help="solo le cartelle con questo prefisso (prove)")
    p.set_defaults(f=cmd_congela)
    p = sub.add_parser("fuori", help="la sonda fuori campione, riepilogo per gruppo e matchup")
    comune(p, partita=False)
    p.add_argument("--posizioni", required=True, help="json di `posizioni`")
    p.add_argument("--per-matchup", help="al più N posizioni per matchup, es. ES=24,EK=24,ER=6")
    p.add_argument("--escludi", help="json delle posizioni di sviluppo (default attacco_20261126/posizioni.json)")
    sond(p)
    p.set_defaults(f=cmd_fuori)
    p = sub.add_parser("t9-foglia", help="il caso diagnostico del T9 (linee guidate, foglia)")
    comune(p, partita=False)
    p.add_argument("--out", required=True)
    p.add_argument("--mondi-t9", type=int, default=100, help="mondi per modo (100)")
    p.set_defaults(f=cmd_t9_foglia)
    a = ap.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
