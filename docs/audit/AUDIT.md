# Rules audit of the engine (2026-11-10)

The engine checked against `docs/rules/CORE_RULES.md` (revision 2026-10-09),
`docs/rules/TOURNAMENT_RULES.md` and the printed card text
(`riftbound/data/reference/piltover_archive.json`), in this order: the two
training precons (`precon_zed`, `precon_shen`) and the rules they play by; the
PARTIAL / GAP rows of `docs/MECHANICS.md` (again in the sixth pass); the
other eight decks, from `BACKLOG.md` O1.

Every deviation below has a test in `tests/audit/` that plays the situation and
checks what the rules or the card say. In phase 1 (`4af83ef`) each test was
marked `xfail(strict=True)`; each fix, one commit per deviation, removed its
marker. Line numbers are those of the commit this audit started from
(`ec62750`).

**The eight non-precon decks were removed on 2026-11-12** (out of date; the
owner will give two current competitive decks). Their passes (D13-D18,
D23-D28) stay: they fixed cards, which are still in the corpus; where this
document names those decks it is the record of where a card was found.

**Kai'Sa and Kennen are no longer played (2026-11-17)**: the 2026-11-13 bans
hit both. The owner's post-ban decks are `competitive_evelynn` and
`competitive_khazix` (seventh pass); the two old files stay, with their tests
and golden games, as engine fixtures.

