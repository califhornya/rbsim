#!/usr/bin/env python
"""Le giocate dei bot (23/11, domande di Astra sulla partita 35.010 di
runs/sett/ekris_s12: Evelynn-Sett, seed 121035009, pesi ckpt_035008).

  partita   rigioca una partita del training (seed, chi comincia, matchup, la
            rete della partita, campionata come nel training) e scrive ogni
            decisione: finestra, carta, tavolo, le opzioni con le probabilità
            della rete della partita e di ogni rete --confronta, la mossa
            estratta (* se la sua probabilità era sotto 0,10).
  bot       la stessa partita fino alla decisione --decisione (un menu:
            principale, reazione o showdown); lì decide il bot completo (bot a
            mano + prior --prior, 0,4 s per mossa, come nelle arene), --volte
            volte con generatori diversi: la mossa e le scelte dichiarate
            (campo, bersagli). Con --forza "etichetta" la mossa è quella e il
            bot sceglie solo campo e bersagli.
  campione  partite nuove, seed dichiarati (--seed0 + 1.000 x indice del
            matchup + k; chi comincia alterna): la rete --ckpt campionata come
            nel training (--argmax: la mossa più probabile), il bot completo
            (--prior) o il bot a mano (né --ckpt né --prior). Per ogni
            decisione della rete: la probabilità della mossa giocata e la più
            alta. Rilevatori: ogni Switcheroo risolto nella partita vera (chi
            scambia con chi, dove, se lo showdown era altrove, se non ha
            scambiato nulla), le unità giocate in base quando la stessa carta
            era offerta su un campo. --esempi N esempi completi per tipo.

Esempi (sul Mac, a arena finita: le arene contano il tempo, 0,4 s per mossa):

  R=runs/sett/ekris_s12
  python scripts/diag/giocate.py partita --seed 121035009 --starter a --matchup ES \\
      --ckpt $R/ckpt_035008.pt --confronta $R/ckpt_040000.pt --out runs/giocate
  python scripts/diag/giocate.py bot --seed 121035009 --starter a --matchup ES \\
      --ckpt $R/ckpt_035008.pt --decisione N --prior $R/ckpt_040000.pt --volte 10 --out runs/giocate
  python scripts/diag/giocate.py campione --ckpt $R/ckpt_040000.pt --partite 20 --out runs/giocate/rete
  python scripts/diag/giocate.py campione --partite 4 --out runs/giocate/bot_a_mano
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

ORDER = ("EK", "ER", "KR", "EI", "KI", "RI", "ES", "KS", "RS", "IS")
SEED0 = 800_000          # campione: disgiunti da training (121M...), arene, mulligan_mano (700k)
LOW = 0.10
_NETS: dict = {}


class _Fine(BaseException):
    """Fine della sonda: la partita si ferma qui."""


# ----------------------------------------------------------------- il tavolo

def _pts(gs, s):
    return getattr(gs, f"points_{s}", "?")


def _unit(u) -> str:
    out = f"{u.card.name} {u.might}M"
    if getattr(u, "damage", 0):
        out += f" ({u.damage} danni)"
    if not u.ready:
        out += " esausta"
    return out


def _bf_name(gs, bf) -> str:
    i = next((k for k, b in enumerate(gs.battlefields) if b is bf), None)
    name = getattr(getattr(bf, "card", None), "name", None)
    return f"{name or 'campo'} [BF{i}]"


def tavolo(gs, side: str) -> str:
    """Quello che serve per giudicare una decisione di `side`: punti, risorse,
    mani (la sua), basi, campi (con lo showdown), catena."""
    opp = gs.other(side)
    lines = [f"turno {gs.turn}, di turno {gs.active}; punti {side} {_pts(gs, side)}, {opp} {_pts(gs, opp)}"]
    for s in (side, opp):
        p = gs.get_player(s)
        legend = getattr(getattr(gs, f"legend_{s}", None), "name", "?")
        runes = sum(len(v) for v in (p.rune_pool or {}).values())
        power = {getattr(d, "name", d): n for d, n in (p.power_pool or {}).items() if n}
        lines.append(f"{s} ({legend}{', chi decide' if s == side else ''}): energia {getattr(p, 'energy', '?')}, "
                     f"potere {power or '-'}, rune in gioco {runes}, mano {len(p.hand)}, mazzo {len(p.deck.cards)}, "
                     f"cimitero {len(p.trash)}")
        lines.append(f"   base: {', '.join(_unit(u) for u in p.base_units) or '-'}")
    me = gs.get_player(side)
    lines.append(f"mano di {side}: {', '.join(c.name for c in me.hand) or '-'}")
    for i, bf in enumerate(gs.battlefields):
        sd = " <- SHOWDOWN" if gs.showdown_active and gs.showdown_bf_idx == i else ""
        ctrl = bf.controller()
        fds = ", ".join(f"coperta di {fd.owner}" + (f" ({fd.card.name})" if fd.owner == side else "")
                        for fd in bf.facedowns)
        lines.append(f"{_bf_name(gs, bf)}{sd}: controllo {ctrl or '-'}; {side}: "
                     f"{', '.join(_unit(u) for u in bf._units_for(side)) or '-'}; {opp}: "
                     f"{', '.join(_unit(u) for u in bf._units_for(opp)) or '-'}" + (f"; {fds}" if fds else ""))
    if gs.chain:
        lines.append("catena: " + " <- ".join(f"{it.card.name} ({it.player})" for it in gs.chain))
    return "\n".join(lines)


def etichetta(loop, side: str, o) -> str:
    """Un'opzione di GameLoop.choose in parole."""
    from riftbound.core.battlefield import Battlefield, FacedownCard
    from riftbound.core.combat import UnitInPlay
    from riftbound.core.loop import NO_MORE
    from riftbound.core.state import ChainItem
    gs = loop.gs
    if isinstance(o, tuple) and o:
        o = o[-1]
    if o is NO_MORE:
        return "basta così"
    if o is None:
        return "niente"
    if isinstance(o, UnitInPlay):
        w = loop._locate_unit(o)
        where = "?" if w is None else ("base" if w[1] is None else _bf_name(gs, w[1]))
        whose = "?" if w is None else ("mia" if w[0] == side else "sua")
        return f"{_unit(o)}, {whose}, {where}"
    if isinstance(o, Battlefield):
        sd = " (showdown qui)" if gs.showdown_active and gs.battlefields[gs.showdown_bf_idx] is o else ""
        return (f"{_bf_name(gs, o)}{sd}: mie [{', '.join(_unit(u) for u in o._units_for(side))}] "
                f"sue [{', '.join(_unit(u) for u in o._units_for(gs.other(side)))}]")
    if isinstance(o, ChainItem):
        return f"in catena: {o.card.name} ({o.player})"
    if isinstance(o, FacedownCard):
        return "coperta" + (f" ({o.card.name})" if o.owner == side else "")
    if hasattr(o, "name") and hasattr(o, "category"):
        return o.name
    return str(getattr(o, "name", o))


