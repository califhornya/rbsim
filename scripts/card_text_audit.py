#!/usr/bin/env python
"""Card text vs encoding: the reading aid for BACKLOG section D.

For every card with ability text, split the printed text into sentences (minus
reminder text in parentheses) and put them next to the effect entries, then
run cheap checks that catch whole classes of encoding mistakes:

- trigger:  a sentence starts with a trigger phrase ("When I attack",
            "DEATHKNELL", "When you conquer here", "[tap]:" ...) and no entry
            has a matching trigger
- dead:     an entry whose trigger can never fire for this card type (an
            on_play entry on a battlefield, a combat trigger on a spell)
- number:   "deal 3", "draw 2", "+2 [might]" ... and no entry carries that number
- may:      "you may" and no entry is optional / has a cost
- for_each: "for each" and no entry scales (amount_source, per_..., ...)
- hand:     "return ... to ... hand" and no entry returns to hand
- count:    more sentences than entries (one entry can cover two sentences)

A flag is a reason to read the card, not a verdict: every card gets read.

Usage:
  uv run python scripts/card_text_audit.py                   # summary
  uv run python scripts/card_text_audit.py --out FILE        # per-card dump
  uv run python scripts/card_text_audit.py --out FILE --set Origins --all
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import typer

REPO = Path(__file__).resolve().parent.parent
CARDS_FILE = REPO / "riftbound" / "data" / "cards" / "all_cards.json"

_PARENS = re.compile(r"\([^()]*\)")
_ICON = re.compile(r"\[[^\]]*\]")
_KEYWORD_LINE = re.compile(
    r"^(?:[A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]+)*(?: \d+| \[[^\]]*\])*\s*)+$")

# Sentence opener -> triggers that express it.
_PLAY = {"on_play", "on_cast"}
_TRIGGER_PHRASES: list[tuple[re.Pattern, set[str]]] = [
    (re.compile(r"^when you play (me|this)\b"), _PLAY),
    (re.compile(r"^when i attack or defend\b"), {"on_attack", "on_defend"}),
    (re.compile(r"^when i attack\b"), {"on_attack"}),
    (re.compile(r"^when i defend\b"), {"on_defend"}),
    (re.compile(r"^when (i|you) conquer\b"), {"on_conquer"}),
    (re.compile(r"^when (i|you) hold\b"), {"on_hold"}),
    (re.compile(r"^when (i|you) conquer or hold\b"), {"on_conquer", "on_hold"}),
    (re.compile(r"^(deathknell|when i die|when this dies)\b"),
     {"on_death", "death_replacement", "leaves_board"}),
    (re.compile(r"^when i move\b"), {"on_move"}),
    (re.compile(r"^at the start of (your|each player's|each) (turn|beginning phase)"),
     {"on_start_of_turn"}),
    (re.compile(r"^at (the )?(start of your )?end(ing)? (of turn|phase)|^at the end of (your|each|this) turn"),
     {"on_end_of_turn"}),
    (re.compile(r"^when you play a spell\b"), {"on_play_spell", "on_card_played"}),
    (re.compile(r"^when you play a (unit|another unit)\b"),
     {"on_friendly_unit_played", "on_card_played"}),
    (re.compile(r"^when you play a card\b"), {"on_card_played"}),
]
_ACTIVATED = re.compile(r"^(action |reaction )?[^.:]*\]\s*:|^(action|reaction)\b.*:|^\[tap\]")
# The triggers the engine fires for a battlefield's own card (GameLoop: turn
# triggers, scoring, _open_combat, hide / play / move-from here); any other one
# on a battlefield never fires unless that trigger's dispatch was taught to.
_BATTLEFIELD_FIRED = {"on_start_of_turn", "on_end_of_turn", "on_conquer", "on_hold",
                      "on_hide_here", "on_unit_played_here", "on_unit_moves_from_here",
                      "on_combat_start_here", "on_attack", "on_defend", "passive",
                      "granted_to_legend", "granted_to_units_here", "on_play_spell",
                      "on_first_unit_here", "on_unit_dies_here", "cost_aura", "activated"}
_TYPE_DEAD_TRIGGERS: dict[str, set[str]] = {
    "spell": {"on_attack", "on_defend", "on_conquer", "on_hold", "on_move",
              "on_death", "on_start_of_turn", "on_end_of_turn"},
    "legend": {"on_play", "on_cast", "on_attack", "on_defend", "on_move",
               "on_death"},
}
_NUMBERS = [
    (re.compile(r"\bdeal (\d+)"), "deal"),
    (re.compile(r"\bdraw (\d+)"), "draw"),
    (re.compile(r"\+(\d+) \[?might"), "+might"),
    (re.compile(r"-(\d+) \[?might"), "-might"),
    (re.compile(r"\bchannel (\d+)"), "channel"),
    (re.compile(r"\b(\d+) \[?might\]? \w+ unit token"), "token might"),
]
_SCALING_KEYS = ("amount_source", "per", "for_each", "count_source", "scaling")


def _category(card: dict) -> str:
    cat = str(card.get("category") or "").lower()
    for base in ("spell", "unit", "gear", "battlefield", "legend", "champion",
                 "token", "rune"):
        if base in cat:
            return base
    return cat


def sentences(card: dict) -> list[str]:
    """Ability sentences of the printed text, reminder text removed, keyword-only
    lines dropped."""
    text = str(card.get("effect") or "")
    eq = str(card.get("effect_equipped") or "")
    if eq:
        text += "\n" + eq
    text = text.replace("—", "-").replace("�", "-")
    prev = None
    while prev != text:   # nested reminders
        prev, text = text, _PARENS.sub(" ", text)
    out: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        # "Choose one - * A. * B." stays one sentence (its modes are one entry)
        if re.search(r"(?i)choose one", line):
            out.append(line)
            continue
        for part in re.split(r"(?<=[.!])\s+(?=[A-Z\[])", line):
            part = part.strip()
            if not part or _KEYWORD_LINE.match(_ICON.sub("", part).strip() or "X"):
                continue
            if not re.search(r"[a-z]{3,}", _ICON.sub(" ", part)):
                continue
            out.append(part)
    return out


def _walk(obj):
    """Every dict nested in an entry (modes, steps, then ...)."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _numbers_in(entries: list[dict]) -> set[int]:
    nums: set[int] = set()
    for d in _walk(entries):
        for v in d.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                nums.add(abs(int(v)))
    return nums