**After the freeze (2026-11-25):** D72-D76 found in games in the coach page, fixed in Rust on the
rules profile 6427b90+D72-D76 (the default stays 6427b90, identical to Python; `docs/RUST.md`, "Profili
delle regole"). Tests `tests/rust/test_d72_d76.py`, red first (`d6e5e32`), then the fixes (`92a42e8`).
D77 (25/11) fixed in Rust on a new profile, 6427b90+D72-D77 (6427b90+D72-D76 stays as it is, so the
runs trained on it stay reproducible): test `tests/rust/test_d77.py`, red first (`46afd65`), then the fix
(`9fcdc25`) (section "Deviations after the freeze"). D78-D80 (25/11) fixed in Rust on a further profile,
6427b90+D72-D80 (the other profiles stay as they are): tests `tests/rust/test_d78_d80.py` (red first, then
each fix: D80 `09d9384`, D79 `11374fa`, D78 `be38cf7`). D71 is reserved for the Switcheroo proposal of
`docs/bot/GIOCATE.md`, not registered here yet.

**State (2026-11-19, ninth pass): 70 deviations found, 63 fixed, 7 open (D59-D65).**
The ninth pass is the Chosen Champion's copies (D69-D70), met with 82FAW's
Ivern list on RiftAtlas: the deck now loads as `competitive_ivern.json`.
Red tests first; golden games identical. Suite: 1860 passed, 5 skipped, no xfail.
Before it, (2026-11-17, eighth pass): 68 found, 61 fixed, 7 open (D59-D65).
The eighth pass is an external review of the engine (reports in
`docs/audit/revisione_esterna/`, checked in this repository as its section
says): D59-D65 are open and, unlike earlier passes, have no test yet; the
order of the fixes is in `docs/PIANO_MOTORE.md`. D66-D68 (the copies of the
game, its phase 1) are fixed, red tests first. Suite: 1831 passed, 6 skipped
(no torch or sqlalchemy in that environment), no xfail.
Before it, (2026-11-17, seventh pass): 58 found, 58 fixed, none open.
The seventh pass read the owner's two post-ban decks: D57-D58, see its
section; the owner answered Q6. Suite: 1786 passed, 5 skipped, no xfail.
Before it, (2026-11-12, sixth pass): 56 found, 56 fixed.
The sixth pass re-checked the PARTIAL / GAP rows of `docs/MECHANICS.md` and
took two Codex review comments: D53-D56, see its section. Suite: 1755
passed, 5 skipped, no xfail. The fifth pass read the owner's two competitive decks
(`competitive_kaisa`, `competitive_kennen`): D50-D52. The fourth pass went outside the
ten decks, by class and not card by card (D29-D49; no golden game changed):
see its section for what was scanned and what was not read. The third pass
read the 119 cards of the other eight decks against the printed text and
played them in the engine (D23-D28; no golden game changed). The second pass
tested the two suspected deviations the first one left in "Not checked" (D19,
D20) and fixed the two it met on the way (D21, D22). The owner answered Q1–Q4
of "Ambiguous rules" (2026-11-11) and Q6 (2026-11-17): Q1, Q3 and Q4 changed the engine, Q2 kept
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

## The Python engine is frozen (2026-11-24)

The rules of reference are the Python engine at `6427b90`; the PPO agent's
version is the one with `f8a50e4` (the `made` context of `PPOAgent.inner`
keyed by the objects). The double fix of the EK porting (a fix in Python, the
same change in Rust) ends here. Every run records the rules, the commit, the
engine each matchup played on, the lists (by content), the card registry and
the checkpoints (`riftbound/provenienza.py`, `provenienza.jsonl` in the run).

From now on:
- **An ordinary defect** goes here with a minimal position, the rule or the
  card text, the outcome seen and the one expected. It is fixed once, in
  Rust, as soon as Rust runs that flow. If it changes materially the actions,
  the training data or a promotion decision under way, only the exposed run
  is suspended or moved to the corrected path; if that run must go on on
  Python, the minimal fix goes there too and is checked on both engines.
- **An intentional correction** keeps the historical comparison and adds a
  Rust test with the outcome the rules prescribe, at the first transition
  that must change (e.g. an ability chosen while a move is pending: does it
  resolve? A game with the same winner can still have lost that choice).

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
| D50 | A HIDDEN gear played from face down goes into no zone | §737.1 | competitive Kennen (2 Edge of Night) | fixed, `df33571` |
| D51 | A Standard Move doesn't fire "when I become exhausted" | §144.2 | competitive Kennen (2 Reckless Innovator) | fixed, `0e03237` |
| D52 | Decree of Unity is cast with no enemy Chaos unit or gear | §355.8 | competitive Kennen (sideboard) | fixed, `334e93c` |
| D59 | An ability chosen in a reaction/showdown window while a Standard Move is pending is not performed (counts as a pass) | §144.3, §323.11, §430.2-3 | 17 times in 576 games of the six decks (Gold, Seal of Discord, Kai'Sa legend) | open, no test |
| D60 | A gear that draws, played in a showdown, counts as a pass | §337.2, §348 | constructed (Jarvan IV + Detonation Amplifier / The Good Stuff); not seen in games | open, no test |
| D61 | A free champion hide (Teemo Scout, Guerilla Warfare) ends the Main Phase | §811.1.b | outside the decks | open, no test |
| D62 | After an Add ability in a chain the pass streak is not reset: the opponent loses a chance to respond | §339.1, §337.2 | 1 golden game, 3 times (same final state) | open, no test |
| D63 | A multi-unit Standard Move is declared one unit at a time, after the first unit's triggers | §144.3, §421.3 | 2 golden games | open, no test |
| D64 | "If this kills it" and Alpha Strike's XP count a unit banished instead of dying | §429.1, §370.1.a.1 | outside the decks (Smite + Disintegrate / Alpha Strike) | open, no test |
| D65 | A once-per-turn ability stays used after its card leaves the board and comes back as a new object | §124, §377.2.b | outside the decks (Riven Deserter + Temporal Breach) | open, no test |
| D66 | A copy of the game forgets once-per-turn uses (`once_per_turn_used` keyed by `id()`) | search copies | 3 of 3,123 copy points (Pyke Returned); Black Market constructed | fixed, `b6e6c76` |
| D67 | A copy of the game forgets who attacks and defends (`combat_designated` keyed by `id()`) | search copies | 58 of 3,123 copy points (Kha'Zix Mutating Horror, Shadow Clone, Twilight Reveler, Kennen) | fixed, `d4bc220` |
| D68 | A copy of the game forgets "return to base on conquer" (`conquer_return` keyed by `id()`) | search copies | constructed (Relentless Pursuit) | fixed, `ca16a51` |
| D69 | The deck loader refuses the Chosen Champion in the Main Deck | §103.3.b.1 | not in these decks; 82FAW's Ivern list (champion + 1) didn't load | fixed, `e2d6b2e` |
| D70 | Hallowed Tomb returns only the card chosen as champion, not a copy in the trash | §103.3.a.3 | not in these decks (reachable since D69) | fixed, `c008776` |
| D72 | Rengar Trophy Hunter can't be played to a battlefield where only enemy units are: from hand never, from the Champion Zone only at reaction speed | §822.1.b, §822.1.d, UNL-120 | Evelynn, Kha'Zix, Sett (hand), Rengar (champion): a missing option; seen by the owner in the coach page | fixed in Rust on the profile 6427b90+D72-D76, `92a42e8` |
| D73 | A unit played with AMBUSH into a showdown misses the battlefield's passives until the next recompute | §822, Packed Amphitheater | seen by the owner (Rengar Trophy Hunter at 6, not 7): the showdown's decisions see the wrong Might; combat is right | fixed in Rust on the profile 6427b90+D72-D76, `92a42e8` |
| D74 | Pillaged Armory buffs only a friendly unit at its own battlefield | Pillaged Armory (gear, DEPLOY) | Sett (deck): seen by the owner, a unit in base not offered | fixed in Rust on the profile 6427b90+D72-D76, `92a42e8` |
| D75 | Sett Kingpin never gets +1 for the buffed friendly units at its battlefield (the passive is ignored); the data also leaves itself out | Sett Kingpin | Sett (champion): seen by the owner, a buffed Kingpin at 6 instead of 7 | fixed in Rust on the profile 6427b90+D72-D76, `92a42e8` |
| D76 | "When you conquer, ready me" on a legend never readies it (Sett The Boss) | Sett The Boss; Irelia Blade Dancer, Sivir Battle Mistress | Sett (legend): its save stays used until the next turn | fixed in Rust on the profile 6427b90+D72-D76, `92a42e8` |
| D77 | A showdown staged by a trigger of a Standard Move that isn't held waits for the next action that isn't a move (or the end of the turn) | §462, Irresistible Faefolk | Sett (deck): seen by the owner, Pillaged Armory played and a defender buffed before the showdown | fixed in Rust on the profile 6427b90+D72-D77, `9fcdc25` |
| D78 | "They can't move it this turn" (Vex Apathetic) stops only the Standard Move, not a move by its controller's spell or ability | §451, CORE_RULES example of Vilemaw's Lair and Flash | Evelynn (Vex) against Sett (Showstopper): seen by the owner in the coach page, Sett Kingpin moved from base on the turn Vex stunned it | fixed in Rust on the profile 6427b90+D72-D80, `be38cf7` |
| D79 | A card played from face down in a showdown or as a reaction: its own "when you play me" goes on the chain and resolves before the other triggers of the same play (Evelynn Agony's Embrace) trigger | §383.3, §383.4.a | Evelynn (Bedeviling Stranger + legend): seen by the owner in the coach page, the legend's draw/discard after the Stranger's bounce had resolved | fixed in Rust on the profile 6427b90+D72-D80, `11374fa` |
| D80 | Points keep counting after the winning one: holding two battlefields at 7 ends 9 to 4 | victory at the Victory Score | Evelynn against Sett: seen by the owner in the coach page (end of game "9 a 4"); the winner is right | fixed in Rust on the profile 6427b90+D72-D80, `09d9384` |

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

## Deviations, fifth pass (2026-11-12): the two competitive decks

The owner's lists (Kai'Sa: Kai'Sa Daughter of the Void, Kai'Sa Survivor;
Kennen: Kennen Heart of the Tempest, Kennen Storm of Shuriken), imported as
`competitive_kaisa.json` and `competitive_kennen.json`, sideboards included.
55 cards: 33 already read (the removed decks of the third pass, the
precons), their tests trusted; the 22 others read against the print with
their `effects`, and the doubtful ones played. Then 480 games of the four
decks with `simple_trade` and `random` under the checks of
`tests/test_invariants.py` (card conservation, no aliasing, resources).
Tests in `tests/audit/test_audit_competitive.py`.

- **D50.** `_play_from_hidden` played every non-spell as a unit: Edge of
  Night and Zhonya's Hourglass, the two HIDDEN gears of the corpus, left the
  Facedown Zone for no zone. Played as gear now; Edge of Night's errata
  ("attach it to a unit you control (here)") chooses among the units there.
- **D51.** The Standard Move took the unit off its location, then exhausted
  it (§144.2): `_exhaust` found no controller and fired nothing. Six cards
  have such abilities (Reckless Innovator, Riven Broken Blade, Strigian
  Oracle, Seraphine Not Alone; Riven Deserter for another unit; Resplendent
  Rostrum is a gear). Attacking and other exhausts were right.
- **D52.** §355.8: `kill_unit_or_gear` was unknown to `has_valid_target`.
- **Read, played and found right.** Kai'Sa's legend (its Power pays only a
  spell), Plundering Poro and An Offer You Can't Refuse (the Gold enters
  exhausted), Reckless Innovator's Gold, Smoke Screen (minimum 1), Bilgewater
  Tracker (two different units), Brittle Steel's FLOW. Read and right:
  Brynhir Thundersong, Hextech Ray, Temporal Breach, The Empyrean, Time Warp,
  Rockfall Path, Decree of Insight, Decree of Rage, Abandon, Bedeviling
  Stranger, Hidden Blade, The Good Stuff, Trifarian Captain.
- **Seen on the way, a test and not the engine.** The invariant test took a
  card hidden at a battlefield for a vanished one, and a [Reaction] ability
  or a [Reaction] spell by FLOW on an open chain for an illegal action.

## Deviations, sixth pass (2026-11-12): the MECHANICS.md rows

The eight PARTIAL rows and the GAP row of `docs/MECHANICS.md` (BACKLOG O2),
each read against its rule and the code, then pinned by a game situation
(`tests/audit/test_audit_mechanics_rows.py`); the decks' cards first
(Empower and Empowered: Zed, Shen, Kennen; Flow: all four; Deflect: Shen,
Decree of Insight; Deploy: The Good Stuff). Two Codex review comments on the
branch were checked: both right (D53, and the round robin's default glob,
which named the removed decks).

- **D53.** Edge of Night's "attach it to a unit you control (here)" fell
  back to units at other battlefields and in base when none of yours was
  there (the battlefield still yours, contested): `_resolve_targets` looks
  elsewhere when nothing is here, and the face-down mark was gone by the
  time the play trigger resolved. `here` now never falls back.
- **D54.** Kai'Sa Daughter of the Void's spell-only [rune] (and Lux
  Crownguard's spell Energy) didn't pay a FLOW cost: Brittle Steel from the
  trash wasn't offered.
- **D55.** Abandon on a spell played with FLOW put it back in hand, still
  marked, so its next normal cast was banished. §829.1.b.1 with §372: in
  either order of the two replacements it ends banished.
- **D56.** Disempower took every EMPOWERED status (§443.1.b: one); Lacerate
  killed a Kayle Justified empowered three times, and its baseline, weighing
  targets, reset the count of a Kayle it didn't choose. Only Kayle stacks.
- **Checked and right.** Deflect: per unit chosen, by spells and abilities
  (Mel Defiant Soul's trigger pays for Steel Paws), any domain, summed,
  waived by Decree of Insight; the old per-battlefield surcharge is gone, the
  row was stale. Hunt (per unit, summed, conquer and hold), Level (the
  current controller's XP), Backline (after every non-Backline unit), Deploy
  (any battlefield), "When I become EMPOWERED" (Mel), EMPOWERED DEATHKNELL.
- **Replacement effects (§367-373) and layers (§475-482), the decks' cards.**
  Scanned the four decks for "instead", "would", "as", "becomes", "minimum",
  "swap", "copy", "maximum". Right: Ki Barrier (bonus damage prevented too,
  §438.1.a.1; lethal counts the shield, §438.5.a; fully prevented is not
  dealt, §438.4), Nocturne Horrifying (offered as it is looked at: dig,
  predict), Abandon against FLOW (D55), "enter ready"; "to a minimum of 1"
  snapshotted as it applies (§479.4.b: Thousand-Tailed Watcher, Smoke Screen,
  Stupefy), Dragon Form's base Might before the arithmetic (§479.2), Switcheroo,
  Might below 0 counted as 0 (§143.2.c). Zhonya's Hourglass is in no deck.
- **Left open.** A FLOW cost takes cost auras only (Stargazer); the other
  increases and discounts of §356.3-4 are not applied to it (none in the four
  decks). Unique: deck construction only (§825.4), with §103. Several death
  replacements on one death apply in a fixed engine order, not the one their
  controller picks (§372), and one Zhonya's Hourglass saves the first of
  simultaneous deaths, not the one chosen (§373): no such card in the decks.
  Layer dependencies (§480-481: "increased to", "to a maximum") are in no deck.

## Deviations, seventh pass (2026-11-17): the owner's post-ban decks

The owner's lists (Evelynn: Evelynn Agony's Embrace, Evelynn Entrancing;
Kha'Zix: Kha'Zix Voidreaver, Kha'Zix Mutating Horror), imported as
`competitive_evelynn.json` and `competitive_khazix.json`, sideboards
included; no banned card. 28 cards not in the audited decks: 8 read in the
third pass (Irresistible Faefolk, Punch First, Rampage, Rengar Trophy Hunter,
Sabotage, Sandswept Tomb, Up from the Deep, Vex Apathetic), their tests
trusted; the 20 others read against the print with their `effects`, and all
played but Unyielding Spirit (read: its prevention covers "spell" damage,
which in `_take_damage` is spells and abilities). Then 480 games of the two
decks (with each other, themselves and the precons; `simple_trade` and
`random`) under the checks of `tests/test_invariants.py`. Tests in
`tests/audit/test_audit_postban.py`.

- **D57.** Evelynn Agony's Embrace: "Once each turn, when you play a card
  from face down, draw 1. Then, if it's not your turn, discard 1." Once each
  turn was kept per instruction: two cards played from face down in a row on
  the opponent's turn, the second trigger skipped the draw (used by the first,
  still on the chain) and kept the discard, which resolved first. An ability
  whose every instruction is once each turn now doesn't trigger again once
  performed (§383.3.e.1). The only such ability in the corpus.
- **D58.** Kha'Zix Voidreaver: "Spend 1 XP, [Tap]: [Buff] a unit." With no
  place given, a legend's chosen unit was one at the first battlefield (the
  others only if none was there). Data: `where` "anywhere"; the only legend
  with such an activated ability.
- **Read, played and found right.** Evelynn Entrancing (a unit at another
  location, bases included; its player attacks, §466.2.c.1; nothing from hand
  or on the opponent's turn), Momentary Companion, Gutter Guardian, Pyke
  Returned (Gold exhausted, once a turn, only while at a battlefield),
  Kha'Zix Mutating Horror and the legend's XP and move, K'Sante Courageous,
  Hold 'Em (a gear to base doesn't count), Boots of Swiftness ([Equip]
  [Chaos], GANKING), Void Assault (the caster attacks), Grim Resolve, Acceptable
  Losses (each player chooses), Decree of Strength, Bandle Scouts' Academy,
  Packed Amphitheater (every champion unit, both sides), Rakelstake (one
  PREDICT a turn per player), Ruin Runner, Onslaught's FLOW.
- **Seen on the way, a test and not the engine.** The invariant test didn't
  count a DEPLOY gear on a battlefield (The Good Stuff): it looked vanished.
- **Q6, answered by the owner (2026-11-17).** A gear played from face down
  (Edge of Night) is played at its battlefield: it counts for Rakelstake and
  for Hold 'Em, as a unit from face down already did. The engine counted
  neither.

## Deviations, eighth pass (2026-11-17): external review

An outside reviewer read the engine at `e72318e` (no engine change since) and
measured it with its own probes: every action offered in 576 seeded games
applied to a copy, the copies of the game played to the end against the
original at 3,123 points, and constructed cases with real cards. Its reports
are in `docs/audit/revisione_esterna/`; its scripts and data are not in the
repository (they hold pickled states). Checked here, in this repository: the
576-game action probe and its control rerun with identical totals, the eight
action reproductions and the 613 + 69 focused trials, the static counts, the
eight small copy reproductions; Black Market, combat designation and Riven
Deserter reproduced with our own scripts; D62 and D64 read in the code. Not
rerun here: the 3,123-point copy probe, D63, the golden forecasts.
D59-D65: **no test yet** (the failing tests are phase 0 of
`docs/PIANO_MOTORE.md`). D66-D68: fixed (phase 1), see below.

The live game:

- **D59.** An ability chosen in a reaction or showdown window while a Standard
  Move is still pending is not performed. `_apply_action` (loop.py ~5500)
  applies the Main Phase rule (anything but joining the move ends it), ends the
  move and returns; `_use_ability_now` sees no change in its partial
  fingerprint, so the window counts a pass. With a showdown already active,
  `_flush_pending_move` clears the marker and `_run_showdown` returns at once.
  The filter at legality.py ~162 covers only the Main Phase menu. Seen with
  Gold, Seal of Discord and Kai'Sa Daughter of the Void (17 times in 576
  games); Gold is made by cards in both current decks. Hiding the ability is
  not the fix (Add abilities may be used while paying a cost, §430.3): see
  the reviewer's `design_action_outcomes`, section 1.
- **D60.** A gear played in a showdown counts only if the hand got smaller
  (`_showdown_step`, loop.py ~7843): Detonation Amplifier (draws 1) and The
  Good Stuff (draws 3), made playable by Jarvan IV Martial Paragon, count as a
  pass. The same check is in `_reaction_step` (~7641), no failing case found.
- **D61.** `_run_main_actions` (~8278) takes an action that changes none of
  `_action_fingerprint`'s counts as nothing done and ends the Main Phase: a
  free hide of Teemo Scout from the Champion Zone (Guerilla Warfare) does that.
- **D62.** `_run_chain` (~7606): an Add ability ("kept") does not reset the
  pass count, so B passes, A uses Gold, A passes, and the chain resolves
  without B's chance (§339.1; the showdown loop does reset it). Seen 3 times in
  the golden game `random:competitive_kennen__vs__simple_trade:competitive_kaisa#2`,
  final state unchanged.
- **D63.** A Standard Move of several units is one action (§144.3): the group
  is chosen before anything happens. The engine adds units one at a time, after
  the first unit's move triggers have resolved. Seen in the golden games
  `random:precon_zed__vs__simple_trade:precon_shen#3` and
  `simple_trade:competitive_kaisa__vs__simple_trade:competitive_kennen#2`.
  Reported by the reviewer, not reproduced here.
- **D64.** `_deal_damage` (effects.py ~120) runs "if this kills it" when a
  target is no longer on the board, and `_unit_split_damage` (~2801) gives XP
  the same way: a Smite-marked unit banished instead of dying makes
  Disintegrate draw and Alpha Strike give XP (§429.1, §370.1.a.1).
- **D65.** A once-per-turn mark is keyed by the Card, which survives a zone
  change: Riven Deserter, banished and replayed by Temporal Breach, can't use
  "Exhaust a friendly unit: Ready a unit" again that turn, though she is a new
  object (§124, §377.2.b).

The copies of the game (search, speculative declarations) — `GameState.clone`
and `deepcopy` remap objects, but three stores hold `id()` integers that still
point to the original's objects:

- **D66.** `once_per_turn_used`: in a copy Black Market can be used again,
  Pyke Returned makes extra Gold.
- **D67.** `combat_designated`: copied units are no longer attacking or
  defending; reopened combat repeats attack/defend triggers (Kha'Zix Mutating
  Horror +2 Might and +2 XP again, Shadow Clone, Twilight Reveler, Kennen
  Keeper of Balance). With D66: 61 of 3,123 copy points diverge, 19 change the
  winner; rebasing these stores alone removes all 61.
- **D68.** `conquer_return`: a copied Relentless Pursuit runner doesn't return
  to base on conquer.

Fixed (2026-11-17, phase 1): the three stores hold the Card or UnitInPlay
itself (identity equality, `eq=False`), which a copy maps to its own. Red
tests first (`f4a9315`), then one commit each. `tests/audit/test_audit_copies.py`
plays the reviewer's reproductions (M1-M7, design 4.1-4.2: a test for each
once-per-turn record), each on three copy routes: `GameState.clone`, the
declaration's deepcopy of the state, the deepcopy of the whole loop. The
real game didn't change: the 28 golden games are identical, and so is the
final state of 1,440 more seeded games (the six decks, `random` and
`simple_trade`, before and after the fix). An `id()` could also be reused
once its object was gone; an object can't. `id()` calls in
`riftbound/`: 96, now 79. Also fixed by D66, checked here with a constructed
case: Evelynn, Agony's Embrace (the legend of `competitive_evelynn`) drew
again in a copy after a second play from face down. Left as it is (owner,
2026-11-17): a copy played on with a new `GameLoop` counts `units_played`
and `spells_cast` from the copy point (comment in `GameLoop.__init__`); no
one reads them from a copy, the search reads the winner. Not rerun here: the
reviewer's 3,123-point copy probe (its scripts are not in the repository).

## Deviations, ninth pass (2026-11-19): copies of the Chosen Champion

On RiftAtlas (2026-11-18) the opponent, 82FAW, played Ivern with Ivern,
Nurturer as Chosen Champion and one more copy in the MainDeck
(`docs/bot/partite/82FAW_ivern_lista.txt`). `load_deck_json` refused the
list, so `scripts/deck_from_txt.py` couldn't import it. Read: §103.3.a.3
(any Champion Unit with the champion's name is the Chosen Champion, wherever
it is, "for any game rules and effects"), §103.3.b / §103.3.b.1 (3 copies,
the champion included: the Volibear example). Tests in
`tests/audit/test_audit_chosen_champion.py`, red first (`e6e7457`).

- **D69.** "Champion ... must not appear in the cards list": the loader
  allowed no copy of the champion in the Main Deck. Now the champion is 1 of
  the 3 copies of its name, main deck and sideboard combined (Tournament
  Rules 403.3): champion + 2 in the Main Deck loads, a fourth copy anywhere
  is refused. 82FAW's list is `riftbound/data/decks/competitive_ivern.json`
  (`deck_from_txt.py` on the .txt; a test keeps them equal).
- **D70.** Hallowed Tomb: "you may return your Chosen Champion from your
  trash to your Champion Zone if it is empty". It looked for the card chosen
  at deckbuilding only: with the champion on the board and a copy in the
  trash it returned nothing. Now the chosen card if it is in the trash, else
  a copy, which becomes the card in the Champion Zone. In the printed text
  of the corpus only two cards name the Chosen Champion or the Champion
  Zone: Hallowed Tomb and Teemo, Swift Scout.
- **Read, played and found right.** A copy drawn and played from hand is a
  unit like any other: paid from hand, "when you play me" (Ivern: look at 3,
  draw the Poro, buff), the champion stays in its zone (`champion_X_deployed`
  untouched) and is still offered; then both on the board. In 20 whole games
  Ivern-Evelynn (`simple_trade`) the copy is played from hand in 5. Teemo,
  Swift Scout's "a Teemo unit you own ... from your Champion Zone or the
  board" already takes copies on the board (it asks for the name, not the
  champion). Sideboarding (`core/match.py`) swaps the champion with a copy by
  name: unchanged.

