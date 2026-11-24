# Inventario Sett (porting Rust)

Generato da `python scripts/rust/inventario.py --liste S --matchup ES KS RS IS Es Ks Rs Is --partite 30`. Esecuzioni: chiamate Python su 90 partite per matchup e per posto (ES, KS, RS, IS, Es, Ks, Rs, Is, ciascuno anche rovesciato; minuscola = la lista con la sideboard nel mazzo, `riftbound/rs/mazzi.py`): self-play PPO a pesi dal seme 1, PPO contro simple_trade, random contro PPO. Sono le partite che il motore Rust gioca identiche.

## Carte

| Carta | Dove | Tipo | Parole chiave | Già in EKRI |
|---|---|---|---|---|
| Call to Glory | Sett mazzo | SPELL | REACTION | no |
| Decree of Strength | Sett sideboard | SPELL | — | sì |
| Decree of Unity | Sett sideboard | SPELL | — | no |
| Fiora Victorious | Sett mazzo | CHAMPION | — | no |
| First Mate | Sett mazzo | UNIT | — | sì |
| Irresistible Faefolk | Sett mazzo | UNIT | — | sì |
| Kinkou Initiate | Sett mazzo | UNIT | — | sì |
| Monastery of Hirana | Sett campi | BATTLEFIELD | — | no |
| Packed Amphitheater | Sett campi | BATTLEFIELD | — | sì |
| Pillaged Armory | Sett mazzo | GEAR | DEPLOY | no |
| Pit Rookie | Sett mazzo | UNIT | — | sì |
| Punch First | Sett mazzo | SPELL | ACTION | sì |
| Rampage | Sett mazzo | SPELL | — | sì |
| Rengar Trophy Hunter | Sett mazzo | CHAMPION | AMBUSH | sì |
| Repulse | Sett sideboard | SPELL | REACTION | no |
| Ruin Runner | Sett mazzo | UNIT | — | sì |
| Sabotage | Sett sideboard | SPELL | — | sì |
| Salvage | Sett sideboard | SPELL | ACTION | sì |
| Sett Kingpin | Sett campione | CHAMPION | TANK | no |
| Sett The Boss | Sett leggenda | LEGEND | — | no |
| Showstopper | Sett mazzo | SPELL | — | no |
| Trifarian Captain | Sett mazzo | UNIT | — | no |
| Valley of Idols | Sett campi | BATTLEFIELD | — | no |
| Vi Peacekeeper | Sett mazzo | CHAMPION | AMBUSH | no |

## Verbi

Stato in Rust: **handler** (rbsim-core `run_effect`), **marcatore** (nessun handler in Python: il motore lo legge dove serve, porting con la funzione che lo legge), **NON PORTATO** (handler Python senza traduzione: in Rust darebbe `NotPorted`).

| Verbo | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|
| ambush | marcatore | 0 | Rengar Trophy Hunter |
| buff_unit | handler | 11642 | Pillaged Armory, Pit Rookie, Showstopper, Valley of Idols |
| cant_be_chosen | marcatore | 0 | Ruin Runner |
| counter_spell | handler | 894 | Repulse |
| dig | handler | 4306 | Trifarian Captain |
| draw_cards | handler | 9845 | Kinkou Initiate, Monastery of Hirana, Salvage |
| fight | handler | 2128 | Rampage |
| give_keyword | handler | 403 | Fiora Victorious |
| grant_might | handler | 0 | Packed Amphitheater |
| grant_temporary_might | handler | 16822 | Call to Glory, Punch First, Rampage |
| grant_temporary_might_per_friendly | NON PORTATO | 0 | Sett Kingpin |
| kill_gear | handler | 984 | Salvage |
| kill_unit_or_gear | NON PORTATO | 360 | Decree of Unity |
| move_unit | handler | 4468 | Irresistible Faefolk, Showstopper |
| ready_unit | handler | 9293 | First Mate, Sett The Boss |
| recycle_from_opponent_hand | handler | 2015 | Decree of Strength, Sabotage |
| sett_save | marcatore | 0 | Sett The Boss |
| spend_buff_free | marcatore | 0 | Call to Glory |
| stun_unit | handler | 1621 | Vi Peacekeeper |

## Condizioni e quantità

Condizioni (`_check_condition`, Rust `check_condition`) e fonti di quantità (`_amount`, Rust `effect_amount`). Esecuzioni: valutazioni in Python.

| Tipo | Che cos'è | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|---|
| friendly_total_might_at_least | condizione | portata | 3406 | Kinkou Initiate |
| kicker_paid | condizione | portata | 2399 | Rampage |
| moved_to_battlefield | condizione | portata | 1951 | Irresistible Faefolk |
| this_is_mighty | condizione | NON PORTATA | 125865 | Fiora Victorious |