# ------------------------------------------------- Switcheroo, nella partita vera

REAL: list = [None]
SWITCH: list = []


def _install_spy() -> None:
    from riftbound.core import effects
    orig = effects.REGISTRY["swap_might"]
    if getattr(orig, "_spia", False):
        return

    def spy(ctx, spec):
        loop = ctx.loop
        if loop is not REAL[0] or getattr(loop, "_dry_run", False) or getattr(loop, "_lookahead", False):
            return orig(ctx, spec)
        gs, side = loop.gs, ctx.actor_side
        units = [(u, s, i) for i, bf in enumerate(gs.battlefields) for s in ("A", "B") for u in bf._units_for(s)]
        before = {id(u): u.might for u, _, _ in units}
        sd = gs.showdown_bf_idx if gs.showdown_active else None
        hidden = getattr(ctx.card, "_hidden_bf", None)
        board = tavolo(gs, side)
        orig(ctx, spec)
        changed = [(u.card.name, "mia" if s == side else "sua", i, before[id(u)], u.might)
                   for u, s, i in units if u.might != before[id(u)]]
        bfs = {c[2] for c in changed}
        ev = {"turn": gs.turn, "side": side, "showdown_bf": sd, "da_coperto_bf": hidden, "scambio": changed,
              "tavolo_prima": board}
        if not changed:
            ev["tipo"] = "nessuno scambio"
        elif len({c[1] for c in changed}) == 1:
            ev["tipo"] = "tra unità " + ("mie" if changed[0][1] == "mia" else "sue")
        else:
            ev["tipo"] = "mia contro sua"
        ev["fuori_dallo_showdown"] = sd is not None and bool(changed) and sd not in bfs
        ev["altro_campo_da_coperto"] = hidden is not None and bool(changed) and hidden not in bfs
        if sd is not None:
            mine = [c for c in changed if c[2] == sd and c[1] == "mia"]
            ev["mio_guadagno_allo_showdown"] = sum(c[4] - c[3] for c in mine)
        SWITCH.append(ev)
    spy._spia = True
    effects.REGISTRY["swap_might"] = spy


