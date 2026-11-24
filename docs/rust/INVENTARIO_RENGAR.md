# Inventario Rengar (porting Rust)

Generato da `python scripts/rust/inventario.py --liste R --matchup ER KR Er Kr --partite 30`. Esecuzioni: chiamate Python su 90 partite per matchup e per posto (ER, KR, Er, Kr, ciascuno anche rovesciato; minuscola = la lista con la sideboard nel mazzo, `riftbound/rs/mazzi.py`): self-play PPO a pesi dal seme 1, PPO contro simple_trade, random contro PPO. Sono le partite che il motore Rust gioca identiche.

## Carte

| Carta | Dove | Tipo | Parole chiave | Già in EK |
|---|---|---|---|---|
| Bilgewater Tracker | Rengar sideboard | UNIT | — | no |
| Brittle Steel | Rengar sideboard | SPELL | FLOW | no |
| Decree of Strength | Rengar sideboard | SPELL | — | sì |
| Elnuk Herd | Rengar mazzo | UNIT | HIDDEN | no |
| Ferrous Forerunner | Rengar mazzo, Rengar sideboard | UNIT | DEATHKNELL | no |
| First Mate | Rengar mazzo | UNIT | — | no |
| Grim Apothecary | Rengar mazzo | UNIT | AMBUSH | no |
| Hunters' Circle | Rengar campi | BATTLEFIELD | — | no |
| Inferna | Rengar mazzo | UNIT | AMBUSH, ASSAULT 2 | no |
| Irresistible Faefolk | Rengar mazzo | UNIT | — | sì |
| Kai'Sa Survivor | Rengar mazzo | CHAMPION | ACCELERATE | no |
| Kinkou Initiate | Rengar mazzo | UNIT | — | no |
| Mech | creata da Ferrous Forerunner | UNIT | — | no |
| Nidalee Cat Form | Rengar mazzo | CHAMPION | AMBUSH | no |
| Noxus Hopeful | Rengar mazzo | UNIT | LEGION | no |
| Pit Rookie | Rengar mazzo | UNIT | — | no |
| Punch First | Rengar mazzo | SPELL | ACTION | sì |
| Pyke Dockside Butcher | Rengar mazzo | CHAMPION | HIDDEN, GANKING | no |
| Rampage | Rengar mazzo, Rengar sideboard | SPELL | — | sì |
| Rengar Pridestalker | Rengar leggenda | LEGEND | — | no |
| Rengar Trophy Hunter | Rengar campione | CHAMPION | AMBUSH | sì |
| Sabotage | Rengar mazzo, Rengar sideboard | SPELL | — | sì |
| Seat of Power | Rengar campi | BATTLEFIELD | — | no |
| Sunken Temple | Rengar campi | BATTLEFIELD | — | no |
| Thrill of the Hunt | Rengar mazzo | SPELL | REACTION | no |

## Verbi

Stato in Rust: **handler** (rbsim-core `run_effect`), **marcatore** (nessun handler in Python: il motore lo legge dove serve, porting con la funzione che lo legge), **NON PORTATO** (handler Python senza traduzione: in Rust darebbe `NotPorted`).

| Verbo | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|
| ambush | marcatore | 0 | Rengar Trophy Hunter |
| blink_unit | handler | 920 | Thrill of the Hunt |
| buff_unit | handler | 1346 | Pit Rookie |
| deal_damage | handler | 482 | Bilgewater Tracker |
| draw_cards | handler | 7307 | Kai'Sa Survivor, Kinkou Initiate, Nidalee Cat Form, Seat of Power, Sunken Temple |
| fight | handler | 1199 | Rampage |
| first_play_here_discount | marcatore | 0 | Hunters' Circle |
| grant_temporary_might | handler | 19412 | Elnuk Herd, Punch First, Pyke Dockside Butcher, Rampage, Rengar Pridestalker |
| kill_gear | handler | 298 | Brittle Steel |
| move_unit | handler | 1750 | Irresistible Faefolk |
| play_token | handler | 2611 | Ferrous Forerunner |
| ready_unit | handler | 976 | First Mate, Pyke Dockside Butcher |
| recall_unit | handler | 4135 | Elnuk Herd, Grim Apothecary |
| recycle_from_opponent_hand | handler | 1527 | Decree of Strength, Sabotage |
| reduce_cost | marcatore | 0 | Noxus Hopeful |

## Condizioni e quantità

Condizioni (`_check_condition`, Rust `check_condition`) e fonti di quantità (`_amount`, Rust `effect_amount`). Esecuzioni: valutazioni in Python.

| Tipo | Che cos'è | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|---|
| friendly_mighty_unit_here | condizione | portata | 674 | Sunken Temple |
| friendly_total_might_at_least | condizione | portata | 1236 | Kinkou Initiate |
| kicker_paid | condizione | portata | 1706 | Pyke Dockside Butcher, Rampage |
| moved_to_battlefield | condizione | portata | 557 | Irresistible Faefolk |
| triggering_card_from_zone | condizione | portata | 10136 | Elnuk Herd |
| you_already_played_another_card_this_turn | condizione | portata | 5137 | Noxus Hopeful |
| other_battlefields_controlled | quantità | portata | 812 | Seat of Power |

