"""Vocabolario condiviso engine↔parser. Modifica QUI quando estendi l'engine,
non duplicare le liste nel parser script.

Single source of truth for the vocabulary the engine understands. The parser
(`scripts/generate_effects.py`) imports these frozensets instead of redeclaring
them, and `loop.py` runs an import-time guard asserting its dispatch tables stay
in sync with these sets — so extending the engine without updating this module
fails loudly rather than drifting silently.
"""

from __future__ import annotations

# Trigger handled by _resolve_card_effects / _fire_units_trigger /
# _fire_turn_trigger and the passive / cost_modifier / death_replacement /
# activated dispatch paths in loop.py.
KNOWN_TRIGGERS: frozenset[str] = frozenset({
    "on_play", "on_cast",                       # play-time resolution
    "on_conquer", "on_hold",                    # scoring
    "on_attack", "on_defend",                   # combat designations
    "on_death",                                 # death-knell family
    "leaves_board",                             # any board exit (death/recall/bounce/banish)
    "on_move",                                  # move-into-battlefield
    "on_start_of_turn", "on_end_of_turn",       # turn boundaries
    "on_start_of_main",                         # the start of your Main Phase (Orianna Lady of Clockwork)
    "on_friendly_unit_played",
    "on_friendly_unit_death",
    "on_play_spell",
    "on_win_combat",
    "on_combat_end",                            # "When a combat that I was in ends"
    "passive",                                  # continuous abilities
    "activated",                                # main-phase tap-style
    "cost_modifier",                            # reduce_cost effects
    "death_replacement",                        # Guardian Angel / Zhonya's
    "on_reveal_from_top",                       # looked at/revealed from top of deck (Nocturne)
    "on_first_unit_here",                        # first non-token unit played here this turn (Star Spring)
    "on_showdown_begin",                         # a showdown begins at this unit's battlefield (Diana Lunari)
    "on_exhaust",                                # this unit/gear becomes exhausted (Reckless Innovator)
    "on_friendly_exhaust",                       # another friendly unit becomes exhausted (Riven Deserter)
    "on_hide_here",                              # a card is hidden at this battlefield (Bandle Scouts' Academy)
    "on_stun_enemy",                             # you stun one or more enemy units (Eclipse Herald, Leona legend)
    "on_card_played",                            # you play a card, from any zone (Kennen legend, Darius Trifarian)
    "on_unit_moves_from_here",                   # battlefield: a unit moves from here (Back-Alley Bar)
    "on_enemy_unit_played",                      # an opponent plays a unit / unit token (Vex Apathetic)
    "on_chosen",                                 # your spell or ability chooses me (Irelia Fervent)
    "on_readied",                                # I go from exhausted to ready (Irelia Fervent)
    "cost_aura",                                 # reduce_cost on OTHER cards you play (Eager Apprentice)
    "enter_ready_aura",                          # units you play matching `filter` enter ready (Magma Wurm)
    "on_hide",                                   # you hide a card (Katarina Reckless)
    "on_buffed",                                 # I get a buff (Simian Ancestor)
    "on_enemy_unit_moves",                       # an opponent's unit moves (Volibear Imposing)
    "on_stunned_enemy_dies_here",                # a stunned enemy unit dies here (Storm Raptor)
    "on_friendly_unit_readied",                  # you ready a friendly unit (Pirate's Haven)
    "on_friendly_unit_buffed",                   # you buff a friendly unit (Mistfall)
    "on_friendly_attack", "on_friendly_defend",  # a friendly unit attacks / defends (Mask of Foresight)
    "on_second_draw",                            # you draw your second card this turn (Frigid Jewel)
    "on_opponent_scores",                        # an opponent scores (Sumpworks Map)
    "on_enemy_unit_died",                        # an enemy unit dies (Nasus Guardian, Solari Shrine)
    "on_discarded",                              # you discard me (Flame Chompers)
    "on_friendly_chosen",                        # you choose a friendly unit (Spirit Wheel)
    "on_gear_ability_used",                      # you use a gear's ability (Prize of Progress)
    "on_combat_start_here",                      # a combat starts at this battlefield (Threshold of the Gray)
    "on_equipment_attached",                     # an Equipment is attached to me (Aphelios, Jax)
    "on_friendly_empowered",                     # you empower something else (Mel, Ambessa)
    "on_become_empowered",                       # I become EMPOWERED (Apprentice Mage, Kharox)
    "on_you_discard",                            # you discard a card (Jinx Rebel)
    "on_banish_own",                             # you banish a card you own (Zed)
    "on_unit_played_here",                       # a player plays a unit here (Valley of Idols)
    "on_self_played",                            # this card is played (from face down: Tornado Warrior)
    "trash_on_card_played",                      # in the trash, you play a card (Meticulous Restorationist)
    "on_enemy_gear_played",                      # an opponent plays a gear (Ravenbloom Prefect)
    "on_enemy_might_reduced",                    # you reduce an enemy unit's Might (Ahri Confident)
    "on_recycle",                                # you recycle cards to your Main Deck (Karma Channeler)
    "on_three_exhausted",                        # 3 units exhausted at once (Seraphine Inspiring)
    "on_friendly_gear_died_at_bf",               # a friendly gear at a battlefield dies (Battlefield Armorer)
    "trash_on_spell_kill",                       # in the trash, you kill a unit with a spell (Immortal Phoenix)
    "on_friendly_deploy",                        # you play a gear with DEPLOY (Jarvan IV Exemplar)
    "granted_to_legend",                         # a battlefield gives your legend an ability (Forge of the Fluft)
    "on_friendly_moves_from_here",               # a friendly unit moves from my location (Stealthy Pursuer)
    "on_attached",                               # this Equipment is attached to a unit (Shady Spectacles)
    "on_enemy_attack",                           # an enemy unit attacks a battlefield you control (Ahri Nine-Tailed Fox)
    "on_you_defend",                             # you defend at a battlefield, anywhere (Loyal Pup)
    "on_unit_dies_here",                         # battlefield: a non-token unit dies here (Black Rose Sanctum)
    "granted_to_units_here",                     # battlefield: units here have this ability (Gardens of Becoming)
    "on_recycle_rune",                           # you recycle a rune (Sivir Battle Mistress)
    "trash_on_conquer",                          # in the trash, you conquer (Super Mega Death Rocket!)
    "on_buff_spent",                             # you spend a buff (Fae Dragon)
    "on_friendly_becomes_mighty",                # a friendly unit becomes MIGHTY (Fiora Worthy)
    "on_revealed",                               # revealed from your deck (Undertitan)
    "on_you_move_enemy",                         # you move an enemy unit (Blast Cone)
    "from_trash",                                # may be played from your trash (Undying Legion)
})

