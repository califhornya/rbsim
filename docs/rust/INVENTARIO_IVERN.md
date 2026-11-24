# Inventario Ivern (porting Rust)

Generato da `python scripts/rust/inventario.py --liste I --matchup EI KI RI Ei Ki Ri --partite 30`. Esecuzioni: chiamate Python su 90 partite per matchup e per posto (EI, KI, RI, Ei, Ki, Ri, ciascuno anche rovesciato; minuscola = la lista con la sideboard nel mazzo, `riftbound/rs/mazzi.py`): self-play PPO a pesi dal seme 1, PPO contro simple_trade, random contro PPO. Sono le partite che il motore Rust gioca identiche.

## Carte

| Carta | Dove | Tipo | Parole chiave | Già in EKR |
|---|---|---|---|---|
| Affectionate Poro | Ivern mazzo | UNIT | — | no |
| Back Off | Ivern mazzo | SPELL | HIDDEN, ACTION | no |
| Bird | creata da Frisky Hunter | UNIT | DEFLECT | no |
| Blitzcrank Impassive | Ivern mazzo | CHAMPION | TANK | no |
| Block | Ivern mazzo | SPELL | HIDDEN, ACTION | no |
| Daisy! | Ivern mazzo | UNIT | — | no |
| Defy | Ivern mazzo | SPELL | REACTION | no |
| Disarming Rake | Ivern mazzo, Ivern sideboard | UNIT | — | no |
| Fallen Feline | Ivern mazzo | UNIT | — | no |
| Forbidding Waste | Ivern campi | BATTLEFIELD | — | no |
| Friendship | Ivern mazzo | SPELL | REACTION | no |
| Frisky Hunter | Ivern mazzo | UNIT | — | no |
| Grand Strategem | Ivern sideboard | SPELL | ACTION | no |
| Hush | Ivern sideboard | SPELL | REACTION | no |
| Iridescent Avian | Ivern mazzo | UNIT | — | no |
| Ivern Green Father | Ivern leggenda | LEGEND | — | no |
| Ivern Nurturer | Ivern campione, Ivern mazzo | CHAMPION | — | no |
| Janna Savior | Ivern sideboard | CHAMPION | REACTION | no |
| Mutated Mouser | Ivern mazzo | UNIT | SHIELD 2, TANK | no |
| Not So Fast | Ivern mazzo | SPELL | REACTION | no |
| Raucous Anthem | Ivern mazzo | SPELL | — | no |
| Rockfall Path | Ivern campi | BATTLEFIELD | — | no |
| Salvage | Ivern sideboard | SPELL | ACTION | no |
| Stalwart Poro | Ivern mazzo | UNIT | SHIELD | no |
| Trusty Ramhound | Ivern mazzo | UNIT | — | no |
| Vilemaw | Ivern sideboard | UNIT | AMBUSH | no |
| Vilemaw's Lair | Ivern campi | BATTLEFIELD | — | no |

## Verbi

Stato in Rust: **handler** (rbsim-core `run_effect`), **marcatore** (nessun handler in Python: il motore lo legge dove serve, porting con la funzione che lo legge), **NON PORTATO** (handler Python senza traduzione: in Rust darebbe `NotPorted`).

| Verbo | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|
| buff_unit | handler | 4289 | Iridescent Avian |
| counter_spell | NON PORTATO | 1414 | Defy, Hush, Not So Fast |
| dig | NON PORTATO | 4594 | Ivern Nurturer |
| draw_cards | handler | 7872 | Affectionate Poro, Back Off, Salvage, Vilemaw |
| enter_ready | marcatore | 0 | Daisy! |
| give_keyword | handler | 1098 | Block |
| give_temporary_shield | handler | 964 | Block |
| grant_might | handler | 0 | Trusty Ramhound |
| grant_temporary_might | handler | 14260 | Friendship, Grand Strategem, Raucous Anthem |
| green_father_brush | NON PORTATO | 12454 | Ivern Green Father |
| heal_unit | NON PORTATO | 788 | Janna Savior |
| kill_gear | handler | 1358 | Disarming Rake, Salvage |
| lone_defender_minus | marcatore | 0 | Forbidding Waste |
| move_unit | handler | 2609 | Blitzcrank Impassive, Janna Savior |
| name_spell | NON PORTATO | 1586 | Fallen Feline |
| no_moves_to_base_from_here | marcatore | 0 | Vilemaw's Lair |
| no_unit_plays_here | marcatore | 0 | Rockfall Path |
| play_token | handler | 3546 | Frisky Hunter |
| ready_units | NON PORTATO | 876 | Raucous Anthem |
| recall_unit | handler | 3607 | Blitzcrank Impassive |
| reduce_cost | marcatore | 0 | Daisy! |
| stun_unit | handler | 2046 | Back Off, Daisy! |
| weaker_enemies_no_damage | marcatore | 0 | Vilemaw |

## Condizioni e quantità

Condizioni (`_check_condition`, Rust `check_condition`) e fonti di quantità (`_amount`, Rust `effect_amount`). Esecuzioni: valutazioni in Python.

| Tipo | Che cos'è | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|---|
| has_all_pet_tags | condizione | NON PORTATA | 195 | Daisy! |
| played_from_hand | condizione | NON PORTATA | 1290 | Back Off |
| this_is_at_battlefield | condizione | portata | 1851 | Blitzcrank Impassive |
| undamaged_this_turn | condizione | NON PORTATA | 209 | Affectionate Poro |
| you_have_n_or_more_units_here | condizione | NON PORTATA | 34088 | Trusty Ramhound |
| n_distinct_tags_among_friendlies | quantità | NON PORTATA | 1835 | Daisy!, Friendship |

