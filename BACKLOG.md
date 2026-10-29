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
  in a domain the play path can't charge yet). Moved to G2.
- [x] The "look at the top cards" family (`dig`): the kept card is a "you
  may" now (`must` for Stacked Deck, Apprentice Smith, Encore); Reinforce and
  Rek'Sai Swarm Queen play a card from among them (new `look_play`: paid,
  Reinforce [5] less, Rek'Sai banished then played, here if a unit);
  Lightning Rush trashes the rest; Decree of Strength recycles a Mind card
  from the opponent's hand (was the caster's deck); Trifarian Captain only
  a unit or gear, [3] and [rune] at most; Encore's last mode kept one and
  then drew and recycled a hand card; Ivern Nurturer's pet buff.

- [x] The cards named in the old notes: Detonation Amplifier (DEATHKNELL
  here twice), Jarvan IV Martial Paragon (DEPLOY gear have ACTION:
  GameLoop._play_timing), The Academy, Marai Spire, Curtain Call (three
  REPEAT costs, each a new mode, at a battlefield / at a base), Temporal
  Breach (either side's unit), Sumpworks Map (REACTION gear, also offered),
  Sivir Battle Mistress ("when you recycle a rune": paying Power recycles
  runes), Mageseeker Warden (gear too), Heartening Soul (legends get its
  ability), Showstopper, Call to Battle (the opponent follows), Akshan
  Mischievous (steals a gear until he leaves), Kharox (plays a unit from
  their trash; ownership is tracked: Card._owner, GameLoop._owner_of, so a
  taken unit goes back to its owner's trash or hand), Akali Deadly Weapon,
  Mel Newly Awakened, Renekton Brute, Legion Marauder, Mobilize / Catalyst
  of Aeons, Atakhan's attack (the defender picks), Diana Lunari (PREDICT
  first), Jinx Rebel (once per discard: GameLoop._discard_event). Neeko
  Blending In is in E.
- Open: Jhin Meticulous Killer's alternative cost: moved to G2. (Atakhan's
  additional cost: done, see E.)
- [x] Origins (293 cards) read; 50 fixed, each tested (tests/test_corpus_origins.py).
  Never worked before: Time Warp's extra turn, Zhonya's Hourglass (gear in
  base), Sett The Boss's save, Unlicensed Armory, Bullet Time (X Power),
  Stormbringer, Dragon's Rage / Last Breath second halves, Noxian Guillotine
  without LEGION, Warwick Hunter's attack, Disintegrate's draw, Get Excited!'s
  damage, Super Mega Death Rocket! back from the trash, Forge of the Future's
  ability, Stand United's +1, Leona Zealot's -8, Lee Sin Ascetic's buffs,
  Spirit's Refuge's DEFLECT, Brazen Buccaneer's discount, Wallop / Call to
  Glory free for a buff, Guerilla Warfare's free hiding, Solari Chief's kill.
  Wrong before: Dr. Mundo / Ekko Recurrent recycled hand cards, Invert
  Timelines discarded one card, Meditation drew 3, Spoils of War read your
  own deaths, Garbage Grabber / Miss Fortune Bounty Hunter had unreadable
  costs (free, unlimited), Mindsplitter's discard picked by its owner,
  Sabotage, Cull the Weak / Acceptable Losses (each player picks their own),
  Hidden Blade only hit enemies, Gemcraft Seer, Unchecked Power, Overt
  Operation, Adaptatron, Cruel Patron's cost, Caitlyn Patrolling / Soraka
  Wanderer ("assigned combat damage last" = BACKLINE), Blind Fury's card
  stays its owner's, Wielder of Water only while fighting. Single-gear kills
  now chosen (they took the first one).
- [x] Spiritforged (222 cards) read; 62 fixed, each tested
  (tests/test_corpus_spiritforged.py). Systemic: counters had a hidden [4] /
  [rune] limit (Not So Fast, Hard Bargain, Riposte, Repulse, Abandon, Lilting
  Lullaby); "becomes MIGHTY" only when played (Fiora Worthy / Grand Duelist:
  now on_friendly_becomes_mighty); "when you spend a buff" (Fae Dragon:
  GameLoop._spend_buff); "Ready your units" / "your Mechs" / "your other
  units" reached only one battlefield (On the Hunt, Shurelya's Requiem,
  Rumble Scrapper, Danger Zone, Undertitan); attach_gear attached the first
  gear in base instead of itself (Edge of Night); MIGHTY counts left out the
  base (Show of Strength). Spells with no target (Blood Rush, Feral
  Strength, Punch First, Gem Jammer, Bonds of Strength, Bellows Breath,
  Sudden Storm, Piercing Light, Thwonk!, Defiant Dance). Missing halves:
  Angle Shot, Strike Down, Deathgrip, Blood Money, Rumble Hotheaded, Rell
  Magnetic, Kato the Arm, Azir Ascendant, Relentless Pursuit, Counter
  Strike, Rally the Troops, Arcane Shift, Riposte, Irelia Blade Dancer,
  Renata Chem-Baroness, Ezreal Prodigy, Jax Unmatched, Soraka Wanderer, The
  Zero Drive (text read from the image), Brutalizer (only the turn it's
  attached), Needlessly Large Yordle ([calm] too), Battering Ram (minimum),
  Poro Snax, Drag Under, Breakneck Mech, Pickpocket, Draven Audacious,
  Forecaster, Guards!, Fae Porter / Windsinger / Buhru Captain ("may"),
  Ancient Henge and Hextech Anomaly (any amount: X).
