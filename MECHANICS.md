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
| 732 | Action | §732 | PARTIAL | `loop.py:1982`, `legality.py:201` | — | showdown-play permission works for **spells**; §732.1.c.1 also allows **units** with Action to be played in showdowns — not modeled. **No ACTION unit is in any current deck** (checked), so low impact; deferred. |
| 733 | Assault | §733 | DONE | `combat.py:171` | `test_combat_keywords.py` | +X might while attacker only; bare = 1 (§733.1.b.3). Combat bonus + lethality asserted. |
| 734 | Deathknell | §734 | DONE | `loop.py:_route_combat_deaths` (`on_death`) | `test_deathknell.py` | "when I die, [Effect]"; fires on true death, correctly **suppressed** when death is replaced by recall (§734.1.d.1) — replacement `continue`s before `truly_dead`. |
| 736 | Ganking | §736 | DONE | `legality.py:112`, `loop.py:1539` | `test_ganking.py` | MOVE permission (bf→bf directly), NOT a play permission — verified bf→bf move is legal only with GANKING. **Still to check (parser):** SFD-093 Dauntless Vanguard's printed text is about *playing* to an enemy bf, not moving — possible wrong GANKING tag (corpus, not engine). |
| 737 | Hidden | §737 | DONE | `loop.py` HIDE/hidden path | `test_hidden.py` | facedown hide, play for [0] at reaction speed, removal on loss of control. Nuances (champion-zone hide / from-hidden targeting) parked in KNOWN_ISSUES #23. |
| 738 | Legion | §738 | DONE | cond `you_already_played_another_card_this_turn` + `_cost_reduction` | `test_legion.py` | cost-reducing Legion (Noxus Hopeful "I cost [2] less") now applies ONCE — fixed a double-count (hardcoded legion path + generic `_cost_reduction` both fired → cost 0). One condition covers both §738.1.c forms (both mean "played another card this turn"). |
| 739 | Reaction | §739 | DONE | `loop.py:1905`, `legality.py:179` | `test_hidden.py`/reaction paths | reaction-speed spell play. (On non-spells REACTION is inert by design — see keyword-edit audit.) |
| 740 | Shield | §740 | DONE | `combat.py:171` | `test_combat_keywords.py` | +X might while defender only; bare = 1. Combat bonus + survival asserted. |
| 741 | Tank | §741 | DONE | `combat.py:96` | `test_combat_keywords.py` | assigned lethal first (§460.2.c) — order + lethal-absorption asserted. Tank+Backline conflict resolved deterministically as Tank (documented simplification vs "controller chooses"). |
| 742 | Temporary | §742 | DONE | `loop.py:284-300` | `test_temporary.py` | kills TEMPORARY units AND unattached TEMPORARY gear at base at the controller's beginning phase; attached gear rides its host (Spinning Axe "if unattached"). Note: moves direct-to-trash (no death trigger) — acceptable, no TEMPORARY permanent has a Deathknell. |
| 743 | Vision | §743 | PARTIAL (safe) | parser → `predict` amount 1 | — | "look at top 1, MAY recycle". Authored as `predict 1`, and the predict handler no-ops for n≤1, so Vision cards effectively do nothing. **Safe** (equivalent to the valid "keep top" choice — under-informs, never wrong). A faithful version needs a look-at-top-1-optionally-recycle primitive + an agent decision. Deferred. |
| 744 | Equip | §744 | DONE | play→base `loop.py:1442`; `_equip_cost` + equip exec | `test_gear_play.py`, `test_equip_cost.py`, `test_equip_deflect.py` | **Fixed end-to-end:** gear plays to BASE unattached (§146.1.a.1); it attaches via the separate Equip action, which now charges the **real EQUIP-ability cost** parsed from the card text ("Equip [fury]" → 1 Fury; "[1][fury]" → 1 energy + 1 Fury; "[rune]" → 1 generic power) — not the play cost. Only Equipment (gear with an Equip ability) is equippable. Attached gear grants might via `grant_might`. Minor: a few gear with an extra non-resource Equip cost (recycle/kill/spend-XP) charge only the resource part (`complex` flag). |
| 745 | Quick-Draw | §745 | PARTIAL | `loop.py:1442` | `test_gear_play.py` | §745.1.d attach-on-play is now correctly gated on the QUICK-DRAW keyword (normal gear goes to base; Quick-Draw attaches to a controlled unit as played). Remaining: the Reaction-speed TIMING (playing the gear during a reaction/showdown window) is not yet modeled. Meta gear: Long Sword, Sterak's Gage, Cloth Armor. |
| 746 | Repeat | §746 | DONE | additional-cost path | `test_repeat_cost.py` | optional additional cost → execute spell effect one extra time. |
| 747 | Weaponmaster | §747 | DONE | `loop.py` WEAPONMASTER block | on-play: pick the first affordable controlled Equipment, pay its **real Equip cost reduced by [A]** (`_equip_cost_minus_A`), attach to the unit; skips when unaffordable. `test_weaponmaster.py`. (Picks the first affordable Equipment rather than an agent choice — a minor stand-in.) |
| — | Deflect | §408/§809 | DONE | `_deflect_surcharge` (`loop.py:778`) | `test_equip_deflect.py` | a spell targeting an opponent's battlefield is surcharged by the max DEFLECT among enemy units there; friendly-targeting spells are not surcharged; `ignore_deflect_here` battlefields waive it. (Ability-targeting surcharge still TODO — spells covered.) |