## Trigger e parole chiave

Letta da: **Rust** (il nome compare nei sorgenti di rbsim-core), **solo Python** (da portare), **nessuno** (un'etichetta senza regole nel motore: LEGION si legge dalla condizione, DEATHKNELL dal trigger `on_death`).

| Nome | Che cos'è | Letta da | Carte |
|---|---|---|---|
| cost_modifier | trigger | Rust | Noxus Hopeful |
| on_cast | trigger | Rust | Brittle Steel, Decree of Strength, Punch First, Rampage, Sabotage, Thrill of the Hunt |
| on_conquer | trigger | Rust | Kai'Sa Survivor, Seat of Power, Sunken Temple |
| on_death | trigger | Rust | Ferrous Forerunner |
| on_friendly_unit_played | trigger | Rust | Rengar Pridestalker |
| on_move | trigger | Rust | Irresistible Faefolk |
| on_play | trigger | Rust | Bilgewater Tracker, Elnuk Herd, First Mate, Grim Apothecary, Kinkou Initiate, Pit Rookie, Pyke Dockside Butcher |
| on_self_played | trigger | Rust | Elnuk Herd |
| on_win_combat | trigger | Rust | Nidalee Cat Form |
| passive | trigger | Rust | Hunters' Circle, Rengar Trophy Hunter |
| ACCELERATE | parola chiave | Rust | Kai'Sa Survivor |
| ACTION | parola chiave | Rust | Punch First |
| AMBUSH | parola chiave | Rust | Grim Apothecary, Inferna, Nidalee Cat Form, Rengar Trophy Hunter |
| ASSAULT | parola chiave | Rust | Inferna |
| DEATHKNELL | parola chiave | nessuno (testo) | Ferrous Forerunner |
| FLOW | parola chiave | nessuno (testo) | Brittle Steel |
| GANKING | parola chiave | Rust | Pyke Dockside Butcher |
| HIDDEN | parola chiave | Rust | Elnuk Herd, Pyke Dockside Butcher |
| LEGION | parola chiave | nessuno (testo) | Noxus Hopeful |
| REACTION | parola chiave | Rust | Thrill of the Hunt |

## Effetti per carta

| Carta | Verbo | Trigger | Tempo | Condizione | Bersaglio | Costo |
|---|---|---|---|---|---|---|
| Bilgewater Tracker | deal_damage | on_play |  |  | chosen_unit |  |
| Brittle Steel | kill_gear | on_cast |  |  | chosen_unit |  |
| Decree of Strength | recycle_from_opponent_hand | on_cast |  |  |  |  |
| Elnuk Herd | grant_temporary_might | on_play |  |  | friendly_unit |  |
| Elnuk Herd | recall_unit | on_self_played |  | triggering_card_from_zone | self |  |
| Ferrous Forerunner | play_token | on_death |  |  | battlefield |  |
| First Mate | ready_unit | on_play |  |  | chosen_unit |  |
| Grim Apothecary | recall_unit | on_play |  |  | friendly_unit |  |
| Hunters' Circle | first_play_here_discount | passive |  |  |  |  |
| Irresistible Faefolk | move_unit | on_move |  | moved_to_battlefield | enemy_unit |  |
| Kai'Sa Survivor | draw_cards | on_conquer |  |  | actor |  |
| Kinkou Initiate | draw_cards | on_play |  | friendly_total_might_at_least |  |  |
| Nidalee Cat Form | draw_cards | on_win_combat |  |  |  |  |
| Noxus Hopeful | reduce_cost | cost_modifier |  | you_already_played_another_card_this_turn |  |  |
| Pit Rookie | buff_unit | on_play |  |  | friendly_unit |  |
| Punch First | grant_temporary_might | on_cast | action |  | chosen_unit |  |
| Pyke Dockside Butcher | ready_unit | on_play |  | kicker_paid | self |  |
| Pyke Dockside Butcher | grant_temporary_might | on_play |  | kicker_paid | self |  |
| Rampage | grant_temporary_might | on_cast |  | kicker_paid | friendly_unit |  |
| Rampage | fight | on_cast |  |  |  |  |
| Rengar Pridestalker | grant_temporary_might | on_friendly_unit_played |  |  | chosen_unit |  |
| Rengar Trophy Hunter | ambush | passive |  |  |  |  |
| Sabotage | recycle_from_opponent_hand | on_cast |  |  |  |  |
| Seat of Power | draw_cards | on_conquer |  |  |  |  |
| Sunken Temple | draw_cards | on_conquer |  | friendly_mighty_unit_here |  | energy |
| Thrill of the Hunt | blink_unit | on_cast | reaction |  |  |  |

## Sintesi

- Carte: 25; effetti: 26; verbi: 15 (handler Rust 12, marcatori 3); condizioni 6, quantità 1, trigger 10, parole chiave 10.
- Non portato: niente.
- Mai eseguiti nel campione: nessuno.
