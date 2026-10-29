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
- Open: Atakhan's additional cost ("kill a friendly unit ... I cost [1] less
  for each Energy it costs and [order] less for each Power"), Jhin
  Meticulous Killer's alternative cost.
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
  Open: Rebuttal (VEN-152) has only "REACTION" in the card data.
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

D is done: every set read. Open only: Rebuttal (VEN-152), its text is missing
from the card data (only "REACTION"); needs the printed text.

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

Ivern Green
Father (Brush battlefield), Baron Nashor + Baron Pit (rewrite; KNOWN_ISSUES
duplicate card), Svellsongur, Void Hatchling, Irelia
Graceful, Endless Riches, Neeko Blending In, Seraphine Starry-Eyed Songstress
(a legend's optional extra cost on every spell: exhaust her and three friendly
units for [2] less; the cost path has no hook for it); FAQ rulings for Kharox + Neeko,
Atakhan + Mordekaiser, Meticulous Restorationist + Mordekaiser, Hunters'
Circle + Baron.

## F. Not rules: the engine's own choices when nobody chooses (AI quality)
Equip's unit, discards, effect-move targets, "you may" additional costs always
paid; the observation doesn't show a held move. A facedown card trashed for
lack of room is the newest (the player should choose). The net's action space
has one HIDDEN_PLAY per battlefield: with two facedown cards at Bandle Tree it
can only play the first (the search and heuristic agents see both).