# ------------------------------------------------------------- the probe agent

def _net(path):
    if path not in _NETS:
        import torch
        from riftbound.ai.ppo.model import load
        torch.set_num_threads(1)
        _NETS[path] = load(path).eval()
    return _NETS[path]


def _sonda_class():
    import torch
    from riftbound.ai.encoding import card_id, encode_observation
    from riftbound.ai.ppo import features as F
    from riftbound.ai.ppo.agent import PPOAgent, _arrays
    from riftbound.core.decisions import DecisionPoint, Observation
    from riftbound.core.legality import legal_actions

    class Sonda(PPOAgent):
        """Un PPOAgent che scrive ogni decisione (con le probabilità di altre
        reti sugli stessi ingressi) e, alla decisione `handoff`, cede al bot."""

        def __init__(self, player, net, others: dict, log: list, game: dict, **kw):
            super().__init__(player, net, **kw)
            self.others, self.log, self.game = others, log, game
            self._labels = None

        def _probs(self, net, x, q, src, c, otype, ocards, ofeats):
            with torch.no_grad():
                logits, _ = net(torch.as_tensor(x[None]), torch.tensor([q]), torch.tensor([src]),
                                torch.as_tensor(c[None]), torch.as_tensor(otype[None]),
                                torch.as_tensor(ocards[None]), torch.as_tensor(ofeats[None]),
                                torch.ones(1, len(otype), dtype=torch.bool))
                return [round(float(p), 4) for p in torch.softmax(logits[0], dim=0)]

        def _ask(self, question, descs, source=None, ctx=None):
            if len(descs) < 2 or self.game.get("stop"):
                if self.game.get("stop"):
                    raise _Fine()
                return super()._ask(question, descs, source, ctx)
            side = self.player.name
            gs = self.loop.gs
            x = encode_observation(Observation.from_state(gs, side))
            q = F.question_of(question)
            src = card_id(getattr(source, "name", None)) if source is not None else 0
            c = ctx if ctx is not None else F.context(len(descs))
            arrs = _arrays(descs)
            p = self._probs(self.net, x, q, src, c, *arrs)
            others = {k: self._probs(n, x, q, src, c, *arrs) for k, n in self.others.items()}
            board = tavolo(gs, side) if self.game.get("tavolo", True) else None
            i = super()._ask(question, descs, source, ctx)
            labels = self._labels or [f"opzione {k}" for k in range(len(descs))]
            self._labels = None
            self.log.append({"n": len(self.log) + 1, "turn": gs.turn, "seat": side,
                             "legend": getattr(getattr(gs, f"legend_{side}", None), "name", "?"),
                             "finestra": question, "carta": getattr(source, "name", None),
                             "opzioni": labels, "p": p, "altre": others, "scelta": i,
                             "p_scelta": p[i], "p_max": max(p), "tavolo": board})
            return i

        def _menu(self, point, question):
            side = self.player.name
            legal = legal_actions(self.loop, point, side)
            if len(legal) >= 2:
                self._labels = [ga.label for ga in legal]
            return super()._menu(point, question)

        def decide_mulligan(self):
            menu = F.mulligan_menu(len(self.player.hand))
            self._labels = ["tiene tutto" if not s else "rimanda " + " + ".join(self.player.hand[i].name for i in s)
                            for s in menu]
            return super().decide_mulligan()

        def inner(self, loop, kind, options, default, source):
            if self.game.get("stop"):
                raise _Fine()
            if len(options) >= 2:
                self._labels = [etichetta(loop, self.player.name, o) for o in options]
            return super().inner(loop, kind, options, default, source)

        # -- the hand-off to the full bot ------------------------------------
        def _maybe_handoff(self, point, decide):
            if self.game.get("stop"):
                raise _Fine()
            h = self.game.get("handoff")
            if h is None or len(self.log) + 1 != h:
                return None
            legal = legal_actions(self.loop, point, self.player.name)
            if len(legal) < 2:
                return None
            return self.game["bot_decides"](self, legal, decide)

        def decide_action(self, opponent, cards_played=0):
            got = self._maybe_handoff(DecisionPoint.TURN_ACTION,
                                      lambda b: b.decide_action(opponent, cards_played))
            return got if got is not None else super().decide_action(opponent, cards_played)

        def decide_reaction(self, opponent, chain):
            got = self._maybe_handoff(DecisionPoint.REACTION, lambda b: b.decide_reaction(opponent, chain))
            return got if got is not None else super().decide_reaction(opponent, chain)

        def decide_showdown_action(self, opponent, bf_idx):
            got = self._maybe_handoff(DecisionPoint.SHOWDOWN_ACTION,
                                      lambda b: b.decide_showdown_action(opponent, bf_idx))
            return got if got is not None else super().decide_showdown_action(opponent, bf_idx)

    return Sonda