def check(card: dict) -> tuple[list[str], list[str]]:
    """(sentences, flags) for one card."""
    sents = sentences(card)
    entries = [e for e in (card.get("effects") or []) if isinstance(e, dict)]
    triggers = {e.get("trigger") or "on_play" for e in entries}
    cat = _category(card)
    flags: list[str] = []
    if not sents:
        return sents, flags
    for s in sents:
        low = s.lower()
        for pat, want in _TRIGGER_PHRASES:
            if pat.search(low):
                if not (want & triggers):
                    flags.append(f"trigger: no {'/'.join(sorted(want))} entry for '{s[:60]}'")
                break
        else:
            if _ACTIVATED.search(low) and "activated" not in triggers \
                    and not re.match(r"^(equip|empower|flow|repeat)\b", low):
                flags.append(f"trigger: no activated entry for '{s[:60]}'")
    for e in entries:
        tr = e.get("trigger") or "on_play"
        if tr in _TYPE_DEAD_TRIGGERS.get(cat, ()) or (cat == "battlefield" and tr not in _BATTLEFIELD_FIRED):
            flags.append(f"dead: {e.get('effect')} on {tr} can't fire on a {cat}"
                         + (" (unless its dispatch reads battlefields)" if cat == "battlefield" else ""))
    if not entries:
        flags.append("count: no entries")
    text = " ".join(sents).lower()
    nums = _numbers_in(entries)
    for pat, label in _NUMBERS:
        for m in pat.finditer(text):
            n = int(m.group(1))
            if n not in nums and n != 1:
                flags.append(f"number: '{label} {n}' not in any entry")
    if entries and re.search(r"\byou may\b|\bmay\b", text):
        if not any(d.get("optional") or d.get("cost") or d.get("additional_cost")
                   or d.get("modes") or "up_to" in json.dumps(d) or d.get("trigger") == "activated"
                   for d in _walk(entries)):
            flags.append("may: no optional / cost entry")
    if entries and "for each" in text:
        blob = json.dumps(entries)
        if not any(k in blob for k in _SCALING_KEYS):
            flags.append("for_each: no scaling entry")
    if entries and re.search(r"\breturn\b[^.]*\bhand\b", text):
        blob = json.dumps(entries)
        if not re.search(r"return|bounce|to_hand", blob):
            flags.append("hand: no return-to-hand entry")
    if len(sents) > len(entries) and entries:
        flags.append(f"count: {len(sents)} sentences, {len(entries)} entries")
    return sents, flags


def _load() -> list[dict]:
    cards = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
    seen: set[str] = set()
    out = []
    for c in cards:
        if c["name"] in seen or _category(c) == "rune":
            continue
        seen.add(c["name"])
        out.append(c)
    return out


def main(out: Path = typer.Option(None, help="write a per-card dump here"),
         set_name: str = typer.Option(None, "--set", help="only this set"),
         all_cards: bool = typer.Option(False, "--all", help="dump unflagged cards too")):
    cards = _load()
    by_set: Counter = Counter()
    by_kind: Counter = Counter()
    lines: list[str] = []
    for c in cards:
        if set_name and c["set"] != set_name:
            continue
        sents, flags = check(c)
        if not sents:
            continue
        kinds = {f.split(":")[0] for f in flags if not f.startswith("count: ")}
        if flags:
            by_set[c["set"]] += 1
            by_kind.update(kinds or {"count"})
        if out and (flags or all_cards):
            lines.append(f"### {c['name']} ({c['card_id']}, {c['category']})")
            for s in sents:
                lines.append(f"  > {s}")
            for e in c.get("effects") or []:
                lines.append(f"  - {json.dumps(e, ensure_ascii=False)}")
            for f in flags:
                lines.append(f"  ! {f}")
            lines.append("")
    print("flagged cards by set:", dict(by_set), "total", sum(by_set.values()))
    print("flags by kind:", dict(by_kind))
    if out:
        out.write_text("\n".join(lines), encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    typer.run(main)
