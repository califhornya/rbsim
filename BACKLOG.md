# Backlog — everything left to finish before any training

Rule (user, 2026-10-27): no training until this list is empty. Each item is
checked against the current code before it is listed (DEFERRED.md and
KNOWN_ISSUES.md hold the history, and many of their entries were fixed later
without being marked). An item is done when a test plays the situation and
checks what the card text / Core Rules say, not when the card "has effects".

## A. The precon decks, card by card (the cards the coach and training play)
Method: read the text (the image when numbers matter), the encoding, the
handler code it runs, then a scripted test of each sentence of the text.

Fixed (2026-10-27, tests/test_precon_cards.py):
- [x] Lacerate — the target was never asked (the engine picked it; the coach
      and the search couldn't, nor was it declared) and only enemies counted:
      now any unit, chosen.
- [x] Pakaa Protector — a revealed non-unit went to the bottom of the deck
      and the +2 [might] was missing (new effect `reveal_top`).
- [x] Shadow Dash — now to a battlefield where you have units, and +1 to your
      units there when there are exactly two.
- [x] Dragon Form — any unit, not only at the spell's battlefield; a spell
      must choose one even when it helps no one.
- [x] Ki Barrier — any unit (it was friendly units only).
- [x] Gust Monk — "banish a card from any trash to give a unit ASSAULT 2" was
      two independent effects (ASSAULT even with nothing banished, only your
      trash): now one effect with the cost (`any_trash`).
- [x] Ravenbloom Prefect — an invented "costs 3 or more" condition: any gear.
- [x] Shadow Order Disciple — burn and +1 were two separate "you may"s (the +1
      without burning): one choice.
- [x] Kinkou Temple — battlefields' Might/keyword passives were never applied
      (also Trifarian War Camp, Windswept Hillock, Black Flame Altar, Packed
      Amphitheater), it named only "friendly" units, and "with TANK" read the
      printed keywords only (Shen's granted TANK didn't count).
- [x] Death Mark, Zed From the Shadows — the token goes where you choose.
- [x] Charm, Twilight Step — any destination (see C).

- [x] The whole Zed deck and its battlefields (2026-10-28): every sentence of
      every card has a test (tests/test_precon_cards.py,
      tests/test_card_fixes_coach.py).
- [x] The whole Shen deck and its battlefields (2026-10-28): every sentence
      tested. Noxian Emissary's EMPOWERED DEATHKNELL never fired (the unit was
      off the board when the condition was read); Steel Paws' DEFLECT (see C).

Section A is done: both precon decks are checked card by card.

