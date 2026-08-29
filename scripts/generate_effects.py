#!/usr/bin/env python
"""Parse each card's natural-language `effect` text into structured `effects`
(EffectSpec list) + `keywords`, enriching all_cards.json in place.

Uses the Anthropic API (Opus 4.8) with prompt caching on the schema/vocabulary
system prompt. Batches cards, validates the model output against the engine's
known effect verbs, retries on bad JSON, saves incrementally (resume-friendly),
and flags low-confidence cards to scripts/review_needed.txt. A completeness
heuristic additionally flags cards whose emitted effect count looks too low for
their clause count (DISEASE-A dropped-clause safety net).

Usage:
  export ANTHROPIC_API_KEY=...
  uv run python scripts/generate_effects.py --set "Proving Grounds"   # 24-card shakedown
  uv run python scripts/generate_effects.py --only-empty               # all cards lacking effects
  uv run python scripts/generate_effects.py --retry-review             # only cards flagged in review_needed.txt
  uv run python scripts/generate_effects.py --limit 10                 # first 10 (any)
  uv run python scripts/generate_effects.py --dry-run                  # build prompts, no API calls
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Keep the prompt vocabulary in sync with the engine.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from riftbound.core.effects import REGISTRY as EFFECT_REGISTRY  # noqa: E402
from riftbound.registry.cards_registry import (  # noqa: E402
    _KNOWN_KEYWORDS,
    _VALUED_KEYWORDS,
)
# Single source of truth for engine vocabulary (do not redeclare these here).
from riftbound.registry.engine_vocab import (  # noqa: E402
    KNOWN_TRIGGERS,
    KNOWN_CONDITIONS,
    KNOWN_FILTER_KEYS,
    KNOWN_AMOUNT_SOURCES,
    KNOWN_ACTIVATED_COST_KEYS,
    KNOWN_ADDITIONAL_COST_KEYS,
    NON_HANDLER_VERBS,
)

CARDS_PATH = Path(__file__).resolve().parent.parent / "riftbound" / "data" / "cards" / "all_cards.json"
REVIEW_PATH = Path(__file__).resolve().parent / "review_needed.txt"
MODEL = "claude-opus-4-8"
BATCH_SIZE = 10

# Sorted views for deterministic prompt text (keeps the cached system prompt stable).
_TRIGGERS_SORTED = sorted(KNOWN_TRIGGERS)
_CONDITIONS_SORTED = sorted(KNOWN_CONDITIONS)
_FILTER_KEYS_SORTED = sorted(KNOWN_FILTER_KEYS)
_AMOUNT_SOURCES_SORTED = sorted(KNOWN_AMOUNT_SOURCES)
_ACTIVATED_COST_KEYS_SORTED = sorted(KNOWN_ACTIVATED_COST_KEYS)
_ADDITIONAL_COST_KEYS_SORTED = sorted(KNOWN_ADDITIONAL_COST_KEYS)

# Targets have no canonical engine list yet; kept local (out of scope for the sync).
TARGETS = [
    "actor", "opponent", "self", "friendly_unit", "enemy_unit",
    "all_friendly_units_here", "all_enemy_units_here", "all_units_here",
    "battlefield", "chosen_unit", "chosen_spell",
]


def build_system_prompt() -> str:
    verbs = ", ".join(sorted(EFFECT_REGISTRY.keys()))
    keywords = ", ".join(sorted(_KNOWN_KEYWORDS))
    valued = ", ".join(sorted(_VALUED_KEYWORDS))
    return f"""You are a parser for the Riftbound TCG simulator. Given a card's printed
rules text (the `effect` field, plus `effect_equipped` for gear), produce a structured
representation the game engine can execute.

CRITICAL — COVER THE WHOLE CARD (read this before anything else):
A card's `effect` text often contains MULTIPLE independent abilities and multi-step
effects, joined by "then", "and", "if you do", "•", or simply written as separate
sentences. You MUST account for EVERY executable clause — not just the first one.
Before returning a card, re-read its `effect` (and `effect_equipped`) text SENTENCE BY
SENTENCE and confirm each sentence maps to at least ONE of:
  (a) an effect object, (b) a keyword, or (c) an explicit `needs_review` flag +
  `suggested_vocab` for a clause whose mechanic you cannot support.
Never stop after the first clause. Silently dropping the back half of a card ("kill X,
THEN do Y"; a second "When I …" ability; a "[tap]:" activated ability after an on-play
line) is the single most common and most damaging error — do not do it.
Reminder text in (parentheses) only restates rules; it never adds a new clause and
needs no effect of its own.
Reconciling completeness with faithfulness: emit an effect for every clause that maps
CLEANLY to the supported vocab. For a clause that maps ONLY via an approximation that
changes the card's MEANING (see "Semantic disambiguation" below), do NOT emit a wrong
effect — parse the other clauses and flag ONLY that clause (needs_review +
suggested_vocab). Partial-but-faithful beats complete-but-wrong, and both beat
dropping-a-clause-silently.

Return, for each card, two things:
1. `keywords`: a list of keyword strings. Only from this set: {keywords}.
   Valued keywords carry a number, e.g. "SHIELD 2", "ASSAULT 3", "HUNT 1", "REPEAT 2": {valued}.
   Migration: write "VISION" as "PREDICT 1"; write "QUICK" as "QUICK-DRAW"; never emit "MIGHTY".
   Keywords are NEVER placed in `effects`.
