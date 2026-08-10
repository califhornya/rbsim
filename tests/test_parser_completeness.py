"""Guards the DISEASE-A completeness heuristic in scripts/generate_effects.py.

`check_completeness` is a safety net that flags cards whose emitted effect count
looks too low for the number of clauses in the printed text (the "kill X, then do
Y" / two-ability drop that validation alone can't catch, because a single valid
effect passes vocab checks). It is deliberately biased toward flagging — these
tests pin that it (a) catches known multi-clause drops, (b) leaves clean single-
and multi-effect parses alone, and (c) never counts parenthetical reminder text as
a clause.
"""
from scripts.generate_effects import check_completeness


def _card(effect, effects, effect_equipped=None):
    """A minimal (raw-text, parsed-entry) pair; here the same dict plays both roles."""
    return {"effect": effect, "effect_equipped": effect_equipped, "effects": effects}


# --- (a) real DISEASE-A drops must flag -------------------------------------

def test_flags_then_clause_drop():
    # "Kill … Then, if … play this from trash" — clause 2 dropped.
    c = _card(
        "Kill a unit at a battlefield. Then, if it had 3 [might] or less, you may "
        "play this from your trash for [rune].",
        [{"effect": "kill_unit", "trigger": "on_cast"}],
    )
    assert check_completeness(c, c) is not None


def test_flags_second_ability_drop():
    # Nami: kicker STUN kept, entire "When I hold …" ability dropped.
    c = _card(
        "You may pay [calm] as an additional cost to play me. When you play me, if "
        "you paid the additional cost, STUN an enemy unit. When I hold, the next time "
        "you play a unit this turn, ready it and BUFF it.",
        [{"effect": "stun_unit", "trigger": "on_play"}],
    )
    assert check_completeness(c, c) is not None


def test_flags_activated_ability_drop():
    # Cursed Sarcophagus: on-play banish kept, "[tap]: play a banished unit" dropped.
    c = _card(
        "When you play this, banish all units from your trash. [tap]: Play a unit "
        "banished with this. (You must pay its costs.)",
        [{"effect": "banish_card", "trigger": "on_play"}],
    )
    assert check_completeness(c, c) is not None


# --- (b) clean parses must NOT flag -----------------------------------------

def test_no_flag_single_clause():
    c = _card(
        "When I attack, deal damage equal to my Might to an enemy here.",
        [{"effect": "deal_damage", "trigger": "on_attack"}],
    )
    assert check_completeness(c, c) is None


def test_no_flag_fully_parsed_multi_ability():
    # Kha'Zix Voidreaver: three sentences, three effects — complete.
    c = _card(
        "When you win a combat, gain 1 XP. Spend 1 XP, [tap]: Buff a unit. Spend 2 "
        "XP, [tap]: Move an exhausted friendly unit from a battlefield to its base.",
        [{"effect": "gain_xp"}, {"effect": "buff_unit"}, {"effect": "move_units_to_base"}],
    )
    assert check_completeness(c, c) is None


def test_no_flag_when_no_effects_emitted():
    # Zero effects is handled by other paths (empty/model-flagged) — not our job.
    c = _card("Choose one — • Deal 4 to a unit. • Kill a gear.", [])
    assert check_completeness(c, c) is None


# --- (c) reminder text in parentheses is never a clause ----------------------

def test_reminder_text_stripped_before_counting():
    # One real clause + a long parenthetical reminder → must not flag.
    c = _card(
        "Units here have +1 [might]. (Including attackers. This lasts only while they "
        "remain here; it is not a buff.)",
        [{"effect": "grant_might", "trigger": "passive"}],
    )
    assert check_completeness(c, c) is None