# Condition types accepted by Loop._check_condition.
# IMPORTANT: three conditions stay "safe-False" in the engine (loop.py:612-614)
# because the engine doesn't track their context yet. They are listed separately
# in SAFE_FALSE_CONDITIONS and are intentionally NOT in KNOWN_CONDITIONS — if the
# parser emitted them the engine would silently discard the gated effects.
KNOWN_CONDITIONS: frozenset[str] = frozenset({
    "you_have_n_or_more_runes",
    "you_have_n_or_more_units_here",
    "spell_cost_at_least",
    "spell_printed_cost_at_least",
    "this_is_alone",
    "this_is_mighty",
    "triggering_unit_is_mighty",
    "this_is_buffed",
    "this_is_empowered",
    "kicker_paid",
    "friendly_unit_died_this_turn",
    "you_played_n_spells_this_turn",
    "you_already_played_another_card_this_turn",
    "you_discarded_card_this_turn",
    "controller_has_xp_at_least",
    "card_in_trash_count_at_least",
    "you_control_subtype",
    "score_within_n_of_victory",
    "cards_burned_this_turn_at_least",
    "friendly_total_might_at_least",
    "you_control_n_or_more_gear",
    "showed_off",                    # SHOW OFF (§832) happened as this card was played
    "opponent_controls_a_battlefield",   # "If an opponent controls a battlefield, I enter ready"
    "you_control_no_other_units",        # "I enter ready if you control no other units"
    "card_with_my_name_in_trash",        # "... if you have a card with my name in your trash"
    "opponent_controls_stunned_unit",    # "If an opponent controls a stunned unit, ..."
    "stunned_enemy_here",                # "While there's a stunned enemy unit here" (Kennen)
    "empowered_times_at_least",          # "While I'm EMPOWERED three times" (Kayle Justified)
    "you_control_this_battlefield",      # "... if you control this battlefield" (DEPLOY gear, battlefields)
    "cards_in_hand_at_most",             # n: "if you have one or fewer cards in your hand"
    "first_turn_of_player",              # the actor's first turn of the game
    "rune_deck_empty",                   # "if your Rune Deck is empty"
    "enemy_alone_here",                  # "if an enemy unit is alone here"
    "one_on_one_here",                   # exactly one unit per side here ("one on one")
    "you_control_bf_with_exactly_n_units",  # n: "a battlefield with exactly two units there"
    "you_have_n_or_fewer_runes",         # n: "if you control 4 or fewer runes"
    "friendly_deployed_gear_here",       # "if there is a friendly gear with DEPLOY here"
    "played_to_battlefield_this_turn",   # "if you've played a unit or gear to a battlefield this turn"
    "your_turn_from_facedown",           # "If it's your turn and you played this from face down"
    "no_open_battlefields",              # "if there are no open battlefields"
    "this_is_at_battlefield",            # the source unit is at a battlefield (not in base)
    "triggering_unit_not_named",         # name: the unit that caused the trigger isn't named so ("non-Recruit")
    "triggering_unit_has_subtype",       # subtype: the unit that caused the trigger has this tag ("another Dragon")
    "fewer_runes_than_opponent",         # "if you control fewer runes than an opponent"
    "cards_played_this_turn_exactly",    # n: "when you play your second card in a turn"
    "opponent_played_n_spells_this_turn",  # n: "if an opponent has played another spell this turn"
    "triggering_card_matches",           # filter: "when you play a spell / a card with Energy cost [7]+"
    "triggering_card_not_from_hand",     # "when you play a card from anywhere other than your hand"
    "moved_to_battlefield",              # on_move: "when I move to a battlefield"
    "moved_from_battlefield",            # on_move: "when I move from a battlefield"
    "all_of",                            # conditions: [...] all hold
    "died_alone",                        # DEATHKNELL "if I died alone"
    "enemy_choices_this_turn_at_least",  # n: "if you've chosen enemy units twice this turn"
    "not_your_turn",                     # "when you play a card on an opponent's turn"
    "triggering_card_from_zone",         # zone: "when you play a card from face down"
    "played_to_controlled_battlefield",  # enter_ready_aura: "units you play to battlefields you control"
    "units_in_base_at_least",            # n: "if you have two or more other units in your base"
    "ready_enemy_here",                  # "if there is a ready enemy unit here"
    "moves_this_turn_exactly",           # n: "the first / third time I move in a turn"
    "moved_to_other_battlefield",        # "an opponent moves to a battlefield other than mine"
    "gained_xp_this_turn",               # "if you've gained XP this turn"
    "power_spent_this_turn_at_least",    # n: "if you've spent at least [rune] [rune] this turn"
    "triggering_unit_alone",             # "when a friendly unit attacks or defends alone"
    "triggering_unit_buffed",            # "when a buffed friendly unit dies"
    "in_showdown",                       # "during a showdown"
    "died_mighty",                       # DEATHKNELL "if I was MIGHTY"
    "units_here_exactly",                # n: "exactly one other unit you control here" (n=2)
    "triggering_unit_stunned",           # "when you kill a stunned enemy unit"
    "died_here",                         # "when an enemy unit here dies"
    "triggering_unit_mightiest",         # "a unit with Might greater than each other unit"
    "controller_has_facedown_card",      # "if you control a facedown card at a battlefield"
    "cards_in_hand_exactly",             # n: "if you have exactly 4 cards in hand"
    "units_at_battlefields_exactly",     # n: "exactly 4 units at battlefields"
    "not",                               # condition: {...} doesn't hold ("unless ...")
    "friendly_gear_here",                # "there's a friendly gear here"
    "holder_didnt_conquer_this_turn",    # Equipment: "if I didn't conquer this turn"
    "conquered_uncontrolled",            # "when I conquer a battlefield that was uncontrolled"
    "your_legend_exhausted",             # your legend is exhausted (Hall of Legends)
    "excess_damage_at_least",            # n: "if you assigned 3 or more excess damage" (this battlefield)
    "facedown_card_here",                # "if you control a facedown card here"
    "played_unit_gear_spell_this_turn",  # Swain Visionary
    "in_beginning_phase",                # during your Beginning Phase (Shard of Undoing)
    "triggering_unit_here",              # the unit is (or died) at my battlefield
    "has_all_pet_tags",                  # your units have Bird, Cat, Dog and Poro among them
    "signpost_possible",                 # Forgotten Signpost has a unit to exhaust and one to move
    "friendly_mighty_unit_here",         # "When you conquer here with one or more MIGHTY units" (Sunken Temple)
    "spell_spent_this_turn_at_least",    # n: "If you've spent [4] or more to play a spell this turn"
    "none_played_this_turn",             # filter: "the first friendly gear played each turn" (Ornn's Forge)
    "enemy_unit_died_this_turn",         # "If an enemy unit has died this turn" (Spoils of War)
    "any_gear_in_play",                  # "you may kill a gear. If you do, ..." (Adaptatron)
    "attached_this_turn",                # "If this was attached to me this turn" (Brutalizer)
    "died_in_combat",                    # "When I die in combat" (Draven Audacious)
    "gear_with_cost_at_most_in_play",    # n: "kill a gear with Energy cost no more than [1]" (Pickpocket)
    "this_unattached",                   # "(Use only if unattached.)" (The Zero Drive)
    "unit_died_this_turn",               # "If a unit died this turn" (Towering Pairofant)
    "friendly_died_in_beginning_phase",  # Shadow Watcher
    "played_from_hand",                  # "If you played this from your hand" (Back Off)
    "undamaged_this_turn",               # "if I haven't been dealt damage this turn" (Affectionate Poro)
    "this_in_combat",                    # "unless I'm in combat" (Akali Silent)
    "you_control_empowered",             # "if you control something that's EMPOWERED" (Shock Blast)
    "first_of_kind_this_turn",           # filter: "the first time you play a non-token gear each turn"
})

