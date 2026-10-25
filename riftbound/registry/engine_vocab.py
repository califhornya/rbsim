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
    "on_friendly_unit_played",
    "on_friendly_unit_death",
    "on_play_spell",
    "on_win_combat",
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
    "you_control_this_battlefield",      # "... if you control this battlefield" (DEPLOY gear, battlefields)
    "cards_in_hand_at_most",             # n: "if you have one or fewer cards in your hand"
    "first_turn_of_player",              # the actor's first turn of the game
    "rune_deck_empty",                   # "if your Rune Deck is empty"
    "enemy_alone_here",                  # "if an enemy unit is alone here"
    "one_on_one_here",                   # exactly one unit per side here ("one on one")
    "you_control_bf_with_exactly_n_units",  # n: "a battlefield with exactly two units there"
    "you_have_n_or_fewer_runes",         # n: "if you control 4 or fewer runes"
    "friendly_deployed_gear_here",       # "if there is a friendly gear with DEPLOY here"
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
})

# Conditions the engine recognizes but always evaluates to False (no context).
# Kept distinct so the loop guard can assert the full handled set while the parser
# never emits them.
SAFE_FALSE_CONDITIONS: frozenset[str] = frozenset({
    "excess_damage_at_least",
    "controller_has_facedown_card",
    "target_was_stunned",
})

# target_filter keys understood by effects._passes_filter.
KNOWN_FILTER_KEYS: frozenset[str] = frozenset({
    "exclude_self", "has_keyword", "lacks_keyword",
    "is_gear", "is_spell", "is_unit", "is_token",
    "subtype", "might_at_most", "might_at_least",
    # B2 additions
    "non_token", "is_buffed", "is_mighty", "might_less_than_self",
    "card_type", "is_legend", "is_champion",
    # Step 3 additions (KNOWN_ISSUES #14/#17): ready-state + gear energy cost.
    "is_exhausted", "is_ready", "energy_at_most", "energy_at_least",
    "power_at_most", "power_at_least",   # zone effects: "no more than [rune]" / "[rune][rune] or more"
})

# amount_source values understood by effects._amount.
KNOWN_AMOUNT_SOURCES: frozenset[str] = frozenset({
    "self_might", "trash_count", "points", "friendly_mighty_units",
    # B2 additions
    "controller_points", "opponent_points", "highest_might_friendly",
    "cards_in_hand", "enemies_here", "friendly_units_here",
    "n_friendly_with_tag", "n_distinct_tags_among_friendlies",
    # SHOW OFF (§832): the shown object's info, snapshotted as the card was played.
    "shown_might", "shown_power_cost", "shown_energy_cost",
    # Per-count cost reductions ("I cost [1] less for each ...").
    "cards_played_this_turn", "friendly_exhausted_units",
    "battlefields_conquered_this_turn", "hold_points_this_turn",
    "cards_with_my_name_in_trash",
})

# Cost dict keys accepted by Loop._parse_activated_cost (activated abilities).
# NOTE: only these SIX keys are actually parsed by the engine today
# (loop.py:1019-1047). The v3 brief listed extra keys (exhaust, exhaust_self,
# recycle_from_trash, sacrifice_self, kill_friendly) as if supported — they are
# NOT. They are intentionally excluded here so the parser doesn't emit costs the
# engine would silently drop; the parser flags such costs to suggested_vocab
# instead. Add a key here only after the engine learns to parse + pay it.
KNOWN_ACTIVATED_COST_KEYS: frozenset[str] = frozenset({
    "energy", "power", "tap", "recycle", "sacrifice", "spend_xp",
    "disempower_self",
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
# - ignore_deflect_here   battlefield passive read by Loop._deflect_surcharge
# - reduce_cost_here       battlefield passive read by Loop._bf_cost_reduction
# - play_from_top          on_reveal_from_top marker read by Loop._offer_reveal_from_top
# - ambush                 AMBUSH lane rule marker read by Loop._ambush_legal_lanes
# - move_ally_here_to_base on_first_unit_here marker read by Loop._fire_first_unit_here
# - show_off               SHOW OFF object marker (its target_filter) read by Loop._show_off
# - no_combat_damage       passive marker ("I don't deal combat damage") folded by Loop._apply_passive_grant
# - enter_ready            enter_ready_aura marker read by Loop._enters_ready
NON_HANDLER_VERBS: frozenset[str] = frozenset({
    "reduce_cost", "bonus_damage_here", "ignore_deflect_here", "reduce_cost_here",
    "play_from_top", "ambush", "move_ally_here_to_base", "show_off", "no_combat_damage",
    "enter_ready", "double_equipment_might",
})
