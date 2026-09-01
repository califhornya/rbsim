<!-- Generated/maintained by hand as the engine mechanics burn-down chart.
     One row per game DYNAMIC (not per card). Source of truth: Riftbound Core
     Rules v1.2.pdf. Status legend:
       DONE     — implemented AND covered by a rules-based test
       PARTIAL  — implemented but a rule nuance is unverified or known-incomplete
       GAP      — the mechanic is not implemented
       WRONG    — implemented incorrectly (a landmine for self-play) -> fix or downgrade
     This is the real Stage-0 gate: AlphaZero learns to win the SIMULATION, so every
     dynamic must be correct. Card coverage (which cards are authored) is a separate,
     deferred concern — an INERT card is a safe blank; a WRONG mechanic is an exploit. -->

# Riftbound Engine — Mechanics Completeness & Correctness

Burn-down of every game **dynamic**. Goal: every row `DONE` or explicitly
`DEFERRED` (with a rule-cited reason) → then the simulator is trustworthy enough
for AlphaZero. Card authoring (the long tail) is **not** tracked here.

## Keyword glossary (Core Rules §730)

| # | keyword | § | status | engine location | test | note / rule nuance to verify |
|---|---------|---|--------|-----------------|------|------------------------------|
| 731 | Accelerate | §731 | DONE | `loop.py:1312` | `test_accelerate.py` | OPTIONAL cost [1] + 1 domain-power → enter ready. Now routed through `decide_optional` (§731.2 "may"; default yes preserves prior play). Single-domain match is enforced; **caveat**: for a domainless/multi-domain unit the [A] power isn't charged (can_pay/pay skip power when domain=None) — minor undercharge, see the [A]-power row below. |
| 732 | Action | §732 | PARTIAL | `loop.py:1982`, `legality.py:201` | — | permission to play/activate during showdowns on any turn. Verify units-with-Action still respect play-location limits (§732.3). Needs a dedicated assertion. |
| 733 | Assault | §733 | DONE | `combat.py:171` | `test_combat_keywords.py` | +X might while attacker only; bare = 1 (§733.1.b.3). Combat bonus + lethality asserted. |
| 734 | Deathknell | §734 | DONE | `loop.py:_route_combat_deaths` (`on_death`) | `test_deathknell.py` | "when I die, [Effect]"; fires on true death, correctly **suppressed** when death is replaced by recall (§734.1.d.1) — replacement `continue`s before `truly_dead`. |
| 736 | Ganking | §736 | PARTIAL | `legality.py:112`, `loop.py:1539` | — | MOVE permission (bf→bf directly), NOT a play permission. Implemented on the move path. Needs `test_ganking.py`. **Also check parser mislabels** (SFD-093 Dauntless Vanguard's printed text is about *playing* to an enemy bf, not moving — possible wrong tag). |
| 737 | Hidden | §737 | DONE | `loop.py` HIDE/hidden path | `test_hidden.py` | facedown hide, play for [0] at reaction speed, removal on loss of control. Nuances (champion-zone hide / from-hidden targeting) parked in KNOWN_ISSUES #23. |
| 738 | Legion | §738 | DONE | cond `you_already_played_another_card_this_turn` + `_cost_reduction` | `test_legion.py` | cost-reducing Legion (Noxus Hopeful "I cost [2] less") now applies ONCE — fixed a double-count (hardcoded legion path + generic `_cost_reduction` both fired → cost 0). One condition covers both §738.1.c forms (both mean "played another card this turn"). |
| 739 | Reaction | §739 | DONE | `loop.py:1905`, `legality.py:179` | `test_hidden.py`/reaction paths | reaction-speed spell play. (On non-spells REACTION is inert by design — see keyword-edit audit.) |
| 740 | Shield | §740 | DONE | `combat.py:171` | `test_combat_keywords.py` | +X might while defender only; bare = 1. Combat bonus + survival asserted. |
| 741 | Tank | §741 | DONE | `combat.py:96` | `test_combat_keywords.py` | assigned lethal first (§460.2.c) — order + lethal-absorption asserted. Tank+Backline conflict resolved deterministically as Tank (documented simplification vs "controller chooses"). |
| 742 | Temporary | §742 | DONE | `loop.py:284-300` | `test_temporary.py` | kills TEMPORARY units AND unattached TEMPORARY gear at base at the controller's beginning phase; attached gear rides its host (Spinning Axe "if unattached"). Note: moves direct-to-trash (no death trigger) — acceptable, no TEMPORARY permanent has a Deathknell. |
| 743 | Vision | §743 | PARTIAL | parser → `predict` | — | "look at top card, may recycle it" (§743.1.b). Verify `predict`/`scry` semantics match (recycle = to bottom/shuffle per rules) and multi-instance behavior (§743.2). |
| 744 | Equip | §744 | DONE | `loop.py:1739`, `combat.py:46` | `test_equip_deflect.py` | attach to a controlled unit (cost from card cost fields); attached gear grants might via its `grant_might` effect (verified +3). |
| 745 | Quick-Draw | §745 | PARTIAL | (gear play path) | — | grants Reaction inherently + attach-on-play at reaction timing (§745.1.d). Verify gear can actually be played at reaction speed and auto-attaches. Needs a test. |
| 746 | Repeat | §746 | DONE | additional-cost path | `test_repeat_cost.py` | optional additional cost → execute spell effect one extra time. |
| 747 | Weaponmaster | §747 | PARTIAL | `loop.py:1308-1319` | — | on-play: choose controlled Equipment, pay its Equip cost reduced by [A], attach (§747.1.c). Verify the [A] discount and failure fallbacks (§747.1.c.5). Needs a test. |
| — | Deflect | §408/§809 | DONE | `_deflect_surcharge` (`loop.py:778`) | `test_equip_deflect.py` | a spell targeting an opponent's battlefield is surcharged by the max DEFLECT among enemy units there; friendly-targeting spells are not surcharged; `ignore_deflect_here` battlefields waive it. (Ability-targeting surcharge still TODO — spells covered.) |

## Core systems

| system | § | status | location | note |
|--------|---|--------|----------|------|
| Turn / phase structure | §300s | DONE | `loop.py` `_phase_*` | resumable loop; golden + invariants cover it. |
| Resources (energy/power/runes/6 domains) | §200s | DONE | `player.py`, `loop.py` | pay/afford paths tested (`test_rune_system.py`). |
| **Earmarked resources** | (Diana Scorn / Ornn) | **GAP** | — | energy usable only in showdowns / power only for gear. Needs a restricted-pool checked per spend site. The one **meta** gap. DEFERRED.md tracks it. |
| Combat + damage-assignment order | §437/§460 | DONE | `combat.py` | Tank/backline order; conservation invariant (`test_invariants.py`, #24 fix). |
| Showdowns | §450s | DONE | `loop.py` `_run_showdown` | ACTION/REACTION timing. |
| Nested showdown from AMBUSH | — | GAP | — | AMBUSH into a contested lane sets flags but doesn't spawn a nested showdown (KNOWN_ISSUES #22). |
| Conquer / hold / scoring | §450s | DONE | `loop.py` | `test_hold_conquer.py`. |
| Movement | §430s | DONE | `loop.py`, `legality.py` | incl. Ganking bf→bf. |
| Triggers / timing windows | §360s | DONE | `loop.py` trigger dispatch | KNOWN_TRIGGERS in `engine_vocab.py`. |
| Targeting + Deflect surcharge | §400s | PARTIAL | `loop.py:_deflect_surcharge` | see Deflect row. |
| Attachments / gear | §716 | DONE | `loop.py:1739` | equip + Weaponmaster (partial). |
| Deck-out / **Burn Out** | §418 | DONE | `loop.py:_draw_one`/`_burn_out` | drawing from an empty deck recycles trash into the deck (randomized), an opponent gains 1 point, then the draw completes (§418.2 / §315.4.b). `test_burnout.py`. (Was mislabeled §431 in earlier notes.) |
| Modal "choose one" | — | GAP | — | no modal-choice effect (`suggested_vocab: mode_choice`×9). |
| `[A]` any-domain power payment | §resources | PARTIAL | `player.py:184` | paying "1 Power of ANY domain" ([A]) isn't modeled — `can_pay_cost`/`pay_cost` treat `domain=None` as "no power required", so any [A] portion of a cost is silently free (e.g. Accelerate on a domainless unit). Under-charges → too cheap. Needs an any-domain power spend. Ties to `suggested_vocab: gain_power_any_domain`. |
| Enters-exhausted | §142.4 | DONE | `combat.py:23`, deploy paths | units enter exhausted (`ready=False`) by default; only Accelerate/effects ready them. `test_accelerate.py`. (KNOWN_ISSUES #21 resolved — its "deploys all units ready" claim was stale.) |

## Wrong-LIVE sweep — cost-reduction class (slice 1, DONE)

The engine applies `reduce_cost`/`cost_modifier` **only to the card being played**
(`loop.py:878` self-cost; `amount_source` dynamic reductions are ignored; auras are
NOT implemented). So the only *exploitable* errors are self-cost reductions that
**over-apply** (make a card too cheap). Fixed by honest downgrade (commit below):

| card | id | problem | rule | action taken |
|------|----|---------|------|--------------|
| Concentrate | UNL-091 | LEVEL 6 "−2" + LEVEL 11 "−4 **instead**" authored as two modifiers that **stack to −6** at xp≥11 (should be −4). | §"instead" tiers | dropped the xp≥11 (−4) modifier; keeps xp≥6 (−2) → never over-applies (correct 6–10, under by 2 at 11+). |
| Drag Under | SFD-164 | "−2 to play from **anywhere other than hand**" authored **unconditionally** → too cheap from hand. | zone-gated cost | removed the `reduce_cost` (no zone condition) → under-applies from trash (safe); kept `kill_unit`. |
| Keeper of Law | VEN-119 | "**exactly** two units" modeled as "≥2" → too cheap at 3+ units. | exactly-N | removed the `reduce_cost` (no exactly-N condition) → INERT (safe). |

**Safe (no action):** self-cost reductions with `amount_source` (Sky Splitter,
Rhasa, Plaza Guardian, Shadowblade Lurker) under-apply — the engine ignores dynamic
amounts, so they cost *more* than real (agent undervalues → safe). **Aura**
reductions on a non-self card (Eager Apprentice, Herald of Scales, Vex, Marai Spire,
Ornn's Forge, Helm of Suppression, Applied Researchers, Stargazer) are silently
**inert** — the self-only engine never applies them (safe, but a fidelity gap). This
includes OGN-031 Raging Firebrand ("next spell costs [5] less" on a unit): inert, not
the permanent global discount first suspected. **Deferred:** an `aura:reduce_cost`
primitive would make these functional — tracked in DEFERRED.md (a separate slice; not
a correctness landmine).

_Later slices extend the sweep to other effect classes (durations, targets, "instead" tiers generally)._

## How this drives work
Each `PARTIAL`/`GAP`/`WRONG` row → one incremental slice: read the rule, make the
additive fix (or honest-INERT downgrade), add a focused `test_<mechanic>.py`, re-run
the full suite + drift guard, regen golden only if a golden-deck card legitimately
changes. Anything needing a subsystem too big for one slice (earmarked resources) is
parked in `DEFERRED.md` — we never block. Gate reached when every row is `DONE` or
`DEFERRED`.
