#!/usr/bin/env python
"""Play ONE game and emit a complete, human-readable decision-by-decision trace.

For every decision (turn action / showdown / reaction) it prints the full board
state at that moment, the legal options, and the action the agent chose — and for
the `mc` search agent, its per-action win-rate estimates (so you can see *why* it
chose). The engine's own event log (channel, draws, plays, combat, conquer,
scoring, end-of-turn) is interleaved via verbose mode. This is the tool for
confirming an agent actually plays sensibly, start to finish.

Usage:
  uv run python scripts/trace_game.py --deckA riftbound/data/decks/vendetta_akali.json \
      --deckB riftbound/data/decks/vendetta_kennen.json --aiA mc --aiB simple_trade \
      --seed 1 --out trace.log
  # then read trace.log (also echoed to the terminal unless --quiet)
"""
from __future__ import annotations

import argparse
import contextlib
import io as _io
import sys
from pathlib import Path

from riftbound.ai.heuristics.base_agent import Action, Agent
from riftbound.core.decisions import DecisionPoint
from riftbound.core.game_factory import AI_REGISTRY, build_game, make_agent
from riftbound.core.legality import legal_actions
from riftbound.core.loop import GameLoop


def _fmt_unit(u) -> str:
    tags = []
    if not u.ready:
        tags.append("tapped")
    if getattr(u, "empowered", False):
        tags.append("EMPOWERED")
    if u.stunned:
        tags.append("stunned")
    if u.damage:
        tags.append(f"dmg{u.damage}")
    if u.might_counters:
        tags.append(f"+{u.might_counters}buff")
    if u.is_token:
        tags.append("token")
    if u.gear:
        tags.append("gear:" + "/".join(getattr(g, "name", "?") for g in u.gear))
    suffix = ("  [" + ", ".join(tags) + "]") if tags else ""
    return f"{u.card.name} m{u.might}{suffix}"


def _units_line(units) -> str:
    return ", ".join(_fmt_unit(u) for u in units) if units else "(none)"


def _dump_board(gs, viewer: str) -> None:
    other = gs.other(viewer)
    me = gs.get_player(viewer)
    op = gs.get_player(other)
    print(f"  Points: A {gs.points_A} — B {gs.points_B}  (to win: {gs.victory_score})"
          f"   Energy: A {gs.A.energy} B {gs.B.energy}   XP: A {gs.get_xp('A')} B {gs.get_xp('B')}")
    pa = {d.name: n for d, n in gs.A.power_pool.items() if n}
    pb = {d.name: n for d, n in gs.B.power_pool.items() if n}
    print(f"  Power: A {pa or '{}'} B {pb or '{}'}   "
          f"Runes: A {gs.A.total_runes_in_play()} B {gs.B.total_runes_in_play()}   "
          f"Deck/Trash: A {len(gs.A.deck.cards)}/{len(gs.A.trash)} B {len(gs.B.deck.cards)}/{len(gs.B.trash)}")
    for side in ("A", "B"):
        lu = gs.legend_unit_A if side == "A" else gs.legend_unit_B
        if lu is not None:
            emp = " [EMPOWERED]" if getattr(lu, "empowered", False) else ""
            print(f"  Legend {side}: {lu.card.name}{emp}")
    for i, bf in enumerate(gs.battlefields):
        named = f" [{bf.card.name}]" if getattr(bf, "card", None) else ""
        print(f"  BF{i}{named}  controller={bf.controller() or '-'}")
        print(f"     A: {_units_line(bf.units_A)}")
        print(f"     B: {_units_line(bf.units_B)}")
    print(f"  Base A: {_units_line(me.base_units) if viewer=='A' else _units_line(gs.A.base_units)}")
    print(f"  Base B: {_units_line(gs.B.base_units)}")
    # Show the deciding player's hand (their own information).
    print(f"  {viewer} hand ({len(me.hand)}): {', '.join(c.name for c in me.hand) or '(empty)'}")


_POINT_LABEL = {
    DecisionPoint.TURN_ACTION: "main phase",
    DecisionPoint.SHOWDOWN_ACTION: "showdown",
    DecisionPoint.REACTION: "reaction",
}