## B. Engine bugs that reach many cards
- [x] `all_units_here` damage hit only the effect's controller's units
      (KNOWN_ISSUES #11): Frozen Fortress, Kog'Maw Caustic now hit both.
- [x] `target: battlefield` + `scope: all` meant "units at the spell's
      battlefield": The Ruination and Angler Beast now reach every unit,
      Flurry of Blades every battlefield (KNOWN_ISSUES 0b; the other
      `battlefield` targets are token locations or battlefield passives).
- [x] Handlers that picked a unit without `loop.choose` (Lacerate's kind):
      audited every handler; 30 now ask the player (the old pick is the
      baseline): Convergent Mutation, Stalking Wolf, Shady Spectacles, Leblanc
      Deceiver, Chronobreak, Bedeviling Stranger, Ivern Friend to All, Bone
      Skewer, Shard of Undoing (its owner), Dusk Rose Lab, Stare Down, Tricksy
      Tentacles, Temptation, Divine Judgment (each player), Twisted Fate,
      Teemo Strategist, Fox-Fire, Here to Help, Glowstone, Profiteer, Jax
      Grandmaster at Arms, K'Sante, Alpha Strike, Shakedown (its controller),
      Maduli, Keeper's Verdict (its owner, top or bottom), Bottled
      Constellation, Acceleration Gate, Switcheroo, deployed-gear moves,
      Forgotten Relic. New choice kinds `battlefield` and `tag`.
      tests/test_player_choices.py. Still the baseline's: how Alpha Strike
      splits its damage, Tricksy Tentacles' destination (their base).
- [x] Generic recall keeps damage / exhausted / buffs (KNOWN_ISSUES #8, §460):
      every recall path checked. Death replacements heal and exhaust because
      every such card says so; Possession exhausted the unit it recalls (only
      Conscription says "exhaust it"). tests/test_player_choices.py.
- [x] Mournful Witness-style "when a combat I was in ends" was encoded as
      "when I win a combat" (trigger on_combat_end).
- [x] A cost inside a played card's instruction ("spend a buff to ...") was
      never paid (Wildclaw Shaman spent nothing). tests/test_instruction_costs.py
- [x] `has_keyword` filters read only printed keywords, not granted ones.
- [x] Tokens: "play a token" naming no place went to base (rules: base or a
      battlefield you control, the player's choice, §440.2.c/§355.2); "here"
      tokens on 11 cards went to base too (Sprite Mother, Faithful
      Manufactor, Vanguard Captain, Royal Guard...); Rally for War's "occupied
      enemy battlefield". 58 specs set from the text (`location`).

## C. Rules approximations (engine systems)
- [ ] Spells: costs are paid before the choices are declared (§356-357 say
      choose, then pay).
- [x] DEFLECT (§809): the tax was Energy, by the spell's battlefield and only
      for spells naming an enemy target. Now [rune] (Power) per enemy unit
      with DEFLECT a spell or ability chooses, paid as it chooses (a spell as
      it goes on the chain); a unit you can't pay for can't be chosen. Heisho
      Shell and Decree of Insight ignore it.
- [ ] "When you choose me" triggers fire as the spell resolves, not as it is
      played.
- [ ] §355.8 check: gear, battlefield and trash targets; spells played
      facedown, by FLOW or from banishment.
- [x] A unit an effect moves into a battlefield contests it (§452) and its
      showdown runs as soon as no chain or showdown is going on (§462): it
      waited for the end of the turn, so Twilight Step + a Standard Move back
      never conquered (GameState.staged_showdowns).
- [x] Move effects naming no place: any location but the unit's own, base
      included (§355.4), chosen (destination `any`; 11 cards). Destinations
      from the text: to a battlefield you control (Call to Battle), to an
      occupied enemy battlefield (Cataclysm), to its base (Janna, Isolate,
      Overzealous Fan), where you have units (Shadow Dash), open (§170.11.c).
- [ ] Move tax (Gravity Field; who pays, §FAQ), Angler Wyrm's opponent moving
      their own unit.
- [ ] HIDDEN: hiding from the Champion Zone (§737.1.b); a card played from
      facedown chooses only at its battlefield (§737.1.d).
- [ ] Combat damage: the assigner chooses the order (only Dune Surfer's side
      does); extra damage assigned through a Ki Barrier shield.
- [ ] Stacking EMPOWER (Radiance §442.1.c.1 / §827.1.c.5): binary today.
- [ ] Multiple additional costs (kickers) on one card: the engine pays the
      first affordable one; check the Core Rules.
- [ ] Single games score the 40-turn guard as "any lead wins"; matches use
      the time rule. Best-of-1 setup (TR 406.1.h) not modeled.

## D. Cards encoded only in part (corpus)
About 300 cards have more sentences than effect entries (a rough count: one
entry can cover two sentences). Named in the old notes and still open:
Detonation Amplifier (DEATHKNELL twice here), Demacian Standard (return on
hold), Jarvan IV Martial Paragon (DEPLOY gear have ACTION), The Academy and
Marai Spire (REPEAT), Curtain Call (per-mode REPEAT costs, "at a battlefield" /
"at a base"), Temporal Breach (enemy units), Sumpworks Map (REACTION gear),
Sivir Battle Mistress (recycle a rune), Mageseeker Warden (gear half),
Heartening Soul (legends' ability), Showstopper / Resonating Strike / Call to
Battle (move details), Akshan Mischievous, Loyal Pup (defend from base),
Kharox (play from their trash), Akali Deadly Weapon (2 when Empowered, where),
Mel Newly Awakened, Renekton Brute, Legion Marauder ([1] or [body]),
Mobilize / Catalyst of Aeons ("if you couldn't, draw 1"), Atakhan, Diana
Lunari (PREDICT), Neeko Blending In, Jinx Rebel (per discard event).
Then every other card, set by set.

## E. Not modeled at all
Bandle Tree, Bushwhack Trap (a second facedown card), Orianna Lady of
Clockwork and The Ball as a unit (gear that becomes a unit), Ivern Green
Father (Brush battlefield), Baron Nashor + Baron Pit (rewrite; KNOWN_ISSUES
duplicate card), Svellsongur, Void Hatchling, Hextech Anomaly, Irelia
Graceful, Endless Riches, Neeko Blending In; FAQ rulings for Kharox + Neeko,
Atakhan + Mordekaiser, Meticulous Restorationist + Mordekaiser, Hunters'
Circle + Baron.

## F. Not rules: the engine's own choices when nobody chooses (AI quality)
Equip's unit, discards, effect-move targets, "you may" additional costs always
paid; the observation doesn't show a held move.