## Trigger e parole chiave

Letta da: **Rust** (il nome compare nei sorgenti di rbsim-core), **solo Python** (da portare), **nessuno** (un'etichetta senza regole nel motore: LEGION si legge dalla condizione, DEATHKNELL dal trigger `on_death`).

| Nome | Che cos'è | Letta da | Carte |
|---|---|---|---|
| on_attack | trigger | Rust | Vi Peacekeeper |
| on_cast | trigger | Rust | Call to Glory, Decree of Strength, Decree of Unity, Punch First, Rampage, Repulse, Sabotage, Salvage, Showstopper |
| on_conquer | trigger | Rust | Monastery of Hirana, Pillaged Armory, Sett The Boss |
| on_move | trigger | Rust | Irresistible Faefolk |
| on_play | trigger | Rust | First Mate, Kinkou Initiate, Pillaged Armory, Pit Rookie, Trifarian Captain |
| on_unit_played_here | trigger | Rust | Valley of Idols |
| passive | trigger | Rust | Call to Glory, Fiora Victorious, Packed Amphitheater, Rengar Trophy Hunter, Ruin Runner, Sett Kingpin, Sett The Boss |
| ACTION | parola chiave | Rust | Punch First, Salvage |
| AMBUSH | parola chiave | Rust | Rengar Trophy Hunter, Vi Peacekeeper |
| DEPLOY | parola chiave | Rust | Pillaged Armory |
| REACTION | parola chiave | Rust | Call to Glory, Repulse |
| TANK | parola chiave | Rust | Sett Kingpin |

## Effetti per carta

| Carta | Verbo | Trigger | Tempo | Condizione | Bersaglio | Costo |
|---|---|---|---|---|---|---|
| Call to Glory | spend_buff_free | passive |  |  |  |  |
| Call to Glory | grant_temporary_might | on_cast | reaction |  | chosen_unit |  |
| Decree of Strength | recycle_from_opponent_hand | on_cast |  |  |  |  |
| Decree of Unity | kill_unit_or_gear | on_cast |  |  |  |  |
| Fiora Victorious | give_keyword | passive |  | this_is_mighty | self |  |
| Fiora Victorious | give_keyword | passive |  | this_is_mighty | self |  |
| Fiora Victorious | give_keyword | passive |  | this_is_mighty | self |  |
| First Mate | ready_unit | on_play |  |  | chosen_unit |  |
| Irresistible Faefolk | move_unit | on_move |  | moved_to_battlefield | enemy_unit |  |
| Kinkou Initiate | draw_cards | on_play |  | friendly_total_might_at_least |  |  |
| Monastery of Hirana | draw_cards | on_conquer |  |  |  | spend_buff |
| Packed Amphitheater | grant_might | passive |  |  | all_units_here |  |
| Pillaged Armory | buff_unit | on_play |  |  | friendly_unit |  |
| Pillaged Armory | buff_unit | on_conquer |  |  | friendly_unit |  |
| Pit Rookie | buff_unit | on_play |  |  | friendly_unit |  |
| Punch First | grant_temporary_might | on_cast | action |  | chosen_unit |  |
| Rampage | grant_temporary_might | on_cast |  | kicker_paid | friendly_unit |  |
| Rampage | fight | on_cast |  |  |  |  |
| Rengar Trophy Hunter | ambush | passive |  |  |  |  |
| Repulse | counter_spell | on_cast | reaction |  | chosen_spell |  |
| Ruin Runner | cant_be_chosen | passive |  |  | self |  |
| Sabotage | recycle_from_opponent_hand | on_cast |  |  |  |  |
| Salvage | kill_gear | on_cast | action |  | chosen_gear |  |
| Salvage | draw_cards | on_cast | action |  |  |  |
| Sett Kingpin | grant_temporary_might_per_friendly | passive |  |  | self |  |
| Sett The Boss | sett_save | passive |  |  |  |  |
| Sett The Boss | ready_unit | on_conquer |  |  | self |  |
| Showstopper | buff_unit | on_cast |  |  | friendly_unit |  |
| Showstopper | move_unit | on_cast |  |  | it |  |
| Trifarian Captain | dig | on_play |  |  |  |  |
| Valley of Idols | buff_unit | on_unit_played_here |  |  | triggering_unit | energy |
| Vi Peacekeeper | stun_unit | on_attack |  |  | enemy_unit |  |

## Sintesi

- Carte: 24; effetti: 32; verbi: 19 (handler Rust 13, marcatori 4); condizioni 4, quantità 0, trigger 7, parole chiave 5.
- Non portato: grant_temporary_might_per_friendly, kill_unit_or_gear, condizione this_is_mighty.
- Mai eseguiti nel campione: grant_might, grant_temporary_might_per_friendly.
