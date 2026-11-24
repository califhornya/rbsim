//! A GameState from a canonical tree (riftbound/rs/canon.py canonical_state):
//! objects keyed by canonical id, references "#id". Used for hand-built
//! positions (audit tests) and copies made by Python.

use serde_json::{Map, Value};
use std::collections::HashMap;
use std::rc::Rc;

use crate::model::*;
use crate::pydict::PyDict;
use crate::registry::Registry;
use crate::rng::PyRandom;
use crate::types::*;

struct Ctx<'a> {
    objs: &'a Map<String, Value>,
    cards: HashMap<String, CardId>,
    units: HashMap<String, UnitId>,
    gear: HashMap<String, GearId>,
}

fn err(s: &str) -> String {
    format!("import: {s}")
}

fn side_of(v: &Value) -> Option<Side> {
    v.as_str().and_then(Side::from_str)
}

fn i64_of(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

fn rid(v: &Value) -> Option<&str> {
    v.as_str().and_then(|s| s.strip_prefix('#'))
}

impl<'a> Ctx<'a> {
    fn card(&self, v: &Value) -> Result<CardId, String> {
        let r = rid(v).ok_or_else(|| err(&format!("card ref {v}")))?;
        self.cards.get(r).copied().ok_or_else(|| err(&format!("no card {r}")))
    }
    fn ocard(&self, v: &Value) -> Result<Option<CardId>, String> {
        if v.is_null() { Ok(None) } else { self.card(v).map(Some) }
    }
    fn unit(&self, v: &Value) -> Result<UnitId, String> {
        let r = rid(v).ok_or_else(|| err(&format!("unit ref {v}")))?;
        self.units.get(r).copied().ok_or_else(|| err(&format!("no unit {r}")))
    }
    fn ounit(&self, v: &Value) -> Result<Option<UnitId>, String> {
        if v.is_null() { Ok(None) } else { self.unit(v).map(Some) }
    }
    fn cards(&self, v: &Value) -> Result<Vec<CardId>, String> {
        v.as_array().map(|a| a.iter().map(|x| self.card(x)).collect()).unwrap_or(Ok(Vec::new()))
    }
    fn units(&self, v: &Value) -> Result<Vec<UnitId>, String> {
        v.as_array().map(|a| a.iter().map(|x| self.unit(x)).collect()).unwrap_or(Ok(Vec::new()))
    }
}

fn side_dict_i(v: &Value) -> PyDict<Side, i64> {
    let mut d = PyDict::new();
    if let Some(o) = v.as_object() {
        for (k, x) in o {
            if let Some(s) = Side::from_str(k) {
                d.set(s, i64_of(x));
            }
        }
    }
    d
}

fn side_dict_pair(v: &Value) -> PyDict<Side, (i64, i64)> {
    let mut d = PyDict::new();
    if let Some(o) = v.as_object() {
        for (k, x) in o {
            if let Some(s) = Side::from_str(k) {
                d.set(s, (i64_of(&x[0]), i64_of(&x[1])));
            }
        }
    }
    d
}

fn arr2_i(v: &Value) -> [i64; 2] {
    [i64_of(&v["A"]), i64_of(&v["B"])]
}

fn arr2_b(v: &Value) -> [bool; 2] {
    [v["A"].as_bool().unwrap_or(false), v["B"].as_bool().unwrap_or(false)]
}

fn domain_dict_runes(v: &Value) -> PyDict<Domain, Vec<Rune>> {
    let mut d = PyDict::new();
    if let Some(rows) = v.get("$dict").and_then(|x| x.as_array()) {
        for row in rows {
            let dom = Domain::from_py(row[0].as_str().unwrap_or("")).unwrap();
            let runes: Vec<Rune> = row[1]
                .as_array()
                .map(|a| a.iter().map(|r| Rune { domain: dom, ready: r["$v"]["ready"].as_bool().unwrap_or(true) }).collect())
                .unwrap_or_default();
            d.set(dom, runes);
        }
    }
    d
}

fn domain_dict_i(v: &Value) -> PyDict<Domain, i64> {
    let mut d = PyDict::new();
    if let Some(rows) = v.get("$dict").and_then(|x| x.as_array()) {
        for row in rows {
            d.set(Domain::from_py(row[0].as_str().unwrap_or("")).unwrap(), i64_of(&row[1]));
        }
    }
    d
}

fn strs(v: &Value) -> Vec<String> {
    v.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect()).unwrap_or_default()
}