def _build(seed, starter, mu):
    from riftbound.ai.ppo.collect import DECK_OF, MAX_TURNS
    from riftbound.core.game_factory import build_game
    return build_game(game_seed=seed, deck_a_path=DECK_OF[mu[0]], deck_b_path=DECK_OF[mu[1]], ai_a=None, ai_b=None,
                      max_turns=MAX_TURNS, first_player=starter)


def replay(seed, starter, mu, ckpt, confronta=(), sample=True, handoff=None, bot_decides=None, journal=False,
           tavolo_sempre=True):
    """Una partita di due Sonda con la rete `ckpt` (come collect.play):
    -> (log, game, gs)."""
    from riftbound.ai.ppo.agent import PPOChooser
    from riftbound.core.loop import GameLoop
    _install_spy()
    Sonda = _sonda_class()
    gs = _build(seed, starter, mu)
    log: list = []
    game = {"handoff": handoff, "bot_decides": bot_decides, "tavolo": tavolo_sempre}
    others = {Path(c).stem: _net(c) for c in confronta}
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        p.agent = Sonda(p, _net(ckpt), others, log, game, sample=sample, seed=seed * 2 + (seat == "B"))
    loop = GameLoop(gs)
    loop.chooser = PPOChooser(gs)
    if journal:
        loop.journal = []
    REAL[0] = loop
    SWITCH.clear()
    game["loop"] = loop
    try:
        res = loop.start()
        game["winner"] = res.winner
    except _Fine:
        game["winner"] = None
    game["switch"] = list(SWITCH)
    return log, game, gs