## Core systems

| system | § | status | location | note |
|--------|---|--------|----------|------|
| Turn / phase structure | §300s | DONE | `loop.py` `_phase_*` | resumable loop; golden + invariants cover it. |
| Resources (energy/power/runes/6 domains) | §200s | DONE | `player.py`, `loop.py` | pay/afford paths tested (`test_rune_system.py`). |
| **Earmarked resources** | (Diana Scorn / Ornn) | DONE | `player.py` pools, `loop.py` `_pay_showdown`/`_pay_gear`/`_pay_equip` | restricted-use pools: Diana Scorn energy spent only in showdowns, Ornn generic power spent only on gear (play/equip/[tap]). Generated by the legend tap; consumed earmark-first at matching spend sites; cleared each turn. `test_earmarked.py`. (Timing simplification: generated via a main-phase tap; the earmark restricts spending.) |
| **on_showdown_begin** (Diana Lunari) | — | DONE | `loop.py:_run_showdown` + `reveal_top_draw_if_spell` | when a showdown begins at a unit's battlefield, its controller's trigger fires; Diana Lunari optionally pays [1] to reveal the top card and draw it if a spell. `test_diana_lunari.py`. (Predict-recycle half simplified.) |
| Combat + damage-assignment order | §437/§460 | DONE | `combat.py` | Tank/backline order; conservation invariant (`test_invariants.py`, #24 fix). |
| Showdowns | §450s | DONE | `loop.py` `_run_showdown` | ACTION/REACTION timing. |
| Nested showdown from AMBUSH | — | GAP | — | AMBUSH into a contested lane sets flags but doesn't spawn a nested showdown (KNOWN_ISSUES #22). |
| Conquer / hold / scoring | §450s | DONE | `loop.py` | `test_hold_conquer.py`. |
| Movement | §430s | DONE | `loop.py`, `legality.py` | incl. Ganking bf→bf. |
| Triggers / timing windows | §360s | DONE | `loop.py` trigger dispatch | KNOWN_TRIGGERS in `engine_vocab.py`. |
| Targeting + Deflect surcharge | §400s | PARTIAL | `loop.py:_deflect_surcharge` | see Deflect row. |
| Attachments / gear | §716 | DONE | `loop.py` play→base / equip / gear abilities | play→base (§146.1.a.1), Equip charges the real EQUIP cost, Quick-Draw attaches on play, attached gear grants might. **Gear's own [tap] abilities now work from base** (`gear_ability` entries + `Card.tapped` state, untapped at turn start) — 26 gear cards were previously inert. `test_gear_play.py`, `test_equip_cost.py`, `test_gear_ability.py`. "This enters exhausted" gear now enters tapped (can't tap the turn it's played). Attached gear's own [tap] abilities are now usable too (`_controls_gear`); Weaponmaster attaches at the real [A] discount. Remaining (tracked in DEFERRED.md, all required): Quick-Draw reaction-timing, complex Equip extra-costs (recycle/kill/XP). |
| Deck-out / **Burn Out** | §418 | DONE | `loop.py:_draw_one`/`_burn_out` | drawing from an empty deck recycles trash into the deck (randomized), an opponent gains 1 point, then the draw completes (§418.2 / §315.4.b). `test_burnout.py`. (Was mislabeled §431 in earlier notes.) |
| Modal "choose one" | — | GAP | — | no modal-choice effect (`suggested_vocab: mode_choice`×9). |
| `[A]` any-domain power payment | §resources | DONE | `_pay_generic_power` (`loop.py:980`) wired into the cost sites | paying "1 Power of ANY domain" ([A]) is charged via `_pay_generic_power` at the sites that use it: Accelerate on a domainless unit ([1]+[A]), gear play/equip/[tap] `[rune]` costs, and Ornn's earmarked gear-power. `test_accelerate.py` / `test_equip_cost.py`. (A general `pay_cost` context flag is still not threaded, but every current [A] spend site is covered.) |
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