# Conditions the engine recognizes but always evaluates to False (no context).
# Kept distinct so the loop guard can assert the full handled set while the parser
# never emits them.
SAFE_FALSE_CONDITIONS: frozenset[str] = frozenset({
    "target_was_stunned",
})

# target_filter keys understood by effects._passes_filter.
KNOWN_FILTER_KEYS: frozenset[str] = frozenset({
    "exclude_self", "has_keyword", "lacks_keyword",
    "is_gear", "is_spell", "is_unit", "is_token",
    "subtype", "might_at_most", "might_at_least",
    # B2 additions
    "non_token", "is_buffed", "is_mighty", "might_less_than_self",
    "card_type", "is_legend", "is_champion", "moved_this_turn",
    # Step 3 additions (KNOWN_ISSUES #14/#17): ready-state + gear energy cost.
    "is_exhausted", "is_ready", "energy_at_most", "energy_at_least",
    "power_at_most", "power_at_least",   # zone effects: "no more than [rune]" / "[rune][rune] or more"
    "at_battlefield",                    # "a unit at a battlefield" (not in a base)
    "is_damaged",                        # "all damaged enemy units here" (Warwick Hunter)
    "is_attacking",                      # "Stun an attacking unit" (Thwonk!)
    "not_it",                            # "another unit" than the one just chosen (Piercing Light)
    "has_named_tag",                     # "a unit with the named tag" (The List)
    "domain", "is_empowered", "not_subtype", "fury_threatened",   # the Decrees, Aurok General, Ocean Drake
})