def _riga(r, nets=()) -> str:
    out = [f"\n#{r['n']} turno {r['turn']}, {r['seat']} ({r['legend']}), finestra {r['finestra']}"
           + (f", carta {r['carta']}" if r.get("carta") else "")]
    if r.get("tavolo"):
        out += ["   " + l for l in r["tavolo"].splitlines()]
    if r.get("bot"):
        out += [f" {'>' if k == r['scelta'] else ' '} {lab}" for k, lab in enumerate(r["opzioni"])]
        return "\n".join(out)
    head = "   p rete" + "".join(f"  p {k}" for k in r.get("altre", {}))
    out.append(head)
    for k, lab in enumerate(r["opzioni"]):
        mark = ("*" if r["p"][k] < LOW else ">") if k == r["scelta"] else " "
        alt = "".join(f"  {r['altre'][n][k]:7.4f}" for n in r.get("altre", {}))
        out.append(f" {mark} {r['p'][k]:7.4f}{alt}  {lab}")
    return "\n".join(out)


# ------------------------------------------------------------------ commands

def cmd_partita(args) -> None:
    log, game, gs = replay(args.seed, args.starter, args.matchup, args.ckpt, args.confronta)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"partita_{args.seed}"
    with open(f"{stem}.jsonl", "w") as f:
        for r in log:
            f.write(json.dumps(r) + "\n")
    low = [r for r in log if r["p_scelta"] < LOW]
    head = (f"Partita {args.seed} ({args.matchup}, comincia {args.starter}), rete {Path(args.ckpt).name}; "
            f"confronto: {', '.join(Path(c).name for c in args.confronta) or '-'}\n"
            f"vince {game['winner']} al turno {gs.turn}, punti A {gs.points_A} B {gs.points_B}; "
            f"{len(log)} decisioni con almeno due opzioni, {len(low)} estratte con p < {LOW}\n"
            f"Switcheroo risolti: {[(e['turn'], e['side'], e['tipo'], e['scambio']) for e in game['switch']]}\n"
            "Legenda: > la mossa estratta, * la mossa estratta con p < 0,10.")
    with open(f"{stem}.txt", "w") as f:
        f.write(head + "\n" + "".join(_riga(r) for r in log) + "\n")
    print(head)
    print(f"-> {stem}.txt")


def cmd_bot(args) -> None:
    import torch
    from riftbound.ai.ppo.prior_bot import PPOPriorAgent
    torch.set_num_threads(1)
    ref, _, _ = replay(args.seed, args.starter, args.matchup, args.ckpt, tavolo_sempre=False)
    if not 1 <= args.decisione <= len(ref):
        sys.exit(f"--decisione tra 1 e {len(ref)}")
    target = ref[args.decisione - 1]
    if target["finestra"] not in ("main", "reaction", "showdown"):
        sys.exit(f"la decisione {args.decisione} è un {target['finestra']}: serve un menu (main, reaction, showdown)")
    args.out.mkdir(parents=True, exist_ok=True)
    out = [f"Partita {args.seed} ({args.matchup}), decisione #{args.decisione}: bot completo con i prior di "
           f"{', '.join(Path(p).name for p in args.prior)}, 0,4 s per mossa, {args.volte} volte per prior"]
    for prior in args.prior:
        tally: Counter = Counter()
        for k in range(args.volte):
            seen: dict = {"choices": []}

            def bot_decides(sonda, legal, decide, prior=prior, k=k, seen=seen):
                loop = sonda.loop
                bot = PPOPriorAgent(sonda.player, _net(prior), rng=random.Random(9_000 + k), budget=0.4)
                bot.loop, bot.gs = loop, loop.gs
                sonda.player.agent = bot
                seen["tavolo"] = tavolo(loop.gs, sonda.player.name)
                seen["menu"] = [ga.label for ga in legal]
                if args.forza:
                    ga = next((g for g in legal if g.label.startswith(args.forza)), None)
                    if ga is None:
                        sys.exit(f"--forza {args.forza!r} non è nel menu: {seen['menu']}")
                    bot._ensure_rng()
                    bot._ensure_fallback()
                    action = ga.to_engine()
                else:
                    action = decide(bot)
                eng = [g.to_engine() for g in legal]
                seen["mossa"] = legal[eng.index(action)].label if action in eng else str(action)
                side = sonda.player.name

                def on_choice(kind, s, n, got, source, loop=loop):
                    if s == side:
                        objs = got if isinstance(got, (list, tuple)) and not hasattr(got, "card") else [got]
                        seen["choices"].append(f"{kind}: " + "; ".join(etichetta(loop, s, o) for o in objs))
                loop.on_choice = on_choice
                sonda.game["stop"] = True
                for name in ("decide_action", "decide_reaction", "decide_showdown_action"):
                    setattr(bot, name, lambda *a, **kw: (_ for _ in ()).throw(_Fine()))
                return action
            log, game, _ = replay(args.seed, args.starter, args.matchup, args.ckpt, handoff=args.decisione,
                                  bot_decides=bot_decides, journal=True, tavolo_sempre=False)
            same = [(r["finestra"], r["scelta"]) for r in log] == \
                   [(r["finestra"], r["scelta"]) for r in ref[:args.decisione - 1]]
            if k == 0:
                out.append(f"\n== prior {Path(prior).name}\n{seen.get('tavolo', '')}\nmenu: {seen.get('menu')}\n"
                           f"rete della partita: {[f'{p:.3f} {o}' for p, o in zip(target['p'], target['opzioni'])]}")
            key = f"{seen.get('mossa')} | " + " | ".join(seen["choices"])
            tally[key] += 1
            out.append(f"  volta {k + 1}: {key}" + ("" if same else "   (ATTENZIONE: partita diversa prima della decisione)"))
        out.append("  riepilogo: " + "; ".join(f"{n}x {key}" for key, n in tally.most_common()))
    text = "\n".join(out)
    (args.out / f"bot_{args.seed}_{args.decisione}.txt").write_text(text + "\n")
    print(text)