## Deviations after the freeze (2026-11-24)

Ordinary defects found after the Python engine was frozen (section "The Python
engine is frozen"): written here, fixed once in Rust.

**Fixed (25/11), decisions of Astra and the owner.** One selector of the rules,
chosen as a game starts and held by its registry (both players, the search
copies, the workers, the replays): `6427b90`, the default, identical to Python,
which the parity checks fix explicitly; `6427b90+D72-D76`, the five corrected.
D72, D73, D75 (the passive) and D76 are code behind the selector; D74 and D75's
`exclude_self` are a versioned data correction (`D72-D76/1`) applied as the
registry loads (`registry.rs: correggi_dati`; `rust/data/registry.json` stays
the reproducible export of Python). D75 also recomputes the passives when a
buff is spent or gained (a Kingpin spending its own buff alone is 5 at the
next decision). Each fix counts when it changes something (`riftbound_rs.correzioni`),
which explains a divergence from the historical rules
(`scripts/rust/confronto_regole.py`). The coach page stays on the frozen Python
engine ("Regole Python 6427b90"). Valley of Idols is not a defect: every unit
played there may be buffed for [1].

### D72. Rengar Trophy Hunter can't be played where only enemy units are

- **Card.** Rengar Trophy Hunter (UNL-120): "AMBUSH (You may play me as a
  REACTION to a battlefield where you have units.) I can be played to a
  battlefield where there are enemy units (even if you don't have units
  there.)" In the data: `{"effect": "ambush", "trigger": "passive",
  "enemy_ok": true}`.
- **Rule.** §822.1.b: AMBUSH is "I may be played to a battlefield where you
  control Units" and "I have [Reaction] as long as I'm being played to" one.
  §822.1.c: it adds valid locations when the unit is played, with no limit of
  time. §822.1.d, the example: Rengar Trophy Hunter "expands the normal
  permissions of the Ambush keyword to include battlefields where there are
  enemy units".
- **Seen.** In the coach page (24/11, Evelynn against Sett, turn 6, the
  owner's main phase): Monastery of Hirana held by the opponent with Fiora
  Victorious, Rakelstake empty, no unit of the owner at a battlefield, 5
  energy and Body Power. Rengar Trophy Hunter in hand: only "Play in base".
- **Minimal positions** (`_loop_with_rengar` and `_enemy` of
  `tests/test_ambush.py`; A active, 10 energy, 5 Body Power, an enemy unit at
  BF1, nothing of A at a battlefield):
  1. Rengar Trophy Hunter in A's hand, no champion. Turn action: only
     `("UNIT", 0, 0)` (base); expected base and BF1. Reaction:
     `_ambush_unit_lanes` is `[]`, no unit play; expected BF1.
  2. Rengar Trophy Hunter as A's Chosen Champion. Reaction:
     `("CHAMPION", None, 1)` (right). Turn action: base only; expected base
     and BF1.
- **Engine.** `loop.py:_ambush_unit_lanes` (the hand, reaction speed) reads
  only the AMBUSH keyword, not `enemy_ok`; `loop.py:_unit_play_destinations`
  (the main phase, hand and Champion Zone) reads neither. Only
  `loop.py:_ambush_legal_lanes` (the champion at reaction speed) has
  `enemy_ok`. Rust is the same (`lp_dest.rs`: `unit_play_destinations`,
  `ambush_unit_lanes`; `lp_costs.rs`: `ambush_legal_lanes`).
- **Not a defect.** For an AMBUSH unit without `enemy_ok` the main phase
  misses nothing: out of a contest, a battlefield where a side has units is
  one it controls.
- **Weight.** A missing option, in four of the five decks (Rengar Trophy
  Hunter in Evelynn, Kha'Zix and Sett, Rengar's champion). The champion's
  priors (`ekris_s12`) were trained without it; the Rust arena reproduces it.
- **Fix (Rust).** The battlefields with enemy units join both lists for a
  card whose `ambush` effect has `enemy_ok` (from hand and from the Champion
  Zone, main phase and reaction speed); a unit played there makes the
  battlefield contested, as `_deploy_ambush_champion` does. Red test first
  with the two positions above.

### D73. An AMBUSH play into a showdown misses the battlefield's passives

- **Card.** Packed Amphitheater: "Champion units here have +1 [Might]."
  Rengar Trophy Hunter is a Champion unit (Might 6).
- **Seen.** In the coach page (24/11, Sett against Sett, turn 5): at Packed
  Amphitheater the opponent's Fiora Victorious at 5 (4 + 1) and Rengar Trophy
  Hunter, just played there with AMBUSH, at 6; the page's total 11. Expected
  7 and 12.
- **Minimal position** (`tests/audit/audit_helpers.py`: `setup(active="B")`,
  `scripted`): BF0 Packed Amphitheater, A's vanilla unit of Might 12 and B's
  Fiora Victorious there, Rengar Trophy Hunter in B's hand;
  `loop._play_ambush_unit(b, 0, 0)`. At A's showdown decision Rengar's
  `might` is 6 (expected 7); with Rengar as B's Chosen Champion,
  `loop._deploy_ambush_champion("B", 0)`: the same. The combat after it is
  right (the unit of 12 dies: 5 + 7).
- **Engine.** `loop.py:_play_ambush_unit` and `_deploy_ambush_champion` call
  `_play_unit`, then `_run_showdown`, with no `_recompute_passives` in
  between: the new unit's `passive_might` stays 0 until the next recompute.
  Rust is the same (`lp_dest.rs:play_ambush_unit`,
  `lp_costs.rs:deploy_ambush_champion`).
- **Weight.** What the showdown's players see and decide on: the Observation
  (the page, the PPO features, `table_value` of the searches), and every
  check by Might during the showdown (not verified one by one: targets by
  Might, damage that kills). Any battlefield or unit passive giving Might to
  the unit just played.
- **Fix (Rust).** Recompute the passives after the unit enters, before the
  showdown. Red test first with the position above.

### D74. Pillaged Armory buffs only a friendly unit at its own battlefield

- **Card.** Pillaged Armory: "DEPLOY ... When you play this or when you
  conquer here, BUFF a friendly unit." The buff names no place: any friendly
  unit, in base or at any battlefield ("here" is only the conquer's place).
- **Seen.** In the coach page (24/11, Sett against Sett): Fiora Victorious
  saved by Sett The Boss (healed, exhausted, recalled to base), then the
  Armory's buff at Packed Amphitheater: "bersaglio → Vi Peacekeeper (unica
  scelta)". Fiora in base wasn't offered.
- **Minimal position** (`tests/audit/audit_helpers.py`: `setup`, `choices`,
  `act`): A's Vi Peacekeeper at BF0, Fiora Victorious in A's base, Pit Rookie
  at BF1, Pillaged Armory in hand; "Play gear Pillaged Armory @BF0". The
  choice `target:buff_unit` offers only Vi Peacekeeper; expected the three.
- **Engine.** The card's two `buff_unit` effects (`on_play`, `on_conquer`,
  `target: friendly_unit`) have no `where`; `effects.py:_resolve_targets`
  then takes "the units here (a spell's battlefield, the source's)". Pit
  Rookie, with the same verb, has `"where": "anywhere"`.
- **Same encoding elsewhere.** In the five decks, effects of non-spells with
  a single target and no `where`: Blitzcrank Impassive, Daisy!, Evelynn
  Entrancing, Irresistible Faefolk, Janna Savior, Vi Peacekeeper (and Void
  Assault, a spell). Not read against the print here; many say "here" or
  move to "my location", where the default is right.
- **Fix (Rust).** `where: anywhere` for both effects of Pillaged Armory. Red
  test first with the position above.

### D75. Sett Kingpin's Might from buffed friendly units never applies

- **Card.** Sett Kingpin (champion, Might 5): "TANK ... I get +1 [Might] for
  each buffed friendly unit at my battlefield." No "other": a buffed Kingpin
  counts itself (the cards that leave themselves out say "another" or
  "other", e.g. Wraith of Echoes, the "Other friendly units ..." examples of
  §478). A buffed Kingpin alone: 5 + 1 (its buff) + 1 = 7.
- **Seen.** In the coach page (24/11, Sett against Sett): a buffed Kingpin
  at 6.
- **Minimal position** (`tests/audit/audit_helpers.py`: `setup`, `unit`):
  A's Sett Kingpin at BF0 with a buff, `_recompute_passives()`: Might 6
  (expected 7). With a buffed Pit Rookie there too: still 6 (expected 8).
- **Engine.** The card's effect is `grant_temporary_might_per_friendly`,
  `trigger: passive`, `target_filter: {is_buffed: true, exclude_self: true}`.
  `loop.py:_apply_passive_grant` folds only some verbs into
  `passive_might`; this one is "safely ignored", so the passive never
  applies (`docs/rust/RAPPORTO_SETT.md` already counted 0 executions). The
  handler in `effects.py` would count every friendly unit, not the buffed
  ones, and as temporary Might. `exclude_self` disagrees with the text.
- **Weight.** Every Sett deck: the Kingpin is its champion, and Sett buffs
  (Sett Brawler, Pit Rookie, Pillaged Armory, Call to Glory). In combat it
  is 1 Might or more short; the champion's priors were trained this way.
- **Fix (Rust).** A continuous +1 per buffed friendly unit at the Kingpin's
  battlefield, itself included (none in base), recomputed with the other
  passives. Red test first with the position above.

### D76. A legend's "ready me" never readies it

- **Card.** Sett The Boss: "If a buffed unit you control would die, you may
  pay [rune], exhaust me, and spend its buff to heal it ... When you conquer,
  ready me." Exhausted by a save, it is ready again when its player conquers.
- **Seen.** Raised by the owner (24/11, Sett against Sett, coach page).
- **Minimal position** (`tests/audit/audit_helpers.py`: `setup`, `legend`,
  `scripted`): A's legend Sett The Boss exhausted, a unit of A at BF0;
  `loop._fire_scoring_trigger("on_conquer", bf, "A")`. The trigger goes on
  the chain ("A TRIGGER on the chain: Sett The Boss (on_conquer)") and
  resolves; the legend stays exhausted (expected ready).
- **Engine.** The effect is `ready_unit`, `target: self`;
  `effects.py:_resolve_targets` takes "self" from `_source_unit`, which looks
  only at the units on the battlefields and in base: the legend's unit
  (`legend_unit_A/B`) isn't there, so nothing is readied.
- **Same encoding.** The other legends with a triggered `ready_unit` on
  `self`: Irelia Blade Dancer (on conquer), Sivir Battle Mistress (when an
  enemy unit dies). Not in the five decks.
- **Weight.** Every Sett deck: after a save, a conquest in the same turn
  should give the Boss another save; it doesn't.
- **Fix (Rust).** "self" of a legend's ability is its legend unit. Red test
  first with the position above.

### D77. A showdown an effect stages during a Standard Move waits for the next action

Fixed in Rust (25/11) on the profile 6427b90+D72-D77, `9fcdc25`; 6427b90 and
6427b90+D72-D76 keep the behavior below.

- **Card.** Irresistible Faefolk (Sett): "When I move to a battlefield, you
  may move an enemy unit to that battlefield."
- **Seen.** Raised by the owner (25/11, Evelynn against Sett, coach page):
  Sett moved Irresistible Faefolk from base to Packed Amphitheater, which it
  controlled; the trigger moved the owner's Gutter Guardian there; Sett then
  played Pillaged Armory (gear, DEPLOY, no ACTION) and buffed First Mate
  before any showdown.
- **Minimal position** (`tests/audit/audit_helpers.py`: `setup`, `scripted`,
  `choices`, `act`): `setup(active="B")`; BF0: Pit Rookie and First Mate of
  B (B controls it); BF1: Gutter Guardian of A; Irresistible Faefolk in B's
  base, Pillaged Armory in B's hand; choices: the "you may" yes, the first
  target. `act(loop, "B", "Move Irresistible Faefolk base→BF0")`. Gutter
  Guardian is at BF0, `gs.staged_showdowns == [(0, "A")]`, no showdown, no
  move held, empty chain; B's legal actions: Pass, Play gear Pillaged Armory
  @BF0/@BF1, moves. Expected: the showdown at BF0 (A contesting it, as
  `_run_staged_showdowns` starts it) once the trigger has resolved, before
  B's next action ("once no chain or showdown is going on", §462); no gear
  without ACTION while it goes on.
- **Engine.** `loop.py:_apply_action` ends with `if kind != "MOVE":
  self._run_staged_showdowns()` (Rust: `lp_action.rs`, the same): a MOVE is
  left out because it may be held (`pending_move`, more units may join it).
  A move that isn't held (to a battlefield its side controls, no enemy
  there) leaves the staged showdown to the next action that isn't a move
  (it runs after that action: after the gear here) or to the end of the
  turn (`_end_turn`).
- **Same encoding.** Every unit brought into a battlefield by a trigger of a
  Standard Move that isn't held. In the five decks: Irresistible Faefolk.
- **Weight.** Sett with Faefolk: plays of the open state (gear, units, spells
  without ACTION, more moves) before the showdown the effect started; here a
  buff on a defender.
- **Fix (Rust).** After a MOVE that leaves no move held, run the staged
  showdowns as after any other action (`lp_action.rs`, behind
  `regole.d77()`; counted as `D77` in `riftbound_rs.correzioni`). Red test
  first with the position above (`46afd65`); a second test keeps the old
  behavior on 6427b90+D72-D76.

### D78. "They can't move it this turn" doesn't stop a spell's move

Fixed in Rust (25/11) on the profile 6427b90+D72-D80, `be38cf7`; 6427b90,
6427b90+D72-D76 and 6427b90+D72-D77 keep the behavior below.

- **Card.** Vex Apathetic (Evelynn): "When an opponent plays a unit while
  I'm at a battlefield, STUN it. They can't move it this turn."
- **Seen.** Raised by the owner (25/11, Evelynn against Sett, coach page,
  rules 6427b90+D72-D77 on Rust): with Vex at Bandle Scouts' Academy, Sett
  played Sett Kingpin to base (stunned, can't move), conquered Packed
  Amphitheater with First Mate, then cast Showstopper ("Buff a friendly unit
  in your base, then move it to a battlefield") on Kingpin, moving it there.
- **Rules.** The CORE_RULES example of Vilemaw's Lair ("Units can't move
  from here to base") and Flash: a "can't move" restriction negates a
  spell's move instruction, the rest of the spell resolves. The player who
  moves is the spell's controller (§191.3; §418.6.b.4 says it for Deal; for
  Move it's a reading). Expected: Showstopper buffs Kingpin, the move is
  negated, Kingpin stays in base.
- **Engine.** `cant_move_this_turn` sets `unit.cant_move_turn`; only the
  Standard Move checks it (`legality.py:165`, `loop.py:5670`; Rust
  `legality.rs:142`, `lp_action.rs:200`). `move_unit` and the other move
  effects ignore it (`_move_candidates`, Rust the same).
- **Same encoding.** Every move by an effect on a unit with
  `cant_move_turn` set: Vex's, and Hunker Down's "It can't move this turn"
  (`effects.py:3600`, the unit's own restriction). Seen in the five decks:
  Vex against Showstopper; other move effects not inventoried yet.
- **Weight.** Sett: Showstopper rescues a champion Vex stopped (here 7 Might
  on the battlefield instead of 5 stuck in base).
- **Fix (Rust).** Behind a new profile's flag: a move effect on a unit
  with `cant_move_turn == turn` is negated when the mover is the unit's
  controller (Vex) or always (Hunker Down: check the data's two encodings);
  whether such a unit may still be chosen (the CORE_RULES example: yes, the
  instruction is negated on resolution). Red test first.
  Done (`566e002`, after `be38cf7`): `move_unit_by_effect` (`lp_move.rs`) takes the mover (the controller of the
  spell/ability, §191.3) and negates the move, counted as `D78`, when the unit has `cant_move_any_turn == turn`
  (unconditional: Hunker Down, Entrenched Boar) or `cant_move_turn == turn` and the mover is the unit's controller
  (Vex Apathetic: the Vex player's own effects may still move it). The unit can still be chosen. The swap effect
  (`effects.rs`, two calls, mover = actor) negates each unit's move on its own.

### D79. A face-down play outside a task splits its triggers

Fixed in Rust (25/11) on the profile 6427b90+D72-D80, `11374fa`; 6427b90,
6427b90+D72-D76 and 6427b90+D72-D77 keep the behavior below.

- **Cards.** Bedeviling Stranger (HIDDEN; "When you play me, choose a
  battlefield. If there are 4 or more units there, you may return an enemy
  unit there to its owner's hand") and Evelynn Agony's Embrace (legend: "Once
  each turn, when you play a card from face down, draw 1. Then, if it's not
  your turn, discard 1").
- **Seen.** Raised by the owner (25/11, Evelynn against Sett, coach page,
  rules 6427b90+D72-D77 on Rust; game saved in `docs/bot/partite/coach/`
  20261125_201243): turn 6 (Sett's), showdown at Bandle Scouts'
  Academy; the owner plays the Stranger from face down there. The chain holds
  only the Stranger's ability (target Sett Kingpin) and the owner is asked to
  respond to it; the legend's draw/discard comes after it has resolved.
- **Rules.** Both trigger on the same event, the play (a unit's "when you
  play me" is a Play Effect, §383.4.a): they go on the chain together, each
  player ordering theirs (§383.3). Expected: the Stranger's ability and the
  legend's on the chain at once, the owner picking the order.
- **Engine.** `_play_from_hidden` from `_showdown_step` (`loop.py:7860`) and
  `_reaction_step` (`loop.py:7662`) runs outside a task (Rust: `lp_showdown.rs:124`,
  `lp_chain.rs:414` → `lp_hidden.rs:177`). With no task running a trigger is
  flushed as it triggers and the chain runs (`lp_triggers.rs:388`): in
  `_play_unit` the card's own effects (`lp_play.rs:90`) go on the chain and
  resolve before `_fire_card_played` (`lp_play.rs:97`) fires the legend's.
  From the Main Phase (`_apply_action`, a task) the two go on the chain together.
- **Same encoding.** Every unit or gear played from face down in a showdown
  or as a reaction with a "when you play me" and another trigger of the same
  play (legend, units, trash). A face-down spell: `_spell_played` fires
  `on_card_played` before the spell is put on the chain, so the legend's
  trigger runs before the spell is there (to check). The reaction path is
  read from the code, not seen.
- **Weight.** Evelynn: the draw (and, on the opponent's turn, the discard)
  can't come before the Stranger's bounce; the opponent answers the two
  abilities apart.
- **Fix (Rust).** Behind the package profile's flag: run
  `play_from_hidden` as a task (`as_task`), so the play's triggers are flushed
  together when it ends. Red test first with the position above; a second
  test keeps the old behavior on 6427b90+D72-D77.
  Done: `play_from_hidden` (`lp_hidden.rs`) runs in `as_task` when no task is running, counted as `D79`.
  The face-down spell case (Sprite Call with Evelynn's legend, checked): before, the legend's trigger was on the
  chain alone and resolved before the spell was put on it; now the spell is on the chain and the trigger on top
  of it, as from the Main Phase. Covered by the same `as_task`.

### D80. Points after the winning one

Fixed in Rust (25/11) on the profile 6427b90+D72-D80, `09d9384`; 6427b90,
6427b90+D72-D76 and 6427b90+D72-D77 keep the behavior below.

- **Seen.** Raised by the owner (25/11, game
  20261125_201243 in `docs/bot/partite/coach/`, coach page on
  Rust): at 7 points holding two battlefields, the game ends "9 a 4". The game
  ends at the 8th point (owner): the second hold is never scored.
- **Engine.** `_gain_points` (Rust `lp_rules.rs:82`) adds the points, then
  `_note_winner` fixes the winner at the first 8; the Beginning Phase goes on
  scoring the other held battlefields (and any trigger after it) as if the game
  were still on. The winner and the end are right; the score isn't.
- **Weight.** The score shown and saved (games, arena rows); anything that
  reads the points after the win (margins, values) sees one too many.
- **Fix (Rust).** Behind the package profile's flag: once a winner is
  noted, `gain_points` gains nothing and the phase stops (check what else runs
  after the win). Red test first: 7 points, two battlefields held, 8 at the end.
  Done: `gain_points` (`lp_rules.rs`) gains nothing once `winner` is set, counted as `D80`; the game's end path
  (`result_now`, `victory`) is unchanged.

### D81. Call to Glory without the buff costs 1 Power

Fixed in Rust (26/11, owner's decision: at once, not in a package) on the
profile 6427b90+D72-D81, `bbf59b3`; the earlier profiles and Python keep the
behavior below.

- **Seen.** Raised by the owner (25/11, Evelynn-Sett, coach page on Rust,
  6427b90+D72-D80, T3): Evelynn Entrancing at 5 (Hold 'Em) attacks, a buffed
  Trifarian Captain (2) defends, Sett has no Energy left. The champion casts
  Call to Glory on the Captain without spending a buff (no "spende il buff di"
  in the log) and pays 1 Power from a recycled rune: the Captain is 5, the two
  trade, and Sett The Boss saves the Captain, still buffed. The card says to
  spend a buff and ignore the cost; without the buff it costs 3 Energy, which
  Sett didn't have.
- **Engine.** `_cost_extras` (Rust `lp_costs2.rs: cost_extras`) prices the buff
  option as the whole printed cost off (`energy` 3, `power` 0, `buffs` 1).
  `_choose_cost_extras` (`choose_cost_extras`) then prices "not spending it" as
  the same cost plus 1 Power per buff kept. That is the rule of
  `spend_buffs_for_power`, not of `spend_buff_free`: the 3 Energy taken off never
  come back. Reproduced on both engines (0 Energy, a buffed unit, a rune to
  recycle): options `({energy 3, power 0, buffs 1}, 0, None)` and
  `({energy 3}, 0, 1)`; the second is paid with 1 Power, keeps the buff, gives +3.
- **Weight.** Wherever the choice is asked: the search (champion and arena bots
  explore it on their copies, so it's in the arena results with Sett), PPO's
  `inner`, the human seat. With a buff around, Call to Glory costs at most
  1 Power and the buff stays (Sett The Boss's save, Monastery of Hirana,
  Sett Kingpin).
- **Fix (Rust).** Behind the next profile's flag: for `spend_buff_free`, the
  option without the buff puts back what the buff took off (`energy +
  extras.energy`, `power + extras.power`), so it is offered only when the full
  cost is affordable; `spend_buffs_for_power` unchanged. Red test first: the
  position above, no option without the buff at 0 Energy; at 3 Energy, offered
  and priced 3.
  Done: `choose_cost_extras` behind `regole.d81()`, counted as `D81`
  (`tests/rust/test_d81.py`, red before on the three D72-D81 cases that change).
  Historical profile 80/80 identical to Python (ES, both seats); D72-D80 against
  D72-D81 on ES, 30 seeds: 9 games differ, D81 fired in all 9 at the first difference.

### D82. Edge of Night from face down attaches at the first battlefield

Fixed in Rust (26/11, at once like D81: it is in the owner's Evelynn list) on the
profile 6427b90+D72-D82; the earlier profiles and Python keep the behavior below.

- **Seen.** Raised by the owner (26/11, Evelynn-Sett, coach page on Rust,
  6427b90+D72-D81, T11): Edge of Night hidden at Valley of Idols (BF1), played
  from face down in the showdown there; its ability offers only his units at
  Bandle Scouts' Academy (BF0), not his unit at Valley of Idols. The card says
  "attach it to a unit you control (here)".
- **Engine.** `_fire_card_played` (Rust `lp_pay.rs: fire_card_played`) fires
  `on_self_played` at the played card's battlefield, found through its unit; a
  gear has none, so it falls back to battlefield 0. `_attach_gear` with `here`
  reads `_units_where(ctx, side, "")`, i.e. `ctx.bf`: the friendly units at BF0.
  The ability is on the chain and resolves after `_hidden_bf` is cleared, so the
  facedown filter (§811.1.d) doesn't apply either. Only Edge of Night (the one
  non-unit `on_self_played`) is affected; hidden at BF0 it works.
- **Weight.** Every Edge of Night played from face down at BF1 (Evelynn lists):
  attached to a unit elsewhere, or to nothing when no friendly unit is at BF0.
- **Fix (Rust).** Behind `regole.d82()`: with no unit for the card, `own_bf` is
  the card's `hidden_bf` (the battlefield it was played at), counted as `D82`.
  Done (`efdb5ff`): `fire_card_played` (`lp_pay.rs`) behind `regole.d82()`; `tests/rust/test_d82.py`, red before on
  the BF1 case (attached to the BF0 unit). Historical profile identical to Python (EK+KE 80/80, ES+SE 80/80);
  D72-D81 against D72-D82 on EK and ES, 30 seeds, both seats: 0/60 differ each (Edge of Night from face down at
  BF1 doesn't come up there): the test is the coverage.

### D83. A cost inside an effect is paid only with the runes, never with a Gold

Fixed in Rust (27/11) on the profile 6427b90+D72-D83; the earlier profiles and Python keep the behavior below.

- **Seen.** Raised by the owner (26/11, game 155859, T12, report 35): Reckless Innovator, "When I become
  exhausted, choose one - Play a Gold ... - Pay [chaos] to draw 1". The Gold ("REACTION[>] Kill this, [tap]: ADD
  [rune]") may pay the [chaos] (CORE_RULES 204.3, 204.3.a, 445.2.b-c, 430.3, 357.1.a, 204.4.b.1: an ADD Reaction can
  be activated whenever a resource must be paid, also inside an instruction). The engine checked and paid it only
  with the runes (`_mode_payable` / `_run_mode` -> `_pay_one_additional_cost` -> `_pay_energy_and_generic`): (a) with a
  Chaos rune and a Gold it recycled the rune without asking; (b) with only the Gold the mode was not offered.
- **Fix (Rust).** Behind `regole.d83()`, in `pay_one_additional_cost_x` (`lp_costs2.rs`): the check counts the ready
  Golds (`golds_needed`); on payment, if the runes do not suffice, the needed Golds are activated (`use_golds`: kill +
  tap, ADD of the cost's domain, no domain question) and then the cost is paid; counted as `D83`. Agents, PPO and search:
  runes first, Gold only if needed. Human seat with `payments=True`: when the runes suffice and a Gold is ready, the
  choice `payment:effect` ("Come paghi?": runes or N Gold; `human.rs`, `coach_rs.py`); other seats are not asked.
  Tests: `tests/rust/test_d83.py` (D72-D82 pinned, D72-D83 corrected).

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
- **Q6. Rakelstake and a hidden gear.** "The first time they play a unit or
  gear here each turn, they [Predict]." Edge of Night played from face down
  at Rakelstake attaches to a unit there: played here or not? The owner
  (2026-11-17): played here. The engine now counts it, for Rakelstake and
  Hold 'Em ("played a unit or gear to a battlefield this turn").

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
  effect ordering (§372-373) and layer dependencies (§480-481) outside the
  decks' cards (sixth pass); "this turn" keyword grants given twice to one unit; copy
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