# amount_source values understood by effects._amount.
KNOWN_AMOUNT_SOURCES: frozenset[str] = frozenset({
    "self_might", "trash_count", "points", "friendly_mighty_units",
    # B2 additions
    "controller_points", "opponent_points", "highest_might_friendly",
    "cards_in_hand", "enemies_here", "friendly_units_here",
    "n_friendly_with_tag", "n_distinct_tags_among_friendlies",
    # SHOW OFF (§832): the shown object's info, snapshotted as the card was played.
    "shown_might", "shown_power_cost", "shown_energy_cost", "chosen_friendly_gear_energy",
    "self_shield",
    # Per-count cost reductions ("I cost [1] less for each ...").
    "cards_played_this_turn", "friendly_exhausted_units",
    "battlefields_conquered_this_turn", "hold_points_this_turn",
    "cards_with_my_name_in_trash",
    "other_battlefields_controlled",     # Seat of Power
    "discarded_energy", "it_might",      # Get Excited!, Last Breath
    "countered_energy", "killed_might", "self_assault",   # Riposte, Deathgrip, Lucian Gunslinger
    "battlefields_controlled", "friendly_units", "friendly_temporary_here",
    "friendly_tokens", "same_name_here_others",   # Illaoi, Spiderling
})

# Cost dict keys accepted by Loop._parse_activated_cost (activated abilities).
# NOTE: only these SIX keys are actually parsed by the engine today
# (loop.py:1019-1047). The v3 brief listed extra keys (exhaust, exhaust_self,
# recycle_from_trash, sacrifice_self, kill_friendly) as if supported — they are
# NOT. They are intentionally excluded here so the parser doesn't emit costs the
# engine would silently drop; the parser flags such costs to suggested_vocab
# instead. Add a key here only after the engine learns to parse + pay it.
KNOWN_ACTIVATED_COST_KEYS: frozenset[str] = frozenset({
    "energy", "power", "tap", "recycle", "sacrifice_self", "spend_xp",
    "disempower_self", "banish_from_trash", "discard", "discard_type", "spend_buff",
    "kill_other_token", "kill_other_friendly",
})