def _campione_game(task):
    seed, starter, mu, ckpt, prior, argmax = task
    _install_spy()
    t = time.time()
    if ckpt:
        log, game, gs = replay(seed, starter, mu, ckpt, sample=not argmax, tavolo_sempre=True)
        for r in log:          # the board only where the examples may need it
            if r["p_scelta"] >= LOW and not _base_instead(r) and r["carta"] != "Switcheroo":
                r["tavolo"] = None
    else:
        log, game, gs = _bot_game(seed, starter, mu, prior)
    return {"seed": seed, "mu": mu, "starter": starter, "winner": game["winner"], "turns": gs.turn,
            "sec": round(time.time() - t, 1), "log": log, "switch": game["switch"]}


def _bot_game(seed, starter, mu, prior):
    """Bot completo (prior) o bot a mano su entrambi i lati; le loro mosse dei
    menu con l'etichetta, per il rilevatore delle unità in base."""
    from riftbound.ai.handwritten import HandwrittenAgent
    from riftbound.core.decisions import DecisionPoint
    from riftbound.core.legality import legal_actions
    from riftbound.core.loop import GameLoop
    gs = _build(seed, starter, mu)
    log: list = []
    for seat in ("A", "B"):
        p = gs.get_player(seat)
        rng = random.Random(seed * 2 + (seat == "B"))
        if prior:
            from riftbound.ai.ppo.prior_bot import PPOPriorAgent
            p.agent = PPOPriorAgent(p, _net(prior), rng=rng, budget=0.4)
        else:
            p.agent = HandwrittenAgent(p, rng=rng, budget=0.4)
        a = p.agent
        for name, point, q in (("decide_action", DecisionPoint.TURN_ACTION, "main"),
                               ("decide_reaction", DecisionPoint.REACTION, "reaction"),
                               ("decide_showdown_action", DecisionPoint.SHOWDOWN_ACTION, "showdown")):
            def wrapped(*a_, _f=getattr(a, name), _point=point, _q=q, _a=a, **kw):
                legal = legal_actions(_a.loop, _point, _a.player.name)
                board = tavolo(_a.loop.gs, _a.player.name) if len(legal) >= 2 else None
                action = _f(*a_, **kw)
                if len(legal) >= 2:
                    eng = [g.to_engine() for g in legal]
                    i = eng.index(action) if action in eng else None
                    gs_ = _a.loop.gs
                    r = {"n": len(log) + 1, "turn": gs_.turn, "seat": _a.player.name,
                         "legend": getattr(getattr(gs_, f"legend_{_a.player.name}", None), "name", "?"),
                         "finestra": _q, "carta": None, "opzioni": [g.label for g in legal],
                         "p": [1.0 if k == i else 0.0 for k in range(len(legal))], "altre": {},
                         "scelta": i if i is not None else 0, "p_scelta": 1.0, "p_max": 1.0, "tavolo": board,
                         "bot": True}
                    if not _base_instead(r):
                        r["tavolo"] = None
                    log.append(r)
                return action
            setattr(a, name, wrapped)
    loop = GameLoop(gs)
    REAL[0] = loop
    SWITCH.clear()
    res = loop.start()
    return log, {"winner": res.winner, "switch": list(SWITCH)}, gs


