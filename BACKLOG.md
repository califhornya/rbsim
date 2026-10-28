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
- [x] Spells: costs are paid before the choices are declared (§356-357 say
      choose, then pay). Checked equivalent: the optional-cost choice (kicker)
      is asked before the targets either way, Energy/Power payment changes no
      target, and the only spells whose cost changes the board and that choose
      a unit (Ki Burst: exhaust a friendly unit; Parallel Convergence: return
      one) choose the same targets in either order. DEFLECT is part of the
      choice (paid as the spell goes on the chain).
- [x] DEFLECT (§809): the tax was Energy, by the spell's battlefield and only
      for spells naming an enemy target. Now [rune] (Power) per enemy unit
      with DEFLECT a spell or ability chooses, paid as it chooses (a spell as
      it goes on the chain); a unit you can't pay for can't be chosen. Heisho
      Shell and Decree of Insight ignore it.
- [x] "When you choose me" triggers fired as the spell resolved: a spell's
      declared choices now take effect as it goes on the chain (on_chosen,
      DEFLECT, enemy-choice counts), not again at resolution.
- [x] §355.8 check: gear targets (Detonate, Factory Recall, Turn to Dust,
      Salvage's enemy gear) and trash targets (Morbid Return, Heedless
      Resurrection) need something to choose; spells played by FLOW or from
      banishment are checked too (facedown: see HIDDEN). Battlefields always
      exist.
- [x] A unit an effect moves into a battlefield contests it (§452) and its
      showdown runs as soon as no chain or showdown is going on (§462): it
      waited for the end of the turn, so Twilight Step + a Standard Move back
      never conquered (GameState.staged_showdowns).
- [x] Move effects naming no place: any location but the unit's own, base
      included (§355.4), chosen (destination `any`; 11 cards). Destinations
      from the text: to a battlefield you control (Call to Battle), to an
      occupied enemy battlefield (Cataclysm), to its base (Janna, Isolate,
      Overzealous Fan), where you have units (Shadow Dash), open (§170.11.c).
- [x] Move tax: Gravity Field's "[1] [rune] to move one or more units to this
      battlefield" is paid by whoever is instructed to move (FAQ), once per
      move (units joining a held move don't pay again); unpaid, no move.
      Angler Wyrm: the chosen opponent picks which of their units moves (and
      pays any tax).
- [x] HIDDEN: a champion with HIDDEN can be hidden from the Champion Zone
      (§811.1.b); a card played from facedown chooses only among what is at
      its battlefield, and a spell with no valid target there can't be played
      from facedown (§811.1.d). Training note: hiding the champion has no slot
      in the net's action space yet (HIDE takes a hand index); add one when
      the action space is next resized.
- [x] Combat damage: the assigner orders every unit while the damage runs
      short (one choice per unit, TANK group first, BACKLINE last; it chose
      only the first); a Ki Barrier shield counts in lethal, so extra damage
      kills through it.
- [x] Stacking EMPOWER (§442.1.c.1 / §827.1.c.5): Kayle Justified, the only
      such card, is empowered up to three times (+2 [might] each; DEFLECT 3 and
      GANKING at three); `max_times`, UnitInPlay.empower_times.
- [x] Multiple additional costs (§356.2): each distinct one is its own choice
      and payment, in any order. No card has two different ones of its own
      (Pyke repeats one on two instructions); ACCELERATE, DEFLECT and
      battlefield surcharges are paid on their own paths.
- [x] Single games at the turn guard follow TR 408.2.b like matches (a 2+
      point lead wins, else a draw); the head judge's best-of-1 setup (TR
      406.1.h) is an option of play_match (`bo1_altered_setup`).

## D. Cards encoded only in part (corpus)
Method (2026-10-28): every card with ability text gets read (text, encoding,
handler), not only the ~300 with more sentences than entries: a random sample
of 30 had wrong cards with the "right" number of entries (Seat of Power fired
on a trigger a battlefield never gets). `scripts/card_text_audit.py` puts the
sentences next to the entries and flags whole classes of mistakes (a trigger
phrase with no matching entry, an entry that can't fire on its card type, a
number or "you may" / "for each" / "return to hand" missing from the
entries); 351 cards flagged at the start. Each fix gets a test of the
sentence (tests/test_corpus_cards.py). Order: the dead triggers, the cards
named below, then set by set.