2. `effects`: a list of structured effect objects. Each object:
   {{
     "effect": <one of the supported verbs below>,
     "trigger": <one of: {", ".join(_TRIGGERS_SORTED)}>,   # default "on_play" for units/gear, "on_cast"≈"on_play" for spells
     "timing": "action" | "reaction" | null,        # only for spells/abilities playable off-turn
     "condition": null | {{"type": <condition type>, "params": {{...}}}},
     "target": <one of: {", ".join(TARGETS)}> (omit to use the engine default),
     "target_filter": null | {{<filter key>: <value>}},   # narrows the chosen targets (see below)
     "amount_source": <dynamic source>,             # use INSTEAD of "amount" when magnitude is computed (see below)
     "scope": "single" | "all" (omit for default),
     "duration": "instant" | "this_turn" | "permanent" (omit for default),
     "amount": <int, when the verb needs a fixed magnitude>,
     "cost": {{<cost key>: <value>}},               # ONLY on "trigger": "activated" (see below)
     ...any other verb-specific params (e.g. "keyword", "token_name", "count", "max_energy")
   }}

Supported effect verbs (use ONLY these): {verbs}.
Plus the special non-handler verb `reduce_cost` (see "Cost modification" below).

Supported condition types: {", ".join(_CONDITIONS_SORTED)}.