# Optional additional-cost (kicker) keys accepted by Loop._try_pay_additional_costs
# on an effect with trigger on_play / on_cast.
KNOWN_ADDITIONAL_COST_KEYS: frozenset[str] = frozenset({
    "energy", "power", "discard_cards",
    "kill_friendly_unit", "exhaust_friendly_unit", "return_friendly_unit",
})

# Engine verbs that aren't in effects.REGISTRY but are consumed elsewhere:
# - reduce_cost           read by Loop._cost_reduction
# - bonus_damage_here     battlefield passive read by EffectContext.deal_damage
# - ignore_deflect_here   battlefield passive read by Loop._deflect_tax
# - ignore_deflect        a spell's own "Ignore DEFLECT while paying" (Loop._deflect_tax)
# - move_tax_here         a deployed gear's tax to move to its battlefield (Loop._move_tax)
# - reduce_cost_here       battlefield passive read by Loop._bf_cost_reduction
# - play_from_top          on_reveal_from_top marker read by Loop._offer_reveal_from_top
# - ambush                 AMBUSH lane rule marker read by Loop._ambush_legal_lanes
# - move_ally_here_to_base on_first_unit_here marker read by Loop._fire_first_unit_here
# - show_off               SHOW OFF object marker (its target_filter) read by Loop._show_off
# - no_combat_damage       passive marker ("I don't deal combat damage") folded by Loop._apply_passive_grant
# - enter_ready            enter_ready_aura marker read by Loop._enters_ready
NON_HANDLER_VERBS: frozenset[str] = frozenset({
    "reduce_cost", "bonus_damage_here", "ignore_deflect_here", "ignore_deflect", "reduce_cost_here",
    "move_tax_here",
    "play_from_top", "ambush", "move_ally_here_to_base", "show_off", "no_combat_damage",
    "enter_ready", "double_equipment_might", "double_deathknell",
    # restrictions read where they apply (GameLoop._can_choose, _can_move_to_base,
    # _can_ready, _play_forbidden, _points_allowed, the Channel Phase, TEMPORARY)
    "cant_be_chosen", "cant_move_to_base", "cant_be_readied", "no_moves_to_base_from_here",
    "warden_no_ready", "play_restriction", "opponents_cant_gain_points",
    "no_score_before_turn", "early_score_draws", "channel_only_one", "no_temporary_here",
    "victory_score_plus",       # Aspirant's Climb: read when the game is built
    # damage and combat rules (GameLoop._take_damage, _combat_mods, combat cleanup)
    "spell_bonus_damage", "no_damage_if_moved_twice", "prevent_enemy_spell_damage",
    "lone_defender_minus", "lone_defender_bonus", "attacking_with_another_bonus", "ignore_tank_here",
    "tie_recall_all",
    # battlefield cost rules (GameLoop._destination_discount, _gear_ability_discount,
    # _pay_repeat) and Altar of Blood (_try_replace_death)
    "first_play_here_discount", "first_gear_ability_discount", "repeat_discount", "altar_of_blood",
    # Detonation Amplifier, Jarvan IV Martial Paragon, Mel Newly Awakened,
    # Renekton Brute (GameLoop._route_deaths, _play_timing, _uncounterable,
    # _extra_might_reduction, _recompute_passives)
    "double_deathknell_here", "deploy_gear_action", "uncounterable", "extra_might_reduction",
    "empower_at_might", "repeat_costs",
    # Origins: GameLoop._try_replace_death (Sett The Boss), _combat_mods (Wielder
    # of Water), _recompute_passives (Leona Zealot), buff_unit (Lee Sin Ascetic),
    # _cost_extras (Wallop, Call to Glory)
    "sett_save", "lone_fighter_bonus", "stunned_enemies_here_minus", "unlimited_buffs",
    "spend_buff_free", "discard_for_energy", "return_gear_for_energy",
    # Spiritforged: Soraka Wanderer, Ezreal Prodigy, Jax Unmatched, Renata Glasc
    # Chem-Baroness (GameLoop._try_replace_death, _pay_one_additional_cost,
    # _quick_draw, _gold_bonus)
    "protect_weaker_here", "cheaper_optional_costs", "equipment_quick_draw", "gold_bonus",
    # Unleashed: Red Brambleback, Blue Sentinel, Vilemaw, Elder Dragon
    "double_conquer_here", "double_hold_here", "weaker_enemies_no_damage", "lethal_damage",
    # Vendetta: Ambessa The Wolf, Gangplank Naval, Jagged Cutlass, Decree of Rage
    "no_damage_outside_combat", "gangplank_redirect", "unmovable_by_enemies", "cant_be_countered",
    # Equipment rules (UnitInPlay.tags, _apply_equipment_conditions, scoring)
    "grant_tag", "equip_conditional_might", "hold_conquer_swap",
    "copy_unit_text",           # Svellsongur: GameLoop._card_effects, UnitInPlay.keyword_value
    "look_before_reveal",       # Void Hatchling: GameLoop._before_deck_reveal
    "enemy_spell_tax",          # Helm of Suppression: GameLoop._enemy_spell_tax
    # where units may be played (GameLoop._unit_play_destinations, _play_unit)
    "play_location", "play_location_aura", "warden_only_base", "no_unit_plays_here",
    "accelerate_non_hand",
    "spells_repeat_in_showdown", "reaction_tax_in_showdown", "channel_plus_one",
    "spells_reaction_in_showdown",
    "sacrifice_instead_of_dying", "mech_instead_of_tokens", "double_tokens_once",
    # cost rules (GameLoop._cost_extras, _effective_cost, _adjust_ability_cost,
    # _play_forbidden, _destination_surcharge, hiding)
    "spend_buffs_for_power", "kill_tokens_for_power", "spend_xp_for_energy",
    "reduce_cost_not_from_hand", "gear_discount_once", "vex_cheerless", "empower_discount_here",
    "dragon_roost", "requires_friendly_gear", "requires_pet", "hide_for_energy",
    "no_enemy_reveals_here",
    "extra_facedown_slot",      # Bandle Tree, Bushwhack Trap: GameLoop._facedown_capacity
    "copy_tap_abilities", "group_move_toll", "jhin_pile", "zero_point_overflow", "rippers_bay",
})
