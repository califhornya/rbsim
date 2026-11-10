#!/usr/bin/env python
"""Official card text from Piltover Archive, and how all_cards.json differs.

    uv run python scripts/piltover_sync.py fetch
    uv run python scripts/piltover_sync.py compare
    uv run python scripts/piltover_sync.py compare --decks riftbound/data/decks/precon_*.json
    uv run python scripts/piltover_sync.py compare --out piltover_diff.md

`fetch` reads every page of https://piltoverarchive.com/cards (the card data
is embedded in each page) and writes riftbound/data/reference/piltover_archive.json:
one entry per printed variant, with the printed text, costs, Might, domains
and the official errata (an errata'd card's text starts with "Card Errata
Text"). Prices and shop ids are left out so a re-fetch only changes what
changed on the cards. No images are stored.

`compare` puts all_cards.json next to it, card by card (by card_id, else by
name): Energy, Power, Might, domain and the printed text. The text is compared
without formatting, icons' brackets and reminder text, so "[Tank]" and "TANK"
match. A flag is a reason to read the card, not a verdict: the site has typos
too. It checks the text we hold, not whether the engine does what it says
(scripts/card_text_audit.py and the tests do that).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "riftbound" / "data" / "cards" / "all_cards.json"
ARCHIVE = ROOT / "riftbound" / "data" / "reference" / "piltover_archive.json"
SITE = "https://piltoverarchive.com/cards"

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.S)
_VARIANT = re.compile(r'\{"id":"[0-9a-f-]{36}","variantNumber"')
_LAST_PAGE = re.compile(r'href="/cards\?page=(\d+)"')


# ---------------------------------------------------------------- fetch

def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rbsim card sync)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def _variants(html: str) -> list[dict]:
    """The variant objects embedded in one page's React Server Components payload."""
    blob = "".join(json.loads(c) for c in _PUSH.findall(html))
    dec = json.JSONDecoder()
    out = []
    for m in _VARIANT.finditer(blob):
        try:
            obj, _ = dec.raw_decode(blob, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj.get("card"), dict):
            out.append(obj)
    return out


def _is_errata(text: str | None) -> bool:
    """The site opens an errata'd card's text with a bold "Card Errata Text" line."""
    first = unicodedata.normalize("NFKC", text or "").split("\n", 1)[0]
    return "errata" in first.lower()


def _entry(v: dict) -> dict:
    c = v["card"]
    text = c.get("description") or ""
    return {
        "variant": v["variantNumber"],
        "variant_type": v.get("variantType"),
        "set": (v.get("set") or {}).get("prefix"),
        "name": c.get("name"),
        "type": c.get("type"),
        "types": c.get("types"),
        "super": c.get("super"),
        "energy": c.get("energy"),
        "power": c.get("power"),
        "might": c.get("might"),
        "might_bonus": c.get("mightBonus"),
        "domains": [d.get("name") for d in c.get("colors") or []],
        "tags": c.get("tags"),
        "text": text,
        "attach_text": c.get("attachText"),
        "effect": c.get("effect"),
        "errata": _is_errata(text),
        "image_url": v.get("imageUrl"),
    }


def fetch(delay: float) -> None:
    first = _get(SITE)
    pages = max((int(n) for n in _LAST_PAGE.findall(first)), default=1)
    found: dict[str, dict] = {}
    for p in range(1, pages + 1):
        html = first if p == 1 else _get(f"{SITE}?page={p}")
        vs = _variants(html)
        for v in vs:
            found[v["variantNumber"]] = _entry(v)
        print(f"page {p}/{pages}: {len(vs)} variants", file=sys.stderr)
        if p < pages:
            time.sleep(delay)
    if not found:
        sys.exit("no card data found: the site's page layout has changed")
    data = {
        "source": SITE,
        "fetched": date.today().isoformat(),
        "cards": dict(sorted(found.items())),
    }
    ARCHIVE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    names = {e["name"] for e in found.values()}
    print(f"{len(found)} variants, {len(names)} cards -> {ARCHIVE.relative_to(ROOT)}")


# -------------------------------------------------------------- compare

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    if _is_errata(s):
        s = s.split("\n", 1)[1] if "\n" in s else ""
    s = s.lower()
    s = re.sub(r"(?<=[a-z])[-\u2013](?=[a-z])", "", s)    # non-unit, Quick–Draw
    s = re.sub(r"[\u2013\u2014]", "", s)                  # "EMPOWER — Discard 1"; "-1" stays
    s = re.sub(r"\([^()]*\)", "", s)                     # reminder text
    s = s.replace("opponent's", "opponents").replace("anytime", "any time")
    return re.sub(r"[^a-z0-9+\-]", "", s)                # brackets, [>], spacing, punctuation