Target filters (`target_filter`) — keys the engine understands:
  {", ".join(_FILTER_KEYS_SORTED)}.
  Semantics: `exclude_self` (bool) drops the source card itself; `has_keyword`/`lacks_keyword`
  take a keyword string; `is_gear`/`is_spell`/`is_unit`/`is_token` are bools matching card type;
  `subtype` takes a string that must appear in the unit's sub_type/tags; `might_at_most`/
  `might_at_least` take an int compared against the unit's might.
  More keys: `non_token` / `is_token` (bool); `is_buffed` (has a +might counter);
  `is_mighty` (might >= 5); `is_legend`/`is_champion` (bool); `card_type`
  ("UNIT"|"SPELL"|"GEAR"|"CHAMPION"|"LEGEND"|"BATTLEFIELD"); `might_less_than_self`
  (bool, compares vs the source unit's might).
  Examples: "another friendly unit" → {{"exclude_self": true}}; "an enemy unit with might 3 or
  less" → {{"might_at_most": 3}}; "a friendly Zaun unit" → {{"subtype": "Zaun"}};
  "a non-token unit" → {{"non_token": true}}; "a buffed unit" → {{"is_buffed": true}};
  "a unit with less might than me" → {{"might_less_than_self": true}}.

Dynamic amount sources (`amount_source`) — use this field INSTEAD of `amount` when the magnitude
is computed at resolution, not fixed. Allowed values: {", ".join(_AMOUNT_SOURCES_SORTED)}.
  Mapping: "damage equal to my might" → "self_might"; "draw 1 for each of your Mighty units" →
  "friendly_mighty_units" (verb draw_cards); "for each card in your trash" → "trash_count";
  "equal to your points" → "controller_points"; "equal to your opponent's points" →
  "opponent_points"; "for each card in your hand" → "cards_in_hand"; "for each enemy unit here"
  → "enemies_here"; "for each friendly unit here" → "friendly_units_here"; "equal to your highest
  might unit" → "highest_might_friendly"; "for each friendly <Tag> unit" → "n_friendly_with_tag"
  (set "tag": "<Tag>"). Do NOT also set `amount` when you set `amount_source`.

Costs for activated abilities (`cost`) — when the text is an activated ability of the form
"[Action] [cost]: <effect>" or "[Reaction] [cost]: <effect>", set "trigger": "activated", set
"timing" to "action"/"reaction", and express the cost as a dict using ONLY these keys:
  {", ".join(_ACTIVATED_COST_KEYS_SORTED)}.
  `tap` is a bool (tap this card); `energy`/`power`/`spend_xp` take ints; `recycle` (recycle a
  card from hand) and `sacrifice` (sacrifice a friendly unit) take ints/bools.
  Concrete: "[Action] [tap]: deal 1 to an enemy unit" →
  {{"effect": "deal_damage", "trigger": "activated", "timing": "action", "amount": 1,
    "target": "enemy_unit", "cost": {{"tap": true}}}}.
  If the cost uses a mechanic NOT in the key list above (e.g. exhaust another unit, recycle from
  trash, kill a friendly unit, pay XP), do NOT invent a key — instead set "needs_review": true and
  add the cost to `suggested_vocab` tagged like "cost:exhaust_self", "cost:recycle_from_trash".

Optional additional cost / kicker (`additional_cost`) — when playing a card from
hand lets you pay an OPTIONAL extra cost for a bonus ("As you play me, you may …;
if you do, …"). Put `additional_cost` on the bonus effect (trigger on_play/on_cast)
AND gate that effect with `condition: {{"type": "kicker_paid"}}`. Allowed keys:
  {", ".join(_ADDITIONAL_COST_KEYS_SORTED)}.
  `energy`/`power`/`discard_cards` take ints; `kill_friendly_unit`/
  `exhaust_friendly_unit` are bools.
  Cost symbols: a bare bracketed number `[N]` is N energy; a domain symbol like
  `[fury]`/`[calm]` is 1 POWER of that domain — use the `power` key, not `energy`.
  Example — "You may pay an additional [fury] to play me. If you did, deal 2
  damage to an enemy unit" (Blast Corps Cadet):
  {{"effect": "deal_damage", "trigger": "on_play", "amount": 2,
    "target": "enemy_unit", "condition": {{"type": "kicker_paid"}},
    "additional_cost": {{"power": 1}}}}.
  Effects WITHOUT a kicker condition fire normally regardless.

Cost modification (`reduce_cost`) — for static/conditional flat discounts. Use verb "reduce_cost"
with "trigger": "cost_modifier" and an integer `amount`.
  Example: "Spells you play cost [1] less" → {{"effect": "reduce_cost", "trigger": "cost_modifier",
  "amount": 1, "target_filter": {{"is_spell": true}}}}.
  NOTE: the engine currently applies `reduce_cost` only as a flat discount to the card that owns
  the effect; auras that reduce OTHER cards' costs are not dispatched yet, but emitting them is
  still correct — also add `suggested_vocab` tag "aura:reduce_cost" so we track coverage.

Semantic disambiguation — NEVER force-fit an approximation that changes meaning:
A populated-but-wrong spec is WORSE than an honest flag: it passes validation and then
runs incorrectly. For each pattern below, if the only available vocab would change the
card's meaning, set `needs_review: true` + `suggested_vocab` for that clause and do NOT
emit the approximate effect.
- "if there is a READY ENEMY unit here" is NOT `you_have_n_or_more_units_here` (that
  counts YOUR units and ignores ready/enemy). No engine condition matches →
  needs_review, suggested_vocab "cond:ready_enemy_unit_here".
- "if the ENEMY unit is alone" is DIFFERENT from "if I am alone". `this_is_alone`
  evaluates the SOURCE's OWN side only. Use `this_is_alone` ONLY for "if I am alone /
  if this is the only unit here (on my side)". For an enemy-alone check →
  needs_review, suggested_vocab "cond:enemy_is_alone".
- "double all DAMAGE dealt to it" / "damage it would take" is a damage-TAKEN modifier,
  NOT `double_might` (which doubles the unit's Might — a buff). No verb exists →
  needs_review, suggested_vocab "effect:double_incoming_damage". Never emit
  `double_might` for a damage-taken effect.
- "deals its Might SPLIT AMONG" / "divided among" targets ≠ the full amount to EACH
  target (`all_enemy_units_here` hits each for the full amount). No split semantics
  exist → needs_review, suggested_vocab "effect:split_damage".
- "when this LEAVES THE BOARD" / "leaves play" is BROADER than `on_death` (recall and
  bounce-to-hand also trigger it). Use `on_death` ONLY for "when I die / when this is
  killed / DEATHKNELL". For leaves-the-board, EMIT the effect with
  `trigger: "leaves_board"` (now a supported trigger) — do NOT flag it and do NOT
  fold it into `on_death`.
- A GATE you cannot represent: if an effect is conditional ("if you control a facedown
  card", "if it had 3 [might] or less") and no supported condition type matches, do
  NOT emit the effect UNGATED — that would run it unconditionally (e.g. a free draw
  every turn). Flag it → needs_review, suggested_vocab "cond:<name>" (e.g.
  "cond:controller_has_facedown").
- Narrowing "your units" / "friendly units" (which mean ANYWHERE) down to
  `all_friendly_units_here` changes scope — see rule 5: flag with
  target:all_friendly_units_anywhere, do not substitute the here-scoped target.
Standing rule: if the closest available condition / verb / target INVERTS a side,
turns "split" into "each", narrows "anywhere" into "here", drops a gate, or maps a
damage-taken modifier onto a Might buff, it is MEANING-CHANGING — do not use it. Flag
that clause instead. A wrong populated parse is worse than an honest flag.

Guidance:
- A "+N might this turn" buff → grant_temporary_might (amount N). A permanent "+N might" (no "this turn") → grant_might.
- "Draw N" → draw_cards (count N). "Deal N damage to an enemy" → deal_damage (amount N, target enemy_unit/opponent).
- "When I conquer/hold ..." → trigger on_conquer/on_hold. "When I die ..." (DEATHKNELL) → trigger on_death.
  "When I attack ..." → on_attack. "When I move ..." → on_move (now supported).
  "When you play another friendly unit ..." → on_friendly_unit_played. "When a friendly unit dies ..." →
  on_friendly_unit_death. "When you play a spell ..." → on_play_spell. "When I win combat ..." → on_win_combat.
- "Counter a spell that costs no more than X ..." → counter_spell with max_energy/max_power params.
- Gear `effect` that says "EQUIP [cost]: Attach ..." → emit the EQUIP keyword; the `effect_equipped` text describes
  what the unit gains while equipped (parse it as the gear's effects with the appropriate trigger).
- If a card's text references a mechanic with NO matching verb/condition, emit an empty `effects` list and set
  "needs_review": true with a short "review_reason", AND add a "suggested_vocab" list naming the new effect verb(s)
  or condition type(s) you would need — snake_case, concise, reusable (e.g. "bonus_damage", "take_control",
  "double_might", "cost_reduction", "cond:target_might_at_most", "filter:has_keyword"). Reuse the same name across
  cards that need the same mechanic so the aggregate is meaningful.
- Reproduce the printed timing keyword (REACTION/ACTION) in `keywords`, and also set `timing` accordingly on the effect.
- Be faithful and conservative. Do not invent effects the text doesn't state.

Few-shot examples (from spot-check feedback — follow these patterns):

1. REPEAT keyword — emit it BARE (no number). The engine defaults the REPEAT
   cost to the spell's printed `cost_energy`. Only emit "REPEAT N" if the rules
   text explicitly states a DIFFERENT cost from the spell's base.
   Text: "REPEAT [2] (You may pay the additional cost to repeat this spell's
   effect.) Ready a unit."  (spell cost_energy is 2)
   → keywords: ["REPEAT"], effects: [{{"effect":"ready_unit","trigger":"on_cast",
     "target":"chosen_unit"}}]
   (Do NOT emit "REPEAT 2" here — the cost equals the spell's base.)

2. EQUIP cost — "EQUIP [fury]" means "pay 1 [fury] to attach", i.e. cost 1, not
   2. The bracketed cost is ONE resource symbol unless a number precedes it.
   Text: "EQUIP [fury] ([fury]: Attach this to a unit you control.)"
   → keywords: ["EQUIP 1"]
   ("EQUIP [2] [fury]" → "EQUIP 2", but the bare "EQUIP [fury]" is 1.)

3. `ADD [rune]` / `ADD [power]` is NOT `add_rune`. `add_rune` puts cards into
   the rune deck. "ADD" in a rune-tap ability means "tap to add 1 power of any
   domain to your pool" — a `gain_power` verb the engine doesn't have yet.
   Until it exists: leave `effects: []`, set `needs_review: true`, and add the
   tag `effect:gain_power_any_domain` to `suggested_vocab`. Do NOT emit
   `add_rune` for these.
   Text: "[tap] REACTION — ADD [rune]. Use only to play spells." → flag.

4. "Choose one — …" multi-modal effects. The engine doesn't dispatch a
   mode-choice yet, so do NOT flatten the branches into stacked effects (that
   would run both). Leave `effects: []`, set `needs_review: true`, and add the
   tag `effect:mode_choice` to `suggested_vocab`.

5. "here" scoping. If the text says "here" / "a unit here" / "an enemy here" /
   "units here", the resolution location IS this battlefield — use
   `friendly_unit`/`enemy_unit`/`all_friendly_units_here`/`all_enemy_units_here`
   (those already mean "at the current battlefield"). When the text DOES say
   "here", emitting those targets is correct and required — that is a normal
   parse, not a reason to flag the card. Do NOT add `here` scope to a target
   if the text doesn't say "here".
   When the text says "at a battlefield" / "to a unit" with no "here", the
   target is a CHOSEN unit (any location) → use `chosen_unit`.
   When the text says "friendly units" / "your units" with NO location qualifier
   (means "everywhere", not just here), there is no engine target for that yet —
   leave `effects: []`, set `needs_review: true`, and tag suggested_vocab
   `target:all_friendly_units_anywhere`. Do NOT emit `all_friendly_units_here`
   as a substitute (it's a strict subset).
   Examples:
   - "Deal 2 to an enemy here" → {{"target":"enemy_unit","amount":2}}
   - "Deal 3 to a unit." (no location) → {{"target":"chosen_unit","amount":3}}
   - "Give friendly units +5 might this turn" → flag (no "anywhere" target yet).

6. HIDDEN keyword — emit as a keyword. Engine support for the facedown alternate
   cost is deferred; do NOT invent verbs for the hidden-play behavior.
   Text: "HIDDEN (Hide now for [rune] to react with later for [0].) ACTION …"
   → keywords: ["HIDDEN","ACTION"]  (then the body's effects as usual)

7. Canonical tokens (Recruit 1 might, Sprite 3 might TEMPORARY, Gold 1 might
   TEMPORARY) have FIXED stats. For `play_token` just name the token; do NOT
   redundantly emit might/keyword fields on the spec. Omitting the redundant
   stats is a STYLE rule, never a reason to refuse the parse: if the printed
   token matches a canonical token, emit `play_token` with the `token_name`
   (plus `ready: true` only when the text says "a ready ... token").
   Text: "[1], [tap]: Play a 1 [might] Recruit unit token."
   → effects: [{{"effect":"play_token","trigger":"activated","timing":"action",
     "cost":{{"energy":1,"tap":true}},"token_name":"Recruit"}}]
   Text: "When you play this, play a ready 3 [might] Sprite unit token with
   TEMPORARY to your base."
   → effects: [{{"effect":"play_token","trigger":"on_play",
     "token_name":"Sprite","ready":true}}]
   (token_name/ready are flat fields on the effect object, never nested.)

8. Kicker / additional cost — when text says "You may pay [X] as an additional
   cost. If you do, …", put `additional_cost` + `condition: kicker_paid` on the
   gated effect (see "Optional additional cost / kicker" section above).
   Text: "You may pay [fury] as an additional cost to play me. When you
   play me, if you paid the additional cost, deal 2 to a unit at a battlefield."
   → effects: [{{"effect":"deal_damage","trigger":"on_play","amount":2,
     "target":"enemy_unit","condition":{{"type":"kicker_paid"}},
     "additional_cost":{{"power":1}}}}]
   (Remember: `[fury]` is a power symbol → `power`; a bare `[1]` would be `energy`.)

9. PARTIAL parses are better than empty ones. When a card has several
   independent abilities and only SOME need unsupported mechanics, parse the
   supported abilities normally and flag ONLY the unsupported remainder
   (needs_review: true + suggested_vocab tags). Do not return an empty
   `effects` list when part of the card is cleanly parseable.
   Text: "When you play this, draw 1. [1] [calm], [tap], Kill this: Draw 1."
   → effects: [{{"effect":"draw_cards","trigger":"on_play","count":1}}],
     needs_review: true, suggested_vocab: ["cost:kill_self"]
   (the on_play draw is supported; the kill-this activated cost is not)
   Text: "Deal 5 to a unit. When you conquer, you may discard 1 to return
   this from your trash to your hand."
   → effects: [{{"effect":"deal_damage","trigger":"on_cast","amount":5,
     "target":"chosen_unit"}}],
     needs_review: true, suggested_vocab: ["cost_gated_trigger",
     "effect:return_self_from_trash"]
   (the damage is supported; a cost-gated triggered ability is not)

10. MULTI-CLAUSE: parse the supported clause AND flag the rest — never drop the
    back half. "Kill … Then/If … do Y" and "When I …; When I …" are TWO clauses.
    Text: "Kill a unit at a battlefield with 2 [might] or less. If it was an enemy
    unit, play a Gold gear token exhausted. If it was a friendly unit, play two Gold
    gear tokens exhausted." (Blood Money)
    → effects: [{{"effect":"kill_unit","trigger":"on_cast","timing":"action",
      "target":"chosen_unit","target_filter":{{"might_at_most":2}}}}],
      needs_review: true,
      suggested_vocab: ["effect:mode_choice","cond:killed_was_enemy"]
    (the kill is supported; the enemy-vs-friendly branch that follows is NOT — flag
    it, do NOT drop it and do NOT invent it.)

11. MULTI-CLAUSE with "Then": the second sentence is a real clause, not flavor.
    Text: "Kill a unit at a battlefield. Then, if it had 3 [might] or less, you may
    play this from your trash for [rune]." (Death from Below)
    → effects: [{{"effect":"kill_unit","trigger":"on_cast","target":"chosen_unit"}}],
      needs_review: true,
      suggested_vocab: ["effect:play_self_from_trash","cond:killed_might_at_most"]
    (parse clause 1; flag the conditional replay-from-trash — do not silently drop it.)

12. TWO SEPARATE ABILITIES: emit the one you support, flag the other whole ability.
    Text: "You may pay [calm] as an additional cost to play me. When you play me, if
    you paid the additional cost, STUN an enemy unit. When I hold, the next time you
    play a unit this turn, ready it and BUFF it." (Nami Headstrong)
    → effects: [{{"effect":"stun_unit","trigger":"on_play","target":"enemy_unit",
      "condition":{{"type":"kicker_paid"}},"additional_cost":{{"power":1}}}}],
      needs_review: true,
      suggested_vocab: ["effect:delayed_next_unit_played"]
    (the kicker STUN is emitted; the ENTIRE second "When I hold …" ability is flagged,
    not dropped. [calm] is a power symbol → additional_cost power:1.)

STEP 3 — newly-supported mechanics (EMIT these now; older guidance said to flag them):

13. LEAVES-THE-BOARD effect — emit with trigger "leaves_board" (fires on death,
    recall, bounce, banish). Still flag any genuinely-unsupported sibling clause.
    Text: "When this leaves the board, draw 1 and channel 1 rune exhausted.
    [Chaos], [Tap]: Kill this." (Treasure Trove)
    → effects: [{{"effect":"draw_cards","trigger":"leaves_board","count":1}},
      {{"effect":"channel_rune","trigger":"leaves_board","amount":1,"exhausted":true}}],
      needs_review: true, suggested_vocab: ["cost:kill_self"]
    (the leaves-board draw + channel are now emitted, NOT flagged; only the
    "[Chaos],[Tap]: Kill this" sacrifice-cost activated ability stays flagged.)

14. BANISH ALL FROM A ZONE — use `banish_card` with `scope:"all"` and a card-type
    `target_filter` ("all UNITS from your trash" → is_unit).
    Text: "When you play this, banish all units from your trash. [tap]: Play a unit
    banished with this." (Cursed Sarcophagus)
    → effects: [{{"effect":"banish_card","trigger":"on_play","target":"self",
      "from":"trash","scope":"all","target_filter":{{"is_unit":true}}}}],
      needs_review: true, suggested_vocab: ["effect:play_banished_by_source"]
    (banish-all is now emitted with scope+filter; only the tap-replay stays flagged.)

15. "a MIGHTY unit you PLAY" gates on the TRIGGERING unit, not the source — use
    condition `triggering_unit_is_mighty` on an on_friendly_unit_played trigger.
    (Contrast `this_is_mighty`, which tests the SOURCE card's own might.)
    Text: "When you play a MIGHTY unit, you may exhaust me to channel 1 rune
    exhausted." (Volibear)
    → effects: [{{"effect":"channel_rune","trigger":"on_friendly_unit_played",
      "amount":1,"exhausted":true,"condition":{{"type":"triggering_unit_is_mighty"}},
      "cost":{{"tap":true}}}}]
    (the optional exhaust-me is a `cost` on the triggered effect; the engine now pays it.)

16. GEAR ENERGY-COST filter + EXHAUSTED-unit filter are now expressible:
    "a gear with Energy cost no more than [1]" → target_filter {{"energy_at_most":1}}
    on `kill_gear`; "an exhausted friendly unit" → target_filter {{"is_exhausted":true}}.
    Text: "Move an exhausted friendly unit from a battlefield to its base."
    → {{"effect":"move_unit","target":"friendly_unit","target_filter":{{"is_exhausted":true}}}}
    (single "a unit" → move_unit, not move_units_to_base which moves ALL.)

17. `chosen_unit` = "player picks a unit", EITHER side (the engine no longer forces it
    to your own side). Use it for an unrestricted "a unit" / "a unit at a battlefield"
    with no friendly/enemy word. Use `enemy_unit`/`friendly_unit` only when the text
    says so. (Removal via chosen_unit now correctly targets the opponent.)

STEP 4 — Vendetta mechanics:

18. EMPOWER / EMPOWERED (now supported — EMIT, do NOT flag).
    "EMPOWER [cost]" is an activated ability that gives the source the empowered
    status. Emit `empower_self` with `trigger:"activated"` and the cost. The cost
    inside the parentheses is the same "[N]=energy, [domain]=1 power pip, repeated
    pip = count" rule as everywhere else.
    "EMPOWERED <X>" is a DEPENDENT ability that applies only while empowered —
    emit X as a `passive` effect with `condition:{{"type":"this_is_empowered"}}`,
    `target:"self"`. Might → grant_might; a keyword → give_keyword.
    "When ..., empower me" (a trigger, not a cost) → `empower_self` on that trigger.
    "disempower a unit" (instruction or cost) → `disempower` with the right target.
    Text: "EMPOWER [2] [Fury] ([2][Fury]: Empower me. Use only if not Empowered.)
    EMPOWERED[>] I have ASSAULT 3. EMPOWERED I have +1 [might]."
    → effects: [
        {{"effect":"empower_self","trigger":"activated","cost":{{"energy":2,"power":1}}}},
        {{"effect":"give_keyword","trigger":"passive","target":"self",
          "condition":{{"type":"this_is_empowered"}},"keyword":"ASSAULT 3"}},
        {{"effect":"grant_might","trigger":"passive","target":"self","amount":1,
          "condition":{{"type":"this_is_empowered"}}}}]
    Also list "EMPOWER"/"EMPOWERED" in `keywords` when the card prints them.
    An EMPOWERED clause that MODIFIES another ability ("deal 2 instead if I'm
    Empowered", "they have +2 instead") is NOT yet expressible — parse the base
    ability, then flag the empowered-modifier clause (suggested_vocab
    "effect:empowered_modifier"); do not drop it.

19. FLOW and BURN are NOT supported yet. FLOW (an alternate cost to play a spell
    from the trash, then banish it) → keep the on-cast body if it's otherwise
    parseable, set needs_review, suggested_vocab ["keyword:flow"]. BURN X (put X
    cards from top of deck into trash) → needs_review, suggested_vocab
    ["effect:burn"]. Do NOT invent verbs for these.

Output format: a JSON array, one object per input card, in the same order:
[{{"name": "<card name>", "keywords": [...], "effects": [...], "needs_review": false}}, ...]
Respond with ONLY the JSON array — no prose, no markdown fences."""


def build_user_message(cards: list[dict]) -> str:
    lines = []
    for c in cards:
        lines.append(json.dumps({
            "name": c.get("name"),
            "category": c.get("category"),
            "domain": c.get("domain"),
            "sub_type": c.get("sub_type"),
            "cost_energy": c.get("cost_energy"),
            "cost_power": c.get("cost_power"),
            "cost_power_domain": c.get("cost_power_domain"),
            "might": c.get("might"),
            "effect": c.get("effect"),
            "effect_equipped": c.get("effect_equipped"),
        }, ensure_ascii=False))
    return "Parse these cards:\n" + "\n".join(lines)


def parse_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array found in response")
    return json.loads(text[start:end + 1])


def validate_card_result(entry: dict) -> list[str]:
    """Return a list of problems (empty = OK). Validated against engine_vocab."""
    problems = []
    for eff in entry.get("effects") or []:
        verb = eff.get("effect")
        if verb not in EFFECT_REGISTRY and verb not in NON_HANDLER_VERBS:
            problems.append(f"unknown effect verb {verb!r}")
        trig = eff.get("trigger", "on_play")
        if trig not in KNOWN_TRIGGERS:
            problems.append(f"unknown trigger {trig!r}")
        cond = eff.get("condition")
        if isinstance(cond, dict) and cond.get("type") not in KNOWN_CONDITIONS:
            problems.append(f"unknown condition type {cond.get('type')!r}")
        tf = eff.get("target_filter")
        if isinstance(tf, dict):
            bad = [k for k in tf if k not in KNOWN_FILTER_KEYS]
            if bad:
                problems.append(f"unknown target_filter key(s) {bad!r}")
        amt_src = eff.get("amount_source")
        if amt_src is not None and amt_src not in KNOWN_AMOUNT_SOURCES:
            problems.append(f"unknown amount_source {amt_src!r}")
        cost = eff.get("cost")
        if isinstance(cost, dict) and trig == "activated":
            bad = [k for k in cost if k not in KNOWN_ACTIVATED_COST_KEYS]
            if bad:
                problems.append(f"unknown activated cost key(s) {bad!r}")
        ac = eff.get("additional_cost")
        if isinstance(ac, dict):
            bad = [k for k in ac if k not in KNOWN_ADDITIONAL_COST_KEYS]
            if bad:
                problems.append(f"unknown additional_cost key(s) {bad!r}")
    return problems


# Reminder text (parentheses) restates rules and never adds a clause — strip it
# before counting. Clause boundaries: sentence separators + bullet points.
_REMINDER_PARENS = re.compile(r"\([^)]*\)")
_SENTENCE_SPLIT = re.compile(r"[.;]\s+|\s*•\s*")
# Words that CHAIN an additional executable clause onto a prior effect.
_CLAUSE_CONTINUATIONS = re.compile(r"\b(?:then|also|if you do)\b", re.IGNORECASE)


def check_completeness(card: dict, entry: dict) -> str | None:
    """Safety net for DISEASE A (dropped clauses): flag cards whose emitted effect
    count looks too low for the number of clauses in the printed text. Returns a
    review reason, or None if the parse looks complete enough.

    Heuristic ONLY — deliberately biased toward flagging: a false flag just adds a
    card to the human review queue, whereas a missed drop ships a half-parsed card.
    Parenthetical reminder text is stripped first so it can't inflate the count.
    Cards that emitted zero effects are skipped (they're empty/flagged by other
    paths already); the caller also skips cards the model itself flagged.
    """
    text = " ".join(t for t in (card.get("effect"), card.get("effect_equipped")) if t)
    if not text:
        return None
    text = _REMINDER_PARENS.sub(" ", text)
    n_effects = len(entry.get("effects") or [])
    if n_effects == 0:
        return None
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    signals = len(sentences) + len(_CLAUSE_CONTINUATIONS.findall(text))
    if signals > n_effects:
        return (f"possible dropped clause (~{signals} text clauses vs "
                f"{n_effects} effect(s) emitted)")
    return None


def call_api(client, system_prompt: str, cards: list[dict], max_retries: int = 2):
    user = build_user_message(cards)
    last_err = None
    for attempt in range(max_retries + 1):
        msg = user if attempt == 0 else (
            user + f"\n\nYour previous reply could not be parsed ({last_err}). "
            "Reply with ONLY a valid JSON array."
        )
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user if attempt == 0 else msg}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            arr = parse_json_array(text)
            return arr, resp.usage
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
    raise RuntimeError(f"failed to parse model output after retries: {last_err}")


def read_review_names() -> list[str]:
    """Unique card names flagged in review_needed.txt (format: '<name>\\t<reason>'),
    in first-seen order. Used by --retry-review to reprocess only those cards."""
    if not REVIEW_PATH.exists():
        return []
    seen: dict[str, None] = {}
    for line in REVIEW_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        name = line.split("\t", 1)[0].strip()
        if name:
            seen.setdefault(name, None)
    return list(seen.keys())


def select_cards(all_cards: list[dict], args) -> list[dict]:
    cards = all_cards
    if getattr(args, "names", None):
        wanted = {n.strip().lower() for n in args.names.split(";") if n.strip()}
        cards = [c for c in cards if c.get("name", "").lower() in wanted]
    if getattr(args, "retry_review", False):
        names = set(read_review_names())
        cards = [c for c in cards if c.get("name") in names]
    if args.set:
        cards = [c for c in cards if c.get("set") == args.set]
    if args.only_empty:
        cards = [c for c in cards if not c.get("effects")]
    if args.sample and len(cards) > args.sample:
        stride = len(cards) / args.sample
        cards = [cards[int(i * stride)] for i in range(args.sample)]
    if args.limit:
        cards = cards[: args.limit]
    return cards


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", help="Only cards from this set (e.g. 'Proving Grounds')")
    ap.add_argument("--names", help="Only these card names, ';'-separated (targeted re-parse)")
    ap.add_argument("--only-empty", action="store_true", help="Only cards lacking structured effects")
    ap.add_argument("--retry-review", action="store_true",
                    help="Only cards currently flagged in review_needed.txt (re-run after a vocab/prompt update)")
    ap.add_argument("--limit", type=int, help="Cap number of cards processed (first N)")
    ap.add_argument("--sample", type=int, help="Evenly sample N cards across the selection (variety across sets)")
    ap.add_argument("--dry-run", action="store_true", help="Build prompts but make no API calls")
    args = ap.parse_args()

    all_cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in all_cards}
    targets = select_cards(all_cards, args)
    print(f"Selected {len(targets)} cards (of {len(all_cards)}).")

    system_prompt = build_system_prompt()

    if args.dry_run:
        print("--- DRY RUN: system prompt length:", len(system_prompt), "chars ---")
        if targets:
            print("--- first batch user message preview ---")
            print(build_user_message(targets[:BATCH_SIZE])[:1500])
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set. Export it and re-run.", file=sys.stderr)
        return 2
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic SDK not installed. Run: uv add anthropic", file=sys.stderr)
        return 2

    client = anthropic.Anthropic()

    # Backups. The original pre-parse backup (if any) is preserved one-time as
    # .json.preparse.bak so it's never lost; .json.bak is then refreshed to the
    # current state as the pre-this-run snapshot.
    bak = CARDS_PATH.with_suffix(".json.bak")
    preparse = CARDS_PATH.with_suffix(".json.preparse.bak")
    if bak.exists() and not preparse.exists():
        shutil.copy(bak, preparse)
        print(f"Preserved original backup to {preparse}")
    shutil.copy(CARDS_PATH, bak)
    print(f"Snapshot saved to {bak}")

    # review_needed.txt is rewritten with this run's flags at the end. On a full
    # run it is reset; on a targeted --names run the entries for cards NOT in
    # this run are preserved (a 5-card re-parse must not wipe the whole list).
    preserved_review: list[str] = []
    if getattr(args, "names", None) and REVIEW_PATH.exists():
        target_names = {c.get("name") for c in targets}
        preserved_review = [
            ln for ln in REVIEW_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip() and ln.split("\t", 1)[0] not in target_names
        ]
    REVIEW_PATH.write_text("", encoding="utf-8")

    review_lines: list[str] = []
    from collections import Counter
    suggested_vocab: Counter = Counter()
    total_in = total_out = total_cache_read = 0
    processed = 0

    for i in range(0, len(targets), BATCH_SIZE):
        batch = targets[i:i + BATCH_SIZE]
        try:
            results, usage = call_api(client, system_prompt, batch)
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i // BATCH_SIZE} FAILED: {e}", file=sys.stderr)
            continue
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0

        for entry in results:
            name = entry.get("name")
            card = by_name.get(name)
            if card is None:
                review_lines.append(f"{name}\tNOT FOUND in all_cards")
                continue
            effects = entry.get("effects") or []
            # Strip stray review markers the model sometimes leaves inside effects.
            for e in effects:
                e.pop("needs_review", None)
                e.pop("review_reason", None)
            problems = validate_card_result(entry)
            if entry.get("needs_review"):
                review_lines.append(f"{name}\t{entry.get('review_reason', 'model flagged')}")
            for v in entry.get("suggested_vocab") or []:
                suggested_vocab[str(v)] += 1
            if problems:
                review_lines.append(f"{name}\t{'; '.join(problems)}")
            # DISEASE-A safety net: if the model didn't flag it and it validated,
            # check the emitted clause count against the printed text. A soft flag
            # (keeps the partial parse; surfaces a likely dropped clause for review).
            elif not entry.get("needs_review"):
                incomplete = check_completeness(card, entry)
                if incomplete:
                    review_lines.append(f"{name}\t{incomplete}")
            # Persist the validated effects the model emitted, even when the card
            # is still flagged for review. `needs_review` now marks a PARTIAL parse:
            # the supported abilities are parsed and kept, while the unsupported
            # remainder is logged (review_needed.txt + suggested_vocab) to revisit
            # when the missing verb lands. Previously a flag wiped ALL effects,
            # which discarded cleanly-parsed abilities on any card that also flagged
            # one unsupported ability (e.g. Poro Snax's on_play draw, SMDR's deal 5).
            # Only a structural validation failure (`problems`) forces empty effects,
            # so we never persist a spec the engine can't execute. Keywords are
            # always safe to keep.
            card["keywords"] = entry.get("keywords") or []
            card["effects"] = [] if problems else effects
            processed += 1

        # Incremental save after each batch (resume-friendly).
        CARDS_PATH.write_text(json.dumps(all_cards, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        print(f"  batch {i // BATCH_SIZE}: {len(batch)} cards "
              f"(in={usage.input_tokens} out={usage.output_tokens} "
              f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)})")

    all_review = preserved_review + review_lines
    if all_review:
        REVIEW_PATH.write_text("\n".join(all_review) + "\n", encoding="utf-8")
        print(f"Flagged {len(review_lines)} entries to {REVIEW_PATH} "
              f"({len(preserved_review)} preserved from previous runs)")
    if suggested_vocab:
        if getattr(args, "names", None):
            # Targeted run: don't clobber the corpus-wide priority queue.
            print("Suggested vocab from this targeted run (file NOT rewritten):")
            for name, count in suggested_vocab.most_common():
                print(f"  {count}\t{name}")
        else:
            vocab_path = Path(__file__).resolve().parent / "suggested_vocab.txt"
            lines = [f"{count}\t{name}" for name, count in suggested_vocab.most_common()]
            vocab_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Aggregated {len(suggested_vocab)} distinct suggested vocab items to {vocab_path}")

    print(f"\nDone. Enriched {processed} cards. "
          f"Tokens: in={total_in} out={total_out} cache_read={total_cache_read}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