Fixed:
- [x] Dead triggers: "When you defend here" (Fortified Position, Durand
      Memorial, Ravenbloom Conservatory) and deployed gear's "attack here"
      (Demacian Standard) never fired (only units and their gear got attack /
      defend triggers); now they fire as the combat opens. Ahri Nine-Tailed
      Fox ("an enemy unit attacks a battlefield you control", new trigger
      on_enemy_attack), Master Yi Wuju Bladesman (lone defender +2), Loyal
      Pup ("When you defend at a battlefield", new trigger on_you_defend),
      Seat of Power and Sunken Temple (were on_play: never fired; Seat now
      draws per other battlefield you control, Sunken Temple needs a MIGHTY
      unit and [1]). "This combat" is a duration now (Fortified Position,
      Durand Memorial, Fiora Peerless: was this turn). Demacian Standard and
      The Good Stuff return to hand when you hold.
- [x] MIGHTY read the printed Might ("While I'm MIGHTY": Fiora Victorious;
      "When you play a MIGHTY unit": Volibear Relentless Storm); now the
      unit's Might.
- [x] Control during a contest (§190.4.b): with units of both sides at a
      battlefield the engine said no one controlled it; the holder keeps
      control until the showdown / combat ends (Battlefield.control(), used by
      every "battlefield you control": unit and token plays, REACTION units,
      hide, conditions, Ahri). The showdown / combat machinery still runs on
      controller() (None while contested).
- [x] Every battlefield (71) read and played in a test. Dead before:
      Abandoned Hall, Altar of Blood, Black Market (a battlefield ability any
      player uses once on their turn: entry type bf_ability), Black Rose
      Sanctum (on_unit_dies_here), Forgotten Library, Gardens of Becoming
      (granted_to_units_here), the four cost rules (Ornn's Forge, Hunters'
      Circle, Piltovan Forge, Marai Spire), Vaults of Helia. Wrong before:
      Star Spring fired on moves (now plays; Rakelstake too, gear included),
      Sigil of the Storm recycled a hand card (now a rune), The Papertree
      channelled for one player, The Candlelit Sanctum put a card in hand
      (new `look_recycle`), Veiled Temple couldn't detach (ready_gear now
      chooses, deployed gear included), Amateur Recital / Ruined Monastery
      weren't optional, Dusk Rose Lab only killed tokens, The Academy, Hallowed
      Tomb had no text (read from the card image).
- [x] "When you play a spell" fired as the spell resolved (and never if
      countered); now as it is played (`_fire_spell_played`), battlefields
      included. "If you spent [4] or more" was never true (no record of what
      was spent): the Energy paid (cost + kicker / REPEAT) is kept per spell
      and per turn (Revna, Forgotten Library, Prepared Neophyte, Jhin
      Virtuoso).
- [x] A unit returned to hand took its Equipment to hand; it stays in base
      (§436.4.b).

Open, found on the way:
- Jhin Meticulous Killer: "you may play me for [mind]" (an alternative cost
  in a domain the play path can't charge yet).
- [x] The "look at the top cards" family (`dig`): the kept card is a "you
  may" now (`must` for Stacked Deck, Apprentice Smith, Encore); Reinforce and
  Rek'Sai Swarm Queen play a card from among them (new `look_play`: paid,
  Reinforce [5] less, Rek'Sai banished then played, here if a unit);
  Lightning Rush trashes the rest; Decree of Strength recycles a Mind card
  from the opponent's hand (was the caster's deck); Trifarian Captain only
  a unit or gear, [3] and [rune] at most; Encore's last mode kept one and
  then drew and recycled a hand card; Ivern Nurturer's pet buff.

Named in the old notes and still open:
Detonation Amplifier (DEATHKNELL twice here), Jarvan IV Martial Paragon (DEPLOY gear have ACTION), The Academy and
Marai Spire (REPEAT), Curtain Call (per-mode REPEAT costs, "at a battlefield" /
"at a base"), Temporal Breach (enemy units), Sumpworks Map (REACTION gear),
Sivir Battle Mistress (recycle a rune), Mageseeker Warden (gear half),
Heartening Soul (legends' ability), Showstopper / Resonating Strike / Call to
Battle (move details), Akshan Mischievous,
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