## Trigger e parole chiave

Letta da: **Rust** (il nome compare nei sorgenti di rbsim-core), **solo Python** (da portare), **nessuno** (un'etichetta senza regole nel motore: LEGION si legge dalla condizione, DEATHKNELL dal trigger `on_death`).

| Nome | Che cos'è | Letta da | Carte |
|---|---|---|---|
| activated | trigger | Rust | Iridescent Avian |
| cost_modifier | trigger | Rust | Daisy! |
| on_attack | trigger | Rust | Daisy! |
| on_cast | trigger | Rust | Back Off, Block, Friendship, Grand Strategem, Hush, Not So Fast, Raucous Anthem, Salvage |
| on_combat_end | trigger | Rust | Affectionate Poro |
| on_conquer | trigger | Rust | Ivern Green Father |
| on_hold | trigger | Rust | Blitzcrank Impassive, Ivern Green Father, Ivern Nurturer, Vilemaw |
| on_play | trigger | Rust | Blitzcrank Impassive, Defy, Disarming Rake, Fallen Feline, Frisky Hunter, Ivern Nurturer, Janna Savior |
| passive | trigger | Rust | Forbidding Waste, Rockfall Path, Trusty Ramhound, Vilemaw, Vilemaw's Lair |
| self_enter_ready | trigger | Rust | Daisy! |
| ACTION | parola chiave | Rust | Back Off, Block, Grand Strategem, Salvage |
| AMBUSH | parola chiave | Rust | Vilemaw |
| DEFLECT | parola chiave | Rust | Bird |
| HIDDEN | parola chiave | Rust | Back Off, Block |
| REACTION | parola chiave | Rust | Defy, Friendship, Hush, Janna Savior, Not So Fast |
| SHIELD | parola chiave | Rust | Mutated Mouser, Stalwart Poro |
| TANK | parola chiave | Rust | Blitzcrank Impassive, Mutated Mouser |

## Effetti per carta

| Carta | Verbo | Trigger | Tempo | Condizione | Bersaglio | Costo |
|---|---|---|---|---|---|---|
| Affectionate Poro | draw_cards | on_combat_end |  | undamaged_this_turn |  |  |
| Back Off | stun_unit | on_cast | action |  | chosen_unit |  |
| Back Off | draw_cards | on_cast | action | played_from_hand |  |  |
| Blitzcrank Impassive | move_unit | on_play |  | this_is_at_battlefield | enemy_unit |  |
| Blitzcrank Impassive | recall_unit | on_hold |  |  | self |  |
| Block | give_temporary_shield | on_cast | action |  | chosen_unit |  |
| Block | give_keyword | on_cast | action |  | it |  |
| Daisy! | enter_ready | self_enter_ready |  |  |  |  |
| Daisy! | reduce_cost | cost_modifier |  |  |  |  |
| Daisy! | stun_unit | on_attack |  | has_all_pet_tags | enemy_unit |  |
| Defy | counter_spell | on_play |  |  |  |  |
| Disarming Rake | kill_gear | on_play |  |  | chosen_gear |  |
| Fallen Feline | name_spell | on_play |  |  |  |  |
| Forbidding Waste | lone_defender_minus | passive |  |  |  |  |
| Friendship | grant_temporary_might | on_cast | reaction |  | chosen_unit |  |
| Frisky Hunter | play_token | on_play |  |  | all_friendly_units_here |  |
| Grand Strategem | grant_temporary_might | on_cast |  |  | all_friendly_units_anywhere |  |
| Hush | counter_spell | on_cast | reaction |  | chosen_spell |  |
| Iridescent Avian | buff_unit | activated |  |  | friendly_unit | tap |
| Ivern Green Father | green_father_brush | on_conquer |  |  |  |  |
| Ivern Green Father | green_father_brush | on_hold |  |  |  |  |
| Ivern Nurturer | dig | on_play |  |  |  |  |
| Ivern Nurturer | dig | on_hold |  |  |  |  |
| Janna Savior | heal_unit | on_play | reaction |  | all_friendly_units_here |  |
| Janna Savior | move_unit | on_play | reaction |  | enemy_unit |  |
| Not So Fast | counter_spell | on_cast | reaction |  | chosen_spell |  |
| Raucous Anthem | ready_units | on_cast |  |  | all_friendly_units_anywhere |  |
| Raucous Anthem | grant_temporary_might | on_cast |  |  | all_friendly_units_anywhere |  |
| Rockfall Path | no_unit_plays_here | passive |  |  |  |  |
| Salvage | kill_gear | on_cast | action |  | chosen_gear |  |
| Salvage | draw_cards | on_cast | action |  |  |  |
| Trusty Ramhound | grant_might | passive |  | you_have_n_or_more_units_here | self |  |
| Vilemaw | weaker_enemies_no_damage | passive |  |  |  |  |
| Vilemaw | draw_cards | on_hold |  |  |  |  |
| Vilemaw's Lair | no_moves_to_base_from_here | passive |  |  |  |  |

## Sintesi

- Carte: 27; effetti: 35; verbi: 23 (handler Rust 11, marcatori 6); condizioni 5, quantità 1, trigger 10, parole chiave 7.
- Non portato: counter_spell, dig, green_father_brush, heal_unit, name_spell, ready_units, condizione has_all_pet_tags, condizione played_from_hand, condizione undamaged_this_turn, condizione you_have_n_or_more_units_here, quantità n_distinct_tags_among_friendlies.
- Mai eseguiti nel campione: grant_might.
