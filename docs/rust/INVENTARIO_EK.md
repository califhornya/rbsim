# Inventario EK (porting Rust, F3)

Generato da `python scripts/rust/inventario.py --partite 30`. Esecuzioni: chiamate degli handler Python su 90 partite EK (self-play PPO a pesi dal seme 1, PPO contro simple_trade, random contro PPO), le stesse che il motore Rust gioca identiche.

## Carte

| Carta | Dove | Tipo | Parole chiave |
|---|---|---|---|
| Abandon | Evelynn sideboard | SPELL | REACTION, PREDICT 1 |
| Acceptable Losses | Kha'Zix sideboard | SPELL | ACTION |
| An Offer You Can't Refuse | Evelynn sideboard, Kha'Zix sideboard | SPELL | ACTION |
| Bandle Scouts' Academy | Evelynn campi | BATTLEFIELD | — |
| Bedeviling Stranger | Evelynn mazzo | UNIT | HIDDEN |
| Boots of Swiftness | Evelynn mazzo | GEAR | EQUIP 1 |
| Decree of Strength | Kha'Zix sideboard | SPELL | — |
| Edge of Night | Evelynn mazzo | GEAR | HIDDEN, EQUIP 1 |
| Evelynn Agony's Embrace | Evelynn leggenda | LEGEND | — |
| Evelynn Entrancing | Evelynn campione, Kha'Zix mazzo | CHAMPION | HIDDEN, BACKLINE |
| Fizz Trickster | Evelynn mazzo, Kha'Zix mazzo | CHAMPION | — |
| Gold | creata da Bandle Scouts' Academy | GEAR | — |
| Grim Resolve | Kha'Zix mazzo | SPELL | ACTION |
| Gust | Evelynn mazzo | SPELL | REACTION |
| Gutter Guardian | Evelynn mazzo | UNIT | HIDDEN, SHOW OFF |
| Hold 'Em | Evelynn mazzo | SPELL | ACTION |
| Irresistible Faefolk | Kha'Zix mazzo | UNIT | — |
| K'Sante Courageous | Evelynn mazzo | CHAMPION | ACCELERATE, SHIELD 2 |
| Kha'Zix Mutating Horror | Kha'Zix campione | CHAMPION | AMBUSH |
| Kha'Zix Voidreaver | Kha'Zix leggenda | LEGEND | — |
| Momentary Companion | Evelynn mazzo | UNIT | HIDDEN |
| Onslaught | Evelynn sideboard, Kha'Zix mazzo | SPELL | FLOW |
| Packed Amphitheater | Evelynn campi, Kha'Zix campi | BATTLEFIELD | — |
| Punch First | Evelynn mazzo, Kha'Zix mazzo | SPELL | ACTION |
| Pyke Returned | Evelynn mazzo | CHAMPION | HIDDEN, BACKLINE |
| Rakelstake | Evelynn campi | BATTLEFIELD | — |
| Rampage | Evelynn mazzo, Kha'Zix mazzo | SPELL | — |
| Ravenbloom Prefect | Evelynn sideboard | UNIT | — |
| Rebuke | Evelynn sideboard | SPELL | ACTION |
| Reckless Innovator | Evelynn mazzo, Kha'Zix mazzo | UNIT | ACCELERATE |
| Rengar Trophy Hunter | Evelynn mazzo, Kha'Zix mazzo | CHAMPION | AMBUSH |
| Ruin Runner | Evelynn sideboard | UNIT | — |
| Sabotage | Kha'Zix mazzo, Kha'Zix sideboard | SPELL | — |
| Sandswept Tomb | Kha'Zix campi | BATTLEFIELD | — |
| Shadow Clone | creata da Zed Without a Sound | UNIT | — |
| Star-Crossed | Evelynn mazzo, Kha'Zix mazzo | SPELL | REACTION |
| Switcheroo | Evelynn mazzo, Kha'Zix mazzo | SPELL | HIDDEN, ACTION |
| Tentacle | creata da Up from the Deep | UNIT | — |
| The Good Stuff | Evelynn mazzo, Kha'Zix mazzo | GEAR | DEPLOY |
| Traveling Merchant | Kha'Zix mazzo | UNIT | — |
| Unyielding Spirit | Evelynn sideboard, Kha'Zix sideboard | SPELL | REACTION |
| Up from the Deep | Kha'Zix mazzo | SPELL | FLOW |
| Vex Apathetic | Evelynn mazzo, Kha'Zix mazzo | CHAMPION | DEFLECT |
| Void Assault | Kha'Zix mazzo | SPELL | — |
| Zaun Warrens | Kha'Zix campi | BATTLEFIELD | — |
| Zed Without a Sound | Kha'Zix mazzo | CHAMPION | — |