def _site_text(e: dict) -> str:
    return " ".join(x for x in (e["text"], e["attach_text"], e["effect"]) if x)


def _our_text(c: dict) -> str:
    return " ".join(x for x in (c.get("effect"), c.get("effect_equipped")) if x)


def _deck_names(patterns: list[str]) -> set[str]:
    names: set[str] = set()
    for pat in patterns:
        for f in sorted(glob.glob(pat)) or [pat]:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            names |= {c["name"] for c in d.get("cards", [])}
            names |= {d[k] for k in ("legend", "champion") if d.get(k)}
            names |= {b["name"] for b in d.get("battlefields", [])}
    return names


def _diffs(c: dict, e: dict) -> list[str]:
    out = []
    if (c.get("cost_energy") or 0) != (e["energy"] or 0):
        out.append(f"energy: ours {c.get('cost_energy')}, printed {e['energy']}")
    if (c.get("cost_power") or 0) != (e["power"] or 0):
        out.append(f"power: ours {c.get('cost_power')}, printed {e['power']}")
    printed_might = e["might_bonus"] if c.get("category") == "Gear" else e["might"]
    if (c.get("might") or 0) != (printed_might or 0):
        out.append(f"might: ours {c.get('might')}, printed {printed_might}")
    ours_dom = sorted(filter(None, re.split(r"[/,\s]+", c.get("domain") or "")))
    if e["domains"] and ours_dom != sorted(e["domains"]):
        out.append(f"domain: ours {c.get('domain')}, printed {'/'.join(e['domains'])}")
    if _norm(_our_text(c)) != _norm(_site_text(e)):
        out.append("text")
    return out


def compare(decks: list[str], out: Path | None, show_all: bool) -> None:
    if not ARCHIVE.exists():
        sys.exit(f"{ARCHIVE.relative_to(ROOT)} missing: run `fetch` first")
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    by_variant = archive["cards"]
    by_name: dict[str, dict] = {}
    for e in by_variant.values():                      # prefer the Standard printing
        if e["name"] not in by_name or e["variant_type"] == "Standard":
            if by_name.get(e["name"], {}).get("variant_type") != "Standard":
                by_name[e["name"]] = e
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    wanted = _deck_names(decks) if decks else None
    if wanted:
        cards = [c for c in cards if c["name"] in wanted]

    lines, flagged, missing, errata = [], 0, [], []
    for c in cards:
        e = by_variant.get(c["card_id"]) or by_name.get(c["name"])
        if e is None:
            missing.append(f"{c['name']} [{c['card_id']}]")
            continue
        if e["errata"]:
            errata.append(c["name"])
        d = _diffs(c, e)
        if not d and not show_all:
            continue
        flagged += bool(d)
        tag = " (errata)" if e["errata"] else ""
        lines.append(f"## {c['name']} [{c['card_id']}]{tag}: {'; '.join(d) or 'ok'}")
        if "text" in d or show_all:
            lines.append(f"    ours:    {_our_text(c).replace(chr(10), ' / ')}")
            lines.append(f"    printed: {_site_text(e).replace(chr(10), ' / ')}")
    head = [
        f"Piltover Archive ({archive['fetched']}) vs all_cards.json"
        + (f", cards in {len(wanted)} deck names" if wanted else ""),
        f"{len(cards)} cards: {flagged} differ, {len(missing)} not on the site, "
        f"{len(errata)} with official errata",
        "",
    ]
    if missing:
        head += ["Not on the site: " + ", ".join(missing), ""]
    report = "\n".join(head + lines) + "\n"
    if out:
        out.write_text(report, encoding="utf-8")
        print("\n".join(head[:2]) + f"\n-> {out}")
    else:
        print(report)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download the site into piltover_archive.json")
    f.add_argument("--delay", type=float, default=0.5, help="seconds between pages")
    c = sub.add_parser("compare", help="report where all_cards.json differs")
    c.add_argument("--decks", nargs="+", default=[], help="only the cards in these deck files or globs")
    c.add_argument("--out", type=Path, help="write the report to this file")
    c.add_argument("--all", action="store_true", help="list matching cards too")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.delay)
    else:
        compare(args.decks, args.out, args.all)


if __name__ == "__main__":
    main()