def _base_instead(r) -> bool:
    """Una carta giocata in base ("Play X") quando la stessa carta era offerta
    su un campo ("Play X to BFi")."""
    if r["finestra"] != "main":
        return False
    lab = r["opzioni"][r["scelta"]]
    return lab.startswith("Play ") and " to BF" not in lab and " from " not in lab and \
        any(o.startswith(lab + " to BF") for o in r["opzioni"])


def cmd_campione(args) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "partite.jsonl"
    done = set()
    if rows_path.exists():
        done = {(g["seed"], g["mu"]) for g in map(json.loads, open(rows_path))}
    mus = args.matchup or list(ORDER)
    tasks = [(args.seed0 + 1_000 * ORDER.index(mu) + k, "a" if k % 2 == 0 else "b", mu, args.ckpt, args.prior,
              args.argmax) for mu in mus for k in range(args.partite)]
    tasks = [t for t in tasks if (t[0], t[2]) not in done]
    print(f"{len(tasks)} partite da giocare, {args.workers} processi", flush=True)
    with Pool(args.workers) as pool, open(rows_path, "a") as f:
        for i, g in enumerate(pool.imap_unordered(_campione_game, tasks), 1):
            f.write(json.dumps(g) + "\n")
            f.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(tasks)} {time.strftime('%H:%M')}", flush=True)
    games = [json.loads(l) for l in open(rows_path)]
    text = riassunto(games, args)
    (args.out / "RIASSUNTO.txt").write_text(text + "\n")
    print(text)


