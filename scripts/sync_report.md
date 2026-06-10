# Sync report — Phase A + B1/B2 reinforcement (round 2)

## Round 1 (Phase A, initial sync)
- `--only-empty` on 488 cards with the synced (not yet reinforced) prompt.
- Cards with `effects[]`: **275 → 344 (+69)**, 0 regressions.
- Token usage: in=70,656 out=74,879 cache_read=165,216.

## Round 2 (this run — reinforced prompt + B1/B2 engine, after clearing 18)
- Pre-run prep: cleared `effects[]` on the 18 spot-check-flagged cards (7 BAD +
  11 MINOR) so they'd be re-parsed alongside the existing empties.
- Pre-run baseline: 326 with effects (344 − 18 cleared).
- `--only-empty` on 437 cards.
- After: **326 → 354 with effects (+28), 0 regressions** vs the pre-run baseline.
- Net vs pre-A round-1 baseline (275): +79.
- Token usage: in=63,395 out=56,466 cache_read=260,881 (heavy cache hit).
- `review_needed.txt`: 452 entries / 368 unique → **387 entries / 358 unique**.

## Recovery on the 18 cleared spot-check cards

**7/18 came back populated** (the parser now produces a real spec):
- Blast Corps Cadet — B1 `additional_cost`+`kicker_paid` correctly emitted.
- Trifarian War Camp — `grant_might` (cleaner than the old `buff_unit`),
  no stale `duration: permanent`.
- Windswept Hillock — GANKING no longer (incorrectly) on the battlefield's own
  keywords.
- Yasuo Remorseful — identical to round 1 (was MINOR for an engine concern,
  not a parse error).
- Recurve Bow — **`EQUIP 1` (was `EQUIP 2`)**.
- Viktor Herald of the Arcane — clean `play_token` spec (no redundant
  might/keyword), matching the few-shot guidance.
- Upstage Comedy — bare `REPEAT` keyword; engine defaults the cost to
  `card.cost_energy` (B1.5 engine change).

**11/18 stayed empty** — split between two categories:
- *Acceptably flagged* (the prompt is correctly refusing wrong parses for
  mechanics the engine doesn't support): Kai'Sa Daughter of the Void (needs
  `gain_power` verb), Shurelya's Requiem (complex equipped aura), Danger Zone
  ("give your Mechs" / no anywhere-all-friendly target), Grand Strategem (same),
  Rocket Barrage ("choose one" not engine-supported), Serrated Dirk (equipped
  effect is pure keyword grant — empty `effects[]` may be correct).
- *Regression suspects* — round 1 had a populated parse, round 2 doesn't.
  The reinforced prompt may be over-conservative for these:
  Sprite Fountain, Navori Fighting Pit, Poro Snax, Super Mega Death Rocket!,
  Sprite Queen. Worth a permissiveness pass in the prompt for `play_token`
  (canonical tokens), `return_from_trash` cost, and `buff_unit` "here" cases.

## What's still blocked (top buckets, by frequency)

From the regenerated `review_needed.txt` and `suggested_vocab.txt`:
- `channel_rune` / `channel_rune_exhausted` ×6/×5
- `play_token_exhausted` ×6
- `bonus_damage` ×5
- `cond:excess_damage_at_least` ×5
- `cost:kill_self` (Poro Snax family) ×4
- `aura:reduce_cost` ×3
- `mutual_combat_damage` ×3
- `effect:gain_power_any_domain` (Kai'Sa family) — flagged via prompt
- `effect:mode_choice` (Rocket Barrage family) — flagged via prompt
- `target:all_friendly_units_anywhere` (Grand Strategem family) — flagged via prompt

These are the Phase C fat head.

## Backups
- `all_cards.json.preparse.bak` — original pre-parse backup (preserved).
- `all_cards.json.bak` — pre-round-2 snapshot (326 with effects).

## Verification
- `uv run pytest -q` → 54 passed.
- Registry loads all 354 cleanly; per-handler resilience guard in
  `_resolve_card_effects` keeps malformed specs from aborting a match.
