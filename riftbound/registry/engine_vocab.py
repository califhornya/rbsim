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
})

# amount_source values understood by effects._amount.
KNOWN_AMOUNT_SOURCES: frozenset[str] = frozenset({
    "self_might", "trash_count", "points", "friendly_mighty_units",
    # B2 additions
    "controller_points", "opponent_points", "highest_might_friendly",
    "cards_in_hand", "enemies_here", "friendly_units_here",
    "n_friendly_with_tag", "n_distinct_tags_among_friendlies",
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
})

# Optional additional-cost (kicker) keys accepted by Loop._try_pay_additional_costs
# on an effect with trigger on_play / on_cast.
KNOWN_ADDITIONAL_COST_KEYS: frozenset[str] = frozenset({
    "energy", "power", "discard_cards",
    "kill_friendly_unit", "exhaust_friendly_unit",
})

# Engine verbs that aren't in effects.REGISTRY but are consumed elsewhere:
# - reduce_cost           read by Loop._cost_reduction
# - bonus_damage_here     battlefield passive read by EffectContext.deal_damage
# - ignore_deflect_here   battlefield passive read by Loop._deflect_surcharge
NON_HANDLER_VERBS: frozenset[str] = frozenset({
    "reduce_cost", "bonus_damage_here", "ignore_deflect_here",
})