## Verbi

Stato in Rust: **handler** (rbsim-core `run_effect`), **marcatore** (nessun handler in Python: il motore lo legge dove serve, porting con la funzione che lo legge), **NON PORTATO** (handler Python senza traduzione: in Rust darebbe `NotPorted`).

| Verbo | Stato Rust | Esecuzioni | Carte |
|---|---|---|---|
| ambush | marcatore | 0 | Rengar Trophy Hunter |
| attach_gear | handler | 40 | Edge of Night |
| banish_self_and_gear | NON PORTATO | 0 | Ravenbloom Prefect |
| bounce_enemy_at_crowded_battlefield | handler | 66 | Bedeviling Stranger |
| buff_unit | handler | 200 | Kha'Zix Voidreaver |
| cant_be_chosen | marcatore | 0 | Ruin Runner |
| channel_rune | handler | 88 | K'Sante Courageous |
| counter_spell | NON PORTATO | 0 | Abandon |
| discard_card | handler | 898 | Evelynn Agony's Embrace, The Good Stuff, Traveling Merchant, Zaun Warrens |
| draw_cards | handler | 1154 | Evelynn Agony's Embrace, The Good Stuff, Traveling Merchant, Zaun Warrens |
| fight | handler | 117 | Rampage |
| gain_power_any_domain | handler | 189 | Gold, Gutter Guardian |
| gain_xp | handler | 312 | Kha'Zix Mutating Horror, Kha'Zix Voidreaver |
| give_keyword | handler | 26 | Boots of Swiftness, Momentary Companion |
| give_temporary_assault | handler | 0 | Shadow Clone |
| grant_might | handler | 0 | Packed Amphitheater |
| grant_temporary_might | handler | 800 | Grim Resolve, Hold 'Em, Kha'Zix Mutating Horror, Onslaught, Punch First, Rampage |
| kill_gear | NON PORTATO | 0 | Acceptable Losses, An Offer You Can't Refuse |
| mode_choice | handler | 274 | Reckless Innovator |
| move_unit | handler | 352 | Evelynn Entrancing, Irresistible Faefolk, Kha'Zix Voidreaver, Void Assault |
| play_from_trash | handler | 130 | Fizz Trickster |
| play_token | handler | 568 | An Offer You Can't Refuse, Bandle Scouts' Academy, Pyke Returned, Up from the Deep, Zed Without a Sound |
| predict | handler | 234 | Abandon, Rakelstake |
| prevent_spell_damage_this_turn | NON PORTATO | 0 | Unyielding Spirit |
| recall_unit | handler | 699 | Gust, Rebuke, Star-Crossed |
| recycle_from_opponent_hand | handler | 48 | Decree of Strength, Sabotage |
| reduce_cost | marcatore | 0 | Hold 'Em |
| reduce_cost_here | marcatore | 0 | Sandswept Tomb |
| return_gear_to_hand | handler | 220 | The Good Stuff |
| sequence | handler | 118 | Vex Apathetic |
| show_off | marcatore | 0 | Gutter Guardian |
| swap_might | handler | 245 | Switcheroo |
| swap_position | handler | 16 | Zed Without a Sound |
| xp_when_it_wins | handler | 61 | Grim Resolve |

## Effetti per carta