def riassunto(games, args) -> str:
    who = (f"rete {Path(args.ckpt).name}" + (" (la mossa più probabile)" if args.argmax else " (campionata)")
           if args.ckpt else f"bot completo, prior {Path(args.prior).name}" if args.prior else "bot a mano")
    rows = [r for g in games for r in g["log"]]
    out = [f"Campione: {who}; {len(games)} partite ({Counter(g['mu'] for g in games)}), seed da {args.seed0}; "
           f"{len(rows)} decisioni con almeno due opzioni"]
    if args.ckpt:
        by = defaultdict(list)
        for r in rows:
            by[r["finestra"]].append(r)
        out.append(f"\nPer finestra: n, p media della mossa giocata, quota con p < {LOW}, quota con p < 0,25, "
                   "quota con p massima > 0,9")
        for q, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            n = len(rs)
            out.append(f"  {q:16s} {n:6d}  {sum(r['p_scelta'] for r in rs) / n:.3f}  "
                       f"{sum(r['p_scelta'] < LOW for r in rs) / n:.3f}  {sum(r['p_scelta'] < 0.25 for r in rs) / n:.3f}"
                       f"  {sum(r['p_max'] > 0.9 for r in rs) / n:.3f}")
        per_game = [sum(r["p_scelta"] < LOW for r in g["log"]) for g in games]
        out.append(f"  mosse con p < {LOW} per partita: media {sum(per_game) / max(len(per_game), 1):.1f}")
    base = [r for r in rows if _base_instead(r)]
    offered = [r for r in rows if r["finestra"] == "main" and any(" to BF" in o for o in r["opzioni"])]
    out.append(f"\nUnità in base con la stessa carta offerta su un campo: {len(base)} "
               f"(su {len(offered)} menu con una carta offerta su un campo)")
    if args.ckpt and base:
        out.append(f"  di cui con p < {LOW}: {sum(r['p_scelta'] < LOW for r in base)}; "
                   f"p media {sum(r['p_scelta'] for r in base) / len(base):.3f}")
    sw = [e for g in games for e in g["switch"]]
    out.append(f"\nSwitcheroo risolti: {len(sw)}")
    for k, n in Counter(e["tipo"] for e in sw).most_common():
        out.append(f"  {k}: {n}")
    out.append(f"  durante uno showdown: {sum(e['showdown_bf'] is not None for e in sw)}; scambio fuori dal campo "
               f"dello showdown: {sum(e['fuori_dallo_showdown'] for e in sw)}; da coperto, scambio su un altro "
               f"campo: {sum(e['altro_campo_da_coperto'] for e in sw)}")
    gains = [e["mio_guadagno_allo_showdown"] for e in sw if "mio_guadagno_allo_showdown" in e]
    if gains:
        out.append(f"  Might guadagnata dal lato che lancia al campo dello showdown: {Counter(gains)}")
    # Examples, declared: the first N of each kind in seed order.
    ex = []
    rnd = random.Random(1)
    if args.ckpt:
        low = [r for r in rows if r["p_scelta"] < LOW and r.get("tavolo")]
        ex += [("Mossa estratta con p < 0,10", r) for r in rnd.sample(low, min(args.esempi, len(low)))]
    ex += [("Unità in base con un campo offerto", r) for r in base[:args.esempi]]
    text = "\n".join(out)
    if ex or sw:
        parts = [f"\n\n=== {k}{_riga(r)}" for k, r in ex]
        parts += [f"\n\n=== Switcheroo, turno {e['turn']}, {e['side']}: {e['tipo']}; scambio {e['scambio']}; "
                  f"showdown a BF{e['showdown_bf']}\n" + "\n".join("   " + l for l in e["tavolo_prima"].splitlines())
                  for e in sw[:args.esempi]]
        (args.out / "ESEMPI.txt").write_text("".join(parts) + "\n")
        text += f"\n\nEsempi completi in {args.out / 'ESEMPI.txt'}"
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("partita", "bot"):
        p = sub.add_parser(name)
        p.add_argument("--seed", type=int, required=True)
        p.add_argument("--starter", choices=("a", "b"), required=True)
        p.add_argument("--matchup", choices=ORDER, required=True)
        p.add_argument("--ckpt", required=True, help="la rete della partita (entrambi i lati)")
        p.add_argument("--out", type=Path, default=ROOT / "runs/giocate")
    sub.choices["partita"].add_argument("--confronta", nargs="*", default=[])
    b = sub.choices["bot"]
    b.add_argument("--decisione", type=int, required=True, help="il numero # nel file della partita")
    b.add_argument("--prior", nargs="+", required=True)
    b.add_argument("--volte", type=int, default=10)
    b.add_argument("--forza", default=None, help="la mossa (inizio dell'etichetta), il bot sceglie solo il resto")
    c = sub.add_parser("campione")
    c.add_argument("--ckpt", default=None)
    c.add_argument("--prior", default=None)
    c.add_argument("--argmax", action="store_true")
    c.add_argument("--partite", type=int, default=20, help="per matchup")
    c.add_argument("--matchup", nargs="*", choices=ORDER, default=None)
    c.add_argument("--seed0", type=int, default=SEED0)
    c.add_argument("--esempi", type=int, default=12)
    c.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    c.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    {"partita": cmd_partita, "bot": cmd_bot, "campione": cmd_campione}[args.cmd](args)


if __name__ == "__main__":
    main()
