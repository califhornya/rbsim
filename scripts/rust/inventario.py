"""Inventario per il porting Rust: le carte reali di una o più liste (mazzo,
sideboard, leggenda, campione, campi, token e carte che creano), i loro
effetti (verbo, trigger, condizione, bersaglio, costo, parole chiave) e lo
stato in Rust di ciò che usano:
- verbi: un handler in rbsim-core/src/effects.rs (`run_effect`), un
  marcatore che il motore legge senza handler, o NON PORTATO (NotPorted);
- condizioni (`_check_condition`, lp_conditions.rs) e fonti di quantità
  (`_amount`, effects_core.rs `effect_amount`): portate o NON PORTATE;
- trigger e parole chiave: lette dal motore Rust (il nome compare nei
  sorgenti), oppure lette solo da Python, oppure da nessuno dei due (testo).
Le esecuzioni si contano su partite Python dei matchup indicati (self-play
PPO a pesi dal seme 1, PPO contro simple_trade, random contro PPO; i due
posti): le stesse che Rust gioca identiche. Le liste sono lettere di
riftbound/rs/mazzi.py (minuscola: con la sideboard nel mazzo).

  python scripts/rust/inventario.py                                  # EK
  python scripts/rust/inventario.py --liste R --matchup ER KR Er Kr \\
      --out docs/rust/INVENTARIO_RENGAR.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUST = ROOT / "rust/rbsim-core/src"
NAMES = {"E": "Evelynn", "K": "Kha'Zix", "R": "Rengar", "I": "Ivern", "S": "Sett"}


def deck_cards(path: Path) -> dict:
    d = json.loads(path.read_text())
    return {"leggenda": [d["legend"]], "campione": [d["champion"]],
            "campi": [b["name"] for b in d["battlefields"]],
            "mazzo": [c["name"] for c in d["cards"]], "sideboard": [c["name"] for c in d.get("sideboard", [])]}


def rust_strings() -> set:
    """The string literals of rbsim-core's code (comments left out)."""
    src = "\n".join(re.sub(r"//.*", "", p.read_text()) for p in sorted(RUST.glob("*.rs")))
    return set(re.findall(r'"([^"\\\n]*)"', src))


def rust_verbs() -> set:
    """The verbs of the match arms of rbsim-core's run_effect."""
    src = (RUST / "effects.rs").read_text()
    body = src[src.index("pub fn run_effect"):]
    body = body[:body.index("other =>")]
    arms = re.findall(r'^\s*((?:"[a-z_]+"\s*\|?\s*)+)=>', body, re.M)
    return {v for arm in arms for v in re.findall(r'"([a-z_]+)"', arm)}


def rust_conditions() -> set:
    """The condition types of check_condition's match arms."""
    src = (RUST / "lp_conditions.rs").read_text()
    body = src[src.index("pub fn check_condition"):]
    body = body[:body.index("other => not_ported!")]
    arms = re.findall(r'^\s*((?:"[a-z_]+"\s*\|?\s*)+)=>', body, re.M)
    return {v for arm in arms for v in re.findall(r'"([a-z_]+)"', arm)}


def rust_amount_sources() -> set:
    src = (RUST / "effects_core.rs").read_text()
    body = src[src.index("pub fn effect_amount"):]
    body = body[:body.index("not_ported!(\"_amount\"")]
    return set(re.findall(r'== "([a-z_]+)"', body))


def python_strings() -> set:
    """The string constants of the Python engine's code (docstrings left out)."""
    import ast
    out = set()
    for p in sorted((ROOT / "riftbound/core").glob("*.py")):
        tree = ast.parse(p.read_text())
        docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        # f-strings are messages (verbose prints), not rules
        docs |= {id(c) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for c in ast.walk(n)}
        out |= {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs}
    return out


