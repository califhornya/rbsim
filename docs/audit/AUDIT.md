# Rules audit of the engine (2026-11-10)

The engine checked against `docs/rules/CORE_RULES.md` (revision 2026-10-09),
`docs/rules/TOURNAMENT_RULES.md` and the printed card text
(`riftbound/data/reference/piltover_archive.json`), in this order: the two
training precons (`precon_zed`, `precon_shen`) and the rules they play by; the
PARTIAL / GAP rows of `docs/MECHANICS.md`; the other eight decks, from
`BACKLOG.md` O1.

Every deviation below has a test in `tests/audit/` that plays the situation and
checks what the rules or the card say. In phase 1 (`4af83ef`) each test was
marked `xfail(strict=True)`; each fix, one commit per deviation, removed its
marker. Line numbers are those of the commit this audit started from
(`ec62750`).

**The eight non-precon decks were removed on 2026-11-12** (out of date; the
owner will give two current competitive decks). Their passes (D13-D18,
D23-D28) stay: they fixed cards, which are still in the corpus; where this
document names those decks it is the record of where a card was found.

**State (2026-11-12, fourth pass): 49 deviations found, 49 fixed, none open.**
The suite is green (1754 passed, no xfail). The fourth pass went outside the
ten decks, by class and not card by card (D29-D49; no golden game changed):
see its section for what was scanned and what was not read. The third pass
read the 119 cards of the other eight decks against the printed text and
played them in the engine (D23-D28; no golden game changed). The second pass
tested the two suspected deviations the first one left in "Not checked" (D19,
D20) and fixed the two it met on the way (D21, D22). The owner answered Q1–Q4
of "Ambiguous rules" (2026-11-11): Q1, Q3 and Q4 changed the engine, Q2 kept
it as it was; Q5 asks nothing. What is still open is in "Not checked"
(what was not audited, and the leftovers noted under D1, D6 and D9). Two
things a fix changed outside the engine: `ACTION_DIM` is 319, was 316 (D2:
saved nets no longer load), and golden games were regenerated in five commits
(D9: 12, D14: 6, D18: 5, D20: 2, D21: 5), each for the reason given in its
commit message.

How the "weight for training" was estimated: 400 Zed-vs-Shen games with
`random` agents (average 16 turns) and 400 with `simple_trade` (13 turns),
counting the games in which the situation comes up. These agents are weak and
their games short, so the counts are an order of magnitude, not what a trained
agent will see; where an agent could look for the situation on purpose it is
said.

## Status