- [x] Unleashed (224 cards) read; 64 fixed, each tested
  (tests/test_corpus_unleashed.py). Never worked: Undying Legion from the
  trash (new entry type trash_play; Death from Below too), Elder Dragon's
  lethal damage, Blast Cone's stun (on_you_move_enemy), Cursed Sarcophagus,
  Red Brambleback / Blue Sentinel (conquer / hold effects twice), Vilemaw,
  Master Yi Unstoppable's levels, Nami Headstrong's hold, Smite, Deadly
  Flourish, Grim Resolve, Dancing Grenade, Keeper of Masks / Mirror Image
  copies, Smoke and Mirrors, Hwei, The List, Existential Dread's return,
  Isolate's draw, Rift Herald's DEATHKNELL, Tactical Retreat, Safety
  Inspector, Lilting Lullaby's silence, Lillia Bashful Bloom's discount.
  Wrong: Disposal Order recycled hand cards, Soul Sword's LEVEL bonus was
  always on (an equipment's conditional +N), Petal Pixie read TEMPORARY as a
  tag, Starhound only Dogs, Daisy!, Shadow, Soul Shepherd / Master Yi Wuju
  Master / Scrutinizing Sergeant / Right of Conquest counted one battlefield,
  Monster Harpoon, Back Off, Spectral Centaur (+2 per death), Sprite Burst
  (ready), Crescent Strike, Yuumi, Heroic Charge, Towering Pairofant, Shadow
  Watcher, Vi Hotheaded's [fury], Leblanc Fragmented, Concentrate, Repulse.
- [x] Vendetta, part 1: 38 cards fixed, each tested (tests/test_corpus_vendetta.py):
  the EMPOWER family (Baccai Sandspinner, Frostcoat Mother, Grumpy Rockbear
  costs; Rage Amplifier, Aurok General, Dame the Despoiler, Ambessa The Wolf,
  Gangplank Naval, Tail-Cloaked Matriarch, Mel Soul's Reflection, Akali Rogue
  Assassin), the Decrees (domain filters; Unity kills a unit or gear), "when
  it dies this turn" (Deadly Flourish, Siphoning Strike: also when the damage
  itself kills), Affectionate Poro, Tomb-Raider Barbara, Akali Silent, Shock
  Blast, Sky Cruiser, Plaza Guardian, Jayce Brilliant Inventor, Guttural
  Roar, Jagged Cutlass, Noxian Demolitionist, Rampage, Wild Claw, Corrupted
  Dragon, Spiderling, Illaoi, Ocean Drake, Dominus, Nasus Curator, Public
  Execution, Consuming Curse.
- [x] Vendetta, part 2: VEN-002..077 read (59 cards), 36 tested, 5 fixed:
  Forsaken Baccai / Oasis Raider count runes before the channel, Mesmerize
  (a friendly unit in base too), Clairvoyance (PREDICT 5), Iterative Design
  ("[Flow] [2] [Mind]" cost parsed); Brutal Hunter's Might 4 (from the user).
- [x] Vendetta, part 3: VEN-078..156 read (58 cards past part 1), 56 tested
  (Shady Spectacles already was), 4 fixed: ASSAULT / SHIELD were only added for
  the damage, now from the Attacker / Defender designation to the end of the
  combat (§807.1.d: Ambessa Respected and Feared's "less Might than me"),
  and no longer linger after it; Shadows of the Past read only your trash;
  Renekton Butcher of the Sands' Energy was free (now only units and units'
  abilities); Acceleration Gate readied only units (now gear and runes too).
  Rebuttal (VEN-152) had only "REACTION" in the card data: done later from the
  printed text (see the end of D).
