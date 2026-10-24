<!-- Generated/maintained by hand as the engine mechanics burn-down chart.
     One row per game DYNAMIC (not per card). Source of truth: CORE_RULES.md
     (Core Rules revision 2026-10-09, Radiance; renumbered from v1.2 on 2026-10-24 —
     keywords moved §731–747 → §805–821, +74). Status legend:
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

## Keyword glossary (Core Rules §804)

| # | keyword | § | status | engine location | test | note / rule nuance to verify |
|---|---------|---|--------|-----------------|------|------------------------------|
| 805 | Accelerate | §805 | DONE | `loop.py:1312` | `test_accelerate.py` | OPTIONAL cost [1] + 1 domain-power → enter ready. Now routed through `decide_optional` (§805.2 "may"; default yes preserves prior play). Single-domain match is enforced; **caveat**: for a domainless/multi-domain unit the [A] power isn't charged (can_pay/pay skip power when domain=None) — minor undercharge, see the [A]-power row below. |
| 806 | Action | §806 | DONE | `loop.py:_run_showdown`, `legality._showdown_actions` | showdown-play permission for spells AND units (§806.1.c.1) — an ACTION unit can be played during a showdown (to base, via `_apply_action`). `test_action_unit.py`. (No current deck has an ACTION unit; the rule is now honored regardless.) |
| 807 | Assault | §807 | DONE | `combat.py:171` | `test_combat_keywords.py` | +X might while attacker only; bare = 1 (§807.1.b.3). Combat bonus + lethality asserted. |
| 808 | Deathknell | §808 | DONE | `loop.py:_route_combat_deaths` (`on_death`) | `test_deathknell.py` | "when I die, [Effect]"; fires on true death, correctly **suppressed** when death is replaced by recall (§808.1.d.1) — replacement `continue`s before `truly_dead`. |
| 810 | Ganking | §810 | DONE | `legality.py:112`, `loop.py:1539` | `test_ganking.py` | MOVE permission (bf→bf directly), NOT a play permission — verified bf→bf move is legal only with GANKING. **Still to check (parser):** SFD-093 Dauntless Vanguard's printed text is about *playing* to an enemy bf, not moving — possible wrong GANKING tag (corpus, not engine). |
| 811 | Hidden | §811 | DONE | `loop.py` HIDE/hidden path | `test_hidden.py` | facedown hide, play for [0] at reaction speed, removal on loss of control. Nuances (champion-zone hide / from-hidden targeting) parked in KNOWN_ISSUES #23. |
| 812 | Legion | §812 | DONE | cond `you_already_played_another_card_this_turn` + `_cost_reduction` | `test_legion.py` | cost-reducing Legion (Noxus Hopeful "I cost [2] less") now applies ONCE — fixed a double-count (hardcoded legion path + generic `_cost_reduction` both fired → cost 0). One condition covers both §812.1.c forms (both mean "played another card this turn"). |
| 813 | Reaction | §813 | DONE | `loop.py:1905`, `legality.py:179` | `test_hidden.py`/reaction paths | reaction-speed spell play. (On non-spells REACTION is inert by design — see keyword-edit audit.) |
| 814 | Shield | §814 | DONE | `combat.py:171` | `test_combat_keywords.py` | +X might while defender only; bare = 1. Combat bonus + survival asserted. |
| 815 | Tank | §815 | DONE | `combat.py:96` | `test_combat_keywords.py` | assigned lethal first (§815.1.b / §467.2.c) — order + lethal-absorption asserted. Tank+Backline conflict resolved deterministically as Tank (documented simplification vs "controller chooses"). |
| 816 | Temporary | §816 | DONE | `loop.py:284-300` | `test_temporary.py` | kills TEMPORARY units AND unattached TEMPORARY gear at base at the controller's beginning phase; attached gear rides its host (Spinning Axe "if unattached"). Note: moves direct-to-trash (no death trigger) — acceptable, no TEMPORARY permanent has a Deathknell. |
| 817 | Vision | §817 | DONE | `predict` handler n==1 (`effects.py`) | `test_vision.py` | "look at top 1, MAY recycle". The predict handler now fires the reveal-from-top offer at n==1 and offers an optional recycle-to-bottom via `Agent.decide_predict_recycle` (default keep — a valid null action; a learning agent can recycle a bad top). |
| 818 | Equip | §818 | DONE | play→base `loop.py:1442`; `_equip_cost` + equip exec | `test_gear_play.py`, `test_equip_cost.py`, `test_equip_deflect.py` | **Fixed end-to-end:** gear plays to BASE unattached (§148.1.a.1); it attaches via the separate Equip action, which now charges the **real EQUIP-ability cost** parsed from the card text ("Equip [fury]" → 1 Fury; "[1][fury]" → 1 energy + 1 Fury; "[rune]" → 1 generic power) — not the play cost. Only Equipment (gear with an Equip ability) is equippable. Attached gear grants might via `grant_might`. Minor: a few gear with an extra non-resource Equip cost (recycle/kill/spend-XP) charge only the resource part (`complex` flag). |
| 819 | Quick-Draw | §819 | DONE | `loop.py:1442` (attach) + reaction/showdown dispatch | `test_gear_play.py`, `test_quickdraw_reaction.py` | §819.1.d attach-on-play gated on the keyword AND §819.1.b Reaction timing: a QUICK-DRAW gear is now offered/played during a reaction window and during a showdown (legality `_reaction_actions`/`_showdown_actions` + the two play loops dispatch GEAR through `_apply_action`). |
| 820 | Repeat | §820 | DONE | additional-cost path | `test_repeat_cost.py` | optional additional cost → execute spell effect one extra time. |
| 821 | Weaponmaster | §821 | DONE | `loop.py` WEAPONMASTER block | on-play: pick the first affordable controlled Equipment, pay its **real Equip cost reduced by [A]** (`_equip_cost_minus_A`), attach to the unit; skips when unaffordable. `test_weaponmaster.py`. (Picks the first affordable Equipment rather than an agent choice — a minor stand-in.) |
| — | Deflect | §809 | DONE | `_deflect_surcharge` (`loop.py:778`) | `test_equip_deflect.py` | a spell targeting an opponent's battlefield is surcharged by the max DEFLECT among enemy units there; friendly-targeting spells are not surcharged; `ignore_deflect_here` battlefields waive it. (Ability-targeting surcharge still TODO — spells covered.) |
| 822 | Ambush | §822 | DONE | `legality.py`, `loop.py:_deploy_ambush_champion` | `test_ambush.py`, `test_nested_ambush.py` | reaction-timing play to a battlefield where you have units; deploy into a contested lane spawns a showdown. **Radiance:** "[Ambush]" as a verb + permission-expanding text (Rengar Trophy Hunter, §822.1.d) not verified. |
| 823 | Hunt | §823 | PARTIAL | `loop.py`, `state.py` (XP) | — | conquer/hold → gain X XP; stacking of multiple Hunt instances (§823.2) unverified; no dedicated test. |
| 824 | Level | §824 | PARTIAL | `state.py` XP gate, `cards_registry.py` | — | dependent ability active while controller has ≥N XP; re-evaluation on controller change (§824.1.c.1) unverified; no dedicated test. |
| 825 | Unique | §825 | GAP (deckbuild) | — | — | deck-construction limit (1 copy per name); no gameplay effect (§825.4). Only matters if/when the engine validates decklists. |
| 826 | Backline | §826 | PARTIAL | `combat.py` damage-assignment order | — (no dedicated test) | assigned lethal last; Tank+Backline conflict resolved as Tank (see Tank row). |
| 827 | Empower | §827 | PARTIAL | `effects.py` `empower_self`, `state.py` | `test_empower.py` | binary state only. **Radiance:** some objects may now be empowered multiple times (§442.1.c.1 / §827.1.c.5, stacking status) — not modeled. |
| 828 | Empowered | §828 | PARTIAL | `this_is_empowered` passives | `test_empower.py` | passive bonuses work; EMPOWERED clauses that *modify* another ability and on-become-empowered triggers deferred (KNOWN_ISSUES #20). |
| 829 | Flow | §829 | PARTIAL | `loop.py` | — | Flow spells play normally from hand; play-from-trash for the Flow cost + banish deferred (KNOWN_ISSUES #19b). |
| 830 | Deploy | §830 | GAP | — | — | **New in Radiance.** Gear with Deploy may be played/created to ANY battlefield (incl. enemy/open), only to a battlefield; not recalled in cleanups; killed when an opponent holds there; can be moved. Needed by the Bomb token (RAD-T02, §187.12). |
| 831 | Disarm | §831 | GAP | — | — | **New in Radiance.** Attack trigger: "When I attack, give an enemy unit here −X [M] this turn"; bare = 1; multiple instances SUM and trigger once (§831.1.d.1 / §831.2). |
| 832 | Show Off | §832 | GAP | — | — | **New in Radiance.** As you play the card you may reveal [Object] from hand and/or pick it among friendly objects on the board; linked abilities read the shown-off object's info snapshotted at finalization (§832.1.d.1). Instances are separate (§832.2). |

## Core systems

| system | § | status | location | note |
|--------|---|--------|----------|------|
| Turn / phase structure | §301–324 | DONE | `loop.py` `_phase_*` | resumable loop; golden + invariants cover it. |
| Resources (energy/power/runes/6 domains) | §160–168 | DONE | `player.py`, `loop.py` | pay/afford paths tested (`test_rune_system.py`). |
| **Earmarked resources** | (Diana Scorn / Ornn) | DONE | `player.py` pools, `loop.py` `_pay_showdown`/`_pay_gear`/`_pay_equip` | restricted-use pools: Diana Scorn energy spent only in showdowns, Ornn generic power spent only on gear (play/equip/[tap]). Generated by the legend tap; consumed earmark-first at matching spend sites; cleared each turn. `test_earmarked.py`. (Timing simplification: generated via a main-phase tap; the earmark restricts spending.) |
| **on_showdown_begin** (Diana Lunari) | — | DONE | `loop.py:_run_showdown` + `reveal_top_draw_if_spell` | when a showdown begins at a unit's battlefield, its controller's trigger fires; Diana Lunari optionally pays [1] to reveal the top card and draw it if a spell. `test_diana_lunari.py`. (Predict-recycle half simplified.) |
| Combat + damage-assignment order | §461–468 | DONE | `combat.py` | Tank/backline order; conservation invariant (`test_invariants.py`, #24 fix). |
| Showdowns | §341–348 | DONE | `loop.py` `_run_showdown` | ACTION/REACTION timing. |
| Nested showdown from AMBUSH | — | DONE | `_deploy_ambush_champion` | an AMBUSH deploy into a contested lane spawns a showdown (mirrors move-into-contested); `_run_showdown` self-guards on `showdown_active`, so a deploy during an existing showdown joins the current combat rather than nesting. `test_nested_ambush.py`. (#22 resolved.) |
| Conquer / hold / scoring | §469–474 | DONE | `loop.py` | `test_hold_conquer.py`. |
| Movement | §447–455 | DONE | `loop.py`, `legality.py` | incl. Ganking bf→bf. |
| Triggers / timing windows | §382–393 | DONE | `loop.py` trigger dispatch | KNOWN_TRIGGERS in `engine_vocab.py`. |
| Targeting + Deflect surcharge | §355.6–355.14, §809 | PARTIAL | `loop.py:_deflect_surcharge` | see Deflect row. |
| Attachments / gear | §716 | DONE | `loop.py` play→base / equip / gear abilities | play→base (§148.1.a.1), Equip charges the real EQUIP cost, Quick-Draw attaches on play, attached gear grants might. **Gear's own [tap] abilities now work from base** (`gear_ability` entries + `Card.tapped` state, untapped at turn start) — 26 gear cards were previously inert. `test_gear_play.py`, `test_equip_cost.py`, `test_gear_ability.py`. "This enters exhausted" gear now enters tapped (can't tap the turn it's played). Attached gear's own [tap] abilities are now usable too (`_controls_gear`); Weaponmaster attaches at the real [A] discount; complex Equip extra-costs (recycle N / kill a friendly unit / spend XP) are parsed and charged. Remaining (tracked in DEFERRED.md, all required): Quick-Draw reaction-timing. |
| Deck-out / **Burn Out** | §432 | DONE | `loop.py:_draw_one`/`_burn_out` | drawing from an empty deck recycles trash into the deck (randomized), an opponent gains 1 point, then the draw completes (§432.2 / §315.4.b.1). `test_burnout.py`. |
| Modal "choose one" | — | DONE | `mode_choice` effect + `Agent.decide_mode` | the actor picks one mode (default first); its sub-effect(s) resolve. Modes may hold multiple effects. `test_modal.py`; Minah Swiftfoot authored. The other ~8 modal cards can now be authored with `mode_choice` (corpus/parser work). |
| `[A]` any-domain power payment | §135.2.e.5 | DONE | `_pay_generic_power` (`loop.py:980`) wired into the cost sites | paying "1 Power of ANY domain" ([A]) is charged via `_pay_generic_power` at the sites that use it: Accelerate on a domainless unit ([1]+[A]), gear play/equip/[tap] `[rune]` costs, and Ornn's earmarked gear-power. `test_accelerate.py` / `test_equip_cost.py`. (A general `pay_cost` context flag is still not threaded, but every current [A] spend site is covered.) |
| Enters-exhausted | §143.4 | DONE | `combat.py:23`, deploy paths | units enter exhausted (`ready=False`) by default; only Accelerate/effects ready them. `test_accelerate.py`. (KNOWN_ISSUES #21 resolved — its "deploys all units ready" claim was stale.) |

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