def count_executions(n: int, matchups: list) -> dict:
    """Calls of the handlers, conditions and amount sources over n games of
    each kind per matchup (both seats: the matchup and its reverse)."""
    import torch
    from riftbound.ai.ppo import collect
    from riftbound.ai.ppo.model import PPONet
    from riftbound.core import effects as E
    from riftbound.core.loop import GameLoop
    from riftbound.rs.mazzi import decks
    calls = {"verbi": Counter(), "condizioni": Counter(), "quantità": Counter()}
    for verb, fn in list(E.REGISTRY.items()):
        def wrapped(ctx, spec, _fn=fn, _v=verb):
            calls["verbi"][_v] += 1
            return _fn(ctx, spec)
        E.REGISTRY[verb] = wrapped
    amount = E._amount

    def _amount(ctx, spec):
        if spec.get("amount_source"):
            calls["quantità"][str(spec.get("amount_source"))] += 1
        return amount(ctx, spec)
    E._amount = _amount
    check = GameLoop._check_condition

    def _check(self, cond, card, actor, opponent, extra):
        if cond:
            calls["condizioni"][str(cond.get("type"))] += 1
        return check(self, cond, card, actor, opponent, extra)
    GameLoop._check_condition = _check
    torch.manual_seed(1)
    torch.set_num_threads(1)
    net = PPONet().eval()
    mus = [m for mu in matchups for m in dict.fromkeys([mu, mu[::-1]])]
    for mu in mus:
        da, db = decks(mu)
        for seed in range(1, n + 1):
            collect.play(seed, {"A": net, "B": net}, {}, deck_a=da, deck_b=db)
            collect.play(seed, {"A": net, "B": None}, {}, opponent="simple_trade", deck_a=da, deck_b=db)
            collect.play(seed, {"A": None, "B": net}, {}, opponent="random", deck_a=da, deck_b=db)
    E._amount = amount
    GameLoop._check_condition = check
    return calls


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", default="EK", help="lettere delle liste da inventariare (EK, R, ...)")
    ap.add_argument("--matchup", nargs="+", default=None,
                    help="matchup delle partite per le esecuzioni (default: le liste fra loro, EK)")
    ap.add_argument("--partite", type=int, default=40, help="partite per tipo e matchup (self-play, contro simple_trade, contro random)")
    ap.add_argument("--out", default=str(ROOT / "docs/rust/INVENTARIO_EK.md"))
    args = ap.parse_args()
    from riftbound.core import effects as E
    from riftbound.registry.cards_registry import CARD_REGISTRY
    from riftbound.rs.mazzi import deck_path
    matchups = args.matchup or [args.liste]
    decks = {NAMES[c]: deck_cards(deck_path(c)) for c in args.liste}
    names: dict = {}
    for who, parts in decks.items():
        for part, cs in parts.items():
            for c in cs:
                names.setdefault(c, set()).add(f"{who} {part}")
    # Tokens and other cards the cards name in their effects (created, copied).
    for c in list(names):
        for es in CARD_REGISTRY[c].effects:
            for v in (es.params or {}).values():
                if isinstance(v, str) and v in CARD_REGISTRY and v not in names:
                    names[v] = {f"creata da {c}"}
    # Cards of the lists Rust already covers (arena_rs.COPERTI), other than the ones inventoried.
    from riftbound.rs.arena_rs import COPERTI
    covered = sorted(set("".join(COPERTI)) - set(args.liste.upper()), key="EKRIS".index)
    already = set()
    for c in covered:
        for cs in deck_cards(deck_path(c)).values():
            already |= set(cs)
    rv, rc, ra = rust_verbs(), rust_conditions(), rust_amount_sources()
    rs_str, py_str = rust_strings(), python_strings()
    calls = count_executions(args.partite, matchups)
    rows, verbs, conds, amounts, triggers, keywords = [], {}, {}, {}, {}, {}
    for c in sorted(names):
        spec = CARD_REGISTRY[c]
        for kw in spec.keywords:
            keywords.setdefault(kw.split()[0], set()).add(c)
        for es in spec.effects:
            cond = (es.condition or {}).get("type") if isinstance(es.condition, dict) else es.condition
            cost = ",".join(sorted(k for k, v in (es.cost or {}).items() if v)) if isinstance(es.cost, dict) else ""
            verbs.setdefault(es.effect, set()).add(c)
            triggers.setdefault(es.trigger, set()).add(c)
            if cond:
                conds.setdefault(cond, set()).add(c)
            for k in ("amount_source", "bonus_source"):
                if (es.params or {}).get(k):
                    amounts.setdefault(es.params[k], set()).add(c)
            rows.append((c, es.effect, es.trigger, es.timing or "", cond or "", es.target or "", cost))
    titolo = "+".join(NAMES[c] for c in args.liste)
    mus = ", ".join(matchups)
    lines = [f"# Inventario {titolo} (porting Rust)", "",
             f"Generato da `python scripts/rust/inventario.py --liste {args.liste} --matchup {' '.join(matchups)} "
             f"--partite {args.partite}`. Esecuzioni: chiamate Python su {3 * args.partite} partite per matchup e per "
             f"posto ({mus}, ciascuno anche rovesciato; minuscola = la lista con la sideboard nel mazzo, "
             "`riftbound/rs/mazzi.py`): self-play PPO a pesi dal seme 1, PPO contro simple_trade, random contro PPO. "
             "Sono le partite che il motore Rust gioca identiche.", "",
             "## Carte", "", "| Carta | Dove | Tipo | Parole chiave |" + (f" Già in {''.join(covered)} |" if already else ""),
             "|---|---|---|---|" + ("---|" if already else "")]
    for c in sorted(names):
        s = CARD_REGISTRY[c]
        lines.append(f"| {c} | {', '.join(sorted(names[c]))} | {getattr(s.category, 'name', s.category)} | "
                     f"{', '.join(s.keywords) or '—'} |" + ((" sì |" if c in already else " no |") if already else ""))
    lines += ["", "## Verbi", "",
              "Stato in Rust: **handler** (rbsim-core `run_effect`), **marcatore** (nessun handler in Python: "
              "il motore lo legge dove serve, porting con la funzione che lo legge), **NON PORTATO** "
              "(handler Python senza traduzione: in Rust darebbe `NotPorted`).", "",
              "| Verbo | Stato Rust | Esecuzioni | Carte |", "|---|---|---|---|"]
    missing = []
    for v in sorted(verbs):
        if v in rv:
            state = "handler"
        elif v not in E.REGISTRY:
            state = "marcatore"
        else:
            state = "NON PORTATO"
            missing.append(v)
        lines.append(f"| {v} | {state} | {calls['verbi'].get(v, 0)} | {', '.join(sorted(verbs[v]))} |")
    lines += ["", "## Condizioni e quantità", "",
              "Condizioni (`_check_condition`, Rust `check_condition`) e fonti di quantità (`_amount`, Rust "
              "`effect_amount`). Esecuzioni: valutazioni in Python.", "",
              "| Tipo | Che cos'è | Stato Rust | Esecuzioni | Carte |", "|---|---|---|---|---|"]
    for k in sorted(conds):
        st = "portata" if k in rc else "NON PORTATA"
        missing += [] if k in rc else [f"condizione {k}"]
        lines.append(f"| {k} | condizione | {st} | {calls['condizioni'].get(k, 0)} | {', '.join(sorted(conds[k]))} |")
    for k in sorted(amounts):
        st = "portata" if k in ra else "NON PORTATA"
        missing += [] if k in ra else [f"quantità {k}"]
        lines.append(f"| {k} | quantità | {st} | {calls['quantità'].get(k, 0)} | {', '.join(sorted(amounts[k]))} |")

    # Keywords both engines read from the rules text, not by name (EQUIP: §744, `_equip_cost`).
    from_text = {"EQUIP": "Rust (dal testo: `parse_equip_cost`)"}

    def read(name: str) -> str:
        if name in from_text:
            return from_text[name]
        if name in rs_str:
            return "Rust"
        return "solo Python" if name in py_str else "nessuno (testo)"
    lines += ["", "## Trigger e parole chiave", "",
              "Letta da: **Rust** (il nome compare nei sorgenti di rbsim-core), **solo Python** (da portare), "
              "**nessuno** (un'etichetta senza regole nel motore: LEGION si legge dalla condizione, DEATHKNELL "
              "dal trigger `on_death`).", "",
              "| Nome | Che cos'è | Letta da | Carte |", "|---|---|---|---|"]
    for t in sorted(triggers):
        r = read(t)
        missing += [f"trigger {t}"] if r == "solo Python" else []
        lines.append(f"| {t} | trigger | {r} | {', '.join(sorted(triggers[t]))} |")
    for k in sorted(keywords):
        r = read(k)
        missing += [f"parola chiave {k}"] if r == "solo Python" else []
        lines.append(f"| {k} | parola chiave | {r} | {', '.join(sorted(keywords[k]))} |")
    lines += ["", "## Effetti per carta", "",
              "| Carta | Verbo | Trigger | Tempo | Condizione | Bersaglio | Costo |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {' | '.join(str(x) for x in r)} |" for r in rows]
    never = [v for v in sorted(verbs) if v in E.REGISTRY and not calls["verbi"].get(v)]
    never += [f"condizione {k}" for k in sorted(conds) if not calls["condizioni"].get(k)]
    never += [f"quantità {k}" for k in sorted(amounts) if not calls["quantità"].get(k)]
    lines += ["", "## Sintesi", "",
              f"- Carte: {len(names)}; effetti: {len(rows)}; verbi: {len(verbs)} "
              f"(handler Rust {sum(1 for v in verbs if v in rv)}, marcatori {sum(1 for v in verbs if v not in E.REGISTRY)}); "
              f"condizioni {len(conds)}, quantità {len(amounts)}, trigger {len(triggers)}, parole chiave {len(keywords)}.",
              f"- Non portato: {', '.join(missing) or 'niente'}.",
              f"- Mai eseguiti nel campione: {', '.join(never) or 'nessuno'}."]
    Path(args.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-3:]))


if __name__ == "__main__":
    main()