- [x] Radiance, part 1: RAD-001..055 read (55 cards), 54 tested
  (tests/test_corpus_radiance.py; Trinket Peddler's DISARM via Ahri /
  Chronomancer), 15 fixed: Brawl (ASSAULT = the unit's Might, was 1),
  Lingering Animus (a gear death counts), Forbidden Technique (played from the
  trash after a [7]+ card, then banished), Detonation Amplifier (a gear's
  additional cost was never paid; a deployed gear's DEATHKNELL here twice,
  Karthus too), Firebrand Raider (readies enemies in base too; other units
  enter ready; no Awaken ready), Ekko Revolutionary (ACTION replay to base),
  Whirling Twirligig (Recruit / Mech abilities: "kill a friendly gear / unit"
  gear costs), Ziggs Short-Fused (gear abilities +1 Bonus Damage), Blossoming
  Dreamroot (deployed gear "win a combat here"), Iridescent Avian (+2
  instead if buffed), Hunker Down (ready, can't move), Invigorating Bloom
  (exhaust a MIGHTY unit ability), Resplendent Rostrum (one [tap]: draw and
  channel), Watchful Curator (gear DEFLECT on gear choices), Lost to the Sands
  (the baseline's mode choice now values gear).
- [x] Radiance, part 2: RAD-056..112 read (57 cards; Overloaded Traveler has
  no text), 55 tested, 20 fixed: Equipment keywords never reached their unit
  (Nazuman Ntofo's SHIELD 2, Serrated Dirk, Cloth Armor, Hexdrinker, Boots of
  Swiftness, Hunter's Machete, Protector's Shield: KNOWN_ISSUES #7's keyword
  facet); Seraphic Wyvern only in the Channel Phase (now every channel);
  mode costs and conditions were ignored (Reckless Innovator drew for free,
  Demon Shade); Improvised Projectile (a friendly gear's Energy cost, was 0),
  The Empyrean (shows off the most Power), Kai'Sa Rebel (spells have
  REACTION in her showdown), Spirit of the Forge (attached gear too), Zero
  Point Inflection (checked after the whole draw), Hold 'Em (a unit or gear
  to a battlefield), Raving Witness (MIGHTY, was "a spell"), Skystrike
  Squadron (the gear really returned), Armored Tusker (its SHIELD), Elnuk
  Herd (recycled from face down), Cataclysm (no enemy spells), The Waters'
  Wage (three ready Golds), An Offer You Can't Refuse (their Gold), Lulu
  Whimsical (a unit anywhere), Ziggs Explosive (gear for +2 defending),
  Mechanical Bandit (a real draw). Bushwhack Trap: modeled later (E).
- [x] Radiance, part 3: RAD-113..T02 read (56 cards; the 10 battlefields and
  15 others already had tests), 28 tested, 17 fixed: unit abilities never paid
  "exhaust a friendly unit" (Riven Deserter's missing ready, once a turn);
  "Choose two" ran one mode (Encore); "a unit or gear" killed only units
  (Mordekaiser Dominating, its discard now a cost of each trigger, not of
  playing him; Mournful Spirit here; Burn Away banishes); Transpositionist
  (plays a smaller unit free), Steadfast Outrider (gear counts; not in base),
  Raucous Anthem (all your units, was one battlefield), Dockside Lock-Up (holds
  to play the banished card), Seraphine Not Alone (+1 per other exhausted
  unit), Ekko Boy Who Shattered Time (disempower: next unit [2] [rune] less,
  killed at end of turn), Ziggs Hexplosives Expert ([rune] was free), Realm of
  Death (they fight), K'Sante Pride of Nazumah (ASSAULT = its SHIELD), Ntofo
  Strikes (deals its SHIELD), Blade of the Exile (EQUIP by exhausting a
  friend); Angler Wyrm, Transpositionist, Ziggs and K'Sante lost an ACTION the
  text doesn't print (§145.2). Not modeled: Seraphine Starry-Eyed Songstress,
  Orianna Lady of Clockwork, Neeko (E).
- [x] Proving Grounds (24 cards) read, all tested
  (tests/test_corpus_proving_grounds.py), 6 fixed: Lux Illuminated and Lux Lady
  of Luminosity never fired ("When you play a spell that costs 5 or more" was a
  passive; now the printed cost, not what was paid: Core Rules, Sky Splitter
  example); Highlander did nothing (now as Tactical Retreat); Gentlemen's Duel
  lacked the fight; Decisive Strike buffed one battlefield (now every friendly
  unit). Systemic: "They deal damage equal to their Mights" took enemies only at
  battlefields (Challenge, Rampage, Realm of Death, Clash of Giants: now
  anywhere; Marching Orders keeps "at a battlefield"), and its damage counted
  as the spell's (Annie Fiery's Bonus Damage, spell immunity): now dealt by the
  units (Core Rules, Challenge example).

D is done: every set read. Rebuttal (VEN-152) done 2026-10-29 from the printed
text (the card data had only "REACTION"): choose a spell costing no more than
[4]; pay [rune] to take it over with new choices, else counter it. Baseline:
the opponent's latest such spell, counter it if it is a counter. A spell taken
over (Mystic Reversal too) now gets its choices made again by its new
controller and goes to its owner's trash (`ChainItem.owner`). Tests in
tests/test_corpus_vendetta.py.

## E. Not modeled at all
- [DONE] Bandle Tree and Bushwhack Trap: a Facedown Zone holds more than one
  card (§107.3.b.1). `Battlefield.facedowns` is a list; the zone holds one,
  +1 at Bandle Tree, +1 per Bushwhack Trap its controller has there
  (`GameLoop._facedown_capacity`). Each facedown card is its own HIDDEN_PLAY
  (index = slot). When the room shrinks (the Trap dies, its controller loses the
  battlefield) the excess goes to the trash (§107.3.b.2). Tests in
  tests/test_hidden.py.
- [DONE] Orianna Lady of Clockwork and The Ball as a unit: at the start of
  your Main Phase (new trigger `on_start_of_main`, after the draw) she may pay
  [1] to choose a friendly gear (base, attached: it detaches §143.5.b, or
  deployed); it becomes a unit where it is (`UnitInPlay.gear_unit`, Might =
  its Energy cost, ready if the gear was), contesting or conquering a
  battlefield like a unit an effect put there. Choosing another turns the first
  back into a gear where it is (DEPLOY stays deployed, any other goes to base,
  §459.1). It moves (The Ball ganks; its "when you move this" fires), fights,
  dies as a unit; still a gear for "a friendly gear here" (Orianna Exquisite),
  "you control N gear" and "kill a gear". Baseline: pay when a gear makes a
  bigger unit than the current one, choose the costliest. Not covered: other
  gear effects (ready/exhaust/return/banish/steal a gear) don't see a unit
  gear. Tests in tests/test_unit_gear.py.
- [DONE] Ivern Green Father and the Brush battlefield token (Replace §439).
  When you conquer or hold, Ivern may exhaust to replace that battlefield
  with a Brush: same Battlefield object (§439.1.a: units, gear, facedown
  cards, who scored stay), its card kept in `Battlefield.replaced` (in
  Banishment, §439.5) and the abilities change (`GameLoop._set_battlefield_card`:
  Aspirant's Climb's +1 points to win ends, Bandle Tree's second facedown card
  is trashed). The battlefield's own conquer / hold effect still resolves
  (Ivern's trigger goes after it, §439.1.a example). Brush: Bird, Cat, Dog,
  Poro and Ivern units here +1 [might] (both players); when you score there
  you may swap it back (§439.7). Baseline: replace when the Brush helps a
  friendly unit there, swap back when it helps none. Brush and Baron Pit are
  battlefield cards in the registry. Tests in tests/test_green_father.py.
- [DONE] Baron Nashor and the Baron Pit, rewritten. As he is played, the Pit
  is added to the board (a third battlefield, if not there already) and he
  enters there (`GameLoop._add_battlefield_token`, a replacement of where he
  enters, §369.3), exhausted, contesting it (his player conquers it if nobody
  is there). He was still played where he was played: Hunters' Circle's [1]
  off and Riven The Exile's "enter ready" go by that place (FAQ). A second
  Baron enters where he was played. Other friendly units have +2 [might]
  everywhere (a passive, it ends when he leaves); enemy spells and abilities
  can't choose him. Pit: any unit may move there from a battlefield, no
  GANKING needed (`_can_move_bf_to_bf`); the Pit stays when Baron leaves. His
  card is in one zone (KNOWN_ISSUES fixed; the invariants test asserts it).
  Tests in tests/test_baron_nashor.py.
- [DONE] Svellsongur: "copy that unit's text to this Equipment's effect
  text" (a copy effect, §479.1; effect text is appended to the unit,
  §136.2.c), so while attached its unit has each of its own abilities once
  more per Svellsongur (`GameLoop._card_effects`; two copy the printed text
  twice, not each other). Triggers fire twice (DEATHKNELL too: the dying
  unit's gear is passed as `died_gear`), passives and auras count twice
  (cost auras, spell bonus damage, enemy spell tax), printed ASSAULT /
  SHIELD / DEFLECT add up (`UnitInPlay.keyword_value`). Not covered: copied
  activated abilities are not listed twice (only a "once per turn" one would
  give a second use), a passive keyword grant stays one instance, "trigger an
  additional time" passives (Karthus) don't stack. Found on the way: EQUIP
  needed a non-token unit at a battlefield; it now attaches to any unit you
  control, base too (§818.1.c.2; golden regenerated). Tests in
  tests/test_svellsongur.py.
- [DONE] Void Hatchling: "If you would reveal cards from a deck, look at the
  top card first. You may recycle it. Then reveal those cards." A replacement
  on every reveal from the top of a deck its controller makes
  (`GameLoop._before_deck_reveal`, called by every reveal handler), once per
  Hatchling (§370.2; Svellsongur's copy is one more). Any deck: the rune deck
  (Twisted Fate Gambler), an opponent's (Drakehound Packmaster: you reveal);
  Blind Fury is revealed by its owner ("Each opponent reveals", `reveal:
  "owner"`), so their Hatchling. Its look offers Nocturne. Looks ("look at the
  top 3 ... you may reveal a unit from among them") aren't reveals of the top:
  `reveal_play_top` reveals only with `reveal`. Baseline: recycle the top card
  when it is worse for the reveal than the average card under it (better,
  when the reveal serves the opponent). Found on the way: Apprentice Smith
  now reveals (it was a look that put the gear in hand without a draw);
  Undertitan's ADD fires on Teemo Strategist's and Scrutinizing Scope's
  reveals too, and Mechanical Bandit's goes to the Undertitan's owner (it gave
  the opponent's to the Bandit's player). Tests in tests/test_void_hatchling.py.
- [DONE] Irelia Graceful: "Your spells that choose me cost [1] or [rune] less."
  The engine pays a spell's cost before its choices, so the discount is taken
  as the spell chooses her (`GameLoop._graceful_discount`, from `_note_chosen`,
  where DEFLECT's [rune] is paid): off that [rune] first, else the Energy paid
  comes back, else the Power paid. Once a spell per Irelia, though it chooses
  her twice (Falling Star); Svellsongur's copy is one more; not for an
  opponent's spells. Left (KNOWN_ISSUES): a spell affordable only with her
  discount can't be played. Tests in tests/test_irelia_graceful.py.
- [DONE] Endless Riches: "When you play this, banish your hand and trash, then
  BURN 7. Skip your Draw Phase. You may play cards from your trash. If a card
  would go to your trash from anywhere other than your Main Deck, banish it
  instead." Effect `banish_hand_and_trash`, then `burn` 7 (Main Deck → trash:
  not replaced); markers `skip_draw_phase` (`_begin_turn`), `play_from_trash`
  (`trash_play` entries with `cost` None: the card's own cost, at its timing,
  like a play from banishment: units to base, spells at the showdown's
  battlefield, else the first), `trash_to_banish` (`GameLoop._put_in_trash`,
  used by every move to the trash but the Main Deck's: deaths, discards,
  spells, facedowns). Killed, it banishes itself (§370.4). Only its
  controller's cards. The heuristic agent now plays `trash_play` entries
  (Undying Legion too). Tests in tests/test_endless_riches.py.

- [DONE] Neeko Blending In: "If Neeko is in your deck, choose up to 3
  different legends in addition to your starting legend. When you play me,
  choose one of those Legends and add it to your Legend Zone while I'm on the
  board." Deckbuilding (§103.1): the deck JSON's "extra_legends" (up to 3,
  legends, no name twice nor the starting legend's, only with a Neeko in the
  main deck, sideboard or champion: `load_extra_legends_json`), in
  `GameState.extra_legends`. Playing her (effect `add_extra_legend`) adds one
  not in the zone yet, a new legend created ready (§174.2.b), in
  `GameState.added_legends` with her unit; it leaves when she is off the board
  (§107.4.d.2; `_drop_added_legends` in `_recompute_passives`). Every legend
  now works from the zone (`GameLoop._legend_units`, `_legend_with`): abilities,
  triggers, passives, "friendly legends have", Awaken readying; "ready / exhaust
  your legend" takes one of them (§355.10.g). The legends are her player's,
  also for an opponent's Neeko played with Kharox (FAQ). Baseline: the first
  the deck lists. Coach shows them next to the legend (not visually checked).
  Found on the way: a card's power with no single domain was free. Neeko's is
  [A] (any domain, §135.2.e.6.b); the 48 multi-domain cards ("Mind/Chaos":
  Moonfall, Death from Below, Icathian Rain, Tibbers ...) now pay any power of
  their domains, mixed (§135.2.e.6.c; `GameLoop._power_domains`,
  `Player.pay_power_of`); `Player.can_pay_cost` with no domain is [A] (agents'
  checks). Golden regenerated. Tests in tests/test_neeko_blending_in.py.

- [x] Seraphine Starry-Eyed Songstress: "As an additional cost to play a
  spell, you may exhaust me and three friendly units to reduce the cost of that
  spell by [2]." Every spell payment may take it (`GameLoop._songstress`,
  `_songstress_discount`; marker `songstress_discount`): `_can_pay_card` also
  tries the cost [2] less (so a spell short [2] is legal), `_pay_card` and FLOW
  pay it. The player chooses (`optional:songstress`; baseline: only when the
  spell can't be paid without it) and which three ready units
  (`cost_unit:exhaust`; baseline: units at battlefields, then tokens, then the
  weakest). Three units exhausted at once fire Seraphine Inspiring; each one's
  "when I become exhausted" fires (Seraphine Not Alone). Tests in
  tests/test_seraphine_songstress.py.

- [x] Atakhan: "You may kill a friendly unit as an additional cost to play
  me. If you do, I cost [1] less for each Energy it costs and [order] less for
  each Power it costs." Every payment of him, from any zone, may take it
  (`GameLoop._kill_discounts`, `_kill_discount`, `_kill_for_cost`; marker
  `kill_unit_for_discount`): `_can_pay_card` also tries each friendly unit's
  cost off (printed or copied, §206: a Reflection of Noxus Hopeful is [4]),
  `_pay_card` pays. The player chooses (`optional:additional_cost`; baseline:
  only when he can't be paid without it) and which unit (`cost_unit:kill`,
  only those that make him affordable; baseline: a token, then the weakest).
  FAQ with Mordekaiser, Iron Revenant: the unit dies after the Energy and
  Power are paid (§357.1-2), so it isn't in the trash for Mordekaiser.
- [x] FAQ Meticulous Restorationist + Mordekaiser, Iron Revenant: "play me
  for [order]" is an alternate cost of a unit, so Mordekaiser's unit/gear-only
  Power pays it. Every "play me for [cost]" (`play_self_from_trash` trigger
  costs, `trash_play` entries: Undying Legion, Death from Below) now uses what
  is earmarked for that kind of card, as `_pay_card` does
  (`GameLoop._less_play_earmarks`). Tests in tests/test_atakhan_mordekaiser.py.

## F. Not rules: the engine's own choices when nobody chooses (AI quality)
Equip's unit, discards, effect-move targets, "you may" additional costs always
paid (Atakhan's kill and Seraphine Songstress's only when the card can't be
paid without them); the observation doesn't show a held move. A facedown card trashed for
lack of room is the newest (the player should choose). The net's action space
has one HIDDEN_PLAY per battlefield: with two facedown cards at Bandle Tree it
can only play the first (the search and heuristic agents see both). The net
sees two battlefields (encoding N_BF = 2): with the Baron Pit (a third) it
doesn't see the Pit, and since the base's move index becomes 3, its moves to
or from the base or Pit map to wrong slots (the search and heuristic agents
see all three). The net sees one legend per player: not the ones Neeko Blending
In adds (their abilities are still in its action space). The heuristic agents
check a multi-domain card's power as any domain's (the engine pays it from its
domains: an agent may try a card it can't pay, a no-op that ends its turn).
The heuristic agents check a card's printed cost, not what it costs now: they
never play a spell only Seraphine Starry-Eyed Songstress's [2] less pays for
(nor one any other reduction makes affordable).

From the re-check of the old notes (2026-10-29, G):
- Hiding the champion (§737.1.b, the engine allows it) has no slot in the
  net's action space.
- The net-guided search decides only the first choice of an action, none while
  defending, none of the hidden ones (dig, predict).
- Coach: the mulligan and the choices made during the opponent's moves aren't
  coached; the coach page for two facedown cards (B8) and Neeko's legends (B16)
  isn't visually checked.
- Stepwise engine for deep MCTS trees (KNOWN_ISSUES): only if the search needs
  it.
- Match: learned sideboarding; the battlefield chooser sees only its own
  battlefields (not the opponent's left, not the match history); a stronger
  battlefield signal; the mulligan and the battlefield in the learned decision
  space; `MINUTES_PER_TURN` (core/match.py) needs real turn times (from the
  user).

## G. Old notes re-checked (2026-10-29): what is still open
Every OPEN / DEFERRED / "Left" / approximation entry in KNOWN_ISSUES.md and
DEFERRED.md, checked against the code and the card data. Those already fixed
(mostly by A-D) are marked CLOSED there (list at the end). Order: G before F
(the engine first, then the AI's choices).

### G1. Engine bugs (seen in the code)
- [x] Units dying in base count as dying at battlefield 0: `_route_deaths` is
  called without `in_base` for TEMPORARY in base (loop.py), Bottled
  Constellation's sacrifice (effects.py `sacrifice_for_points`) and
  `kill_friendly` (effects.py); the Storm Raptor check (`if
  dead_unit.stunned` in `_route_deaths`) isn't gated by `in_base`. "Here"
  death triggers (Black Rose Sanctum, Storm Raptor, Detonation Amplifier's
  doubled DEATHKNELL here) can fire for a death in base. DONE B20: the three
  callers pass `in_base`, Storm Raptor is gated, and "died alone" (Lonely
  Poro) looks at the base for a death in base (tests/test_g1_engine_bugs.py).
- [x] Base units' passives use battlefield 0 as "here" (`anchor` in the unit
  passives pass, loop.py): "your units here ..." from a unit in base (Alpha
  Wildclaw) reaches battlefield 0's units instead of the base. Confirmed by a
  test. DONE B20: the base pass marks its context `in_base`
  (`_apply_unit_passives` / `_apply_gear_passives`), and `_passive_targets`
  then takes "here" as that player's base (no enemy units).
- [x] PREDICT 2+ (effects.py `_predict`): never recycles, no choice; it sorts
  the top cards by Might. Rules: look at N, recycle any of them, put the rest
  back in any order. DONE B20 (§437.1.a): one `predict_recycle` choice per
  card, top first (source = that card; baseline: the agent's
  decide_predict_recycle, else keep), then `predict_order` (choose_many, top
  first; baseline: the mightiest drawn first). Cards Nocturne took are out.
- [ ] Cost extras (KNOWN_ISSUES #27): what a card lets you spend to cost less
  (Brazen Buccaneer's discard, Skystrike Squadron's gear, Kraken Hunter's
  buffs, Commander Ledros's tokens, Poppy's XP, Wallop's buff) applies from
  the hand only (rules: any zone, §356.2), and a play through an effect (Here
  to Help, `_reveal_play_for` mode "reduce", `_play_from_zone` with
  `pay_cost`) takes the discount without spending them. Fix: choose and spend
  them in `_pay_card`, as Atakhan's kill does. DONE B20: `_effective_cost`
  takes them off from any zone; `_pay_card(..., extras=True)` chooses them
  (`_choose_cost_extras`; a dict = already chosen, as the UNIT action does
  before its surcharge check; False = a cost not from `_effective_cost`: Rift
  Herald's "ignoring its Energy cost") and spends them after the Energy,
  Power and Atakhan's kill. `_spell_played` no longer spends them (a free
  cast took no discount).

### G2. Card approximations (data unchanged since DEFERRED "Corpus pass")
- [x] Origins: Fading Memories (can't choose a gear), Pack of Wonders (units
  only, not gear or facedown cards), Facebreaker (the two units needn't share
  a battlefield), Miss Fortune Captain (readies units only, not "something
  else"), Malzahar Fanatic (the cost kills tokens only), Commander Ledros
  (kills tokens only), Sivir Battle Mistress (fires at the next state refresh
  after the Power payment). DONE B21 (tests/test_g2_origins.py): Sivir's
  `_drain_rune_recycles` runs as a payment ends (`_pay_card`,
  `_pay_generic_power`, `_pay_energy_and_generic`, `_spell_played`, FLOW),
  §818.1.c.1. Malzahar: `_units_or_gear_to_kill` (any unit or gear, in base,
  attached or deployed, himself last; simple_trade still uses him only with a
  token). Ledros: effect `kill_units_for_power`, cost extra `kills`
  (baseline: tokens, real units only if he can't be paid otherwise;
  `cost_unit:kill` picks which). Fading Memories: `give_gear_temporary` with
  `or_unit`; Turn to Dust now chooses any gear and a deployed one stays
  deployed (killed at its controller's Beginning Phase). Pack of Wonders:
  effect `return_friendly_to_hand` (no ACTION: main phase only), helper
  `_return_unit` shared with recall_unit. Miss Fortune Captain and Jayce
  Brilliant Inventor: effect `ready_something` (unit, legend, gear or rune;
  rune = +1 Energy). Facebreaker was already right (both units "here" = the
  battlefield it is aimed at): checked by a test.
- [x] Spiritforged: Emperor's Divide (moves all, not "any number"), Assembly
  Rig (recycles any card, not a unit from the trash), Arcane Shift (comes back
  to base, no choice), The Zero Drive (to the trash, not banished), Kato the
  Arm (also lends keywords given for the turn), counters that "choose" read
  spells' declared choices only (not abilities'), Undertitan's ADD on "you may
  reveal a unit from among them". DONE B22 (tests/test_g2_spiritforged.py):
  Emperor's Divide: `move_units_to_base` with `any_number`, one
  `optional:move_units_to_base` choice per unit (baseline: all). Assembly Rig:
  cost key `recycle_type` ("unit"), `GameLoop._recyclable(player, kind)` used
  by the usability checks and `_recycle_from_trash(player, n, kind)`. Arcane
  Shift: `blink_unit` destination `play_location` = base or a battlefield the
  owner controls (§355.2.a; one it was alone at still counts, §190.4.c),
  choice `destination:blink_unit` (baseline: back where it was unless losing
  its fight there, else base). The Zero Drive: cost key `banish_self`,
  `_remove_gear(..., banish=True)` (to banishment, Zed's "banish a card you
  own" fires). Kato: the old note was wrong by the rules (§801.3: granted
  keywords are his), now also this-combat ones and Svellsongur's copies.
  Undertitan: `dig` / `reveal_and_choose` call `_note_revealed` for the kept
  card unless `must` or `reveal: false` (Lightning Rush "choose a card",
  Stacked Deck "Put 1"). Not So Fast / Repulse vs abilities: abilities never
  go on the chain in this engine, so moved to G3 "Abilities on the chain".
- [ ] Unleashed: Iascylla (moves at once, not at the start of your next Main
  Phase), Undying Loyalty ([2] less for a Bird / Cat / Dog / Poro: missing),
  Hextech Gauntlets (Equip cost not reduced by the unit's Might), Dancing
  Grenade (replays inside the first cast, no responses between), Crescent
  Guardian ([chaos] payable with no spell played), Death from Below
  (replayable later in the turn, not only right after).
- [ ] Vendetta: Nasus Curator of the Sands (not on activated abilities costing
  [7]+), Tail-Cloaked Matriarch (reads the unit from your trash), Decree of
  Focus (spells' choices only, not abilities'), Bottled Constellation (start of
  turn, not the Main Phase: `on_start_of_main` exists now), Sanction (empowers
  a friendly / disempowers an enemy unit only; text: any unit).
- [ ] Others: Jhin Meticulous Killer ("you may play me for [mind]": not
  encoded, from D), Hunters' Circle (not on AMBUSH / REACTION units played in
  a showdown), Abandoned Hall / Forgotten Library ("spent" counts Energy, not
  Power), Master Yi Wuju Bladesman / Forbidding Waste (combat damage only, not
  MIGHTY checks during the combat), Resonating Strike ("a unit at a different
  location": check).

### G3. Rules systems
- [ ] Control (§190.4): a side moving alone onto an uncontrolled battlefield
  controls it at once (rules: after its showdown); a holder whose units all
  die mid-showdown loses control at once (rules: at the end of the combat
  steps).
- [ ] Declared choices: a later instruction's choice is made after the earlier
  ones resolved on the copy (it can't name a unit the first one kills).
- [ ] Costs before choices (KNOWN_ISSUES): a spell affordable only with Irelia
  Graceful's discount can't be played; "if you spent [N]" sees the Energy
  before her discount.
- [ ] Abilities on the chain (§328, §337.2, from G2 Spiritforged): activated
  and triggered abilities resolve at once (`_apply_activated_ability`,
  `_resolve_triggered_effects`; `_reaction_step` "kept"), so nobody can respond
  to one. Rules: every ability but an Add goes on the chain, its choices
  declared, and can be reacted to. Cards hit: Not So Fast / Repulse ("counter
  an enemy spell or ability that chooses ..." reads `ChainItem.declared` of
  spells only: `effects._chose_mine`), Decree of Focus (`_fury_threatened`,
  G2 Vendetta), any REACTION played in answer to an ability.
- [ ] Leftovers of E: Orianna (ready / exhaust / return / banish / steal a gear
  don't see a unit gear); Svellsongur (copied activated abilities aren't
  listed twice, a passive keyword grant stays one instance, Karthus-style
  "additional time" doesn't stack).

Closed in KNOWN_ISSUES / DEFERRED (fixed earlier, now marked): EQUIP's own
cost (`_equip_cost`); resolved spells to the trash (#19a); 0b malformed specs;
0c parser notes; #1 cost keys; #2 multiple kickers (C); #3 discard semantics;
#4 / #10 cost auras; #5 buff vs modifier; #6 location filters; #7 gear
triggers and keywords; #8 recall (B); #11 all_units_here (B); #13 Cursed
Sarcophagus; #17 kill_gear; #19b FLOW; #20 EMPOWERED "instead", on-burn,
stacking EMPOWER; #22, #23 HIDDEN (C); Gem Jammer this turn; activated costs'
Power domain; Diana Lunari; the Radiance DEPLOY list; Hextech Anomaly; batches
1-12 "Left" items (D); FAQ Angler Wyrm, Gravity Field, Mobilize, Kharox,
Hunters' Circle + Baron; Bo1 setup and the single-game turn guard (C);
targeting baseline (effects ask the player).