class TracingAgent(Agent):
    """Wraps a real agent: logs the board + legal actions + chosen action (and the
    mc agent's per-action win-rate estimates) at every decision, then delegates."""

    name = "trace"

    def __init__(self, player, inner: Agent):
        super().__init__(player)
        self.inner = inner

    def _sync(self) -> None:
        self.inner.loop = getattr(self, "loop", None)
        self.inner.gs = getattr(self, "gs", None)

    def _log_decision(self, point: DecisionPoint) -> None:
        gs = self.gs
        side = self.player.name
        print(f"\n{'─'*70}")
        print(f"DECISION ── {side} (turn {gs.turn}, {_POINT_LABEL.get(point, point)})")
        _dump_board(gs, side)
        opts = legal_actions(self.loop, point, side)
        print("  Legal actions:")
        for idx, a in enumerate(opts):
            print(f"     {idx:>2} {a.label or a.kind}")

    def _log_choice(self, act: Action) -> None:
        # mc reasoning, if present.
        ev = getattr(self.inner, "last_eval", None)
        if ev:
            ranked = sorted(ev, key=lambda kv: -kv[1])
            pretty = "  ".join(f"[{lbl}={sc:.2f}]" for lbl, sc in ranked)
            print(f"  mc eval: {pretty}")
        print(f"  → CHOSE: {act}")

    def decide_action(self, opponent, cards_played: int = 0) -> Action:
        self._sync()
        self._log_decision(DecisionPoint.TURN_ACTION)
        act = self.inner.decide_action(opponent, cards_played)
        self._log_choice(act)
        return act

    def decide_mulligan(self) -> list:
        self._sync()
        keep = self.inner.decide_mulligan()
        print(f"\n[MULLIGAN] {self.player.name} returns hand indices: {keep or 'none (keep all)'}")
        return keep

    def decide_showdown_action(self, opponent, bf_idx: int) -> Action:
        self._sync()
        self._log_decision(DecisionPoint.SHOWDOWN_ACTION)
        act = self.inner.decide_showdown_action(opponent, bf_idx)
        self._log_choice(act)
        return act

    def decide_reaction(self, opponent, chain) -> Action:
        self._sync()
        self._log_decision(DecisionPoint.REACTION)
        act = self.inner.decide_reaction(opponent, chain)
        self._log_choice(act)
        return act


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deckA", type=Path, required=True)
    ap.add_argument("--deckB", type=Path, required=True)
    ap.add_argument("--aiA", default="mc")
    ap.add_argument("--aiB", default="simple_trade")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--first-player", default="random")
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--out", type=Path, default=Path("trace.log"))
    ap.add_argument("--quiet", action="store_true", help="Only write the file, don't echo to terminal")
    args = ap.parse_args()

    for label, name in (("--aiA", args.aiA), ("--aiB", args.aiB)):
        if name.strip().lower() not in AI_REGISTRY:
            raise SystemExit(f"Unknown AI '{name}' for {label}. Available: {', '.join(AI_REGISTRY)}")

    gs = build_game(game_seed=args.seed, deck_a_path=args.deckA, deck_b_path=args.deckB,
                    ai_a=None, ai_b=None, first_player=args.first_player, max_turns=args.max_turns)
    gs.A.agent = TracingAgent(gs.A, make_agent(args.aiA, gs.A))
    gs.B.agent = TracingAgent(gs.B, make_agent(args.aiB, gs.B))

    buf = _io.StringIO()
    header = (f"=== TRACE  A={args.aiA} ({args.deckA.stem})  vs  B={args.aiB} ({args.deckB.stem})  "
              f"seed={args.seed} ===")
    with contextlib.redirect_stdout(buf):
        print(header)
        result = GameLoop(gs, verbose=True).start()
        print(f"\n=== RESULT: winner={result.winner} in {result.turns} turns "
              f"(final points A {gs.points_A} — B {gs.points_B}) ===")

    text = buf.getvalue()
    args.out.write_text(text, encoding="utf-8")
    if not args.quiet:
        sys.stdout.write(text)
    sys.stdout.write(f"\n[trace written to {args.out} — {text.count(chr(10))} lines]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