| # | Deviation | § / card | Zed vs Shen | Status |
|---|-----------|----------|-------------|--------|
| D1 | BURN past the end of the Main Deck is no Burn Out | §441.4, §432 | 0 / 800 games (games end first); free milling once it happens | fixed, `b496a02` |
| D2 | The Chosen Champion can't be played to a battlefield | §108.3.d, §355.2.a | 30-57% of games | fixed, `944c733` |
| D3 | A facedown card outlives the loss of its battlefield | §323.6.a, §107.3.d | the card lingers in ~10% of games; exploitable | fixed, `069bf5e, c6bded3` |
| D4 | A Combat Cleanup heals only the units that fought | §468.1.a.1 | ~2% of games | fixed, `af44349` |
| D5 | STUN never ends on a unit in a base | §424.1.a.2 | 3-5% of games | fixed, `5f7a55c` |
| D6 | The game goes on after a player has the Victory Score | §323.1, §194.2 | 13-25% of games keep asking for actions; the winner can change | fixed, `8095a39` |
| D7 | An Equipment is trashed when its unit is banished | §719.5, §436.4.b | ~1% of games | fixed, `bdb111a` |
| D8 | A unit played from facedown in the Main Phase chooses anywhere | §811.1.d.3 | <1% of games (Kennen) | fixed, `983fc60` |
| D9 | An activated ability can be paid for with no legal target | §403.3, §355.8, §355.4.a | 50-100% of games (wasted, not exploitable) | fixed, `6b64fc1` |
| D10 | A REACTION unit can't be played to base at reaction speed | §813.1.c.1, §813.3.a | Shen Kinkou, 1 card: a missing option | fixed, `f7b6848` |
| D11 | REACTION plays in a showdown only at its battlefield | §822.1.b, §811.6 | a missing option | fixed, `5452770` |
| D12 | TANK + BACKLINE on one unit: no choice for the assigner | §467.2.c.8 | never (no BACKLINE in the two decks) | fixed, `d521c78` |
| D13 | Stupefy gives +1 instead of -1 | OGN-095 | other decks (Diana, Ezreal) | fixed, `85da2a0` |
| D14 | Noxus Hopeful has Might 3, printed 4 | OGN-012 | other decks (Pyke, Rengar) | fixed, `2cbb2b1` |
| D15 | Thrill of the Hunt costs two Power, printed one | UNL-184 | other decks (Rengar) | fixed, `fe44ded` |
| D16 | Pit Crew has no text | OGN-091 | other decks (Ornn) | fixed, `427f1dd` |
| D17 | The Harrowing has no text | OGN-198 | other decks (Kennen) | fixed, `02c4877` |
| D18 | Existential Dread can choose the caster's own attacker | UNL-134 | other decks (Diana) | fixed, `cd5b5e9` |
| D19 | The Start of Turn runs Channel, Hold, then the start-of-Beginning abilities | §315 | every Hold with an ability: two runes too many to react with; other decks: Frozen Fortress after the Hold | fixed, `99678b6` |
| D20 | No Conquer of a battlefield lost and taken back in one turn | §471.1 | not measured; 2 of 20 golden games (Diana's Moonfall) | fixed, `eb8acb7` |
| D21 | Moonfall is played at a battlefield with no unit of its player | UNL-198 | other decks (Diana) | fixed, `3ada8b6` |
| D22 | A Hold gives its point after its abilities resolve | §473 | Shadow Temple's Burn Out at one point from the end each | fixed, `197be0b` |
| D23 | An ability with no [Action] is used in a showdown | §145.2, §151.2 | other decks (Heart of Dark Ice: Yasuo; The List: Ezreal); 34 cards of the corpus | fixed, `17838db` |
| D24 | QUICK-DRAW attaches only at the battlefield it is played "at" | §819.1.d | other decks (Cloth Armor, Sterak's Gage: Ornn; Long Sword: Akali) | fixed, `6376f85` |
| D25 | Bellows Breath hits units at different locations | SFD-080 | other decks (Ezreal) | fixed, `4947f42` |
| D26 | Ezreal's legend doesn't count an enemy gear chosen | SFD-199 | other decks (Ezreal) | fixed, `a0063f2` |
| D27 | Patched Porobot is a unit only, printed "Unit Gear" | §178, VEN-058 | other decks (Ornn, 3 copies) | fixed, `840876a` |
| D28 | Rengar's and Kennen's legends give only to a friendly unit | UNL-183, VEN-155 | other decks (Rengar, Kennen): a missing option, never the better one | fixed, `0ac459e` |
| D29 | An ability that chooses a gear, a card or a place is offered with nothing to choose | §403.3, §355.5 | Pack of Wonders (Kennen, Pyke decks); 9 cards outside the decks | fixed, `b4d8b2e` |
| D30 | Jax's legend moves an attached Equipment only from base to a battlefield | SFD-193 | outside the decks | fixed, `15475ff` |
| D31 | Teemo's legend takes a Teemo only from the Champion Zone | OGN-263 | outside the decks | fixed, `bf2db18` |
| D32 | Baited Hook kills the weakest non-token unit, unasked | OGN-242 | outside the decks | fixed, `2c54656` |
| D33 | Ambessa's legend readies only a friendly exhausted unit | VEN-153 | outside the decks | fixed, `73f504b` |
| D34 | [rune][rune] can't be paid with Power of two domains | generic Power | any deck: DEFLECT 2 (Ornn Forge God), Jayce, Dominus | fixed, `28c756d` |
| D35-D38 | Premonition, Zaunite Bouncer, King's Edict, Overloaded Traveler have no effect | SFD-087, OGN-188, OGN-237, RAD-072 | outside the decks | fixed, `598611d` |
| D39 | Spectral Centaur Might 5 (6), Fallen Feline Might 2 (3), Brittle Steel no Power cost ([Fury]), Grand Strategem no [ACTION] | UNL-068, VEN-132, VEN-003, OGN-233 | outside the decks | fixed, `598611d` |
| D40 | Harnessed Dragon kills a unit of its own player | OGN-234 | outside the decks | fixed, `598611d` |
| D41 | Carnivorous Snapvine fights an enemy unit in a base | OGN-149 | outside the decks | fixed, `598611d` |
| D42 | Lillia Protector of Dreams keeps her +1 Might for good | UNL-058 | outside the decks | fixed, `598611d` |
| D43 | Apprentice Mage has no "[Empowered] +1 Might" | VEN-047 | outside the decks | fixed, `598611d` |
| D44 | Elnuk Herd can't give its +3 to itself (errata) | RAD-081 | outside the decks | fixed, `598611d` |
| D45 | Iridescent Avian buffs an enemy unit | RAD-027 | outside the decks | fixed, `598611d` |
| D46 | Meticulous Restorationist asks for Order Power, printed [Rune] | RAD-120 | outside the decks | fixed, `598611d` |
| D47 | Blighted Battleaxe's Equip asks for Fury, printed [Rune] | UNL-019 | outside the decks | fixed, `598611d` |
| D48 | Reinforce plays from the deck, errata: banish, then play | OGN-062 | outside the decks | fixed, `598611d` |
| D49 | Mageseeker Investigator's toll is paid in Energy, printed [Rune] | UNL-163 | outside the decks | fixed, `598611d` |

## Deviations, priority 1: the precons and the rules they use

### D1. BURN past the end of the Main Deck is no Burn Out

- **Rule.** §441.4: "When Burning is part of an effect, then a player must Burn
  as many cards as possible. If instructed to burn more cards than they have
  in their main deck, they burn that many cards, burn out and then burn the
  rest." §432.2: to Burn Out, the player "Recycles their trash into their Main
  Deck", "Chooses an opponent to gain 1 point", then "Completes the remainder
  of the action".
- **Engine.** `effects.py:5238` (`_burn`) calls `Player.burn`
  (`player.py:334`), which stops when the deck is empty: nothing is recycled,
  nobody gains a point, the rest isn't burned. Only a draw burns out
  (`loop.py:1354`).
- **Cards.** Zed: Shadow Temple (BURN 3 at each Hold, for whoever holds it,
  Shen too), Death Mark (BURN 3), Blade Twirler ("choose a player. They BURN
  1": the opponent too), Shadow Order Disciple (BURN 1).
- **Tests.** `test_burn_with_too_few_cards_burns_out`,
  `test_blade_twirler_burns_out_the_player_it_chooses`
  (`tests/audit/test_audit_precon_rules.py`).
- **Weight.** It needs a Main Deck with fewer cards than the BURN: in 800
  games it never came up (39 cards last longer than 13-16 turns). Longer,
  more defensive games reach it. When it does, the engine makes milling free
  (the real rule gives the opponent a point each time) and denies Blade
  Twirler its point against an empty deck: an agent that gets there learns the
  opposite of the rule. Rare now, wrong in a way that pays.
- **Fixed.** `_burn` burns what is there, calls `GameLoop._burn_out` (trash
  recycled, the opponent gains a point, which can end the game: D6) and burns
  the rest. No golden game changes.
- **Left over.** As for a draw (`_draw_one`), one Burn Out per instruction: with
  the Main Deck and the trash both empty §432.3 has the player burn out again
  and again until an opponent wins; the engine gives one point per attempt.

### D2. The Chosen Champion can't be played to a battlefield

- **Rule.** §108.3.d: "The Chosen Champion can be played from here as normal,
  following the rules of Playing a Card." §355.2.a: "By default, Valid
  locations include the controller's Base or a Battlefield the controller
  controls."
- **Engine.** `legality.py:97` offers one action, `GameAction.champion(0, ...)`,
  and `loop.py:5441-5458` plays the champion with no battlefield
  (`_play_unit(champion, ..., from_zone="champion")`): always to base. A unit
  card in hand gets "Play X to BF0" (`legality.py:76-86`).
- **Test.** `test_the_chosen_champion_can_be_played_to_a_battlefield_you_control`.
- **Weight.** Every game plays the champion; in 30% (`simple_trade`) to 57%
  (`random`) of games its player controlled a battlefield at that moment. In
  base it enters exhausted and can only walk to the battlefield next turn, after
  that turn's Hold. Shen Leader of the Kinkou Order ("When I hold, if there is
  exactly one other unit you control here, you score 1 point") and Zed From
  the Shadows lose a full turn. Not an exploit: a systematic handicap on the
  strongest play of both decks, and the net learns to value the champion
  accordingly.
- **Fixed.** The main-phase CHAMPION action takes a destination like a UNIT
  (`("CHAMPION", None, 0, dst)`), from `_unit_play_destinations`, with the
  destination's discount and surcharge. The action encoding
  (`riftbound/ai/encoding.py`) has `N_BF` more slots (`_OFF_CHAMP_BF`):
  **`ACTION_DIM` grows by 3, so a net saved before this commit no longer
  loads** (BACKLOG O4 already calls for training from scratch). The heuristic
  agents still play the champion to base (their choice, not a rule). No golden
  game changes.

### D3. A facedown card outlives the loss of its battlefield

- **Rule.** §107.3.d: "If a player loses Control of a Battlefield, any cards in
  the Facedown Zone associated with that Battlefield are removed during the
  next Cleanup." §323.5-323.6.a, in every Cleanup: "Players lose control of any
  controlled Battlefields without their Units occupying them if the turn is in
  an Open State and there is no Showdown or Combat ongoing there", then "Remove
  all Hidden cards from all Battlefields that are not controlled by the same
  player and place them in their owner's Trash."
- **Engine.** `_cleanup_hidden_cards` (`loop.py:3588`) runs once, at the end of
  the turn (`loop.py:8050`); `_hidden_playable` (`loop.py:3597`) says "Current
  control is NOT required". So when Zed kills Shen's only unit at a
  battlefield with a spell in the Main Phase and then moves in, Shen still
  plays the card hidden there, for [0], into the showdown.
- **Test.** `test_a_facedown_card_is_trashed_as_its_player_loses_the_battlefield`.
- **Weight.** Shen has five HIDDEN cards (3 Disciple of Shen, Kennen,
  Resonating Strike). With random play a facedown card sat at a battlefield
  its owner no longer controlled at 18 decision points over 150 games; the
  illegal play itself was not seen in 800 games, but it is there to be found:
  the rule's counterplay (clear the battlefield with Ruthless Strike or Wind
  and Ghosts before attacking, and the hidden card is gone) doesn't exist in
  the simulation, so Shen's hidden cards are safer than they should be and Zed
  never learns the answer.
- **Fixed.** `_cleanup_hidden_cards` also runs once an action is done
  (`_apply_action`), once a chain has resolved (`_resolve_chain`) and once a
  showdown or combat is over (`_run_showdown`, §468.5.c: the first fix missed
  this one, a second commit added it with
  `test_a_facedown_card_is_trashed_as_its_battlefield_is_conquered`), not only
  as the turn ends. It reads `Battlefield.control()`, which keeps control
  during a showdown or combat there (§190.4.b), so a card hidden at a
  battlefield under attack stays playable until the fight is over. Over 300
  random games no facedown card is left at a battlefield its owner doesn't
  control at any decision outside a showdown or chain (18 in 150 games
  before). No golden game changes.
  `tests/test_g2_origins.py::test_pack_of_wonders_returns_a_gear_or_a_facedown_card`
  had a card hidden at a battlefield nobody controlled (§107.3.c forbids it);
  its board now has a unit there.

### D4. A Combat Cleanup heals only the units that fought

- **Rule.** §468.1.a.1: 'Invoke a Combat Special Cleanup. Insert "3c. Heal all
  Units."' The same words as the end of turn (§317.2.b). §143.3.b: "Damage is
  Healed from Units at two specific times: At the end of each player's turn.
  During a Combat Cleanup."
- **Engine.** `combat.py:374-377` (`resolve_might_combat`) resets the damage of
  the survivors of that combat only; `_phase_combat_and_conquer_single`
  (`loop.py:7698`) heals nothing else.
- **Test.** `test_a_combat_heals_the_units_everywhere`: Ruthless Strike deals 3
  to a 5 [might] unit at one battlefield, a combat ends at the other, a second
  Ruthless Strike: the unit survives by the rules, dies in the engine.
- **Weight.** ~2% of `simple_trade` games had a combat while a unit elsewhere
  was damaged. Zed is the one who profits: damage from Ruthless Strike (3
  copies) and a lost combat add up across the turn, and Morgana Vindictive
  ("deal damage to a unit equal to the damage marked on it") finds damage that
  should be gone.
- **Note.** "Heal all Units" is read as written: every unit on the board, the
  same words as the end of the turn. If you know a ruling that limits it to
  the units of that combat, the fix is one loop to remove.
- **Fixed.** `_phase_combat_and_conquer_single` clears `damage` on every unit
  in play once the combat's deaths are routed, before the attackers are
  recalled (the order of §468.1.a). No golden game changes.

### D5. STUN never ends on a unit in a base

- **Rule.** §424.1.a.2: "Stunned Units lose the Stunned status during step 3d
  of the end of turn cleanup."
- **Engine.** `loop.py:937-940` clears `stunned` at the start of each turn, and
  only on units at battlefields. A unit stunned in its base (Kennen Keeper of
  Balance: "you may pay [2] to STUN a unit", any unit) stays stunned until it
  has been at a battlefield at the start of a turn: it moves out next turn,
  fights, and deals no combat damage.
- **Test.** `test_a_unit_stunned_in_its_base_is_no_longer_stunned_next_turn`.
- **Weight.** 3-5% of games had a unit stunned in a base at the end of a turn.
  Exploitable by Shen: [2] on a unit in base disarms it for its next attack as
  well, where the rule gives one turn. Only Kennen stuns in the two decks (1
  copy, plus its attack trigger).
- **Fixed.** The Expiration Step of `_end_turn` clears `stunned` on every unit
  in play, bases included. No golden game changes.

### D6. The game goes on after a player has the Victory Score

- **Rule.** §323.1, the first step of every Cleanup: "If a player has points
  greater than or equal to the Victory Score, and more points than every
  opponent, that player wins." §196: "When a player wins the game, the game
  ends."
- **Engine.** `_gain_points` (`loop.py:7216`) only adds. The score is looked at
  twice a turn: after the Hold (`loop.py:7947`) and at the end of the turn
  (`loop.py:8026`), each time side A first, without "more points than every
  opponent". `_run_main_actions` (`loop.py:7967`) keeps asking for actions.
  Two consequences: (1) the winner keeps playing to the end of the turn; (2) a
  point given outside those two checks doesn't end the game: A burns out in
  its Draw Phase and gives B its 8th point, plays its turn, reaches 8 too, and
  `points_A >= victory_score` is checked first: A wins a game B had won.
- **Tests.** `test_the_game_ends_as_soon_as_a_player_has_the_victory_score`,
  `test_a_burn_out_that_gives_the_last_point_ends_the_game`.
- **Weight.** (1) 13-25% of games ask for actions after the last point: they
  can't change the result but they are positions and moves in the training
  data whose value is fixed, labelled as decisions. (2) needs a Burn Out, as
  rare as D1 today; the winner did not change in 300 random games.
- **Fixed.** `GameState.winner` is set the moment a side has the Victory Score
  and more points than the other (`GameLoop._note_winner`, from
  `_gain_points`); with equal points nobody has won yet (§194.2.b). From then
  on no player is asked anything (no action, reaction or showdown step, no new
  showdown), and `_begin_turn` (after the Hold and after the Draw Phase),
  `_run_main_actions` and `_end_turn` return the result. "You win the game"
  (`win_game`) sets it directly (§195). 300 random games: 310 decisions asked
  after the last point before, none now. No golden game changes.
- **Left over.** What is already resolving when the last point is gained (the
  rest of that spell, the chain under it) still resolves with nobody choosing;
  it can't change the winner. Hold points are still added after the Hold
  triggers of that turn have been put on the chain (`_begin_turn`), where the
  rule gives the point first: a Hold trigger that burns its controller out
  while the Hold itself is the winning point would be judged in the wrong
  order. Not seen, not fixed (it needs the Hold to gain its point inside
  `_phase_beginning_steps`).

### D7. An Equipment is trashed when its unit is banished

- **Rule.** §719.5: "When a Top-Most Card changes zones from a board zone to a
  non-board zone, all Attached cards Detach from it, remaining in their
  current zones." §436.4.b: the Equipment detaches to "the last location the
  Top-Most Card was at", and §436.4.a: "it will be Recalled during the next
  Cleanup".
- **Engine.** `effects.py:961-983` (`_banish_unit`): "its gear goes to the
  trash". A unit that dies or returns to hand leaves its Equipment in its
  controller's base (checked: correct).
- **Cards.** Wind and Ghosts ("If it has 3 [might] or less, banish it"), Mel
  Defiant Soul ("banish an enemy unit at a battlefield with 3 [might] or
  less") against Shen's Hand Hammer (2 copies).
- **Test.** `test_an_equipment_stays_when_its_unit_is_banished`.
- **Weight.** ~1% of games. Zed gets a two-for-one the rules don't give.
- **Fixed.** In `_banish_unit` the gear goes to its controller's base
  (`base_gear`), as on death. No golden game changes.

### D8. A unit played from facedown in the Main Phase chooses anywhere

- **Rule.** §811.1.d.3: "If a play effect of a hidden permanent chooses any
  targets, those targets must be chosen from among options at the battlefield
  it was played to".
- **Engine.** `_play_from_hidden` (`loop.py:3628`) marks the card
  (`_hidden_bf`) while it plays it and removes the mark in `finally`
  (`loop.py:3650`). Played as a turn action, the play effect is a pending
  trigger that goes on the chain after the action (`_apply_action` is a task),
  when the mark is gone: `_resolve_targets` (`effects.py:4020`) no longer
  restricts it. Played inside a showdown or on a chain the trigger is flushed
  at once and the restriction holds (checked: correct).
- **Card.** Kennen Keeper of Balance: "When you play me ..., you may pay [2] to
  STUN a unit."
- **Test.** `test_a_unit_played_from_facedown_in_the_main_phase_chooses_at_its_battlefield`.
- **Weight.** 1 game in 400. Kennen is one card, and the play that shows the
  bug (from facedown in one's own Main Phase) is not the usual one.
- **Fixed.** The play effect's pending trigger carries the mark in its flags
  (`_resolve_card_effects`), put back on the card while the ability is
  finalized and resolves (`_card_flags`). No golden game changes.

### D9. An activated ability can be paid for with no legal target

- **Rule.** §403.3: "If legal options are not available for an Activated
  Ability, it is not legal to activate it." §355.8: "In order to put a spell or
  ability on the chain, valid choices must be made for all targets." §355.4.a:
  "A valid Location for a Move Effect is one other than the Units' current
  Location".
- **Engine.** `_ability_usable` (`loop.py:5907-5998`) checks the cost and the
  condition, never the targets (a spell's are checked: `_spell_has_targets`).
  Shen Eye of Twilight ("ACTION [tap]: Give a friendly unit TANK this turn")
  is offered with no friendly unit on the board; Zed Without a Sound ("ACTION
  [1] [Chaos]: Move me and a Shadow Clone you control to each other's
  locations") with the only Clone at Zed's own location, where it costs [1]
  [Chaos] and does nothing (`effects.py:4953`).
- **Tests.** `test_shen_eye_of_twilight_needs_a_friendly_unit`,
  `test_zed_without_a_sound_needs_a_shadow_clone_somewhere_else`.
- **Weight.** The most frequent of all: `simple_trade` taps Shen's legend into
  nothing in every game (turn 1), `random` in half; Zed's swap is wasted in
  ~30% of games. It can't be exploited (the player only loses resources), but
  these are illegal actions in the legal set, visited by self-play and MCTS,
  and the legend is then exhausted for the showdown where it matters.
- **Fixed.** `_ability_usable` ends with `_ability_has_target`: for an ability
  that chooses one unit, `effects.has_valid_target` (every location when the
  text names no place); for `swap_position`, a unit to swap with at another
  location. Across the ten decks it now refuses, with no legal target: Shen Eye
  of Twilight, Zed Without a Sound, Yasuo Unforgiven ("Move a friendly unit to
  or from its base"), The List (no unit with the named tag), Kennen Heart of
  the Tempest. 12 golden games change: all those `simple_trade` plays with the
  Yasuo deck, where it used to pay [2] and exhaust Yasuo Unforgiven on turn 1
  with no unit to move; it now plays a unit instead.
- **Left over (card data, other decks).** Kennen Heart of the Tempest's "Give a
  unit ASSAULT 2" is encoded as "a friendly unit": with only enemy units on the
  board the ability is now refused, though by the print an enemy unit is a
  legal (and pointless) choice.

### D10. A REACTION unit can't be played to base at reaction speed

- **Rule.** §813.1.c.1: "This can be played during Closed States on any
  player's turn." §813.1.b: "Reaction grants ... all abilities and permissions
  of Action" (showdowns). §813.3.a: "Playing Units with Reaction still has the
  inherent restrictions of playing Units without Reaction. It can only be
  played to the controlling player's base or a battlefield they control."
- **Engine.** `_ambush_unit_lanes` (`loop.py:5045`) lists battlefields only;
  `legality.py:192-197` and `225-231` offer a REACTION unit only there (during
  a showdown: only at the showdown's battlefield, and "to base" only for the
  ACTION keyword).
- **Card.** Shen Kinkou (1 copy).
- **Tests.** `test_a_reaction_unit_can_be_played_to_base_in_a_closed_state`,
  `test_a_reaction_unit_can_be_played_to_base_during_a_showdown`.
- **Weight.** Low: a missing option, and rarely the best one (the unit enters
  exhausted in base).
- **Fixed.** On a chain a REACTION unit is also offered "to base"
  (`("UNIT", idx, 0, base index)`, played by `_play_ambush_unit`); in a showdown
  it is offered like an ACTION unit (to base). Third test:
  `test_a_reaction_unit_played_to_base_on_a_chain_enters_there`. No golden game
  changes.

### D11. REACTION plays in a showdown only at its battlefield

- **Rule.** §822.1.b (AMBUSH): "I may be played to a battlefield where you
  control Units" and "I have [Reaction] as long as I'm being played to a
  battlefield where you control Units." §811.6: a facedown card "may be played
  any time a card with Reaction may be played". Neither names the showdown's
  battlefield.
- **Engine.** `legality.py:229-231` (AMBUSH and REACTION units: `lane in
  _ambush_unit_lanes`, the showdown's lane only) and `legality.py:244`
  (`only_lane=lane` for facedown cards); `_showdown_step` plays a facedown card
  at `bf_idx` whatever the action says (`loop.py:7586-7589`). On a chain
  (`_reaction_actions`) every battlefield is offered.
- **Test.** `test_ambush_and_facedown_plays_at_another_battlefield_during_a_showdown`.
- **Weight.** Low: a missing option (Soulspinner, Morgana, Shen Kinkou, the
  facedown cards), useful when the fight is lost and the other battlefield is
  the one to reinforce before the Hold.
- **Fixed.** `_showdown_actions` offers every battlefield `_ambush_unit_lanes`,
  `_ambush_legal_lanes` (the champion) and `_hidden_playable` return;
  `_showdown_step` plays at the battlefield the action names. Second test:
  `test_a_unit_ambushed_and_a_card_played_from_facedown_elsewhere_during_a_showdown`.
  No golden game changes.

## Deviations, priority 2: `docs/MECHANICS.md` PARTIAL / GAP rows

### D12. TANK + BACKLINE on one unit: no choice for the assigner

- **Rule.** §467.2.c.8: "If a Unit has one or more Abilities or effects applying
  to it that demand it be assigned damage in a specific way that is
  exclusionary, then the assigning player chooses only one of those abilities
  to apply when assigning damage."
- **Engine.** `combat.py:194-209` (`_ordered_targets`): "we resolve
  deterministically as Tank".
- **Test.** `test_the_assigner_chooses_between_tank_and_backline_on_one_unit`
  (`tests/audit/test_audit_mechanics.py`).
- **Weight.** None for Zed vs Shen (no BACKLINE; Shen's legend gives TANK only
  to Shen's units). Other decks: a BACKLINE unit given TANK.
- **Fixed.** One more choice, `combat_tank_or_backline` (the assigner's;
  baseline TANK, as before), per such unit as the damage order is built. The
  audit test answers that choice (it was written against the order choice,
  which is not where the rule puts the decision); a second test checks the
  TANK answer. No golden game changes. Like the other choices made inside an
  action, the net-guided search doesn't make it yet (BACKLOG O3).

The other rows, re-read against the code and tests:

| Row | Finding |
|-----|---------|
| 823 Hunt (PARTIAL) | Correct: printed and granted values add up (§823.2), XP on Conquer and on Hold. Checked by play (Scorchclaw HUNT 2 + granted HUNT 2 = 4 XP). The row can be DONE. |
| 824 Level (PARTIAL) | Not re-checked beyond the existing tests: the controller change (§824.1.c.1) is not tested. |
| 825 Unique (GAP) | Deck construction only (§825.4); decks are not validated at all (see "Not checked"). |
| 826 Backline (PARTIAL) | D12. |
| 827 Empower, 828 Empowered (PARTIAL) | The row is stale: stacking is in (`empower_times`, `tests/test_empower_family.py`), "When I become EMPOWERED" triggers (Mel Defiant Soul, checked by play). The row can be DONE. |
| 829 Flow (PARTIAL) | The row is stale: play from trash for the Flow cost, then banished, at the spell's own timing. Checked by play: the seven Flow costs of the precons. The row can be DONE. |
| 830 Deploy (PARTIAL) | Not re-checked ("Deathknells here trigger twice", Jarvan's ACTION). |
| Targeting + Deflect (PARTIAL) | The row is stale for abilities: DEFLECT is charged to an ability's choice too (Mel Defiant Soul's banish choosing Steel Paws, checked by play). |
| 822 Ambush as a verb | Not re-checked. |

## Deviations, second pass (2026-11-11): the turn's start and the scoring

Tests in `tests/audit/test_audit_mechanics.py` (D19, D20) and
`tests/audit/test_audit_precon_rules.py` (D22). Line numbers here are those of
`95ca177`, the commit this pass started from.

### D19. The Start of Turn: Channel, Hold, then the start-of-Beginning abilities

- **Rule.** §315: Awaken Phase (315.1, ready), Beginning Phase (315.2.a "At
  the start of Beginning Phase game effects take place", 315.2.b the Scoring
  Step: "The Turn Player Holds all Battlefields they Control"), Channel Phase
  (315.3), Draw Phase (315.4). §816.1.b: TEMPORARY is "At the start of this
  permanent's controller's Beginning Phase, before scoring, kill this."
- **Engine.** `loop.py:895-995` (`_phase_beginning_steps`): TEMPORARY kills,
  then ready, then the turn's runes, then the Hold; `loop.py:8076`
  (`_begin_turn`): the "at the start of your Beginning Phase" abilities fire
  after the Hold and its victory check.
- **Cards.** Shen: Grove of the God-Willow, Shen Scourge of Shadows, Shen
  Leader of the Kinkou Order (Hold abilities); Zed: Shadow Temple. The player
  could react to them (Ki Barrier) with the two runes of the turn. Other
  decks: Frozen Fortress (vendetta_ezreal) and Dusk Rose Lab say "This happens
  before scoring" and happened after; Jinx Loose Cannon, Dr. Mundo Expert,
  Sprite Queen, Mushroom Pouch, The Arena's Greatest, Gutter Palace.
- **Tests.** `test_frozen_fortress_deals_its_damage_before_the_hold`,
  `test_a_start_of_beginning_ability_resolves_before_a_hold_that_wins`,
  `test_the_runes_of_the_turn_are_channeled_after_the_hold`; and
  `test_the_runes_in_play_pay_for_a_reaction_to_a_hold_ability` (what must
  stay).
- **Fixed.** `_phase_beginning_steps`: ready (the readied runes' Energy and
  Power go to the pool at once, as the engine pays from it), TEMPORARY kills
  and `on_start_of_turn`, the Hold, then the turn's runes. No golden game
  changes. `tests/test_corpus_vendetta.py` fired `on_start_of_turn` by hand
  after `_phase_beginning`: it is part of it now.
- **Left.** The victory check after the Hold is still made after the Channel
  (the game is over either way). Forsaken Baccai and Oasis Raider ("fewer
  runes than an opponent at the start of your Beginning Phase") still read
  `runes_at_beginning`, a count taken before the phase: right, and no longer
  needed.

### D20. No Conquer of a battlefield lost and taken back in one turn

- **Rule.** §471.1: "Conquer: A player gains Control of a Battlefield they did
  not yet Score this turn." §472: once per battlefield per turn.
- **Engine.** `battlefield.py:239` (`can_score_conquer`): no Conquer for the
  side alone there as the turn started (`last_controller`), whatever happened
  since.
- **Test.** `test_a_player_conquers_a_battlefield_lost_and_taken_back_in_one_turn`
  (two Charms: out to base, back); and
  `test_a_defender_who_keeps_the_battlefield_does_not_conquer_it` (what
  `last_controller` was there for).
- **Weight.** Needs an effect that moves or plays a unit of the non-turn
  player (Charm, Moonfall, a REACTION unit) onto a battlefield that player
  lost this turn. In 2 of the 20 golden games: Diana's Moonfall moving an
  enemy unit onto the battlefield its player had just left.
- **Fixed.** `Battlefield.gained_control`: the side that gained Control this
  turn and has it since (set as Control passes to a side, not when a contest
  gives it back to its holder; cleared as the turn starts). `can_score_conquer`
  asks for it. `last_controller` stays for the golden signature only. 2 golden
  games regenerated.

### D22. A Hold gives its point after its abilities resolve

- **Rule.** §473: "When a player Scores, two things occur: 473.1 The player
  Gains up to one Point ... 473.2 Trigger Score abilities at the Battlefield
  that Scored." §474: the win is checked at the next cleanup.
- **Engine.** `loop.py:983-995`: the Hold's points are counted
  (`_points_allowed`) and given by `_begin_turn` after the phase
  (`loop.py:8063`); the Hold abilities resolve in between.
- **Cards.** Zed: Shadow Temple ("When you hold here, BURN 3"), for whoever
  holds it. One point from the Victory Score each and fewer than 3 cards in
  the holder's deck: the Burn Out gave the opponent the game.
- **Tests.** `test_the_hold_gives_its_point_before_a_hold_ability_burns_out`,
  `test_a_hold_ability_sees_the_point_of_its_hold`.
- **Weight.** Not measured: needs a Burn Out (0 / 800 games, D1) at 7-7.
- **Fixed.** The Scoring Step gives each point as it scores (`_gain_points`).
  No golden game changes.

## Deviations, third pass (2026-11-11): the other eight decks, card by card

How it was done: for each of the 119 cards of the eight decks that are not in
the precons (106 Main Deck cards, legends and champions, 13 battlefields), the
printed text and stats of `piltover_archive.json` next to our keywords and
`effects`; then the card played in a hand-made situation wherever the reading
left a doubt or no test names the card (about 60 cards; the others have their
own tests, which were not re-read). Three static scans over the whole corpus
followed the classes found (D23, D24, D28). Tests in
`tests/audit/test_audit_decks.py`.

### D23. An ability with no [Action] is used in a showdown

- **Rule.** §145.2 (units), §151.2 (gear): "may be executed at any time during
  the controlling player's Main Phase during an Open State, and not during a
  Showdown." Only [Action] / [Reaction] widen that.
- **Engine.** `_WINDOW_TIMINGS` is right; the data was not: 39 activated
  abilities of 34 cards carried `"timing": "action"` their card doesn't print
  (the example in `scripts/generate_effects.py`'s prompt has it). Each could
  be used in a showdown, by the defender on the opponent's turn too.
- **Cards.** In the decks: Heart of Dark Ice ("[Tap]: Give a unit +3 [Might]
  this turn", Yasuo) and The List (Ezreal). In the corpus: Iron Ballista,
  Xerath Freed, Arena Kingpin, Tools of Empire, Whirling Twirligig, Pitiless
  Stalker and 26 more.
- **Tests.** `test_a_gear_ability_with_no_action_is_not_used_in_a_showdown`,
  `test_an_ability_has_only_the_timing_its_card_prints` (the whole corpus).
- **Fixed.** `17838db`: the timing removed from the data.
  `test_g3_abilities_on_chain` used Xerath Freed in a showdown: it uses
  Divining Shells (printed [Action]) now.

### D24. QUICK-DRAW attaches only at the battlefield it is played "at"

- **Rule.** §819.1.d: "When you play this, attach it to a Unit you control."
- **Engine.** `_play_gear` offered the units at the lane of the action; none
  there, the gear stayed in base unattached, and a unit in base was never
  offered. Long Sword and Sterak's Gage have an `attach_gear` instruction
  that covered the first case; Cloth Armor, Spinning Axe, Protector's Shield
  and Jax Unmatched's granted Quick-Draw have not.
- **Tests.** `test_quick_draw_attaches_to_a_unit_in_base`,
  `test_quick_draw_chooses_among_all_the_units_you_control`.
- **Fixed.** `6376f85`: every unit of the player is offered, those at that
  battlefield first (the baseline picks among them when there are any).

### D25. Bellows Breath hits units at different locations

- **Card.** SFD-080: "Deal 1 to up to three units at the same location."
- **Engine.** `deal_damage` with `count: 3`, `where: anywhere`: three units
  anywhere.
- **Test.** `test_bellows_breath_hits_units_at_the_same_location`.
- **Fixed.** `4947f42`: `same_location` on the instruction; `choose_many`
  takes `allowed(taken, option)`. Not done: Facebreaker ("a friendly unit and
  an enemy unit at the same battlefield", not in a deck) was not played.

### D26. Ezreal's legend doesn't count an enemy gear chosen

- **Card.** SFD-199: "Use only if you've chosen enemy units and/or gear twice
  this turn with spells or unit abilities."
- **Engine.** `_note_chosen` counts units only. In the deck: Turn to Dust,
  Pickpocket; Detonate in others.
- **Test.** `test_ezreal_legend_counts_an_enemy_gear_chosen`.
- **Fixed.** `a0063f2`: `_note_gear_chosen`, called where a gear is chosen.
  A unit is counted as the spell goes on the chain, a gear as it resolves
  (where its DEFLECT is paid too): the legend can't answer on that same chain
  with a gear's choice. Left as it is.

### D27. Patched Porobot is a unit only

- **Rule.** §178.1: "A Game Object that is more than one type has the
  properties of all of their types"; §178.3: it "can be targeted by spells
  and abilities ... that say 'Kill a unit,' or 'Kill a gear.'"
- **Card.** VEN-058, printed type "Unit Gear": "(I enter exhausted.) When you
  play me, if you control 3 or more other gear, draw 1." The only such card
  in the archive. The owner confirmed it (2026-11-11): a unit and a gear at
  once.
- **Engine.** A `UnitCard`. Not a gear for: Pit Crew ("When you play a gear,
  ready me"), Ornn's Forge (the first gear costs [1] less), Ornn Blacksmith
  and Aspiring Engineer (a gear from the deck / the trash), Veiled Temple,
  Detonate, the gear counts. All of these are in vendetta_ornn, with 3
  Porobots.
- **Tests.** `test_patched_porobot_is_a_gear_too`,
  `test_patched_porobot_is_killed_as_a_gear`,
  `test_patched_porobot_is_the_first_gear_ornns_forge_makes_cheaper`,
  `test_patched_porobot_counts_the_other_gear`,
  `test_patched_porobot_is_a_gear_in_the_deck_and_in_the_trash`,
  `test_a_unit_printed_as_a_gear_keeps_its_might`,
  `test_a_porobot_that_became_a_copy_of_a_unit_is_no_gear`,
  `test_a_unit_that_became_a_copy_of_a_porobot_is_a_gear`.
- **Fixed.** `840876a`. `types: [Unit, Gear]` in the data; the registry sets
  `also_gear` on the card; `cards.is_gear()` is the one question "has the
  gear type", asked by the zone filters (`is_gear`, the legacy `gear`
  filter), Swain's condition, "discard a gear", gear's bonus damage,
  Orianna's discount and the Power earmarked for gear. In play
  `UnitInPlay.is_gear` (a gear Orianna made a unit, `gear_unit`, or a unit
  whose card is a gear too) gives it what Orianna's unit gear already had
  (chosen, killed, readied and counted as a gear). It is read from the card
  the unit is now, so a Porobot that became a copy of another unit (Shady
  Spectacles) is no gear while it is one, and a unit that became a copy of a
  Porobot is (review of PR #19: the first version latched it as the unit
  entered play). Its Might is
  the printed one; Orianna doesn't turn it back into a gear; "3 or more other
  gear" leaves it out. It is still played, moved and paid for as a unit: the
  `isinstance(card, GearCard)` tests that pick how a card is played are
  unchanged. No golden game changed.
- **Checked in the fourth pass, found right.** An Equipment on it: it is
  attached and gives its Might (Long Sword: 4), Detonate offers the Porobot
  and its Equipment as two gears, and the Equipment of a killed Porobot goes
  back to base (§719.5). It is no Equipment: Arise! doesn't count it, Jax's
  legend and Angle Shot don't offer it. The AI encodes it by its card, in the
  unit zones: the net sees which card it is; the gear counts of the encoding
  leave it out (as they leave out Orianna's unit gear).

### D28. Rengar's and Kennen's legends give only to a friendly unit

- **Cards.** Rengar Pridestalker: "give a unit +1 [Might] this turn"; Kennen
  Heart of the Tempest: "Give a unit [Assault 2] this turn."
- **Engine.** `target: friendly_unit` on both.
- **Tests.** `test_rengar_legend_can_choose_an_enemy_unit`,
  `test_kennen_legend_can_choose_an_enemy_unit`.
- **Fixed.** `0ac459e`: `chosen_unit`. Same reading on two cards outside the
  decks, not changed: Navori Fighting Pit ("buff a unit here"), Ambessa
  Matriarch of War ("ready a unit").

### Read, played and found right

Costs, Might, keywords and equipment bonuses of all 119 match the print.
Played and right: En Garde, Gust, Eclipse, Switcheroo, Thousand-Tailed
Watcher (minimum 1), Kinkou Initiate (other units), First Mate, Grim
Apothecary, Aspiring Engineer, Lecturing Yordle, Sterak's Gage, Sprite
Fountain, Treasure Trove, Rhasa the Sunderer, Sky Splitter, Wages of Pain,
Treasure Hunter and Pyke's legend (the Gold enters exhausted), Yasuo's legend,
Yasuo Remorseful (an enemy here), Nidalee, Kai'Sa Survivor, Ferrous
Forerunner, Irresistible Faefolk, Inferna, Minefield, Frozen Fortress (both
players' turns), Seat of Power, the FLOW costs (Lightning Rush, Shuriken Flip,
Up from the Deep), Last Rites' EQUIP cost, Helm of Suppression, Astral Heron,
Emperor's Divide, Pack of Wonders, Deadly Flourish, Detonate, Sabotage, Irelia
Fervent, Darius Trifarian, Mask of Foresight, Hard Bargain, Kennen's legend
(empowered by a FLOW play, not by one from hand), Akali's legend (off its
player's turn it exhausts and does nothing).

Seen on the way, not a deviation of a card: a chooser that raises while a
spell's choices are declared on the copy (`_declare_choices` swallows it)
leaves the spell choosing as it resolves with `choices_noted` set, so "when
you choose me" and DEFLECT are skipped. No agent of the repo raises there.

## Deviations, fourth pass (2026-11-12): outside the ten decks, by class

How it was done. Not card by card: the corpus outside the ten decks is about
930 cards. Four scans over the whole corpus, each followed by reading and
playing what it flagged:
1. every activated ability (138 cards) offered with its source alone on the
   board, with one ready friendly unit, and on a full board (what is offered
   with nothing to choose; what is never offered): D29, and D30-D33 read on
   the way;
2. the 131 cards `piltover_sync.py compare` flags, each read against the
   print with its `effects` (most are the site's typos): D35-D49;
3. cards with printed text and no effect; printed keywords missing from the
   registry (only Grand Strategem); every Equipment's Equip cost and Might
   bonus against the print (only Blighted Battleaxe);
4. the leftovers of D25 / D28 (Facebreaker, Ambessa, Navori Fighting Pit).
Tests in `tests/audit/test_audit_corpus.py`.

- **D29.** §403.3. D9 covered an ability that chooses one unit. Still offered
  with nothing to choose: Jax Grandmaster at Arms (both), Pyke Bloodharbor
  Ripper, Jayce Defender of Tomorrow, Teemo Swift Scout, Akali Rogue Assassin
  (outside a showdown), Maduli the Gatekeeper, Unlicensed Armory, Pack of
  Wonders, Baited Hook, Cursed Sarcophagus. `effects.has_valid_target` now
  asks the handler's own list of options (`_HAS_OPTION`) and looks inside a
  `sequence`. As in D9, "legal" is "the handler has something to do": Jayce's
  "Ready a gear" needs an exhausted gear of yours, though by the print a ready
  or an enemy gear is a legal, pointless choice.
- **D30-D33.** See the table: the handler was narrower than the print.
- **D34.** Seen while reading Mageseeker Investigator:
  `_can_pay_generic_power` wanted all the Power from one domain. One domain is
  still used when it covers the cost, so nothing changes where it did.
- **D35-D49.** See the table. King's Edict: the opponent chooses, among the
  units the caster doesn't control, anywhere (two players only).
- **Read and found right.** Facebreaker (a spell is cast "at" a battlefield:
  both units are there); Wraith of Echoes (not its own death); Xerath Freed,
  Ultrasoft Poro, Renata Glasc ("only while I'm at a battlefield");
  Unyielding Spirit, Symbol of the Solari, Highlander, Possession, Siphon
  Power, Conscription, Emperor's Dais, Diana Lunari, the two AMBUSH errata.
- **Not a deviation, a bug met on the way** (`cc3d776`): the coach kept a
  second answer to one question (a double click) for the next question; the
  game then ended in an error. `tests/test_coach.py` failed about one run in
  four under load because of it.
- **Left open.** Navori Fighting Pit's data now say "a unit here" (no board
  differs). Seraphine Not Alone is marked "Preview Card - Not Legal" on the
  site.

## Deviations, priority 3: card data (BACKLOG O1)

Printed text from `piltover_archive.json`; tests in
`tests/audit/test_audit_card_data.py`. None of these cards is in the precons.

| # | Card | Printed | Ours | Decks | Test |
|---|------|---------|------|-------|------|
| D13 | Stupefy OGN-095 | "Give a unit -1 [Might] this turn, to a minimum of 1 [Might]. Draw 1." | `grant_temporary_might` `amount: 1` (+1) | chaos_mind_diana, vendetta_ezreal | `test_stupefy_gives_minus_one` |
| D14 | Noxus Hopeful OGN-012 | Might 4 | Might 3 | fury_chaos_pyke, vendetta_rengar | `test_noxus_hopeful_has_four_might` |
| D15 | Thrill of the Hunt UNL-184 | Energy 2, Power 1 (Body / Fury) | `cost_power: 2` | vendetta_rengar | `test_thrill_of_the_hunt_costs_one_power` |
| D16 | Pit Crew OGN-091 | "When you play a gear, ready me." | no text, no effects | vendetta_ornn | `test_pit_crew_readies_when_you_play_a_gear` |
| D17 | The Harrowing OGN-198 | "Play a unit from your trash, ignoring its Energy cost. (You must still pay its Power cost.)" | no text, no effects | vendetta_kennen | `test_the_harrowing_plays_a_unit_from_your_trash` |
| D18 | Existential Dread UNL-134 | "[Stun] an attacking enemy unit. If it's already stunned, return it to its owner's hand instead." | `stun_or_return_attacker`: any attacking unit; the attacker can play it on its own | chaos_mind_diana | `test_existential_dread_chooses_an_attacking_enemy_unit` |
| D21 | Moonfall UNL-198 | "Choose a battlefield where you have units. You may move up to one enemy unit to that battlefield. Then give enemy units there -2 [Might] this turn." | played at any battlefield, with no unit of its player there | chaos_mind_diana | `test_moonfall_chooses_a_battlefield_where_its_player_has_units`, `test_moonfall_cannot_be_played_with_no_units_at_a_battlefield` |

D21 was not in the O1 list: seen in the golden games D20 changed (second
pass). Fixed with `battlefield: friendly_units` on the card's first
instruction, read by `_spell_has_targets`; 5 golden games regenerated. No
other spell of the corpus says "a battlefield where you have units".

Read and found equivalent to the print (wording only): En Garde, Yasuo
Remorseful, Ornn's Forge ("When" / "While": encoded as the passive it is),
Fizz Trickster, Emperor's Dais, Diana Lunari, Rengar Trophy Hunter, Death from
Below (errata wording, same encoding). Brutalizer: the site lists no attach
text; ours has one, not compared.

## Ambiguous rules, and engine choices the rules don't dictate

Q1–Q4 answered by the owner (2026-11-11); each change has a test in
`tests/audit/test_audit_mechanics.py`. Q5 is a list, not a question.

- **Q1. Who gets priority first on a chain.** §337.4: after a chain item is
  finalized "the controller of the next item on the chain gains Priority",
  i.e. the player who just played it; the other gets it when that player
  passes (§338.1.b.1). The engine gives the opponent the first word
  (`loop.py:7338`: `active = self.gs.other(caster)`) and the caster the second.
  The same chains can be built either way (each player can still answer the
  other), but the caster decides whether to add to their own spell after
  seeing the opponent pass or react, not before. Keep, or follow §337.4?
  **Answer: follow §337.4.** Fixed in `673643e`: the controller of the newest
  item has Priority first, after each action and after each resolution
  (§340.4). No golden game changed.
- **Q2. Shadow Order Disciple with an empty Main Deck.** "When I move, you may
  BURN 1 to give me +1 [might] this turn": BURN 1 is a cost within an
  instruction. §203.3 says an impossible cost can't be paid; §432.1.b says
  moving a card out of an empty deck is a Burn Out, not an impossibility.
  Since the D1 fix the engine Burns Out (the opponent gains a point) and gives
  the +1; the player can decline the "you may". Is that the reading you want?
  **Answer: yes, kept.**
- **Q3. The 40-turn cap in self-play.** `selfplay.py` and `env.py` build games
  with `max_turns=40`, and a game that reaches it is decided by a two-point
  lead (TR 408.2.b), a draw otherwise (`loop.py:8067`). Riftbound has no turn
  limit; the cap makes "be two points ahead at turn 40" a way to win. None of
  700 random / heuristic games reached turn 40, so today it is only a stall
  guard; a trained, defensive agent may reach it. Should a capped game be a
  draw for training? **Answer: yes, always a draw.** Fixed in `c44d91b`
  (`GameLoop._final_result`); a match still applies the clock's 2-point rule
  through `match._game_result`.
- **Q4. Keeper of Law.** "I cost [2] [order] less if you control a battlefield
  with exactly two units there": the engine counts the units of both players
  there (`loop.py:2884`). On your turn outside a combat only your units are at
  a battlefield you control, so it only matters when Keeper is played... never,
  in practice (it has no REACTION). Left as is; say if "two units" should be
  "two of your units". **Answer: two of your units.** Fixed in `81f90ea`.
- **Q5. Choices the engine makes for the player.** Which rune pays a Power of
  any domain (`player.py:296`: the domain with the most left), the order of
  combat damage beyond the first choice, which unit an effect picks when the
  search doesn't ask (BACKLOG O3): not rules deviations, but decisions the
  rules give the player and the learner doesn't make. Listed so they aren't
  mistaken for audited rules.

## Checked and found correct

Against the rule cited: by play in this audit (scripted situations, traced
games), or, where marked †, by an existing test re-read against the rule and
not played again.

- **Setup, mulligan.** Four cards each; up to two set aside, the same number
  drawn, then recycled to the bottom in a random order (§116-117). The second
  player channels three runes on its first turn (§487.7). Both players draw on
  their first turn (§315.4).
- **Runes, Energy, Power.** Every rune gives 1 Energy a turn; a Power is paid
  by recycling a rune of that domain to the bottom of the Rune Deck (fewer
  runes next turn); unspent Energy of ready runes stays for reactions in the
  opponent's turn; ADDed Energy (Threshold of the Gray) is lost when the Rune
  Pool empties (§164-167). Dual-domain costs take either domain (Death Mark,
  Shadow Dash).
- **Playing.** Units enter exhausted, to base or a battlefield their player
  controls; a permanent's "when you play me" goes on the chain and can be
  answered; a spell needs a legal target to be played (§355.8); optional
  additional costs (Zed From the Shadows†, Gust Monk†, Ruthless Strike).
- **Chain.** Reactions in a closed state, last in first out, priority again
  after each resolution (§340.4); non-REACTION cards refused on a chain; no
  window after a Standard Move (§448.3.c).
- **Movement.** Standard Move exhausts; base to battlefield and back;
  battlefield to battlefield only with GANKING (Kinkou Lifeblade empowered);
  several units to one battlefield as one move; none during a showdown.
- **Contest, showdown, combat.** A unit moved by an effect contests like any
  move: Charm moving an enemy unit to an open battlefield gives that enemy the
  showdown, the focus and the Conquer; Shadow Dash pulling an enemy unit onto
  Shen's units makes that enemy the Attacker, Shen's units Defenders with
  their SHIELD (§466.2.c.1). Focus to the player who contested, passes in
  turn, ACTION / REACTION only. ASSAULT attacking, SHIELD defending, TANK
  first†, lethal before the next unit, stunned units deal nothing†, damage
  already marked counts, Ki Barrier's 7 counts toward lethal (§438.5.a).
  Attackers recalled when defenders are left (§468.1.a.2). Two attacks on one
  battlefield in a turn.
- **Scoring.** Hold in the Beginning Phase for each battlefield controlled;
  Conquer once per battlefield per turn; the Final Point by Conquer only with
  every battlefield scored this turn, a card drawn otherwise, the Conquer
  effects still trigger (§473.1.b); Shen Leader's extra point is not a Conquer
  and is not restricted (§473.1.a.1).
- **Burn Out on a draw†.** Trash recycled, the opponent gains a point, the draw
  completes (§432.2).
- **HIDDEN.** [A] to hide at a battlefield you control with room; playable from
  the next turn, for [0], at reaction speed; a unit enters at that
  battlefield; a spell's and a play effect's targets at that battlefield when
  played in a showdown or on a chain (Resonating Strike: the battlefield is
  the hidden one, the unit comes from elsewhere, §811.1.d.4). The champion can
  be hidden from the Champion Zone.
- **EMPOWER / EMPOWERED.** Only in its controller's own Main Phase, not in
  showdowns or the opponent's turn; costs (Energy, Power, "Discard 1",
  "Discard a spell")†; EMPOWERED bonuses†; Mournful Witness after a combat†; Mel's banish; Noxian Emissary's EMPOWERED DEATHKNELL.
- **FLOW.** The seven Flow costs of the precons, the spell's own timing†, the
  spell banished after† (which empowers Zed Master of Shadows†).
- **DEFLECT.** Charged to spells and to abilities that choose the unit; with no
  Power to pay it the unit can't be chosen (Steel Paws, Serene Ascetic).
- **Legends.** Shen's and Zed's ACTION abilities are offered in showdowns on
  either player's turn; Zed's needs him EMPOWERED.
- **Equipment.** Hand Hammer goes to base when its unit dies or returns to
  hand (§719.5).
- **The 51 cards.** Each encoding read against its printed text;
  `tests/test_precon_cards.py` plays each sentence. Beyond those tests:
  Loyal Poro draws when two die together; Twilight Shroud stops enemy spells
  from choosing the unit; "exactly one other unit you control here" is false
  in base; Kennen's stun from facedown in a showdown stays at its battlefield.
- **Robustness.** 550 random games of the two precons and 180 across the other
  eight decks: no exception, no skipped effect (`[EFFECT-SKIP]`), every card
  in exactly one zone at every decision.

## Not checked

- **Seen in the code, not tested** (second pass). A unit taken off the board
  by `_take_off_board` (returned to hand, recalled) leaves its battlefield's
  `held_by` as it was until the next `Battlefield._note_control`; every reader
  goes through `control()`, which calls it, so nothing was seen to go wrong.
  A battlefield still Contested as a turn starts (both sides there) is held
  by nobody for `can_score_hold`, which reads `controller()`, not `control()`.
- **Not checked.** Deck construction (§103: 40 cards, 3 copies, domain
  identity, signature cards, Unique); the match procedure (`core/match.py`:
  best of 3, sideboards, the clock) beyond reading TR 404-408; replacement
  effect ordering (§372-373); layers and dependencies (§475-482) beyond the
  cases above; "this turn" keyword grants given twice to one unit; copy
  effects; three-player rules (not modeled).
- **The corpus.** The eight decks were read card by card in the third pass
  (see there for what "read" means: about 60 of the 119 cards were checked
  only by reading, their existing tests trusted). Outside the ten decks
  (about 930 cards) the fourth pass read only what its scans flagged: a card
  whose text matches the site and whose effects are wrong in a way no scan
  looks for (a target narrower or wider than the print, a missing clause) is
  still there. D40, D41, D45 are of that kind and were found only because
  the site's wording differed from ours.
- **The AI side.** Encoding, search and coach were read only where a fix
  touches them.