/// Build a GameState from a canonical tree; the RNG is seeded with `seed`
/// (a hand-built position's rng state is not carried).
pub fn from_canonical(reg: Rc<Registry>, tree: &Value, seed: i128) -> Result<GameState, String> {
    let objs = tree["objs"].as_object().ok_or_else(|| err("objs"))?;
    let root = &tree["root"];
    let mut gs = crate::setup::empty_state(reg.clone(), PyRandom::new(seed));
    let mut cx = Ctx { objs, cards: HashMap::new(), units: HashMap::new(), gear: HashMap::new() };
    // Cards first.
    for (cid, o) in objs {
        if o["$t"] == "Card" {
            let name = o["name"].as_str().unwrap_or("");
            let i = reg.index(name).ok_or_else(|| err(&format!("unknown card {name}")))?;
            let c = gs.new_card(i as u32);
            cx.cards.insert(cid.clone(), c);
        }
    }
    // Units and deployed gear (they reference cards).
    for (cid, o) in objs {
        if o["$t"] == "UnitInPlay" {
            let c = cx.card(&o["card"])?;
            let u = gs.new_unit(Unit::new(c));
            cx.units.insert(cid.clone(), u);
        } else if o["$t"] == "DeployedGear" {
            let c = cx.card(&o["card"])?;
            let g = gs.new_dgear(DGear { card: c, is_token: o["is_token"].as_bool().unwrap_or(false) });
            cx.gear.insert(cid.clone(), g);
        }
    }
    // Card dynamic fields.
    for (cid, o) in objs {
        if o["$t"] != "Card" {
            continue;
        }
        let c = cx.cards[cid];
        let mut card = gs.card(c).clone();
        card.tapped = o["tapped"].as_bool().unwrap_or(false);
        for (k, v) in o.as_object().unwrap() {
            match k.as_str() {
                "$t" | "name" | "tapped" => {}
                "is_token" => card.is_token = v.as_bool(),
                "_kicker_paid" => card.set_kicker(v.as_bool()),
                "_showed_off" => card.set_showed(v.as_bool()),
                "_shown" => card.shown = Some(v.clone()),
                "_owner" => card.owner = side_of(v),
                "_played_from" => card.played_from = v.as_str().map(|s| s.to_string()),
                "_named_spell" => card.named_spell = v.as_str().map(|s| s.to_string()),
                "_spent" => card.spent = v.as_i64(),
                "_power_paid" => card.power_paid = v.as_i64(),
                "_attached_turn" => card.attached_turn = v.as_i64(),
                "_attached_to" => card.attached_to = cx.ounit(v)?,
                "_hidden_bf" => card.hidden_bf = v.as_u64().map(|x| x as usize),
                "_graceful_from" => card.graceful_from = Some(Value::Array(Vec::new())),
                "_graceful_owed" => card.graceful_owed = Some(cx.units(v)?),
                "_graceful_prepaid" => card.graceful_prepaid = Some(v.clone()),
                "_granted_repeat" => card.granted_repeat = Some(v.clone()),
                "_repeat_paid" => card.repeat_paid = Some(v.clone()),
                "_repeat_extra" => card.repeat_extra = Some(v.clone()),
                "_play_pending" => card.play_pending = Some(v.clone()),
                "empowered" => card.empowered = v.as_bool(),
                "_flow_banish" => card.flow_banish = v.as_bool(),
                other => return Err(err(&format!("card attribute {other}"))),
            }
        }
        *gs.card_mut(c) = card;
    }
    // Unit fields.
    for (cid, o) in objs {
        if o["$t"] != "UnitInPlay" {
            continue;
        }
        let u = cx.units[cid];
        let mut x = gs.unit(u).clone();
        x.damage = i64_of(&o["damage"]);
        x.ready = o["ready"].as_bool().unwrap_or(false);
        x.bonus_might = i64_of(&o["bonus_might"]);
        x.temporary_might = i64_of(&o["temporary_might"]);
        x.gear = cx.cards(&o["gear"])?;
        x.stunned = o["stunned"].as_bool().unwrap_or(false);
        x.might_counters = i64_of(&o["might_counters"]);
        x.aura_might = i64_of(&o["aura_might"]);
        x.passive_might = i64_of(&o["passive_might"]);
        x.passive_keywords = strs(&o["passive_keywords"]);
        x.hidden = o["hidden"].as_bool().unwrap_or(false);
        x.empowered = o["empowered"].as_bool().unwrap_or(false);
        x.empower_times = i64_of(&o["empower_times"]);
        x.is_token = o["is_token"].as_bool().unwrap_or(false);
        x.no_combat_damage = o["no_combat_damage"].as_bool().unwrap_or(false);
        x.turn_keywords = strs(&o["turn_keywords"]);
        x.granted_keywords = strs(&o["granted_keywords"]);
        x.combat_keywords = strs(&o["combat_keywords"]);
        x.combat_might = i64_of(&o["combat_might"]);
        x.doomed_turn = i64_of(&o["doomed_turn"]);
        x.ward_turn = i64_of(&o["ward_turn"]);
        x.prevent_next_turn = i64_of(&o["prevent_next_turn"]);
        x.was_mighty = o["was_mighty"].as_bool().unwrap_or(false);
        x.ward_free = o["ward_free"].as_bool().unwrap_or(false);
        x.banish_if_dies_turn = i64_of(&o["banish_if_dies_turn"]);
        x.damaged_turn = i64_of(&o["damaged_turn"]);
        x.unmovable_by_enemies = o["unmovable_by_enemies"].as_bool().unwrap_or(false);
        x.win_xp_turn = i64_of(&o["win_xp_turn"]);
        x.cant_move_turn = i64_of(&o["cant_move_turn"]);
        x.equip_bonus_mult = o["equip_bonus_mult"].as_i64().unwrap_or(1);
        x.base_might_override = o["base_might_override"].as_i64();
        x.moves_this_turn = i64_of(&o["moves_this_turn"]);
        x.unchoosable = o["unchoosable"].as_bool().unwrap_or(false);
        x.cant_be_chosen_turn = i64_of(&o["cant_be_chosen_turn"]);
        x.no_move_to_base = o["no_move_to_base"].as_bool().unwrap_or(false);
        x.cant_ready = o["cant_ready"].as_bool().unwrap_or(false);
        x.spell_immune = o["spell_immune"].as_bool().unwrap_or(false);
        x.double_damage_turn = i64_of(&o["double_damage_turn"]);
        x.damage_shield = i64_of(&o["damage_shield"]);
        x.conquered_turn = i64_of(&o["conquered_turn"]);
        x.gear_unit = o["gear_unit"].as_bool().unwrap_or(false);
        if !o["turn_abilities"].as_array().map_or(true, |a| a.is_empty()) || !o["death_bonus"].is_null()
            || !o["borrowed"].is_null() || !o["copied_from"].is_null() || !o["extra_tags"].as_array().map_or(true, |a| a.is_empty())
        {
            return Err(err("unit fields outside the ported perimeter"));
        }
        *gs.unit_mut(u) = x;
    }
    // Battlefields.
    let bfs = root["battlefields"].as_array().ok_or_else(|| err("battlefields"))?;
    for (i, r) in bfs.iter().enumerate() {
        let o = &objs[rid(r).ok_or_else(|| err("bf ref"))?];
        let _ = i;
        let mut bf = Battlefield::new(cx.ocard(&o["card"])?);
        bf.units = [cx.units(&o["units_A"])?, cx.units(&o["units_B"])?];
        bf.contested_this_turn = o["contested_this_turn"].as_bool().unwrap_or(false);
        bf.scored_this_turn = [o["scored_this_turn_A"].as_bool().unwrap_or(false), o["scored_this_turn_B"].as_bool().unwrap_or(false)];
        bf.first_unit_here = [o["first_unit_here_A"].as_bool().unwrap_or(false), o["first_unit_here_B"].as_bool().unwrap_or(false)];
        bf.plays_here = side_dict_pair(&o["plays_here"]);
        bf.last_controller = side_of(&o["last_controller"]);
        bf.held_by = side_of(&o["held_by"]);
        bf.gained_control = side_of(&o["gained_control"]);
        bf.contested_by = side_of(&o["contested_by"]);
        bf.showdown_pending = o["showdown_pending"].as_bool().unwrap_or(false);
        bf.replaced = cx.ocard(&o["replaced"])?;
        for f in o["facedowns"].as_array().cloned().unwrap_or_default() {
            let v = &f["$v"];
            bf.facedowns.push(Facedown { card: cx.card(&v["card"])?, owner: side_of(&v["owner"]).unwrap(), turn_hidden: i64_of(&v["turn_hidden"]) });
        }
        bf.conquered_turn = side_dict_i(&o["conquered_turn"]);
        bf.excess_damage = side_dict_pair(&o["excess_damage"]);
        bf.combat_designated = cx.units(&o["combat_designated"]["$set"])?;
        bf.combat_started = o["combat_started"].as_bool().unwrap_or(false);
        bf.combat_attacker = side_of(&o["combat_attacker"]);
        for (s, k) in [(0, "gear_A"), (1, "gear_B")] {
            for g in o[k].as_array().cloned().unwrap_or_default() {
                let r = rid(&g).unwrap();
                bf.gear[s].push(cx.gear[r]);
            }
        }
        bf.kills = [i64_of(&o["kills_A"]), i64_of(&o["kills_B"])];
        bf.deaths = [i64_of(&o["deaths_A"]), i64_of(&o["deaths_B"])];
        if let Some(pc) = o.get("prev_controller") {
            bf.prev_controller = Some(side_of(pc));
        }
        gs.battlefields.push(bf);
    }
    // Players.
    for s in Side::BOTH {
        let p = &root[s.name()]["$v"];
        let deck = &p["deck"]["$v"];
        let rd = &p["rune_deck"]["$v"];
        let runes: Vec<Rune> = rd["runes"]
            .as_array()
            .map(|a| a.iter().map(|r| Rune { domain: Domain::from_py(r["$v"]["domain"].as_str().unwrap()).unwrap(), ready: r["$v"]["ready"].as_bool().unwrap_or(true) }).collect())
            .unwrap_or_default();
        let mut pl = Player::new(s, Deck { cards: cx.cards(&deck["cards"])?, known_top: cx.cards(&deck["known_top"])? },
                                 RuneDeck { runes, unseen: rd["unseen"].as_i64() });
        pl.hp = p["hp"].as_i64().unwrap_or(10);
        pl.hand = cx.cards(&p["hand"])?;
        pl.hand_public = cx.cards(&p["hand_public"])?;
        pl.trash = cx.cards(&p["trash"])?;
        pl.banished = cx.cards(&p["banished"])?;
        pl.base_gear = cx.cards(&p["base_gear"])?;
        pl.rune_energy = i64_of(&p["rune_energy"]);
        pl.pool_energy = i64_of(&p["pool_energy"]);
        pl.earmarked_energy_showdown = i64_of(&p["earmarked_energy_showdown"]);
        pl.earmarked_power_gear = i64_of(&p["earmarked_power_gear"]);
        pl.earmarked_power_spell = i64_of(&p["earmarked_power_spell"]);
        pl.earmarked_power_permanent = i64_of(&p["earmarked_power_permanent"]);
        pl.earmarked_energy_spell = i64_of(&p["earmarked_energy_spell"]);
        pl.earmarked_energy_unit = i64_of(&p["earmarked_energy_unit"]);
        pl.rune_pool = domain_dict_runes(&p["rune_pool"]);
        pl.power_pool = domain_dict_i(&p["power_pool"]);
        pl.floating_power = domain_dict_i(&p["floating_power"]);
        pl.power_spent_this_turn = i64_of(&p["power_spent_this_turn"]);
        pl.draws_this_turn = i64_of(&p["draws_this_turn"]);
        pl.base_units = cx.units(&p["base_units"])?;
        pl.runes_recycled = p.get("runes_recycled").and_then(|v| v.as_i64());
        gs.players[s.idx()] = pl;
    }
    let r = root;
    gs.turn = i64_of(&r["turn"]);
    gs.max_turns = i64_of(&r["max_turns"]);
    gs.active = side_of(&r["active"]).unwrap();
    gs.champion = [cx.ocard(&r["champion_A"])?, cx.ocard(&r["champion_B"])?];
    gs.legend = [cx.ocard(&r["legend_A"])?, cx.ocard(&r["legend_B"])?];
    gs.legend_unit = [cx.ounit(&r["legend_unit_A"])?, cx.ounit(&r["legend_unit_B"])?];
    gs.points = [i64_of(&r["points_A"]), i64_of(&r["points_B"])];
    gs.victory_score = i64_of(&r["victory_score"]);
    gs.winner = side_of(&r["winner"]);
    gs.champion_deployed = [r["champion_A_deployed"].as_bool().unwrap_or(false), r["champion_B_deployed"].as_bool().unwrap_or(false)];
    if !r["chain"].as_array().map_or(true, |a| a.is_empty()) {
        return Err(err("a position with a chain"));
    }
    gs.pending_move = r["pending_move"].as_array().map(|a| (a[0].as_u64().unwrap() as usize, side_of(&a[1]).unwrap()));
    gs.staged_showdowns = r["staged_showdowns"].as_array().map(|a| a.iter().map(|x| (x[0].as_u64().unwrap() as usize, side_of(&x[1]).unwrap())).collect()).unwrap_or_default();
    gs.showdown_active = r["showdown_active"].as_bool().unwrap_or(false);
    gs.showdown_bf_idx = r["showdown_bf_idx"].as_u64().map(|x| x as usize);
    gs.showdown_attacker = side_of(&r["showdown_attacker"]);
    gs.focus_player = side_of(&r["focus_player"]);
    gs.xp = [i64_of(&r["xp_A"]), i64_of(&r["xp_B"])];
    gs.cards_played_this_turn = arr2_i(&r["cards_played_this_turn"]);
    gs.spells_played_this_turn = arr2_i(&r["spells_played_this_turn"]);
    gs.played_cards_this_turn = [cx.cards(&r["played_cards_this_turn"]["A"])?, cx.cards(&r["played_cards_this_turn"]["B"])?];
    gs.enemy_choices_this_turn = arr2_i(&r["enemy_choices_this_turn"]);
    gs.xp_gained_turn = side_dict_i(&r["xp_gained_turn"]);
    gs.no_spell_damage_turn = i64_of(&r["no_spell_damage_turn"]);
    gs.decree_turn = i64_of(&r["decree_turn"]);
    gs.spell_spent = side_dict_pair(&r["spell_spent"]);
    gs.move_group = r["move_group"].as_array().map(|a| (i64_of(&a[0]), side_of(&a[1]).unwrap(), a[2].as_u64().unwrap() as usize, i64_of(&a[3])));
    gs.died_in_beginning = side_dict_i(&r["died_in_beginning"]);
    gs.in_beginning_phase = r["in_beginning_phase"].as_bool().unwrap_or(false);
    gs.runes_at_beginning = (i64_of(&r["runes_at_beginning"][0]), side_dict_i(&r["runes_at_beginning"][1]));
    gs.in_ending_phase = r["in_ending_phase"].as_bool().unwrap_or(false);
    gs.turns_taken = arr2_i(&r["turns_taken"]);
    gs.units_enter_ready_turn = arr2_i(&r["units_enter_ready_turn"]);
    gs.next_units_enter_ready = arr2_i(&r["next_units_enter_ready"]);
    gs.friendly_unit_died_this_turn = arr2_b(&r["friendly_unit_died_this_turn"]);
    gs.friendly_gear_died_this_turn = arr2_b(&r["friendly_gear_died_this_turn"]);
    gs.discarded_this_turn = arr2_b(&r["discarded_this_turn"]);
    gs.cards_burned_this_turn = arr2_i(&r["cards_burned_this_turn"]);
    gs.conquered_this_turn = arr2_i(&r["conquered_this_turn"]);
    gs.hold_points_this_turn = arr2_i(&r["hold_points_this_turn"]);
    // once_per_turn_used: (card, idx) and (tag, side) keys
    if let Some(rows) = r["once_per_turn_used"].get("$dict").and_then(|x| x.as_array()) {
        for row in rows {
            let k = &row[0];
            let key = match (&k[0], &k[1]) {
                (Value::String(s), Value::String(sd)) if !s.starts_with('#') => OnceK::Named(s.clone(), Side::from_str(sd).unwrap()),
                (c, Value::Number(n)) => OnceK::Card(cx.card(c)?, OnceKey::Idx(n.as_i64().unwrap())),
                _ => return Err(err("once_per_turn_used key")),
            };
            gs.once_per_turn_used.set(key, i64_of(&row[1]));
        }
    }
    for k in ["next_card_discounts", "delayed_effects", "delayed_main", "held_hostage", "turn_cost_changes", "extra_turns", "conquer_return"] {
        let v = &r[k];
        let empty = match v {
            Value::Array(a) => a.is_empty(),
            Value::Object(o) => o.values().all(|x| x.as_array().map_or(true, |a| a.is_empty())),
            _ => true,
        };
        if !empty {
            return Err(err(&format!("{k} outside the ported perimeter")));
        }
    }
    Ok(gs)
}