| Carta | Verbo | Trigger | Tempo | Condizione | Bersaglio | Costo |
|---|---|---|---|---|---|---|
| Abandon | counter_spell | on_cast | reaction |  | chosen_spell |  |
| Abandon | predict | on_cast | reaction |  |  |  |
| Acceptable Losses | kill_gear | on_cast | action |  | each_player |  |
| An Offer You Can't Refuse | kill_gear | on_cast | action |  | chosen_unit |  |
| An Offer You Can't Refuse | play_token | on_cast | action |  | it_controller |  |
| Bandle Scouts' Academy | play_token | on_hide_here |  |  |  |  |
| Bedeviling Stranger | bounce_enemy_at_crowded_battlefield | on_play |  |  |  |  |
| Boots of Swiftness | give_keyword | passive |  |  |  |  |
| Decree of Strength | recycle_from_opponent_hand | on_cast |  |  |  |  |
| Edge of Night | attach_gear | on_self_played |  | triggering_card_from_zone | friendly_unit |  |
| Evelynn Agony's Embrace | draw_cards | on_card_played |  | triggering_card_from_zone |  |  |
| Evelynn Agony's Embrace | discard_card | on_card_played |  | all_of |  |  |
| Evelynn Entrancing | move_unit | on_self_played |  | all_of | enemy_unit |  |
| Fizz Trickster | play_from_trash | on_play |  |  |  |  |
| Gold | gain_power_any_domain | activated | reaction |  |  | sacrifice_self,tap |
| Grim Resolve | grant_temporary_might | on_cast | action |  | friendly_unit |  |
| Grim Resolve | xp_when_it_wins | on_cast | action |  |  |  |
| Gust | recall_unit | on_cast | reaction |  | chosen_unit |  |
| Gutter Guardian | show_off | on_play |  |  |  |  |
| Gutter Guardian | gain_power_any_domain | on_play |  | showed_off |  |  |
| Hold 'Em | reduce_cost | cost_modifier |  | played_to_battlefield_this_turn |  |  |
| Hold 'Em | grant_temporary_might | on_cast | action |  | chosen_unit |  |
| Irresistible Faefolk | move_unit | on_move |  | moved_to_battlefield | enemy_unit |  |
| K'Sante Courageous | channel_rune | on_hold |  |  |  |  |
| Kha'Zix Mutating Horror | grant_temporary_might | on_attack |  | enemy_alone_here | self |  |
| Kha'Zix Mutating Horror | gain_xp | on_attack |  | enemy_alone_here |  |  |
| Kha'Zix Mutating Horror | grant_temporary_might | on_defend |  | enemy_alone_here | self |  |
| Kha'Zix Mutating Horror | gain_xp | on_defend |  | enemy_alone_here |  |  |
| Kha'Zix Voidreaver | gain_xp | on_win_combat |  |  |  |  |
| Kha'Zix Voidreaver | buff_unit | activated |  |  | chosen_unit | spend_xp,tap |
| Kha'Zix Voidreaver | move_unit | activated |  |  | friendly_unit | spend_xp,tap |
| Momentary Companion | give_keyword | on_play |  | not_your_turn | self |  |
| Onslaught | grant_temporary_might | on_cast |  |  | chosen_unit |  |
| Packed Amphitheater | grant_might | passive |  |  | all_units_here |  |
| Punch First | grant_temporary_might | on_cast | action |  | chosen_unit |  |
| Pyke Returned | play_token | on_enemy_unit_died |  | this_is_at_battlefield |  |  |
| Rakelstake | predict | on_first_unit_here |  |  | actor |  |
| Rampage | grant_temporary_might | on_cast |  | kicker_paid | friendly_unit |  |
| Rampage | fight | on_cast |  |  |  |  |
| Ravenbloom Prefect | banish_self_and_gear | on_enemy_gear_played |  |  |  |  |
| Rebuke | recall_unit | on_cast | action |  | chosen_unit |  |
| Reckless Innovator | mode_choice | on_exhaust |  |  |  |  |
| Rengar Trophy Hunter | ambush | passive |  |  |  |  |
| Ruin Runner | cant_be_chosen | passive |  |  | self |  |
| Sabotage | recycle_from_opponent_hand | on_cast |  |  |  |  |
| Sandswept Tomb | reduce_cost_here | passive |  |  |  |  |
| Shadow Clone | give_temporary_assault | on_attack |  |  | self | banish_from_trash |
| Star-Crossed | recall_unit | on_cast | reaction |  | friendly_unit |  |
| Star-Crossed | recall_unit | on_cast | reaction |  | enemy_unit |  |
| Switcheroo | swap_might | on_play |  |  |  |  |
| The Good Stuff | discard_card | on_play |  |  |  |  |
| The Good Stuff | draw_cards | on_play |  |  |  |  |
| The Good Stuff | return_gear_to_hand | on_hold |  |  | self |  |
| Traveling Merchant | discard_card | on_move |  |  | actor |  |
| Traveling Merchant | draw_cards | on_move |  |  | actor |  |
| Unyielding Spirit | prevent_spell_damage_this_turn | on_cast |  |  |  |  |
| Up from the Deep | play_token | on_cast |  |  |  |  |
| Vex Apathetic | sequence | on_enemy_unit_played |  | this_is_at_battlefield |  |  |
| Void Assault | move_unit | on_cast |  |  | friendly_unit |  |
| Void Assault | move_unit | on_cast |  |  | enemy_unit |  |
| Zaun Warrens | discard_card | on_conquer |  |  | actor |  |
| Zaun Warrens | draw_cards | on_conquer |  |  | actor |  |
| Zed Without a Sound | play_token | on_conquer |  |  |  |  |
| Zed Without a Sound | swap_position | activated | action |  |  | domain,energy,power |

## Sintesi

- Carte: 46; effetti: 64; verbi: 34 (handler Rust 25, marcatori 5, non portati 4: banish_self_and_gear, counter_spell, kill_gear, prevent_spell_damage_this_turn).
- Verbi mai eseguiti nel campione: banish_self_and_gear, counter_spell, give_temporary_assault, grant_might, kill_gear, prevent_spell_damage_this_turn.
